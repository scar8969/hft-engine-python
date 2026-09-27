"""Shared models: MarketData, Order, Trade, enums."""
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    NEW = "NEW"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass
class MarketData:
    """One OHLCV bar."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Order:
    symbol: str
    side: OrderSide
    price: float
    volume: int
    timestamp: datetime
    status: OrderStatus = OrderStatus.NEW
    reason: str = ""


@dataclass
class Trade:
    """A closed round-trip (entry -> exit)."""
    symbol: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    volume: int
    pnl: float
    pnl_pct: float
