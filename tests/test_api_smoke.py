"""Smoke tests for FastAPI routes — uses TestClient (no real server needed).

These tests verify routing, response shape, and basic logic without
requiring collectors to be running or the DB to be populated.
"""

import pytest


# ──────────────────────────────────────────────
# Core routes
# ──────────────────────────────────────────────

def test_root_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308)


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert "score" in j
    assert isinstance(j["score"], int)
    assert 0 <= j["score"] <= 100


def test_anomalies_endpoint(client):
    r = client.get("/api/anomalies")
    assert r.status_code == 200
    j = r.json()
    assert "current" in j
    assert "count" in j
    assert isinstance(j["current"], list)


def test_correlate_endpoint(client):
    r = client.get("/api/correlate?window=300&top=5")
    assert r.status_code == 200
    j = r.json()
    assert "volume" in j
    assert "pairs" in j
    assert isinstance(j["volume"], list)
    assert isinstance(j["pairs"], list)


def test_leaks_endpoint(client):
    r = client.get("/api/leaks")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_crashes_endpoint(client):
    r = client.get("/api/crashes")
    assert r.status_code == 200
    j = r.json()
    assert "counts" in j
    assert "recent" in j


# ──────────────────────────────────────────────
# Prometheus
# ──────────────────────────────────────────────

def test_prometheus_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert "# HELP" in body
    assert "# TYPE" in body


def test_prometheus_metric_names_valid(client):
    r = client.get("/metrics")
    for line in r.text.splitlines():
        if line.startswith("# "):
            continue
        if not line.strip():
            continue
        name = line.split("{")[0].split(" ")[0]
        assert name.startswith("sh_"), f"unexpected metric name: {name}"


# ──────────────────────────────────────────────
# Thresholds
# ──────────────────────────────────────────────

def test_get_thresholds(client):
    r = client.get("/api/config/thresholds")
    assert r.status_code == 200
    j = r.json()
    assert "cpu_warn" in j
    assert "cpu_err" in j
    assert j["cpu_warn"] < j["cpu_err"]


def test_post_thresholds(client):
    r = client.get("/api/config/thresholds")
    current = r.json()
    current["cpu_warn"] = 70
    current["cpu_err"] = 88
    r2 = client.post("/api/config/thresholds", json=current)
    assert r2.status_code == 200
    assert r2.json()["cpu_warn"] == 70
    assert r2.json()["cpu_err"] == 88


def test_reset_thresholds(client):
    r = client.post("/api/config/thresholds/reset")
    assert r.status_code == 200
    j = r.json()
    assert j["cpu_warn"] == 75  # default


# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

def test_get_polling_config(client):
    r = client.get("/api/config/polling")
    assert r.status_code == 200


def test_get_pinned_apps(client):
    r = client.get("/api/config/apps")
    assert r.status_code == 200
    assert "pinned" in r.json()


# ──────────────────────────────────────────────
# System / Processes
# ──────────────────────────────────────────────

def test_system_current(client):
    r = client.get("/api/system/current")
    assert r.status_code == 200


def test_processes_list(client):
    r = client.get("/api/processes")
    assert r.status_code == 200


# ──────────────────────────────────────────────
# Units / Services
# ──────────────────────────────────────────────

def test_units_endpoint(client):
    r = client.get("/api/units")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
