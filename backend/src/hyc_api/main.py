from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint

from hyc_api.config import Settings
from hyc_api.contracts import ErrorEnvelope, HealthEnvelope
from hyc_api.dependencies import ReadinessDependencies
from hyc_api.routes.documents import router as documents_router
from hyc_api.routes.inspections import router as inspections_router
from hyc_api.routes.intakes import router as intakes_router
from hyc_api.routes.lots import router as lots_router


def create_app(
    settings: Settings | None = None,
    readiness_factory: Callable[[Settings], ReadinessDependencies] = ReadinessDependencies,
) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="HYC Inspection API", version="0.1.0", openapi_version="3.1.0")
    app.state.settings = settings
    app.state.readiness_factory = readiness_factory
    app.state.engine = create_engine(settings.database_url, pool_pre_ping=True)
    app.state.session_factory = sessionmaker(app.state.engine, expire_on_commit=False)
    app.state.p3_sessions = {}
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=(
            r"^http://(?:127\.0\.0\.1|localhost)(?::\d+)?$"
            if settings.p3_fixture_mode
            else None
        ),
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )

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

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        payload = ErrorEnvelope(
            schema_version="1.0",
            code="REQUEST_VALIDATION_ERROR",
            message="Request validation failed",
            correlation_id=request.state.correlation_id,
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        payload = ErrorEnvelope(
            schema_version="1.0",
            code="HTTP_ERROR",
            message=str(error.detail),
            correlation_id=request.state.correlation_id,
        )
        return JSONResponse(status_code=error.status_code, content=payload.model_dump(mode="json"))

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

    @app.get("/health/live", tags=["health"], response_model=HealthEnvelope)
    async def live() -> HealthEnvelope:
        return HealthEnvelope(status="live")

    @app.get(
        "/health/ready",
        tags=["health"],
        response_model=HealthEnvelope,
        responses={503: {"model": ErrorEnvelope}},
    )
    async def ready(request: Request) -> JSONResponse:
        dependencies = request.app.state.readiness_factory(request.app.state.settings)
        try:
            is_ready = dependencies.database_ok() and dependencies.redis_ok()
        except (OSError, RedisError, SQLAlchemyError, ValueError):
            is_ready = False
        if is_ready:
            return JSONResponse(HealthEnvelope(status="ready").model_dump(mode="json"))
        payload = ErrorEnvelope(
            schema_version="1.0",
            code="DEPENDENCY_UNAVAILABLE",
            message="Required dependency is unavailable",
            correlation_id=request.state.correlation_id,
        )
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))

    app.include_router(intakes_router)
    app.include_router(documents_router)
    app.include_router(inspections_router)
    app.include_router(lots_router)

    return app


app = create_app()
