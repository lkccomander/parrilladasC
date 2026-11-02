from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from parrilladas.core.config import AdminSettings
from parrilladas.core.security_headers import SecurityHeadersMiddleware
from parrilladas.modules.accounts.errors import InvalidCredentials
from parrilladas.modules.dashboard.client import ApiUnavailable
from parrilladas.modules.dashboard.cookies import set_session_cookie
from parrilladas.modules.dashboard.router import page
from parrilladas.modules.dashboard.router import router as dashboard_router
from parrilladas.modules.health.admin import router as health_router


def create_app(
    settings: AdminSettings | None = None, *, api_http: httpx.Client | None = None
) -> FastAPI:
    """Admin service only: renders UI and calls the API over HTTP; no database resources."""
    settings = settings if settings is not None else AdminSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.api_http = api_http or httpx.Client(
            base_url=settings.api_base_url,
            timeout=httpx.Timeout(8.0, connect=3.0),
            follow_redirects=False,
        )
        try:
            yield
        finally:
            if api_http is None:
                app.state.api_http.close()

    app = FastAPI(
        title="Parrilladas Admin",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.secure_cookies = settings.app_env in {"staging", "production"}
    app.add_middleware(SecurityHeadersMiddleware)

    @app.middleware("http")
    async def refreshed_cookies(request: Request, call_next):
        response = await call_next(request)
        created = getattr(request.state, "pending_credentials", None)
        if created is not None:
            set_session_cookie(request, response, created)
        return response

    @app.exception_handler(ApiUnavailable)
    async def unavailable(request: Request, error: ApiUnavailable):
        return page(request, "unavailable.html", 503)

    @app.exception_handler(InvalidCredentials)
    async def expired(request: Request, error: InvalidCredentials):
        return RedirectResponse("/login", status_code=303)

    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "modules" / "dashboard" / "static"),
        name="static",
    )
    app.include_router(health_router)
    app.include_router(dashboard_router)
    return app
