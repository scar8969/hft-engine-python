# Launch Pack — hft-engine-python

Copy-paste posts for launching https://github.com/scar8969/hft-engine-python
Pick one platform per day; LinkedIn first (recruiters), HN last (brutal crowd, post Tue–Thu 8–11am ET).

---

## LinkedIn

I rebuilt a C# HFT trading engine from scratch in Python — and shipped everything the original never had.

The original repo (encryptedtouhid/HFT-Engine) is a skeleton: a MarketDataHandler with NotImplementedException and a strategy that buys whenever price < 100. Fair enough as a teaching stub — but I wanted the real thing.

What's in the rebuild (~1500 lines, MIT):

→ Event-driven engine: market data → strategy → risk → order manager, wired with callbacks like the C# original
→ 4 strategies: SMA cross, RSI mean-reversion, momentum, and the original's threshold logic (kept for parity)
→ Real transaction costs: per-order commission + basis-point slippage — most toy backtesters skip these and lie to you
→ Walk-forward optimization (fixed the cold-start bug where test windows never warmed up indicators)
→ ATAS-style footprint charts from live Binance order flow — no API key needed
→ Portfolio optimization via skfolio: max Sharpe, min volatility, risk parity
→ Streamlit dashboard + CLI + CSV/PNG outputs
→ 49-test offline pytest suite, green in CI on every push

The one-line pitch: market data in, honest metrics out — returns, max drawdown, Sharpe, win rate — with costs modeled.

Try it in 10 seconds (no keys, no accounts):
git clone https://github.com/scar8969/hft-engine-python && cd hft-engine-python
pip install -r requirements.txt
python main.py --symbol AAPL --start 2023-01-01 --end 2024-01-01 --strategy sma

Feedback welcome — especially on the risk manager and fill model.

#algotrading #python #quantitativefinance #opensource #backtesting

---

## X / Twitter (thread)

1/ Rebuilt a C# HFT engine in Python from scratch. The original is a skeleton (NotImplementedException + "buy if price < 100"). Mine actually ships. 🧵

2/ Event-driven core: market data → strategy → risk → order manager, callback-wired like the C# original. 4 strategies: SMA cross, RSI mean-reversion, momentum, threshold.

3/ The part most toy backtesters skip: transaction costs. Per-order commission + bps slippage. Without them your backtest is a fantasy novel.

4/ Walk-forward optimization with proper warm-up (found + fixed a cold-start bug where test windows never primed indicators — silent killer of OOS results).

5/ Live order-flow footprint charts from Binance WebSocket — no API key. Animated demo GIF in the README. Plus portfolio opt (max Sharpe / min vol / risk parity) via skfolio.

6/ 49-test offline pytest suite running in CI. MIT licensed. ~1500 lines.

github.com/scar8969/hft-engine-python

7/ Try it: pip install -r requirements.txt && python main.py --symbol AAPL --start 2023-01-01 --end 2024-01-01 --strategy sma

No keys. No accounts. Metrics out: return, max DD, Sharpe, win rate.

---

## Hacker News (Show HN)

Title: Show HN: HFT-Engine in Python – event-driven backtester with order-flow footprints

Body:

I rebuilt encryptedtouhid/HFT-Engine (C#) from scratch in Python. The original is a teaching skeleton — handlers that throw NotImplementedException and a threshold strategy (buy if price < 100). I kept that strategy for parity but built everything around it into a working system:

- Event-driven pipeline: MarketDataHandler → StrategyEngine → RiskManager → OrderManager, wired with callbacks (mirrors the C# event model)
- Transaction costs: per-order commission + basis-point slippage on every fill
- Walk-forward optimization with indicator warm-up on test windows (the original design's cold-start bug silently poisons out-of-sample results)
- Live order-flow: Binance WebSocket trades + depth, ATAS-style footprint charts (bid/ask volume per price level, cumulative delta). No API key.
- Portfolio aggregation across symbols + skfolio optimization (max Sharpe, min vol, risk parity)
- 49 offline deterministic tests, CI-green; Streamlit dashboard; CLI with CSV/PNG export

Data: yfinance for daily bars (equities), Binance REST/WS for order flow (crypto). No paid feeds required anywhere.

github.com/scar8969/hft-engine-python

Happy to take criticism on the fill model (market-at-close with slippage) and the risk manager — those are the parts I'd want a practitioner to tear apart.

---

## Reddit (r/algotrading, r/quant, r/Python) — optional

Use the HN body, prefixed with: "Built this over a weekend as a learning exercise — rebuilt a C# skeleton into a working Python backtester with live order-flow footprints. Looking for feedback on the fill model and risk checks."

Rule: no link-only posts; engage in comments for the first 2 hours or mods remove it.

---

## Posting checklist

- [ ] README gif renders on GitHub (check on mobile)
- [ ] CI badge green before posting (add badge if wanted: actions/workflows/ci.yml)
- [ ] Pin the repo on GitHub profile
- [ ] LinkedIn: post Tue–Thu morning, attach the demo GIF directly (native video/gif > link)
- [ ] HN: Show HN on a weekday morning ET, reply to every comment same day
- [ ] X: thread, attach demo_footprint.gif to tweet 5
- [ ] Add topics on GitHub repo page: algorithmic-trading, backtesting, order-flow, hft, python, quantitative-finance
