"""Consolidation client - sends consolidation requests to Evernight via A2A."""
from __future__ import annotations

import logging
from typing import Any

from twin.shared.a2a.client import A2AClient

logger = logging.getLogger(__name__)


class ConsolidationClient:
    """
    Client for sending consolidation requests to Evernight.
    
    This replaces the old local consolidation pipeline with A2A calls.
    """

    def __init__(self, evernight_url: str, timeout: float = 300.0):
        self.a2a_client = A2AClient(base_url=evernight_url, timeout=timeout)
        logger.info("ConsolidationClient initialized for %s", evernight_url)

    async def consolidate_scope(
        self,
        scope: str,
        scope_id: str,
        reason: str = "auto",
        max_messages: int = 200,
    ) -> dict[str, Any]:
        """
        Send consolidation request to Evernight.
        
        Returns dict with status, timeline_summary, profile_updates, etc.
        """
        logger.info(
            "ConsolidationClient: requesting consolidation scope=%s scope_id=%s reason=%s",
            scope, scope_id, reason,
        )
        
        try:
            result = await self.a2a_client.send_data_task(
                skill="consolidate_discussion",
                session_id=scope_id,
                params={
                    "payload": {
                        "scope": scope,
                        "scope_id": scope_id,
                        "reason": reason,
                        "max_messages": max_messages,
                    }
                },
            )
            
            logger.info(
                "ConsolidationClient: consolidation completed scope=%s/%s status=%s",
                scope, scope_id, result.get("status"),
            )
            return result
            
        except Exception as exc:
            logger.error(
                "ConsolidationClient: consolidation failed scope=%s/%s: %s",
                scope, scope_id, exc, exc_info=True,
            )
            return {
                "status": "failed",
                "scope": scope,
                "scope_id": scope_id,
                "error": str(exc),
            }

    async def close(self) -> None:
        """Close the A2A client session."""
        await self.a2a_client.close()
