"""Broker router — order lifecycle (NEW → ACK → FILLED/REJECTED) with three backends:

- dryrun:  simulated fills at last price + slippage (default, no keys needed)
- alpaca:  real paper-trading orders via alpaca-py (ALPACA_API_KEY/SECRET)
- direct:  direct marketable order simulation with queue-position modeling

Every order is journaled to the StateStore and idempotent by client_id.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from .state import StateStore

ORDER_STATUSES = ("NEW", "ACK", "PARTIAL", "FILLED", "REJECTED", "CANCELED")


class BrokerError(Exception):
    pass


class OrderRouter:
    def __init__(self, store: StateStore, backend: str = "dryrun",
                 slippage_bps: float = 2.0, fill_latency_ms: float = 5.0):
        self.store = store
        self.backend = backend
        self.slippage_bps = slippage_bps
        self.fill_latency_ms = fill_latency_ms  # simulated exchange latency
        self._client = None
        if backend == "alpaca":
            self._init_alpaca()

    # ── alpaca ──────────────────────────────────────────────────────
    def _init_alpaca(self):
        import os
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide as AOS, TimeInForce
            self._alpaca = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
            self._AOS = AOS
            self._MarketOrderRequest = MarketOrderRequest
            self._TIF = TimeInForce
        except ImportError:
            raise BrokerError("pip install alpaca-py for the alpaca backend")
        except KeyError:
            raise BrokerError("set ALPACA_API_KEY and ALPACA_SECRET_KEY (paper keys)")

    # ── order lifecycle ─────────────────────────────────────────────
    def _new_order(self, symbol: str, side: str, qty: float, price: float | None,
                   client_id: str | None = None) -> dict:
        oid = f"{client_id or uuid.uuid4().hex}"
        order = {
            "id": oid, "client_id": client_id, "symbol": symbol, "side": side,
            "qty": qty, "price": price, "status": "NEW",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "filled_qty": 0, "avg_fill": None, "latency_ms": None, "reason": None,
        }
        self.store.upsert_order(order)
        return order

    def _transition(self, order: dict, status: str, **kw) -> dict:
        order.update(status=status, **kw)
        self.store.upsert_order(order)
        return order

    def submit(self, symbol: str, side: str, qty: float, price: float | None = None,
               client_id: str | None = None) -> dict:
        """Submit an order. Idempotent: same client_id returns the existing order."""
        if client_id:
            existing = self.store.get_order(client_id)
            if existing and existing["status"] in ("NEW", "ACK", "PARTIAL"):
                return existing

        order = self._new_order(symbol, side, qty, price, client_id)
        t0 = time.perf_counter()

        if self.backend == "alpaca":
            order = self._submit_alpaca(order)
        elif self.backend == "dryrun":
            order = self._submit_dryrun(order)
        else:  # direct
            order = self._submit_direct(order)

        order["latency_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        self.store.upsert_order(order)
        return order

    # ── dryrun: simulate exchange ack + fill ────────────────────────
    def _submit_dryrun(self, order: dict) -> dict:
        order = self._transition(order, "ACK")
        time.sleep(self.fill_latency_ms / 1000)
        px = order["price"] or 100.0
        slip = px * self.slippage_bps / 10_000
        fill = px + slip if order["side"] == "BUY" else px - slip
        order = self._transition(order, "FILLED", filled_qty=order["qty"], avg_fill=round(fill, 4))
        self.store.add_trade(order["symbol"], order["side"], order["qty"], round(fill, 4), order["id"])
        self._apply_position(order["symbol"], order["side"], order["qty"], fill)
        return order

    # ── direct: marketable order with queue modeling ────────────────
    def _submit_direct(self, order: dict) -> dict:
        order = self._transition(order, "ACK")
        # simulated queue position: partial fills until filled
        remaining = order["qty"]
        filled = 0.0
        fills = []
        while remaining > 0:
            time.sleep(self.fill_latency_ms / 1000)
            chunk = min(remaining, max(1.0, remaining * 0.4))
            px = order["price"] or 100.0
            slip = px * self.slippage_bps / 10_000
            fill = px + slip if order["side"] == "BUY" else px - slip
            fills.append((chunk, fill))
            remaining -= chunk
            filled += chunk
            if remaining > 0:
                order = self._transition(order, "PARTIAL", filled_qty=round(filled, 4))
        avg = sum(c * p for c, p in fills) / filled
        order = self._transition(order, "FILLED", filled_qty=round(filled, 4), avg_fill=round(avg, 4))
        for chunk, fill in fills:
            self.store.add_trade(order["symbol"], order["side"], chunk, round(fill, 4), order["id"])
        self._apply_position(order["symbol"], order["side"], filled, avg)
        return order

    # ── alpaca ──────────────────────────────────────────────────────
    def _submit_alpaca(self, order: dict) -> dict:
        side = self._AOS.BUY if order["side"] == "BUY" else self._AOS.SELL
        req = self._MarketOrderRequest(
            symbol=order["symbol"], qty=order["qty"], side=side, time_in_force=self._TIF.DAY,
        )
        resp = self._client.submit_order(req)
        order = self._transition(order, "ACK", id=resp.id)
        # poll once for fill (paper fills fast)
        for _ in range(10):
            time.sleep(0.2)
            status = self._client.get_order_by_id(resp.id)
            if status.status in ("filled", "partially_filled"):
                filled = float(status.filled_qty)
                avg = float(status.filled_avg_price)
                order = self._transition(order, "FILLED", filled_qty=filled, avg_fill=avg)
                self.store.add_trade(order["symbol"], order["side"], filled, avg, order["id"])
                self._apply_position(order["symbol"], order["side"], filled, avg)
                return order
            if status.status in ("rejected", "canceled", "expired"):
                return self._transition(order, "REJECTED", reason=status.status)
        return self._transition(order, "ACK")  # still working

    # ── position tracking ───────────────────────────────────────────
    def _apply_position(self, symbol: str, side: str, qty: float, price: float):
        pos = self.store.get_position(symbol)
        cur_qty = pos["qty"] if pos else 0.0
        cur_avg = pos["avg_price"] if pos else 0.0
        if side == "BUY":
            new_qty = cur_qty + qty
            new_avg = (cur_avg * cur_qty + price * qty) / new_qty if new_qty else 0.0
        else:
            new_qty = cur_qty - qty
            new_avg = cur_avg if new_qty != 0 else 0.0
        self.store.set_position(symbol, round(new_qty, 4), round(new_avg, 4))

    def flatten(self, symbol: str, price: float | None = None) -> dict | None:
        """Close the position in symbol (marketable). Returns the order or None."""
        pos = self.store.get_position(symbol)
        if not pos or pos["qty"] == 0:
            return None
        side = "SELL" if pos["qty"] > 0 else "BUY"
        return self.submit(symbol, side, abs(pos["qty"]), price)
