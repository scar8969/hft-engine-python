"""Monte Carlo bootstrap confidence bands."""
import pytest

from montecarlo import bootstrap


def test_band_ordering():
    curve = [(i, 100.0 * (1.01 ** i)) for i in range(100)]
    out = bootstrap(curve, n=200, seed=42)
    assert len(out["p5"]) == len(curve)
    assert len(out["p50"]) == len(curve)
    assert len(out["p95"]) == len(curve)
    # p5 <= p50 <= p95 at every point
    assert (out["p5"] <= out["p50"]).all()
    assert (out["p50"] <= out["p95"]).all()


def test_final_band_values():
    curve = [(i, 100.0 * (1.01 ** i)) for i in range(100)]
    out = bootstrap(curve, n=200, seed=42)
    assert out["final_p05"] <= out["final_p50"] <= out["final_p95"]
    # p50 should be near the actual final equity (100 * 1.01^99 ≈ 267.9)
    assert out["final_p50"] == pytest.approx(curve[-1][1], rel=0.15)


def test_deterministic_seed():
    curve = [(i, 100.0 + i) for i in range(50)]
    a = bootstrap(curve, n=100, seed=7)
    b = bootstrap(curve, n=100, seed=7)
    assert (a["p5"] == b["p5"]).all()
    assert (a["p95"] == b["p95"]).all()


def test_too_short_curve_raises():
    with pytest.raises(ValueError, match="too short"):
        bootstrap([(0, 100.0)], n=10)


def test_paths_shape():
    curve = [(i, 100.0 + i) for i in range(30)]
    out = bootstrap(curve, n=50, seed=1)
    assert out["paths"].shape == (50, 30)
