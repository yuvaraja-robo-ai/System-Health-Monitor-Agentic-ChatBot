"""Tests for chat endpoint and direct-answer layer."""

import asyncio

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


def test_parse_agent_response_handles_json_fences():
    from app.api.chat import _parse_agent_response

    parsed = _parse_agent_response(
        '```json\n{"tool_name":"get_live_context","tool_arguments":{"window":"5m"}}\n```'
    )
    assert parsed["tool_name"] == "get_live_context"
    assert parsed["tool_arguments"]["window"] == "5m"


def test_agentic_chat_uses_tool_loop(monkeypatch):
    from app.api.chat import ChatMessage, ChatRequest, chat_endpoint

    calls = iter(
        [
            {"text": '{"tool_name":"get_live_context","tool_arguments":{"window":"5m"}}', "backend": "ollama", "model": "test-model"},
            {"text": '{"answer":"Memory is climbing; inspect the top RSS process and recent error cluster."}', "backend": "ollama", "model": "test-model"},
        ]
    )

    async def fake_chat(messages, system=None, response_format=None):
        return next(calls)

    monkeypatch.setattr("app.api.chat._llm_configured", lambda: True)
    monkeypatch.setattr("app.api.chat._direct_answer", lambda question: None)
    monkeypatch.setattr("app.api.chat._needs_llm", lambda question: True)
    monkeypatch.setattr("app.api.chat.llm.chat", fake_chat)
    async def fake_collect_context_async(scope):
        return {
            "window_s": 300,
            "health": {"score": 72},
            "system": {},
            "leaks": [],
            "crashes": {"counts": {}, "recent_n": 0},
            "log_clusters": [],
            "top_procs": [],
            "scope": scope,
        }

    monkeypatch.setattr("app.api.chat.collect_context_async", fake_collect_context_async)
    monkeypatch.setattr("app.api.chat._digest_text", lambda ctx: "digest for scope")

    body = ChatRequest(messages=[ChatMessage(role="user", content="why is memory climbing?")])
    out = asyncio.run(chat_endpoint(body))
    assert out["backend"] == "ollama+agent"
    assert "Memory is climbing" in out["answer"]


def test_llm_configured_simple_resource_question_stays_direct(monkeypatch):
    from app.api.chat import ChatMessage, ChatRequest, chat_endpoint

    async def fail_chat(*args, **kwargs):
        raise AssertionError("simple resource questions should not call the LLM")

    monkeypatch.setattr("app.api.chat._llm_configured", lambda: True)
    monkeypatch.setattr("app.api.chat._direct_answer", lambda question: "CPU: 12.0%")
    monkeypatch.setattr("app.api.chat.llm.chat", fail_chat)

    body = ChatRequest(messages=[ChatMessage(role="user", content="what is the CPU usage?")])
    out = asyncio.run(chat_endpoint(body))
    assert out["backend"] == "direct"
    assert out["answer"] == "CPU: 12.0%"


def test_direct_log_status_answer(monkeypatch):
    from app.api.chat import _direct_answer

    monkeypatch.setattr(
        "app.api.chat.ldb.query_logs",
        lambda **kwargs: [
            {
                "ts": "2026-04-24T10:00:00",
                "level": "ERR",
                "service": "myapp.service",
                "message": "connection refused",
                "host": "host",
                "fields": {},
                "source": "journald",
            }
        ],
    )
    monkeypatch.setattr(
        "app.api.chat.ldb.cluster_logs",
        lambda since_s, limit=5: [
            {
                "service": "myapp.service",
                "level": "ERR",
                "count": 3,
                "sample": "connection refused",
                "first": "2026-04-24T09:55:00",
                "last": "2026-04-24T10:00:00",
            }
        ],
    )

    answer = _direct_answer("are logs available")
    assert answer is not None
    assert "Logs available check" in answer
    assert "stored row" in answer


def test_chat_prefers_direct_log_availability_answer(monkeypatch):
    from app.api.chat import ChatMessage, ChatRequest, chat_endpoint

    monkeypatch.setattr("app.api.chat._llm_configured", lambda: True)
    monkeypatch.setattr("app.api.chat._direct_answer", lambda question: "Logs available check: 4 stored row(s) found in 15m.")
    monkeypatch.setattr("app.api.chat._needs_llm", lambda question: False)

    body = ChatRequest(messages=[ChatMessage(role="user", content="check if logs are available")])
    out = asyncio.run(chat_endpoint(body))
    assert out["backend"] == "direct"
    assert "Logs available check" in out["answer"]
