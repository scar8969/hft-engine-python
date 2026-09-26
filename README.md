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
- **Two strategies**:
  - `sma` — golden/death cross on fast/slow moving averages
  - `threshold` — the original repo's strategy (buy when price < threshold), kept for parity
- **Transaction costs** — per-order commission + adverse slippage in basis points
- **Portfolio mode** — comma-separated symbols, equal capital split, combined equity curve
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

# dashboard
streamlit run dashboard.py
```

## Sample results

| run | return | max DD | Sharpe | trades | win rate |
|-----|--------|--------|--------|--------|----------|
| AAPL 2023, sma 20/50 | +0.50% | -0.55% | 0.62 | 1 | 100% |
| AAPL 2023, threshold 180 | +7.00% | -1.28% | 2.62 | 4 | 100% |
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
  strategy.py       StrategyEngine — signal generation
  risk.py           RiskManager — pre-trade validation
  order_manager.py  OrderManager — execution, position, equity
  models.py         MarketData / Order / Trade dataclasses
  __init__.py       HFTEngine — event wiring
backtest.py         metrics (return, drawdown, Sharpe, win rate)
main.py             CLI
dashboard.py        Streamlit UI
```

## Why this exists

The C# original is a skeleton: a `MarketDataHandler` with a `NotImplementedException`, a strategy that buys whenever price < 100, and no way to evaluate performance. This rebuild keeps the same five-component architecture and the same threshold strategy, then adds what an HFT engine actually needs to be testable: a bar-replay backtest loop, transaction costs, portfolio aggregation, and a metrics layer.
