"""Live order-flow feed: Binance public WebSocket — real trades + depth, no API key.

Gives ATAS-style data (footprint / delta / volume profile) for crypto:
- trade tape (aggressor side: taker buy/sell)
- depth snapshots (bid/ask ladder)
- delta = buy volume - sell volume per bar
- cumulative delta + volume profile accumulation

Usage:
    python livefeed.py --symbol BTCUSDT --bars 30
    python livefeed.py --symbol ETHUSDT --bars 60 --interval 5s
"""
import argparse
import asyncio
import json
import time
from datetime import datetime

import websockets

BINANCE_WS = "wss://stream.binance.com:9443/stream?streams={streams}"


class OrderFlowFeed:
    def __init__(self, symbol: str, bar_seconds: int = 60):
        self.symbol = symbol.lower()
        self.bar_seconds = bar_seconds
        self.bars = []          # completed bars: {t, o, h, l, c, vol, buy_vol, sell_vol, delta, trades}
        self.cur = None         # current forming bar
        self.depth = {"bids": [], "asks": []}
        self._last_trade = None

    # ── bar management ────────────────────────────────────────────────
    def _bar_key(self, ts: float) -> int:
        return int(ts // self.bar_seconds)

    def _new_bar(self, price: float, vol: float, side: str, ts: float):
        self.cur = {
            "t": ts, "o": price, "h": price, "l": price, "c": price,
            "vol": vol,
            "buy_vol": vol if side == "buy" else 0.0,
            "sell_vol": vol if side == "sell" else 0.0,
            "delta": vol if side == "buy" else -vol,
            "trades": 1,
        }

    def _update_bar(self, price: float, vol: float, side: str, ts: float):
        b = self.cur
        b["h"] = max(b["h"], price)
        b["l"] = min(b["l"], price)
        b["c"] = price
        b["vol"] += vol
        if side == "buy":
            b["buy_vol"] += vol
            b["delta"] += vol
        else:
            b["sell_vol"] += vol
            b["delta"] -= vol
        b["trades"] += 1

    def on_trade(self, price: float, qty: float, side: str, ts: float):
        """side: 'buy' = taker buy (aggressor bought), 'sell' = taker sell."""
        key = self._bar_key(ts)
        if self.cur is None or self._bar_key(self.cur["t"]) != key:
            if self.cur is not None:
                self.bars.append(self.cur)
            self._new_bar(price, qty, side, ts)
        else:
            self._update_bar(price, qty, side, ts)

    # ── websocket handlers ────────────────────────────────────────────
    def _apply_depth(self, side_key: str, updates):
        """Apply a depthUpdate delta to the maintained book (qty 0 = remove level)."""
        book = dict(self.depth[side_key])
        for p, q in updates:
            p, q = float(p), float(q)
            if q == 0:
                book.pop(p, None)
            else:
                book[p] = q
        self.depth[side_key] = sorted(book.items(), reverse=(side_key == "bids"))[:10]

    async def _handle(self, ws):
        async for raw in ws:
            msg = json.loads(raw)
            data = msg.get("data", msg)
            if "e" not in data:
                # depth20 partial snapshot: {lastUpdateId, bids, asks}
                if "bids" in data and "asks" in data:
                    self.depth["bids"] = [(float(p), float(q)) for p, q in data.get("bids", [])[:10]]
                    self.depth["asks"] = [(float(p), float(q)) for p, q in data.get("asks", [])[:10]]
                continue
            if data["e"] == "trade":
                price = float(data["p"])
                qty = float(data["q"])
                side = "buy" if not data.get("m") else "sell"  # m=False -> taker buy
                ts = data["T"] / 1000.0
                self.on_trade(price, qty, side, ts)
                self._last_trade = (price, qty, side, ts)
            elif data["e"] == "depthUpdate":
                self._apply_depth("bids", data.get("b", []))
                self._apply_depth("asks", data.get("a", []))

    async def run(self, duration: float | None = None):
        streams = f"{self.symbol}@trade/{self.symbol}@depth20@100ms/{self.symbol}@depth20"
        url = BINANCE_WS.format(streams=streams)
        start = time.time()
        async with websockets.connect(url) as ws:
            print(f"connected: {self.symbol} (bar={self.bar_seconds}s) — Ctrl+C to stop")
            task = asyncio.ensure_future(self._handle(ws))
            try:
                while duration is None or (time.time() - start) < duration:
                    await asyncio.sleep(0.5)
                    self._render()
            finally:
                task.cancel()

    # ── output ────────────────────────────────────────────────────────
    def _render(self):
        if self.cur is None:
            return
        b = self.cur
        bid, ask = self._best_bid_ask()
        spread = (ask - bid) if bid and ask else 0.0
        print(f"\r[{datetime.now():%H:%M:%S}] {self.symbol} "
              f"px={b['c']:.2f} Δ={b['delta']:+.1f} vol={b['vol']:.1f} "
              f"(B {b['buy_vol']:.1f}/S {b['sell_vol']:.1f}) trades={b['trades']} "
              f"spread={spread:.2f}  bid={bid} ask={ask}   ", end="", flush=True)

    def _best_bid_ask(self):
        bids, asks = self.depth["bids"], self.depth["asks"]
        bid = max(bids)[0] if bids else None
        ask = min(asks)[0] if asks else None
        return bid, ask

    def summary(self):
        print()
        print(f"\n=== {self.symbol} order-flow session ===")
        if not self.bars:
            print("no completed bars yet")
            return
        for b in self.bars[-10:]:
            t = datetime.fromtimestamp(b["t"]).strftime("%H:%M:%S")
            print(f"  {t}  O{b['o']:.2f} H{b['h']:.2f} L{b['l']:.2f} C{b['c']:.2f} "
                  f"vol={b['vol']:.1f} Δ={b['delta']:+.1f} ({b['buy_vol']:.1f}/{b['sell_vol']:.1f})")
        tot_delta = sum(b["delta"] for b in self.bars)
        tot_vol = sum(b["vol"] for b in self.bars)
        print(f"  total: {len(self.bars)} bars, vol={tot_vol:.1f}, cumulative delta={tot_delta:+.1f}")


def main():
    ap = argparse.ArgumentParser(description="Binance live order-flow feed (ATAS-style)")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--bars", type=int, default=30, help="bar size in seconds")
    ap.add_argument("--duration", type=int, default=None, help="run N seconds, then stop")
    args = ap.parse_args()

    feed = OrderFlowFeed(args.symbol, args.bars)
    try:
        asyncio.run(feed.run(args.duration))
    except KeyboardInterrupt:
        pass
    feed.summary()


if __name__ == "__main__":
    main()
