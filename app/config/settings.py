from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_name: str = "RBI Lending Intelligence Graph RAG"
    app_env: str = "development"
    data_dir: Path = Path("data")
    database_url: str | None = Field(default=None, repr=False)
    postgres_schema: str = "public"
    admin_api_key: str | None = Field(default=None, repr=False)
    monitor_secret: str | None = Field(default=None, repr=False)
    regulatory_sources_path: Path = Path("config/regulatory_sources.yaml")
    vector_backend: str = "filesystem"
    extraction_provider: str = "deterministic"
    answer_provider: str = "deterministic"
    openai_api_key: str | None = Field(default=None, repr=False)
    cohere_api_key: str | None = Field(default=None, repr=False)  # ADR-026
    openai_extraction_model: str = "gpt-4o-mini"
    openai_answer_model: str = "gpt-4o-mini"
    openai_input_cost_per_million: float = 0.15
    openai_output_cost_per_million: float = 0.60
    cohere_cost_per_thousand_searches: float = 2.0  # configured estimate; not invoice pricing
    openai_timeout_seconds: float = 45.0
    openai_max_output_tokens: int = 900
    chunk_size: int = 900
    # structure (default since the Phase 2 gate, ADR-023), fixed, recursive, or legacy (word windows, chunk_size/chunk_overlap).
    chunker: str = "structure"
    chunk_overlap: int = 150
    vector_top_k: int = 5
    rerank_candidates: int = 30
    abstain_below: float = 0.34  # Cohere top relevance score; tuned on dev (ADR-026)
    log_level: str = "INFO"
    # Switch off to send every successor to review (the replay report decides whether it stays on).
    auto_trust_enabled: bool = True
    cors_allowed_origins: str = ""

    @field_validator("openai_api_key", "cohere_api_key", mode="before")
    @classmethod
    def normalize_provider_key(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if any(char.isspace() for char in value):
                raise ValueError("Provider API keys must be a single token without whitespace.")
            return value or None
        return value

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
