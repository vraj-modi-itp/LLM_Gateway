import asyncio
import uuid
import os
import httpx
import asyncpg

# --- Configuration ---
GATEWAY_URL = "http://localhost:8000/v1/chat/completions"
DB_DSN = "postgresql://proxy_user:proxy_password@127.0.0.1:5433/proxy_db"

# We use a unique App ID just for this test so it's easy to query the database afterwards
UNIQUE_APP_ID = f"stateless_tester_{uuid.uuid4().hex[:4]}"

async def main():
    print(f"🚀 STARTING STATELESS TEST | App ID: {UNIQUE_APP_ID}")
    print("Sending 3 independent requests WITHOUT a session ID...\n")
    
    prompts = [
        "Tell me a one-line joke.",
        "What is 10 + 10?",
        "Translate 'Hello' to Spanish."
    ]
    
    async with httpx.AsyncClient() as client:
        for i, user_msg in enumerate(prompts, 1):
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": user_msg}]
            }
            
            # NOTICE: x-session-id IS INTENTIONALLY MISSING
            headers = {
                "x-app-id": UNIQUE_APP_ID,
                "x-bypass-cache": "true",
                "Content-Type": "application/json"
            }
            
            print(f"📤 Dispatching Request {i}...")
            await client.post(GATEWAY_URL, json=payload, headers=headers, timeout=15.0)

    print("\n🔍 VERIFYING DATABASE (Expecting 3 completely different Session IDs)")
    await asyncio.sleep(1.5) # Wait for background tasks to finish writing
    
    conn = await asyncpg.connect(DB_DSN)
    # Fetch all rows for this specific test App ID
    rows = await conn.fetch("SELECT session_id, response FROM audit_chat_history WHERE app_id = $1 ORDER BY created_at ASC", UNIQUE_APP_ID)
    
    print(f"✅ Found {len(rows)} database records for {UNIQUE_APP_ID}:")
    for row in rows:
        print(f"   Generated Session ID: [{row['session_id']}] -> Output snippet: '{row['response'][:30]}...'")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())