import requests
import time

PROXY_URL = "http://localhost:8000/v1/chat/completions"

# Notice we removed "X-Target-Provider". The proxy is smart now!
HEADERS = {
    "x-app-id": "test-script-v2",
    "Content-Type": "application/json"
}

def send_request(prompt_text, test_name):
    print(f"\n{'='*50}")
    print(f"🚀 RUNNING TEST: {test_name}")
    print(f"{'='*50}")
    
    payload = {
        "model": "default", # The proxy dynamically overrides this based on the target
        "messages": [{"role": "user", "content": prompt_text}]
    }
    
    start = time.time()
    try:
        response = requests.post(PROXY_URL, json=payload, headers=HEADERS)
        end = time.time()
        
        if response.status_code == 200:
            data = response.json()
            headers = response.headers
            
            # Print a snippet of the response
            answer = data['choices'][0]['message']['content'].strip().replace('\n', ' ')
            print(f"🤖 LLM Answer: {answer[:100]}...")
            
            # Print our custom proxy headers
            print(f"\n📊 --- Telemetry ---")
            print(f"⏱️ Client Latency : {round((end - start) * 1000, 2)} ms")
            print(f"⚡ Cache Hit      : {headers.get('X-Proxy-Cache-Hit', 'False')}")
            print(f"🔀 Routed To      : {headers.get('X-Routed-To', 'UNKNOWN').upper()}")
            print(f"🛡️ Fallback Used  : {headers.get('X-Fallback-Triggered', 'False')}")
            
        else:
            print(f"❌ Request failed with status: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Is the FastAPI proxy running on port 8000?")

# ---------------------------------------------------------
# EDGE CASE 1: Standard/Simple Request -> Should hit Ollama
# ---------------------------------------------------------
send_request(
    "Name the capital city of Japan. Answer in one word.", # Changed from France to Japan
    "1. Low-Stakes Routing (Expect: OLLAMA)"
)

# ---------------------------------------------------------
# EDGE CASE 2: Code Generation -> Should hit Groq
# ---------------------------------------------------------
send_request(
    "Write a javascript function to sort an array of numbers. Do not explain, just code.", # Changed to Javascript
    "2. Code Intent Routing (Expect: GROQ)"
)

# ---------------------------------------------------------
# EDGE CASE 3: Cache Hit Validation -> Should bypass network
# ---------------------------------------------------------
time.sleep(1) 
send_request(
    "Write a javascript function to sort an array of numbers. Do not explain, just code.", 
    "3. Exact Duplicate (Expect: CACHE HIT)"
)

# ---------------------------------------------------------
# EDGE CASE 4: Large Context Window -> Should hit Gemini
# ---------------------------------------------------------
massive_prompt = "Please summarize this text: " + ("A completely different random sentence about cats. " * 150)
send_request(
    massive_prompt, 
    "4. Large Context Routing (Expect: GEMINI)"
)

# ---------------------------------------------------------
# EDGE CASE 5: DLP Security / PII Leak
# ---------------------------------------------------------
send_request(
    "My email address is secret.ceo@company.com. Please confirm you received this email.", 
    "5. DLP Security Redaction"
)