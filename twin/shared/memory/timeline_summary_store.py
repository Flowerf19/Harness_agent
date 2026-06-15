"""Simplified timeline summary storage - replaces complex T2 atomic memories."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class TimelineSummary:
    """A timeline summary entry - one conversation summarized."""

    def __init__(
        self,
        user_id: str,
        content: str,
        embedding: list[float],
        importance: int = 3,
        summary_id: str | None = None,
        created_at: datetime | None = None,
    ):
        self.summary_id = summary_id or str(uuid.uuid4())
        self.user_id = user_id
        self.content = content
        self.embedding = embedding
        self.importance = importance
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "user_id": self.user_id,
            "content": self.content,
            "embedding": self.embedding,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
        }


class TimelineSummaryStore:
    """
    Simple vector store for timeline summaries.
    
    Replaces the complex T2 system (atomic memories + topics + supersede chains).
    Just stores conversation summaries with embeddings for semantic search.
    """

    def __init__(self, redis_client: Any, embedding_dim: int = 1024):
        self.redis = redis_client
        self.embedding_dim = embedding_dim
        self.index_name = "timeline_summaries"
        self.prefix = "timeline:summary"

    async def initialize(self) -> None:
        """Create Redis index if not exists."""
        try:
            await self.redis.execute_command("FT.INFO", self.index_name)
            logger.info("Timeline index already exists")
        except Exception:
            # Index doesn't exist, create it
            await self.redis.execute_command(
                "FT.CREATE", self.index_name,
                "ON", "HASH",
                "PREFIX", "1", f"{self.prefix}:",
                "SCHEMA",
                "user_id", "TAG",
                "importance", "NUMERIC",
                "created_at", "NUMERIC", "SORTABLE",
                "embedding", "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32",
                "DIM", str(self.embedding_dim),
                "DISTANCE_METRIC", "COSINE",
            )
            logger.info("Created timeline index")

    async def store_summary(
        self,
        user_id: str,
        content: str,
        embedding: list[float],
        importance: int = 3,
    ) -> str:
        """Store a timeline summary, return summary_id."""
        summary = TimelineSummary(
            user_id=user_id,
            content=content,
            embedding=embedding,
            importance=importance,
        )
        
        key = f"{self.prefix}:{summary.summary_id}"
        await self.redis.hset(
            key,
            mapping={
                "user_id": user_id,
                "content": content,
                "importance": importance,
                "created_at": summary.created_at.timestamp(),
                "embedding": self._pack_embedding(embedding),
            }
        )
        
        # Set TTL based on importance (days)
        ttl_days = self._importance_to_ttl(importance)
        await self.redis.expire(key, ttl_days * 86400)
        
        logger.info("Stored timeline summary %s for user %s", summary.summary_id, user_id)
        return summary.summary_id

    async def search(
        self,
        user_id: str,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search for similar summaries."""
        query = (
            f"(@user_id:{{{user_id}}})=>[KNN {limit} @embedding $vec AS score]"
        )
        
        try:
            results = await self.redis.execute_command(
                "FT.SEARCH", self.index_name,
                query,
                "PARAMS", "2", "vec", self._pack_embedding(query_embedding),
                "SORTBY", "score", "ASC",
                "LIMIT", "0", str(limit),
                "DIALECT", "2",
            )
            
            summaries = []
            if isinstance(results, dict):
                raw_results = results.get(b"results") or results.get("results") or []
                for item in raw_results:
                    key = item.get(b"id") or item.get("id")
                    extra_attrs = item.get(b"extra_attributes") or item.get("extra_attributes") or {}
                    
                    summary_dict = {}
                    for k, v in extra_attrs.items():
                        field_name = k.decode() if isinstance(k, bytes) else k
                        try:
                            field_value = v.decode() if isinstance(v, bytes) else v
                        except UnicodeDecodeError:
                            field_value = v
                        summary_dict[field_name] = field_value
                    
                    if key:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        summary_dict["summary_id"] = key_str.replace(f"{self.prefix}:", "")
                    summaries.append(summary_dict)
            else:
                # Parse results: [count, key1, [field1, val1, ...], key2, ...]
                i = 1
                while i < len(results):
                    key = results[i]
                    i += 1
                    if i < len(results):
                        fields = results[i]
                        i += 1
                        # Convert to dict
                        summary_dict = {}
                        for j in range(0, len(fields), 2):
                            field_name = fields[j].decode() if isinstance(fields[j], bytes) else fields[j]
                            try:
                                field_value = fields[j+1].decode() if isinstance(fields[j+1], bytes) else fields[j+1]
                            except UnicodeDecodeError:
                                field_value = fields[j+1]
                            summary_dict[field_name] = field_value
                        
                        # Extract summary_id from key
                        if key:
                            key_str = key.decode() if isinstance(key, bytes) else key
                            summary_dict["summary_id"] = key_str.replace(f"{self.prefix}:", "")
                        summaries.append(summary_dict)
            
            return summaries
            
        except Exception as exc:
            logger.error("Timeline search failed: %s", exc)
            return []

    async def get_recent(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent summaries for a user."""
        query = f"@user_id:{{{user_id}}}"
        
        try:
            results = await self.redis.execute_command(
                "FT.SEARCH", self.index_name,
                query,
                "SORTBY", "created_at", "DESC",
                "LIMIT", "0", str(limit),
            )
            
            summaries = []
            if isinstance(results, dict):
                raw_results = results.get(b"results") or results.get("results") or []
                for item in raw_results:
                    key = item.get(b"id") or item.get("id")
                    extra_attrs = item.get(b"extra_attributes") or item.get("extra_attributes") or {}
                    
                    summary_dict = {}
                    for k, v in extra_attrs.items():
                        field_name = k.decode() if isinstance(k, bytes) else k
                        try:
                            field_value = v.decode() if isinstance(v, bytes) else v
                        except UnicodeDecodeError:
                            field_value = v
                        summary_dict[field_name] = field_value
                    
                    if key:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        summary_dict["summary_id"] = key_str.replace(f"{self.prefix}:", "")
                    summaries.append(summary_dict)
            else:
                i = 1
                while i < len(results):
                    key = results[i]
                    i += 1
                    if i < len(results):
                        fields = results[i]
                        i += 1
                        summary_dict = {}
                        for j in range(0, len(fields), 2):
                            field_name = fields[j].decode() if isinstance(fields[j], bytes) else fields[j]
                            try:
                                field_value = fields[j+1].decode() if isinstance(fields[j+1], bytes) else fields[j+1]
                            except UnicodeDecodeError:
                                field_value = fields[j+1]
                            summary_dict[field_name] = field_value
                        
                        if key:
                            key_str = key.decode() if isinstance(key, bytes) else key
                            summary_dict["summary_id"] = key_str.replace(f"{self.prefix}:", "")
                        summaries.append(summary_dict)
            
            return summaries
            
        except Exception as exc:
            logger.error("Timeline get_recent failed: %s", exc)
            return []

    def _pack_embedding(self, embedding: list[float]) -> bytes:
        """Pack embedding list into bytes for Redis."""
        import struct
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def _importance_to_ttl(importance: int) -> int:
        """Convert importance (1-5) to TTL in days."""
        ttl_map = {
            5: 365,  # 1 year
            4: 180,  # 6 months
            3: 90,   # 3 months
            2: 30,   # 1 month
            1: 7,    # 1 week
        }
        return ttl_map.get(importance, 90)
