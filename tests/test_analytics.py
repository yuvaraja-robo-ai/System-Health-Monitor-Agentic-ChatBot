"""Unit tests for analytics modules — no server, no DB required."""

import time
import pytest


# ──────────────────────────────────────────────
# correlate._pearson
# ──────────────────────────────────────────────

def test_pearson_perfect_positive():
    from app.analytics.correlate import _pearson
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [2.0, 4.0, 6.0, 8.0, 10.0]
    r = _pearson(a, b)
    assert r is not None
    assert abs(r - 1.0) < 1e-6


def test_pearson_perfect_negative():
    from app.analytics.correlate import _pearson
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [5.0, 4.0, 3.0, 2.0, 1.0]
    r = _pearson(a, b)
    assert r is not None
    assert abs(r + 1.0) < 1e-6


def test_pearson_constant_returns_none():
    from app.analytics.correlate import _pearson
    a = [3.0] * 10
    b = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert _pearson(a, b) is None


def test_pearson_too_short_returns_none():
    from app.analytics.correlate import _pearson
    assert _pearson([1.0, 2.0], [1.0, 2.0]) is None


# ──────────────────────────────────────────────
# health._compute_score
# ──────────────────────────────────────────────

def _sys(cpu=0, mem_pct=0, cores=4, load1=0, sat_pct=None, disks=None, temps=None, pressure=None):
    total_mem = 4 * 1024 ** 3
    used_mem = int(total_mem * mem_pct / 100)
    load_val = load1 if load1 else 0.0
    return {
        "cpu": {
            "total": cpu,
            "cores": cores,
            "load": [load_val, load_val, load_val],
            "saturation_pct": sat_pct,
            "per_core": [],
        },
        "mem": {"total": total_mem, "used": used_mem, "available": total_mem - used_mem},
        "disks": disks or [{"mount": "/", "pct": 50, "used": 10, "total": 100}],
        "temps": temps or {},
        "pressure": pressure or {},
    }


def test_score_healthy_system():
    from app.analytics.health import _compute_score
    result = _compute_score(_sys(cpu=20, mem_pct=40), {}, [], [], {})
    assert result["score"] == 100
    assert result["drivers"] == []


def test_score_high_cpu_warn():
    from app.analytics.health import _compute_score
    result = _compute_score(_sys(cpu=80), {}, [], [], {})
    assert result["score"] < 100
    factors = [d["factor"] for d in result["drivers"]]
    assert "cpu_util" in factors


def test_score_high_cpu_err():
    from app.analytics.health import _compute_score
    result = _compute_score(_sys(cpu=95), {}, [], [], {})
    cpu_driver = next(d for d in result["drivers"] if d["factor"] == "cpu_util")
    assert cpu_driver["weight"] <= -10


def test_score_high_mem():
    from app.analytics.health import _compute_score
    result = _compute_score(_sys(mem_pct=95), {}, [], [], {})
    factors = [d["factor"] for d in result["drivers"]]
    assert "mem_util" in factors


def test_score_saturation_penalty():
    from app.analytics.health import _compute_score
    # load > 1.5x cores → saturation penalty
    result = _compute_score(_sys(cores=4, load1=8.0, sat_pct=200.0), {}, [], [], {})
    factors = [d["factor"] for d in result["drivers"]]
    assert "cpu_saturation" in factors
    sat = next(d for d in result["drivers"] if d["factor"] == "cpu_saturation")
    assert sat["weight"] <= -15


def test_score_psi_memory_pressure():
    from app.analytics.health import _compute_score
    pressure = {"memory": {"some_avg10": 15.0, "full_avg10": 5.0}}
    result = _compute_score(_sys(pressure=pressure), {}, [], [], {})
    factors = [d["factor"] for d in result["drivers"]]
    assert "mem_pressure" in factors


def test_score_disk_full():
    from app.analytics.health import _compute_score
    disks = [{"mount": "/", "pct": 97, "used": 97, "total": 100}]
    result = _compute_score(_sys(disks=disks), {}, [], [], {})
    factors = [d["factor"] for d in result["drivers"]]
    assert "disk" in factors


def test_score_with_leaks():
    from app.analytics.health import _compute_score
    leaks = [{"flagged": True, "name": "myapp", "pid": 123, "slope_mb_min": 1.5}]
    result = _compute_score(_sys(), {}, [], leaks, {})
    factors = [d["factor"] for d in result["drivers"]]
    assert "leaks" in factors


def test_score_with_crashes():
    from app.analytics.health import _compute_score
    result = _compute_score(_sys(), {}, [], [], {"myapp": 5})
    factors = [d["factor"] for d in result["drivers"]]
    assert "crashes" in factors


def test_score_with_anomalies():
    from app.analytics.health import _compute_score
    anomalies = [{"metric": "cpu.total", "z": 4.2, "value": 95}]
    result = _compute_score(_sys(), {}, anomalies, [], {})
    factors = [d["factor"] for d in result["drivers"]]
    assert "anomalies" in factors


