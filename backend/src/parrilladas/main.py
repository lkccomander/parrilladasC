import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

import parrilladas.db.models  # noqa: F401  # Register all ORM models with Base.metadata.
from parrilladas import __version__
from parrilladas.core.config import ApiSettings
from parrilladas.core.security_headers import SecurityHeadersMiddleware
from parrilladas.db.session import create_database_engine
from parrilladas.integrations.whatsapp.router import create_outbound_sender
from parrilladas.integrations.whatsapp.router import router as whatsapp_router
from parrilladas.modules.accounts.errors import (
    AccessDenied,
    AccountConflict,
    AccountError,
    AccountNotFound,
    InvalidCredentials,
    LoginThrottled,
)
from parrilladas.modules.accounts.router import router as accounts_router
from parrilladas.modules.assistant.config import AssistantSettings
from parrilladas.modules.assistant.errors import ExtractionUnavailable
from parrilladas.modules.assistant.knowledge_router import router as knowledge_router
from parrilladas.modules.assistant.monitoring.evaluation import EvaluationService
from parrilladas.modules.assistant.monitoring.instrumentation import TraceRecorder
from parrilladas.modules.assistant.monitoring.router import router as monitoring_router
from parrilladas.modules.assistant.monitoring.service import MonitoringService
from parrilladas.modules.assistant.monitoring.worker import MonitoringWorker
from parrilladas.modules.assistant.rag import KnowledgeService
from parrilladas.modules.assistant.router import router as assistant_router
from parrilladas.modules.assistant.service import AssistantService
from parrilladas.modules.assistant.telemetry import Telemetry
from parrilladas.modules.assistant.telemetry_router import router as telemetry_router
from parrilladas.modules.conversations.router import router as conversations_router
from parrilladas.modules.conversations.worker import ConversationWorker
from parrilladas.modules.health.router import router as health_router
from parrilladas.modules.integrations.router import router as integrations_router

_SOURCE_ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"
ASSETS_DIR = next(
    (directory for directory in (_SOURCE_ASSETS_DIR, Path("/app/assets")) if directory.is_dir()),
    _SOURCE_ASSETS_DIR,
)


async def account_error(request: Request, error: AccountError) -> JSONResponse:
    status = {
        AccessDenied: 403,
        AccountConflict: 409,
        AccountNotFound: 404,
        InvalidCredentials: 401,
        LoginThrottled: 429,
    }.get(type(error), 400)
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
    if status == 429:
        headers["Retry-After"] = "900"
    return JSONResponse(status_code=status, content={"detail": str(error)}, headers=headers)


async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    # Pydantic's default JSON errors include raw inputs, including passwords.
    details = [
        {"loc": item["loc"], "type": item["type"], "msg": item["msg"]} for item in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


def create_app(
    settings: ApiSettings | None = None,
    *,
    meta_http: httpx.Client | None = None,
    assistant_settings: AssistantSettings | None = None,
    extractor=None,
) -> FastAPI:
    """API service only: owns database resources and JSON business endpoints."""
    settings = settings if settings is not None else ApiSettings()
    assistant_settings = assistant_settings or AssistantSettings(app_env=settings.app_env)
    if assistant_settings.natural_language_enabled and not settings.conversation_worker_enabled:
        raise ValueError("Live natural language requires the durable conversation worker")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO)
        engine = create_database_engine(settings)
        app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        app.state.meta_http = meta_http if meta_http is not None else httpx.Client()
        app.state.telemetry = Telemetry(app.state.session_factory)
        app.state.trace_recorder = TraceRecorder(
            app.state.session_factory,
            settings.jwt_secret,
            retention_days=assistant_settings.rag_trace_retention_days,
        )
        app.state.assistant_settings = assistant_settings
        provider = extractor
        if assistant_settings.natural_language_enabled and provider is None:
            from parrilladas.integrations.vertex_ai.client import VertexExtractor

            try:
                provider = VertexExtractor.from_settings(assistant_settings)
            except ExtractionUnavailable:
                app.state.telemetry.emit(
                    operation="extraction_result",
                    status="fallback",
                    reason="provider_unavailable",
                    error_kind="authentication",
                )
                logging.getLogger(__name__).warning(
                    "Assistant authentication unavailable; guided mode"
                )
        if provider is not None and extractor is None:
            provider.telemetry = app.state.telemetry
        knowledge_provider = None
        if assistant_settings.rag_enabled and provider is not None and extractor is None:
            from parrilladas.integrations.vertex_ai.knowledge import VertexKnowledge

            try:
                knowledge_provider = VertexKnowledge.from_settings(assistant_settings, provider)
            except ExtractionUnavailable:
                app.state.telemetry.emit(
                    operation="rag_result",
                    status="fallback",
                    reason="catalog_fallback",
                    error_kind="authentication",
                )
                logging.getLogger(__name__).warning(
                    "RAG authentication unavailable; catalog fallback"
                )
        app.state.knowledge = KnowledgeService(
            app.state.session_factory,
            knowledge_provider,
            assistant_settings,
            telemetry=app.state.telemetry,
            recorder=app.state.trace_recorder,
        )
        app.state.evaluations = EvaluationService(
            app.state.session_factory, app.state.knowledge, assistant_settings
        )
        app.state.monitoring = MonitoringService(
            app.state.session_factory, assistant_settings, evaluations=app.state.evaluations
        )
        monitoring_worker = None
        if assistant_settings.rag_monitoring_enabled:
            monitoring_worker = MonitoringWorker(
                app.state.monitoring,
                interval_seconds=assistant_settings.rag_monitoring_interval_seconds,
            )
            monitoring_worker.start()
        app.state.assistant = AssistantService(
            provider,
            enabled=assistant_settings.natural_language_enabled and provider is not None,
            knowledge=app.state.knowledge,
            telemetry=app.state.telemetry,
        )
        worker = None
        if settings.conversation_worker_enabled:
            worker = ConversationWorker(
                app.state.session_factory,
                sender=create_outbound_sender(app.state.meta_http, settings),
                assistant=app.state.assistant,
                settings=settings,
            )
            worker.start()
        app.state.conversation_worker = worker
        try:
            yield
        finally:
            if worker is not None:
                await run_in_threadpool(worker.stop)
            if monitoring_worker is not None:
                await run_in_threadpool(monitoring_worker.stop)
            if knowledge_provider is not None:
                knowledge_provider.close()
            if provider is not None and extractor is None:
                provider.close()
            if meta_http is None:
                app.state.meta_http.close()
            engine.dispose()

    docs = settings.app_env in {"development", "test"}
    app = FastAPI(
        title="Parrilladas API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_exception_handler(AccountError, account_error)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
    app.include_router(health_router)
    app.include_router(accounts_router)
    app.include_router(assistant_router)
    app.include_router(knowledge_router)
    app.include_router(telemetry_router)
    app.include_router(monitoring_router)
    app.include_router(conversations_router)
    app.include_router(whatsapp_router)
    app.include_router(integrations_router)
    return app
