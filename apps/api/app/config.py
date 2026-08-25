"""Environment-driven configuration. No secrets committed to Git -- see `.env.example`."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://ankur:ankur@localhost:5432/ankur"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Repo-relative (or absolute) paths to the DACP corpus. Defaults match the
    # repo layout for local/dev runs. In the container image these are no
    # longer baked in -- see apps/api/Dockerfile -- so point them at a
    # mounted volume (e.g. `/app/data/raw`, `/app/data/processed`) when
    # running there.
    ankur_raw_root: str = "data/raw"
    ankur_corpus_root: str = "data/processed"

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
