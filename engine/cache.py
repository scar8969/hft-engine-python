"""yfinance download cache — avoids repeated network calls + rate limits.

Caches the raw DataFrame to parquet under ~/.hft_cache/ keyed by
symbol/start/end, with a TTL (default 1 day). Falls back to network
on any cache miss or read error.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(os.environ.get("HFT_CACHE_DIR", Path.home() / ".hft_cache"))
TTL_SECONDS = 24 * 60 * 60  # 1 day


def _key(symbol: str, start: str, end: str) -> Path:
    safe = "".join(c if c.isalnum() else "_" for c in f"{symbol}_{start}_{end}")
    return CACHE_DIR / f"{safe}.parquet"


def load(symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """Return cached df if fresh, else None."""
    path = _key(symbol, start, end)
    try:
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > TTL_SECONDS:
            return None
        return pd.read_parquet(path)
    except Exception:
        return None


def save(symbol: str, start: str, end: str, df: pd.DataFrame):
    """Persist df to the cache (best-effort)."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_key(symbol, start, end))
    except Exception:
        pass
