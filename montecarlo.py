"""Monte Carlo confidence bands for backtest equity curves.

Resamples the daily return sequence N times (bootstrap) and computes
5th/50th/95th percentile equity paths — the standard way to show a
backtest isn't just luck.
"""
import numpy as np


def bootstrap(equity_curve, n=500, seed=42, pct=(5, 50, 95)):
    """Bootstrap-resample the equity curve's returns.

    Args:
        equity_curve: list of (timestamp, equity) tuples.
        n: number of resampled paths.
        seed: RNG seed for reproducibility.
        pct: percentiles to report.

    Returns:
        dict with keys f"p{p}" -> np.ndarray of length len(equities),
        plus "paths" (n x len) when requested via include_paths.
    """
    rng = np.random.default_rng(seed)
    equities = np.array([e for _, e in equity_curve], dtype=float)
    if len(equities) < 2:
        raise ValueError("equity curve too short for bootstrap (need >= 2 points)")

    rets = np.diff(equities) / equities[:-1]
    paths = np.empty((n, len(equities)))
    for i in range(n):
        boot = rng.choice(rets, size=len(rets), replace=True)
        paths[i] = equities[0] * np.concatenate(([1.0], np.cumprod(1 + boot)))

    out = {}
    for p in pct:
        out[f"p{p}"] = np.percentile(paths, p, axis=0)
    out["paths"] = paths
    out["final_p50"] = float(np.percentile(paths[:, -1], 50))
    out["final_p05"] = float(np.percentile(paths[:, -1], 5))
    out["final_p95"] = float(np.percentile(paths[:, -1], 95))
    return out
