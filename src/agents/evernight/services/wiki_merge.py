"""WikiMergeService - LLM-based merge for WikiPages."""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.shared.models.wiki_page import WikiPagePayload, generate_page_id
from src.services.llm.llm_response import LLMResponse

logger = logging.getLogger(__name__)


WIKI_MERGE_PROMPT = """Role: Memory_Consolidator
Task: Merge_Wiki_Pages

Input:
  old_page: {old_page_json}
  new_info: {new_info_json}

Merge_Rules:
  1. MUTABLE_FACTS_REPLACE: Preferences, ratings, opinions
     - old: "rating 9/10" + new: "rating 8/10" → use 8/10
     - Add to history_log: "rating: 9→8"

  2. ACCUMULATIVE_FACTS_APPEND: Events, experiences
     - old: "watched ep 1-6" + new: "watched ep 7-13"
     → combine: "watched ep 1-13"

  3. CONTRADICTIONS_RESOLVE: Prefer NEWEST (user's current state)

Output: Return ONLY valid JSON (no markdown, no explanation):
{{
  "current_summary": "<merged summary>",
  "key_points": ["<accumulated fact 1>", "<accumulated fact 2>"],
  "history_log": ["<change 1>", "<change 2>"],
  "category": "<category if changed>",
  "importance": <1-5 number if changed>
}}"""


class WikiMergeService:
    """
    LLM-based merge for WikiPages.

    SRP: Only handles merge logic using LLM.
    """

    def __init__(self, llm_client: Any):
        """
        Initialize WikiMergeService.

        Args:
            llm_client: LLM client with generate_response(messages) method
        """
        self.llm_client = llm_client

    def _clean_json_output(self, raw_text: str) -> str:
        """Clean markdown and extra characters from LLM JSON output."""
        cleaned = raw_text.strip()
        # Remove ```json and ``` markers
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```$", "", cleaned)
        return cleaned.strip()

    async def merge(
        self,
        old_page: WikiPagePayload,
        new_info: dict,
    ) -> Optional[WikiPagePayload]:
        """
        Call LLM to merge old page with new info.

        Args:
            old_page: Existing WikiPagePayload
            new_info: New information dict to merge

        Returns:
            Merged WikiPagePayload or None if merge fails
        """
        try:
            # Prepare input for LLM
            old_page_json = json.dumps(
                {
                    "canonical_topic": old_page.canonical_topic,
                    "current_summary": old_page.current_summary,
                    "key_points": old_page.key_points,
                    "history_log": old_page.history_log,
                    "category": old_page.category,
                    "importance": old_page.importance,
                },
                ensure_ascii=False,
                indent=2,
            )

            new_info_json = json.dumps(new_info, ensure_ascii=False, indent=2)

            # Format prompt
            prompt = WIKI_MERGE_PROMPT.format(
                old_page_json=old_page_json,
                new_info_json=new_info_json,
            )

            # Call LLM
            llm_response = await self.llm_client.generate_response(
                messages=[{"role": "user", "content": prompt}]
            )

            # Extract text from response
            if isinstance(llm_response, LLMResponse):
                raw_text = llm_response.content
            else:
                raw_text = str(llm_response)

            # Parse JSON response
            json_str = self._clean_json_output(raw_text)
            merged_data = json.loads(json_str)

            # Update the page with merged data
            now = datetime.now(timezone.utc)
            old_page.current_summary = merged_data.get("current_summary", old_page.current_summary)
            old_page.key_points = merged_data.get("key_points", old_page.key_points)
            old_page.history_log = merged_data.get("history_log", old_page.history_log)
            if "category" in merged_data:
                old_page.category = merged_data["category"]
            if "importance" in merged_data:
                old_page.importance = merged_data["importance"]

            old_page.last_updated = now

            logger.info(f"✅ WikiMergeService: Merged page '{old_page.canonical_topic}'")
            return old_page

        except json.JSONDecodeError as e:
            logger.error(f"❌ WikiMergeService: LLM returned invalid JSON: {e}\nRaw: {raw_text}")
            return None

        except Exception as e:
            logger.error(f"❌ WikiMergeService: Merge failed: {e}", exc_info=True)
            return None

    def create_new_page(
        self,
        user_id: str,
        canonical_topic: str,
        new_info: dict,
    ) -> WikiPagePayload:
        """
        Create a new WikiPage from extracted info.

        Args:
            user_id: Discord user ID
            canonical_topic: LLM-normalized topic name
            new_info: Extracted information dict

        Returns:
            New WikiPagePayload (without embedding)
        """
        now = datetime.now(timezone.utc)
        page_id = generate_page_id(user_id, canonical_topic)

        # Calculate TTL from importance
        importance = new_info.get("importance", 3)
        ttl_days = self._calculate_ttl(importance)

        return WikiPagePayload(
            page_id=page_id,
            user_id=user_id,
            canonical_topic=canonical_topic,
            category=new_info.get("category", "casual"),
            current_summary=new_info.get("summary", ""),
            key_points=new_info.get("key_points", []),
            importance=importance,
            ttl_days=ttl_days,
            created_at=now,
            last_updated=now,
            last_accessed=now,
            access_count=0,
            history_log=[],
            confidence=new_info.get("confidence", 1.0),
            embedding=None,
        )

    def _calculate_ttl(self, importance: int) -> int:
        """
        Calculate TTL in days based on importance.

        Args:
            importance: Importance level 1-5

        Returns:
            TTL in days (7-90)
        """
        ttl_map = {
            5: 90,  # High importance - 90 days
            4: 60,  # 60 days
            3: 30,  # Default - 30 days
            2: 14,  # 14 days
            1: 7,   # Low importance - 7 days
        }
        return ttl_map.get(importance, 30)