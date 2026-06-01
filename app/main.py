from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from app.core.config import settings
from app.api.router import router as api_router
from app.services.cache import semantic_cache

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs exactly when the Uvicorn worker process safely stabilizes
    print("Loading local embedding model and connecting to Qdrant...")
    semantic_cache.initialize()
    print("Infrastructure engines fully initialized!")
    yield
    # Any cleanup code would go here when shutting down
    print("Shutting down worker proxy application...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    default_response_class=ORJSONResponse,
    lifespan=lifespan  # Attach our lifespan control
)

app.include_router(api_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "proxy": settings.PROJECT_NAME}