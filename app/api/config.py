from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import runtime
from app.config import settings

router = APIRouter(prefix="/api/config", tags=["config"])


class PollingConfig(BaseModel):
    system_s: float = Field(..., ge=0.2, le=60.0)
    process_s: float = Field(..., ge=0.2, le=60.0)
    app_monitor_s: float = Field(..., ge=0.2, le=300.0)


class AppName(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class LLMConfig(BaseModel):
    provider: str = Field(..., pattern="^(auto|none|ollama|llama_cpp|openai|openai_compatible|anthropic|gemini)$")
    model: str = Field(..., min_length=1, max_length=160)
    timeout_s: float = Field(30.0, ge=1.0, le=300.0)
    max_tokens: int = Field(512, ge=64, le=8192)
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    ollama_url: str | None = Field(None, max_length=300)
    llama_url: str | None = Field(None, max_length=300)
    openai_base_url: str | None = Field(None, max_length=300)
    anthropic_base_url: str | None = Field(None, max_length=300)
    gemini_base_url: str | None = Field(None, max_length=300)
    api_key: str | None = Field(None, max_length=300)
    clear_api_key: bool = False


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


@router.get("/llm")
def get_llm_config() -> dict:
    return runtime.llm_config()


@router.post("/llm")
def update_llm_config(cfg: LLMConfig) -> dict:
    try:
        return runtime.apply_llm_config(cfg.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/agent")
def get_agent_config() -> dict:
    """Return agent executor/verifier/ui model config loaded from env."""
    return {
        "executor_provider": settings.executor_provider,
        "executor_model": settings.executor_model,
        "verifier_provider": settings.verifier_provider,
        "verifier_model": settings.verifier_model,
        "ui_provider": settings.ui_provider,
        "ui_model": settings.ui_model,
        "ollama_url": settings.ollama_url,
    }
