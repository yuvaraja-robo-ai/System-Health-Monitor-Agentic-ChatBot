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


def test_recent_application_errors_uses_log_clusters_not_process_list(monkeypatch):
    from app.api.chat import _direct_answer

    def fake_latest(topic):
        if topic == "processes":
            return {
                "data": {
                    "procs": [
                        {"pid": 167320, "name": "uvicorn", "cpu": 15.0, "rss": 343 * 1024 * 1024},
                    ]
                }
            }
        return None

    monkeypatch.setattr("app.api.chat.hub.latest", fake_latest)
    monkeypatch.setattr(
        "app.api.chat.ldb.cluster_logs",
        lambda since_s, limit=10: [
            {
                "service": "uvicorn",
                "level": "ERROR",
                "count": 4,
                "sample": "database connection failed",
            }
        ],
    )

    answer = _direct_answer("What are the recent errors from the applications")
    assert answer is not None
    assert answer.startswith("1 log cluster(s)")
    assert "uvicorn ERROR x4: database connection failed" in answer
    assert not answer.startswith("Top processes by CPU:")


def test_log_availability_does_not_route_to_sla(monkeypatch):
    from app.api.chat import _direct_answer

    monkeypatch.setattr("app.api.chat.ldb.query_logs", lambda **kwargs: [])
    monkeypatch.setattr("app.api.chat.ldb.cluster_logs", lambda since_s, limit=5: [])

    answer = _direct_answer("show log availability status")
    assert answer is not None
    assert answer.startswith("Logs available check:")
    assert not answer.startswith("SLA")


def test_system_resource_summary_combines_available_live_data(monkeypatch):
    from app.api.chat import _direct_answer

    def fake_latest(topic):
        if topic == "system":
            return {
                "data": {
                    "cpu": {"total": 42.0, "load": [1.25, 1.5, 1.75]},
                    "mem": {"used": 2 * 1024 * 1024 * 1024, "total": 8 * 1024 * 1024 * 1024},
                    "disks": [{"mount": "/", "pct": 73, "used": 73, "total": 100}],
                    "net": {"rx_bps": 2048, "tx_bps": 4096},
                }
            }
        if topic == "jetson":
            return {"data": {"gpu_load": 12.5, "power_w": 7.2}}
        if topic == "health":
            return {"data": {"score": 82, "drivers": []}}
        return None

    monkeypatch.setattr("app.api.chat.hub.latest", fake_latest)

    answer = _direct_answer("give me a current resource usage summary")
    assert answer is not None
    assert "Health score: 82/100" in answer
    assert "CPU: 42.0%" in answer
    assert "RAM:" in answer
    assert "Network: RX" in answer
    assert "Jetson: GPU 12.5%, power 7.2W" in answer


def test_sla_question_uses_health_history(monkeypatch):
    from app.api.chat import _direct_answer

    now = 1_000_000
    monkeypatch.setattr("app.api.sla.time.time", lambda: now)
    monkeypatch.setattr(
        "app.api.sla.sdb.history",
        lambda field, since, end, step: [
            (now - 180, 90.0),
            (now - 120, 55.0),
            (now - 60, 80.0),
        ],
    )

    answer = _direct_answer("what is the SLA uptime percentage and MTTR for 1h")
    assert answer is not None
    assert answer.startswith("SLA 1h:")
    assert "uptime 66.67%" in answer
    assert "incidents 1" in answer


def test_direct_apps_consuming_cpu_returns_process_list(monkeypatch):
    from app.api.chat import _direct_answer

    def fake_latest(topic):
        if topic == "system":
            return {"data": {"cpu": {"total": 10.1, "load": [2.74, 3.10, 3.40], "cores": 6}}}
        if topic == "processes":
            return {
                "data": {
                    "procs": [
                        {"pid": 101, "name": "api-server", "cpu": 31.2, "rss": 300 * 1024 * 1024},
                        {"pid": 202, "name": "worker", "cpu": 12.4, "rss": 900 * 1024 * 1024},
                        {"pid": 303, "name": "nginx", "cpu": 2.5, "rss": 80 * 1024 * 1024},
                    ]
                }
            }
        return None

    monkeypatch.setattr("app.api.chat.hub.latest", fake_latest)

    answer = _direct_answer("what are the applications consuming more CPU list out apps")
    assert answer is not None
    assert answer.startswith("Top processes by CPU:")
    assert "api-server (pid 101): cpu 31.2%" in answer
    assert "load avg" not in answer


