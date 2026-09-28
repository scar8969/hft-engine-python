"""Footprint chart renderer — ATAS-style bid/ask volume per price level per bar.

Data sources:
  - history: Binance aggTrades REST (recent trades, no key)
  - live:    OrderFlowFeed from livefeed.py (real-time)

Renders:
  - footprint grid: rows = price levels, cols = bars, cell = buy/sell volume
  - cumulative delta line
  - volume profile (horizontal histogram)

Usage:
    python footprint.py --symbol BTCUSDT --bars 12 --bar-seconds 60
    python footprint.py --symbol ETHUSDT --bars 15 --bar-seconds 30 --out hero.png
"""
import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BINANCE_AGG = "https://api.binance.com/api/v3/aggTrades?symbol={sym}&limit={limit}"


def fetch_trades(symbol: str, limit: int = 1000):
    """Fetch recent aggregated trades from Binance REST."""
    url = BINANCE_AGG.format(sym=symbol.upper(), limit=limit)
    req = urllib.request.Request(url, headers={"User-Agent": "hft-python/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    trades = []
    for t in data:
        trades.append({
            "price": float(t["p"]),
            "qty": float(t["q"]),
            "side": "sell" if t["m"] else "buy",  # m=True -> buyer maker -> taker sell
            "ts": t["T"] / 1000.0,
        })
    return trades


def build_footprint(trades, bar_seconds: int = 60, tick_size: float | None = None):
    """Group trades into bars and price levels.

    Returns (bars, levels, grid) where:
      bars   = sorted list of bar start timestamps
      levels = sorted list of price levels (desc)
      grid   = {(bar_idx, level_idx): (buy_vol, sell_vol)}
    """
    if not trades:
        return [], [], {}
    if tick_size is None:
        # infer from price magnitude: 0.01 for <1000, 0.1 for <10000, 1 for >=10000
        px = trades[0]["price"]
        tick_size = 0.01 if px < 1000 else (0.1 if px < 10000 else 1.0)

    bars = sorted({int(t["ts"] // bar_seconds) * bar_seconds for t in trades})
    bar_idx = {b: i for i, b in enumerate(bars)}

    # price levels: round each trade price to nearest tick
    levels = sorted({round(t["price"] / tick_size) * tick_size for t in trades}, reverse=True)
    level_idx = {l: i for i, l in enumerate(levels)}

    grid = defaultdict(lambda: [0.0, 0.0])
    for t in trades:
        bi = bar_idx[int(t["ts"] // bar_seconds) * bar_seconds]
        li = level_idx[round(t["price"] / tick_size) * tick_size]
        if t["side"] == "buy":
            grid[(bi, li)][0] += t["qty"]
        else:
            grid[(bi, li)][1] += t["qty"]
    return bars, levels, dict(grid)


def render_footprint(bars, levels, grid, symbol: str, bar_seconds: int, out_path: str):
    """Render footprint grid + cumulative delta + volume profile."""
    n_bars, n_levels = len(bars), len(levels)
    if n_bars == 0 or n_levels == 0:
        raise ValueError("no data to render")

    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 2, width_ratios=[6, 1], height_ratios=[4, 1],
                          left=0.08, right=0.92, top=0.92, bottom=0.08, hspace=0.35, wspace=0.05)

    # ── main footprint grid ────────────────────────────────────────────
    ax = fig.add_subplot(gs[0, 0])
    cell = np.zeros((n_levels, n_bars))  # net delta per cell
    buy_vol = np.zeros((n_levels, n_bars))
    sell_vol = np.zeros((n_levels, n_bars))
    for (bi, li), (b, s) in grid.items():
        cell[li, bi] = b - s
        buy_vol[li, bi] = b
        sell_vol[li, bi] = s

    vmax = max(abs(cell.max()), abs(cell.min()), 1e-9)
    ax.imshow(cell, cmap="RdYlGn", aspect="auto", vmin=-vmax, vmax=vmax)

    # cell text: buy/sell volumes
    for li in range(n_levels):
        for bi in range(n_bars):
            b, s = buy_vol[li, bi], sell_vol[li, bi]
            if b == 0 and s == 0:
                continue
            color = "black" if abs(cell[li, bi]) / vmax < 0.55 else "white"
            ax.text(bi, li, f"{b:.1f}\n{s:.1f}", ha="center", va="center",
                    fontsize=6.5, color=color, linespacing=0.9)

    ax.set_xticks(range(n_bars))
    ax.set_xticklabels([datetime.fromtimestamp(b).strftime("%H:%M") for b in bars],
                       fontsize=8, rotation=45)
    ax.set_yticks(range(n_levels))
    ax.set_yticklabels([f"{l:.2f}" for l in levels], fontsize=8)
    ax.set_title(f"{symbol} footprint — {n_bars}×{bar_seconds}s bars "
                 f"({datetime.fromtimestamp(bars[0]).strftime('%H:%M')}–"
                 f"{datetime.fromtimestamp(bars[-1]).strftime('%H:%M')})", fontsize=12)
    ax.grid(True, color="white", linewidth=0.5, alpha=0.4)

    # ── volume profile (right) ─────────────────────────────────────────
    axp = fig.add_subplot(gs[0, 1], sharey=ax)
    total = buy_vol + sell_vol
    prof = total.sum(axis=1)
    axp.barh(range(n_levels), prof, color="#888", alpha=0.7)
    axp.set_xlabel("vol")
    axp.tick_params(labelleft=False)
    axp.grid(True, axis="x", alpha=0.3)

    # ── cumulative delta (bottom) ──────────────────────────────────────
    axd = fig.add_subplot(gs[1, 0])
    deltas = cell.sum(axis=0)
    cum = np.cumsum(deltas)
    axd.plot(range(n_bars), cum, color="#1f77b4", linewidth=1.8, marker="o", markersize=4)
    axd.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    axd.fill_between(range(n_bars), cum, 0, where=cum >= 0, color="#1f77b4", alpha=0.2)
    axd.fill_between(range(n_bars), cum, 0, where=cum < 0, color="#d62728", alpha=0.2)
    axd.set_xticks(range(n_bars))
    axd.set_xticklabels([datetime.fromtimestamp(b).strftime("%H:%M") for b in bars],
                        fontsize=8, rotation=45)
    axd.set_ylabel("cum Δ")
    axd.set_title("cumulative delta", fontsize=10)
    axd.grid(True, alpha=0.3)

    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"saved: {out_path}")


def main():
    ap = argparse.ArgumentParser(description="ATAS-style footprint chart from Binance trades")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--bars", type=int, default=12, help="number of bars to show")
    ap.add_argument("--bar-seconds", type=int, default=60)
    ap.add_argument("--trades", type=int, default=1000, help="aggTrades to fetch")
    ap.add_argument("--out", default="footprint.png")
    args = ap.parse_args()

    trades = fetch_trades(args.symbol, args.trades)
    if not trades:
        print("no trades fetched"); sys.exit(1)
    print(f"{args.symbol}: {len(trades)} trades fetched")

    bars, levels, grid = build_footprint(trades, args.bar_seconds)
    # keep only the last N bars for readability — remap bar indices so grid stays valid
    if len(bars) > args.bars:
        keep = set(bars[-args.bars:])
        bar_remap = {b: i for i, b in enumerate(bars[-args.bars:])}
        grid = {k: v for k, v in grid.items() if bars[k[0]] in keep}
        grid = {(bar_remap[bars[k[0]]], k[1]): v for k, v in grid.items()}
        bars = bars[-args.bars:]

    render_footprint(bars, levels, grid, args.symbol, args.bar_seconds, args.out)


if __name__ == "__main__":
    main()
