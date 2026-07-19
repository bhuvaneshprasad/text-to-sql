from fastapi import FastAPI
from .config import get_settings
from .api.router import app_router
from contextlib import asynccontextmanager
from app.database.pool import create_read_only_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    database_pool = create_read_only_pool(settings=settings)

    await database_pool.open()
    await database_pool.wait()

    app.state.database_pool = database_pool

    try: 
        yield
    finally:
        await database_pool.close()

def create_app():
    settings = get_settings()
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