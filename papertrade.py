"""Live paper trading: polls latest bar, runs strategy, prints signals. No real orders."""
import argparse
import time
from datetime import datetime

import yfinance as yf

from engine import HFTEngine
from engine.models import MarketData


def poll_once(engine: HFTEngine, symbol: str):
    """Fetch the latest daily bar and feed it through the engine pipeline."""
    df = yf.download(symbol, period="5d", interval="1d", progress=False, auto_adjust=True)
    if hasattr(df.columns, "levels"):  # MultiIndex
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        print(f"[{datetime.now():%H:%M:%S}] no data for {symbol}")
        return

    last = df.iloc[-1]
    bar = MarketData(
        symbol=symbol,
        timestamp=df.index[-1].to_pydatetime(),
        open=float(last["Open"]), high=float(last["High"]),
        low=float(last["Low"]), close=float(last["Close"]),
        volume=float(last["Volume"]),
    )
    engine.market_data.process(bar)
    engine.orders.mark_to_market(bar.timestamp, bar.close)
    print(f"[{datetime.now():%H:%M:%S}] {symbol} close={bar.close:.2f} "
          f"position={engine.orders.position} equity=${engine.orders.cash + engine.orders.position * bar.close:,.2f}")


def main():
    ap = argparse.ArgumentParser(description="HFT-Engine live paper trading (no real orders)")
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--strategy", choices=["sma", "threshold", "rsi"], default="sma")
    ap.add_argument("--fast", type=int, default=20)
    ap.add_argument("--slow", type=int, default=50)
    ap.add_argument("--threshold", type=float, default=100.0)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--commission", type=float, default=1.0)
    ap.add_argument("--slippage", type=float, default=5.0)
    ap.add_argument("--rsi-period", type=int, default=14)
    ap.add_argument("--oversold", type=float, default=30.0)
    ap.add_argument("--overbought", type=float, default=70.0)
    ap.add_argument("--interval", type=int, default=60, help="poll seconds")
    args = ap.parse_args()

    # warm up with history so indicators have data
    engine = HFTEngine(
        args.symbol, "2024-01-01", str(datetime.now().date()),
        strategy=args.strategy, fast=args.fast, slow=args.slow,
        threshold=args.threshold, initial_capital=args.capital,
        commission=args.commission, slippage_bps=args.slippage,
        rsi_period=args.rsi_period, oversold=args.oversold, overbought=args.overbought,
    )
    for bar in engine.market_data.connect():  # warm-up: feed history through the pipeline
        engine.market_data.process(bar)
    print(f"=== paper trading {args.symbol} ({args.strategy}) — Ctrl+C to stop ===")

    try:
        while True:
            poll_once(engine, args.symbol)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
