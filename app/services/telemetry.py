import asyncpg

# Hardcoded DB connection matching our docker-compose.yml setup
DB_DSN = "postgresql://proxy_user:proxy_password@localhost:5433/proxy_db"

async def log_transaction(
    app_id: str,
    target_provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    is_cached: bool
):
    """Asynchronously writes the LLM request metrics to PostgreSQL."""
    try:
        # Establish a quick connection to the database
        conn = await asyncpg.connect(DB_DSN)
        
        # Calculate a rough mock cost (e.g., $0.001 per 1,000 tokens)
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = total_tokens * 0.000001
        
        # Insert the telemetry row
        await conn.execute(
            """
            INSERT INTO llm_transactions 
            (app_id, target_provider, prompt_tokens, completion_tokens, latency_ms, cost_usd, is_cached)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            app_id, target_provider, prompt_tokens, completion_tokens, latency_ms, cost_usd, is_cached
        )
        
        # Close the connection
        await conn.close()
    except Exception as e:
        print(f"Telemetry logging failed: {e}")