def test_direct_each_process_cpu_returns_process_list(monkeypatch):
    from app.api.chat import _direct_answer

    def fake_latest(topic):
        if topic == "system":
            return {"data": {"cpu": {"total": 12.6, "load": [2.71, 3.08, 3.38], "cores": 6}}}
        if topic == "processes":
            return {
                "data": {
                    "procs": [
                        {"pid": 10, "name": "python", "cpu": 18.0, "rss": 100 * 1024 * 1024},
                        {"pid": 20, "name": "postgres", "cpu": 7.0, "rss": 500 * 1024 * 1024},
                    ]
                }
            }
        return None

    monkeypatch.setattr("app.api.chat.hub.latest", fake_latest)

    answer = _direct_answer("what are the applications consuming CPU . check each process")
    assert answer is not None
    assert answer.startswith("Top processes by CPU:")
    assert "python (pid 10): cpu 18.0%" in answer
    assert "postgres (pid 20): cpu 7.0%" in answer


def test_memory_leak_question_uses_leak_detector_not_memory_list(monkeypatch):
    from app.api.chat import _direct_answer

    def fake_latest(topic):
        if topic == "system":
            return {"data": {"mem": {"used": 2 * 1024 * 1024 * 1024, "total": 8 * 1024 * 1024 * 1024}}}
        if topic == "processes":
            return {
                "data": {
                    "procs": [
                        {"pid": 27813, "name": "llama-server", "cpu": 0.1, "rss": 3900 * 1024 * 1024},
                    ]
                }
            }
        return None

    class FakeLeakDetector:
        @staticmethod
        def current():
            return []

    monkeypatch.setattr("app.api.chat.hub.latest", fake_latest)
    monkeypatch.setattr("app.analytics.leak.detector", FakeLeakDetector)

    answer = _direct_answer("Is there any memory leak in applications")
    assert answer == "No memory leaks detected."


def test_direct_io_wait_keyword_returns_live_io_wait(monkeypatch):
    from app.api.chat import _direct_answer

    def fake_latest(topic):
        if topic == "system":
            return {
                "data": {
                    "io_wait": 7.5,
                    "pressure": {"io": {"some_avg10": 2.25, "full_avg10": 0.5}},
                }
            }
        return None

    monkeypatch.setattr("app.api.chat.hub.latest", fake_latest)

    answer = _direct_answer("show iowait and blocked io")
    assert answer is not None
    assert "I/O wait: 7.5%" in answer
    assert "io pressure some_avg10: 2.25%" in answer


def test_direct_jetson_doc_aliases_route_to_existing_support(monkeypatch):
    from app.api.chat import _direct_answer

    def fake_latest(topic):
        if topic == "jetson":
            return {
                "data": {
                    "gpu_load": 44.0,
                    "power_w": 12.3,
                    "power_mode": "MAXN",
                    "emc_load": 66.0,
                    "engines": {"NVDLA0": 25.0, "NVENC": 5.0},
                }
            }
        return None

    monkeypatch.setattr("app.api.chat.hub.latest", fake_latest)

    gpu_answer = _direct_answer("what is gr3d_freq doing")
    assert gpu_answer is not None
    assert "GPU load: 44.0%" in gpu_answer

    power_answer = _direct_answer("show nvpmodel and VDD power rail")
    assert power_answer is not None
    assert "Power mode: MAXN" in power_answer
    assert "Total power: 12.3W" in power_answer

    emc_answer = _direct_answer("show emc_freq and nvdla")
    assert emc_answer is not None
    assert "EMC (memory controller): 66.0%" in emc_answer
    assert "NVDLA0: 25%" in emc_answer


def test_gpu_process_and_power_question_does_not_return_cpu_process_list(monkeypatch):
    from app.api.chat import _direct_answer

    def fake_latest(topic):
        if topic == "jetson":
            return {
                "data": {
                    "gpu_load": 72.4,
                    "gpu_ram_used": 512 * 1024 * 1024,
                    "gpu_ram_total": 2048 * 1024 * 1024,
                    "power_w": 9.8,
                    "power_mode": "15W",
                }
            }
        if topic == "processes":
            return {
                "data": {
                    "procs": [
                        {"pid": 167320, "name": "uvicorn", "cpu": 37.7, "rss": 323 * 1024 * 1024},
                    ]
                }
            }
        return None

    monkeypatch.setattr("app.api.chat.hub.latest", fake_latest)

    answer = _direct_answer("what is the current GPU process using and power consumption?")
    assert answer is not None
    assert "Per-process GPU attribution is not available" in answer
    assert "GPU load: 72.4%" in answer
    assert "GPU RAM:" in answer
    assert "Power mode: 15W" in answer
    assert "Total power: 9.8W" in answer
    assert not answer.startswith("Top processes by CPU:")
