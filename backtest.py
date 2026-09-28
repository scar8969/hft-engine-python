"""Backtest metrics: returns, win rate, max drawdown, Sharpe."""
import math

import numpy as np


def compute_metrics(equity_curve, trades, initial_capital, risk_free=0.0):
    equities = np.array([e for _, e in equity_curve])
    if len(equities) < 2:
        return {"total_return_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe": 0.0,
                "trade_count": 0, "win_rate_pct": 0.0, "avg_win": 0.0,
                "avg_loss": 0.0, "final_equity": float(initial_capital),
                "sortino": 0.0, "calmar": 0.0, "cagr": 0.0, "profit_factor": 0.0,
                "expectancy": 0.0, "var_95": 0.0, "avg_holding_days": 0.0}

    # total return
    total_return = (equities[-1] / initial_capital - 1) * 100

    # max drawdown
    peak = np.maximum.accumulate(equities)
    drawdown = (equities - peak) / peak
    max_dd = float(drawdown.min() * 100)

    # returns series
    rets = np.diff(equities) / equities[:-1]
    n = len(rets)

    # Sharpe (annualized, daily bars)
    std = rets.std()
    sharpe = (rets.mean() - risk_free / 252) / std * math.sqrt(252) if std > 0 else 0.0

    # Sortino: downside deviation only
    downside = rets[rets < 0]
    dstd = downside.std() if len(downside) > 0 else 0.0
    sortino = (rets.mean() - risk_free / 252) / dstd * math.sqrt(252) if dstd > 0 else 0.0

    # CAGR: annualized growth over the curve
    years = n / 252
    cagr = ((equities[-1] / equities[0]) ** (1 / years) - 1) * 100 if years > 0 and equities[0] > 0 else 0.0

    # Calmar: CAGR / |max drawdown|
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0

    # trade stats
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0.0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0.0

    # profit factor: gross wins / |gross losses|
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)

    # expectancy: mean PnL per trade
    expectancy = np.mean([t.pnl for t in trades]) if trades else 0.0

    # VaR 95: 5th percentile of daily returns (negative = loss tail)
    var_95 = float(np.percentile(rets, 5) * 100) if n > 0 else 0.0

    # avg holding days: entry -> exit time span
    holding_days = []
    for t in trades:
        if t.entry_time and t.exit_time:
            holding_days.append((t.exit_time - t.entry_time).days)
    avg_holding_days = float(np.mean(holding_days)) if holding_days else 0.0

    return {
        "total_return_pct": total_return,
        "max_drawdown_pct": max_dd,
        "sharpe": sharpe,
        "trade_count": len(trades),
        "win_rate_pct": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "final_equity": float(equities[-1]),
        "sortino": sortino,
        "calmar": calmar,
        "cagr": cagr,
        "profit_factor": profit_factor,
        "expectancy": float(expectancy),
        "var_95": var_95,
        "avg_holding_days": avg_holding_days,
    }
