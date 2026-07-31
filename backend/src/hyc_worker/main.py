from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from redis import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import RequestResponseEndpoint

from hyc_api.config import Settings
from hyc_api.contracts import ErrorEnvelope, HealthEnvelope

RedisFactory = Callable[[str, float], Redis]


def create_redis_client(url: str, timeout: float) -> Redis:
    return Redis.from_url(url, socket_connect_timeout=timeout)


def create_worker_app(
    settings: Settings | None = None, redis_factory: RedisFactory = create_redis_client
) -> FastAPI:
    settings = settings or Settings(app_name="hyc-inspection-worker")
    app = FastAPI(title="HYC Inspection Worker", version="0.1.0", openapi_url=None)

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
