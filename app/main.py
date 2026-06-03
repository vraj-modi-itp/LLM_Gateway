from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse
from contextlib import asynccontextmanager
import asyncio
import time
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues

# 1. INITIALIZE OBSERVABILITY FIRST
from app.logger import setup_logging, gateway_log
from app.observability import init_observability, get_tracer

setup_logging()
init_observability()
tracer = get_tracer()

# 2. IMPORT ROUTERS & SERVICES
from app.core.config import settings
from app.api.router import router as api_router
from app.services.cache import semantic_cache
from app.services.telemetry import refresh_provider_metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    gateway_log.info("Loading local embedding model and connecting to Qdrant...")
    semantic_cache.initialize()
    asyncio.create_task(refresh_provider_metrics())
    gateway_log.info("Infrastructure engines fully initialized!")
    yield
    gateway_log.info("Shutting down worker proxy application...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    default_response_class=ORJSONResponse,
    lifespan=lifespan
)

@app.middleware("http")
async def log_and_trace_requests(request: Request, call_next):
    start_time = time.perf_counter()
    app_id = request.headers.get("x-app-id", "unknown_app")
    
    # Rename to something Phoenix likes, and add the CHAIN attribute
    with tracer.start_as_current_span("ai_gateway_workflow") as span:
        # Tell Phoenix: "This entire web request is an AI Workflow (Chain)"
        span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.CHAIN.value)
        
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.url", str(request.url))
        span.set_attribute("app.id", app_id)
        
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.status.Status(trace.status.StatusCode.ERROR))
            raise e
        finally:
            duration = (time.perf_counter() - start_time) * 1000
            final_status = locals().get('status_code', 500)
            
            span.set_attribute("http.status_code", final_status)
            span.set_attribute("duration_ms", duration)
            
            gateway_log.info(
                f"Processed HTTP {request.method} request for path {request.url.path}",
                extra={"extra_fields": {
                    "app_id": app_id,
                    "status_code": final_status,
                    "latency_ms": round(duration, 2),
                    "path": request.url.path
                }}
            )
        return response

app.include_router(api_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}