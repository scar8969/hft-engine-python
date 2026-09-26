"""Walk-forward optimization: sweep strategy params on rolling train windows, validate on out-of-sample test windows."""
import argparse
import itertools
import sys
from datetime import datetime

import pandas as pd
import yfinance as yf

from engine import HFTEngine
from backtest import compute_metrics


def load_bars(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.get_level_values(0)
    return df


def run_window(symbol, df, start_idx, end_idx, strategy, params, capital, commission, slippage):
    """Run the engine on df.iloc[start_idx:end_idx], with indicator warmup before the window.

    The engine needs `slow`/`mom_period`/`rsi_period` bars of history before signals
    fire, so we start it `warmup` bars earlier and slice results to the window.
    """
    warmup = max(params.get("slow", 50), params.get("mom_period", 50),
                 params.get("rsi_period", 14)) + 10
    lo = max(0, start_idx - warmup)
    window = df.iloc[lo:end_idx]
    if len(window) < 60:
        return None
    start = window.index[0].strftime("%Y-%m-%d")
    end = window.index[-1].strftime("%Y-%m-%d")
    engine = HFTEngine(
        symbol, start, end, strategy=strategy,
        fast=params.get("fast", 20), slow=params.get("slow", 50),
        threshold=params.get("threshold", 100.0),
        rsi_period=params.get("rsi_period", 14),
        oversold=params.get("oversold", 30.0), overbought=params.get("overbought", 70.0),
        mom_period=params.get("mom_period", 50),
        initial_capital=capital, commission=commission, slippage_bps=slippage,
    )
    orders = engine.run()

    # slice equity curve + trades to the actual window (drop warmup bars)
    win_start = df.index[start_idx]
    orders.equity_curve = [(ts, e) for ts, e in orders.equity_curve if ts >= win_start]
    orders.trades = [t for t in orders.trades if t.exit_time is None or t.exit_time >= win_start]

    m = compute_metrics(orders.equity_curve, orders.trades, capital)
    return m


def param_grid(strategy):
    if strategy == "sma":
        return [{"fast": f, "slow": s} for f in (10, 20, 30) for s in (50, 100, 150) if f < s]
    if strategy == "rsi":
        return [{"rsi_period": p, "oversold": o, "overbought": 100 - o}
                for p in (7, 14, 21) for o in (25, 30, 35)]
    if strategy == "momentum":
        return [{"mom_period": p} for p in (20, 50, 100, 150)]
    return [{}]


def main():
    ap = argparse.ArgumentParser(description="Walk-forward optimization")
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2024-01-01")
    ap.add_argument("--strategy", choices=["sma", "rsi", "momentum"], default="sma")
    ap.add_argument("--train-days", type=int, default=252)
    ap.add_argument("--test-days", type=int, default=63)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--commission", type=float, default=1.0)
    ap.add_argument("--slippage", type=float, default=5.0)
    args = ap.parse_args()

    df = load_bars(args.symbol, args.start, args.end)
    if df.empty:
        print("no data"); sys.exit(1)
    n = len(df)
    print(f"{args.symbol}: {n} bars ({args.start}..{args.end})")

    grid = param_grid(args.strategy)
    print(f"strategy={args.strategy} grid={len(grid)} param sets, "
          f"train={args.train_days}d test={args.test_days}d")

    # rolling windows: train -> test, stepping by test_days
    results = []
    start = 0
    while start + args.train_days + args.test_days <= n:
        train_end = start + args.train_days
        test_end = train_end + args.test_days

        # pick best params on train
        best, best_m = None, None
        for params in grid:
            m = run_window(args.symbol, df, start, train_end, args.strategy, params,
                           args.capital, args.commission, args.slippage)
            if m and (best_m is None or m["total_return_pct"] > best_m["total_return_pct"]):
                best, best_m = params, m

        # validate best on test (out-of-sample)
        test_m = run_window(args.symbol, df, train_end, test_end, args.strategy, best,
                            args.capital, args.commission, args.slippage)

        w_start = df.index[start].strftime("%Y-%m-%d")
        w_train = df.index[train_end - 1].strftime("%Y-%m-%d")
        w_test = df.index[test_end - 1].strftime("%Y-%m-%d")
        row = {
            "window": f"{w_start}..{w_test}",
            "train": f"{w_start}..{w_train}",
            "best_params": best,
            "train_return": round(best_m["total_return_pct"], 2) if best_m else None,
            "test_return": round(test_m["total_return_pct"], 2) if test_m else None,
            "test_sharpe": round(test_m["sharpe"], 2) if test_m else None,
            "test_maxdd": round(test_m["max_drawdown_pct"], 2) if test_m else None,
        }
        results.append(row)
        print(f"  [{row['window']}] best={best} "
              f"train={row['train_return']}% -> test={row['test_return']}% (sharpe {row['test_sharpe']})")

        start += args.test_days

    # aggregate out-of-sample stats
    tests = [r for r in results if r["test_return"] is not None]
    if tests:
        avg_test = sum(r["test_return"] for r in tests) / len(tests)
        wins = sum(1 for r in tests if r["test_return"] > 0)
        print(f"\n=== walk-forward summary ({len(tests)} windows) ===")
        print(f"avg out-of-sample return: {avg_test:+.2f}%  (winning windows: {wins}/{len(tests)})")
        print(f"best window: {max(tests, key=lambda r: r['test_return'])}")
        print(f"worst window: {min(tests, key=lambda r: r['test_return'])}")


if __name__ == "__main__":
    main()
