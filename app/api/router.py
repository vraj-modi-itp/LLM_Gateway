import time
import json
import numpy as np
from typing import List, Tuple, Dict
from fastapi import APIRouter, Header, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import JSONResponse
import httpx

# --- Observability & Semantic Conventions ---
from opentelemetry import trace
from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues

from app.api.schemas import ChatCompletionRequest, ChatMessage
from app.core.config import settings
from app.services.dlp import dlp_service
from app.services.cache import semantic_cache
from app.services.telemetry import log_transaction_and_routing, log_security_alert
from app.services.prompt_analyzer import prompt_analyzer
from app.services.budget import budget_service

# --- Path A Audit Logging Service ---
try:
    from app.services.audit_service import audit_service
except ImportError:
    # Safe fallback if the file isn't created yet to prevent crashing
    class DummyAudit:
        async def log_interaction(self, *args, **kwargs): pass
    audit_service = DummyAudit()

router = APIRouter(prefix="/v1")
google_native_router = APIRouter()

PROVIDER_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "ollama": settings.OLLAMA_BASE_URL
}

FALLBACK_PRIORITY = {
    "groq": ["groq", "gemini", "ollama"],
    "gemini": ["gemini", "groq", "ollama"],
    "ollama": ["ollama", "groq", "gemini"]
}

PROVIDER_TIMEOUTS = {
    "groq": 15.0,
    "gemini": 45.0,
    "ollama": 180.0
}

ROUTE_EXAMPLES = {
    "groq": [
        "Write a python function to reverse a string.",
        "How do I fix a NullPointerException in Java?",
        "Create a React component for a dropdown menu.",
        "Debug this SQL query, it's running too slow.",
        "What is the difference between an interface and abstract class?"
    ],
    "gemini": [
        "Summarize this 20-page document on monetary policy.",
        "Analyze the themes of isolation in Mary Shelley's Frankenstein.",
        "Compare and contrast the economic impacts of the Industrial Revolution.",
        "Write a comprehensive essay on the history of the Roman Empire.",
        "Extract all the key arguments from this legal transcript."
    ],
    "ollama": [
        "What is the capital of France?",
        "Who wrote the play Hamlet?",
        "Tell me a joke about a programmer.",
        "What are the ingredients for a chocolate cake?",
        "Write a short polite email declining a meeting."
    ]
}

class SemanticClassifier:
    def __init__(self):
        self.centroids: Dict[str, np.ndarray] = {}
        self.is_initialized = False

    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        return dot_product / (norm_v1 * norm_v2)

    def initialize_centroids(self, embedding_model):
        for provider, examples in ROUTE_EXAMPLES.items():
            embeddings = embedding_model.encode(examples)
            self.centroids[provider] = np.mean(embeddings, axis=0)
        self.is_initialized = True

    def classify(self, prompt: str, embedding_model) -> Tuple[str, str]:
        if len(prompt.split()) > 800:
            return "gemini", "Length > 800 words; physical token limit override."
        if not self.is_initialized:
            self.initialize_centroids(embedding_model)

        prompt_vector = embedding_model.encode(prompt)
        best_provider = "ollama" 
        highest_score = -1.0
        scores_debug = []

        for provider, centroid in self.centroids.items():
            score = self._cosine_similarity(prompt_vector, centroid)
            scores_debug.append(f"{provider}: {score:.2f}")
            if score > highest_score:
                highest_score = score
                best_provider = provider

        reason = f"Semantic Match ({best_provider}). Confidences: [{', '.join(scores_debug)}]"
        return best_provider, reason

intent_classifier = SemanticClassifier()

