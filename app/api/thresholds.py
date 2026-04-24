"""Alert threshold configuration.

Stores user-defined warn/err thresholds in data/thresholds.json.
Health scorer reads these at runtime via get_thresholds().
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(prefix="/api/config", tags=["config"])

_THRESH_FILE = settings.data_dir / "thresholds.json"
_lock = threading.Lock()

_DEFAULTS: dict[str, Any] = {
    "cpu_warn": 75,
    "cpu_err": 90,
    "mem_warn": 80,
    "mem_err": 92,
    "temp_warn": 75,
    "temp_err": 85,
    "psi_mem_warn": 1.0,
    "psi_mem_err": 10.0,
    "psi_io_warn": 5.0,
    "psi_io_err": 20.0,
    "disk_warn": 85,
    "disk_err": 95,
    "gpu_warn": 80,
    "gpu_err": 95,
    "power_warn": 12,
    "power_err": 18,
}


def get_thresholds() -> dict[str, Any]:
    with _lock:
        if not _THRESH_FILE.exists():
            return dict(_DEFAULTS)
        try:
            data = json.loads(_THRESH_FILE.read_text())
            return {**_DEFAULTS, **data}
        except Exception:
            return dict(_DEFAULTS)


def _save(data: dict[str, Any]) -> None:
    with _lock:
        _THRESH_FILE.write_text(json.dumps(data, indent=2))


class Thresholds(BaseModel):
    cpu_warn: float = Field(75, ge=0, le=100)
    cpu_err: float = Field(90, ge=0, le=100)
    mem_warn: float = Field(80, ge=0, le=100)
    mem_err: float = Field(92, ge=0, le=100)
    temp_warn: float = Field(75, ge=0, le=200)
    temp_err: float = Field(85, ge=0, le=200)
    psi_mem_warn: float = Field(1.0, ge=0, le=100)
    psi_mem_err: float = Field(10.0, ge=0, le=100)
    psi_io_warn: float = Field(5.0, ge=0, le=100)
    psi_io_err: float = Field(20.0, ge=0, le=100)
    disk_warn: float = Field(85, ge=0, le=100)
    disk_err: float = Field(95, ge=0, le=100)
    gpu_warn: float = Field(80, ge=0, le=100)
    gpu_err: float = Field(95, ge=0, le=100)
    power_warn: float = Field(12, ge=0, le=100)
    power_err: float = Field(18, ge=0, le=100)


@router.get("/thresholds")
def get_thresh() -> dict:
    return get_thresholds()


@router.post("/thresholds")
def set_thresh(body: Thresholds) -> dict:
    data = body.model_dump()
    _save(data)
    return data


@router.post("/thresholds/reset")
def reset_thresh() -> dict:
    if _THRESH_FILE.exists():
        _THRESH_FILE.unlink()
    return dict(_DEFAULTS)


@router.get("/thresholds/suggest")
def suggest_thresh() -> dict:
    """Auto-tune: suggest tighter thresholds based on anomaly history.

    For each metric in anomaly history, computes p95 of observed values
    and suggests warn = p75, err = p95 if tighter than current defaults.
    """
    from app.analytics.anomaly import detector as anomaly_detector
    import statistics

    history = anomaly_detector.history(limit=500)
    if not history:
        return {"suggestions": [], "note": "no anomaly history yet — run longer to collect data"}

    metric_vals: dict[str, list[float]] = {}
    for entry in history:
        m = entry.get("metric")
        v = entry.get("value")
        if m and v is not None:
            metric_vals.setdefault(m, []).append(float(v))

    current = get_thresholds()
    suggestions = []
    metric_to_thresh = {
        "cpu.total": ("cpu_warn", "cpu_err"),
        "mem.used": None,  # absolute bytes, skip
        "gpu.load": ("gpu_warn", "gpu_err"),
    }

    for metric, vals in metric_vals.items():
        if len(vals) < 5:
            continue
        vals_sorted = sorted(vals)
        p75 = vals_sorted[int(len(vals_sorted) * 0.75)]
        p95 = vals_sorted[int(len(vals_sorted) * 0.95)]
        keys = metric_to_thresh.get(metric)
        if keys:
            warn_key, err_key = keys
            cur_warn = current.get(warn_key, 100)
            cur_err = current.get(err_key, 100)
            if p75 < cur_warn or p95 < cur_err:
                suggestions.append({
                    "metric": metric,
                    "warn_key": warn_key,
                    "err_key": err_key,
                    "suggested_warn": round(p75, 1),
                    "suggested_err": round(p95, 1),
                    "current_warn": cur_warn,
                    "current_err": cur_err,
                    "samples": len(vals),
                })
        else:
            suggestions.append({
                "metric": metric,
                "note": "absolute metric — review manually",
                "p75": round(p75, 2),
                "p95": round(p95, 2),
                "samples": len(vals),
            })

    return {"suggestions": suggestions, "based_on_samples": sum(len(v) for v in metric_vals.values())}
