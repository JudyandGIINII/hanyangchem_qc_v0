from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from scripts.check_sensitive_documents import FORBIDDEN_SUFFIXES
from scripts.scan_secrets import credential_finding, is_approved_fixture

from hyc_api import dependencies
from hyc_api.config import Settings
from hyc_api.dependencies import ReadinessDependencies
from hyc_api.main import create_app
from hyc_worker.main import create_worker_app


class RaisingApiDependencies(ReadinessDependencies):
    def database_ok(self) -> bool:
        raise OSError("unavailable")


def test_api_readiness_connection_exception_is_a_typed_503() -> None:
    response = TestClient(create_app(Settings(), RaisingApiDependencies)).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


def test_api_readiness_configuration_error_is_a_typed_503() -> None:
    class InvalidApiDependencies(ReadinessDependencies):
        def database_ok(self) -> bool:
            raise ValueError("malformed configuration")

    response = TestClient(create_app(Settings(), InvalidApiDependencies)).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


def test_default_readiness_settings_fail_closed_without_successful_probes() -> None:
    assert Settings().check_database_on_ready is True
    assert Settings().check_redis_on_ready is True


def test_api_dependency_probe_catches_database_connection_exception(monkeypatch) -> None:
    def failing_create_engine(*_args: object, **_kwargs: object):
        raise OSError("unavailable")

    monkeypatch.setattr(dependencies, "create_engine", failing_create_engine)
    assert ReadinessDependencies(Settings(check_database_on_ready=True)).database_ok() is False


def test_worker_readiness_connection_exception_is_a_typed_503() -> None:
    def failing_redis_factory(_: str, __: float):
        raise RedisConnectionError("unavailable")

    app = create_worker_app(Settings(check_redis_on_ready=True), failing_redis_factory)
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert response.headers["X-Correlation-ID"] == response.json()["correlation_id"]


def test_worker_configuration_error_is_a_typed_503() -> None:
    class InvalidRedis:
        def ping(self) -> bool:
            raise ValueError("malformed configuration")

        def close(self) -> None:
            pass

    app = create_worker_app(Settings(check_redis_on_ready=True), lambda *_: InvalidRedis())
    response = TestClient(app).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


def test_worker_unhandled_error_is_typed_and_correlated() -> None:
    def exploding_factory(*_: object) -> object:
        raise RuntimeError("must not leak")

    supplied = "123e4567-e89b-12d3-a456-426614174012"
    response = TestClient(
        create_worker_app(Settings(check_redis_on_ready=True), exploding_factory),
        raise_server_exceptions=False,
    ).get("/health/ready", headers={"X-Correlation-ID": supplied})
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["message"] == "Internal server error"
    assert response.headers["X-Correlation-ID"] == supplied
    assert response.json()["correlation_id"] == supplied


def test_secret_scan_rejects_generic_allowance_comments_and_uri_credentials() -> None:
    expected_assignment = "password" + " = " + "value-without-allowance"
    expected_key_assignment = "api_key" + " = " + "value-without-allowance"
    unallowed_uri = "postgresql://local_user:" + "not-a-placeholder@db/hyc"
    assert credential_finding("docs/sentinel.md", 1, expected_assignment)
    assert credential_finding("backend/tests/sentinel.py", 1, expected_key_assignment)
    assert credential_finding("compose.yaml", 1, unallowed_uri)
    generic_bypass = expected_assignment + " # secret-scan: allow-placeholder"
    assert credential_finding("docs/sentinel.md", 1, generic_bypass)
    suffix = "value-for-test"
    keys = (
        "POSTGRES_" + "PASSWORD",
        "OPENAI_" + "API_KEY",
        "AWS_" + "SECRET_ACCESS_KEY",
        "SECRET_KEY",
        "db_" + "password",
        "ACCESS_" + "TOKEN",
        "AUTH_" + "TOKEN",
    )
    for key in keys:
        assert credential_finding("docs/sentinel.md", 1, f"{key}={suffix}")
    assert credential_finding(
        "docs/sentinel.json", 1, '{"OPENAI_' + 'API_KEY": "value-for-test"}'
    )


def test_secret_scan_allows_only_known_local_placeholders() -> None:
    assert credential_finding(".env.example", 1, "password=local-placeholder-only") is None
    assert (
        credential_finding(
            "compose.yaml", 1, "postgresql://local_user:local-placeholder-only@postgres/hyc"
        )
        is None
    )
    assert (
        credential_finding("docs/evidence/example.json", 1, "postgresql://local_user:***@db/hyc")
        is None
    )
    placeholder = "local-" + "placeholder-only"
    assert credential_finding(".env.example", 1, "POSTGRES_" + f"PASSWORD={placeholder}") is None
    assert credential_finding(".env.example", 1, '"OPENAI_API_KEY": "***"') is None
    for ordinary_key in ("monkey", "keyboard", "password_policy", "api_key_rotation"):
        assert credential_finding("docs/sentinel.md", 1, f"{ordinary_key}=ordinary-value") is None


def test_secret_scan_fixture_policy_is_path_and_content_bound() -> None:
    fixture = "password = synthetic-fixture-value"
    assert credential_finding("renamed-fixture.py", 1, fixture)
    assert credential_finding(
        "backend/tests/integration/importers/test_spec_workbook_dry_run.py", 999, fixture
    )
    assert not is_approved_fixture("renamed-fixture.py", fixture)


def test_secret_scan_approved_fixture_cannot_be_renamed_or_shifted() -> None:
    fixture_path = Path("backend/tests/integration/importers/test_spec_workbook_dry_run.py")
    fixture_content = fixture_path.read_text()
    assert is_approved_fixture(fixture_path.as_posix(), fixture_content)
    assert not is_approved_fixture("backend/tests/renamed.py", fixture_content)
    assert not is_approved_fixture(fixture_path.as_posix(), "\n" + fixture_content)


def test_sensitive_document_prevention_covers_all_required_extensions() -> None:
    assert {".doc", ".docx", ".hwp", ".hwpx", ".ppt", ".pptx", ".csv"} <= FORBIDDEN_SUFFIXES
