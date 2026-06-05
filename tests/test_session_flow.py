import asyncio
import uuid
import json
import os
import httpx
import asyncpg

# --- Configuration ---
GATEWAY_URL = "http://localhost:8000/v1/chat/completions"
DB_DSN = "postgresql://proxy_user:proxy_password@127.0.0.1:5433/proxy_db"
APP_ID = "session_flow_tester"

# Generate ONE persistent session ID for the entire conversation
EXPLICIT_SESSION_ID = f"explicit-session-{uuid.uuid4().hex[:8]}"

async def main():
    print(f"🔄 STARTING SESSION TEST | Session ID: {EXPLICIT_SESSION_ID}")
    
    chat_history = []
    prompts = [
        "Hi, what is the capital city of France?",
        "What is the most famous museum in that city?"
    ]
    
    async with httpx.AsyncClient() as client:
        for i, user_msg in enumerate(prompts, 1):
            print(f"\n💬 [Turn {i}] User: {user_msg}")
            chat_history.append({"role": "user", "content": user_msg})
            
            payload = {"model": "llama-3.1-8b-instant", "messages": chat_history}
            headers = {
                "x-app-id": APP_ID,
                "x-session-id": EXPLICIT_SESSION_ID,  # EXPLICITLY SENT
                "x-bypass-cache": "true",
                "Content-Type": "application/json"
            }
            
            res = await client.post(GATEWAY_URL, json=payload, headers=headers, timeout=15.0)
            assistant_reply = res.json()["choices"][0]["message"]["content"]
            print(f"🤖 [Turn {i}] Assistant: {assistant_reply.strip()}")
            
            chat_history.append({"role": "assistant", "content": assistant_reply})
            await asyncio.sleep(1) # Breathe between network requests

    print("\n🔍 VERIFYING DATABASE (Expecting multiple snapshots under ONE Session ID)")
    await asyncio.sleep(1.5) # Wait for background tasks to finish writing
    
    conn = await asyncpg.connect(DB_DSN)
    rows = await conn.fetch("SELECT session_id, messages FROM audit_chat_history WHERE session_id = $1 ORDER BY created_at ASC", EXPLICIT_SESSION_ID)
    
    print(f"✅ Found {len(rows)} database snapshots for {EXPLICIT_SESSION_ID}")
    for idx, row in enumerate(rows, 1):
        msg_count = len(json.loads(row['messages']))
        print(f"   Snapshot {idx} -> Contained {msg_count} messages in history array.")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())