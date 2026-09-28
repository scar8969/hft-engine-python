"""compute_metrics — returns, drawdown, Sharpe, win rate math."""
import math

import pytest

from backtest import compute_metrics
from engine.models import Trade


def make_trade(pnl):
    return Trade(symbol="T", entry_time=None, entry_price=100.0,
                 exit_time=None, exit_price=100.0, volume=1,
                 pnl=pnl, pnl_pct=pnl)


class TestReturns:
    def test_total_return_pct(self):
        curve = [(0, 100.0), (1, 110.0), (2, 105.0)]
        m = compute_metrics(curve, [], initial_capital=100.0)
        assert m["total_return_pct"] == pytest.approx(5.0)
        assert m["final_equity"] == pytest.approx(105.0)

    def test_flat_curve_zero_metrics(self):
        curve = [(0, 100.0), (1, 100.0), (2, 100.0)]
        m = compute_metrics(curve, [], initial_capital=100.0)
        assert m["total_return_pct"] == pytest.approx(0.0)
        assert m["max_drawdown_pct"] == pytest.approx(0.0)
        assert m["sharpe"] == 0.0  # zero-vol guard

    def test_too_short_curve_returns_zero_filled(self):
        m = compute_metrics([(0, 100.0)], [], 100.0)
        assert m["total_return_pct"] == 0.0
        assert m["trade_count"] == 0
        assert m["final_equity"] == pytest.approx(100.0)
        m2 = compute_metrics([], [], 100.0)
        assert m2["total_return_pct"] == 0.0
        assert m2["final_equity"] == pytest.approx(100.0)


class TestDrawdown:
    def test_max_drawdown_from_peak(self):
        curve = [(i, e) for i, e in enumerate([100, 120, 90, 110])]
        m = compute_metrics(curve, [], initial_capital=100.0)
        # peak 120 -> trough 90 = -25%
        assert m["max_drawdown_pct"] == pytest.approx(-25.0)

    def test_monotonic_up_has_zero_drawdown(self):
        curve = [(i, e) for i, e in enumerate([100, 110, 120, 130])]
        m = compute_metrics(curve, [], initial_capital=100.0)
        assert m["max_drawdown_pct"] == pytest.approx(0.0)


class TestSharpe:
    def test_sharpe_positive_for_steady_gains(self):
        curve = [(i, 100.0 * (1.01 ** i)) for i in range(252)]
        m = compute_metrics(curve, [], initial_capital=100.0)
        # constant 1% daily return, ~zero vol -> large positive sharpe
        assert m["sharpe"] > 100 or math.isinf(m["sharpe"]) or m["sharpe"] > 10

    def test_risk_free_shifts_sharpe_down(self):
        curve = [(i, 100.0 + i * 0.1 + (i % 3) * 0.05) for i in range(100)]
        m0 = compute_metrics(curve, [], 100.0, risk_free=0.0)
        m1 = compute_metrics(curve, [], 100.0, risk_free=10.0)
        assert m1["sharpe"] < m0["sharpe"]


class TestTradeStats:
    def test_win_rate_and_averages(self):
        trades = [make_trade(50), make_trade(30), make_trade(-20)]
        m = compute_metrics([(0, 100.0), (1, 160.0)], trades, 100.0)
        assert m["trade_count"] == 3
        assert m["win_rate_pct"] == pytest.approx(200 / 3)
        assert m["avg_win"] == pytest.approx(40.0)
        assert m["avg_loss"] == pytest.approx(-20.0)

    def test_no_trades_zero_win_rate(self):
        m = compute_metrics([(0, 100.0), (1, 100.0)], [], 100.0)
        assert m["trade_count"] == 0
        assert m["win_rate_pct"] == 0.0

    def test_zero_pnl_counts_as_loss(self):
        m = compute_metrics([(0, 100.0), (1, 100.0)], [make_trade(0)], 100.0)
        assert m["win_rate_pct"] == 0.0  # pnl <= 0 is a loss by convention


class TestRichMetrics:
    def test_all_new_fields_present(self):
        curve = [(i, 100.0 * (1.005 ** i)) for i in range(252)]
        trades = [make_trade(50), make_trade(30), make_trade(-20)]
        m = compute_metrics(curve, trades, 100.0)
        for key in ["sortino", "calmar", "cagr", "profit_factor",
                    "expectancy", "var_95", "avg_holding_days",
                    "total_return_pct", "max_drawdown_pct", "sharpe",
                    "trade_count", "win_rate_pct", "avg_win", "avg_loss",
                    "final_equity"]:
            assert key in m, f"missing metric {key}"

    def test_profit_factor_math(self):
        trades = [make_trade(100), make_trade(50), make_trade(-25), make_trade(-25)]
        m = compute_metrics([(0, 100.0), (1, 100.0)], trades, 100.0)
        assert m["profit_factor"] == pytest.approx(150.0 / 50.0)  # 3.0

    def test_expectancy_math(self):
        trades = [make_trade(100), make_trade(-50)]
        m = compute_metrics([(0, 100.0), (1, 100.0)], trades, 100.0)
        assert m["expectancy"] == pytest.approx(25.0)  # (100 - 50) / 2

    def test_cagr_positive_for_growth(self):
        curve = [(i, 100.0 * (1.01 ** i)) for i in range(252)]  # ~1yr daily
        m = compute_metrics(curve, [], 100.0)
        assert m["cagr"] > 0

    def test_var_95_negative_for_losses(self):
        # mostly losses -> VaR should be negative (worst 5% tail)
        curve = [(i, 100.0 - i * 0.1) for i in range(100)]
        m = compute_metrics(curve, [], 100.0)
        assert m["var_95"] < 0
