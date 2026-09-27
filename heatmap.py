"""Parameter heatmap: sweep two strategy params, plot total return as a heatmap."""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from engine import HFTEngine
from backtest import compute_metrics


def main():
    ap = argparse.ArgumentParser(description="Parameter heatmap (total return %)")
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2024-01-01")
    ap.add_argument("--strategy", choices=["sma", "rsi", "momentum"], default="sma")
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--commission", type=float, default=1.0)
    ap.add_argument("--slippage", type=float, default=5.0)
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    # param ranges per strategy
    if args.strategy == "sma":
        x_name, y_name = "fast", "slow"
        x_vals, y_vals = [5, 10, 20, 30, 50], [30, 50, 100, 150, 200]
    elif args.strategy == "rsi":
        x_name, y_name = "rsi_period", "oversold"
        x_vals, y_vals = [5, 7, 10, 14, 21], [20, 25, 30, 35, 40]
    else:  # momentum
        x_name, y_name = "mom_period", "threshold"
        x_vals, y_vals = [20, 30, 50, 75, 100], [50, 100, 150, 200, 250]

    grid = np.full((len(y_vals), len(x_vals)), np.nan)
    for j, xv in enumerate(x_vals):
        for i, yv in enumerate(y_vals):
            params = {}
            if args.strategy == "sma":
                if xv >= yv:
                    continue
                params = {"fast": xv, "slow": yv}
            elif args.strategy == "rsi":
                params = {"rsi_period": xv, "oversold": yv, "overbought": 100 - yv}
            else:
                params = {"mom_period": xv, "threshold": yv}

            engine = HFTEngine(
                args.symbol, args.start, args.end, strategy=args.strategy,
                initial_capital=args.capital, commission=args.commission,
                slippage_bps=args.slippage, **params,
            )
            orders = engine.run()
            m = compute_metrics(orders.equity_curve, orders.trades, args.capital)
            grid[i, j] = m["total_return_pct"]

    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(grid, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(x_vals)), [str(v) for v in x_vals])
    ax.set_yticks(range(len(y_vals)), [str(v) for v in y_vals])
    ax.set_xlabel(x_name); ax.set_ylabel(y_name)
    ax.set_title(f"{args.symbol} {args.strategy} — total return % heatmap "
                 f"({args.start}..{args.end})")

    for i in range(len(y_vals)):
        for j in range(len(x_vals)):
            v = grid[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=8,
                        color="black" if abs(v) < 15 else "white")

    fig.colorbar(im, label="total return %")
    plt.tight_layout()
    plt.savefig(f"{args.out}/heatmap_{args.strategy}.png", dpi=120)

    # best cell
    best_idx = np.unravel_index(np.nanargmax(grid), grid.shape)
    best = grid[best_idx]
    print(f"best {args.strategy}: {y_name}={y_vals[best_idx[0]]}, {x_name}={x_vals[best_idx[1]]} "
          f"-> {best:+.2f}%")
    print(f"saved: {args.out}/heatmap_{args.strategy}.png")


if __name__ == "__main__":
    sys.exit(main())
