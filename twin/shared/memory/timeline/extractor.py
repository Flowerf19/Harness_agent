"""T2 extractor — 1 LLM call to atomic-extract candidate memories from a transcript."""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from twin.shared.memory.timeline.constants import (
    EXTRACT_MAX_TOKENS,
    MAX_CANDIDATES_PER_TRANSCRIPT,
    MAX_CATALOGS_PER_MEMORY,
)
from twin.shared.memory.timeline.models import CATALOG_SET, T2Topic


def _extract_json(text: str) -> str:
    """Return the first complete, balanced JSON object found in *text*.

    Reasoning models wrap the answer in chain-of-thought prose and/or ```json
    fences. A string-aware brace scan locates the first balanced ``{...}`` and
    ignores everything around it. Truncated output (no closing brace) raises so
    the caller can retry. Raises ``ValueError`` when no object is present.
    """
    s = text or ""
    start = s.find("{")
    if start == -1:
        raise ValueError("no JSON object")

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    raise ValueError("no JSON object")


SYSTEM_PROMPT = (
    "Bạn là Memory Extractor. Đọc đoạn hội thoại, rút ra TỐI ĐA 5 ký ức atomic "
    "đáng lưu (mỗi cái 1-3 câu, độc lập). Bỏ qua xã giao, đùa, spam.\n\n"
    "Transcript có nhiều người, mỗi dòng có dạng `Tên: nội dung`. Dòng `Bot:` là "
    "của chính trợ lý (bot) — xem mục === BOT ===. Người dùng có thể gọi bot bằng "
    "biệt danh; ĐỪNG coi biệt danh đó là một người dùng và ĐỪNG tạo ký ức nhận dạng "
    "(identity) cho bot.\n\n"
    "Mỗi ký ức phải có:\n"
    "- content: 1-3 câu, atomic, viết ở ngôi thứ 3 (\"Hoà thích phim Pháp\")\n"
    "- subject: tên người mà ký ức NÓI VỀ — phải đúng một tên đứng trước dấu \":\" "
    "trong transcript (== một người trong === NGƯỜI THAM GIA ===). Không phải bot.\n"
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

# Appended on retry when the first call returns prose instead of JSON.
STRICT_JSON_SUFFIX = (
    "\n\nQUAN TRỌNG: Chỉ in JSON thuần đúng schema, bắt đầu bằng '{' và kết thúc "
    "bằng '}'. KHÔNG suy luận, KHÔNG giải thích, KHÔNG markdown fence."
)


class CandidateMemory(BaseModel):
    content: str
    subject: str = ""
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
        bot_name: str | None = None,
    ) -> ExtractResult:
        """1 LLM call to atomic-extract + classify. Returns ExtractResult (never raises)."""
        if not transcript or not transcript.strip():
            return _empty_result()

        sections = [
            "=== HỒ SƠ NGƯỜI DÙNG (T3) ===",
            t3_snapshot or "(chưa có)",
            "",
            "=== TOPIC ĐÃ CÓ (T2 glossary) ===",
            format_glossary(topic_glossary),
            "",
        ]
        if bot_name:
            sections += [
                "=== BOT ===",
                f"Trợ lý trong hội thoại tên là \"{bot_name}\" (các dòng `Bot:`). "
                "Không phải người dùng.",
                "",
            ]
        if participants:
            names = ", ".join(sorted({n for n in participants.values() if n}))
            sections += ["=== NGƯỜI THAM GIA ===", names or "(chưa rõ)", ""]
        sections += ["=== TRANSCRIPT ===", transcript]
        user_prompt = "\n".join(sections)

        # Reasoning models often answer the first call with chain-of-thought
        # prose and no JSON. Try the normal prompt, then retry once with a
        # stricter "JSON only" instruction before giving up.
        result: ExtractResult | None = None
        attempts = (SYSTEM_PROMPT, SYSTEM_PROMPT + STRICT_JSON_SUFFIX)
        for attempt, system_prompt in enumerate(attempts):
            try:
                response = await self.llm.generate_response(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    use_native_tools=False,
                    max_tokens=EXTRACT_MAX_TOKENS,
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
                break
            except Exception as exc:
                if attempt + 1 < len(attempts):
                    self.logger.info(
                        "T2:extractor: parse failed (attempt %d), retrying strict: %s",
                        attempt + 1, exc,
                    )
                    continue
                self.logger.warning(
                    "T2:extractor: JSON parse/validate failed: %s | raw=%r",
                    exc, text[:300],
                )
                return _empty_result()

        if result is None:  # defensive; loop either breaks or returns
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
