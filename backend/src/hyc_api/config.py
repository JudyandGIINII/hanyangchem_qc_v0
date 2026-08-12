from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; dependency probing is opt-in outside Compose."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_name: str = "hyc-inspection-api"
    database_url: str = "postgresql+psycopg://local_user:local-placeholder-only@postgres:5432/hyc"
    redis_url: str = "redis://redis:6379/0"
    check_database_on_ready: bool = True
    check_redis_on_ready: bool = True
    ncr_report_module_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HYC_NCR_REPORT_MODULE_ENABLED", "NCR_REPORT_MODULE_ENABLED"),
    )
    ncr_approver_module_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "HYC_NCR_APPROVER_MODULE_ENABLED", "NCR_APPROVER_MODULE_ENABLED"
        ),
    )
    ncr_retest_module_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HYC_NCR_RETEST_MODULE_ENABLED", "NCR_RETEST_MODULE_ENABLED"),
    )
    ncr_attachment_module_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "HYC_NCR_ATTACHMENT_MODULE_ENABLED", "NCR_ATTACHMENT_MODULE_ENABLED"
        ),
    )
    ncr_completion_date_module_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "HYC_NCR_COMPLETION_DATE_MODULE_ENABLED", "NCR_COMPLETION_DATE_MODULE_ENABLED"
        ),
    )
    request_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    p3_fixture_mode: bool = False
    p3_storage_root: str = "/tmp/hyc-p3-documents"
    p6_report_storage_root: str = "./.local-report-artifacts"
    p3_fault_injection_enabled: bool = False
    local_ocr_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HYC_LOCAL_OCR_ENABLED", "LOCAL_OCR_ENABLED"),
    )
    local_ocr_manifest_path: str = Field(
        default="backend/local_ocr/model-manifest.v1.json",
        validation_alias=AliasChoices(
            "HYC_LOCAL_OCR_MANIFEST_PATH", "LOCAL_OCR_MANIFEST_PATH"
        ),
    )
    local_ocr_models_root: str = Field(
        default=".local-ocr-models/models",
        validation_alias=AliasChoices("HYC_LOCAL_OCR_MODELS_ROOT", "LOCAL_OCR_MODELS_ROOT"),
    )
    ingest_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HYC_INGEST_ENABLED", "INGEST_ENABLED"),
    )
    traceability_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HYC_TRACEABILITY_ENABLED", "TRACEABILITY_ENABLED"),
    )
