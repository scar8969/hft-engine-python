"""CLI entry point for the live HFT engine.

Usage:
    python live_engine.py --symbol BTCUSDT --strategy momentum --gateway binance --backend dryrun
    python live_engine.py --symbol AAPL --strategy sma --backend alpaca   # needs keys

Ctrl+C flattens positions and shuts down gracefully.
"""
import argparse
import asyncio

from engine.live_engine import LiveEngine
from engine.state import StateStore


async def main():
    ap = argparse.ArgumentParser(description="HFT-Engine live trading")
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--strategy", choices=["sma", "threshold", "rsi", "momentum"], default="sma")
    ap.add_argument("--fast", type=int, default=20)
    ap.add_argument("--slow", type=int, default=50)
    ap.add_argument("--threshold", type=float, default=100.0)
    ap.add_argument("--rsi-period", type=int, default=14)
    ap.add_argument("--oversold", type=float, default=30.0)
    ap.add_argument("--overbought", type=float, default=70.0)
    ap.add_argument("--mom-period", type=int, default=50)
    ap.add_argument("--qty", type=int, default=10)
    ap.add_argument("--max-position", type=int, default=100)
    ap.add_argument("--max-exposure", type=float, default=100_000.0)
    ap.add_argument("--backend", choices=["dryrun", "direct", "alpaca"], default="dryrun",
                    help="order router backend")
    ap.add_argument("--gateway", choices=["poll", "binance"], default="poll",
                    help="market data backend")
    ap.add_argument("--db", default="hft_live.db")
    args = ap.parse_args()

    store = StateStore(args.db)
    engine = LiveEngine(
        args.symbol, store, backend=args.backend, strategy=args.strategy,
        fast=args.fast, slow=args.slow, threshold=args.threshold,
        rsi_period=args.rsi_period, oversold=args.oversold, overbought=args.overbought,
        mom_period=args.mom_period, qty=args.qty,
        max_position=args.max_position, max_exposure=args.max_exposure,
        gateway_backend=args.gateway,
    )

    await engine.start()
    print(f"=== LIVE {args.symbol} ({args.strategy}) backend={args.backend} gateway={args.gateway} — Ctrl+C to flatten+stop ===")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[ctrl-c] flattening + stopping...")
        await engine.flatten()
        await engine.stop()
        store.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
