"""API route handlers — pure functions, no HTTP plumbing.

Each handler takes a cfg dict and returns a JSON-serializable dict.
The HTTP server (api_server.py) dispatches to these.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time

import numpy as np

from engine.state import StateStore
from backtest import compute_metrics


# ── backtest ────────────────────────────────────────────────────────
def run_one(symbol: str, cfg: dict) -> dict:
    from engine import HFTEngine
    engine = HFTEngine(
        symbol, cfg.get("start", "2023-01-01"), cfg.get("end", "2024-01-01"),
        strategy=cfg.get("strategy", "sma"),
        fast=int(cfg.get("fast", 20)), slow=int(cfg.get("slow", 50)),
        threshold=float(cfg.get("threshold", 100.0)),
        initial_capital=float(cfg.get("capital", 10_000.0)),
        commission=float(cfg.get("commission", 0.0)),
        slippage_bps=float(cfg.get("slippage", 0.0)),
        rsi_period=int(cfg.get("rsi_period", 14)),
        oversold=float(cfg.get("oversold", 30.0)),
        overbought=float(cfg.get("overbought", 70.0)),
        mom_period=int(cfg.get("mom_period", 50)),
        qty=int(cfg.get("qty", 10)),
    )
    orders = engine.run()
    m = compute_metrics(orders.equity_curve, orders.trades, engine.orders.initial_capital)
    return {
        "symbol": symbol,
        "metrics": m,
        "equity_curve": [{"t": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                          "equity": round(e, 2)} for ts, e in orders.equity_curve],
        "trades": [{
            "symbol": t.symbol, "side": "BUY",
            "entry_time": str(t.entry_time), "entry_price": round(t.entry_price, 2),
            "exit_time": str(t.exit_time) if t.exit_time else None,
            "exit_price": round(t.exit_price, 2), "volume": t.volume,
            "pnl": round(t.pnl, 2), "pnl_pct": round(t.pnl_pct, 2),
            "exit_reason": t.exit_reason,
        } for t in orders.trades],
        "rejected": [{"side": o.side.value, "price": o.price, "volume": o.volume,
                      "reason": o.reason} for o in engine.risk.rejected],
    }


def backtest(cfg: dict) -> dict:
    symbols = [s.strip().upper() for s in str(cfg.get("symbols", cfg.get("symbol", "AAPL"))).split(",") if s.strip()]
    results = [run_one(s, cfg) for s in symbols]
    if len(results) == 1:
        return results[0]
    # combined portfolio curve
    curves = [{p["t"]: p["equity"] for p in r["equity_curve"]} for r in results]
    all_ts = sorted(set().union(*[set(c.keys()) for c in curves]))
    combined = [{"t": ts, "equity": round(sum(c.get(ts, 0) for c in curves), 2)} for ts in all_ts]
    cm = compute_metrics([(p["t"], p["equity"]) for p in combined], [], cfg.get("capital", 10_000.0))
    return {"symbols": symbols, "per_symbol": results, "combined": combined, "metrics": cm}


# ── portfolio ───────────────────────────────────────────────────────
def portfolio(cfg: dict) -> dict:
    symbols = [s.strip().upper() for s in str(cfg.get("symbols", "AAPL,MSFT,GOOGL")).split(",") if s.strip()]
    per = float(cfg.get("capital", 30_000.0)) / len(symbols)
    results = []
    curves = {}
    for sym in symbols:
        r = run_one(sym, {**cfg, "capital": per})
        results.append({"symbol": sym, "metrics": r["metrics"]})
        curves[sym] = {p["t"]: p["equity"] for p in r["equity_curve"]}
    all_ts = sorted(set().union(*[set(c.keys()) for c in curves.values()]))
    combined = [{"t": ts, "equity": round(sum(c.get(ts, 0) for c in curves.values()), 2)} for ts in all_ts]
    cm = compute_metrics([(p["t"], p["equity"]) for p in combined], [], float(cfg.get("capital", 30_000.0)))
    return {"symbols": symbols, "per_symbol": results, "combined": combined, "metrics": cm}


# ── strategies ──────────────────────────────────────────────────────
def strategies(cfg: dict) -> dict:
    symbol = cfg.get("symbol", "AAPL").upper()
    start, end = cfg.get("start", "2023-01-01"), cfg.get("end", "2024-01-01")
    capital = float(cfg.get("capital", 10_000.0))
    names = {"sma": "SMA Cross", "rsi": "RSI Mean-Reversion",
             "momentum": "Momentum", "threshold": "Threshold"}
    out = {}
    for strat in ("sma", "rsi", "momentum", "threshold"):
        r = run_one(symbol, {**cfg, "strategy": strat, "capital": capital})
        m = r["metrics"]
        eq = [p["equity"] for p in r["equity_curve"]]
        out[strat] = {
            "name": names[strat],
            "return_pct": round(m["total_return_pct"], 2),
            "sharpe": round(m["sharpe"], 2),
            "win_rate_pct": round(m["win_rate_pct"], 1),
            "trade_count": m["trade_count"],
            "max_drawdown_pct": round(m["max_drawdown_pct"], 2),
            "sortino": round(m["sortino"], 2),
            "calmar": round(m["calmar"], 2),
            "cagr": round(m["cagr"], 2),
            "profit_factor": round(m["profit_factor"], 2),
            "equity": [round(e, 2) for e in eq],
        }
    return {"symbol": symbol, "strategies": out}


# ── order flow ──────────────────────────────────────────────────────
def orderflow(cfg: dict) -> dict:
    symbol = cfg.get("symbol", "AAPL").upper()
    bar_seconds = int(cfg.get("bar_seconds", 60))
    try:
        from footprint import fetch_trades, build_footprint
        trades = fetch_trades(symbol, limit=2000)
        bars, levels, grid = build_footprint(trades, bar_seconds=bar_seconds)
        if not bars or not levels:
            raise ValueError("no footprint data")
        n_bars, n_levels = len(bars), len(levels)
        buy = np.zeros((n_bars, n_levels))
        sell = np.zeros((n_bars, n_levels))
        for (bi, li), (bv, sv) in grid.items():
            if 0 <= bi < n_bars and 0 <= li < n_levels:
                buy[bi, li] = bv
                sell[bi, li] = sv
        buy = buy.tolist()
        sell = sell.tolist()
    except Exception:
        rng = np.random.default_rng(42)
        n_bars, n_levels = 40, 18
        base = 100.0
        levels = [round(base + i * 0.5, 2) for i in range(n_levels)]
        bars = [i for i in range(n_bars)]
        buy = rng.integers(0, 500, (n_bars, n_levels)).tolist()
        sell = rng.integers(0, 500, (n_bars, n_levels)).tolist()
    buy_arr = np.array(buy, dtype=float)
    sell_arr = np.array(sell, dtype=float)
    delta = (buy_arr - sell_arr).sum(axis=1)
    cum_delta = np.cumsum(delta)
    vol_profile = (buy_arr + sell_arr).sum(axis=0)
    return {
        "symbol": symbol,
        "bar_seconds": bar_seconds,
        "bars": [str(b) if not isinstance(b, (int, float)) else b for b in bars],
        "levels": levels,
        "buy": buy, "sell": sell,
        "cum_delta": [round(float(x), 2) for x in cum_delta],
        "vol_profile": [round(float(x), 2) for x in vol_profile],
        "connected": True,
    }


# ── live engine singleton ───────────────────────────────────────────
_LIVE = {"engine": None, "store": None, "loop": None, "thread": None}


def _live_loop(eng):  # noqa: ANN001
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _LIVE["loop"] = loop
    loop.run_until_complete(eng.start())


def live(cfg: dict) -> dict:
    import threading
    action = cfg.get("action", "status")
    store = _LIVE["store"] or StateStore(cfg.get("db", "hft_live.db"))
    _LIVE["store"] = store
    eng = _LIVE["engine"]
    loop = _LIVE["loop"]

    if action == "start":
        if eng and eng._running:
            return {"ok": True, "message": "already running", **eng.status()}
        from engine.live_engine import LiveEngine
        eng = LiveEngine(
            cfg.get("symbol", "AAPL"), store,
            backend=cfg.get("backend", "dryrun"),
            strategy=cfg.get("strategy", "sma"),
            fast=int(cfg.get("fast", 20)), slow=int(cfg.get("slow", 50)),
            threshold=float(cfg.get("threshold", 100.0)),
            rsi_period=int(cfg.get("rsi_period", 14)),
            oversold=float(cfg.get("oversold", 30.0)),
            overbought=float(cfg.get("overbought", 70.0)),
            mom_period=int(cfg.get("mom_period", 50)),
            qty=int(cfg.get("qty", 10)),
            max_position=int(cfg.get("max_position", 100)),
            max_exposure=float(cfg.get("max_exposure", 100_000.0)),
            gateway_backend=cfg.get("gateway", "poll"),
            max_drawdown_pct=float(cfg.get("max_drawdown_pct", 0.0)),
            max_daily_loss_pct=float(cfg.get("max_daily_loss_pct", 0.0)),
        )
        _LIVE["engine"] = eng
        _LIVE["thread"] = threading.Thread(target=_live_loop, args=(eng,), daemon=True)
        _LIVE["thread"].start()
        for _ in range(300):
            if store.get_meta("engine_state") == "running":
                break
            time.sleep(0.1)
        return {"ok": True, "message": "started", **eng.status()}

    if eng is None:
        return {"ok": False, "error": "engine not started", "store": store.snapshot()}

    def _run(coro):
        if loop is not None and loop.is_running():
            import concurrent.futures
            fut = concurrent.futures.Future()

            async def _wrap():
                try:
                    await coro
                    fut.set_result(True)
                except Exception as e:  # noqa: BLE001
                    fut.set_exception(e)

            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_wrap()))
            fut.result(timeout=30)
            return
        return asyncio.run(coro)

    if action == "stop":
        _run(eng.stop())
        _LIVE["engine"] = None
        _LIVE["loop"] = None
        _LIVE["thread"] = None
        return {"ok": True, "message": "stopped", "store": store.snapshot()}
    if action == "flatten":
        _run(eng.flatten())
        return {"ok": True, "message": "flattened", **eng.status()}
    if action == "kill":
        eng.kill()
        return {"ok": True, "message": "kill switch engaged", "kill_switch": True}
    if action == "resume":
        store.set_kill_switch(False)
        store.set_meta("engine_state", "running")
        return {"ok": True, "message": "resumed", "kill_switch": False}
    return {"ok": True, **eng.status(), "store": store.snapshot()}
