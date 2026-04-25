import asyncio
import sys
from pathlib import Path

import numpy as np


def test_kb_build_and_query(tmp_path, monkeypatch):
    from app.agent import kb
    from app.config import settings

    kb_dir = tmp_path / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "high_cpu.md").write_text(
        """---
title: \"High CPU Usage\"
tags: cpu, performance
severity: warn
---

# High CPU Usage

## Steps
1. Check top processes
2. Check thermal throttling
"""
    )

    monkeypatch.setattr(settings, "kb_dir", kb_dir)
    monkeypatch.setattr("app.agent.kb.embed.available", lambda: True)

    def fake_embed(texts):
        return np.array([[1.0, 0.0] for _ in list(texts)], dtype=np.float32)

    monkeypatch.setattr("app.agent.kb.embed.embed", fake_embed)

    class FakeIndex:
        def __init__(self, dim):
            self.dim = dim
            self.rows = []

        def add(self, vecs):
            self.rows = vecs

        def search(self, vecs, k):
            return np.array([[0.99]], dtype=np.float32), np.array([[0]], dtype=np.int64)

    class FakeFaiss:
        IndexFlatIP = FakeIndex

        @staticmethod
        def write_index(idx, path):
            Path(path).write_text("fake-index")

    monkeypatch.setitem(sys.modules, "faiss", FakeFaiss)

    kb.build(force=True)
    out = kb.query("cpu usage high", k=3)
    assert out
    assert out[0]["title"] == "High CPU Usage"
    assert out[0]["steps"] == ["Check top processes", "Check thermal throttling"]



def test_chat_uses_kb_when_no_direct_and_no_llm(monkeypatch):
    from app.api.chat import ChatMessage, ChatRequest, chat_endpoint

    monkeypatch.setattr("app.api.chat._direct_answer", lambda question: None)
    monkeypatch.setattr("app.api.chat._llm_configured", lambda: False)
    async def fake_collect_context_async(scope):
        return {
            "window_s": 300,
            "health": {"score": 88},
            "system": {},
            "leaks": [],
            "crashes": {"counts": {}, "recent_n": 0},
            "log_clusters": [],
            "top_procs": [],
            "scope": {},
        }

    monkeypatch.setattr("app.api.chat.collect_context_async", fake_collect_context_async)
    monkeypatch.setattr("app.api.chat._digest_text", lambda ctx: "digest")
    monkeypatch.setattr("app.api.chat._kb_answer", lambda q, d: "KB: High CPU Usage\nSteps:\n  1. Check top")

    body = ChatRequest(messages=[ChatMessage(role="user", content="how to fix cpu spike")])
    out = asyncio.run(chat_endpoint(body))
    assert out["backend"] == "kb"
    assert out["answer"].startswith("KB: High CPU Usage")



def test_chat_returns_none_with_digest_when_no_direct_no_kb_no_llm(monkeypatch):
    from app.api.chat import ChatMessage, ChatRequest, chat_endpoint

    monkeypatch.setattr("app.api.chat._direct_answer", lambda question: None)
    monkeypatch.setattr("app.api.chat._llm_configured", lambda: False)
    async def fake_collect_context_async(scope):
        return {
            "window_s": 300,
            "health": {"score": 70},
            "system": {},
            "leaks": [],
            "crashes": {"counts": {}, "recent_n": 0},
            "log_clusters": [],
            "top_procs": [],
            "scope": {},
        }

    monkeypatch.setattr("app.api.chat.collect_context_async", fake_collect_context_async)
    monkeypatch.setattr("app.api.chat._digest_text", lambda ctx: "live digest text")
    monkeypatch.setattr("app.api.chat._kb_answer", lambda q, d: None)

    body = ChatRequest(messages=[ChatMessage(role="user", content="why is this happening")])
    out = asyncio.run(chat_endpoint(body))
    assert out["backend"] == "none"
    assert "Live system snapshot" in out["answer"]
    assert "live digest text" in out["answer"]
