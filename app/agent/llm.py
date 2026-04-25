import logging
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)

Message = dict[str, str]  # {"role": "user"|"assistant"|"system", "content": "..."}


async def complete(
    prompt: str,
    system: str | None = None,
    response_format: str | None = None,
) -> dict[str, Any]:
    if settings.ollama_url:
        return await _ollama(prompt, system, response_format=response_format)
    if settings.llama_url:
        return await _llama(prompt, system, response_format=response_format)
    return {"text": "(no LLM configured — set SH_OLLAMA_URL or SH_LLAMA_URL)", "backend": "none"}


async def chat(
    messages: list[Message],
    system: str | None = None,
    response_format: str | None = None,
) -> dict[str, Any]:
    """Multi-turn chat with conversation history."""
    if settings.ollama_url:
        return await _ollama_chat(messages, system, response_format=response_format)
    if settings.llama_url:
        return await _llama_chat(messages, system, response_format=response_format)
    return {"text": "(no LLM configured — set SH_OLLAMA_URL or SH_LLAMA_URL)", "backend": "none"}



async def _ollama_chat(
    messages: list[Message],
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)
    body = {"model": settings.llm_model, "messages": all_messages, "stream": False}
    if response_format == "json":
        body["format"] = "json"
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=body)
        r.raise_for_status()
        j = r.json()
    text = (j.get("message") or {}).get("content") or j.get("response", "")
    return {"text": text, "backend": "ollama", "model": settings.llm_model}


async def _ollama(
    prompt: str,
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    body = {
        "model": settings.llm_model,
        "prompt": prompt,
        "system": system or "",
        "stream": False,
    }
    if response_format == "json":
        body["format"] = "json"
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.ollama_url.rstrip('/')}/api/generate", json=body)
        r.raise_for_status()
        j = r.json()
    return {"text": j.get("response", ""), "backend": "ollama", "model": settings.llm_model}


async def _llama(
    prompt: str,
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    messages: list[Message] = [{"role": "user", "content": prompt}]
    return await _llama_chat(messages, system, response_format=response_format)


async def _llama_chat(
    messages: list[Message],
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    effective_system = (system or "")
    if response_format == "json":
        effective_system = (effective_system + "\nReturn valid JSON only. Do not use markdown fences.").strip()
    all_messages = []
    if effective_system:
        all_messages.append({"role": "system", "content": effective_system})
    all_messages.extend(messages)
    body = {
        "model": settings.llm_model,
        "messages": all_messages,
        "max_tokens": 512,
        "temperature": 0.2,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.llama_url.rstrip('/')}/v1/chat/completions", json=body)
        r.raise_for_status()
        j = r.json()
    choice = (j.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or choice.get("text", "")
    return {"text": text, "backend": "llama.cpp", "model": j.get("model") or settings.llm_model}
