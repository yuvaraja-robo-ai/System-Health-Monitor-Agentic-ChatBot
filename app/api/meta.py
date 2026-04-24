from fastapi import APIRouter

from app.host import detect, kernel, power_mode, uptime_seconds
from app.hub import hub
from app import runtime

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta")
def meta() -> dict:
    cap = detect()
    return {
        "host": cap.host,
        "arch": cap.arch,
        "uptime_s": int(uptime_seconds()),
        "kernel": kernel(),
        "power_mode": power_mode(),
        "jetson_model": cap.jetson_model,
        "capabilities": {
            "jtop": cap.has_jtop,
            "journald": cap.has_journald,
            "fan": cap.has_fan,
            "power_mode": cap.has_power_mode,
        },
        "polling": runtime.polling_config(),
        "heartbeats": hub.heartbeats(),
    }
