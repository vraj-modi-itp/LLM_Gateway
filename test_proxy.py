import requests
import time
import copy
import uuid

PROXY_URL = "http://localhost:8000/v1/chat/completions"

BASE_HEADERS = {
    "x-app-id": "qa-stress-test-v3",
    "Content-Type": "application/json"
}

def send_request(prompt_text, test_name, extra_headers=None):
    print(f"\n{'='*60}")
    print(f"🚀 RUNNING TEST: {test_name}")
    print(f"{'='*60}")
    
    headers = copy.deepcopy(BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
        print(f"📝 Injecting Custom Headers: {extra_headers}")
    
    payload = {
        "model": "default", 
        "messages": [{"role": "user", "content": prompt_text}]
    }
    
    start = time.time()
    try:
        response = requests.post(PROXY_URL, json=payload, headers=headers)
        end = time.time()
        
        if response.status_code == 200:
            data = response.json()
            resp_headers = response.headers
            
            # Print a snippet of the response safely
            choices = data.get('choices', [])
            if choices:
                answer = choices[0].get('message', {}).get('content', '').strip().replace('\n', ' ')
                print(f"🤖 LLM Answer: {answer}")
            else:
                print("🤖 LLM Answer: [Empty/Malformed]")
            
            # Print telemetry
            print(f"\n📊 --- Telemetry ---")
            print(f"⏱️ Latency        : {round((end - start) * 1000, 2)} ms")
            print(f"⚡ Cache Hit      : {resp_headers.get('X-Proxy-Cache-Hit', 'False')}")
            print(f"🔀 Routed To      : {resp_headers.get('X-Routed-To', 'UNKNOWN').upper()}")
            print(f"🛡️ Fallback Used  : {resp_headers.get('X-Fallback-Triggered', 'False')}")
            
        else:
            print(f"❌ Request failed with status: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Is the FastAPI proxy running on port 8000?")

# ==============================================================================
# PHASE 1: SEMANTIC ROUTING BOUNDARIES
# ==============================================================================

# send_request(
#     "Name the capital city of Australia. Answer in one word.", 
#     "1. Low-Stakes Routing (Expect: OLLAMA)"
# )

# send_request(
#     "Write a SQL query to join the users and orders tables where order_total > 100.", 
#     "2. Explicit Code Intent (Expect: GROQ)"
# )

# send_request(
#     "Can you explain the history of object-oriented programming? I don't need code, just the philosophy.",
#     "3. Nuanced Code Intent (Expect: GROQ - Semantic router should catch this via centroid)"
# )

# # ==============================================================================
# # PHASE 2: ADVANCED CACHE MANIPULATION
# # ==============================================================================
# time.sleep(1) # Let Qdrant index Test 2

# send_request(
#     "Write a SQL query to join the users and orders tables where order_total > 100.", 
#     "4. Exact Cache Match (Expect: CACHE HIT)"
# )

# send_request(
#     "Create a SQL query that joins the orders and users tables where the total is greater than 100.", 
#     "5. Semantic Cache Match (Expect: CACHE HIT - Different words, same meaning!)"
# )

# send_request(
#     "Write a SQL query to join the users and orders tables where order_total > 100.", 
#     "6. Cache Bypass Header (Expect: GROQ - Forced Network Call)",
#     extra_headers={"x-bypass-cache": "true"}
# )

# # ==============================================================================
# # PHASE 3: DLP & SECURITY INTERSECTIONS
# # ==============================================================================

# send_request(
#     "Please update my file. My SSN is 111-22-3333, my phone is 555-0199, and my card is 4111-1111-1111-1111.", 
#     "7. Multi-Entity PII Attack (Expect: Redaction of all 3 entities)"
# )

# time.sleep(1)

# # Here we send a completely DIFFERENT SSN, Phone, and Card. 
# # BUT because Presidio redacts them into <US_SSN>, <PHONE_NUMBER>, etc. BEFORE hitting the cache,
# # the cache should actually see this as an EXACT MATCH to Test 7!
# send_request(
#     "Please update my file. My SSN is 999-88-7777, my phone is 555-0987, and my card is 5555-4444-3333-2222.", 
#     "8. DLP + Cache Intersection (Expect: CACHE HIT on redacted template!)"
# )

# # ==============================================================================
# # PHASE 4: PAYLOAD & LIMIT STRESS TESTS
# # ==============================================================================

# send_request(
#     "   \n  \t  ", 
#     "9. Empty / Whitespace Prompt (Expect: Graceful handling by default route)"
# )

# # Generate a prompt that is EXACTLY 750 words (under the 800 limit)
# long_text = "apple " * 750
# send_request(
#     long_text, 
#     "10. High-Volume Standard Routing (Expect: Semantic router decides - likely OLLAMA/GEMINI)"
# )

# # Generate a prompt that is EXACTLY 810 words (over the 800 limit)
# massive_text = "apple " * 810
# send_request(
#     massive_text, 
#     "11. Hard Limit Override Routing (Expect: Forced to GEMINI due to >800 word count)"
# )

# ==============================================================================
# PHASE 5: PROMPT INTELLIGENCE & AUTO-ENHANCEMENT
# ==============================================================================

send_request(
    "build me something cool i need it fast just do it for me", 
    "12. The Rambling Wall (Expect: Low Score, Auto-Enhanced with Context)",
    extra_headers={"x-app-id": "qa-stress-test-v3", "x-bypass-cache": "true"}
)

send_request(
    "Write SQL query joining users and orders.", 
    "13. Short But Perfect (Expect: Max Score, No Enhancement needed)",
    extra_headers={"x-bypass-cache": "true"}
)

# Demonstrating PII Masking + Enhancement Pipeline Safety
send_request(
    "email the report to ceo@intuitive.ai and make sure it looks good", 
    "14. DLP + Enhancement Safety (Expect: Email redacted BEFORE enhancement injection)",
    extra_headers={"x-app-id": "sales_assistant", "x-bypass-cache": "true"}
)

# ==============================================================================
# PHASE 6: SESSION ISOLATION & DYNAMIC THRESHOLDS (ReAct Agent Loop Fix)
# ==============================================================================

agent_session = str(uuid.uuid4())
print(f"\n[+] Starting simulated Agent Run with Session ID: {agent_session}")

send_request(
    "Calculate the square root of 144.", 
    "15. Agent Step 1 (Expect: NETWORK MISS, saves to Qdrant with Session ID)",
    extra_headers={
        "x-request-type": "agent", 
        "x-session-id": agent_session
    }
)

time.sleep(1) # Let Qdrant index

send_request(
    "Calculate the square root of 144.\nThought: The answer is 12.\nAction: Verify.", 
    "16. Agent Step 2 (Expect: NETWORK MISS. Blocked from hitting Step 1 by Session Isolation!)",
    extra_headers={
        "x-request-type": "agent", 
        "x-session-id": agent_session
    }
)

new_user_session = str(uuid.uuid4())
print(f"\n[+] Starting NEW run tomorrow with Session ID: {new_user_session}")

send_request(
    "Calculate the square root of 144.", 
    "17. New User Request (Expect: CACHE HIT. Allowed to pull from previous isolated sessions)",
    extra_headers={
        "x-request-type": "standard", 
        "x-session-id": new_user_session
    }
)