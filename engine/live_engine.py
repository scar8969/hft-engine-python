"""Live trading engine orchestrator.

Wires: gateway (real-time feed) → strategy (signals) → risk (pre-trade checks)
→ broker router (order lifecycle) → state store (journal) → latency tracker.

Runs as a background asyncio task; exposes start/stop/flatten/kill for the API.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from .broker import OrderRouter
from .gateway import MarketGateway
from .latency import LatencyTracker
from .state import StateStore
from .strategy import StrategyEngine
from .models import MarketData, Order

logger = logging.getLogger("hft.live")


class LiveEngine:
    def __init__(self, symbol: str, store: StateStore, backend: str = "dryrun",
                 strategy: str = "sma", fast: int = 20, slow: int = 50,
                 threshold: float = 100.0, rsi_period: int = 14,
                 oversold: float = 30.0, overbought: float = 70.0,
                 mom_period: int = 50, qty: int = 10,
                 max_position: int = 100, max_exposure: float = 100_000.0,
                 gateway_backend: str = "poll",
                 max_drawdown_pct: float = 0.0, max_daily_loss_pct: float = 0.0):
        self.symbol = symbol.upper()
        self.store = store
        self.qty = qty
        self.max_position = max_position
        self.max_exposure = max_exposure
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self._peak_equity = 0.0
        self._day_start_equity = 0.0

        self.strategy = StrategyEngine(strategy, fast, slow, threshold,
                                       rsi_period, oversold, overbought, mom_period, qty=qty)
        self.broker = OrderRouter(store, backend=backend)
        self.latency = LatencyTracker()
        self.gateway = MarketGateway(symbol, backend=gateway_backend, on_tick=self._on_tick)

        self._running = False
        self._task = None
        self._last_price = None
        self._last_signal_ts = None
        self._tick_count = 0

        # wire strategy signals → risk → broker
        self.strategy.on_signal = self._on_signal

        # warm up indicators from history
        self._warmup()

    # ── warmup: feed history so indicators are ready ────────────────
    def _warmup(self, start: str = "2024-01-01"):
        try:
            from .market_data import MarketDataHandler
            bars = MarketDataHandler(self.symbol, start,
                                     datetime.now().strftime("%Y-%m-%d")).connect()
            for b in bars:
                self.strategy.on_market_data(b)
            logger.info("warmup: %d bars loaded for %s", len(bars), self.symbol)
        except Exception as e:
            logger.warning("warmup skipped (%s)", e)

    # ── risk: auto-kill on drawdown / daily loss ────────────────────
    def _check_drawdown(self, equity: float):
        """Engage the kill switch if equity breaches max drawdown or daily loss."""
        if self.store.kill_switch():
            return
        if self._peak_equity <= 0:
            self._peak_equity = equity
            self._day_start_equity = equity
            return
        if equity > self._peak_equity:
            self._peak_equity = equity
        if self.max_drawdown_pct > 0:
            dd = (self._peak_equity - equity) / self._peak_equity * 100
            if dd >= self.max_drawdown_pct:
                logger.warning("AUTO-KILL: drawdown %.1f%% >= %.1f%%", dd, self.max_drawdown_pct)
                self.kill()
                return
        if self.max_daily_loss_pct > 0 and self._day_start_equity > 0:
            day_loss = (self._day_start_equity - equity) / self._day_start_equity * 100
            if day_loss >= self.max_daily_loss_pct:
                logger.warning("AUTO-KILL: daily loss %.1f%% >= %.1f%%", day_loss, self.max_daily_loss_pct)
                self.kill()

    # ── tick handler ────────────────────────────────────────────────
    def _on_tick(self, tick: dict):
        self._last_price = tick["price"]
        bar = MarketData(
            symbol=self.symbol, timestamp=datetime.fromtimestamp(tick["ts_epoch"]),
            open=tick["price"], high=tick["price"], low=tick["price"],
            close=tick["price"], volume=tick.get("qty", 0.0),
        )
        self.strategy.on_market_data(bar)
        # throttle SQLite journaling: journal on first tick, then every 10th
        self._tick_count += 1
        if self._tick_count == 1 or self._tick_count % 10 == 0:
            self.store.set_meta("last_bar", json.dumps({"price": tick["price"], "ts": tick["ts"]}))
            pos = self.store.get_position(self.symbol)
            qty = pos["qty"] if pos else 0.0
            cash = float(self.store.get_meta("cash", "100000"))
            equity = round(cash + qty * tick["price"], 2)
            self.store.append_equity(equity)
            self._check_drawdown(equity)

    # ── signal → risk → broker ──────────────────────────────────────
    def _on_signal(self, order: Order):
        if self.store.kill_switch():
            return
        pos = self.store.get_position(self.symbol)
        cur_qty = pos["qty"] if pos else 0.0
        # both sides respect max_position (long AND short)
        if abs(cur_qty) + order.volume > self.max_position:
            return
        if order.price * order.volume > self.max_exposure:
            return
        # cash-sufficiency: BUY must not exceed available cash (short frees cash)
        if order.side.value == "BUY":
            cash = float(self.store.get_meta("cash", "100000"))
            if order.price * order.volume > cash:
                logger.warning("reject BUY %s: order value %.2f > cash %.2f",
                               self.symbol, order.price * order.volume, cash)
                return

        self._last_signal_ts = time.time()
        client_id = f"{self.symbol}-{order.side.value}-{int(time.time() * 1000)}"
        bro = self.broker.submit(self.symbol, order.side.value, order.volume,
                                 order.price, client_id=client_id)
        # latency: broker returns real ack/fill timestamps from the lifecycle
        self.latency.record(self._last_signal_ts, bro.get("ack_ts"), bro.get("fill_ts"),
                            (time.time() - self.gateway.last_tick_ts) if self.gateway.last_tick_ts else None)
    # ── lifecycle ───────────────────────────────────────────────────
    async def start(self):
        if self._running:
            return
        self._running = True
        self.store.set_meta("engine_state", "running")
        self.store.set_meta("started_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.store.set_meta("cash", str(float(self.store.get_meta("cash", "100000"))))
        self._task = asyncio.create_task(self.gateway.run())
        logger.info("engine running: %s strategy=%s backend=%s",
                    self.symbol, self.strategy.strategy, self.broker.backend)
        # keep the loop alive until stop() is called
        while self._running:
            await asyncio.sleep(0.5)

    async def stop(self):
        self._running = False
        self.gateway.stop()
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self.store.set_meta("engine_state", "stopped")
        logger.info("engine stopped")

    async def flatten(self):
        """Close all positions at market."""
        if self.store.kill_switch():
            return
        pos = self.store.get_position(self.symbol)
        if pos and pos["qty"] != 0:
            self.broker.flatten(self.symbol, self._last_price)
            self.store.set_meta("engine_state", "flattened")
            logger.info("flattened %s", self.symbol)

    def kill(self):
        self.store.set_kill_switch(True)
        self.store.set_meta("engine_state", "killed")
        logger.warning("KILL SWITCH ENGAGED — no new orders")

    def status(self) -> dict:
        return {
            "symbol": self.symbol,
            "running": self._running,
            "kill_switch": self.store.kill_switch(),
            "engine_state": self.store.get_meta("engine_state", "stopped"),
            "last_price": self._last_price,
            "feed": {
                "backend": self.gateway.backend,
                "last_tick": self.gateway.last_tick,
                "stale": self.gateway.is_stale(),
                "reconnects": self.gateway.reconnects,
            },
            "latency": self.latency.summary(),
            "strategy": self.strategy.strategy,
            "position": self.store.get_position(self.symbol),
            "cash": self.store.get_meta("cash", "100000"),
        }
