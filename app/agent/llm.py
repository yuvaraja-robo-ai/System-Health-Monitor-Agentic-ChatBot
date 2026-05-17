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
    provider = _provider()
    if provider == "ollama":
        return await _ollama(prompt, system, response_format=response_format)
    if provider == "llama_cpp":
        return await _llama(prompt, system, response_format=response_format)
    messages: list[Message] = [{"role": "user", "content": prompt}]
    if provider in {"openai", "openai_compatible"}:
        return await _openai_chat(messages, system, response_format=response_format)
    if provider == "anthropic":
        return await _anthropic_chat(messages, system, response_format=response_format)
    if provider == "gemini":
        return await _gemini_chat(messages, system, response_format=response_format)
    return {"text": "(no LLM configured — configure a provider in the dashboard or set SH_OLLAMA_URL / SH_LLAMA_URL)", "backend": "none"}


async def chat(
    messages: list[Message],
    system: str | None = None,
    response_format: str | None = None,
) -> dict[str, Any]:
    """Multi-turn chat with conversation history."""
    provider = _provider()
    if provider == "ollama":
        return await _ollama_chat(messages, system, response_format=response_format)
    if provider == "llama_cpp":
        return await _llama_chat(messages, system, response_format=response_format)
    if provider in {"openai", "openai_compatible"}:
        return await _openai_chat(messages, system, response_format=response_format)
    if provider == "anthropic":
        return await _anthropic_chat(messages, system, response_format=response_format)
    if provider == "gemini":
        return await _gemini_chat(messages, system, response_format=response_format)
    return {"text": "(no LLM configured — configure a provider in the dashboard or set SH_OLLAMA_URL / SH_LLAMA_URL)", "backend": "none"}


def _provider() -> str:
    provider = (settings.llm_provider or "auto").strip()
    if provider == "none":
        return "none"
    if provider == "auto":
        if settings.ollama_url:
            return "ollama"
        if settings.llama_url:
            return "llama_cpp"
        if settings.openai_api_key:
            return "openai"
        if settings.anthropic_api_key:
            return "anthropic"
        if settings.gemini_api_key:
            return "gemini"
        return "none"
    return provider



async def _ollama_chat_with_model(
    model: str,
    messages: list[Message],
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)
    body = {"model": model, "messages": all_messages, "stream": False}
    if response_format == "json":
        body["format"] = "json"
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=body)
        r.raise_for_status()
        j = r.json()
    text = (j.get("message") or {}).get("content") or j.get("response", "")
    return {"text": text, "backend": "ollama", "model": model}


async def _ollama_chat(
    messages: list[Message],
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    try:
        return await _ollama_chat_with_model(settings.llm_model, messages, system, response_format)
    except Exception as e:
        if settings.llm_fallback_model and settings.llm_fallback_model != settings.llm_model:
            log.warning("ollama primary model %r failed (%s) — retrying with fallback %r", settings.llm_model, e, settings.llm_fallback_model)
            return await _ollama_chat_with_model(settings.llm_fallback_model, messages, system, response_format)
        raise


async def _ollama_generate_with_model(
    model: str,
    prompt: str,
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    body = {
        "model": model,
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
    return {"text": j.get("response", ""), "backend": "ollama", "model": model}


async def _ollama(
    prompt: str,
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    try:
        return await _ollama_generate_with_model(settings.llm_model, prompt, system, response_format)
    except Exception as e:
        if settings.llm_fallback_model and settings.llm_fallback_model != settings.llm_model:
            log.warning("ollama primary model %r failed (%s) — retrying with fallback %r", settings.llm_model, e, settings.llm_fallback_model)
            return await _ollama_generate_with_model(settings.llm_fallback_model, prompt, system, response_format)
        raise


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
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.llama_url.rstrip('/')}/v1/chat/completions", json=body)
        r.raise_for_status()
        j = r.json()
    choice = (j.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or choice.get("text", "")
    return {"text": text, "backend": "llama.cpp", "model": j.get("model") or settings.llm_model}


async def _openai_chat(
    messages: list[Message],
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    if not settings.openai_api_key:
        return {"text": "(OpenAI API key is not configured)", "backend": "none"}
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)
    body: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": all_messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
    }
    if response_format == "json":
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.openai_base_url.rstrip('/')}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        j = r.json()
    choice = (j.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or choice.get("text", "")
    return {"text": text, "backend": _provider(), "model": j.get("model") or settings.llm_model}


async def _anthropic_chat(
    messages: list[Message],
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    if not settings.anthropic_api_key:
        return {"text": "(Anthropic API key is not configured)", "backend": "none"}
    clean_messages = []
    for msg in messages:
        role = "assistant" if msg.get("role") == "assistant" else "user"
        clean_messages.append({"role": role, "content": msg.get("content", "")})
    effective_system = system or ""
    if response_format == "json":
        effective_system = (effective_system + "\nReturn valid JSON only. Do not use markdown fences.").strip()
    body: dict[str, Any] = {
        "model": settings.llm_model,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
        "messages": clean_messages,
    }
    if effective_system:
        body["system"] = effective_system
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(f"{settings.anthropic_base_url.rstrip('/')}/v1/messages", headers=headers, json=body)
        r.raise_for_status()
        j = r.json()
    text = "".join(part.get("text", "") for part in (j.get("content") or []) if part.get("type") == "text")
    return {"text": text, "backend": "anthropic", "model": j.get("model") or settings.llm_model}


async def _gemini_chat(
    messages: list[Message],
    system: str | None,
    response_format: str | None = None,
) -> dict[str, Any]:
    if not settings.gemini_api_key:
        return {"text": "(Gemini API key is not configured)", "backend": "none"}
    contents = []
    for msg in messages:
        role = "model" if msg.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
    effective_system = system or ""
    if response_format == "json":
        effective_system = (effective_system + "\nReturn valid JSON only. Do not use markdown fences.").strip()
    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": settings.llm_temperature,
            "maxOutputTokens": settings.llm_max_tokens,
        },
    }
    if effective_system:
        body["system_instruction"] = {"parts": [{"text": effective_system}]}
    headers = {"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"}
    url = f"{settings.gemini_base_url.rstrip('/')}/models/{settings.llm_model}:generateContent"
    async with httpx.AsyncClient(timeout=settings.llm_timeout_s) as c:
        r = await c.post(url, headers=headers, json=body)
        r.raise_for_status()
        j = r.json()
    candidate = (j.get("candidates") or [{}])[0]
    content = candidate.get("content") or {}
    text = "".join(part.get("text", "") for part in (content.get("parts") or []))
    return {"text": text, "backend": "gemini", "model": settings.llm_model}
