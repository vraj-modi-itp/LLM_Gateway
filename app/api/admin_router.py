import os
import asyncpg
from fastapi import APIRouter, Header, HTTPException, Request, Depends

admin_router = APIRouter(prefix="/admin")
DB_DSN = "postgresql://proxy_user:proxy_password@localhost:5433/proxy_db"

def verify_admin(x_admin_key: str = Header(...)):
    """Validates the static admin key from the environment."""
    expected_key = os.getenv("ADMIN_API_KEY")
    if not expected_key or x_admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin Key")

@admin_router.get("/flags", dependencies=[Depends(verify_admin)])
async def get_feature_flags():
    """Returns all current feature flags in the database."""
    conn = await asyncpg.connect(DB_DSN)
    try:
        rows = await conn.fetch("SELECT flag_name, is_enabled, description, updated_at FROM gateway_feature_flags")
        return {"flags": [dict(row) for row in rows]}
    finally:
        await conn.close()

@admin_router.post("/flags/{flag_name}", dependencies=[Depends(verify_admin)])
async def update_feature_flag(flag_name: str, request: Request):
    """Instantly toggles a feature flag."""
    payload = await request.json()
    is_enabled = payload.get("is_enabled")
    updated_by = payload.get("updated_by", "admin")

    if is_enabled is None:
        raise HTTPException(status_code=400, detail="Missing 'is_enabled' boolean in body")

    conn = await asyncpg.connect(DB_DSN)
    try:
        # Update the database. The 30-second TTL cache in flag_resolver.py will pick this up automatically.
        result = await conn.execute("""
            UPDATE gateway_feature_flags 
            SET is_enabled = $1, updated_by = $2, updated_at = NOW() 
            WHERE flag_name = $3
        """, is_enabled, updated_by, flag_name)
        
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail=f"Flag '{flag_name}' not found")
            
        return {"status": "success", "flag_name": flag_name, "is_enabled": is_enabled}
    finally:
        await conn.close()