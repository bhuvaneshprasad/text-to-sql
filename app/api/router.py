from fastapi import APIRouter
from .health import health_router

app_router = APIRouter()
app_router.include_router(health_router)