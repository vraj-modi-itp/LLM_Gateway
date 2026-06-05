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
        # --- EXISTING TABLES ---
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
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_chat_history(session_id);
            CREATE INDEX IF NOT EXISTS idx_audit_app ON audit_chat_history(app_id);
        """)

        # --- NEW CHANGE 1 TABLES & COLUMNS ---
        print("🏗️ Creating 'gateway_feature_flags' table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gateway_feature_flags (
                flag_name VARCHAR(100) PRIMARY KEY,
                is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                description TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                updated_by VARCHAR(100) DEFAULT 'system'
            );
        """)
        
        print("🌱 Seeding Prompt Intelligence Master Switch...")
        await conn.execute("""
            INSERT INTO gateway_feature_flags (flag_name, is_enabled, description)
            VALUES ('prompt_intelligence_enabled', TRUE, 
                    'Global master switch for Prompt Intelligence Engine. When FALSE, all apps skip PI regardless of per-app setting.')
            ON CONFLICT (flag_name) DO NOTHING;
        """)

        print("🏗️ Modifying 'app_budgets' table with PI override flag...")
        await conn.execute("""
            ALTER TABLE app_budgets
            ADD COLUMN IF NOT EXISTS pi_enabled BOOLEAN DEFAULT NULL;
        """)

        print("🏗️ Modifying 'llm_transactions' table with telemetry tracking...")
        # Note: Fails silently if llm_transactions doesn't exist yet, but ensures schema safety
        await conn.execute("""
            ALTER TABLE llm_transactions
            ADD COLUMN IF NOT EXISTS pi_was_run BOOLEAN DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS pi_category VARCHAR(20) DEFAULT NULL;
        """)
        
        print("✅ Database migration complete! Audit and Feature Flag tables are ready.")
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(setup_database())