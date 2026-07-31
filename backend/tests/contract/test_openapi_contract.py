from __future__ import annotations

from fastapi.testclient import TestClient

from hyc_api.config import Settings
from hyc_api.dependencies import ReadinessDependencies
from hyc_api.main import create_app


class DownDependencies(ReadinessDependencies):
    def database_ok(self) -> bool:
        return False


def test_health_surface_and_correlation_id() -> None:
    client = TestClient(create_app())
    supplied = "123e4567-e89b-12d3-a456-426614174010"
    response = client.get("/health/live", headers={"X-Correlation-ID": supplied})
    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert response.headers["X-Correlation-ID"] == supplied
    openapi = client.get("/openapi.json").json()
    assert set(openapi["paths"]) >= {"/health/live", "/health/ready"}
    assert openapi["info"]["version"] == "0.1.0"


def test_readiness_failure_uses_typed_error_envelope() -> None:
    client = TestClient(create_app(Settings(), DownDependencies))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert response.headers["X-Correlation-ID"] == response.json()["correlation_id"]


def test_not_found_uses_typed_error_envelope() -> None:
    response = TestClient(create_app()).get("/not-a-route")
    assert response.status_code == 404
    assert response.json()["code"] == "HTTP_ERROR"


class ExplodingDependencies(ReadinessDependencies):
    def database_ok(self) -> bool:
        raise RuntimeError("must not leak")


def test_unhandled_api_error_is_typed_and_correlated() -> None:
    supplied = "123e4567-e89b-12d3-a456-426614174011"
    response = TestClient(
        create_app(Settings(), ExplodingDependencies), raise_server_exceptions=False
    ).get("/health/ready", headers={"X-Correlation-ID": supplied})
    assert response.status_code == 500
    assert response.json() == {
        "schema_version": "1.0",
        "code": "INTERNAL_ERROR",
        "message": "Internal server error",
        "correlation_id": supplied,
    }
    assert response.headers["X-Correlation-ID"] == supplied
