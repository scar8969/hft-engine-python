"""Backtest metrics: returns, win rate, max drawdown, Sharpe."""
import math

import numpy as np


def compute_metrics(equity_curve, trades, initial_capital, risk_free=0.0):
    equities = np.array([e for _, e in equity_curve])
    if len(equities) < 2:
        return {}

    # total return
    total_return = (equities[-1] / initial_capital - 1) * 100

    # max drawdown
    peak = np.maximum.accumulate(equities)
    drawdown = (equities - peak) / peak
    max_dd = float(drawdown.min() * 100)

    # Sharpe (annualized, daily bars)
    rets = np.diff(equities) / equities[:-1]
    std = rets.std()
    sharpe = (rets.mean() - risk_free / 252) / std * math.sqrt(252) if std > 0 else 0.0

    # trade stats
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0.0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0.0

    return {
        "total_return_pct": total_return,
        "max_drawdown_pct": max_dd,
        "sharpe": sharpe,
        "trade_count": len(trades),
        "win_rate_pct": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "final_equity": float(equities[-1]),
    }
