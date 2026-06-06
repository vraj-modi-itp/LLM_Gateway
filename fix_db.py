import asyncio
import asyncpg
from dotenv import load_dotenv

# Load your environment variables just in case
load_dotenv()

# We use port 5433 as you mentioned in your STEPS_TO_RUN.md
DB_DSN = "postgresql://proxy_user:proxy_password@localhost:5433/proxy_db"

async def fix_database():
    print("🔌 Connecting to Postgres...")
    conn = await asyncpg.connect(DB_DSN)
    
    try:
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
        
        # Turn the feature ON by default
        await conn.execute("""
            INSERT INTO gateway_feature_flags (flag_name, is_enabled, description)
            VALUES ('prompt_intelligence_enabled', TRUE, 'Global master switch')
            ON CONFLICT (flag_name) DO NOTHING;
        """)

        print("🏗️ Creating 'dynamic_blacklist' table for the background learning...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dynamic_blacklist (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                original_word VARCHAR(255) UNIQUE NOT NULL,
                mask_tag VARCHAR(100) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Add a test word so the fast-map has something to load
        await conn.execute("""
            INSERT INTO dynamic_blacklist (original_word, mask_tag) 
            VALUES ('Intuitive.AI', '[COMPANY_NAME]') 
            ON CONFLICT DO NOTHING;
        """)
        
        print("✅ Database is fully updated! You are ready to go.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_database())