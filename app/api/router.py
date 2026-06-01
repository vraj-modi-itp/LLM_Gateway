import time
from fastapi import APIRouter, Header, HTTPException, status, BackgroundTasks
from fastapi.responses import ORJSONResponse
import httpx

from app.api.schemas import ChatCompletionRequest
from app.core.config import settings
from app.services.dlp import dlp_service
from app.services.cache import semantic_cache
from app.services.telemetry import log_transaction 

router = APIRouter(prefix="/v1")

PROVIDER_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
}

@router.post("/chat/completions", response_class=ORJSONResponse)
async def proxy_chat_completion(
    payload: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    x_app_id: str = Header(..., description="The internal application tracking identifier"),
    x_target_provider: str = Header(..., description="Target engine: 'groq' or 'gemini'"),
    x_bypass_cache: bool = Header(False, description="Set to true to skip semantic caching") 
):
    start_time = time.time() # ⏱️ Start the stopwatch
    provider = x_target_provider.lower().strip()
    
    if provider not in PROVIDER_URLS:
        raise HTTPException(status_code=400, detail="Unsupported provider.")

    # 1. DLP Security Scan
    sanitized_messages, entities_found, was_modified = dlp_service.scan_and_redact_messages(payload.messages)
    payload.messages = sanitized_messages

    # 2. Semantic Cache Check (Surgical Bypass)
    if not x_bypass_cache:
        cached_response = semantic_cache.query_cache(payload.messages, threshold=0.95)
        if cached_response:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            # Fire off the database log in the background
            background_tasks.add_task(log_transaction, x_app_id, provider, 0, 0, latency_ms, True)
            
            return ORJSONResponse(
                content={
                    "id": "chatcmpl-cached",
                    "object": "chat.completion",
                    "model": payload.model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": cached_response}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                },
                status_code=200,
                headers={
                    "X-Proxy-Latency-Ms": str(latency_ms),
                    "X-Proxy-Total-Tokens": "0",
                    "X-Proxy-Cache-Hit": "True"
                }
            )

    # 3. LLM Network Forwarding (Cache Miss or Cache Bypassed)
    target_url = PROVIDER_URLS[provider]
    api_key = settings.GROQ_API_KEY if provider == "groq" else settings.GEMINI_API_KEY
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(target_url, json=payload.model_dump(), headers=headers)
            response_json = response.json()
            
            prompt_tokens, completion_tokens = 0, 0
            
            if response.status_code == 200:
                # Extract tokens from the provider's response
                usage = response_json.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                
                # Only update the cache if we aren't bypassing it
                if not x_bypass_cache:
                    assistant_text = response_json["choices"][0]["message"]["content"]
                    semantic_cache.update_cache(payload.messages, assistant_text)

            # Stop the stopwatch
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            # Fire off the database log in the background
            background_tasks.add_task(
                log_transaction, x_app_id, provider, prompt_tokens, completion_tokens, latency_ms, False
            )

            return ORJSONResponse(
                content=response_json,
                status_code=response.status_code,
                headers={
                    "X-Proxy-Latency-Ms": str(latency_ms),
                    "X-Proxy-Total-Tokens": str(prompt_tokens + completion_tokens),
                    "X-Proxy-Cache-Hit": "False"
                }
            )
        except httpx.HTTPError as err:
            raise HTTPException(status_code=502, detail=f"Outbound failure: {str(err)}")