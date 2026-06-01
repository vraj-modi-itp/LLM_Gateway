import requests
import time

PROXY_URL = "http://localhost:8000/v1/chat/completions"
HEADERS = {
    "x-app-id": "test-script-v1",
    "X-Target-Provider": "groq", # We will route to Groq for speed
    "Content-Type": "application/json"
}

def send_request(prompt_text, test_name):
    print(f"\n--- Running Test: {test_name} ---")
    payload = {
        "model": "llama-3.1-8b-instant", # Dummy model name, Groq will handle it
        "messages": [{"role": "user", "content": prompt_text}]
    }
    
    start = time.time()
    response = requests.post(PROXY_URL, json=payload, headers=HEADERS)
    end = time.time()
    
    if response.status_code == 200:
        data = response.json()
        headers = response.headers
        
        print(f"🤖 LLM Answer: {data['choices'][0]['message']['content'][:100]}...")
        print(f"⏱️ Client-side Latency: {round((end - start) * 1000, 2)} ms")
        print(f"📊 Proxy Latency Header: {headers.get('X-Proxy-Latency-Ms')} ms")
        print(f"🪙 Proxy Token Header: {headers.get('X-Proxy-Total-Tokens')}")
        print(f"⚡ Proxy Cache Hit Header: {headers.get('X-Proxy-Cache-Hit')}")
    else:
        print(f"❌ Request failed: {response.status_code}")
        print(response.text)

# Test 1: The Initial Request (Should be a Cache Miss)
send_request("Explain the theory of relativity in one sentence.", "1. First Request (Cache Miss)")

# Test 2: The Exact Duplicate (Should be a Cache Hit)
send_request("Explain the theory of relativity in one sentence.", "2. Duplicate Request (Cache Hit)")

# Test 3: The PII Leak (Should be Redacted before hitting LLM)
send_request("My name is John Doe and my phone number is 555-0198. Please repeat my phone number back to me.", "3. DLP Security Test")