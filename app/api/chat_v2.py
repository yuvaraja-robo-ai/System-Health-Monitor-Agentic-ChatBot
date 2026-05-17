"""Chat endpoint backed by ai_core (native tool-use + generative UI).

Replaces prompted-JSON pattern in `app/api/chat.py` with native tool-use via
llm_gatewayV2, parallel dispatch, structured Verdict, and a generative UI
composer that emits prefab cards (metric_tile, sparkline, table, alert, ...).

Routes:
  POST /api/chat_v2          one-shot: returns trace + verdict + ui cards
  WS   /api/chat_v2/stream   streams step-by-step log, then ui + verdict
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ai_core import render_ui
from app.agent.aicore_chat import answer
from app.config import settings

router = APIRouter()


def _s(attr: str) -> str:
    return getattr(settings, attr)


def _resolve_model(provider: str, model: str | None, settings_attr: str) -> str | None:
    """Pick a model name for the given provider.

    - Explicit model from the request always wins.
    - For Ollama, fall back to the configured settings default (e.g. qwen3:1.7b).
    - For "auto" and every other provider, return None so the gateway uses its
      own per-provider default — avoids leaking Ollama model names to Groq/Gemini/etc.
    """
    if model:
        return model
    if provider == "ollama":
        return getattr(settings, settings_attr)
    return None


class ChatV2Request(BaseModel):
    message: str = Field(min_length=1)
    executor_provider: str = Field(default_factory=lambda: settings.executor_provider)
    verifier_provider: str = Field(default_factory=lambda: settings.verifier_provider)
    ui_provider: str = Field(default_factory=lambda: settings.ui_provider)
    # Models are Optional — only forwarded when explicitly set. Empty string
    # / None lets the gateway pick its own default per provider, which is what
    # we want for "auto" routing and for non-Ollama providers.
    executor_model: str | None = None
    verifier_model: str | None = None
    ui_model: str | None = None
    max_turns: int = 12
    routing_policy: str | None = None  # auto | fast | quality | cheap | balanced


@router.post("/api/chat_v2")
async def chat_v2(req: ChatV2Request):
    """One-shot: run agent → verify → compose UI cards."""
    from fastapi import HTTPException
    logs: list[str] = []
    exec_model = _resolve_model(req.executor_provider, req.executor_model, "executor_model")
    ver_model = _resolve_model(req.verifier_provider, req.verifier_model, "verifier_model")
    ui_model = _resolve_model(req.ui_provider, req.ui_model, "ui_model")
    try:
        trace, verdict = await answer(
            req.message,
            executor_provider=req.executor_provider,
            verifier_provider=req.verifier_provider,
            executor_model=exec_model,
            verifier_model=ver_model,
            max_turns=req.max_turns,
            routing_policy=req.routing_policy,
            log=logs.append,
        )
    except Exception as eg:
        cause = eg.exceptions[0] if hasattr(eg, "exceptions") else eg
        raise HTTPException(500, detail=f"{type(cause).__name__}: {cause}") from cause
    _fast_ui = req.ui_provider in ("ollama", "auto", "")
    ui = await render_ui(trace, verdict, provider=req.ui_provider, model=ui_model, fast=_fast_ui)
    return {
        "trace": trace.model_dump(),
        "verdict": verdict.model_dump(),
        "ui": ui.model_dump(),
        "log_lines": logs,
    }


@router.websocket("/api/chat_v2/stream")
async def chat_v2_stream(ws: WebSocket):
    """Stream each step live, then send verdict + generated UI cards."""
    await ws.accept()
    _log_tasks: list[asyncio.Task] = []

    async def _drain_log_tasks() -> None:
        """Wait for all pending log-send tasks to finish, ignoring errors."""
        if _log_tasks:
            await asyncio.gather(*_log_tasks, return_exceptions=True)
            _log_tasks.clear()

    try:
        req = await ws.receive_json()
        question = req.get("message", "").strip()
        if not question:
            await ws.send_json({"type": "error", "message": "empty question"})
            await ws.close()
            return

        def emit(line: str):
            truncated = line[:500] + " …[truncated]" if len(line) > 500 else line
            async def _send():
                try:
                    await ws.send_json({"type": "log", "text": truncated})
                except Exception:
                    pass
                except asyncio.CancelledError:
                    pass  # task cancelled when ASGI scope ends — exit cleanly
            _log_tasks.append(asyncio.create_task(_send()))

        exec_prov = req.get("executor_provider") or settings.executor_provider
        ver_prov = req.get("verifier_provider") or settings.verifier_provider
        ui_prov = req.get("ui_provider") or settings.ui_provider
        exec_model = _resolve_model(exec_prov, req.get("executor_model"), "executor_model")
        ver_model = _resolve_model(ver_prov, req.get("verifier_model"), "verifier_model")
        ui_model = _resolve_model(ui_prov, req.get("ui_model"), "ui_model")

        trace, verdict = await answer(
            question,
            executor_provider=exec_prov,
            verifier_provider=ver_prov,
            executor_model=exec_model,
            verifier_model=ver_model,
            max_turns=req.get("max_turns", 12),
            routing_policy=req.get("routing_policy"),
            log=emit,
        )

        # Drain all pending log sends before sending terminal messages so they
        # arrive in-order and none leak past ws.close().
        await _drain_log_tasks()

        await ws.send_json({"type": "log",    "text": "[PHASE:COMPOSE] Building prefab UI cards…"})
        await ws.send_json({"type": "status", "text": "Composing UI cards…"})
        # fast=True skips the LLM call and builds cards from structured trace data.
        # Saves 10-30 s on local Ollama. Set False only for cloud providers.
        _fast_ui = ui_prov in ("ollama", "auto", "")
        ui = await render_ui(trace, verdict, provider=ui_prov, model=ui_model, fast=_fast_ui)

        await ws.send_json({
            "type": "done",
            "trace": trace.model_dump(),
            "verdict": verdict.model_dump(),
            "ui": ui.model_dump(),
        })
    except WebSocketDisconnect:
        return
    except Exception as e:
        # anyio wraps exceptions from stdio_client as nested ExceptionGroups — unwrap fully
        cause = e
        while hasattr(cause, "exceptions") and cause.exceptions:
            cause = cause.exceptions[0]
        try:
            await ws.send_json({"type": "error", "message": f"{type(cause).__name__}: {cause}"})
        except Exception:
            pass
    finally:
        # Cancel and drain any tasks still pending (error path).
        for t in _log_tasks:
            t.cancel()
        await asyncio.gather(*_log_tasks, return_exceptions=True)
        try:
            await ws.close()
        except Exception:
            pass
