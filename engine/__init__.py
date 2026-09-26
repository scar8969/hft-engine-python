"""HFTEngine: wires the components together, event-driven like the C# original."""
from .market_data import MarketDataHandler
from .strategy import StrategyEngine
from .risk import RiskManager
from .order_manager import OrderManager
from .models import Order


class HFTEngine:
    def __init__(self, symbol: str, start: str, end: str,
                 strategy: str = "sma", fast: int = 20, slow: int = 50,
                 threshold: float = 100.0, initial_capital: float = 10_000.0,
                 commission: float = 0.0, slippage_bps: float = 0.0):
        self.market_data = MarketDataHandler(symbol, start, end)
        self.strategy = StrategyEngine(strategy, fast, slow, threshold)
        self.risk = RiskManager()
        self.orders = OrderManager(initial_capital, commission, slippage_bps)
        self.symbol = symbol

        # Wire up events (mirrors the C# event wiring)
        self.market_data.on_market_data = self.strategy.on_market_data
        self.strategy.on_signal = self._on_signal

    def _on_signal(self, order: Order):
        if self.risk.validate(order, self.orders.position):
            self.orders.place_order(order, order.price)

    def run(self):
        bars = self.market_data.connect()
        for bar in bars:
            self.market_data.process(bar)
            self.orders.mark_to_market(bar.timestamp, bar.close)
        if bars:
            self.orders.finalize(bars[-1].close)
        return self.orders
