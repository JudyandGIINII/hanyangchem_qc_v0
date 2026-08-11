from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint

from hyc_api.config import Settings
from hyc_api.contracts import ErrorEnvelope, HealthEnvelope
from hyc_api.dependencies import ReadinessDependencies
from hyc_api.extraction import ExtractionProvider
from hyc_api.routes.aliases import router as aliases_router
from hyc_api.routes.documents import router as documents_router
from hyc_api.routes.feature_flags import router as feature_flags_router
from hyc_api.routes.inspections import router as inspections_router
from hyc_api.routes.intakes import router as intakes_router
from hyc_api.routes.lots import router as lots_router
from hyc_api.routes.masters import router as masters_router
from hyc_api.routes.nonconformances import router as nonconformances_router
from hyc_api.routes.reports import router as reports_router
from hyc_api.routes.specs import router as specs_router
from hyc_api.routes.statistics import router as statistics_router

LocalOcrProviderFactory = Callable[[Settings], ExtractionProvider]


class LocalOcrProviderInitializationError(RuntimeError):
    """Bounded fail-closed startup error for explicitly enabled local OCR."""

    def __init__(self) -> None:
        super().__init__("LOCAL_OCR_INITIALIZATION_FAILED")


def _build_local_ocr_provider(settings: Settings) -> ExtractionProvider:
    """Import optional OCR dependencies only after explicit local enablement."""

    try:
        provider_type: Any = import_module("hyc_api.extraction").LocalOcrExtractionProvider
        engine_type: Any = import_module("hyc_local_ocr.engine").PaddleOcrEngine
        backend_type: Any = import_module("hyc_local_ocr.pdf_backend").PyMuPdfDocumentBackend
        pipeline_type: Any = import_module("hyc_local_ocr.pipeline").LocalOcrPipeline
        preprocessor_type: Any = import_module("hyc_local_ocr.preprocess").OpenCvPreprocessor
        engine = engine_type.from_local_models(
            Path(settings.local_ocr_manifest_path), Path(settings.local_ocr_models_root)
        )
        pipeline = pipeline_type(backend_type(), engine, preprocessor=preprocessor_type())
        return cast(ExtractionProvider, provider_type(pipeline))
    except Exception as error:
        raise LocalOcrProviderInitializationError() from error


def create_app(
    settings: Settings | None = None,
    readiness_factory: Callable[[Settings], ReadinessDependencies] = ReadinessDependencies,
    local_ocr_provider_factory: LocalOcrProviderFactory = _build_local_ocr_provider,
) -> FastAPI:
    settings = settings or Settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    document_lock_engine: Engine | None = None
    if engine.dialect.name == "postgresql":
        # Advisory locks retain their checked-out connection for the request.
        # Keep that connection out of the application QueuePool entirely.
        document_lock_engine = create_engine(
            settings.database_url,
            poolclass=NullPool,
            pool_pre_ping=True,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if document_lock_engine is not None:
                document_lock_engine.dispose()
            engine.dispose()

    app = FastAPI(
        title="HYC Inspection API",
        version="0.1.0",
        openapi_version="3.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.readiness_factory = readiness_factory
    app.state.engine = engine
    app.state.session_factory = sessionmaker(app.state.engine, expire_on_commit=False)
    app.state.document_lock_engine = document_lock_engine
    app.state.p3_sessions = {}
    app.state.local_ocr_provider = (
        local_ocr_provider_factory(settings) if settings.local_ocr_enabled else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=(
            r"^http://(?:127\.0\.0\.1|localhost)(?::\d+)?$" if settings.p3_fixture_mode else None
        ),
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
    app.include_router(masters_router)
    app.include_router(specs_router)
    app.include_router(aliases_router)
    app.include_router(nonconformances_router)
    app.include_router(reports_router)
    app.include_router(statistics_router)
    app.include_router(feature_flags_router)


    return app


app = create_app()
