"""Shared fixtures/helpers for the hft-python test suite (all offline, deterministic)."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import MarketData, Order, OrderSide  # noqa: E402


def make_bar(close: float, i: int = 0, symbol: str = "TEST") -> MarketData:
    ts = datetime(2024, 1, 1) + timedelta(days=i)
    return MarketData(symbol=symbol, timestamp=ts,
                      open=close, high=close * 1.01, low=close * 0.99,
                      close=close, volume=1000.0)


def make_bars(closes, symbol: str = "TEST"):
    return [make_bar(c, i, symbol) for i, c in enumerate(closes)]


class SignalCollector:
    """Captures orders emitted by a StrategyEngine."""

    def __init__(self, engine):
        self.orders = []
        engine.on_signal = self.orders.append

    @property
    def sides(self):
        return [o.side for o in self.orders]

    @property
    def prices(self):
        return [o.price for o in self.orders]

    @property
    def volumes(self):
        return [o.volume for o in self.orders]


def feed(engine, closes):
    for i, c in enumerate(closes):
        engine.on_market_data(make_bar(c, i))


def make_order(side=OrderSide.BUY, price=100.0, volume=10, symbol="TEST") -> Order:
    return Order(symbol=symbol, side=side, price=price, volume=volume,
                 timestamp=datetime(2024, 1, 1))
