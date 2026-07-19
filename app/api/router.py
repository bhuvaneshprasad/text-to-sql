from fastapi import APIRouter
from .health import health_router
from .chat import chat_router

app_router = APIRouter()
app_router.include_router(health_router)
app_router.include_router(chat_router)