def test_score_drivers_sorted_by_weight():
    from app.analytics.health import _compute_score
    leaks = [{"flagged": True, "name": "a"}, {"flagged": True, "name": "b"}]
    anomalies = [{"metric": "cpu.total", "z": 5.0}]
    result = _compute_score(_sys(cpu=95, mem_pct=95), {}, anomalies, leaks, {"app": 4})
    weights = [d["weight"] for d in result["drivers"]]
    assert weights == sorted(weights)


def test_score_never_below_zero():
    from app.analytics.health import _compute_score
    leaks = [{"flagged": True}] * 10
    anomalies = [{"metric": f"m{i}", "z": 5.0} for i in range(10)]
    disks = [{"mount": f"/d{i}", "pct": 98} for i in range(5)]
    result = _compute_score(_sys(cpu=99, mem_pct=99, disks=disks), {}, anomalies, leaks, {"a": 10})
    assert result["score"] >= 0


def test_score_jetson_thermal():
    from app.analytics.health import _compute_score
    jetson = {"soc_temp": 85.0, "gpu_load": 50, "power_w": 5}
    result = _compute_score(_sys(), jetson, [], [], {})
    factors = [d["factor"] for d in result["drivers"]]
    assert "thermal" in factors


def test_score_jetson_gpu_high():
    from app.analytics.health import _compute_score
    jetson = {"soc_temp": 50.0, "gpu_load": 98.0, "power_w": 5}
    result = _compute_score(_sys(), jetson, [], [], {})
    factors = [d["factor"] for d in result["drivers"]]
    assert "gpu_util" in factors


# ──────────────────────────────────────────────
# anomaly detector (unit — no hub)
# ──────────────────────────────────────────────

def _feed_jitter(det, metric, center, n=50, base_ts=None):
    """Feed n samples with tiny jitter so stdev > 0 but z stays low."""
    ts = base_ts or int(time.time()) - n
    for i in range(n):
        # alternates center±0.5 — stdev ~0.5, far from spike
        det.observe(metric, center + (0.5 if i % 2 == 0 else -0.5), ts + i)


def test_anomaly_no_trigger_below_threshold():
    from app.analytics.anomaly import AnomalyDetector
    det = AnomalyDetector()
    # Tight jitter baseline — z always < 3
    _feed_jitter(det, "cpu.total", 50.0, n=50)
    assert len(det.active) == 0


def test_anomaly_triggers_on_spike():
    from app.analytics.anomaly import AnomalyDetector
    det = AnomalyDetector()
    _feed_jitter(det, "cpu.total", 20.0, n=55)
    # z = (20000 - 20) / 0.5 >> 3
    det.observe("cpu.total", 20000.0, int(time.time()))
    assert "cpu.total" in det.active


def test_anomaly_clears_after_normal():
    from app.analytics.anomaly import AnomalyDetector
    det = AnomalyDetector()
    _feed_jitter(det, "cpu.total", 20.0, n=55)
    det.observe("cpu.total", 20000.0, int(time.time()))
    assert "cpu.total" in det.active
    # Return to normal — z drops
    for i in range(5):
        det.observe("cpu.total", 20.0, int(time.time()) + i + 1)
    assert "cpu.total" not in det.active


def test_anomaly_history_records():
    from app.analytics.anomaly import AnomalyDetector
    det = AnomalyDetector()
    _feed_jitter(det, "mem.used", 1000.0, n=55)
    det.observe("mem.used", 9999999.0, int(time.time()))
    h = det.history(limit=10)
    assert len(h) >= 1
    assert h[-1]["metric"] == "mem.used"


# ──────────────────────────────────────────────
# thresholds API (unit)
# ──────────────────────────────────────────────

def test_thresholds_defaults():
    from app.api.thresholds import get_thresholds, _DEFAULTS
    t = get_thresholds()
    for k in _DEFAULTS:
        assert k in t


# ──────────────────────────────────────────────
# alert router dedup
# ──────────────────────────────────────────────

def test_alert_router_dedup():
    from app.alerts.router import AlertRouter
    router = AlertRouter()
    key = router._dedup_key("anomaly", "cpu spike")
    assert router._allowed(key) is True   # first call passes
    assert router._allowed(key) is False  # second within cooldown blocked


def test_alert_router_dedup_different_messages():
    from app.alerts.router import AlertRouter
    router = AlertRouter()
    assert router._allowed(router._dedup_key("anomaly", "cpu")) is True
    assert router._allowed(router._dedup_key("anomaly", "mem")) is True  # different key → passes


# ──────────────────────────────────────────────
# njmon flatten
# ──────────────────────────────────────────────

def test_flatten_njmon_basic():
    from app.api.apps import _flatten_njmon
    nested = {"cpu": {"total": 45.0, "load": [1.0, 0.5, 0.2]}, "name": "myapp"}
    flat = _flatten_njmon(nested)
    assert flat["name"] == "myapp"
    assert flat["cpu_total"] == 45.0
    assert flat["cpu_load_latest"] == 0.2


def test_flatten_njmon_no_nested():
    from app.api.apps import _flatten_njmon
    nested = {"score": 95, "host": "jetson"}
    flat = _flatten_njmon(nested)
    assert flat == nested


def test_flatten_njmon_empty_list():
    from app.api.apps import _flatten_njmon
    nested = {"history": []}
    flat = _flatten_njmon(nested)
    assert flat["history"] == []
