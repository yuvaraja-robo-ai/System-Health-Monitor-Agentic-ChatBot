import json
import threading
from typing import Any

from app.collectors.base import Collector
from app.config import settings

_COLLECTORS: dict[str, Collector] = {}
_APPS_LOCK = threading.Lock()


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
