import json
import logging
import asyncpg
from typing import List, Dict, Any
from app.services.telemetry import DB_DSN

logger = logging.getLogger("gateway.audit")

class AuditLogService:
    async def log_interaction(
        self,
        session_id: str,
        app_id: str,
        provider: str,
        model_used: str,
        messages: List[Dict[str, Any]],
        response_text: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0
    ) -> None:
        """
        Persists the transaction audit log asynchronously to PostgreSQL.
        Wrapped in a try-except block to ensure logging failures never 
        crash the primary routing response.
        """
        query = """
            INSERT INTO audit_chat_history (
                session_id, app_id, provider, model_used, messages, response, prompt_tokens, completion_tokens
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8);
        """
        try:
            # Connect directly using the proven DSN from telemetry
            conn = await asyncpg.connect(DB_DSN)
            await conn.execute(
                query,
                session_id,
                app_id,
                provider,
                model_used,
                json.dumps(messages),
                response_text,
                prompt_tokens,
                completion_tokens
            )
            await conn.close()
        except Exception as e:
            # Crucial: Protect core proxy execution if database logging fluctuates
            error_msg = f"Failed to write audit log for session {session_id}: {str(e)}"
            logger.error(error_msg)
            print(f"[-] Audit Logger Error: {error_msg}")

# Instantiate the singleton so router.py can import it
audit_service = AuditLogService()