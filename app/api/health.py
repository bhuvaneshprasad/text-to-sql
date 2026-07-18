from fastapi import APIRouter

from app.models.health import HealthResponse

health_router = APIRouter(prefix="/health")

@health_router.get(path="/", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")