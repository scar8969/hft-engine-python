"""API handler tests — pure functions, no HTTP server needed."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from api.handlers import backtest, orderflow, portfolio, strategies


class TestBacktest:
    def test_returns_metrics_and_curve(self, monkeypatch):
        import engine.market_data as md
        import pandas as pd
        import numpy as np

        idx = pd.date_range("2023-01-01", periods=100, freq="B")
        closes = 100 * (1.002 ** np.arange(100))
        df = pd.DataFrame({"Open": closes * 0.99, "High": closes * 1.02,
                           "Low": closes * 0.98, "Close": closes, "Volume": 1e6},
                          index=idx)
        monkeypatch.setattr(md.yf, "download", lambda *a, **k: df)

        r = backtest({"symbol": "AAPL", "start": "2023-01-01", "end": "2023-06-01"})
        assert "metrics" in r
        assert "equity_curve" in r
        assert "trades" in r
        assert len(r["metrics"]) >= 15  # rich metrics

    def test_multi_symbol_returns_combined(self, monkeypatch):
        import engine.market_data as md
        import pandas as pd
        import numpy as np

        idx = pd.date_range("2023-01-01", periods=100, freq="B")
        closes = 100 * (1.001 ** np.arange(100))
        df = pd.DataFrame({"Open": closes * 0.99, "High": closes * 1.02,
                           "Low": closes * 0.98, "Close": closes, "Volume": 1e6},
                          index=idx)
        monkeypatch.setattr(md.yf, "download", lambda *a, **k: df)

        r = backtest({"symbols": "AAPL,MSFT", "start": "2023-01-01", "end": "2023-06-01"})
        assert r["symbols"] == ["AAPL", "MSFT"]
        assert "combined" in r


class TestPortfolio:
    def test_returns_per_symbol_metrics(self, monkeypatch):
        import engine.market_data as md
        import pandas as pd
        import numpy as np

        idx = pd.date_range("2023-01-01", periods=100, freq="B")
        closes = 100 * (1.001 ** np.arange(100))
        df = pd.DataFrame({"Open": closes * 0.99, "High": closes * 1.02,
                           "Low": closes * 0.98, "Close": closes, "Volume": 1e6},
                          index=idx)
        monkeypatch.setattr(md.yf, "download", lambda *a, **k: df)

        r = portfolio({"symbols": "AAPL,MSFT,GOOGL"})
        assert r["symbols"] == ["AAPL", "MSFT", "GOOGL"]
        assert len(r["per_symbol"]) == 3
        assert "combined" in r


class TestStrategies:
    def test_returns_four_strategies(self, monkeypatch):
        import engine.market_data as md
        import pandas as pd
        import numpy as np

        idx = pd.date_range("2023-01-01", periods=100, freq="B")
        closes = 100 * (1.001 ** np.arange(100))
        df = pd.DataFrame({"Open": closes * 0.99, "High": closes * 1.02,
                           "Low": closes * 0.98, "Close": closes, "Volume": 1e6},
                          index=idx)
        monkeypatch.setattr(md.yf, "download", lambda *a, **k: df)

        r = strategies({"symbol": "AAPL"})
        assert set(r["strategies"].keys()) == {"sma", "rsi", "momentum", "threshold"}
        for s in r["strategies"].values():
            assert "return_pct" in s and "sharpe" in s and "equity" in s


class TestOrderflow:
    def test_returns_grid_or_fallback(self):
        r = orderflow({"symbol": "BTCUSDT", "bar_seconds": 60})
        assert "bars" in r and "levels" in r
        assert "buy" in r and "sell" in r
        assert len(r["buy"]) == len(r["bars"])
        assert len(r["levels"]) > 0
