from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RBI Lending Intelligence Graph RAG"
    app_env: str = "development"
    data_dir: Path = Path("data")
    regulatory_sources_path: Path = Path("config/regulatory_sources.yaml")
    vector_backend: str = "filesystem"
    extraction_provider: str = "deterministic"
    answer_provider: str = "deterministic"
    openai_api_key: str | None = None
    openai_extraction_model: str = "gpt-4o-mini"
    openai_answer_model: str = "gpt-4o-mini"
    openai_input_cost_per_million: float = 0.15
    openai_output_cost_per_million: float = 0.60
    openai_timeout_seconds: float = 45.0
    openai_max_output_tokens: int = 900
    chunk_size: int = 900
    chunk_overlap: int = 150
    vector_top_k: int = 5
    log_level: str = "INFO"
    cors_allowed_origins: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def runtime_dir(self) -> Path:
        return self.data_dir / "runtime"


@lru_cache
def get_settings() -> Settings:
    return Settings()
