import pytest

from twin.shared.observability import langsmith as observability


@pytest.mark.asyncio
async def test_traceable_noop_drops_langsmith_extra_when_tracing_is_off(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)

    @observability.traceable(name="unit.noop", run_type="chain")
    async def sample(value):
        return value

    result = await sample("ok", langsmith_extra={"metadata": {"model": "m1"}})

    assert result == "ok"


@pytest.mark.asyncio
async def test_call_with_langsmith_extra_uses_traceable_when_tracing_is_on(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    captured = {}

    def fake_traceable(**trace_kwargs):
        captured["trace_kwargs"] = trace_kwargs

        def decorator(func):
            async def wrapper(*args, **kwargs):
                captured["langsmith_extra"] = kwargs.pop("langsmith_extra", None)
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    monkeypatch.setattr(observability, "_ls_traceable", fake_traceable)

    @observability.traceable(name="unit.enabled", run_type="chain")
    async def sample(value):
        return value

    extra = observability.langsmith_extra(
        tags=["unit"],
        metadata={"workflow": "test", "model": "m1"},
    )

    result = await observability.call_with_langsmith_extra(
        sample,
        "ok",
        langsmith_extra=extra,
    )

    assert result == "ok"
    assert captured["trace_kwargs"]["name"] == "unit.enabled"
    assert captured["trace_kwargs"]["project_name"] == "march7-bot"
    assert captured["langsmith_extra"] == extra
    assert extra["metadata"]["trace_module"] == "model_semantic_0trace"


@pytest.mark.asyncio
async def test_call_with_langsmith_extra_skips_plain_functions_when_tracing_is_on(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    async def plain(value):
        return value

    result = await observability.call_with_langsmith_extra(
        plain,
        "ok",
        langsmith_extra={"metadata": {"workflow": "plain"}},
    )

    assert result == "ok"


def test_add_current_run_metadata_noop_when_tracing_is_off(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)

    def boom():
        raise AssertionError("should not be called when tracing is disabled")

    monkeypatch.setattr(observability, "get_current_run_tree", boom)

    # Must not raise even though get_current_run_tree would blow up if reached.
    observability.add_current_run_metadata({"entries_shipped": 3})


def test_add_current_run_metadata_noop_when_no_active_run(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setattr(observability, "get_current_run_tree", lambda: None)

    # No active run tree — silently does nothing, no exception.
    observability.add_current_run_metadata({"entries_shipped": 3})


def test_add_current_run_metadata_merges_into_active_run(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    captured = {}

    class FakeRunTree:
        def add_metadata(self, metadata):
            captured["metadata"] = metadata

    monkeypatch.setattr(observability, "get_current_run_tree", lambda: FakeRunTree())

    observability.add_current_run_metadata({"entries_shipped": 2, "trimmed": 0})

    assert captured["metadata"]["entries_shipped"] == 2
    assert captured["metadata"]["trimmed"] == 0
    assert captured["metadata"]["trace_module"] == "model_semantic_0trace"


def test_langsmith_extra_and_trace_output_summaries_are_compact():
    extra = observability.langsmith_extra(tags=["chat", "chat", "march7"])

    assert extra["tags"] == ["chat", "march7"]
    assert observability.summarize_trace_output("secret reply") == {
        "has_output": True,
        "output_chars": 12,
    }
    class Response:
        content = "secret reply"

    assert observability.summarize_trace_output(Response()) == {
        "result_type": "Response",
        "has_output": True,
        "output_chars": 12,
    }
