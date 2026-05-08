"""WikiStorage - Qdrant operations for WikiPages."""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from src.agents.shared.models.wiki_page import (
    WikiPagePayload,
    generate_page_id,
    calculate_relevance,
)

from src.config.settings import Config

logger = logging.getLogger(__name__)


class WikiStorage:
    """
    Qdrant storage service for WikiPages.

    SRP: Only handles storage operations (CRUD + semantic search).
    """

    COLLECTION_NAME = "wiki_pages"

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: Optional[str] = None,
        vector_size: int = None,
    ):
        """
        Initialize WikiStorage with Qdrant connection.

        Args:
            url: Qdrant server URL
            api_key: Optional API key for Qdrant Cloud
            vector_size: Embedding vector dimension (default from Config)
        """
        if vector_size is None:
            vector_size = Config.EMBEDDING_VECTOR_SIZE
        self.url = url
        self.api_key = api_key
        self.vector_size = vector_size
        self._client = AsyncQdrantClient(url=url, api_key=api_key)

    async def initialize(self) -> None:
        """Create collection if not exists."""
        try:
            collections = await self._client.get_collections()
            existing_names = [c.name for c in collections.collections]

            if self.COLLECTION_NAME not in existing_names:
                await self._client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.debug(f"✅ WikiStorage: Created collection '{self.COLLECTION_NAME}'")
            else:
                logger.debug(f"✅ WikiStorage: Collection '{self.COLLECTION_NAME}' already exists")
        except Exception as e:
            logger.error(f"❌ WikiStorage: Error initializing collection: {e}")
            raise

    async def close(self) -> None:
        """Close Qdrant client connection."""
        await self._client.close()
        logger.debug("🔴 WikiStorage: Connection closed")

    async def lookup_by_page_id(self, page_id: str) -> Optional[WikiPagePayload]:
        """
        Lookup WikiPage by deterministic page_id.

        Args:
            page_id: The page ID to look up

        Returns:
            WikiPagePayload if found, None otherwise
        """
        try:
            results, _ = await self._client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="page_id",
                            match=models.MatchValue(value=page_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )

            if not results:
                return None

            point = results[0]
            return self._point_to_page(point)

        except Exception as e:
            logger.error(f"❌ WikiStorage: Error looking up page_id={page_id}: {e}")
            return None

    async def upsert_page(self, page: WikiPagePayload) -> bool:
        """
        Upsert WikiPage with embedding.

        Args:
            page: WikiPagePayload to upsert (must have embedding)

        Returns:
            True if successful, False otherwise
        """
        if not page.embedding:
            logger.warning("⚠️ WikiStorage: Cannot upsert page without embedding")
            return False

        try:
            payload = page.model_dump()
            # Convert datetime to ISO string for Qdrant
            payload["created_at"] = page.created_at.isoformat()
            payload["last_updated"] = page.last_updated.isoformat()
            payload["last_accessed"] = page.last_accessed.isoformat()

            await self._client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[
                    models.PointStruct(
                        id=page.page_id,
                        vector=page.embedding,
                        payload=payload,
                    )
                ],
            )
            logger.debug(f"💾 WikiStorage: Upserted page '{page.canonical_topic}' for user {page.user_id}")
            return True

        except Exception as e:
            logger.error(f"❌ WikiStorage: Error upserting page: {e}")
            return False

    async def list_all_for_user(
        self,
        user_id: str,
        limit: int = 100,
    ) -> List[WikiPagePayload]:
        """
        Fetch all WikiPages for a user.

        Args:
            user_id: Discord user ID to filter by
            limit: Maximum number of results

        Returns:
            List of WikiPagePayload
        """
        try:
            results, _ = await self._client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id),
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            pages = []
            for point in results:
                page = self._point_to_page(point)
                if page is not None:
                    pages.append(page)

            return pages

        except Exception as e:
            logger.error(f"❌ WikiStorage: Error listing pages for user {user_id}: {e}")
            return []

    async def search_by_time(
        self,
        user_id: str,
        days: int = 7,
        top_k: int = 10,
    ) -> List[WikiPagePayload]:
        """
        Search by last_updated within X days.

        Args:
            user_id: Discord user ID to filter by
            days: Number of days to look back
            top_k: Maximum number of results

        Returns:
            List of WikiPagePayload sorted by last_updated descending
        """
        try:
            current_time = datetime.now(timezone.utc)

            # Fetch all pages for user
            all_pages = await self.list_all_for_user(user_id)

            # Filter by time
            filtered_pages = []
            for page in all_pages:
                days_since_update = (current_time - page.last_updated).days
                if days_since_update <= days:
                    filtered_pages.append(page)

            # Sort by last_updated descending
            filtered_pages.sort(key=lambda p: p.last_updated, reverse=True)

            return filtered_pages[:top_k]

        except Exception as e:
            logger.error(f"❌ WikiStorage: Error searching by time: {e}")
            return []

    async def search_by_topic(
        self,
        user_id: str,
        topic_keyword: str,
        top_k: int = 10,
    ) -> List[WikiPagePayload]:
        """
        Search by canonical_topic contains keyword (case-insensitive).

        Args:
            user_id: Discord user ID to filter by
            topic_keyword: Keyword to search in canonical_topic
            top_k: Maximum number of results

        Returns:
            List of WikiPagePayload sorted by importance descending
        """
        try:
            # Fetch all pages for user
            all_pages = await self.list_all_for_user(user_id)

            # Filter by topic keyword (case-insensitive)
            keyword_lower = topic_keyword.lower()
            filtered_pages = [
                page for page in all_pages
                if keyword_lower in page.canonical_topic.lower()
            ]

            # Sort by importance descending
            filtered_pages.sort(key=lambda p: p.importance, reverse=True)

            return filtered_pages[:top_k]

        except Exception as e:
            logger.error(f"❌ WikiStorage: Error searching by topic: {e}")
            return []

    async def search_similar(
        self,
        user_id: str,
        query_vector: List[float],
        top_k: int = 5,
        min_relevance: float = 0.5,
    ) -> List[WikiPagePayload]:
        """
        Semantic search with TTL decay filtering.

        Args:
            user_id: Discord user ID to filter by
            query_vector: Embedding vector for the query
            top_k: Maximum number of results
            min_relevance: Minimum relevance threshold after TTL decay

        Returns:
            List of WikiPagePayload sorted by relevance
        """
        try:
            current_time = datetime.now(timezone.utc)

            results = await self._client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id),
                        )
                    ]
                ),
                limit=top_k * 2,  # Fetch more to allow for relevance filtering
                with_payload=True,
                with_vectors=True,
            )

            pages_with_relevance: List[tuple[WikiPagePayload, float]] = []
            for point in results.points:
                page = self._point_to_page(point)
                if page is None:
                    continue

                # Calculate relevance with TTL decay
                relevance = calculate_relevance(page, current_time)
                if relevance >= min_relevance:
                    pages_with_relevance.append((page, relevance))

            # Sort by relevance descending
            pages_with_relevance.sort(key=lambda x: x[1], reverse=True)
            return [p[0] for p in pages_with_relevance[:top_k]]

        except Exception as e:
            logger.error(f"❌ WikiStorage: Error searching: {e}")
            return []

    async def refresh_access(self, page_id: str) -> None:
        """
        Update last_accessed and access_count for a page.

        Args:
            page_id: The page ID to refresh
        """
        try:
            # Get current page
            page = await self.lookup_by_page_id(page_id)
            if page is None:
                logger.warning(f"⚠️ WikiStorage: Cannot refresh access for non-existent page {page_id}")
                return

            # Update access metadata
            page.last_accessed = datetime.now(timezone.utc)
            page.access_count += 1

            # Upsert back
            await self.upsert_page(page)
            logger.debug(f"🔄 WikiStorage: Refreshed access for page {page_id}")

        except Exception as e:
            logger.error(f"❌ WikiStorage: Error refreshing access: {e}")

    def _point_to_page(self, point: models.ScoredPoint | models.Record) -> Optional[WikiPagePayload]:
        """
        Convert Qdrant point to WikiPagePayload.

        Args:
            point: Qdrant point (ScoredPoint or Record)

        Returns:
            WikiPagePayload or None if parsing fails
        """
        try:
            payload = point.payload
            if payload is None:
                return None

            # Parse datetime strings back to datetime objects
            created_at = payload.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            last_updated = payload.get("last_updated")
            if isinstance(last_updated, str):
                last_updated = datetime.fromisoformat(last_updated)
            last_accessed = payload.get("last_accessed")
            if isinstance(last_accessed, str):
                last_accessed = datetime.fromisoformat(last_accessed)

            # Get embedding from vector
            embedding = None
            if hasattr(point, "vector") and point.vector:
                embedding = point.vector

            return WikiPagePayload(
                page_id=payload.get("page_id"),
                user_id=payload.get("user_id"),
                canonical_topic=payload.get("canonical_topic"),
                category=payload.get("category"),
                current_summary=payload.get("current_summary"),
                key_points=payload.get("key_points", []),
                importance=payload.get("importance", 1),
                ttl_days=payload.get("ttl_days", 30),
                created_at=created_at or datetime.now(timezone.utc),
                last_updated=last_updated or datetime.now(timezone.utc),
                last_accessed=last_accessed or datetime.now(timezone.utc),
                access_count=payload.get("access_count", 0),
                history_log=payload.get("history_log", []),
                confidence=payload.get("confidence", 1.0),
                embedding=embedding,
            )

        except Exception as e:
            logger.warning(f"⚠️ WikiStorage: Error parsing point to page: {e}")
            return None

    async def delete_page(self, page_id: str) -> bool:
        """
        Delete a WikiPage by page_id.

        Args:
            page_id: The page ID to delete

        Returns:
            True if deleted, False otherwise
        """
        try:
            await self._client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=models.PointIdsList(points=[page_id]),
            )
            logger.debug(f"🗑️ WikiStorage: Deleted page {page_id}")
            return True

        except UnexpectedResponse as e:
            if e.status_code == 404:
                logger.warning(f"⚠️ WikiStorage: Page {page_id} not found")
                return False
            logger.error(f"❌ WikiStorage: Error deleting page: {e}")
            return False

        except Exception as e:
            logger.error(f"❌ WikiStorage: Error deleting page: {e}")
            return False