# HFT-Engine (Python Rebuild)

A from-scratch Python rebuild of [encryptedtouhid/HFT-Engine](https://github.com/encryptedtouhid/HFT-Engine) (C#).
Same 5-component architecture, but with a real backtest loop, event-driven wiring, and a metrics report.

## Architecture

```
HFT Engine
├── MarketDataHandler   # pulls OHLCV bars (yfinance), emits MarketData events
├── StrategyEngine      # subscribes to market data, emits Order signals
├── RiskManager         # validates every order before execution
├── OrderManager        # fills orders against the bar, tracks position/equity
└── Backtester          # replays history bar-by-bar, collects trades + equity curve
```

## Quick start

```bash
pip install yfinance pandas numpy
python main.py --symbol AAPL --start 2023-01-01 --end 2024-01-01 --strategy sma --fast 20 --slow 50
```

## Strategies

| name | logic |
|------|-------|
| `sma` | golden cross: buy when fast SMA crosses above slow SMA, sell on cross below |
| `threshold` | the original repo's strategy — buy when price < threshold (kept for parity) |

## Output

- console trade log + final metrics (total return, win rate, max drawdown, Sharpe, trade count)
- `equity_curve.csv` + `equity_curve.png` (equity vs buy&hold)
- `trades.csv` — every fill with entry/exit, PnL

## Files

- `engine/` — the 5 components
- `main.py` — CLI entry point
- `backtest.py` — replay loop
