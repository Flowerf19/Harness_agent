"""T2 topic resolver — match proposed topic name to existing T2Topic.

4-stage cascade:
  1. exact name / alias match (case-insensitive, normalized)
  2. KNN ≥ auto_threshold (0.92) → auto-attach alias
  3. KNN in [llm_threshold, auto_threshold) → LLM judge
  4. otherwise → create new topic
"""
from __future__ import annotations

import logging
import re

from twin.shared.memory.timeline.constants import (
    TOPIC_MATCH_THRESHOLD_AUTO,
    TOPIC_MATCH_THRESHOLD_LLM,
)
from twin.shared.memory.timeline.models import T2Topic
from twin.shared.memory.timeline.store import TimelineStore

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(name: str) -> str:
    """Lowercase, strip, collapse whitespace. Preserves diacritics."""
    return _WHITESPACE_RE.sub(" ", name.strip().lower())


class TopicResolver:
    """Resolve a proposed topic name to an existing T2Topic or create new."""

    def __init__(
        self,
        store: TimelineStore,
        embedder,
        llm,
        *,
        auto_threshold: float = TOPIC_MATCH_THRESHOLD_AUTO,
        llm_threshold: float = TOPIC_MATCH_THRESHOLD_LLM,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.llm = llm
        self.auto_threshold = auto_threshold
        self.llm_threshold = llm_threshold
        self.logger = logging.getLogger(__name__)

    async def resolve(
        self,
        user_id: str,
        proposed_name: str,
        *,
        catalogs: list[str] | None = None,
        content_hint: str | None = None,
        importance: int = 3,
    ) -> T2Topic:
        """4-stage cascade. Returns existing topic or newly created one."""
        normalized = _normalize(proposed_name)
        self.logger.debug(
            "T2:resolver: resolve user=%s name=%r normalized=%r",
            user_id, proposed_name, normalized,
        )

        # Stage 1 — exact name / alias match.
        existing = await self.store.find_topic_by_name_or_alias(user_id, normalized)
        if existing is not None:
            self.logger.info(
                "T2:resolver: matched via=exact user=%s topic=%s name=%r",
                user_id, existing.topic_id, existing.name,
            )
            await self._attach_alias(existing, proposed_name)
            await self.store.refresh_topic(user_id, existing.topic_id, bump_access=True)
            return existing

        # Stage 2 — embed + KNN top-3.
        query_text = (
            f"{proposed_name}: {content_hint}" if content_hint else proposed_name
        )
        vec = await self.embedder.get_embedding(query_text)
        if not vec:
            self.logger.debug(
                "T2:resolver: empty embedding, falling through to create"
            )
            return await self._create_new(
                user_id, proposed_name, vec or [], catalogs, importance
            )

        candidates = await self.store.knn_topics(user_id, vec, k=3)
        self.logger.debug(
            "T2:resolver: knn returned %d candidates for user=%s",
            len(candidates), user_id,
        )

        if candidates:
            best_topic, best_sim = candidates[0]
            if best_sim >= self.auto_threshold:
                self.logger.info(
                    "T2:resolver: matched via=knn user=%s topic=%s sim=%.3f",
                    user_id, best_topic.topic_id, best_sim,
                )
                await self._attach_alias(best_topic, proposed_name)
                await self.store.refresh_topic(
                    user_id, best_topic.topic_id, bump_access=True
                )
                return best_topic

            # Stage 3 — borderline LLM judge.
            if best_sim >= self.llm_threshold:
                same = await self._llm_same_topic(
                    proposed_name, best_topic, content_hint
                )
                if same:
                    self.logger.info(
                        "T2:resolver: matched via=llm user=%s topic=%s sim=%.3f",
                        user_id, best_topic.topic_id, best_sim,
                    )
                    await self._attach_alias(best_topic, proposed_name)
                    await self.store.refresh_topic(
                        user_id, best_topic.topic_id, bump_access=True
                    )
                    return best_topic

        # Stage 4 — create new.
        return await self._create_new(
            user_id, proposed_name, vec, catalogs, importance
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _create_new(
        self,
        user_id: str,
        proposed_name: str,
        vec: list[float],
        catalogs: list[str] | None,
        importance: int,
    ) -> T2Topic:
        normalized = _normalize(proposed_name)
        aliases = [proposed_name] if proposed_name != normalized else []
        topic = T2Topic(
            user_id=user_id,
            name=normalized,
            aliases=aliases,
            catalogs=catalogs or [],
            embedding=vec or [],
            importance=importance,
        )
        await self.store.upsert_topic(topic)
        self.logger.info(
            "T2:resolver: matched via=new user=%s topic=%s name=%r",
            user_id, topic.topic_id, topic.name,
        )
        return topic

    async def _attach_alias(self, topic: T2Topic, proposed_name: str) -> None:
        """Add proposed_name as alias if not already present (case-insensitive)."""
        n = _normalize(proposed_name)
        if n == topic.name:
            return
        existing = {_normalize(a) for a in topic.aliases}
        if n in existing:
            return
        await self.store.add_topic_alias(topic.user_id, topic.topic_id, proposed_name)
        topic.aliases.append(proposed_name)

    async def _llm_same_topic(
        self,
        proposed_name: str,
        best_topic: T2Topic,
        content_hint: str | None,
    ) -> bool:
        """Ask LLM whether proposed_name refers to the same topic. Default NO on error."""
        prompt = (
            "Bạn đang gộp topic ký ức. Hai cái tên này có phải CÙNG một chủ đề "
            "(không phải chỉ liên quan) không?\n\n"
            f'Topic A (đã có): "{best_topic.name}" — aliases: {best_topic.aliases}\n'
            f'Topic B (mới):  "{proposed_name}"\n'
            f"Context (nếu có): {content_hint or 'không có'}\n\n"
            "Trả ĐÚNG MỘT từ: YES hoặc NO. Không giải thích."
        )
        try:
            resp = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None,
                use_native_tools=False,
            )
            content = getattr(resp, "content", resp)
            if not isinstance(content, str):
                return False
            return content.strip().upper().startswith("YES")
        except Exception as exc:
            self.logger.warning("T2:resolver: LLM judge failed: %s", exc)
            return False
