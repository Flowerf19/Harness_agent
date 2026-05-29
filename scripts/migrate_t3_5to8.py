#!/usr/bin/env python3
"""One-shot migration from legacy 5-section T3 markdown to 8-section profile."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

SECTIONS = [
    "basic", "contact", "relationship", "work",
    "interest", "habit", "psychological", "rules",
]

SECTION_HEADERS = {
    "basic": "Thông tin cơ bản",
    "contact": "Liên hệ",
    "relationship": "Quan hệ",
    "work": "Nghề nghiệp & Học vấn",
    "interest": "Sở thích",
    "habit": "Thói quen",
    "psychological": "Tâm lý & Cảm xúc",
    "rules": "Ràng buộc & Cấm kỵ",
}

LEGACY_HEADER_DEFAULTS = {
    "thông tin cơ bản": "basic",
    "liên hệ": "contact",
    "quan hệ": "relationship",
    "nghề nghiệp & học vấn": "work",
    "sở thích": "interest",
    "thói quen": "habit",
    "tâm lý & cảm xúc": "psychological",
    "ràng buộc & cấm kỵ": "rules",
    "nghề nghiệp & xã hội": "work",
    "sở thích & thói quen": "interest",
    "ghi chú & mật mã": "rules",
}

EMPTY_PLACEHOLDER = "(chưa có)"


def _heading(line: str) -> str | None:
    stripped = line.strip()
    marker = stripped.find("## ")
    if marker < 0:
        return None
    prefix = stripped[:marker]
    if prefix and not prefix.isalpha():
        return None
    return stripped[marker + 3 :].strip().lower()


def _parse(path: Path) -> dict[str, list[str]]:
    buckets = {key: [] for key in SECTIONS}
    current = "basic"
    for raw in path.read_text(encoding="utf-8").splitlines():
        header = _heading(raw)
        if header:
            current = LEGACY_HEADER_DEFAULTS.get(header, current)
            continue
        line = raw.strip()
        if not line.startswith("- "):
            continue
        bullet = line[2:].strip()
        if not bullet or "chưa có thông tin" in bullet.lower() or bullet == EMPTY_PLACEHOLDER:
            continue
        section = _classify_bullet(current, bullet)
        if bullet not in buckets[section]:
            buckets[section].append(bullet)
    return buckets


def _classify_bullet(default: str, bullet: str) -> str:
    text = bullet.lower()
    if text.startswith("nhân khẩu học"):
        return "basic"
    if default == "rules":
        return "rules"
    if any(k in text for k in ("người quen", "bạn ", "gia đình", "người yêu", "quan hệ")):
        return "relationship"
    if any(k in text for k in ("email", "số điện thoại", "phone", "discord", "liên hệ")):
        return "contact"
    if any(k in text for k in ("nghề", "công việc", "học", "trường", "developer", "engineer")):
        return "work"
    if any(k in text for k in ("thói quen", "hay ", "thường ")):
        return "habit"
    if any(k in text for k in ("sở thích", "thích ", "game", "phim", "công nghệ")):
        return "interest"
    if any(k in text for k in ("buồn", "vui", "lo", "stress", "tâm lý", "cảm xúc")):
        return "psychological"
    if any(k in text for k in ("không ", "cấm", "ràng buộc", "pass", "mật mã", "code-name")):
        return "rules"
    return default if default in SECTIONS else "basic"


def _render(sections: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for index, key in enumerate(SECTIONS):
        lines.append(f"## {SECTION_HEADERS[key]}")
        bullets = sections.get(key) or []
        if bullets:
            lines.extend(f"- {bullet}" for bullet in bullets)
        else:
            lines.append(f"- {EMPTY_PLACEHOLDER}")
        if index != len(SECTIONS) - 1:
            lines.append("")
    return "\n".join(lines) + "\n"


def migrate_file(path: Path, *, apply: bool) -> bool:
    new_text = _render(_parse(path))
    old_text = path.read_text(encoding="utf-8")
    if new_text == old_text:
        print(f"unchanged {path}")
        return False
    if apply:
        backup = path.with_suffix(path.suffix + ".bak5")
        shutil.copy2(path, backup)
        path.write_text(new_text, encoding="utf-8")
        print(f"migrated {path} (backup: {backup})")
    else:
        print(f"would migrate {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="memories", help="Profile directory")
    parser.add_argument("--apply", action="store_true", help="Write changes")
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        raise SystemExit(f"path not found: {root}")
    changed = 0
    for path in sorted(root.glob("*.md")):
        if migrate_file(path, apply=args.apply):
            changed += 1
    print(f"{changed} file(s) {'migrated' if args.apply else 'would change'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
