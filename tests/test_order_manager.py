"""OrderManager fills, slippage, commission, PnL, equity accounting."""
import pytest

from conftest import make_order
from engine.models import OrderSide
from engine.order_manager import OrderManager


class TestFills:
    def test_buy_deducts_cash_and_tracks_position(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        assert om.cash == pytest.approx(9000.0)
        assert om.position == 10
        assert om.avg_entry == pytest.approx(100.0)

    def test_sell_closes_round_trip_with_pnl(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        om.place_order(make_order(side=OrderSide.SELL, price=110.0, volume=10),
                       bar_close=110.0)
        assert om.position == 0
        assert len(om.trades) == 1
        t = om.trades[0]
        assert t.pnl == pytest.approx(100.0)          # (110-100)*10
        assert t.pnl_pct == pytest.approx(10.0)
        assert om.cash == pytest.approx(10_100.0)


class TestSlippage:
    def test_buyer_pays_more_seller_receives_less(self):
        om = OrderManager(initial_capital=10_000.0, slippage_bps=10.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        assert om.avg_entry == pytest.approx(100.10)  # +10bps
        om.place_order(make_order(side=OrderSide.SELL, price=110.0, volume=10),
                       bar_close=110.0)
        t = om.trades[0]
        assert t.exit_price == pytest.approx(109.89)  # -10bps
        assert t.pnl == pytest.approx((109.89 - 100.10) * 10)

    def test_zero_slippage_fills_at_order_price(self):
        om = OrderManager(slippage_bps=0.0)
        om.place_order(make_order(price=100.0, volume=1), bar_close=100.0)
        assert om.avg_entry == pytest.approx(100.0)


class TestCommission:
    def test_fees_charged_both_ways(self):
        om = OrderManager(initial_capital=10_000.0, commission=1.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        om.place_order(make_order(side=OrderSide.SELL, price=100.0, volume=10),
                       bar_close=100.0)
        assert om.total_fees == pytest.approx(2.0)
        # flat round trip loses exactly the commissions
        assert om.trades[0].pnl == pytest.approx(-1.0)
        assert om.cash == pytest.approx(10_000.0 - 2.0)


class TestEquity:
    def test_mark_to_market_includes_unrealized(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        om.mark_to_market("t1", close=105.0)
        assert om.equity_curve[-1] == ("t1", pytest.approx(9000.0 + 10 * 105.0))

    def test_finalize_closes_open_position(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        om.finalize(last_close=120.0)
        assert len(om.trades) == 1
        assert om.trades[0].exit_price == pytest.approx(120.0)
        assert om.trades[0].pnl == pytest.approx(200.0)
        assert om._open_entry is None

    def test_finalize_noop_when_flat(self):
        om = OrderManager()
        om.finalize(last_close=100.0)
        assert om.trades == []

    def test_avg_entry_averages_adds(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        om.place_order(make_order(price=200.0, volume=10), bar_close=200.0)
        assert om.avg_entry == pytest.approx(150.0)
        assert om.position == 20
