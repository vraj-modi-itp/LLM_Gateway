import time
import re
import numpy as np
from typing import List, Tuple, Dict
from fastapi import APIRouter, Header, HTTPException, status, BackgroundTasks
from fastapi.responses import ORJSONResponse
import httpx

from app.api.schemas import ChatCompletionRequest, ChatMessage
from app.core.config import settings
from app.services.dlp import dlp_service
from app.services.cache import semantic_cache
from app.services.telemetry import log_transaction_and_routing
from app.services.prompt_analyzer import prompt_analyzer  # NEW IMPORT

router = APIRouter(prefix="/v1")

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

# ==========================================
# 🧠 THE SEMANTIC ROUTER ENGINE
# ==========================================

ROUTE_EXAMPLES = {
    "groq": [
        "Write a python function to reverse a string.",
        "How do I fix a NullPointerException in Java?",
        "Create a React component for a dropdown menu.",
        "Debug this SQL query, it's running too slow.",
        "What is the difference between an interface and abstract class?",
        "Write a bash script to parse these logs.",
        "How to center a div using CSS flexbox?",
        "Convert this JSON object into a TypeScript interface.",
        "Explain how garbage collection works in Go.",
        "Write a regex to match an email address."
    ],
    "gemini": [
        "Summarize this 20-page document on monetary policy.",
        "Analyze the themes of isolation in Mary Shelley's Frankenstein.",
        "Compare and contrast the economic impacts of the Industrial Revolution.",
        "Write a comprehensive essay on the history of the Roman Empire.",
        "Extract all the key arguments from this legal transcript.",
        "Review this entire codebase and write documentation for it.",
        "Draft a 5-page research proposal on quantum computing.",
        "Synthesize these five articles into a literature review.",
        "Evaluate the strategic business plan for market expansion.",
        "Generate a detailed chapter-by-chapter outline for a fantasy novel."
    ],
    "ollama": [
        "What is the capital of France?",
        "Who wrote the play Hamlet?",
        "Tell me a joke about a programmer.",
        "What are the ingredients for a chocolate cake?",
        "Write a short polite email declining a meeting.",
        "How far is the moon from the Earth?",
        "Translate 'hello' into Spanish.",
        "Give me a 3-day itinerary for a trip to Rome.",
        "What is the meaning of life?",
        "Recommend a good sci-fi movie."
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

@router.post("/chat/completions", response_class=ORJSONResponse)
async def proxy_chat_completion(
    payload: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    x_app_id: str = Header(..., description="Internal app identifier"),
    x_bypass_cache: str = Header("false", description="Skip caching") 
):
    start_time = time.time()
    bypass_cache = x_bypass_cache.lower() in ["true", "1", "yes"]
    
    # 1. DLP Security Scan (PII is scrubbed BEFORE prompt intelligence)
    sanitized_messages, entities_found, was_modified = dlp_service.scan_and_redact_messages(payload.messages)
    
    # Extract the user prompt from the sanitized list
    user_prompt_index = -1
    original_user_prompt = ""
    for i in range(len(sanitized_messages) - 1, -1, -1):
        if sanitized_messages[i].role == "user":
            user_prompt_index = i
            original_user_prompt = sanitized_messages[i].content
            break

    # 2. 🧠 Prompt Intelligence Engine (NEW)
    score, final_prompt, is_enhanced, issues = prompt_analyzer.analyze_and_enhance(original_user_prompt, x_app_id)
    
    # Inject enhanced prompt back into payload if modified
    if is_enhanced and user_prompt_index != -1:
        sanitized_messages[user_prompt_index].content = final_prompt
        
    payload.messages = sanitized_messages

    # 3. Intelligent Intent Classification
    primary_target, routing_reason = intent_classifier.classify(final_prompt, semantic_cache.embedding_model)

    # 4. Cache Check
    if not bypass_cache:
        cached_response = semantic_cache.query_cache(payload.messages, threshold=0.95)
        if cached_response:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            background_tasks.add_task(
                log_transaction_and_routing, x_app_id, primary_target, primary_target, 0, 0, latency_ms, True, "Cache Hit", False, original_user_prompt, final_prompt, score, is_enhanced, issues
            )
            return ORJSONResponse(
                content={
                    "id": "chatcmpl-cached",
                    "object": "chat.completion",
                    "model": payload.model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": cached_response}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                },
                headers={"X-Proxy-Cache-Hit": "True", "X-Routed-To": "CACHE"}
            )

    # 5. Resilient Network Forwarding Loop
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

        async with httpx.AsyncClient(timeout=current_timeout) as client:
            try:
                response = await client.post(target_url, json=temp_payload, headers=headers)
                
                if response.status_code != 200:
                    if attempt_idx < len(providers_to_try) - 1:
                        fallback_used = True
                        continue 
                    else:
                        return ORJSONResponse(content=response.json(), status_code=response.status_code)

                response_json = response.json()
                usage = response_json.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                
                choices = response_json.get("choices", [])
                if choices:
                    assistant_text = choices[0].get("message", {}).get("content", "")
                    if assistant_text and not bypass_cache:
                        semantic_cache.update_cache(payload.messages, assistant_text)

                latency_ms = round((time.time() - start_time) * 1000, 2)
                
                background_tasks.add_task(
                    log_transaction_and_routing, 
                    x_app_id, primary_target, current_provider, prompt_tokens, completion_tokens, latency_ms, False, actual_routing_reason, fallback_used,
                    original_user_prompt, final_prompt, score, is_enhanced, issues
                )

                return ORJSONResponse(
                    content=response_json,
                    status_code=response.status_code,
                    headers={
                        "X-Proxy-Latency-Ms": str(latency_ms),
                        "X-Routed-To": current_provider.upper(),
                        "X-Fallback-Triggered": str(fallback_used)
                    }
                )

            except httpx.RequestError as exc:
                if attempt_idx < len(providers_to_try) - 1:
                    fallback_used = True
                    continue
                raise HTTPException(status_code=504, detail=f"Network failure on all fallbacks: {str(exc)}")