"""Multi-symbol live trading — fans out to N single-symbol LiveEngines sharing one store.

Keeps the single-symbol LiveEngine untouched (its tests + API path stay valid);
this wrapper gives the portfolio view: per-symbol positions, one kill switch,
flatten-all, and a combined status.
"""
from __future__ import annotations

from .live_engine import LiveEngine
from .state import StateStore


class MultiSymbolEngine:
    def __init__(self, symbols: list[str], store: StateStore, backend: str = "dryrun",
                 strategy: str = "sma", fast: int = 20, slow: int = 50,
                 threshold: float = 100.0, rsi_period: int = 14,
                 oversold: float = 30.0, overbought: float = 70.0,
                 mom_period: int = 50, qty: int = 10,
                 max_position: int = 100, max_exposure: float = 100_000.0,
                 gateway_backend: str = "poll"):
        self.symbols = [s.upper() for s in symbols]
        self.store = store
        self.backend = backend
        self.engines: dict[str, LiveEngine] = {}
        for sym in self.symbols:
            self.engines[sym] = LiveEngine(
                sym, store, backend=backend, strategy=strategy,
                fast=fast, slow=slow, threshold=threshold,
                rsi_period=rsi_period, oversold=oversold, overbought=overbought,
                mom_period=mom_period, qty=qty,
                max_position=max_position, max_exposure=max_exposure,
                gateway_backend=gateway_backend,
            )

    async def start(self):
        for eng in self.engines.values():
            await eng.start()

    async def stop(self):
        for eng in self.engines.values():
            await eng.stop()

    def kill(self):
        self.store.set_kill_switch(True)
        self.store.set_meta("engine_state", "killed")

    def flatten_all(self):
        """Close every symbol's position at market (sync, per-engine broker)."""
        for sym, eng in self.engines.items():
            pos = self.store.get_position(sym)
            if pos and pos["qty"] != 0:
                eng.broker.flatten(sym, eng._last_price)
        self.store.set_meta("engine_state", "flattened")

    def status(self) -> dict:
        return {
            "symbols": self.symbols,
            "running": any(e._running for e in self.engines.values()),
            "kill_switch": self.store.kill_switch(),
            "engine_state": self.store.get_meta("engine_state", "stopped"),
            "positions": {sym: self.store.get_position(sym) for sym in self.symbols},
            "cash": self.store.get_meta("cash", "100000"),
            "per_symbol": {sym: eng.status() for sym, eng in self.engines.items()},
        }
