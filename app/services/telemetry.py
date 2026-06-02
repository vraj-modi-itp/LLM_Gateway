import asyncpg
import asyncio
from typing import Dict

DB_DSN = "postgresql://proxy_user:proxy_password@localhost:5433/proxy_db"

# In-Memory Registry to hold rolling averages
PROVIDER_REGISTRY: Dict[str, Dict[str, float]] = {
    "groq": {"avg_latency": 0.0, "avg_cost": 0.0},
    "gemini": {"avg_latency": 0.0, "avg_cost": 0.0},
    "ollama": {"avg_latency": 0.0, "avg_cost": 0.0} 
}

async def refresh_provider_metrics():
    """Background task that runs every 60 seconds to update average latencies."""
    while True:
        try:
            conn = await asyncpg.connect(DB_DSN)
            rows = await conn.fetch("""
                WITH recent_tx AS (
                    SELECT routed_to, latency_ms, cost_usd,
                           ROW_NUMBER() OVER(PARTITION BY routed_to ORDER BY created_at DESC) as rn
                    FROM llm_transactions
                    WHERE is_cached = false AND routed_to IS NOT NULL
                )
                SELECT routed_to, AVG(latency_ms) as avg_latency, AVG(cost_usd) as avg_cost
                FROM recent_tx
                WHERE rn <= 100
                GROUP BY routed_to;
            """)
            
            for row in rows:
                provider = row['routed_to']
                if provider in PROVIDER_REGISTRY:
                    PROVIDER_REGISTRY[provider]['avg_latency'] = row['avg_latency'] or 0.0
                    PROVIDER_REGISTRY[provider]['avg_cost'] = row['avg_cost'] or 0.0
                    
            await conn.close()
        except Exception as e:
            print(f"Metrics refresh failed: {e}")
            
        await asyncio.sleep(60)

async def log_transaction_and_routing(
    app_id: str,
    target_provider: str,
    routed_to: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    is_cached: bool,
    routing_reason: str,
    fallback_used: bool
):
    """Logs the transaction AND the routing decision in one go."""
    try:
        conn = await asyncpg.connect(DB_DSN)
        
        cost_usd = 0.0
        if routed_to != "ollama" and not is_cached:
            cost_usd = (prompt_tokens + completion_tokens) * 0.000001
            
        tx_id = await conn.fetchval(
            """
            INSERT INTO llm_transactions 
            (app_id, target_provider, routed_to, prompt_tokens, completion_tokens, latency_ms, cost_usd, is_cached)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            app_id, target_provider, routed_to, prompt_tokens, completion_tokens, latency_ms, cost_usd, is_cached
        )
        
        if tx_id:
            await conn.execute(
                """
                INSERT INTO routing_decisions (transaction_id, selected_provider, reason, fallback_used)
                VALUES ($1, $2, $3, $4)
                """,
                tx_id, routed_to, routing_reason, fallback_used
            )
            
        await conn.close()
    except Exception as e:
        print(f"Telemetry logging failed: {e}")