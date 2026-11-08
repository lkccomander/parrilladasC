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

import parrilladas.db.models  # noqa: F401  # Register all ORM models with Base.metadata.
from parrilladas import __version__
from parrilladas.core.config import ApiSettings
from parrilladas.core.security_headers import SecurityHeadersMiddleware
from parrilladas.db.session import create_database_engine
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
    settings: ApiSettings | None = None, *, meta_http: httpx.Client | None = None
) -> FastAPI:
    """API service only: owns database resources and JSON business endpoints."""
    settings = settings if settings is not None else ApiSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO)
        engine = create_database_engine(settings)
        app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        app.state.meta_http = meta_http if meta_http is not None else httpx.Client()
        try:
            yield
        finally:
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
    app.include_router(whatsapp_router)
    app.include_router(integrations_router)
    return app
