import asyncio
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent import diagnose as diag

router = APIRouter(prefix="/api", tags=["diagnose"])

_llm_lock = asyncio.Semaphore(1)
_last_call: float = 0.0
_COOLDOWN_S = 10.0


class Scope(BaseModel):
    window: str = "5m"
    pids: list[int] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)


class DiagnoseRequest(BaseModel):
    scope: Scope = Field(default_factory=Scope)
    question: str | None = None


@router.post("/kb/reload")
async def kb_reload() -> dict[str, Any]:
    from app.agent import kb
    kb.build(force=True)
    return {"ok": True, "entries": len(kb._META)}


class KbSearchRequest(BaseModel):
    query: str
    k: int = 5


@router.post("/kb/search")
async def kb_search(req: KbSearchRequest) -> dict[str, Any]:
    """Semantic search the runbook KB. Used by ai_core MCP tool `search_kb`."""
    from app.agent import kb
    results = kb.query(req.query, k=req.k)
    return {"results": results}


@router.post("/diagnose/context")
async def diagnose_context(req: DiagnoseRequest) -> dict[str, Any]:
    """Return scoped diagnostic context only (no LLM call).
    Used by ai_core MCP tool `diagnose_scope`."""
    ctx = await diag.collect_context_async(req.scope.model_dump())
    return {"context": ctx, "digest_text": diag._digest_text(ctx)}


@router.post("/diagnose")
async def diagnose_endpoint(req: DiagnoseRequest) -> dict[str, Any]:
    global _last_call
    now = time.monotonic()
    wait = _COOLDOWN_S - (now - _last_call)
    if wait > 0:
        raise HTTPException(429, f"rate limited — retry in {wait:.1f}s")
    if not _llm_lock.locked():
        async with _llm_lock:
            _last_call = time.monotonic()
            return await diag.diagnose(req.scope.model_dump(), req.question)
    raise HTTPException(429, "diagnosis already in progress")
