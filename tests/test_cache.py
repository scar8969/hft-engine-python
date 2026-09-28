"""yfinance cache layer — save/load round-trip, TTL, fallback."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest

from engine import cache


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "TTL_SECONDS", 3600)
    yield tmp_path


def test_save_load_round_trip(tmp_cache):
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0]})
    cache.save("AAPL", "2023-01-01", "2024-01-01", df)
    out = cache.load("AAPL", "2023-01-01", "2024-01-01")
    assert out is not None
    assert list(out["Close"]) == [1.0, 2.0, 3.0]


def test_miss_returns_none(tmp_cache):
    assert cache.load("MSFT", "2020-01-01", "2021-01-01") is None


def test_expired_returns_none(tmp_cache, monkeypatch):
    df = pd.DataFrame({"Close": [1.0]})
    cache.save("AAPL", "2023-01-01", "2024-01-01", df)
    monkeypatch.setattr(cache, "TTL_SECONDS", -1)  # force expiry
    assert cache.load("AAPL", "2023-01-01", "2024-01-01") is None


def test_corrupt_cache_returns_none(tmp_cache):
    (tmp_cache / "AAPL_2023-01-01_2024-01-01.parquet").write_bytes(b"not parquet")
    assert cache.load("AAPL", "2023-01-01", "2024-01-01") is None
