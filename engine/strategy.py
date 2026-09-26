"""StrategyEngine: subscribes to market data, emits Order signals."""
from typing import Callable, List

from .models import MarketData, Order, OrderSide


class StrategyEngine:
    def __init__(self, strategy: str = "sma", fast: int = 20, slow: int = 50,
                 threshold: float = 100.0, rsi_period: int = 14,
                 oversold: float = 30.0, overbought: float = 70.0):
        self.strategy = strategy
        self.fast = fast
        self.slow = slow
        self.threshold = threshold
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.on_signal: Callable[[Order], None] = lambda o: None

        self._closes: List[float] = []
        self._in_position = False

    def on_market_data(self, data: MarketData):
        """Called by the engine on every bar. Emits BUY/SELL signals."""
        self._closes.append(data.close)

        if self.strategy == "sma":
            self._sma_logic(data)
        elif self.strategy == "threshold":
            self._threshold_logic(data)
        elif self.strategy == "rsi":
            self._rsi_logic(data)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    # --- strategies -----------------------------------------------------

    def _sma_logic(self, data: MarketData):
        if len(self._closes) < self.slow:
            return
        fast_ma = sum(self._closes[-self.fast:]) / self.fast
        slow_ma = sum(self._closes[-self.slow:]) / self.slow
        prev_fast = sum(self._closes[-self.fast - 1:-1]) / self.fast
        prev_slow = sum(self._closes[-self.slow - 1:-1]) / self.slow

        # golden cross: fast crosses above slow
        if prev_fast <= prev_slow and fast_ma > slow_ma and not self._in_position:
            self._emit(data, OrderSide.BUY)
        # death cross: fast crosses below slow
        elif prev_fast >= prev_slow and fast_ma < slow_ma and self._in_position:
            self._emit(data, OrderSide.SELL)

    def _threshold_logic(self, data: MarketData):
        """Parity with the original C# repo: buy when price < threshold, sell above."""
        if data.close < self.threshold and not self._in_position:
            self._emit(data, OrderSide.BUY)
        elif data.close >= self.threshold and self._in_position:
            self._emit(data, OrderSide.SELL)

    def _rsi_logic(self, data: MarketData):
        """Mean reversion: buy when RSI crosses below oversold, sell when it crosses above overbought."""
        rsi = self._rsi_wilder()
        if rsi is None:
            return
        prev = self._rsi_wilder(offset=1)
        if prev is None:
            return

        if prev >= self.oversold and rsi < self.oversold and not self._in_position:
            self._emit(data, OrderSide.BUY)
        elif prev <= self.overbought and rsi > self.overbought and self._in_position:
            self._emit(data, OrderSide.SELL)

    # --- indicators -----------------------------------------------------

    def _rsi_wilder(self, offset: int = 0) -> float | None:
        """Wilder-smoothed RSI over closes, optionally excluding the last `offset` bars."""
        closes = self._closes
        n = self.rsi_period
        if len(closes) <= n + offset:
            return None
        end = len(closes) - offset
        gains, losses = [], []
        for i in range(1, end):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0.0))
            losses.append(max(-d, 0.0))
        if len(gains) < n:
            return None
        avg_gain = sum(gains[:n]) / n
        avg_loss = sum(losses[:n]) / n
        for i in range(n, len(gains)):
            avg_gain = (avg_gain * (n - 1) + gains[i]) / n
            avg_loss = (avg_loss * (n - 1) + losses[i]) / n
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    # --- helpers --------------------------------------------------------

    def _emit(self, data: MarketData, side: OrderSide):
        order = Order(
            symbol=data.symbol,
            side=side,
            price=data.close,
            volume=10,  # fixed size, like the original
            timestamp=data.timestamp,
        )
        self._in_position = (side == OrderSide.BUY)
        self.on_signal(order)
