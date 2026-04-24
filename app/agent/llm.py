import logging
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

Message = dict[str, str]  # {"role": "user"|"assistant"|"system", "content": "..."}


async def complete(prompt: str, system: str | None = None) -> dict[str, Any]:
    if settings.ollama_url:
        return await _ollama(prompt, system)
    if settings.llama_url:
        return await _llama(prompt, system)
    return {"text": "(no LLM configured — set SH_OLLAMA_URL or SH_LLAMA_URL)", "backend": "none"}


async def chat(messages: list[Message], system: str | None = None) -> dict[str, Any]:
    """Multi-turn chat with conversation history."""
    if settings.ollama_url:
        return await _ollama_chat(messages, system)
    if settings.llama_url:
        # llama.cpp: flatten messages into a single prompt
        prompt = _flatten_messages(messages)
        return await _llama(prompt, system)
    return {"text": "(no LLM configured — set SH_OLLAMA_URL or SH_LLAMA_URL)", "backend": "none"}


def _flatten_messages(messages: list[Message]) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    parts.append("Assistant:")
    return "\n".join(parts)


async def _ollama_chat(messages: list[Message], system: str | None) -> dict[str, Any]:
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)
    body = {"model": settings.llm_model, "messages": all_messages, "stream": False}
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=body)
        r.raise_for_status()
        j = r.json()
    text = (j.get("message") or {}).get("content") or j.get("response", "")
    return {"text": text, "backend": "ollama", "model": settings.llm_model}


async def _ollama(prompt: str, system: str | None) -> dict[str, Any]:
    body = {
        "model": settings.llm_model,
        "prompt": prompt,
        "system": system or "",
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.ollama_url.rstrip('/')}/api/generate", json=body)
        r.raise_for_status()
        j = r.json()
    return {"text": j.get("response", ""), "backend": "ollama", "model": settings.llm_model}


async def _llama(prompt: str, system: str | None) -> dict[str, Any]:
    body = {
        "prompt": (f"<<SYS>>\n{system}\n<</SYS>>\n\n" if system else "") + prompt,
        "n_predict": 512,
        "temperature": 0.2,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.llama_url.rstrip('/')}/completion", json=body)
        r.raise_for_status()
        j = r.json()
    return {"text": j.get("content", ""), "backend": "llama.cpp"}
