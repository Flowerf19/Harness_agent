from datetime import timedelta

from twin.march7.memories.activate_memory.management.context_builder import ContextBuilder
from twin.march7.memories.activate_memory.models import MemoryEntry, get_utc_now


def test_context_builder_keeps_enough_recent_messages_for_redis_stack_sessions():
    now = get_utc_now()
    entries = [
        MemoryEntry(
            user_id="u1",
            role="user" if i % 2 == 0 else "assistant",
            content=f"message-{i}",
            tokens=1,
            timestamp=now + timedelta(seconds=i),
        )
        for i in range(30)
    ]

    context = ContextBuilder().build_context(entries, max_entries=24, max_tokens=1000)

    assert len(context) == 24
    assert context[0]["content"] == "message-6"
    assert context[-1]["content"] == "message-29"


def test_context_builder_respects_token_budget_and_keeps_chronological_order():
    now = get_utc_now()
    entries = [
        MemoryEntry(
            user_id="u1",
            role="user",
            content=f"message-{i}",
            tokens=100,
            timestamp=now + timedelta(seconds=i),
        )
        for i in range(10)
    ]

    context = ContextBuilder().build_context(entries, max_entries=32, max_tokens=350)

    assert [item["content"] for item in context] == ["message-7", "message-8", "message-9"]


def test_context_builder_keeps_latest_message_even_when_it_exceeds_budget():
    now = get_utc_now()
    entries = [
        MemoryEntry(
            user_id="u1",
            role="user",
            content="old",
            tokens=10,
            timestamp=now,
        ),
        MemoryEntry(
            user_id="u1",
            role="user",
            content="latest-long-message",
            tokens=500,
            timestamp=now + timedelta(seconds=1),
        ),
    ]

    context = ContextBuilder().build_context(entries, max_entries=32, max_tokens=100)

    assert context == [{"role": "user", "content": "latest-long-message"}]


def test_context_builder_channel_scope_prefixes_user_messages_with_author():
    entries = [
        MemoryEntry(
            scope="channel",
            scope_id="c1",
            user_id="u1",
            role="user",
            author_id="u1",
            author_name="Hoà",
            channel_id="c1",
            content="alo",
            tokens=1,
        )
    ]

    context = ContextBuilder().build_context(entries)

    assert context == [{"role": "user", "content": "Hoà: alo"}]


def test_context_builder_channel_scope_keeps_assistant_messages_clean():
    entries = [
        MemoryEntry(
            scope="channel",
            scope_id="c1",
            user_id="march7",
            role="assistant",
            author_id="march7",
            author_name="March7",
            channel_id="c1",
            content="2080 nha",
            tokens=2,
        )
    ]

    context = ContextBuilder().build_context(entries)

    assert context == [{"role": "assistant", "content": "2080 nha"}]


def test_context_builder_user_scope_unchanged():
    entries = [
        MemoryEntry(
            user_id="u1",
            role="user",
            content="hi",
            tokens=1,
        )
    ]

    context = ContextBuilder().build_context(entries)

    assert context == [{"role": "user", "content": "hi"}]


def test_context_builder_channel_scope_falls_back_to_user_id_without_author_name():
    entries = [
        MemoryEntry(
            scope="channel",
            scope_id="c1",
            user_id="u42",
            role="user",
            channel_id="c1",
            content="alo",
            tokens=1,
        )
    ]

    context = ContextBuilder().build_context(entries)

    assert context == [{"role": "user", "content": "u42: alo"}]
