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
        print("🏗️ Creating 'app_budgets' table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS app_budgets (
                app_id VARCHAR(100) PRIMARY KEY,
                monthly_token_limit INT DEFAULT 1000000,
                monthly_cost_limit_usd FLOAT DEFAULT 50.0,
                current_month_tokens INT DEFAULT 0,
                current_month_cost FLOAT DEFAULT 0.0,
                is_blocked BOOLEAN DEFAULT FALSE,
                last_reset_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        print("🏗️ Creating 'alerts' table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                alert_type VARCHAR(50),
                app_id VARCHAR(100),
                message TEXT,
                fired_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                acknowledged BOOLEAN DEFAULT FALSE
            );
        """)
        
        print("✅ Database migration complete! All tables are ready.")
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(setup_database())