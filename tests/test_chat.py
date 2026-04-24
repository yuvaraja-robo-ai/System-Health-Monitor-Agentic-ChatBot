"""Tests for chat endpoint and direct-answer layer."""

import pytest


# ── direct answer (no LLM required) ──

def test_direct_cpu_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "what is the CPU usage"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"
    assert "CPU" in j["answer"] or "cpu" in j["answer"].lower()
    assert j["latency_ms"] < 500  # instant, no LLM call


def test_direct_memory_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "how much memory is used"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"
    assert "RAM" in j["answer"] or "B" in j["answer"]


def test_direct_disk_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "what is disk usage"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"


def test_direct_uptime_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "show uptime"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"
    assert "Uptime" in j["answer"]


def test_direct_health_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "what is the health score"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"
    assert "Health score" in j["answer"]


def test_direct_anomalies_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "any anomalies detected"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"


def test_direct_leaks_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "any memory leaks"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"


def test_direct_processes_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "show top processes"}]})
    assert r.status_code == 200
    j = r.json()
    # direct when hub has live data, kb/none when collectors haven't populated yet
    assert j["backend"] in ("direct", "kb", "none")
    assert len(j["answer"]) > 5


def test_direct_network_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "what is the network bandwidth"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"


def test_direct_load_average(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "show load average"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"
    assert "Load" in j["answer"]


def test_direct_crashes_answer(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "any crashes"}]})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"


# ── non-direct falls to none (no LLM in test env) ──

def test_non_direct_why_question(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "why is memory climbing"}]})
    assert r.status_code == 200
    j = r.json()
    # no LLM in tests — backend should be "none" or "kb"
    assert j["backend"] in ("none", "kb", "direct")
    assert len(j["answer"]) > 10


def test_chat_response_shape(client):
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "cpu"}]})
    assert r.status_code == 200
    j = r.json()
    assert "answer" in j
    assert "backend" in j
    assert "latency_ms" in j


def test_chat_conversation_history(client):
    """Multi-turn: second message references first."""
    messages = [
        {"role": "user", "content": "what is the CPU usage"},
        {"role": "assistant", "content": "CPU is at 45%"},
        {"role": "user", "content": "and memory?"},
    ]
    r = client.post("/api/chat", json={"messages": messages})
    assert r.status_code == 200
    j = r.json()
    assert j["backend"] == "direct"  # "memory" triggers direct answer


def test_chat_with_scope(client):
    r = client.post("/api/chat", json={
        "messages": [{"role": "user", "content": "show disk usage"}],
        "scope": {"window": "15m"},
    })
    assert r.status_code == 200
    assert r.json()["backend"] == "direct"
