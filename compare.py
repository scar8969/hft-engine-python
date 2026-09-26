"""Strategy comparison: run all strategies on the same symbol/period, print table + overlay chart."""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from engine import HFTEngine
from backtest import compute_metrics

STRATEGIES = {
    "sma": dict(strategy="sma", fast=20, slow=50),
    "rsi": dict(strategy="rsi", rsi_period=14, oversold=30, overbought=70),
    "momentum": dict(strategy="momentum", mom_period=50),
    "threshold": dict(strategy="threshold", threshold=180.0),
}


def main():
    ap = argparse.ArgumentParser(description="Compare all strategies on one symbol/period")
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2024-01-01")
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--commission", type=float, default=1.0)
    ap.add_argument("--slippage", type=float, default=5.0)
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    print(f"=== strategy comparison: {args.symbol} {args.start}..{args.end} ===")
    print(f"costs: ${args.commission}/order, {args.slippage}bps slippage, capital ${args.capital:,.0f}\n")
    print(f"{'strategy':<12}{'return':>9}{'maxDD':>9}{'sharpe':>8}{'trades':>8}{'winrate':>9}{'fees':>8}")
    print("-" * 63)

    results = []
    for name, params in STRATEGIES.items():
        engine = HFTEngine(
            args.symbol, args.start, args.end,
            initial_capital=args.capital, commission=args.commission,
            slippage_bps=args.slippage, **params,
        )
        orders = engine.run()
        m = compute_metrics(orders.equity_curve, orders.trades, args.capital)
        results.append((name, engine, orders, m))
        print(f"{name:<12}{m['total_return_pct']:>+8.2f}%{m['max_drawdown_pct']:>8.2f}%"
              f"{m['sharpe']:>8.2f}{m['trade_count']:>8}{m['win_rate_pct']:>8.1f}%"
              f"{orders.total_fees:>8.2f}")

    # overlay chart
    plt.figure(figsize=(11, 6))
    for name, engine, orders, m in results:
        times = [ts for ts, _ in orders.equity_curve]
        eq = [e for _, e in orders.equity_curve]
        plt.plot(times, eq, label=f"{name} ({m['total_return_pct']:+.1f}%)", linewidth=1.6)

    first = results[0][2].equity_curve
    if first:
        bh = [args.capital * e / first[0][1] for _, e in first]
        plt.plot([ts for ts, _ in first], bh, label="buy & hold", linestyle="--", alpha=0.5, color="black")

    plt.title(f"{args.symbol} — all strategies ({args.start}..{args.end})")
    plt.xlabel("date"); plt.ylabel("equity ($)")
    plt.legend(); plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"{args.out}/strategy_compare.png", dpi=120)
    print(f"\nsaved: {args.out}/strategy_compare.png")


if __name__ == "__main__":
    sys.exit(main())
