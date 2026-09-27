"""OrderManager: fills orders against the bar, tracks position + equity."""
from typing import List, Optional

from .models import Order, OrderSide, Trade


class OrderManager:
    def __init__(self, initial_capital: float = 10_000.0,
                 commission: float = 0.0, slippage_bps: float = 0.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.position = 0          # shares held
        self.avg_entry = 0.0       # avg cost of current position
        self.trades: List[Trade] = []
        self.equity_curve: List[tuple] = []  # (timestamp, equity)
        self._open_entry: Optional[tuple] = None  # (time, price, volume, symbol)
        self.commission = commission          # $ per order
        self.slippage_bps = slippage_bps      # basis points of adverse slippage
        self.total_fees = 0.0

    def _fill_price(self, order: Order, side: OrderSide) -> float:
        """Apply slippage: buyers pay more, sellers receive less."""
        slip = order.price * self.slippage_bps / 10_000
        return order.price + slip if side == OrderSide.BUY else order.price - slip

    def place_order(self, order: Order, bar_close: float):
        """Execute a filled order at the bar close (with slippage + commission)."""
        if order.side == OrderSide.BUY:
            fill = self._fill_price(order, OrderSide.BUY)
            cost = fill * order.volume + self.commission
            self.cash -= cost
            self.position += order.volume
            self.avg_entry = ((self.avg_entry * (self.position - order.volume)) + fill * order.volume) / self.position
            self._open_entry = (order.timestamp, fill, order.volume, order.symbol)
            self.total_fees += self.commission
        else:  # SELL
            fill = self._fill_price(order, OrderSide.SELL)
            proceeds = fill * order.volume - self.commission
            self.cash += proceeds
            self.position -= order.volume
            self.total_fees += self.commission
            if self._open_entry:
                entry_t, entry_p, vol, sym = self._open_entry
                pnl = (fill - entry_p) * vol - self.commission
                pnl_pct = (fill / entry_p - 1) * 100
                self.trades.append(Trade(
                    symbol=sym, entry_time=entry_t, entry_price=entry_p,
                    exit_time=order.timestamp, exit_price=fill, volume=vol,
                    pnl=pnl, pnl_pct=pnl_pct,
                ))
                self._open_entry = None

    def mark_to_market(self, timestamp, close: float):
        equity = self.cash + self.position * close
        self.equity_curve.append((timestamp, equity))

    def finalize(self, last_close: float, symbol: str | None = None):
        """Close any open position at the last price so metrics are clean."""
        if self.position > 0 and self._open_entry:
            entry_t, entry_p, vol, sym = self._open_entry
            pnl = (last_close - entry_p) * vol - self.commission
            self.trades.append(Trade(
                symbol=symbol or sym, entry_time=entry_t, entry_price=entry_p,
                exit_time=None, exit_price=last_close, volume=vol,
                pnl=pnl, pnl_pct=(last_close / entry_p - 1) * 100,
            ))
            self._open_entry = None
