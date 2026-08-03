from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from hyc_api.config import Settings
from hyc_local_ocr.errors import LocalOcrError
from hyc_worker.main import create_worker_app


def _settings() -> Settings:
    return Settings(
        app_name="local-ocr-readiness-test",
        check_redis_on_ready=False,
        local_ocr_enabled=True,
        local_ocr_manifest_path="opaque-manifest-ref",
        local_ocr_models_root="opaque-model-root-ref",
    )


def test_worker_readiness_requires_local_models_when_enabled() -> None:
    calls = 0

    def unavailable(_manifest: str, _root: str) -> bool:
        nonlocal calls
        calls += 1
        return False

    client = TestClient(
        create_worker_app(settings=_settings(), local_ocr_probe=unavailable)
    )

    response = client.get("/health/ready")
    repeated = client.get("/health/ready")

    assert response.status_code == 503
    assert repeated.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert calls == 1


def test_worker_readiness_maps_safe_local_ocr_failure_to_generic_envelope() -> None:
    def blocked(_manifest: str, _root: str) -> bool:
        raise LocalOcrError("LOCAL_OCR_MODEL_MISSING")

    client = TestClient(create_worker_app(settings=_settings(), local_ocr_probe=blocked))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert "MODEL" not in response.json()["message"]


def test_worker_readiness_passes_after_local_manifest_verification() -> None:
    calls = 0

    def available(_manifest: str, _root: str) -> bool:
        nonlocal calls
        calls += 1
        return True

    client = TestClient(
        create_worker_app(settings=_settings(), local_ocr_probe=available)
    )

    response = client.get("/health/ready")
    repeated = client.get("/health/ready")

    assert response.status_code == 200
    assert repeated.status_code == 200
    assert response.json() == {"status": "ready"}
    assert calls == 1


def test_worker_readiness_offloads_initial_model_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offloaded: list[Callable[..., object]] = []

    async def fake_to_thread(function: Callable[..., Any], *args: object) -> Any:
        offloaded.append(function)
        return function(*args)

    monkeypatch.setattr("hyc_worker.main.asyncio.to_thread", fake_to_thread)
    client = TestClient(
        create_worker_app(
            settings=_settings(), local_ocr_probe=lambda _manifest, _root: True
        )
    )

    assert client.get("/health/ready").status_code == 200
    assert len(offloaded) == 1


def test_hyc_local_ocr_environment_names_and_legacy_names_both_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYC_LOCAL_OCR_ENABLED", "true")
    monkeypatch.setenv("HYC_LOCAL_OCR_MANIFEST_PATH", "hyc-manifest")
    monkeypatch.setenv("HYC_LOCAL_OCR_MODELS_ROOT", "hyc-models")
    hyc = Settings(_env_file=None)

    assert hyc.local_ocr_enabled is True
    assert hyc.local_ocr_manifest_path == "hyc-manifest"
    assert hyc.local_ocr_models_root == "hyc-models"

    monkeypatch.delenv("HYC_LOCAL_OCR_ENABLED")
    monkeypatch.delenv("HYC_LOCAL_OCR_MANIFEST_PATH")
    monkeypatch.delenv("HYC_LOCAL_OCR_MODELS_ROOT")
    monkeypatch.setenv("LOCAL_OCR_ENABLED", "true")
    monkeypatch.setenv("LOCAL_OCR_MANIFEST_PATH", "legacy-manifest")
    monkeypatch.setenv("LOCAL_OCR_MODELS_ROOT", "legacy-models")
    legacy = Settings(_env_file=None)

    assert legacy.local_ocr_enabled is True
    assert legacy.local_ocr_manifest_path == "legacy-manifest"
    assert legacy.local_ocr_models_root == "legacy-models"
