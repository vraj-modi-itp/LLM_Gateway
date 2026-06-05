import requests
import time
import copy

PROXY_URL = "http://localhost:8000/v1/chat/completions"

# Base headers required to pass governance/guardrails
BASE_HEADERS = {
    "x-app-id": "qa-routing-tester",
    "Content-Type": "application/json",
    "x-bypass-cache": "true" # Critical: Prevents cache hits from masking the routing test
}

def send_test_request(test_name: str, prompt: str, extra_headers: dict = None):
    print(f"\n{'='*60}")
    print(f"🚀 RUNNING TEST: {test_name}")
    print(f"{'='*60}")
    
    headers = copy.deepcopy(BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
        print(f"📝 Injecting Headers: {extra_headers}")
        
    payload = {
        "model": "default", # The proxy should override this if x-force-model is provided
        "messages": [{"role": "user", "content": prompt}]
    }
    
    start_time = time.time()
    try:
        response = requests.post(PROXY_URL, json=payload, headers=headers)
        latency = round((time.time() - start_time) * 1000, 2)
        
        if response.status_code == 200:
            data = response.json()
            routed_to = response.headers.get("X-Routed-To", "UNKNOWN")
            model_used = data.get("model", "unknown")
            answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().replace("\n", " ")
            
            print(f"✅ Success ({latency}ms)")
            print(f"🔀 Routed To  : {routed_to.upper()}")
            print(f"🧠 Model Used : {model_used}")
            print(f"🤖 Response   : {answer[:100]}...")
        else:
            print(f"❌ Failed with Status: {response.status_code} ({latency}ms)")
            print(f"🔍 Error Details: {response.text}")
            
    except Exception as e:
        print(f"❌ Connection Error: {e}")

# ==============================================================================
# TEST SUITE
# ==============================================================================

# TEST 1: Baseline Semantic Routing (No overrides)
# The prompt is a simple fact question, so the semantic router should pick OLLAMA.
send_test_request(
    test_name="1. Baseline Semantic Routing",
    prompt="What is the capital of France?"
)

# TEST 2: Force Groq & Llama 3
# We ask a simple question but force it to Groq's high-speed model.
send_test_request(
    test_name="2. Explicit Override -> Groq (llama-3.1-8b-instant)",
    prompt="What is the capital of France?",
    extra_headers={
        "x-force-provider": "groq",
        "x-force-model": "llama-3.1-8b-instant"
    }
)

# TEST 3: Force Gemini & Flash
# We ask a coding question (which normally routes to Groq) but force it to Gemini.
send_test_request(
    test_name="3. Explicit Override -> Gemini (gemini-1.5-flash)",
    prompt="Write a simple python hello world script.",
    extra_headers={
        "x-force-provider": "gemini",
        "x-force-model": "gemini-3.1-flash-lite"
    }
)

# TEST 4: Invalid Provider Guardrail
# Test the defensive programming logic we added for bad headers.
send_test_request(
    test_name="4. Error Handling -> Invalid Provider Name",
    prompt="Hello!",
    extra_headers={
        "x-force-provider": "anthropic", # Does not exist in PROVIDER_URLS
        "x-force-model": "claude-3-haiku"
    }
)