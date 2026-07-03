"""VN (Asia/Ho_Chi_Minh) calendar-day helpers.

Shared by the T2 diary model (timeline_summary_store.py) and the T1
archive-on-trim path (active/store.py) — both need to agree on the exact
same "what day is this" answer (T2 diary plan architecture decision #2: day
boundary is Asia/Ho_Chi_Minh, computed from the entry/conversation
timestamp, not wall-clock consolidation time). Centralizing here means one
ZoneInfo lookup and no risk of the two layers drifting on the definition of
"day".
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def vn_now() -> datetime:
    """Current time as a VN-local aware datetime."""
    return datetime.now(VN_TZ)


def vn_day_str(ts: float) -> str:
    """VN-local calendar day (YYYY-MM-DD) for a UTC epoch timestamp."""
    return datetime.fromtimestamp(ts, tz=VN_TZ).strftime("%Y-%m-%d")
