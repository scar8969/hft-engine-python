"""Real-time market data gateway with reconnection + heartbeat.

Backends:
- binance:  public WebSocket trade stream (crypto, no key) — real ticks
- poll:     yfinance polling fallback (equities, no key) — 1m bars

The gateway emits ticks to a callback and tracks feed health (last tick age,
reconnect count) so the engine can act on stale data.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import websockets


class FeedError(Exception):
    pass


class MarketGateway:
    def __init__(self, symbol: str, backend: str = "poll",
                 on_tick=None, poll_interval: float = 15.0):
        self.symbol = symbol.upper()
        self.backend = backend
        self.on_tick = on_tick or (lambda tick: None)
        self.poll_interval = poll_interval
        self.last_tick = None
        self.last_tick_ts = 0.0
        self.reconnects = 0
        self._running = False

    # ── health ──────────────────────────────────────────────────────
    def is_stale(self, max_age: float = 30.0) -> bool:
        return bool(self.last_tick_ts) and (time.time() - self.last_tick_ts) > max_age

    def _emit(self, price: float, ts: float | None = None, **kw):
        tick = {"symbol": self.symbol, "price": price,
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "ts_epoch": ts or time.time(), **kw}
        self.last_tick = tick
        self.last_tick_ts = time.time()
        self.on_tick(tick)

    # ── binance ws ──────────────────────────────────────────────────
    async def _binance_loop(self):
        url = f"wss://stream.binance.com:9443/ws/{self.symbol.lower()}@trade"
        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    while self._running:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        d = json.loads(raw)
                        if d.get("e") == "trade":
                            self._emit(float(d["p"]), d["T"] / 1000.0,
                                       qty=float(d["q"]), side="buy" if not d.get("m") else "sell")
            except (asyncio.TimeoutError, websockets.ConnectionClosed, OSError):
                self.reconnects += 1
                await asyncio.sleep(min(30, 2 ** min(self.reconnects, 5)))

    # ── yfinance poll ───────────────────────────────────────────────
    async def _poll_loop(self):
        import yfinance as yf
        while self._running:
            try:
                df = yf.download(self.symbol, period="1d", interval="1m",
                                 progress=False, auto_adjust=True)
                if df is not None and not df.empty:
                    if hasattr(df.columns, "levels"):  # MultiIndex flatten
                        df.columns = df.columns.get_level_values(0)
                    last = df.iloc[-1]
                    self._emit(float(last["Close"]))
            except Exception as e:
                print(f"[gateway] poll error: {e}", flush=True)
            await asyncio.sleep(self.poll_interval)

    async def run(self):
        self._running = True
        if self.backend == "binance":
            await self._binance_loop()
        else:
            await self._poll_loop()

    def stop(self):
        self._running = False
