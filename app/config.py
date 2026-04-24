from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SH_", env_file=".env", extra="ignore")

    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    static_dir: Path = Path(__file__).resolve().parent.parent

    system_tick_s: float = 1.0
    process_tick_s: float = 2.0
    app_monitor_tick_s: float = 5.0
    leak_update_s: float = 10.0
    leak_window_s: int = 1800
    leak_min_samples: int = 300
    leak_slope_mb_min: float = 0.2
    leak_min_r2: float = 0.6
    leak_min_span_s: int = 900

    history_raw_retention_s: int = 3600
    history_10s_retention_s: int = 86400
    history_1m_retention_s: int = 2592000

    log_app_dirs: list[str] = []
    monitored_apps: list[str] = []
    log_batch_size: int = 500
    log_max_tail: int = 5000

    llama_url: str | None = None
    ollama_url: str | None = None
    llm_model: str = "llama3.2:3b"
    llm_timeout_s: float = 30.0

    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    kb_dir: Path | None = None

    alert_webhook_url: str | None = None
    alert_cooldown_s: int = 300

    @property
    def metrics_db(self) -> Path:
        return self.data_dir / "metrics.sqlite"

    @property
    def logs_db(self) -> Path:
        return self.data_dir / "logs.duckdb"

    @property
    def kb_path(self) -> Path:
        return self.kb_dir or (self.data_dir / "kb")


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.kb_path.mkdir(parents=True, exist_ok=True)
