"""EvernightAgent - Background T2 consolidation agent."""
import logging
from typing import Any, List, Optional  # noqa: F401

from langsmith import traceable

from src.agents.evernight.services.wiki_storage import WikiStorage
from src.agents.evernight.services.wiki_merge import WikiMergeService
from src.agents.shared.models.wiki_page import WikiPagePayload, generate_page_id

logger = logging.getLogger(__name__)


# Prompt for extracting topics from T1 snapshot
TOPIC_EXTRACTION_PROMPT = """Role: Topic_Extractor
Task: Extract_Topics_From_Snapshot

Input: A chat snapshot (list of messages)

Extract distinct topics mentioned in this conversation. For each topic, provide:
- canonical_topic: Normalized name (snake_case, e.g., "Evangelion_Anime")
- category: One of [entertainment, relationship, work_study, casual, daily_mood]
- summary: Brief summary about this topic from the conversation
- key_points: List of specific facts/mentions
- importance: 1-5 (how important this topic seems to the user)
- confidence: 0.0-1.0 (how confident in extraction)

Output: Return ONLY valid JSON array:
[
  {
    "canonical_topic": "<topic_name>",
    "category": "<category>",
    "summary": "<brief summary>",
    "key_points": ["<fact1>", "<fact2>"],
    "importance": <1-5>,
    "confidence": <0.0-1.0>
  }
]

If no clear topics found, return: []
"""


class EvernightAgent:
    """
    Sub-Agent for T2 Wiki consolidation.

    SRP: Only handles consolidation of T1 snapshots into WikiPages.
    """

    def __init__(
        self,
        wiki_storage: WikiStorage,
        wiki_merge: WikiMergeService,
        llm_client: Any,
        embedding_service: Any,
    ):
        """
        Initialize EvernightAgent.

        Args:
            wiki_storage: WikiStorage for Qdrant operations
            wiki_merge: WikiMergeService for LLM-based merging
            llm_client: LLM client with generate_response(messages) method
            embedding_service: Service with get_embedding(text) -> List[float] method
        """
        self.storage = wiki_storage
        self.merge = wiki_merge
        self.llm = llm_client
        self.embedding = embedding_service

    @traceable(
        name="T2_Consolidate_Snapshot",
        run_type="chain",
        tags=["tier_2", "wiki", "consolidation"],
    )
    async def consolidate(self, user_id: str, snapshot: List[dict]) -> bool:
        """
        Consolidate T1 snapshot into WikiPages.

        Flow:
        1. Extract topics from snapshot via LLM
        2. For each topic:
           - Generate page_id
           - Lookup existing page
           - Merge or create
           - Embed and upsert

        Args:
            user_id: Discord user ID
            snapshot: List of message dicts from T1 memory

        Returns:
            True if consolidation succeeded, False otherwise
        """
        logger.info(f"⏳ EvernightAgent: Consolidating snapshot for user {user_id}")

        try:
            # 1. Extract topics from snapshot
            topics = await self._extract_topics(snapshot)
            if not topics:
                logger.info("ℹ️ EvernightAgent: No distinct topics found in snapshot")
                return True

            logger.info(f"📋 EvernightAgent: Found {len(topics)} topics to consolidate")

            # 2. Process each topic
            success_count = 0
            for topic_info in topics:
                try:
                    canonical_topic = topic_info.get("canonical_topic")
                    if not canonical_topic:
                        continue

                    # Generate deterministic page_id
                    page_id = generate_page_id(user_id, canonical_topic)

                    # Lookup existing page
                    existing_page = await self.storage.lookup_by_page_id(page_id)

                    if existing_page:
                        # Merge with existing
                        merged_page = await self.merge.merge(existing_page, topic_info)
                        if merged_page:
                            # Embed and upsert
                            await self._embed_and_upsert(merged_page)
                            success_count += 1
                    else:
                        # Create new page
                        new_page = self.merge.create_new_page(
                            user_id=user_id,
                            canonical_topic=canonical_topic,
                            new_info=topic_info,
                        )
                        # Embed and upsert
                        await self._embed_and_upsert(new_page)
                        success_count += 1

                except Exception as topic_error:
                    logger.error(f"❌ EvernightAgent: Error processing topic: {topic_error}")
                    continue

            logger.info(
                f"✅ EvernightAgent: Consolidated {success_count}/{len(topics)} topics for user {user_id}"
            )
            return success_count > 0

        except Exception as e:
            logger.error(f"❌ EvernightAgent: Consolidation failed: {e}", exc_info=True)
            return False

    async def _extract_topics(self, snapshot: List[dict]) -> List[dict]:
        """
        Extract topics from T1 snapshot using LLM.

        Args:
            snapshot: List of message dicts

        Returns:
            List of topic info dicts
        """
        import json
        import re

        from src.services.llm.llm_response import LLMResponse

        try:
            # Format snapshot for LLM
            snapshot_text = self._format_snapshot(snapshot)
            prompt = TOPIC_EXTRACTION_PROMPT + f"\n\nChat Snapshot:\n{snapshot_text}"

            # Call LLM
            llm_response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}]
            )

            # Extract text
            if isinstance(llm_response, LLMResponse):
                raw_text = llm_response.content
            else:
                raw_text = str(llm_response)

            # Clean and parse JSON
            cleaned = raw_text.strip()
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"```$", "", cleaned).strip()

            topics = json.loads(cleaned)

            if isinstance(topics, list):
                return topics

            logger.warning(f"⚠️ EvernightAgent: LLM returned non-list: {type(topics)}")
            return []

        except json.JSONDecodeError as e:
            logger.error(f"❌ EvernightAgent: Failed to parse topics JSON: {e}")
            return []

        except Exception as e:
            logger.error(f"❌ EvernightAgent: Topic extraction failed: {e}")
            return []

    def _format_snapshot(self, snapshot: List[dict]) -> str:
        """
        Format snapshot for LLM input.

        Args:
            snapshot: List of message dicts

        Returns:
            Formatted string
        """
        lines = []
        for msg in snapshot:
            role = msg.get("role", "unknown") if isinstance(msg, dict) else getattr(msg, "role", "unknown")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            lines.append(f"[{role.upper()}]: {content}")
        return "\n".join(lines)

    def _build_search_content(self, page: WikiPagePayload) -> str:
        """
        Concatenate all searchable content for embedding.

        Args:
            page: WikiPagePayload to extract content from

        Returns:
            Concatenated string of canonical_topic, summary, and key_points
        """
        parts = [page.canonical_topic, page.current_summary]
        if page.key_points:
            parts.extend(page.key_points)
        return "\n".join(parts)

    async def _embed_and_upsert(self, page: WikiPagePayload) -> bool:
        """
        Generate embedding for page and upsert to storage.

        Embeds concatenated content: canonical_topic + current_summary + key_points.
        This enables semantic search to match queries against all searchable content.

        Args:
            page: WikiPagePayload to embed and store

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build search content and generate embedding
            search_content = self._build_search_content(page)
            embedding = await self.embedding.get_embedding(search_content)
            if not embedding:
                logger.warning(f"⚠️ EvernightAgent: Failed to embed page '{page.canonical_topic}'")
                return False

            page.embedding = embedding

            # Upsert to storage
            success = await self.storage.upsert_page(page)
            if success:
                logger.debug(f"💾 EvernightAgent: Upserted page '{page.canonical_topic}'")
            return success

        except Exception as e:
            logger.error(f"❌ EvernightAgent: Embed and upsert failed: {e}")
            return False