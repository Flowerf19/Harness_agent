import logging
import re
import datetime
from typing import Any

from twin.shared.memory.timeline.models import T2Memory, CATALOG_TO_T3, T3_PROMOTABLE
from twin.shared.memory.profile.markdown_store import _parse_markdown

_SPEAKER_GATED_CATALOGS = frozenset({"identity", "contact"})

class ProfilePromotionGuard:
    def __init__(self, timeline_store: Any, profile_store: Any, llm_service: Any):
        self.timeline_store = timeline_store
        self.profile_store = profile_store
        self.llm_service = llm_service
        self.logger = logging.getLogger(__name__)

    async def process_candidate(self, user_id: str, memory: T2Memory) -> dict | None:
        if memory.importance < 4 or memory.confidence < 0.8:
            return None

        raw_profile = await self.profile_store.read_raw(user_id)
        parsed_profile = _parse_markdown(raw_profile)
        total_bullets = sum(len(bullets) for bullets in parsed_profile.values())

        if total_bullets == 0:
            return await self._handle_profile_seeding(user_id, memory)
        else:
            return await self._handle_hybrid_refinement(user_id, memory, parsed_profile)

    async def _handle_profile_seeding(self, user_id: str, memory: T2Memory) -> dict | None:
        self.logger.info("T3 is empty, starting seeding accumulation")
        
        recent = await self.timeline_store.list_recent(user_id, hours=720, limit=50)
        eligible_memories = [
            m for m in recent 
            if m.importance >= 4 and m.confidence >= 0.8 and m.speaker == 'user'
        ]

        if len(eligible_memories) < 10:
            return None

        prompt = (
            "You are a psychological profiler. Consolidate the following raw memories into a structured Markdown profile.\n"
            "You MUST output ONLY Markdown using the strict headers:\n"
            "## Thông tin cơ bản\n"
            "## Liên hệ\n"
            "## Quan hệ\n"
            "## Nghề nghiệp & Học vấn\n"
            "## Sở thích\n"
            "## Thói quen\n"
            "## Tâm lý & Cảm xúc\n"
            "## Ràng buộc & Cấm kỵ\n\n"
            "Raw memories:\n"
        )
        for m in eligible_memories:
            prompt += f"- {m.content}\n"

        messages = [{"role": "user", "content": prompt}]
        response = await self.llm_service.generate_response(messages=messages)
        llm_response_text = response.content if hasattr(response, 'content') else response

        # Parse response as requested by design
        _parse_markdown(llm_response_text)
        
        await self.profile_store.write_raw(user_id, llm_response_text)
        
        self.logger.info("T3 profile seeding completed for user %s", user_id)
        
        return {
            "promoted": [{
                "section": "seeding", 
                "content": "Cold start complete", 
                "memory_id": memory.memory_id, 
                "user_id": user_id
            }]
        }

    async def _handle_hybrid_refinement(self, user_id: str, memory: T2Memory, parsed_profile: dict) -> dict | None:
        catalogs = memory.catalogs or []
        promoted = []

        for cat in catalogs:
            if cat not in T3_PROMOTABLE:
                continue
            if cat in _SPEAKER_GATED_CATALOGS and memory.speaker not in ("user", "joint"):
                self.logger.info(
                    "T3: promotion_guard refuse T3 promote of bot-sourced %s "
                    "(speaker=%s) user=%s", cat, memory.speaker, user_id,
                )
                continue

            section = CATALOG_TO_T3[cat]
            is_duplicate = False

            try:
                if hasattr(self.timeline_store, "knn_memories"):
                    similar = await self.timeline_store.knn_memories(
                        user_id, memory.embedding, k=3, catalog=cat, min_importance=4
                    )
                    similar = [(m, s) for m, s in similar if m.confidence >= 0.8 and m.speaker == 'user']

                    if similar:
                        old_mem, sim = similar[0]
                        
                        try:
                            with open("memories/semantic_trace.log", "a", encoding="utf-8") as f:
                                f.write(f"[{datetime.datetime.now().isoformat()}] SEMANTIC TRACE\n")
                                f.write(f"Query (New): {memory.content!r}\n")
                                f.write(f"Matched (Old): {old_mem.content!r}\n")
                                f.write(f"Cosine Similarity: {sim:.4f}\n")
                        except Exception:
                            pass

                        if sim >= 0.85:
                            words1 = {w for w in re.findall(r"\w+", memory.content.lower()) if w}
                            words2 = {w for w in re.findall(r"\w+", old_mem.content.lower()) if w}
                            intersection = words1 & words2
                            overlap = len(intersection) / max(len(words1), len(words2)) if (words1 and words2) else 0.0
                            
                            if overlap >= 0.65:
                                is_duplicate = True
                                self.logger.info(
                                    "T3: promotion_guard semantic duplicate detected user=%s section=%s sim=%.3f overlap=%.2f",
                                    user_id, section, sim, overlap
                                )
                                try:
                                    with open("memories/semantic_trace.log", "a", encoding="utf-8") as f:
                                        f.write(f"Token Overlap: {overlap:.2f} (>= 0.65) -> DUPLICATE DETECTED\n")
                                        f.write("-" * 50 + "\n")
                                except Exception:
                                    pass
                                
                                await self.timeline_store.mark_superseded(
                                    user_id, old_mem.memory_id, memory.memory_id, "update", "Superseded by newer T3 promotion"
                                )
                                
                                bullets = await self.profile_store.read_section(user_id, section)
                                replaced = False
                                for idx, b in enumerate(bullets):
                                    if b.strip().lower() == old_mem.content.strip().lower():
                                        bullets[idx] = memory.content
                                        replaced = True
                                        break
                                
                                if replaced:
                                    current_hash = await self.profile_store.read_raw_hash(user_id)
                                    await self.profile_store.replace_section(
                                        user_id, section, bullets, expected_profile_hash=current_hash
                                    )
                                    promoted.append({"section": section, "content": memory.content, "memory_id": memory.memory_id, "user_id": user_id})
                                    self.logger.info("T3: promotion_guard replaced old bullet in section=%s for user=%s", section, user_id)
                                else:
                                    await self.profile_store.append_raw(user_id, section, memory.content)
                                    promoted.append({"section": section, "content": memory.content, "memory_id": memory.memory_id, "user_id": user_id})

            except Exception as exc:
                self.logger.warning("T3: promotion_guard duplicate check failed section=%s: %s", section, exc)
                try:
                    with open("memories/semantic_trace.log", "a", encoding="utf-8") as f:
                        f.write(f"Check failed: {exc}\n" + "-" * 50 + "\n")
                except Exception:
                    pass

            if not is_duplicate:
                try:
                    await self.profile_store.append_raw(user_id, section, memory.content)
                    promoted.append({"section": section, "content": memory.content, "memory_id": memory.memory_id, "user_id": user_id})
                    try:
                        with open("memories/semantic_trace.log", "a", encoding="utf-8") as f:
                            f.write(f"Action: Not a duplicate (Sim < 0.85 or Overlap < 0.65). APPENDED.\n")
                            f.write("-" * 50 + "\n")
                    except Exception:
                        pass
                except Exception as exc:
                    self.logger.warning("T3: promotion_guard append failed section=%s: %s", section, exc)

        return {"promoted": promoted} if promoted else None
