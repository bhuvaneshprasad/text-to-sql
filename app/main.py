import logging

from fastapi import FastAPI
from .config import get_settings
from .api.router import app_router
from contextlib import asynccontextmanager
from app.database.pool import create_read_only_pool
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting up: opening read-only database pool")
    database_pool = create_read_only_pool(settings=settings)

    await database_pool.open()
    await database_pool.wait()

    app.state.database_pool = database_pool
    logger.info("Database pool ready (min=%s, max=%s)", settings.postgres_pool_min_size, settings.postgres_pool_max_size)

    try:
        yield
    finally:
        logger.info("Shutting down: closing database pool")
        await database_pool.close()

def create_app():
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Creating app '%s' (debug=%s)", settings.app_name, settings.debug)
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan
    )

    app.include_router(
        app_router,
        prefix="/api/v1"
    )

    return app

app = create_app()