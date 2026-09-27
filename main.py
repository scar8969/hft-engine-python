"""CLI entry point for the HFT engine backtest."""
import argparse
import csv
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from engine import HFTEngine
from backtest import compute_metrics


def run_single(args, symbol):
    engine = HFTEngine(
        symbol, args.start, args.end,
        strategy=args.strategy, fast=args.fast, slow=args.slow,
        threshold=args.threshold, initial_capital=args.capital,
        commission=args.commission, slippage_bps=args.slippage,
        rsi_period=args.rsi_period, oversold=args.oversold, overbought=args.overbought,
        mom_period=args.mom_period,
    )
    orders = engine.run()
    m = compute_metrics(orders.equity_curve, orders.trades, args.capital)
    return engine, orders, m


def print_report(symbol, args, engine, orders, m, show_trades=True):
    print(f"\n=== HFT-Engine backtest: {symbol} {args.start}..{args.end} ===")
    print(f"strategy: {args.strategy} (fast={args.fast} slow={args.slow})"
          f"  costs: ${args.commission}/order, {args.slippage}bps slippage")
    print(f"bars: {len(orders.equity_curve)}  rejected orders: {len(engine.risk.rejected)}")
    print("-" * 46)
    print(f"final equity:   ${m.get('final_equity', 0):,.2f}")
    print(f"total return:   {m.get('total_return_pct', 0):+.2f}%")
    print(f"max drawdown:   {m.get('max_drawdown_pct', 0):.2f}%")
    print(f"sharpe:         {m.get('sharpe', 0):.2f}")
    print(f"trades:         {m.get('trade_count', 0)}  win rate {m.get('win_rate_pct', 0):.1f}%")
    print(f"avg win/loss:   ${m.get('avg_win', 0):.2f} / ${m.get('avg_loss', 0):.2f}")
    print(f"total fees:     ${orders.total_fees:,.2f}")
    print("-" * 46)
    if show_trades:
        for t in orders.trades[-8:]:
            print(f"  {t.entry_time.date()} -> {t.exit_time.date() if t.exit_time else 'OPEN'}  "
                  f"{t.pnl:+.2f} ({t.pnl_pct:+.2f}%)")

def save_outputs(args, symbol, orders, out_prefix=""):
    with open(f"{out_prefix}trades.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "entry_time", "entry_price", "exit_time", "exit_price", "volume", "pnl", "pnl_pct"])
        for t in orders.trades:
            w.writerow([t.symbol, t.entry_time, t.entry_price,
                        t.exit_time or "", t.exit_price, t.volume, round(t.pnl, 2), round(t.pnl_pct, 2)])

    with open(f"{out_prefix}equity_curve.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "equity"])
        for ts, eq in orders.equity_curve:
            w.writerow([ts, round(eq, 2)])


def plot_equity(args, orders, symbol, out_prefix=""):
    times = [ts for ts, _ in orders.equity_curve]
    eq = [e for _, e in orders.equity_curve]
    bh = [args.capital * e / eq[0] for e in eq]  # buy & hold benchmark

    plt.figure(figsize=(10, 5))
    plt.plot(times, eq, label=f"{args.strategy} strategy", linewidth=1.8)
    plt.plot(times, bh, label="buy & hold", linestyle="--", alpha=0.6)
    plt.title(f"{symbol} — equity curve ({args.start}..{args.end})")
    plt.xlabel("date"); plt.ylabel("equity ($)")
    plt.legend(); plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"{out_prefix}equity_curve.png", dpi=120)


def main():
    ap = argparse.ArgumentParser(description="HFT-Engine python rebuild — backtest")
    ap.add_argument("--symbol", default="AAPL", help="ticker or comma-separated list (portfolio mode)")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2024-01-01")
    ap.add_argument("--strategy", choices=["sma", "threshold", "rsi", "momentum"], default="sma")
    ap.add_argument("--fast", type=int, default=20)
    ap.add_argument("--slow", type=int, default=50)
    ap.add_argument("--threshold", type=float, default=100.0)
    ap.add_argument("--rsi-period", type=int, default=14)
    ap.add_argument("--oversold", type=float, default=30.0)
    ap.add_argument("--overbought", type=float, default=70.0)
    ap.add_argument("--mom-period", type=int, default=50)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--commission", type=float, default=0.0, help="$ per order")
    ap.add_argument("--slippage", type=float, default=0.0, help="adverse slippage in basis points")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbol.split(",") if s.strip()]

    if len(symbols) == 1:
        symbol = symbols[0]
        engine, orders, m = run_single(args, symbol)
        print_report(symbol, args, engine, orders, m)
        save_outputs(args, symbol, orders, f"{args.out}/")
        plot_equity(args, orders, symbol, f"{args.out}/")
        print(f"\nsaved: {args.out}/trades.csv, {args.out}/equity_curve.csv, {args.out}/equity_curve.png")
    else:
        # portfolio mode: equal capital split per symbol, combined equity curve
        per = args.capital / len(symbols)
        combined = {}
        all_engines = []
        for sym in symbols:
            a = argparse.Namespace(**vars(args)); a.capital = per
            engine, orders, m = run_single(a, sym)
            all_engines.append((sym, engine, orders, m))
            print_report(sym, a, engine, orders, m, show_trades=False)
            for ts, eq in orders.equity_curve:
                combined[ts] = combined.get(ts, 0.0) + eq

        combined_curve = sorted(combined.items())
        cm = compute_metrics(combined_curve, [], args.capital)
        print(f"\n=== PORTFOLIO ({len(symbols)} symbols, equal split) ===")
        print(f"final equity:   ${cm.get('final_equity', 0):,.2f}")
        print(f"total return:   {cm.get('total_return_pct', 0):+.2f}%")
        print(f"max drawdown:   {cm.get('max_drawdown_pct', 0):.2f}%")
        print(f"sharpe:         {cm.get('sharpe', 0):.2f}")

        with open(f"{args.out}/portfolio_equity.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "equity"])
            for ts, eq in combined_curve:
                w.writerow([ts, round(eq, 2)])

        plt.figure(figsize=(10, 5))
        times = [ts for ts, _ in combined_curve]
        eq = [e for _, e in combined_curve]
        bh = [args.capital * e / eq[0] for e in eq]
        plt.plot(times, eq, label=f"portfolio ({args.strategy})", linewidth=1.8)
        plt.plot(times, bh, label="buy & hold", linestyle="--", alpha=0.6)
        plt.title(f"Portfolio equity curve ({', '.join(symbols)})")
        plt.xlabel("date"); plt.ylabel("equity ($)")
        plt.legend(); plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"{args.out}/portfolio_equity.png", dpi=120)
        print(f"\nsaved: {args.out}/portfolio_equity.csv, {args.out}/portfolio_equity.png")


if __name__ == "__main__":
    sys.exit(main())
