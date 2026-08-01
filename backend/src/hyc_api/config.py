from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; dependency probing is opt-in outside Compose."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "hyc-inspection-api"
    database_url: str = "postgresql+psycopg://local_user:local-placeholder-only@postgres:5432/hyc"
    redis_url: str = "redis://redis:6379/0"
    check_database_on_ready: bool = True
    check_redis_on_ready: bool = True
    ncr_feature_enabled: bool = False
    request_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    p3_fixture_mode: bool = False
    p3_storage_root: str = "/tmp/hyc-p3-documents"
    p3_fault_injection_enabled: bool = False
