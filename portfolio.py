"""Portfolio optimization with skfolio — mean-variance, max Sharpe, risk parity.

Takes the per-symbol returns from the HFT engine backtests and computes
optimal portfolio weights, then re-runs the combined equity curve.

Usage:
    python portfolio.py --symbols AAPL,MSFT,GOOGL --start 2022-01-01 --end 2024-01-01
"""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from engine import HFTEngine
from backtest import compute_metrics


def load_returns(symbols, start, end):
    """Run each symbol's engine, return DataFrame of daily returns."""
    rets = {}
    for sym in symbols:
        engine = HFTEngine(sym, start, end, strategy="sma", fast=20, slow=50)
        orders = engine.run()
        eq = pd.Series({ts: e for ts, e in orders.equity_curve})
        rets[sym] = eq.pct_change().dropna()
    return pd.DataFrame(rets)


def main():
    ap = argparse.ArgumentParser(description="skfolio portfolio optimization")
    ap.add_argument("--symbols", default="AAPL,MSFT,GOOGL")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--end", default="2024-01-01")
    ap.add_argument("--method", choices=["sharpe", "minvol", "riskparity"], default="sharpe")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    rets = load_returns(symbols, args.start, args.end)
    print(f"returns matrix: {rets.shape[0]} days x {rets.shape[1]} symbols")

    from skfolio import RiskMeasure
    from skfolio.optimization import MeanRisk, RiskBudgeting, ObjectiveFunction

    if args.method == "riskparity":
        model = RiskBudgeting(risk_measure=RiskMeasure.VARIANCE)
    else:
        model = MeanRisk(
            risk_measure=RiskMeasure.VARIANCE,
            objective_function=ObjectiveFunction.MAXIMIZE_UTILITY if args.method == "sharpe" else ObjectiveFunction.MINIMIZE_RISK,
        )
    model.fit(rets)
    weights = model.weights_

    print(f"\n=== {args.method} portfolio weights ===")
    for sym, w in zip(symbols, weights):
        print(f"  {sym}: {w:.1%}")

    # portfolio return series
    port_ret = rets @ weights
    port_eq = (1 + port_ret).cumprod() * 10_000

    # metrics
    m = compute_metrics([(ts, e) for ts, e in port_eq.items()], [], 10_000)
    print(f"\nportfolio: return {m['total_return_pct']:+.2f}%, "
          f"maxDD {m['max_drawdown_pct']:.2f}%, sharpe {m['sharpe']:.2f}")

    # chart: weights + cumulative return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.bar(symbols, weights, color="#1f77b4")
    ax1.set_title(f"{args.method} weights")
    ax1.set_ylabel("weight")
    ax2.plot(port_eq.index, port_eq.values, label=f"{args.method} portfolio", linewidth=1.8)
    ax2.set_title(f"portfolio equity ({args.start}..{args.end})")
    ax2.set_ylabel("equity ($)")
    ax2.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"{args.out}/portfolio_opt.png", dpi=120)
    print(f"saved: {args.out}/portfolio_opt.png")


if __name__ == "__main__":
    sys.exit(main())
