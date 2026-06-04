import asyncio
import asyncpg
from dotenv import load_dotenv

# Load the environment variables
load_dotenv()

DB_DSN = "postgresql://proxy_user:proxy_password@localhost:5433/proxy_db"

async def setup_database():
    print("🔌 Connecting to PostgreSQL...")
    conn = await asyncpg.connect(DB_DSN)
    
    try:
        print("🏗️ Creating 'audit_chat_history' table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_chat_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id VARCHAR(255) NOT NULL,
                app_id VARCHAR(100) NOT NULL,
                provider VARCHAR(50) NOT NULL,
                model_used VARCHAR(100) NOT NULL,
                prompt_tokens INT DEFAULT 0,
                completion_tokens INT DEFAULT 0,
                messages JSONB NOT NULL,
                response TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        print("🏗️ Creating indexes for 'audit_chat_history'...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_chat_history(session_id);
            CREATE INDEX IF NOT EXISTS idx_audit_app ON audit_chat_history(app_id);
        """)
        
        print("✅ Database migration complete! Audit table is ready.")
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(setup_database())