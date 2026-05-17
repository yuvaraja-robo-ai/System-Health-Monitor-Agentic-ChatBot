import json
import threading
from typing import Any

from app.collectors.base import Collector
from app.config import settings

_COLLECTORS: dict[str, Collector] = {}
_APPS_LOCK = threading.Lock()
_LLM_LOCK = threading.Lock()


def register_collectors(collectors: list[Collector]) -> None:
    global _COLLECTORS
    _COLLECTORS = {c.name: c for c in collectors}


def clear_collectors() -> None:
    _COLLECTORS.clear()


def polling_config() -> dict[str, float]:
    return {
        "system_s": float(settings.system_tick_s),
        "process_s": float(settings.process_tick_s),
        "app_monitor_s": float(settings.app_monitor_tick_s),
    }


def apply_polling_config(system_s: float, process_s: float, app_monitor_s: float) -> dict[str, Any]:
    settings.system_tick_s = float(system_s)
    settings.process_tick_s = float(process_s)
    settings.app_monitor_tick_s = float(app_monitor_s)

    if "psutil" in _COLLECTORS:
        _COLLECTORS["psutil"].interval_s = float(system_s)
    if "processes" in _COLLECTORS:
        _COLLECTORS["processes"].interval_s = float(process_s)
    if "app-monitor" in _COLLECTORS:
        _COLLECTORS["app-monitor"].interval_s = float(app_monitor_s)

    return {
        "polling": polling_config(),
        "active_collectors": sorted(_COLLECTORS.keys()),
    }


def _llm_path():
    return settings.data_dir / "llm_config.json"


def _mask(value: str | None) -> bool:
    return bool(value)


def llm_config(redact: bool = True) -> dict[str, Any]:
    data = {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "timeout_s": settings.llm_timeout_s,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
        "ollama_url": settings.ollama_url or "",
        "llama_url": settings.llama_url or "",
        "openai_base_url": settings.openai_base_url,
        "anthropic_base_url": settings.anthropic_base_url,
        "gemini_base_url": settings.gemini_base_url,
        "has_openai_api_key": _mask(settings.openai_api_key),
        "has_anthropic_api_key": _mask(settings.anthropic_api_key),
        "has_gemini_api_key": _mask(settings.gemini_api_key),
    }
    if not redact:
        data.update(
            {
                "openai_api_key": settings.openai_api_key or "",
                "anthropic_api_key": settings.anthropic_api_key or "",
                "gemini_api_key": settings.gemini_api_key or "",
            }
        )
    return data


def _sync_llm_settings(data: dict[str, Any]) -> None:
    for key in (
        "llm_provider",
        "llm_model",
        "llm_timeout_s",
        "llm_max_tokens",
        "llm_temperature",
        "ollama_url",
        "llama_url",
        "openai_base_url",
        "anthropic_base_url",
        "gemini_base_url",
        "openai_api_key",
        "anthropic_api_key",
        "gemini_api_key",
    ):
        if key in data:
            value = data[key]
            if key.endswith("_api_key") and not value:
                value = None
            setattr(settings, key, value)


def init_llm_config() -> None:
    p = _llm_path()
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text())
        if isinstance(data, dict):
            _sync_llm_settings(data)
    except Exception:
        return


def apply_llm_config(data: dict[str, Any]) -> dict[str, Any]:
    provider = str(data.get("provider") or settings.llm_provider or "auto")
    allowed = {"auto", "none", "ollama", "llama_cpp", "openai", "openai_compatible", "anthropic", "gemini"}
    if provider not in allowed:
        raise ValueError(f"unsupported provider: {provider}")

    current = llm_config(redact=False)
    persisted = {
        "llm_provider": provider,
        "llm_model": str(data.get("model") or current.get("model") or "llama3.2:3b"),
        "llm_timeout_s": float(data.get("timeout_s") or current.get("timeout_s") or 30.0),
        "llm_max_tokens": int(data.get("max_tokens") or current.get("max_tokens") or 512),
        "llm_temperature": float(data.get("temperature") if data.get("temperature") is not None else current.get("temperature") or 0.2),
        "ollama_url": str(data.get("ollama_url") or current.get("ollama_url") or "") or None,
        "llama_url": str(data.get("llama_url") or current.get("llama_url") or "") or None,
        "openai_base_url": str(data.get("openai_base_url") or current.get("openai_base_url") or "https://api.openai.com/v1"),
        "anthropic_base_url": str(data.get("anthropic_base_url") or current.get("anthropic_base_url") or "https://api.anthropic.com"),
        "gemini_base_url": str(data.get("gemini_base_url") or current.get("gemini_base_url") or "https://generativelanguage.googleapis.com/v1beta"),
        "openai_api_key": current.get("openai_api_key") or None,
        "anthropic_api_key": current.get("anthropic_api_key") or None,
        "gemini_api_key": current.get("gemini_api_key") or None,
    }

    api_key = str(data.get("api_key") or "")
    clear_key = bool(data.get("clear_api_key"))
    if provider in {"openai", "openai_compatible"}:
        if clear_key:
            persisted["openai_api_key"] = None
        elif api_key:
            persisted["openai_api_key"] = api_key
    elif provider == "anthropic":
        if clear_key:
            persisted["anthropic_api_key"] = None
        elif api_key:
            persisted["anthropic_api_key"] = api_key
    elif provider == "gemini":
        if clear_key:
            persisted["gemini_api_key"] = None
        elif api_key:
            persisted["gemini_api_key"] = api_key

    with _LLM_LOCK:
        _sync_llm_settings(persisted)
        _llm_path().write_text(json.dumps(persisted, indent=2))
    return llm_config()


def _pinned_path():
    return settings.data_dir / "pinned_apps.json"


def load_pinned_apps() -> list[str]:
    p = _pinned_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _sync_settings(apps: list[str]) -> None:
    merged = list(dict.fromkeys(list(settings.monitored_apps) + apps))
    settings.monitored_apps = merged


def init_pinned_apps() -> None:
    _sync_settings(load_pinned_apps())


def add_pinned_app(name: str) -> list[str]:
    with _APPS_LOCK:
        pinned = load_pinned_apps()
        norm = name.strip()
        if norm and norm not in pinned:
            pinned.append(norm)
            _pinned_path().write_text(json.dumps(pinned))
        _sync_settings(pinned)
        return pinned


def remove_pinned_app(name: str) -> list[str]:
    with _APPS_LOCK:
        pinned = [p for p in load_pinned_apps() if p.lower() != name.lower()]
        _pinned_path().write_text(json.dumps(pinned))
        settings.monitored_apps = [a for a in settings.monitored_apps if a.lower() != name.lower()]
        return pinned
