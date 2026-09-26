"""build_footprint grid construction — pure function, no network."""
import pytest

from footprint import build_footprint


def trade(price, qty, side, ts):
    return {"price": price, "qty": qty, "side": side, "ts": ts}


class TestGrouping:
    def test_empty_trades(self):
        assert build_footprint([]) == ([], [], {})

    def test_single_bar_single_level_aggregates_sides(self):
        trades = [trade(100.0, 1.0, "buy", 0.0),
                  trade(100.0, 2.0, "sell", 5.0)]
        bars, levels, grid = build_footprint(trades, bar_seconds=10, tick_size=1.0)
        assert len(bars) == 1
        assert levels == pytest.approx([100.0])
        assert grid[(0, 0)] == pytest.approx([1.0, 2.0])  # [buy, sell]

    def test_bars_split_by_bar_seconds(self):
        trades = [trade(100.0, 1.0, "buy", 0.0),
                  trade(100.0, 1.0, "buy", 12.0)]
        bars, levels, grid = build_footprint(trades, bar_seconds=10, tick_size=1.0)
        assert len(bars) == 2
        assert bars[1] - bars[0] == 10
        assert (0, 0) in grid and (1, 0) in grid

    def test_levels_sorted_descending(self):
        trades = [trade(99.0, 1, "buy", 0), trade(101.0, 1, "buy", 0),
                  trade(100.0, 1, "buy", 0)]
        _, levels, _ = build_footprint(trades, bar_seconds=10, tick_size=1.0)
        assert levels == sorted(levels, reverse=True)
        assert levels == pytest.approx([101.0, 100.0, 99.0])

    def test_price_rounding_to_tick(self):
        # 100.004 and 99.996 both round to 100.0 at tick=0.01
        trades = [trade(100.004, 1.0, "buy", 0), trade(99.996, 2.0, "buy", 0)]
        _, levels, grid = build_footprint(trades, bar_seconds=10, tick_size=0.01)
        assert len(levels) == 1
        assert grid[(0, 0)][0] == pytest.approx(3.0)


class TestTickInference:
    def test_infers_tick_from_price_magnitude(self):
        # a hundredths-place fraction only survives rounding at tick 0.01
        _, levels, _ = build_footprint([trade(500.006, 1, "buy", 0)], bar_seconds=10)
        assert levels[0] == pytest.approx(500.01)
        # tenths-place fraction -> tick 0.1 for mid prices
        _, levels, _ = build_footprint([trade(5000.06, 1, "buy", 0)], bar_seconds=10)
        assert levels[0] == pytest.approx(5000.1)
        # whole-dollar tick for >= 10000
        _, levels, _ = build_footprint([trade(50000.6, 1, "buy", 0)], bar_seconds=10)
        assert levels[0] == pytest.approx(50001.0)


class TestDeltaConvention:
    def test_delta_is_buy_minus_sell(self):
        """footprint.py colors cells by buy-sell; demo_gif must match."""
        trades = [trade(100.0, 5.0, "buy", 0), trade(100.0, 3.0, "sell", 0)]
        _, _, grid = build_footprint(trades, bar_seconds=10, tick_size=1.0)
        b, s = grid[(0, 0)]
        assert b - s == pytest.approx(2.0)  # positive delta = net buying
