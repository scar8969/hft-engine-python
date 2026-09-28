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


class TestShorts:
    def test_sell_when_flat_opens_short(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(side=OrderSide.SELL, price=100.0, volume=10),
                       bar_close=100.0)
        assert om.position == -10
        assert om.cash == pytest.approx(11_000.0)  # 10k + 10*100 proceeds
        assert om._open_entry is not None

    def test_buy_closes_short_with_pnl(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(side=OrderSide.SELL, price=100.0, volume=10),
                       bar_close=100.0)
        om.place_order(make_order(price=90.0, volume=10), bar_close=90.0)  # buy back cheaper
        assert om.position == 0
        assert len(om.trades) == 1
        t = om.trades[0]
        assert t.pnl == pytest.approx(100.0)  # (100-90)*10 — short profit

    def test_short_loss_when_price_rises(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(side=OrderSide.SELL, price=100.0, volume=10),
                       bar_close=100.0)
        om.place_order(make_order(price=110.0, volume=10), bar_close=110.0)  # buy back dearer
        assert om.trades[0].pnl == pytest.approx(-100.0)

    def test_finalize_closes_short(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(side=OrderSide.SELL, price=100.0, volume=10),
                       bar_close=100.0)
        om.finalize(last_close=95.0)
        assert len(om.trades) == 1
        assert om.trades[0].pnl == pytest.approx(50.0)  # (100-95)*10

    def test_short_mark_to_market_equity(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(side=OrderSide.SELL, price=100.0, volume=10),
                       bar_close=100.0)
        om.mark_to_market("t1", close=90.0)
        # cash 11000 + position(-10) * 90 = 11000 - 900 = 10100
        assert om.equity_curve[-1] == ("t1", pytest.approx(10100.0))


class TestStopLossTakeProfit:
    def test_stop_loss_triggers_exit(self):
        om = OrderManager(initial_capital=10_000.0)
        order = make_order(price=100.0, volume=10)
        order.stop_loss = 0.05  # 5% below entry = 95
        om.place_order(order, bar_close=100.0)
        om.mark_to_market("t1", close=94.0)  # breaches 95
        assert len(om.trades) == 1
        assert om.trades[0].exit_reason == "stop_loss"
        assert om.trades[0].exit_price == pytest.approx(95.0)  # filled at stop level
        assert om.position == 0

    def test_take_profit_triggers_exit(self):
        om = OrderManager(initial_capital=10_000.0)
        order = make_order(price=100.0, volume=10)
        order.take_profit = 0.10  # 10% above entry = 110
        om.place_order(order, bar_close=100.0)
        om.mark_to_market("t1", close=111.0)  # breaches 110
        assert len(om.trades) == 1
        assert om.trades[0].exit_reason == "take_profit"
        assert om.trades[0].exit_price == pytest.approx(110.0)
        assert om.position == 0

    def test_no_exit_within_bands(self):
        om = OrderManager(initial_capital=10_000.0)
        order = make_order(price=100.0, volume=10)
        order.stop_loss = 0.05
        order.take_profit = 0.10
        om.place_order(order, bar_close=100.0)
        om.mark_to_market("t1", close=102.0)  # inside bands
        assert om.trades == []
        assert om.position == 10

    def test_stop_loss_on_short(self):
        om = OrderManager(initial_capital=10_000.0)
        order = make_order(side=OrderSide.SELL, price=100.0, volume=10)
        order.stop_loss = 0.05  # short stops 5% ABOVE entry = 105
        om.place_order(order, bar_close=100.0)
        om.mark_to_market("t1", close=106.0)
        assert len(om.trades) == 1
        assert om.trades[0].exit_reason == "stop_loss"
        assert om.position == 0

    def test_signal_exit_still_works(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        om.place_order(make_order(side=OrderSide.SELL, price=110.0, volume=10),
                       bar_close=110.0)
        assert om.trades[0].exit_reason == "signal"


class TestIntrabarFills:
    def test_buy_fills_at_open_when_open_below_close(self):
        om = OrderManager(initial_capital=10_000.0)
        # bar: open 98, high 105, low 97, close 104 — BUY fills at open (98)
        om.place_order(make_order(price=104.0, volume=10), bar_close=104.0,
                       bar_open=98.0, bar_high=105.0, bar_low=97.0)
        assert om.avg_entry == pytest.approx(98.0)

    def test_sell_fills_at_open_when_open_above_close(self):
        om = OrderManager(initial_capital=10_000.0)
        # bar: open 106, high 108, low 105, close 102 — SELL fills at open (106)
        om.place_order(make_order(side=OrderSide.SELL, price=102.0, volume=10),
                       bar_close=102.0, bar_open=106.0, bar_high=108.0, bar_low=105.0)
        assert om.avg_entry == pytest.approx(106.0)

    def test_no_ohlc_keeps_close_fill(self):
        om = OrderManager(initial_capital=10_000.0)
        om.place_order(make_order(price=100.0, volume=10), bar_close=100.0)
        assert om.avg_entry == pytest.approx(100.0)


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
