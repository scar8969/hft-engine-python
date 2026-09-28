"""Walk-forward optimization — parallel == serial determinism."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from optimize import param_grid, run_window


@pytest.fixture
def df():
    """Synthetic 300-bar frame so run_window has enough data."""
    import numpy as np
    import pandas as pd

    idx = pd.date_range("2022-01-01", periods=300, freq="B")
    closes = 100 * (1.005 ** np.arange(300))
    return pd.DataFrame({
        "Open": closes * 0.99, "High": closes * 1.02,
        "Low": closes * 0.98, "Close": closes, "Volume": 1_000_000,
    }, index=idx)


def test_param_grid_sizes():
    assert len(param_grid("sma")) == 9  # 3 fast x 3 slow, all f < s
    assert len(param_grid("rsi")) == 9
    assert len(param_grid("momentum")) == 4
    assert param_grid("threshold") == [{}]


def test_run_window_returns_metrics(df, monkeypatch):
    # run_window re-downloads via HFTEngine — mock yfinance to use our df
    import engine.market_data as md

    def fake_download(symbol, start=None, end=None, **kw):
        return df

    monkeypatch.setattr(md.yf, "download", fake_download)
    m = run_window("SYN", df, 0, 200, "sma", {"fast": 10, "slow": 50},
                   10_000.0, 1.0, 5.0)
    assert m is not None
    assert "total_return_pct" in m
    assert m["final_equity"] > 0


def test_parallel_matches_serial(df, monkeypatch):
    """Parallel sweep over the grid must pick the same best params as serial."""
    import engine.market_data as md

    def fake_download(symbol, start=None, end=None, **kw):
        return df

    monkeypatch.setattr(md.yf, "download", fake_download)
    from concurrent.futures import ProcessPoolExecutor

    grid = param_grid("sma")
    serial_best, serial_m = None, None
    for params in grid:
        m = run_window("SYN", df, 0, 200, "sma", params, 10_000.0, 1.0, 5.0)
        if m and (serial_m is None or m["total_return_pct"] > serial_m["total_return_pct"]):
            serial_best, serial_m = params, m

    with ProcessPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(run_window, "SYN", df, 0, 200, "sma", p, 10_000.0, 1.0, 5.0): p
                   for p in grid}
        par_best, par_m = None, None
        for fut in futures:
            m = fut.result()
            p = futures[fut]
            if m and (par_m is None or m["total_return_pct"] > par_m["total_return_pct"]):
                par_best, par_m = p, m

    assert par_best == serial_best
    assert par_m["total_return_pct"] == pytest.approx(serial_m["total_return_pct"])
