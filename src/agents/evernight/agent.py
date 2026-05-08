"""EvernightAgent - Background T2 consolidation agent."""
import logging
from typing import Any, List  # noqa: F401

from langsmith import traceable

from src.agents.shared.models.wiki_page import WikiPagePayload, generate_page_id

logger = logging.getLogger(__name__)


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
    Uses EpisodicMemoryManager for storage + embedding.
    """

    def __init__(
        self,
        memory_manager: Any,
        wiki_merge: Any,
        llm_client: Any,
    ):
        self.memory = memory_manager
        self.merge = wiki_merge
        self.llm = llm_client

    @traceable(
        name="T2_Consolidate_Snapshot",
        run_type="chain",
        tags=["tier_2", "wiki", "consolidation"],
    )
    async def consolidate(self, user_id: str, snapshot: List[dict]) -> bool:
        logger.info(f"⏳ EvernightAgent: Consolidating snapshot for user {user_id}")

        try:
            topics = await self._extract_topics(snapshot)
            if not topics:
                logger.info("ℹ️ EvernightAgent: No distinct topics found in snapshot")
                return True

            logger.info(f"📋 EvernightAgent: Found {len(topics)} topics to consolidate")

            success_count = 0
            for topic_info in topics:
                try:
                    canonical_topic = topic_info.get("canonical_topic")
                    if not canonical_topic:
                        continue

                    page_id = generate_page_id(user_id, canonical_topic)
                    existing_page = await self.memory.lookup_by_page_id(page_id)

                    if existing_page:
                        merged_page = await self.merge.merge(existing_page, topic_info)
                        if merged_page:
                            await self.memory.embed_page(merged_page)
                            success_count += 1
                    else:
                        new_page = self.merge.create_new_page(
                            user_id=user_id,
                            canonical_topic=canonical_topic,
                            new_info=topic_info,
                        )
                        await self.memory.embed_page(new_page)
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
        import json
        import re

        from src.services.llm.llm_response import LLMResponse

        try:
            snapshot_text = self._format_snapshot(snapshot)
            prompt = TOPIC_EXTRACTION_PROMPT + f"\n\nChat Snapshot:\n{snapshot_text}"

            llm_response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}]
            )

            if isinstance(llm_response, LLMResponse):
                raw_text = llm_response.content
            else:
                raw_text = str(llm_response)

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
        lines = []
        for msg in snapshot:
            role = msg.get("role", "unknown") if isinstance(msg, dict) else getattr(msg, "role", "unknown")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            lines.append(f"[{role.upper()}]: {content}")
        return "\n".join(lines)
