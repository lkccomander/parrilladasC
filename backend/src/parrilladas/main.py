import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from parrilladas import __version__
from parrilladas.core.config import Settings
from parrilladas.db.session import create_database_engine
from parrilladas.modules.dashboard.router import router as dashboard_router
from parrilladas.modules.health.router import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Compose modules and resources; importing this module performs no database I/O."""
    settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(level=logging.INFO)
        engine = create_database_engine(settings)
        app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            yield
        finally:
            engine.dispose()

    development_docs = settings.app_env in {"development", "test"}
    app = FastAPI(
        title="Parrilladas",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if development_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if development_docs else None,
    )
    app.include_router(health_router)
    app.include_router(dashboard_router)
    return app
