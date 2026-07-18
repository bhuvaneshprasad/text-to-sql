from fastapi import FastAPI
from .config import settings
from .api.router import app_router

def create_app():
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug
    )

    app.include_router(
        app_router,
        prefix="/api/v1"
    )

    return app

app = create_app()