"""Streamlit dashboard for the HFT-Engine backtester."""
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, ".")
from engine import HFTEngine
from backtest import compute_metrics

st.set_page_config(page_title="HFT-Engine Backtester", layout="wide")
st.title("⚡ HFT-Engine — Backtest Dashboard")
st.caption("Python rebuild of the C# HFT-Engine · event-driven · market data → strategy → risk → order manager")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _run_backtest_tab():
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
        run = st.button("Run backtest", type="primary", width="stretch")

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
    st.dataframe(pd.DataFrame(rows), width="stretch")

    st.subheader("Equity curves (vs buy & hold)")
    fig, ax = plt.subplots(figsize=(11, 5))
    for sym, engine, orders, m in results:
        times = [ts for ts, _ in orders.equity_curve]
        eq = [e for _, e in orders.equity_curve]
        ax.plot(times, eq, label=f"{sym} ({m.get('total_return_pct', 0):+.1f}%)", linewidth=1.6)

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
    st.dataframe(pd.DataFrame(trade_rows), width="stretch")


def _run_footprint_tab():
    st.subheader("Live order flow — footprint")
    st.caption("ATAS-style bid/ask volume per price level per bar, from Binance public WebSocket (no API key)")

    col1, col2, col3 = st.columns(3)
    with col1:
        fsym = st.text_input("Symbol", "BTCUSDT").strip().upper()
    with col2:
        fbars = st.slider("Bars", 4, 20, 10)
    with col3:
        fsecs = st.selectbox("Bar size", [15, 30, 60, 120, 300], index=2)
    fgo = st.button("Render footprint", type="primary")

    if fgo:
        try:
            from footprint import fetch_trades, build_footprint, render_footprint
            import tempfile, os
            trades = fetch_trades(fsym, 2000)
            if not trades:
                st.error("no trades fetched — check symbol")
                return
            bars, levels, grid = build_footprint(trades, bar_seconds=fsecs)
            if len(bars) > fbars:
                keep = set(bars[-fbars:])
                bar_remap = {b: i for i, b in enumerate(bars[-fbars:])}
                grid = {k: v for k, v in grid.items() if bars[k[0]] in keep}
                grid = {(bar_remap[bars[k[0]]], k[1]): v for k, v in grid.items()}
                bars = bars[-fbars:]
            out = os.path.join(tempfile.gettempdir(), "footprint_live.png")
            render_footprint(bars, levels, grid, fsym, fsecs, out)
            st.image(out)
        except Exception as e:
            st.error(f"footprint failed: {e}")


def _run_portfolio_tab():
    st.subheader("Portfolio optimization (skfolio)")
    st.caption("Optimal weights from the engine's per-symbol returns — max Sharpe, min vol, risk parity")

    col1, col2, col3 = st.columns(3)
    with col1:
        psyms = st.text_input("Symbols", "AAPL,MSFT,GOOGL").strip().upper()
    with col2:
        pstart = st.date_input("Start", pd.Timestamp("2022-01-01").date())
    with col3:
        pend = st.date_input("End", pd.Timestamp("2024-01-01").date())
    pmethod = st.selectbox("Method", ["sharpe", "minvol", "riskparity"])
    pgo = st.button("Optimize", type="primary")

    if pgo:
        try:
            from portfolio import load_returns
            from skfolio import RiskMeasure
            from skfolio.optimization import MeanRisk, RiskBudgeting, ObjectiveFunction

            symbols = [s for s in psyms.split(",") if s.strip()]
            rets = load_returns(symbols, str(pstart), str(pend))
            if rets.empty or len(rets.columns) < 2:
                st.error("need at least 2 symbols with data")
                return

            if pmethod == "riskparity":
                model = RiskBudgeting(risk_measure=RiskMeasure.VARIANCE)
            else:
                model = MeanRisk(
                    risk_measure=RiskMeasure.VARIANCE,
                    objective_function=ObjectiveFunction.MAXIMIZE_UTILITY if pmethod == "sharpe"
                    else ObjectiveFunction.MINIMIZE_RISK,
                )
            model.fit(rets)
            weights = model.weights_

            st.write("**Optimal weights:**")
            wdf = pd.DataFrame({"Symbol": symbols, "Weight %": [round(w * 100, 1) for w in weights]})
            st.dataframe(wdf, width="stretch")

            port_ret = rets @ weights
            port_eq = (1 + port_ret).cumprod() * 10_000
            m = compute_metrics([(ts, e) for ts, e in port_eq.items()], [], 10_000)
            st.write(f"**Portfolio:** return {m['total_return_pct']:+.2f}%, "
                     f"maxDD {m['max_drawdown_pct']:.2f}%, sharpe {m['sharpe']:.2f}")

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
            ax1.bar(symbols, weights, color="#1f77b4")
            ax1.set_title(f"{pmethod} weights"); ax1.set_ylabel("weight")
            ax2.plot(port_eq.index, port_eq.values, linewidth=1.8)
            ax2.set_title("portfolio equity"); ax2.set_ylabel("equity ($)")
            ax2.grid(alpha=0.3)
            st.pyplot(fig)
        except Exception as e:
            st.error(f"optimization failed: {e}")


tab_backtest, tab_footprint, tab_portfolio = st.tabs(["Backtest", "Live Order Flow", "Portfolio Optimization"])

with tab_backtest:
    _run_backtest_tab()

with tab_footprint:
    _run_footprint_tab()

with tab_portfolio:
    _run_portfolio_tab()
