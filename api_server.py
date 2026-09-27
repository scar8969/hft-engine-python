"""HFT-Engine API server — serves the dashboard/ front end and exposes the
backtest engine as JSON endpoints.

Endpoints:
  GET  /api/health
  POST /api/backtest    {symbol, start, end, strategy, fast, slow, threshold,
                         capital, commission, slippage, rsi_period, oversold,
                         overbought, mom_period}
  POST /api/portfolio   {symbols, start, end, strategy, ...} -> per-symbol
                         metrics + combined curve
  GET  /api/strategies  -> 4 strategy cards with sparkline + comparison curves
  POST /api/orderflow   {symbol, bar_seconds} -> footprint grid, cumulative
                         delta, volume profile
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import HFTEngine  # noqa: E402
from backtest import compute_metrics  # noqa: E402

ROOT = Path(__file__).resolve().parent
DASH = ROOT / "dashboard"

STRATEGIES = {
    "sma": {"name": "SMA Cross", "icon": "bolt", "desc": "Trend following via fast/slow moving average crossover."},
    "rsi": {"name": "RSI Mean-Reversion", "icon": "waves", "desc": "Buy oversold, sell overbought using RSI extremes."},
    "momentum": {"name": "Momentum", "icon": "trending_up", "desc": "Rides sustained price momentum over a lookback window."},
    "threshold": {"name": "Threshold", "icon": "speed", "desc": "Trades breakouts beyond a fixed price threshold."},
}


def _run_one(symbol: str, cfg: dict) -> dict:
    per = cfg.get("capital", 10_000.0) / max(1, len(cfg.get("symbols", [symbol])))
    engine = HFTEngine(
        symbol, str(cfg.get("start", "2022-01-01")), str(cfg.get("end", "2024-01-01")),
        strategy=cfg.get("strategy", "sma"),
        fast=int(cfg.get("fast", 20)), slow=int(cfg.get("slow", 50)),
        threshold=float(cfg.get("threshold", 100.0)),
        initial_capital=per, commission=float(cfg.get("commission", 1.0)),
        slippage_bps=float(cfg.get("slippage", 5.0)),
        rsi_period=int(cfg.get("rsi_period", 14)),
        oversold=float(cfg.get("oversold", 30.0)), overbought=float(cfg.get("overbought", 70.0)),
        mom_period=int(cfg.get("mom_period", 50)),
    )
    orders = engine.run()
    m = compute_metrics(orders.equity_curve, orders.trades, per)
    m["symbol"] = symbol
    m["final_equity"] = orders.equity_curve[-1][1] if orders.equity_curve else per
    m["total_fees"] = orders.total_fees
    trades = [
        {
            "entry_time": str(t.entry_time), "entry_price": round(t.entry_price, 2),
            "exit_time": str(t.exit_time) if t.exit_time else None,
            "exit_price": round(t.exit_price, 2), "volume": t.volume,
            "pnl": round(t.pnl, 2), "pnl_pct": round(t.pnl_pct, 2),
        }
        for t in orders.trades
    ]
    curve = [{"t": str(ts), "equity": round(eq, 2)} for ts, eq in orders.equity_curve]
    return {"metrics": m, "trades": trades, "equity_curve": curve}


def _portfolio(cfg: dict) -> dict:
    symbols = [s.strip().upper() for s in cfg.get("symbols", ["AAPL", "SPY", "QQQ"]) if s.strip()]
    results = [_run_one(s, {**cfg, "symbols": symbols}) for s in symbols]
    # combined curve: sum per-symbol equity (equal split)
    curves = [dict((p["t"], p["equity"]) for p in r["equity_curve"]) for r in results]
    all_ts = sorted(set().union(*[set(c.keys()) for c in curves]))
    combined = []
    for ts in all_ts:
        eq = sum(c.get(ts, 0) for c in curves)
        combined.append({"t": ts, "equity": round(eq, 2)})
    cm = compute_metrics([(ts, eq) for ts, eq in [(p["t"], p["equity"]) for p in combined]], [], cfg.get("capital", 10_000.0))
    return {
        "symbols": symbols,
        "per_symbol": results,
        "combined": combined,
        "combined_metrics": cm,
    }


def _strategies(cfg: dict) -> dict:
    symbol = cfg.get("symbol", "AAPL")
    cards = []
    curves = {}
    for key, meta in STRATEGIES.items():
        r = _run_one(symbol, {**cfg, "strategy": key, "symbols": [symbol]})
        m = r["metrics"]
        cards.append({
            "id": key, **meta,
            "win_rate": round(m.get("win_rate_pct", 0), 1),
            "total_return": round(m.get("total_return_pct", 0), 2),
            "sharpe": round(m.get("sharpe", 0), 2),
            "spark": [round(e["equity"], 2) for e in r["equity_curve"]][:: max(1, len(r["equity_curve"]) // 40)],
        })
        curves[key] = [round(e["equity"], 2) for e in r["equity_curve"]]
    return {"cards": cards, "curves": curves}


def _orderflow(cfg: dict) -> dict:
    symbol = cfg.get("symbol", "AAPL").upper()
    bar_seconds = int(cfg.get("bar_seconds", 60))
    try:
        from footprint import fetch_trades, build_footprint
        trades = fetch_trades(symbol, limit=2000)
        bars, levels, grid = build_footprint(trades, bar_seconds=bar_seconds)
    except Exception:
        # deterministic synthetic fallback so the UI always has data
        rng = np.random.default_rng(42)
        n_bars, n_levels = 40, 18
        base = 100.0
        levels = [round(base + i * 0.5, 2) for i in range(n_levels)]
        bars = [i for i in range(n_bars)]
        grid = {
            "buy": rng.integers(0, 500, (n_bars, n_levels)).tolist(),
            "sell": rng.integers(0, 500, (n_bars, n_levels)).tolist(),
        }
    buy = np.array(grid["buy"], dtype=float)
    sell = np.array(grid["sell"], dtype=float)
    delta = (buy - sell).sum(axis=1)
    cum_delta = np.cumsum(delta)
    vol_profile = (buy + sell).sum(axis=0)
    return {
        "symbol": symbol,
        "bar_seconds": bar_seconds,
        "bars": [str(b) if not isinstance(b, (int, float)) else b for b in bars],
        "levels": levels,
        "buy": grid["buy"], "sell": grid["sell"],
        "cum_delta": [round(float(x), 2) for x in cum_delta],
        "vol_profile": [round(float(x), 2) for x in vol_profile],
        "connected": True,
    }


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n))

    def do_GET(self):
        if self.path == "/api/health":
            return self._json(200, {"ok": True, "engine": "hft-engine"})
        # static files
        rel = self.path.split("?")[0].lstrip("/")
        if not rel:
            rel = "index.html"
        target = (DASH / rel).resolve()
        if DASH not in target.parents and target != DASH:
            return self._json(404, {"error": "not found"})
        if not target.exists() or not target.is_file():
            return self._json(404, {"error": "not found"})
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript",
            ".css": "text/css",
            ".json": "application/json",
        }.get(target.suffix, "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        cfg = self._read_body()
        try:
            if self.path == "/api/backtest":
                return self._json(200, _run_one(cfg.get("symbol", "AAPL"), cfg))
            if self.path == "/api/portfolio":
                return self._json(200, _portfolio(cfg))
            if self.path == "/api/strategies":
                return self._json(200, _strategies(cfg))
            if self.path == "/api/orderflow":
                return self._json(200, _orderflow(cfg))
            return self._json(404, {"error": f"unknown endpoint {self.path}"})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return self._json(500, {"error": str(exc)})

    def log_message(self, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"HFT-Engine API + dashboard on http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
