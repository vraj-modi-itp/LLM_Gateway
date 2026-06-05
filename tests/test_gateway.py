import requests
import time
import copy

PROXY_URL = "http://localhost:8000/v1/chat/completions"
ADMIN_URL = "http://localhost:8000/admin/flags/prompt_intelligence_enabled"
ADMIN_KEY = "your_super_secret_admin_password" # Make sure this matches your .env

BASE_HEADERS = {
    "x-app-id": "test-app-1",
    "Content-Type": "application/json",
    "x-bypass-cache": "true"
}

def send_chat_request(test_name):
    print(f"\n🚀 {test_name}")
    payload = {
        "model": "gemini-1.5-flash", 
        "messages": [{"role": "user", "content": "Explain quantum computing in one sentence."}]
    }
    
    start = time.time()
    try:
        response = requests.post(PROXY_URL, json=payload, headers=BASE_HEADERS)
        end = time.time()
        
        if response.status_code == 200:
            print(f"⏱️ Latency        : {round((end - start) * 1000, 2)} ms")
            print(f"🔀 Routed To      : {response.headers.get('X-Routed-To', 'UNKNOWN').upper()}")
        else:
            print(f"❌ Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

def toggle_kill_switch(is_enabled):
    print(f"\n[!] ADMIN ACTION: Setting Prompt Intelligence ENABLED = {is_enabled}")
    admin_headers = {"Content-Type": "application/json", "x-admin-key": ADMIN_KEY}
    payload = {"is_enabled": is_enabled, "updated_by": "Local Dev"}
    
    requests.post(ADMIN_URL, json=payload, headers=admin_headers)

# ==============================================================================
# THE TEST RUN
# ==============================================================================

# 1. Baseline: Should take ~300ms
send_chat_request("Test 1: Baseline (PI Engine Active)")

# 2. Disable via Admin API
toggle_kill_switch(False)
print("⏳ Waiting 32 seconds for TTL Cache to expire...")
time.sleep(32)

# 3. Bypassed: Should drop to ~70ms
send_chat_request("Test 2: Bypassed (PI Engine Disabled)")

# 4. Clean up: Turn it back on so your local environment isn't permanently broken
toggle_kill_switch(True)
print("✅ Test complete. PI Engine restored to normal.")