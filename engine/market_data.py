"""MarketDataHandler: fetches OHLCV bars and emits MarketData events (like the C# websocket handler)."""
from typing import Callable, List

import pandas as pd
import yfinance as yf

from .models import MarketData


class MarketDataHandler:
    def __init__(self, symbol: str, start: str, end: str):
        self.symbol = symbol
        self.start = start
        self.end = end
        self.on_market_data: Callable[[MarketData], None] = lambda md: None

    def connect(self) -> List[MarketData]:
        """Pull daily bars from yfinance and convert to MarketData objects."""
        df = yf.download(
            self.symbol, start=self.start, end=self.end,
            progress=False, auto_adjust=True,
        )
        if df.empty:
            raise RuntimeError(f"No data returned for {self.symbol} {self.start}..{self.end}")

        # newer yfinance returns MultiIndex columns (('Open','AAPL'), ...) — flatten
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        bars: List[MarketData] = []
        for ts, row in df.iterrows():
            bars.append(MarketData(
                symbol=self.symbol,
                timestamp=ts.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            ))
        return bars

    def process(self, bar: MarketData):
        """Emit one bar to subscribers (event wiring)."""
        self.on_market_data(bar)
