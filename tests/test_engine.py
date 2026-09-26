"""HFTEngine end-to-end wiring with a stubbed data feed (no network)."""
import pytest

from conftest import make_bars
from engine import HFTEngine
from engine.market_data import MarketDataHandler


@pytest.fixture
def stub_feed(monkeypatch):
    def _stub(bars):
        monkeypatch.setattr(MarketDataHandler, "connect", lambda self: bars)
    return _stub


class TestWiring:
    def test_threshold_round_trip(self, stub_feed):
        bars = make_bars([90, 95, 110, 120, 80])
        stub_feed(bars)
        engine = HFTEngine("TEST", "2024-01-01", "2024-02-01",
                           strategy="threshold", threshold=100.0)
        om = engine.run()
        # BUY@90 -> SELL@110 (closed) -> BUY@80 (finalized at 80)
        assert len(om.trades) == 2
        assert om.trades[0].pnl == pytest.approx((110 - 90) * 10)
        assert om.position == 0 or om._open_entry is None
        assert len(om.equity_curve) == len(bars)

    def test_equity_curve_one_point_per_bar(self, stub_feed):
        bars = make_bars([100, 101, 102, 103, 104])
        stub_feed(bars)
        engine = HFTEngine("TEST", "2024-01-01", "2024-02-01", strategy="threshold")
        om = engine.run()
        assert len(om.equity_curve) == 5
        # never traded (all above default threshold=100 except equality edge)
        assert om.cash == pytest.approx(10_000.0)

    def test_risk_rejection_blocks_all_trades(self, stub_feed):
        bars = make_bars([90, 110, 90, 110])
        stub_feed(bars)
        engine = HFTEngine("TEST", "2024-01-01", "2024-02-01",
                           strategy="threshold", threshold=100.0)
        engine.risk.max_exposure = 1.0  # everything exceeds $1 -> all rejected
        om = engine.run()
        assert om.trades == []
        assert len(engine.risk.rejected) > 0
        assert om.cash == pytest.approx(10_000.0)

    def test_slippage_and_commission_reduce_pnl(self, stub_feed):
        bars = make_bars([90, 110])
        stub_feed(bars)
        clean = HFTEngine("TEST", "2024-01-01", "2024-02-01",
                          strategy="threshold", threshold=100.0)
        clean.run()
        dirty = HFTEngine("TEST", "2024-01-01", "2024-02-01",
                          strategy="threshold", threshold=100.0,
                          commission=5.0, slippage_bps=50.0)
        dirty.run()
        assert dirty.orders.trades[0].pnl < clean.orders.trades[0].pnl
        assert dirty.orders.total_fees == pytest.approx(10.0)

    def test_sma_strategy_runs_end_to_end(self, stub_feed):
        closes = [100 - i * 0.5 for i in range(60)] + \
                 [70 + i * 1.5 for i in range(60)]  # downtrend then uptrend
        stub_feed(make_bars(closes))
        engine = HFTEngine("TEST", "2024-01-01", "2025-01-01",
                           strategy="sma", fast=10, slow=30)
        om = engine.run()
        assert len(om.equity_curve) == 120
        assert any(t.pnl > 0 for t in om.trades)  # caught the reversal

    def test_unknown_strategy_raises(self, stub_feed):
        stub_feed(make_bars([100, 101]))
        engine = HFTEngine("TEST", "2024-01-01", "2024-02-01", strategy="yolo")
        with pytest.raises(ValueError, match="Unknown strategy"):
            engine.run()
