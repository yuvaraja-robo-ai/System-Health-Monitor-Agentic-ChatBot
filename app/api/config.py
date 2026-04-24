from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import runtime

router = APIRouter(prefix="/api/config", tags=["config"])


class PollingConfig(BaseModel):
    system_s: float = Field(..., ge=0.2, le=60.0)
    process_s: float = Field(..., ge=0.2, le=60.0)
    app_monitor_s: float = Field(..., ge=0.2, le=300.0)


class AppName(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


@router.get("/polling")
def get_polling() -> dict:
    return {"polling": runtime.polling_config()}


@router.post("/polling")
def update_polling(cfg: PollingConfig) -> dict:
    return runtime.apply_polling_config(
        system_s=cfg.system_s,
        process_s=cfg.process_s,
        app_monitor_s=cfg.app_monitor_s,
    )


@router.get("/apps")
def get_apps() -> dict:
    pinned = runtime.load_pinned_apps()
    return {"pinned": pinned}


@router.post("/apps")
def add_app(body: AppName) -> dict:
    pinned = runtime.add_pinned_app(body.name)
    return {"pinned": pinned}


@router.delete("/apps/{name}")
def remove_app(name: str) -> dict:
    pinned = runtime.remove_pinned_app(name)
    return {"pinned": pinned}
