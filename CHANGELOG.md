# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Live order-flow feed (`livefeed.py`) — Binance WebSocket trades + depth, ATAS-style delta/volume bars
- Strategy comparison tool (`compare.py`)
- Parameter heatmap tool (`heatmap.py`)
- Walk-forward optimization for rsi/momentum/threshold strategies
- Momentum strategy
- Alpaca paper trading bridge (`alpaca_bridge.py`)
- RSI mean-reversion strategy
- Live paper trading loop (`papertrade.py`)
- Portfolio mode (multi-symbol, equal capital split)
- Transaction costs (commission + slippage)
- Streamlit dashboard (`dashboard.py`)

### Fixed
- Walk-forward cold-start bug — test windows now warm up indicators before slicing
- yfinance MultiIndex column flattening

## [0.1.0] - 2026-09-26

### Added
- Initial release: event-driven backtesting engine with SMA + threshold strategies
- Risk manager (max exposure, max position)
- Metrics (return, max drawdown, Sharpe, win rate)
- Equity curve + trades CSV output
