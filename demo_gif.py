"""Generate a demo GIF: footprint bars building up frame-by-frame from recent Binance trades.

Usage:
    python demo_gif.py --symbol BTCUSDT --bars 12 --bar-seconds 60 --out demo_footprint.gif
"""
import argparse
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from PIL import Image

from footprint import fetch_trades, build_footprint


def _frame_image(bars, levels, grid, total_delta, symbol, shown, t0):
    """Render one GIF frame: footprint up to `shown` bars + cumulative delta."""
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(11, 8), gridspec_kw={"height_ratios": [3, 1]}, facecolor="black")
    ax.set_facecolor("black")
    ax2.set_facecolor("black")

    max_cell = max((bv + sv for (bi, _), (bv, sv) in grid.items() if bi < shown), default=1) or 1
    for i in range(shown):
        for (bi, li), (bv, sv) in grid.items():
            if bi != i:
                continue
            if bv:
                a = min(1, bv / max_cell)
                ax.add_patch(Rectangle((i - 0.45, li - 0.4), 0.45, 0.8,
                                       facecolor=(0.1, 0.2 + 0.6 * a, 0.15), alpha=0.9))
                ax.text(i - 0.22, li, f"{bv:.2f}", color="white", fontsize=5.5,
                        ha="center", va="center")
            if sv:
                a = min(1, sv / max_cell)
                ax.add_patch(Rectangle((i, li - 0.4), 0.45, 0.8,
                                       facecolor=(0.2 + 0.6 * a, 0.12, 0.1), alpha=0.9))
                ax.text(i + 0.22, li, f"{sv:.2f}", color="white", fontsize=5.5,
                        ha="center", va="center")

    ax.set_xlim(-0.6, len(bars) + 0.1)
    ax.set_ylim(-1, len(levels) + 1)
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([f"+{(b - t0) // 60}m" for b in bars], color="white", fontsize=7)
    ystep = max(1, len(levels) // 10)
    ax.set_yticks(range(0, len(levels), ystep))
    ax.set_yticklabels([f"{levels[j]:,.0f}" for j in range(0, len(levels), ystep)],
                       color="white", fontsize=7)
    ax.set_title(f"{symbol} footprint — bid|ask volume per price level  ·  frame {shown}/{len(bars)}",
                 color="white", fontsize=12)
    for s in ax.spines.values():
        s.set_color("white")

    x = np.arange(shown)
    ax2.plot(x, total_delta[:shown], color="#4dd2ff", linewidth=1.8)
    ax2.fill_between(x, total_delta[:shown], 0, color="#4dd2ff", alpha=0.2)
    ax2.set_title("cumulative delta", color="white", fontsize=9)
    ax2.tick_params(colors="white", labelsize=7)
    for s in ax2.spines.values():
        s.set_color("white")
    ax2.grid(alpha=0.15, color="white")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=90, facecolor="black")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB").copy()


def make_gif(symbol, n_bars, bar_seconds, out_path, fps=2):
    trades = fetch_trades(symbol, 2000)
    if not trades:
        print("no trades")
        return
    # truncate the trade stream first so grid indices stay valid after build
    horizon = bar_seconds * n_bars * 1000
    last_ts = max(t["ts"] for t in trades)
    trades = [t for t in trades if t["ts"] >= last_ts - horizon]
    bars, levels, grid = build_footprint(trades, bar_seconds=bar_seconds)
    if not bars:
        print("no bars")
        return

    # keep the most recent price band; remap level indices
    max_lv = 60
    if len(levels) > max_lv:
        lo = len(levels) - max_lv
        levels = levels[lo:]
        grid = {(bi, li - lo): v for (bi, li), v in grid.items() if li >= lo}

    t0 = bars[0]
    total_delta = []
    run = 0
    for i in range(len(bars)):
        run += sum(sv - bv for (bi, _), (bv, sv) in grid.items() if bi == i)
        total_delta.append(run)

    frames = [_frame_image(bars, levels, grid, total_delta, symbol, s, t0)
              for s in range(1, len(bars) + 1)]
    # hold the final frame a beat longer
    frames += [frames[-1]] * fps
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=int(1000 / fps), loop=0, optimize=True)
    print("saved:", out_path, f"({len(frames)} frames)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--bars", type=int, default=12)
    ap.add_argument("--bar-seconds", type=int, default=60)
    ap.add_argument("--out", default="demo_footprint.gif")
    args = ap.parse_args()
    make_gif(args.symbol, args.bars, args.bar_seconds, args.out)
