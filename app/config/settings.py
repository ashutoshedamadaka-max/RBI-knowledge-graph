from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RBI Lending Intelligence Graph RAG"
    app_env: str = "development"
    data_dir: Path = Path("data")
    vector_backend: str = "filesystem"
    chunk_size: int = 900
    chunk_overlap: int = 150
    vector_top_k: int = 5
    log_level: str = "INFO"

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

