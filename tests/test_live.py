"""Tests for the live engine: state store, broker router, latency, live engine wiring."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from engine.state import StateStore
from engine.broker import OrderRouter
from engine.latency import LatencyTracker


@pytest.fixture
def store(tmp_path):
    return StateStore(tmp_path / "test.db")


# ── StateStore ─────────────────────────────────────────────────────
class TestStateStore:
    def test_order_upsert_and_get(self, store):
        store.upsert_order({"id": "o1", "symbol": "AAPL", "side": "BUY", "qty": 10,
                            "price": 100.0, "status": "NEW"})
        o = store.get_order("o1")
        assert o["symbol"] == "AAPL" and o["status"] == "NEW"
        store.upsert_order({"id": "o1", "symbol": "AAPL", "side": "BUY", "qty": 10,
                            "price": 100.0, "status": "FILLED", "filled_qty": 10, "avg_fill": 100.5})
        assert store.get_order("o1")["status"] == "FILLED"

    def test_position_set_and_get(self, store):
        store.set_position("AAPL", 10, 100.0)
        assert store.get_position("AAPL")["qty"] == 10
        store.set_position("AAPL", 5, 102.0)
        assert store.get_position("AAPL")["qty"] == 5

    def test_kill_switch(self, store):
        assert store.kill_switch() is False
        store.set_kill_switch(True)
        assert store.kill_switch() is True

    def test_equity_append(self, store):
        store.append_equity(10000.0)
        store.append_equity(10100.0)
        eq = store.equity_curve()
        assert len(eq) == 2 and eq[-1]["equity"] == 10100.0

    def test_snapshot_shape(self, store):
        s = store.snapshot()
        assert set(s) >= {"orders", "trades", "positions", "equity", "kill_switch"}


# ── OrderRouter ────────────────────────────────────────────────────
class TestOrderRouter:
    def test_dryrun_fills_and_tracks_position(self, store):
        router = OrderRouter(store, backend="dryrun", fill_latency_ms=0)
        o = router.submit("AAPL", "BUY", 10, 100.0)
        assert o["status"] == "FILLED"
        assert o["filled_qty"] == 10
        assert o["avg_fill"] > 100.0  # buy pays slippage
        pos = store.get_position("AAPL")
        assert pos["qty"] == 10
        assert len(store.recent_trades()) == 1

    def test_dryrun_sell_reduces_position(self, store):
        router = OrderRouter(store, backend="dryrun", fill_latency_ms=0)
        router.submit("AAPL", "BUY", 10, 100.0)
        router.submit("AAPL", "SELL", 4, 105.0)
        assert store.get_position("AAPL")["qty"] == 6

    def test_idempotent_client_id(self, store):
        router = OrderRouter(store, backend="dryrun", fill_latency_ms=0)
        o1 = router.submit("AAPL", "BUY", 10, 100.0, client_id="c1")
        o2 = router.submit("AAPL", "BUY", 10, 100.0, client_id="c1")
        assert o1["id"] == o2["id"]
        assert len(store.recent_orders()) == 1

    def test_direct_partial_fills(self, store):
        router = OrderRouter(store, backend="direct", fill_latency_ms=0)
        o = router.submit("AAPL", "BUY", 100, 100.0)
        assert o["status"] == "FILLED"
        assert o["filled_qty"] == 100
        assert store.get_position("AAPL")["qty"] == 100

    def test_flatten(self, store):
        router = OrderRouter(store, backend="dryrun", fill_latency_ms=0)
        router.submit("AAPL", "BUY", 10, 100.0)
        router.flatten("AAPL", 105.0)
        assert store.get_position("AAPL")["qty"] == 0


# ── LatencyTracker ─────────────────────────────────────────────────
class TestLatency:
    def test_record_and_summary(self):
        lt = LatencyTracker(window=10)
        lt.record(0.0, 0.001, 0.005, 0.002)
        lt.record(1.0, 1.001, 1.006, 0.003)
        s = lt.summary()
        assert s["samples"] == 2
        assert s["signal_to_ack_ms"] == pytest.approx(1.0)
        assert s["ack_to_fill_ms"] == pytest.approx(4.5)  # (4 + 5) / 2
        assert s["total_ms"] == pytest.approx(5.5)  # (5 + 6) / 2
