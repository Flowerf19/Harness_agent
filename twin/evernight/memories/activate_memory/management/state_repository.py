import json
from datetime import datetime, timedelta
from typing import Any

from ..constants import SUMMARY_LOCK_TTL_MINUTES
from ..models import SummaryState, get_utc_now


class SummaryStateRepository:
    """Sidecar persistence for summary metadata."""

    def __init__(self, redis_client: Any | None = None):
        self.redis = redis_client
        self._memory: dict[str, SummaryState] = {}

    def _key(self, scope: str, scope_id: str) -> str:
        return f"summary_state:{scope}:{scope_id}"

    async def get(self, scope: str, scope_id: str) -> SummaryState:
        key = self._key(scope, scope_id)
        if self.redis is None:
            return self._memory.setdefault(key, SummaryState(scope=scope, scope_id=scope_id))

        data = await self.redis.hgetall(key)
        if not data:
            state = SummaryState(scope=scope, scope_id=scope_id)
            await self.save(state)
            return state
        if any(isinstance(k, bytes) for k in data):
            data = {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in data.items()
            }
        return SummaryState.model_validate({k: json.loads(v) for k, v in data.items()})

    async def save(self, state: SummaryState) -> None:
        key = self._key(state.scope, state.scope_id)
        if self.redis is None:
            self._memory[key] = state
            return
        data = state.model_dump(mode="json")
        await self.redis.hset(key, mapping={k: json.dumps(v) for k, v in data.items()})

    async def record_entry(self, scope: str, scope_id: str, tokens: int) -> SummaryState:
        state = await self.get(scope, scope_id)
        state.last_activity_at = get_utc_now()
        state.unsummarized_message_count += 1
        state.unsummarized_token_count += tokens
        await self.save(state)
        return state

    async def set_in_progress(
        self,
        scope: str,
        scope_id: str,
        lock_ttl_minutes: int = SUMMARY_LOCK_TTL_MINUTES,
    ) -> SummaryState:
        state = await self.get(scope, scope_id)
        state.summary_in_progress = True
        state.locked_until = get_utc_now() + timedelta(minutes=lock_ttl_minutes)
        await self.save(state)
        return state

    async def mark_completed(self, payload: dict) -> SummaryState:
        state = await self.get(payload["scope"], payload["scope_id"])
        state.last_summarized_at = get_utc_now()
        ids = payload.get("summarized_entry_ids") or []
        if ids:
            state.last_summarized_entry_id = ids[-1]
        state.unsummarized_message_count = 0
        state.unsummarized_token_count = 0
        state.summary_in_progress = False
        state.locked_until = None
        state.retry_count = 0
        await self.save(state)
        return state

    async def clear_in_progress(self, scope: str, scope_id: str) -> SummaryState:
        state = await self.get(scope, scope_id)
        state.summary_in_progress = False
        await self.save(state)
        return state

    async def set_locked_until(self, scope: str, scope_id: str, until: datetime) -> SummaryState:
        state = await self.get(scope, scope_id)
        state.locked_until = until
        state.retry_count += 1
        await self.save(state)
        return state

    async def mark_failed(self, payload: dict) -> SummaryState:
        retry_after = int(payload.get("retry_after_seconds", 600))
        await self.clear_in_progress(payload["scope"], payload["scope_id"])
        return await self.set_locked_until(
            payload["scope"],
            payload["scope_id"],
            get_utc_now() + timedelta(seconds=retry_after),
        )

    async def list_active(self, scope: str) -> list[str]:
        if self.redis is None:
            states = self._memory.values()
        else:
            states = []
            async for key in self.redis.scan_iter(self._key(scope, "*")):
                data = await self.redis.hgetall(key)
                if data:
                    if any(isinstance(k, bytes) for k in data):
                        data = {
                            (k.decode() if isinstance(k, bytes) else k): (
                                v.decode() if isinstance(v, bytes) else v
                            )
                            for k, v in data.items()
                        }
                    states.append(SummaryState.model_validate({k: json.loads(v) for k, v in data.items()}))
        return [
            state.scope_id
            for state in states
            if state.scope == scope
            and state.unsummarized_message_count > 0
            and not state.summary_in_progress
        ]
