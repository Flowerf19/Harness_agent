"""T2 extractor — 1 LLM call to atomic-extract candidate memories from a transcript."""
from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from twin.shared.memory.timeline.constants import (
    MAX_CANDIDATES_PER_TRANSCRIPT,
    MAX_CATALOGS_PER_MEMORY,
)
from twin.shared.memory.timeline.models import CATALOG_SET, T2Topic


_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```|(\{.*\})",
    re.DOTALL,
)


def _extract_json(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    m = _JSON_BLOCK_RE.search(text or "")
    if m:
        return (m.group(1) or m.group(2)).strip()
    raise ValueError("no JSON object")


SYSTEM_PROMPT = (
    "Bạn là Memory Extractor. Đọc đoạn hội thoại, rút ra TỐI ĐA 5 ký ức atomic "
    "đáng lưu (mỗi cái 1-3 câu, độc lập). Bỏ qua xã giao, đùa, spam.\n\n"
    "Mỗi ký ức phải có:\n"
    "- content: 1-3 câu, atomic, viết ở ngôi thứ 3 (\"Hoà thích phim Pháp\")\n"
    "- topic_names: 1-3 tên topic (tiếng Việt, danh từ ngắn). Ví dụ \"phim ảnh\", "
    "\"công việc dev\", \"gia đình\"\n"
    "- catalogs: 1-2 từ danh sách:\n"
    "  identity, contact, relationship, work, interest, habit, psychological,\n"
    "  rules, decision, event, emotion, discussion\n"
    "- importance: 1-5 (5 = identity/contact/critical, 1 = casual)\n"
    "- confidence: 0.0-1.0 mức độ chắc chắn của trích xuất\n"
    "- speaker: \"user\" / \"bot\" / \"joint\" (cả 2 đóng góp)\n"
    "- change_type_hint: \"new\" / \"update\" / \"correction\" / \"reinforcement\"\n\n"
    "Cũng trả thêm primary_catalog (đại diện chính cho transcript này, 1 catalog) "
    "và primary_confidence.\n\n"
    "Nếu không có gì đáng lưu → memories: [], primary_catalog: \"discussion\", "
    "primary_confidence: 0.3.\n\n"
    "Trả JSON đúng schema. Không markdown fence, không comment."
)


class CandidateMemory(BaseModel):
    content: str
    topic_names: list[str] = Field(default_factory=list)
    catalogs: list[str] = Field(default_factory=list)
    importance: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0.0, le=1.0)
    speaker: Literal["user", "bot", "joint"] = "user"
    source_msg_ids: list[str] = Field(default_factory=list)
    change_type_hint: Literal["new", "update", "correction", "reinforcement"] = "new"


class ExtractResult(BaseModel):
    memories: list[CandidateMemory] = Field(default_factory=list)
    primary_catalog: str | None = None
    primary_confidence: float = 0.0


def format_glossary(topics: list[T2Topic] | None) -> str:
    if not topics:
        return "(chưa có)"
    lines: list[str] = []
    for t in topics[:20]:
        aliases = f" (aliases: {', '.join(t.aliases)})" if t.aliases else ""
        cats = ",".join(t.catalogs) if t.catalogs else "none"
        lines.append(f"- {t.name}{aliases} [catalogs: {cats}]")
    return "\n".join(lines)


def _empty_result() -> ExtractResult:
    return ExtractResult(memories=[], primary_catalog="discussion", primary_confidence=0.0)


class Extractor:
    """1 LLM call: atomic extraction + classification."""

    def __init__(self, llm) -> None:
        self.llm = llm
        self.logger = logging.getLogger(__name__)

    async def extract(
        self,
        transcript: str,
        *,
        t3_snapshot: str = "",
        topic_glossary: list[T2Topic] | None = None,
        participants: dict[str, str] | None = None,
    ) -> ExtractResult:
        """1 LLM call to atomic-extract + classify. Returns ExtractResult (never raises)."""
        if not transcript or not transcript.strip():
            return _empty_result()

        user_prompt = (
            "=== HỒ SƠ NGƯỜI DÙNG (T3) ===\n"
            f"{t3_snapshot or '(chưa có)'}\n\n"
            "=== TOPIC ĐÃ CÓ (T2 glossary) ===\n"
            f"{format_glossary(topic_glossary)}\n\n"
            "=== TRANSCRIPT ===\n"
            f"{transcript}"
        )

        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=SYSTEM_PROMPT,
                use_native_tools=False,
            )
        except Exception as exc:
            self.logger.warning("T2:extractor: LLM call failed: %s", exc, exc_info=True)
            return _empty_result()

        text = getattr(response, "content", None)
        if not isinstance(text, str):
            text = str(response) if response is not None else ""

        try:
            json_str = _extract_json(text)
            result = ExtractResult.model_validate_json(json_str)
        except Exception as exc:
            self.logger.warning(
                "T2:extractor: JSON parse/validate failed: %s | raw=%r",
                exc, text[:300],
            )
            return _empty_result()

        # Filter + cap memories.
        cleaned: list[CandidateMemory] = []
        for cand in result.memories:
            valid_cats = [c for c in cand.catalogs if c in CATALOG_SET]
            if not valid_cats:
                self.logger.debug(
                    "T2:extractor: dropping candidate, no valid catalogs: %s",
                    cand.catalogs,
                )
                continue
            if len(valid_cats) > MAX_CATALOGS_PER_MEMORY:
                valid_cats = valid_cats[:MAX_CATALOGS_PER_MEMORY]
            cand.catalogs = valid_cats
            cleaned.append(cand)
            if len(cleaned) >= MAX_CANDIDATES_PER_TRANSCRIPT:
                break

        result.memories = cleaned
        if result.primary_catalog and result.primary_catalog not in CATALOG_SET:
            result.primary_catalog = "discussion"
        return result
