"""Alpaca paper-trading bridge: run the engine live against Alpaca's free paper account.

Requires ALPACA_API_KEY and ALPACA_SECRET_KEY env vars (paper keys from
https://app.alpaca.markets/paper). Uses the paper endpoint, never real money.
"""
import argparse
import os
import sys

from engine import HFTEngine
from engine.models import MarketData

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
except ImportError:
    sys.exit("pip install alpaca-py  (and set ALPACA_API_KEY / ALPACA_SECRET_KEY)")


def get_client():
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        sys.exit("set ALPACA_API_KEY and ALPACA_SECRET_KEY (paper keys)")
    return TradingClient(key, secret, paper=True)


def main():
    ap = argparse.ArgumentParser(description="Alpaca paper trading via HFT-Engine")
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--strategy", choices=["sma", "threshold", "rsi", "momentum"], default="sma")
    ap.add_argument("--fast", type=int, default=20)
    ap.add_argument("--slow", type=int, default=50)
    ap.add_argument("--threshold", type=float, default=100.0)
    ap.add_argument("--rsi-period", type=int, default=14)
    ap.add_argument("--oversold", type=float, default=30.0)
    ap.add_argument("--overbought", type=float, default=70.0)
    ap.add_argument("--mom-period", type=int, default=50)
    ap.add_argument("--qty", type=int, default=10, help="shares per order")
    args = ap.parse_args()

    client = get_client()
    account = client.get_account()
    print(f"Alpaca paper account: {account.account_number}  equity=${float(account.equity):,.2f}")

    # warm up engine with history
    engine = HFTEngine(
        args.symbol, "2024-01-01", "2025-01-01",
        strategy=args.strategy, fast=args.fast, slow=args.slow,
        threshold=args.threshold, rsi_period=args.rsi_period,
        oversold=args.oversold, overbought=args.overbought,
        mom_period=args.mom_period,
    )
    for bar in engine.market_data.connect():
        engine.market_data.process(bar)
    print(f"warmed up {args.symbol} ({args.strategy}), position={engine.orders.position}")

    # hook engine signals -> alpaca paper orders
    def on_signal(order):
        side = AlpacaSide.BUY if order.side.value == "BUY" else AlpacaSide.SELL
        req = MarketOrderRequest(
            symbol=args.symbol, qty=args.qty, side=side, time_in_force=TimeInForce.DAY,
        )
        try:
            resp = client.submit_order(req)
            print(f"-> {side.value} {args.qty} {args.symbol} @ ~{order.price:.2f} "
                  f"(alpaca id {resp.id})")
        except Exception as e:
            print(f"-> order failed: {e}")

    engine.strategy.on_signal = on_signal

    # fetch latest bar and run once (one-shot paper trade check)
    from engine.market_data import MarketDataHandler
    bars = MarketDataHandler(args.symbol, "2024-01-01", "2025-01-01").connect()
    last = bars[-1]
    engine.market_data.process(last)
    print(f"latest bar {last.timestamp.date()} close={last.close:.2f} -> signals fired")

    # show final position from alpaca
    try:
        pos = client.get_position(args.symbol)
        print(f"alpaca position: {pos.qty} {args.symbol} @ {pos.avg_entry_price}")
    except Exception:
        print("alpaca position: none")


if __name__ == "__main__":
    main()
