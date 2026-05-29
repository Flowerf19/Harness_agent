"""Fast-path regex detector for T3-promotable T2 catalogs.

Checks user messages for cheap signals that indicate identity-class information
worth extracting eagerly (Phase 4 LLM step uses this to decide when to fire
extra extraction outside the normal token-threshold flow).
"""
from __future__ import annotations

import re

# Priority order from spec: identity > contact > rules > work > relationship >
# psychological > habit > interest.
# Exception: a hard contact signal (email/phone/discord-id regex) beats the
# softer identity phrases ("tôi là ...") so "email tôi là a@b.com" is
# classified as contact, not identity.
_HARD_CONTACT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\S+@\S+\.\S+"),
    re.compile(r"\b0\d{9}\b"),
    re.compile(r"(?:id\s*discord|discord)[^\d]{0,20}\b\d{17,20}\b", re.IGNORECASE),
]

_PATTERNS: list[tuple[str, list[re.Pattern[str]]]] = [
    (
        "identity",
        [
            re.compile(r"\b(t[êe]n l[àa]|t[ôo]i l[àa]|tao l[àa]|em l[àa])\b", re.IGNORECASE),
            re.compile(r"\b(tu[ổo]i|n[ăa]m sinh|sinh n[ăa]m|qu[êe]|s[ôố]ng [ởo])\b", re.IGNORECASE),
        ],
    ),
    (
        "contact",
        [
            *_HARD_CONTACT_PATTERNS,
            re.compile(r"\bs[đd]t\b", re.IGNORECASE),
            re.compile(r"\bemail\b", re.IGNORECASE),
        ],
    ),
    (
        "rules",
        [
            re.compile(r"\b(kh[ôo]ng th[íi]ch|gh[ée]t|c[ấa]m|đ[ừu]ng|kh[ôo]ng đ[ưu][ợo]c|taboo|ki[êe]ng)\b", re.IGNORECASE),
        ],
    ),
    (
        "work",
        [
            re.compile(r"\b(l[àa]m [ởo]|đang l[àa]m|c[ôo]ng ty|c[ôo]ng vi[ệe]c|d[ựu] [áa]n|side project|freelance)\b", re.IGNORECASE),
        ],
    ),
    (
        "relationship",
        [
            re.compile(r"\b(b[ạa]n c[ủu]a|b[ạa]n th[âa]n|anh em|v[ợo]|ch[ồo]ng|ng[ưu][ờo]i y[êe]u|crush)\b", re.IGNORECASE),
        ],
    ),
    (
        "psychological",
        [
            re.compile(r"b[ịi]\s+(lo [âa]u|tr[ầa]m c[ảa]m|stress|MBTI)", re.IGNORECASE),
            re.compile(r"\bt[íi]nh c[áa]ch\b", re.IGNORECASE),
            # 4-letter MBTI codes
            re.compile(r"\b(?:I|E)(?:N|S)(?:T|F)(?:J|P)\b"),
        ],
    ),
    (
        "habit",
        [
            re.compile(r"\b(th[ưu][ờo]ng|hay|lu[ôo]n lu[ôo]n|kh[ôo]ng bao gi[ờo]|m[ỗo]i ng[àa]y|m[ỗo]i tu[ầa]n)\b", re.IGNORECASE),
        ],
    ),
    (
        "interest",
        [
            re.compile(r"\b(th[íi]ch|s[ởo] th[íi]ch|m[êe]|fan c[ủu]a|h[âa]m m[ộo])\b", re.IGNORECASE),
        ],
    ),
]


class FastPathDetector:
    """Detect promotable-catalog signals in user content using regex."""

    def is_critical(self, content: str) -> str | None:
        """Return the first matching catalog or None."""
        if not content:
            return None
        # Hard contact signals win over identity phrases regardless of order.
        for pat in _HARD_CONTACT_PATTERNS:
            if pat.search(content):
                return "contact"
        for catalog, patterns in _PATTERNS:
            for pat in patterns:
                if pat.search(content):
                    return catalog
        return None
