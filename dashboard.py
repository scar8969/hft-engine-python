"""Streamlit dashboard for the HFT-Engine backtester."""
import argparse
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, ".")
from engine import HFTEngine
from backtest import compute_metrics

st.set_page_config(page_title="HFT-Engine Backtester", layout="wide")
st.title("⚡ HFT-Engine — Backtest Dashboard")
st.caption("Python rebuild of the C# HFT-Engine · event-driven · market data → strategy → risk → order manager")

with st.sidebar:
    st.header("Configuration")
    symbol = st.text_input("Symbol(s)", "AAPL,MSFT").strip().upper()
    start = st.date_input("Start", pd.Timestamp("2022-01-01").date())
    end = st.date_input("End", pd.Timestamp("2024-01-01").date())
    strategy = st.selectbox("Strategy", ["sma", "threshold", "rsi", "momentum"])
    fast = st.slider("Fast SMA", 5, 60, 20)
    slow = st.slider("Slow SMA", 20, 200, 50)
    threshold = st.number_input("Threshold (for threshold strategy)", 50.0, 500.0, 180.0)
    rsi_period = st.slider("RSI period", 2, 30, 14)
    oversold = st.slider("RSI oversold", 10.0, 40.0, 30.0, 1.0)
    overbought = st.slider("RSI overbought", 60.0, 90.0, 70.0, 1.0)
    mom_period = st.slider("Momentum period", 10, 200, 50)
    capital = st.number_input("Initial capital ($)", 1_000.0, 1_000_000.0, 10_000.0, step=1_000.0)
    commission = st.number_input("Commission ($/order)", 0.0, 50.0, 1.0, step=0.5)
    slippage = st.number_input("Slippage (bps)", 0.0, 100.0, 5.0, step=1.0)
    run = st.button("Run backtest", type="primary", use_container_width=True)

if run or "last_result" not in st.session_state:
    symbols = [s for s in symbol.split(",") if s.strip()]
    if not symbols:
        st.error("Enter at least one symbol")
        st.stop()

    per = capital / len(symbols)
    results = []
    for sym in symbols:
        engine = HFTEngine(
            sym, str(start), str(end), strategy=strategy,
            fast=fast, slow=slow, threshold=threshold,
            initial_capital=per, commission=commission, slippage_bps=slippage,
            rsi_period=rsi_period, oversold=oversold, overbought=overbought,
            mom_period=mom_period,
        )
        orders = engine.run()
        m = compute_metrics(orders.equity_curve, orders.trades, per)
        m["symbol"] = sym
        m["final_equity"] = orders.equity_curve[-1][1] if orders.equity_curve else 0
        results.append((sym, engine, orders, m))

    st.session_state["last_result"] = results
    st.session_state["last_cfg"] = dict(symbol=symbol, start=str(start), end=str(end), strategy=strategy,
                                        capital=capital, commission=commission, slippage=slippage)

results = st.session_state["last_result"]
cfg = st.session_state["last_cfg"]

# ---- metrics table ------------------------------------------------------
st.subheader("Per-symbol metrics")
rows = []
for sym, engine, orders, m in results:
    rows.append({
        "Symbol": sym,
        "Return %": round(m.get("total_return_pct", 0), 2),
        "Max DD %": round(m.get("max_drawdown_pct", 0), 2),
        "Sharpe": round(m.get("sharpe", 0), 2),
        "Trades": m.get("trade_count", 0),
        "Win rate %": round(m.get("win_rate_pct", 0), 1),
        "Final equity": round(m.get("final_equity", 0), 2),
        "Fees $": round(orders.total_fees, 2),
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ---- equity curves -------------------------------------------------------
st.subheader("Equity curves (vs buy & hold)")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(11, 5))
for sym, engine, orders, m in results:
    times = [ts for ts, _ in orders.equity_curve]
    eq = [e for _, e in orders.equity_curve]
    ax.plot(times, eq, label=f"{sym} ({m.get('total_return_pct', 0):+.1f}%)", linewidth=1.6)

# combined buy & hold benchmark
if len(results) > 1:
    combined = {}
    for sym, engine, orders, m in results:
        for ts, e in orders.equity_curve:
            combined[ts] = combined.get(ts, 0) + e
    cc = sorted(combined.items())
    ax.plot([t for t, _ in cc], [e for _, e in cc], label="PORTFOLIO", linewidth=2.2, color="black")

ax.set_title(f"Equity curves — {cfg['symbol']} ({cfg['start']}..{cfg['end']})")
ax.set_xlabel("date"); ax.set_ylabel("equity ($)")
ax.legend(); ax.grid(alpha=0.3)
st.pyplot(fig)

# ---- trades table --------------------------------------------------------
st.subheader("Trades")
trade_rows = []
for sym, engine, orders, m in results:
    for t in orders.trades:
        trade_rows.append({
            "Symbol": t.symbol, "Entry": str(t.entry_time.date()),
            "Entry px": round(t.entry_price, 2),
            "Exit": str(t.exit_time.date()) if t.exit_time else "OPEN",
            "Exit px": round(t.exit_price, 2),
            "PnL $": round(t.pnl, 2), "PnL %": round(t.pnl_pct, 2),
        })
st.dataframe(pd.DataFrame(trade_rows), use_container_width=True)