def get_provider_auth(provider: str) -> dict:
    if provider == "groq":
        return {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
    elif provider == "gemini":
        return {"Authorization": f"Bearer {settings.GEMINI_API_KEY}", "Content-Type": "application/json"}
    else: 
        return {"Content-Type": "application/json"}

# --- STANDARD OPENAI COMPATIBLE ROUTE ---
@router.post("/chat/completions")
async def proxy_chat_completion(
    payload: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    x_app_id: str = Header(..., description="Internal app identifier"),
    x_bypass_cache: str = Header("false", description="Skip caching"),
    x_session_id: str = Header(None, description="Unique session ID for agent loop isolation"),
    x_request_type: str = Header("standard", description="Traffic classifier: standard or agent"),
    x_opt_out_audit: str = Header("false", description="Privacy flag to skip chat history logging") # NEW: Privacy Opt-Out Header
):
    tracer = trace.get_tracer("ai-proxy-gateway")
    
    # Process the opt-out flag securely
    opt_out_audit = x_opt_out_audit.lower() in ["true", "1", "yes"]
    
    # --- 1. ACTIVE GOVERNANCE: BUDGET & RATE LIMIT ENFORCEMENT ---
    if not budget_service.is_allowed(x_app_id):
        with tracer.start_as_current_span("blocked_by_gateway_guardrail") as span:
            span.set_attribute("app.id", x_app_id)
            span.set_attribute("rejection_reason", "429_budget_or_rate_limit")
        
        background_tasks.add_task(
            log_security_alert, x_app_id, "RATE_LIMIT_OR_BUDGET", 
            "Application blocked: Hit Request-Per-Minute limit or monthly budget cap."
        )
        raise HTTPException(
            status_code=429, 
            detail="HTTP 429: Application budget exceeded or rate limit hit. Contact Admin."
        )

    start_time = time.time()
    bypass_cache = x_bypass_cache.lower() in ["true", "1", "yes"]
    
    # --- DYNAMIC CACHE THRESHOLD ---
    cache_threshold = 0.99 if x_request_type.lower() == "agent" else 0.92   
    
    sanitized_messages, entities_found, was_modified = dlp_service.scan_and_redact_messages(payload.messages)
    
    if was_modified:
        background_tasks.add_task(
            log_security_alert, x_app_id, "DLP_INGRESS_INTERCEPT", 
            f"Blocked sensitive PII in user prompt: {', '.join(entities_found)}"
        )

    user_prompt_index = -1
    scrubbed_prompt = ""
    for i in range(len(sanitized_messages) - 1, -1, -1):
        if sanitized_messages[i].role == "user":
            user_prompt_index = i
            scrubbed_prompt = sanitized_messages[i].content
            break

    # --- 3. PROMPT INTELLIGENCE ENGINE (Categorical Engine Update) ---
    category, final_prompt, is_enhanced, issues = await prompt_analyzer.analyze_and_enhance(scrubbed_prompt, x_app_id)
    
    # If the user's prompt is INSUFFICIENT, intercept and return immediately
    if category == "INSUFFICIENT":
        latency_ms = round((time.time() - start_time) * 1000, 2)
        background_tasks.add_task(
            log_transaction_and_routing, x_app_id, "INTERCEPTED", "LOCAL_ENGINE", 0, 0, latency_ms, False, "Prompt Rejected: INSUFFICIENT", False, scrubbed_prompt, final_prompt, category, is_enhanced, issues
        )
        
        return JSONResponse(
            content={
                "id": "chatcmpl-rejected",
                "object": "chat.completion",
                "model": payload.model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Your request lacks context, is too vague, or is repetitive. Please provide a more specific and detailed prompt."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            },
            headers={"X-Proxy-Intercepted": "True"}
        )

    # For NEEDS_CONTEXT or OPTIMAL, replace with enhanced message if applicable
    if is_enhanced and user_prompt_index != -1:
        sanitized_messages[user_prompt_index].content = final_prompt
        
    payload.messages = sanitized_messages

    primary_target, routing_reason = intent_classifier.classify(final_prompt, semantic_cache.embedding_model)

    if not bypass_cache:
        cached_response = semantic_cache.query_cache(
            messages=payload.messages, 
            threshold=cache_threshold, 
            session_id=x_session_id
        )
        if cached_response:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            # Standard Cost Telemetry
            background_tasks.add_task(
                log_transaction_and_routing, x_app_id, primary_target, primary_target, 0, 0, latency_ms, True, "Cache Hit", False, scrubbed_prompt, final_prompt, category, is_enhanced, issues
            )
            
            # --- PATH A STATELESS AUDIT LOGGING (CACHE HIT) ---
            if not opt_out_audit:  # Ensure Privacy Header is respected
                background_tasks.add_task(
                    audit_service.log_interaction,
                    session_id=x_session_id or "stateless-session",
                    app_id=x_app_id,
                    provider="qdrant_cache",
                    model_used=payload.model,
                    messages=payload.model_dump()["messages"],
                    response_text=cached_response,
                    prompt_tokens=0,
                    completion_tokens=0
                )
            
            with tracer.start_as_current_span("semantic_cache_hit") as span:
                span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.LLM.value)
                span.set_attribute(SpanAttributes.LLM_MODEL_NAME, "qdrant_cache")
                span.set_attribute(SpanAttributes.LLM_PROVIDER, "local_cache")
                
                for i, msg in enumerate(payload.messages):
                    span.set_attribute(f"llm.input_messages.{i}.message.role", msg.role)
                    span.set_attribute(f"llm.input_messages.{i}.message.content", msg.content)

                span.set_attribute("llm.output_messages.0.message.role", "assistant")
                span.set_attribute("llm.output_messages.0.message.content", cached_response)

            return JSONResponse(
                content={
                    "id": "chatcmpl-cached",
                    "object": "chat.completion",
                    "model": payload.model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": cached_response}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                },
                headers={"X-Proxy-Cache-Hit": "True", "X-Routed-To": "CACHE"}
            )

    providers_to_try = FALLBACK_PRIORITY.get(primary_target, ["ollama", "groq", "gemini"])
    fallback_used = False
    actual_routing_reason = routing_reason
    
    for attempt_idx, current_provider in enumerate(providers_to_try):
        target_url = PROVIDER_URLS[current_provider]
        headers = get_provider_auth(current_provider)
        current_timeout = PROVIDER_TIMEOUTS.get(current_provider, 30.0)
        
        temp_payload = payload.model_dump()
        if current_provider == "ollama":
            temp_payload["model"] = settings.OLLAMA_MODEL
        elif current_provider == "groq":
            temp_payload["model"] = "llama-3.1-8b-instant" 
        elif current_provider == "gemini":
            temp_payload["model"] = "gemini-1.5-flash"

        if fallback_used:
            actual_routing_reason = f"Fallback trigger (Original target: {primary_target})"

        with tracer.start_as_current_span(f"llm_call_{current_provider}") as span:
            span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.LLM.value)
            span.set_attribute(SpanAttributes.LLM_PROVIDER, current_provider)
            span.set_attribute(SpanAttributes.LLM_MODEL_NAME, temp_payload["model"])
            
            for i, msg in enumerate(temp_payload["messages"]):
                span.set_attribute(f"llm.input_messages.{i}.message.role", msg["role"])
                span.set_attribute(f"llm.input_messages.{i}.message.content", msg["content"])

            async with httpx.AsyncClient(timeout=current_timeout) as client:
                try:
                    response = await client.post(target_url, json=temp_payload, headers=headers)
                    
                    if response.status_code != 200:
                        span.set_attribute("http.status_code", response.status_code)
                        if attempt_idx < len(providers_to_try) - 1:
                            fallback_used = True
                            continue 
                        else:
                            return JSONResponse(content=response.json(), status_code=response.status_code)

                    response_json = response.json()
                    usage = response_json.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    
                    choices = response_json.get("choices", [])
                    assistant_text = ""
                    if choices:
                        raw_assistant_text = choices[0].get("message", {}).get("content", "")
                        
                        assistant_text = dlp_service.scan_and_redact_text(raw_assistant_text)
                        
                        if assistant_text != raw_assistant_text:
                            background_tasks.add_task(
                                log_security_alert, x_app_id, "DLP_EGRESS_INTERCEPT", 
                                "Redacted sensitive PII generated by the LLM before returning to client."
                            )
                        
                        response_json["choices"][0]["message"]["content"] = assistant_text
                        
                        span.set_attribute("llm.output_messages.0.message.role", "assistant")
                        span.set_attribute("llm.output_messages.0.message.content", assistant_text)
                        
                        span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, prompt_tokens)
                        span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, completion_tokens)
                        span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_TOTAL, prompt_tokens + completion_tokens)

                        if assistant_text and not bypass_cache:
                            semantic_cache.update_cache(payload.messages, assistant_text, session_id=x_session_id)

                    latency_ms = round((time.time() - start_time) * 1000, 2)
                    
                    # Standard Cost Telemetry
                    background_tasks.add_task(
                        log_transaction_and_routing, 
                        x_app_id, primary_target, current_provider, prompt_tokens, completion_tokens, latency_ms, False, actual_routing_reason, fallback_used,
                        scrubbed_prompt, final_prompt, category, is_enhanced, issues
                    )

                    # --- PATH A STATELESS AUDIT LOGGING (NETWORK HIT) ---
                    if not opt_out_audit:  # Ensure Privacy Header is respected
                        background_tasks.add_task(
                            audit_service.log_interaction,
                            session_id=x_session_id or "stateless-session",
                            app_id=x_app_id,
                            provider=current_provider,
                            model_used=temp_payload["model"],
                            messages=payload.model_dump()["messages"],
                            response_text=assistant_text,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens
                        )

                    return JSONResponse(
                        content=response_json,
                        status_code=response.status_code,
                        headers={
                            "X-Proxy-Latency-Ms": str(latency_ms),
                            "X-Routed-To": current_provider.upper(),
                            "X-Fallback-Triggered": str(fallback_used)
                        }
                    )

                except httpx.RequestError as exc:
                    span.record_exception(exc)
                    if attempt_idx < len(providers_to_try) - 1:
                        fallback_used = True
                        continue
                    raise HTTPException(status_code=504, detail=f"Network failure on all fallbacks: {str(exc)}")


