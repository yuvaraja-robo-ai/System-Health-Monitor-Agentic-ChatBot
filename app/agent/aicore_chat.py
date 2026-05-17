"""SystemHealth chat backed by ai_core (replaces app/agent/diagnose.py prompted-JSON pattern).

Loads the qualified system prompt + spawns mcp_server.py via stdio + runs the
generic agent loop from ai_core. Provides both:
  - `answer(question) -> (AgentTrace, Verdict)` — programmatic API
  - `__main__` CLI: `python -m app.agent.aicore_chat "why is cpu high?"`

Used by app/api/chat_v2.py to serve `/api/chat_v2`.
"""

from __future__ import annotations

import asyncio
import sys
import logging
from pathlib import Path
from typing import Optional

from ai_core import AgentTrace, Verdict, run_agent
from app.config import settings

_log = logging.getLogger("systemhealth.agent")


def _make_logger(user_log=None):
    """Returns a log fn that writes to both stderr (always) and user_log (if provided)."""
    def _inner(msg: str):
        _log.info(msg)
        print(msg, file=sys.stderr, flush=True)
        if user_log is not None:
            try:
                user_log(msg)
            except Exception:
                pass
    return _inner


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent  # SystemHealth root (where pyproject.toml lives)
HEALTH_PROMPT = (ROOT / "health_prompt.md").read_text()
MCP_SERVER_PATH = str(ROOT / "mcp_server.py")

# Maps each MCP tool → CoT reasoning category (matches tags in health_prompt.md)
HEALTH_TOOL_REASONING_TAGS: dict[str, str] = {
    "get_system_metrics": "metric_lookup",
    "get_metric_history": "metric_lookup",
    "get_top_processes": "leak_check",
    "get_process_history": "leak_check",
    "query_logs": "log_search",
    "get_log_clusters": "log_search",
    "get_briefing": "correlation",
    "diagnose_scope": "correlation",
    "search_kb": "kb_lookup",
    "get_thresholds": "verify",
}

HEALTH_VERIFIER_SYSTEM = (
    "You are an expert SRE/sysadmin verifier. Assess whether the agent's diagnosis "
    "is supported by the evidence it collected: do the cited metric values, log "
    "patterns, and process states actually support the stated finding? "
    "Flag any leaps in reasoning.\n"
    "Return ONLY a single flat JSON object with EXACTLY these four fields:\n"
    '{"passed": true|false, "reason": "one sentence", "final_answer": "brief answer", "confidence": 0.0-1.0}\n'
    "No wrapper keys. No markdown fences. No extra fields."
)


async def answer(
    question: str,
    *,
    executor_provider: Optional[str] = None,
    verifier_provider: Optional[str] = None,
    executor_model: Optional[str] = None,
    verifier_model: Optional[str] = None,
    executor_reasoning: str = "off",
    verifier_reasoning: str = "off",
    max_turns: int = 12,
    routing_policy: Optional[str] = None,
    gateway_url: Optional[str] = None,
    log=print,
) -> tuple[AgentTrace, Verdict]:
    """Answer a sysadmin question by running the ai_core agent against MCP tools.

    Returns (AgentTrace, Verdict).
    """
    _ep = executor_provider or settings.executor_provider
    _em = executor_model or settings.executor_model
    _vp = verifier_provider or settings.verifier_provider
    _vm = verifier_model or settings.verifier_model
    _logger = _make_logger(log if log is not print else None)
    _logger(f"[aicore_chat] answer() called: question={question!r:.80}")
    _logger(f"[aicore_chat] executor={_ep}/{_em}  verifier={_vp}/{_vm}  gateway={gateway_url or 'default'}")
    _logger(f"[aicore_chat] MCP server: {MCP_SERVER_PATH}")
    _logger(f"[aicore_chat] project root: {PROJECT_ROOT}")
    return await run_agent(
        problem=question,
        mcp_server_path=MCP_SERVER_PATH,
        system_prompt=HEALTH_PROMPT,
        executor_provider=_ep,
        verifier_provider=_vp,
        verifier_system=HEALTH_VERIFIER_SYSTEM,
        executor_reasoning=executor_reasoning,
        verifier_reasoning=verifier_reasoning,
        executor_model=_em,
        verifier_model=_vm,
        max_turns=max_turns,
        routing_policy=routing_policy,
        gateway_url=gateway_url,
        tool_reasoning_tags=HEALTH_TOOL_REASONING_TAGS,
        mcp_command="uv",
        mcp_args_extra=["run", "--project", str(PROJECT_ROOT), "python", MCP_SERVER_PATH],
        log=_logger,
    )


async def _cli():
    question = " ".join(sys.argv[1:]) or "What is the current health of this host?"
    trace, verdict = await answer(question)

    print("\n" + "=" * 60)
    print("TRACE SUMMARY")
    print("=" * 60)
    print(f"Turns: {trace.total_turns} | Tool calls: {len(trace.steps)} | Provider: {trace.provider}")

    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    print(verdict.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(_cli())
