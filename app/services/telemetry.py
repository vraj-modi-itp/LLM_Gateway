import os
import asyncio
import asyncpg
from uuid import uuid4
from typing import Dict, List
from dotenv import load_dotenv

# Force load environment variables
load_dotenv()

DB_DSN = os.getenv("DB_DSN", "postgresql://proxy_user:proxy_password@localhost:5433/proxy_db")

# In-Memory Registry to hold rolling averages for routing decisions
PROVIDER_REGISTRY: Dict[str, Dict[str, float]] = {
    "groq": {"avg_latency": 0.0, "avg_cost": 0.0},
    "gemini": {"avg_latency": 0.0, "avg_cost": 0.0},
    "ollama": {"avg_latency": 0.0, "avg_cost": 0.0} 
}

# Approximate pricing per 1 million tokens for cost calculation
PRICING = {
    "groq": {"input": 0.05 / 1_000_000, "output": 0.08 / 1_000_000},
    "gemini": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "ollama": {"input": 0.0, "output": 0.0}
}

async def refresh_provider_metrics():
    """Background task that runs every 60 seconds to update average latencies and costs."""
    print("🔄 Starting background provider metrics refresh loop...")
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
            print(f"[-] Metrics refresh failed: {e}")
            
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
    fallback_used: bool,
    original_prompt: str = "",
    enhanced_prompt: str = "",
    prompt_score: float = 0.0,
    is_enhanced: bool = False,
    detected_issues: List[str] = None
):
    """Logs the transaction, routing decision, prompt intelligence, and deducts budgets atomically."""
    if detected_issues is None:
        detected_issues = []
        
    # Calculate exact USD costs based on token consumption
    provider_rates = PRICING.get(routed_to, {"input": 0.0, "output": 0.0})
    cost_usd = 0.0
    if not is_cached:
        cost_usd = (prompt_tokens * provider_rates["input"]) + (completion_tokens * provider_rates["output"])
    
    total_tokens = prompt_tokens + completion_tokens

    try:
        conn = await asyncpg.connect(DB_DSN)
        tx = conn.transaction()
        await tx.start()
        
        # 1. Insert Core Transaction
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
            # 2. Insert Routing Decisions
            await conn.execute(
                """
                INSERT INTO routing_decisions (transaction_id, selected_provider, reason, fallback_used)
                VALUES ($1, $2, $3, $4)
                """,
                tx_id, routed_to, routing_reason, fallback_used
            )
            
            # 3. Insert Prompt Intelligence Metrics
            if original_prompt:
                await conn.execute(
                    """
                    INSERT INTO prompt_quality_scores 
                    (transaction_id, original_prompt, enhanced_prompt, score, is_enhanced, detected_issues)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    tx_id, original_prompt, enhanced_prompt, prompt_score, is_enhanced, detected_issues
                )

            # 4. ATOMIC BUDGET DEDUCTION (Phase 3 Guardrail)
            await conn.execute(
                """
                INSERT INTO app_budgets (app_id, current_month_tokens, current_month_cost)
                VALUES ($1, $2, $3)
                ON CONFLICT (app_id) DO UPDATE 
                SET current_month_tokens = app_budgets.current_month_tokens + EXCLUDED.current_month_tokens,
                    current_month_cost = app_budgets.current_month_cost + EXCLUDED.current_month_cost,
                    is_blocked = CASE 
                        WHEN (app_budgets.current_month_cost + EXCLUDED.current_month_cost) >= app_budgets.monthly_cost_limit_usd 
                        THEN TRUE 
                        ELSE FALSE 
                    END;
                """,
                app_id, total_tokens, cost_usd
            )
            
        await tx.commit()
        await conn.close()
    except Exception as e:
        print(f"[-] Telemetry logging failed: {e}")

async def log_security_alert(app_id: str, alert_type: str, message: str):
    """Instantly logs a security or governance alert to the database for the Streamlit UI."""
    try:
        conn = await asyncpg.connect(DB_DSN)
        await conn.execute(
            "INSERT INTO alerts (alert_type, app_id, message) VALUES ($1, $2, $3)",
            alert_type, app_id, message
        )
        await conn.close()
    except Exception as e:
        print(f"[-] Failed to log security alert: {e}")