# --- NATIVE GOOGLE SDK PASSTHROUGH ROUTE (ADK AGENTS) ---
@google_native_router.post("/{api_version}/models/{full_model_path:path}")
async def google_native_passthrough(
    api_version: str,
    full_model_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_app_id: str = Header("adk-default-app", description="Internal app identifier"),
    x_bypass_cache: str = Header("false", description="Skip caching"),
    x_session_id: str = Header(None, description="Unique session ID for agent loop isolation"),
    x_request_type: str = Header("standard", description="Traffic classifier: standard or agent"),
    x_opt_out_audit: str = Header("false", description="Opt out of audit logging")
):
    # Process the opt-out flag securely
    opt_out_audit = x_opt_out_audit.lower() in ["true", "1", "yes"]
    
    if not budget_service.is_allowed(x_app_id):
        background_tasks.add_task(
            log_security_alert, x_app_id, "RATE_LIMIT_OR_BUDGET", 
            "Application blocked: Hit Request-Per-Minute limit or monthly budget cap."
        )
        raise HTTPException(status_code=429, detail="HTTP 429: Application budget exceeded.")

    start_time = time.time()
    raw_payload = await request.json()
    target_url = f"https://generativelanguage.googleapis.com/{api_version}/models/{full_model_path}"
    bypass_cache = x_bypass_cache.lower() in ["true", "1", "yes"]
    cache_threshold = 0.90 if x_request_type.lower() == "agent" else 0.92
    
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY
    }

    # --- 1. EXTRACT NATIVE PAYLOAD FOR PROCESSING ---
    user_text = ""
    try:
        user_text = raw_payload.get("contents", [])[-1].get("parts", [])[0].get("text", "")
    except Exception:
        pass

    is_enhanced = False
    category = "OPTIMAL" # Default category to replace old score variable
    issues = []
    final_prompt = user_text
    scrubbed_prompt = user_text

    if user_text:
        # INGRESS DLP SCAN
        scrubbed_prompt = dlp_service.scan_and_redact_text(user_text)
        if scrubbed_prompt != user_text:
            background_tasks.add_task(
                log_security_alert, x_app_id, "DLP_INGRESS_INTERCEPT", "Blocked sensitive PII in native Google payload."
            )
        
        # PROMPT INTELLIGENCE
        category, final_prompt, is_enhanced, issues = await prompt_analyzer.analyze_and_enhance(scrubbed_prompt, x_app_id)
        
        # RE-INJECT SAFE/ENHANCED TEXT
        try:
            raw_payload["contents"][-1]["parts"][0]["text"] = final_prompt
        except Exception:
            pass

    # --- 2. CACHE CHECK ---
    dummy_messages = [ChatMessage(role="user", content=final_prompt)] if final_prompt else []    
    if not bypass_cache and dummy_messages:
        cached_response = semantic_cache.query_cache(messages=dummy_messages, threshold=cache_threshold, session_id=x_session_id)
        if cached_response:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            background_tasks.add_task(
                log_transaction_and_routing, x_app_id, "gemini", "gemini", 0, 0, latency_ms, True, "Cache Hit", False, scrubbed_prompt, final_prompt, category, is_enhanced, issues
            )
            
            mock_native_response = {
                "candidates": [
                    {
                        "content": {"parts": [{"text": cached_response}], "role": "model"},
                        "finishReason": "STOP"
                    }
                ],
                "usageMetadata": {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0}
            }
            
            return JSONResponse(
                content=mock_native_response,
                headers={"X-Proxy-Cache-Hit": "True", "X-Routed-To": "CACHE", "X-Proxy-Latency-Ms": str(latency_ms)}
            )
    
    # --- 3. NETWORK FORWARDING ---
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(target_url, json=raw_payload, headers=headers)
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            if response.status_code != 200:
                return JSONResponse(content=response.json(), status_code=response.status_code)

            response_json = response.json()
            
            usage = response_json.get("usageMetadata", {})
            prompt_tokens = usage.get("promptTokenCount", 0)
            completion_tokens = usage.get("candidatesTokenCount", 0)
            
            # --- 4. EGRESS DLP SCAN & CACHE UPDATE ---
            raw_assistant_text = ""
            try:
                raw_assistant_text = response_json.get("candidates", [])[0].get("content", {}).get("parts", [])[0].get("text", "")
            except Exception:
                pass

            if raw_assistant_text:
                assistant_text = dlp_service.scan_and_redact_text(raw_assistant_text)
                if assistant_text != raw_assistant_text:
                    background_tasks.add_task(
                        log_security_alert, x_app_id, "DLP_EGRESS_INTERCEPT", "Redacted sensitive PII generated by Gemini."
                    )
                    try:
                        response_json["candidates"][0]["content"]["parts"][0]["text"] = assistant_text
                    except Exception:
                        pass
                
                if not bypass_cache and dummy_messages:
                    semantic_cache.update_cache(dummy_messages, assistant_text, session_id=x_session_id)
            
            background_tasks.add_task(
                log_transaction_and_routing, 
                x_app_id, "gemini", "gemini", prompt_tokens, completion_tokens, latency_ms, False, "Native ADK Passthrough", False, scrubbed_prompt, final_prompt, category, is_enhanced, issues
            )

            # --- STATLESS AUDIT LOGGING FOR NATIVE ROUTE ---
            if not opt_out_audit and dummy_messages: 
                # Convert the dummy ChatMessage object to a dict to match what the audit_service expects
                audit_messages = [{"role": msg.role, "content": msg.content} for msg in dummy_messages]
                
                background_tasks.add_task(
                    audit_service.log_interaction,
                    session_id=x_session_id or "stateless-session",
                    app_id=x_app_id,
                    provider="gemini",
                    model_used=full_model_path,
                    messages=audit_messages,
                    response_text=assistant_text if raw_assistant_text else "",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens
                )

            return JSONResponse(
                content=response_json,
                status_code=response.status_code,
                headers={"X-Proxy-Latency-Ms": str(latency_ms)}
            )
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=504, detail=f"Native Google proxy failure: {str(exc)}")