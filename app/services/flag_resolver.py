import time
import asyncpg
from app.core.config import settings

DB_DSN = "postgresql://proxy_user:proxy_password@localhost:5433/proxy_db"

# In-memory TTL Cache Dictionary
_flag_cache = {
    "data": {},
    "last_refreshed": 0
}
CACHE_TTL_SECONDS = 30

async def _refresh_cache():
    """Fetches the global flag and all app-specific overrides from Postgres."""
    conn = await asyncpg.connect(DB_DSN)
    try:
        # Get Global Flag
        global_row = await conn.fetchrow(
            "SELECT is_enabled FROM gateway_feature_flags WHERE flag_name = 'prompt_intelligence_enabled'"
        )
        global_enabled = global_row["is_enabled"] if global_row else True

        # Get App Overrides
        app_rows = await conn.fetch("SELECT app_id, pi_enabled FROM app_budgets")
        
        new_data = {"GLOBAL_PI": global_enabled, "apps": {}}
        for row in app_rows:
            new_data["apps"][row["app_id"]] = row["pi_enabled"]

        _flag_cache["data"] = new_data
        _flag_cache["last_refreshed"] = time.time()
    finally:
        await conn.close()

async def resolve_pi_enabled(app_id: str) -> bool:
    """Returns True if Prompt Intelligence should run, False if it should be skipped."""
    if time.time() - _flag_cache["last_refreshed"] > CACHE_TTL_SECONDS:
        await _refresh_cache()

    cache_data = _flag_cache["data"]
    global_flag = cache_data.get("GLOBAL_PI", True)

    # 1. Global Kill Switch unconditionally overrides everything
    if not global_flag:
        return False

    # 2. Check for App-Specific Override
    app_override = cache_data.get("apps", {}).get(app_id)
    if app_override is not None:
        return app_override  # True or False

    # 3. Default to Global Flag
    return global_flag