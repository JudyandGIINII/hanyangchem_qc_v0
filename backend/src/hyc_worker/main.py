from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from redis import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import RequestResponseEndpoint

from hyc_api.config import Settings
from hyc_api.contracts import ErrorEnvelope, HealthEnvelope
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.manifest import load_and_verify_manifest

RedisFactory = Callable[[str, float], Redis]
LocalOcrProbe = Callable[[str, str], bool]


def create_redis_client(url: str, timeout: float) -> Redis:
    return Redis.from_url(url, socket_connect_timeout=timeout)


def verify_local_ocr_models(manifest_path: str, models_root: str) -> bool:
    load_and_verify_manifest(Path(manifest_path), Path(models_root))
    return True


def create_worker_app(
    settings: Settings | None = None,
    redis_factory: RedisFactory = create_redis_client,
    local_ocr_probe: LocalOcrProbe = verify_local_ocr_models,
) -> FastAPI:
    settings = settings or Settings(app_name="hyc-inspection-worker")
    app = FastAPI(title="HYC Inspection Worker", version="0.1.0", openapi_url=None)
    local_ocr_verification: bool | None = None
    local_ocr_verification_lock = asyncio.Lock()

    async def local_ocr_is_ready() -> bool:
        nonlocal local_ocr_verification
        if local_ocr_verification is not None:
            return local_ocr_verification
        async with local_ocr_verification_lock:
            if local_ocr_verification is not None:
                return local_ocr_verification
            try:
                local_ocr_verification = await asyncio.to_thread(
                    local_ocr_probe,
                    settings.local_ocr_manifest_path,
                    settings.local_ocr_models_root,
                )
            except (LocalOcrError, OSError, ValueError):
                local_ocr_verification = False
            return local_ocr_verification

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raw_id = request.headers.get("X-Correlation-ID")
        try:
            correlation_id = UUID(raw_id) if raw_id else uuid4()
        except ValueError:
            correlation_id = uuid4()
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        return response

    @app.exception_handler(Exception)
    async def internal_error(request: Request, _: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", uuid4())
        payload = ErrorEnvelope(
            schema_version="1.0",
            code="INTERNAL_ERROR",
            message="Internal server error",
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=500,
            content=payload.model_dump(mode="json"),
            headers={"X-Correlation-ID": str(correlation_id)},
        )

    @app.get("/health/live", response_model=HealthEnvelope)
    async def live() -> HealthEnvelope:
        return HealthEnvelope(status="live")

    @app.get(
        "/health/ready",
        response_model=HealthEnvelope,
        responses={503: {"model": ErrorEnvelope}},
    )
    async def ready(request: Request) -> HealthEnvelope | JSONResponse:
        if settings.local_ocr_enabled:
            if not await local_ocr_is_ready():
                return unavailable(request)
        if settings.check_redis_on_ready:
            client: Redis | None = None
            try:
                client = redis_factory(settings.redis_url, settings.request_timeout_seconds)
                if not client.ping():
                    return unavailable(request)
            except (OSError, RedisError, ValueError):
                return unavailable(request)
            finally:
                if client is not None:
                    client.close()
        return HealthEnvelope(status="ready")

    def unavailable(request: Request) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=ErrorEnvelope(
                schema_version="1.0",
                code="DEPENDENCY_UNAVAILABLE",
                message="Required dependency is unavailable",
                correlation_id=request.state.correlation_id,
            ).model_dump(mode="json"),
        )

    return app


app = create_worker_app()
