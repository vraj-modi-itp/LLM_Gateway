from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
import asyncio

from app.core.config import settings
from app.api.router import router as api_router
from app.services.cache import semantic_cache
from app.services.telemetry import refresh_provider_metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Loading local embedding model and connecting to Qdrant...")
    semantic_cache.initialize()
    
    # Start the 60-second background telemetry loop
    asyncio.create_task(refresh_provider_metrics())
    
    print("Infrastructure engines fully initialized!")
    yield
    print("Shutting down worker proxy application...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    default_response_class=ORJSONResponse,
    lifespan=lifespan
)

app.include_router(api_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "proxy": settings.PROJECT_NAME}