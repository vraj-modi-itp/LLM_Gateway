import asyncio
import asyncpg
import time
from typing import Dict
from app.services.telemetry import DB_DSN

class BudgetService:
    def __init__(self):
        # Local cache: { "app_id": is_blocked_boolean }
        self._blocked_apps: Dict[str, bool] = {}
        
        # RPM Cache: { "app_id": {"count": int, "window_start": float} }
        self._rpm_tracker: Dict[str, dict] = {}
        self.max_rpm = 60 # Maximum 60 requests per minute per app

    def is_allowed(self, app_id: str) -> bool:
        """Synchronous, 0ms check to see if an app is allowed to execute."""
        # 1. Check hard budget block from DB sync
        if self._blocked_apps.get(app_id, False):
            return False
            
        # 2. Check live Rate Limits (RPM)
        current_time = time.time()
        tracker = self._rpm_tracker.get(app_id)
        
        if not tracker or (current_time - tracker["window_start"] > 60):
            # Reset window
            self._rpm_tracker[app_id] = {"count": 1, "window_start": current_time}
            return True
            
        if tracker["count"] >= self.max_rpm:
            return False # Rate limit hit
            
        tracker["count"] += 1
        return True

    async def sync_budgets_loop(self):
        """Background task that checks the Postgres DB for blocked apps every 30 seconds."""
        while True:
            try:
                conn = await asyncpg.connect(DB_DSN)
                
                # Fetch apps that have exceeded their budget or are manually blocked
                rows = await conn.fetch("SELECT app_id, is_blocked FROM app_budgets")
                
                new_cache = {}
                for row in rows:
                    new_cache[row['app_id']] = row['is_blocked']
                
                self._blocked_apps = new_cache
                await conn.close()
            except Exception as e:
                print(f"Budget sync failed: {e}")
                
            await asyncio.sleep(30)

budget_service = BudgetService()