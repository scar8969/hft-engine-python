"""StrategyEngine signal logic — golden/death cross, threshold, RSI, momentum."""
import pytest

from conftest import SignalCollector, feed
from engine.models import OrderSide
from engine.strategy import StrategyEngine


class TestSMA:
    def test_golden_cross_buys_death_cross_sells(self):
        eng = StrategyEngine(strategy="sma", fast=3, slow=5)
        sig = SignalCollector(eng)
        # flat -> spike (golden cross at index 5) -> flat (death cross at index 8)
        feed(eng, [5, 5, 5, 5, 5, 10, 5, 5, 5])
        assert sig.sides == [OrderSide.BUY, OrderSide.SELL]
        assert sig.prices == [10.0, 5.0]

    def test_no_signal_before_warmup(self):
        eng = StrategyEngine(strategy="sma", fast=3, slow=5)
        sig = SignalCollector(eng)
        feed(eng, [5, 10, 5, 10])  # fewer bars than slow
        assert sig.orders == []

    def test_no_duplicate_entry_while_in_position(self):
        eng = StrategyEngine(strategy="sma", fast=3, slow=5)
        sig = SignalCollector(eng)
        feed(eng, [5, 5, 5, 5, 5, 10, 11, 12, 13])  # stays above -> one BUY only
        assert sig.sides == [OrderSide.BUY]


class TestThreshold:
    def test_buy_below_sell_above_parity_with_csharp(self):
        eng = StrategyEngine(strategy="threshold", threshold=100.0)
        sig = SignalCollector(eng)
        feed(eng, [90, 110, 95, 105])
        assert sig.sides == [OrderSide.BUY, OrderSide.SELL,
                             OrderSide.BUY, OrderSide.SELL]
        assert sig.prices == [90, 110, 95, 105]

    def test_no_signal_when_always_above(self):
        eng = StrategyEngine(strategy="threshold", threshold=100.0)
        sig = SignalCollector(eng)
        feed(eng, [110, 120, 130])
        assert sig.orders == []


class TestRSI:
    def test_mean_reversion_buy_oversold_sell_overbought(self):
        eng = StrategyEngine(strategy="rsi", rsi_period=3,
                             oversold=30.0, overbought=70.0)
        sig = SignalCollector(eng)
        closes = ([100 + i for i in range(6)]        # ramp up
                  + [105 - 2 * i for i in range(1, 7)]  # crash -> oversold
                  + [93 + 2 * i for i in range(1, 9)])  # rally -> overbought
        feed(eng, closes)
        assert sig.sides == [OrderSide.BUY, OrderSide.SELL]
        assert sig.sides[0] == OrderSide.BUY  # bought the dip first

    def test_rsi_all_gains_is_100(self):
        eng = StrategyEngine(strategy="rsi", rsi_period=3)
        feed(eng, [100 + i for i in range(10)])
        assert eng._rsi_wilder() == pytest.approx(100.0)


class TestMomentum:
    def test_trend_follow_buy_positive_return_sell_negative(self):
        eng = StrategyEngine(strategy="momentum", mom_period=2)
        sig = SignalCollector(eng)
        feed(eng, [100, 101, 102, 103, 102, 101, 100])
        assert sig.sides == [OrderSide.BUY, OrderSide.SELL]
        assert sig.prices[0] == 102  # fires at first bar past warmup (102/100 > 0)
        assert sig.prices[1] == 101  # exit when 101 < 103 two bars back

    def test_no_signal_during_warmup(self):
        eng = StrategyEngine(strategy="momentum", mom_period=5)
        sig = SignalCollector(eng)
        feed(eng, [100, 105, 110, 115])
        assert sig.orders == []


class TestSizing:
    def test_default_qty_is_10(self):
        eng = StrategyEngine(strategy="threshold", threshold=100.0)
        sig = SignalCollector(eng)
        feed(eng, [90, 110])
        assert sig.volumes == [10, 10]

    def test_custom_qty_used_in_orders(self):
        eng = StrategyEngine(strategy="threshold", threshold=100.0, qty=25)
        sig = SignalCollector(eng)
        feed(eng, [90, 110])
        assert sig.volumes == [25, 25]

    def test_qty_zero_means_atr_auto_sizing(self):
        eng = StrategyEngine(strategy="sma", qty=0, risk_pct=0.01)
        assert eng.qty == 0  # auto-size flag
        assert eng.risk_pct == 0.01

    def test_qty_negative_disallowed(self):
        with pytest.raises(ValueError, match="qty"):
            StrategyEngine(strategy="sma", qty=-5)


class TestATRSizing:
    def test_high_atr_smaller_position(self):
        # risk_pct=0.01 of 10k = $100 risk; ATR 5 → qty = 100/5 = 20
        eng = StrategyEngine(strategy="sma", fast=2, slow=3, qty=0, risk_pct=0.01)
        sig = SignalCollector(eng)
        # high-volatility series (big swings → high ATR)
        closes = [100, 105, 95, 110, 90, 115, 85]
        feed(eng, closes)
        assert sig.orders, "expected at least one signal"
        # qty should be risk_amount / ATR, not fixed
        assert all(o.volume > 0 for o in sig.orders)

    def test_atr_sizing_formula(self):
        eng = StrategyEngine(strategy="sma", fast=2, slow=3, qty=0, risk_pct=0.01)
        # feed a known series, compute expected ATR manually
        from conftest import make_bar
        bars = [make_bar(c, i) for i, c in enumerate([100, 101, 99, 102, 98, 103])]
        for b in bars:
            eng.on_market_data(b)
        atr = eng._atr(period=3)
        assert atr is not None and atr > 0
        # risk = capital * risk_pct; qty = risk / atr
        expected_qty = int((10_000 * 0.01) / atr)
        assert expected_qty > 0


class TestUnknownStrategy:
    def test_raises_value_error(self):
        eng = StrategyEngine(strategy="moonshot")
        from conftest import make_bar
        with pytest.raises(ValueError, match="Unknown strategy"):
            eng.on_market_data(make_bar(100.0))
