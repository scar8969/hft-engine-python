# ⚡ HFT-Engine (Python)

A from-scratch Python rebuild of [encryptedtouhid/HFT-Engine](https://github.com/encryptedtouhid/HFT-Engine) (C#), with the backtest loop the original never shipped.

Event-driven architecture, identical component boundaries to the C# original, but wired to real market data (yfinance), a replay-based backtester, transaction-cost modeling, and a Streamlit dashboard.

## Architecture

```
                    ┌────────────────────┐
   yfinance ──────► │  MarketDataHandler │  pulls OHLCV bars, emits MarketData
                    └─────────┬──────────┘
                              │ on_market_data
                    ┌─────────▼──────────┐
                    │   StrategyEngine   │  SMA cross / threshold → Order signals
                    └─────────┬──────────┘
                              │ on_signal
                    ┌─────────▼──────────┐
                    │    RiskManager     │  validates exposure & position caps
                    └─────────┬──────────┘
                    ┌─────────▼──────────┐
                    │    OrderManager    │  fills at bar close (slippage + commission),
                    │                   │  tracks position, equity curve, closed trades
                    └────────────────────┘
```

## Features

- **Event-driven pipeline** — market data handler → strategy → risk → order manager, wired with callbacks exactly like the C# event model
- **Four strategies**:
  - `sma` — golden/death cross on fast/slow moving averages
  - `rsi` — mean reversion: buy when RSI crosses below oversold, sell when it crosses above overbought (Wilder smoothing)
  - `momentum` — trend following: buy when return over `mom_period` is positive, sell when negative
  - `threshold` — the original repo's strategy (buy when price < threshold), kept for parity
- **Transaction costs** — per-order commission + adverse slippage in basis points
- **Portfolio mode** — comma-separated symbols, equal capital split, combined equity curve
- **Walk-forward optimization** — rolling train/test windows, picks best params on train, validates out-of-sample
- **Alpaca paper trading** — live bridge to Alpaca's free paper account (no real money)
- **Risk manager** — max exposure ($) and max position (shares) rejection with reasons
- **Metrics** — total return, max drawdown, annualized Sharpe, win rate, avg win/loss, fees paid
- **Streamlit dashboard** — interactive config, per-symbol metrics, equity curves, trade table

## Quick start

```bash
pip install yfinance pandas numpy matplotlib streamlit

# single symbol
python main.py --symbol AAPL --start 2023-01-01 --end 2024-01-01 --strategy sma

# with transaction costs
python main.py --symbol AAPL --start 2023-01-01 --end 2024-01-01 --commission 1 --slippage 5

# portfolio mode
python main.py --symbol AAPL,MSFT,GOOGL --start 2022-01-01 --end 2024-01-01

# RSI mean reversion
python main.py --symbol AAPL --start 2022-01-01 --end 2024-01-01 --strategy rsi

# momentum
python main.py --symbol AAPL --start 2022-01-01 --end 2024-01-01 --strategy momentum --mom-period 50

# walk-forward optimization
python optimize.py --symbol AAPL --start 2020-01-01 --end 2024-01-01 --strategy sma

# live paper trading (polls latest bar, no real orders)
python papertrade.py --symbol AAPL --strategy rsi

# Alpaca paper trading (needs ALPACA_API_KEY + ALPACA_SECRET_KEY, paper keys)
python alpaca_bridge.py --symbol AAPL --strategy sma

# dashboard
streamlit run dashboard.py
```

## Deploy

Railway (Procfile included) or any streamlit-compatible host:

```bash
railway up   # needs a paid plan after trial
```

Or HuggingFace Spaces (free): create a Space with SDK "Streamlit", upload the repo, set `HF_TOKEN`.

## Sample results

| run | return | max DD | Sharpe | trades | win rate |
|-----|--------|--------|--------|--------|----------|
| AAPL 2023, sma 20/50 | +0.50% | -0.55% | 0.62 | 1 | 100% |
| AAPL 2023, threshold 180 | +7.00% | -1.28% | 2.62 | 4 | 100% |
| AAPL 2022–24, rsi 14/30/70 | +2.31% | -2.94% | 0.47 | 2 | 100% |
| AAPL 2022–24, momentum 50 | +0.45% | -3.74% | 0.10 | 10 | 40% |
| SPY 2020–2025, sma 20/50 | +15.33% | -11.81% | 0.64 | 11 | 54.5% |
| AAPL 2020–2025, sma 20/50 | +9.88% | -4.84% | 0.66 | 14 | 64.3% |

## Outputs

- `trades.csv` — every fill with entry/exit, PnL
- `equity_curve.csv` / `equity_curve.png` — strategy vs buy & hold
- `portfolio_equity.csv` / `.png` — combined portfolio curve (portfolio mode)

## Project layout

```
engine/
  market_data.py    MarketDataHandler — data feed (yfinance)
  strategy.py       StrategyEngine — signal generation (sma / rsi / momentum / threshold)
  risk.py           RiskManager — pre-trade validation
  order_manager.py  OrderManager — execution, position, equity
  models.py         MarketData / Order / Trade dataclasses
  __init__.py       HFTEngine — event wiring
backtest.py         metrics (return, drawdown, Sharpe, win rate)
main.py             CLI
optimize.py         walk-forward optimization
papertrade.py       live paper trading loop (no real orders)
alpaca_bridge.py    Alpaca paper trading bridge
dashboard.py        Streamlit UI
```

## Why this exists

The C# original is a skeleton: a `MarketDataHandler` with a `NotImplementedException`, a strategy that buys whenever price < 100, and no way to evaluate performance. This rebuild keeps the same five-component architecture and the same threshold strategy, then adds what an HFT engine actually needs to be testable: a bar-replay backtest loop, transaction costs, portfolio aggregation, and a metrics layer.
