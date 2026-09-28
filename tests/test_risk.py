"""RiskManager validation rules."""
from conftest import make_order
from engine.models import OrderSide, OrderStatus
from engine.risk import RiskManager


class TestExposureLimit:
    def test_rejects_order_over_max_exposure(self):
        rm = RiskManager(max_exposure=100_000.0)
        order = make_order(price=5000.0, volume=30)  # 150k > 100k
        assert rm.validate(order, current_position=0) is False
        assert order.status == OrderStatus.REJECTED
        assert "max exposure" in order.reason
        assert order in rm.rejected

    def test_accepts_order_under_max_exposure(self):
        rm = RiskManager(max_exposure=100_000.0)
        order = make_order(price=100.0, volume=10)  # 1k
        assert rm.validate(order, current_position=0) is True
        assert order.status == OrderStatus.FILLED
        assert rm.rejected == []


class TestPositionCap:
    def test_rejects_buy_breaching_max_position(self):
        rm = RiskManager(max_position=100)
        order = make_order(side=OrderSide.BUY, price=10.0, volume=60)
        assert rm.validate(order, current_position=50) is False  # 110 > 100
        assert order.status == OrderStatus.REJECTED
        assert "max" in order.reason

    def test_accepts_buy_within_cap(self):
        rm = RiskManager(max_position=100)
        order = make_order(side=OrderSide.BUY, price=10.0, volume=40)
        assert rm.validate(order, current_position=50) is True

    def test_sell_never_capped_by_position(self):
        rm = RiskManager(max_position=100)
        order = make_order(side=OrderSide.SELL, price=10.0, volume=500)
        assert rm.validate(order, current_position=500) is True
        assert order.status == OrderStatus.FILLED


class TestCashSufficiency:
    def test_rejects_buy_exceeding_cash(self):
        rm = RiskManager(max_exposure=100_000.0)
        order = make_order(side=OrderSide.BUY, price=100.0, volume=200)  # 20k > 10k
        assert rm.validate(order, current_position=0, cash=10_000.0) is False
        assert order.status == OrderStatus.REJECTED
        assert "cash" in order.reason

    def test_accepts_buy_within_cash(self):
        rm = RiskManager(max_exposure=100_000.0)
        order = make_order(side=OrderSide.BUY, price=100.0, volume=50)  # 5k < 10k
        assert rm.validate(order, current_position=0, cash=10_000.0) is True
        assert order.status == OrderStatus.FILLED

    def test_sell_ignores_cash(self):
        rm = RiskManager(max_exposure=100_000.0)
        order = make_order(side=OrderSide.SELL, price=100.0, volume=200)
        # selling doesn't need cash — only buys are cash-constrained
        assert rm.validate(order, current_position=200, cash=0.0) is True

    def test_no_cash_arg_keeps_old_behavior(self):
        rm = RiskManager(max_exposure=1_000_000.0, max_position=1000)
        order = make_order(side=OrderSide.BUY, price=100.0, volume=200)
        # cash not passed → no cash check (backward compat)
        assert rm.validate(order, current_position=0) is True


class TestBoundary:
    def test_exposure_exactly_at_limit_passes(self):
        rm = RiskManager(max_exposure=1000.0)
        order = make_order(price=100.0, volume=10)  # == 1000, not >
        assert rm.validate(order, current_position=0) is True

    def test_position_exactly_at_cap_passes(self):
        rm = RiskManager(max_position=100)
        order = make_order(side=OrderSide.BUY, price=1.0, volume=50)
        assert rm.validate(order, current_position=50) is True  # == 100, not >
