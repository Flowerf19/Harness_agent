"""Small LangSmith integration helpers for the bot workflow."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from functools import wraps
import inspect
import os
from typing import Any, Awaitable, Callable, Mapping

import langsmith as ls
from langsmith import traceable as _ls_traceable
from langsmith.run_helpers import get_current_run_tree


DEFAULT_PROJECT_NAME = "march7-bot"
TRACE_MODULE = "model_semantic_0trace"
_TRACEABLE_ATTR = "_march7_langsmith_traceable"


def tracing_enabled_from_env() -> bool:
    return (
        os.getenv("LANGSMITH_TRACING", "").lower() == "true"
        or os.getenv("LANGSMITH_TRACING_V2", "").lower() == "true"
        or os.getenv("LANGCHAIN_TRACING", "").lower() == "true"
        or os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
    )


def default_project_name() -> str:
    return (
        os.getenv("LANGSMITH_PROJECT")
        or os.getenv("LANGCHAIN_PROJECT")
        or DEFAULT_PROJECT_NAME
    )


def _langsmith_traceable(**kwargs: Any):
    trace_kwargs = dict(kwargs)
    trace_kwargs.setdefault("enabled", True)
    trace_kwargs.setdefault("project_name", default_project_name())
    return _ls_traceable(**trace_kwargs)


def _wrap_noop_or_langsmith(func: Callable[..., Any], trace_kwargs: dict[str, Any]):
    cached: Callable[..., Any] | None = None

    def traced_func() -> Callable[..., Any]:
        nonlocal cached
        if cached is None:
            cached = _langsmith_traceable(**trace_kwargs)(func)
        return cached

    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*f_args: Any, **f_kwargs: Any):
            if tracing_enabled_from_env():
                return await traced_func()(*f_args, **f_kwargs)
            f_kwargs.pop("langsmith_extra", None)
            return await func(*f_args, **f_kwargs)

        setattr(async_wrapper, _TRACEABLE_ATTR, True)
        return async_wrapper

    @wraps(func)
    def sync_wrapper(*f_args: Any, **f_kwargs: Any):
        if tracing_enabled_from_env():
            return traced_func()(*f_args, **f_kwargs)
        f_kwargs.pop("langsmith_extra", None)
        return func(*f_args, **f_kwargs)

    setattr(sync_wrapper, _TRACEABLE_ATTR, True)
    return sync_wrapper


def traceable(*args: Any, **kwargs: Any):
    """LangSmith ``traceable`` wrapper that is a safe no-op when tracing is off."""
    if args and callable(args[0]) and len(args) == 1 and not kwargs:
        return _wrap_noop_or_langsmith(args[0], {})

    if args:
        return _ls_traceable(*args, **kwargs)

    def decorator(func):
        return _wrap_noop_or_langsmith(func, dict(kwargs))

    return decorator


def _clean_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    cleaned: dict[str, Any] = {"trace_module": TRACE_MODULE}
    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned


def langsmith_extra(
    *,
    tags: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    name: str | None = None,
    project_name: str | None = None,
    parent: Any = None,
) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "metadata": _clean_metadata(metadata),
        "tags": list(tags or []),
        "project_name": project_name or default_project_name(),
    }
    if name:
        extra["name"] = name
    if parent is not None:
        extra["parent"] = parent
    return extra


async def call_with_langsmith_extra(
    func: Callable[..., Awaitable[Any]],
    /,
    *args: Any,
    langsmith_extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Call a traceable async function with dynamic LangSmith metadata."""
    if tracing_enabled_from_env() and langsmith_extra and _supports_langsmith_extra(func):
        return await func(*args, **kwargs, langsmith_extra=langsmith_extra)
    return await func(*args, **kwargs)


def _supports_langsmith_extra(func: Callable[..., Any]) -> bool:
    bound_func = getattr(func, "__func__", None)
    return bool(
        getattr(func, _TRACEABLE_ATTR, False)
        or (bound_func is not None and getattr(bound_func, _TRACEABLE_ATTR, False))
    )


def current_run_headers() -> dict[str, str]:
    if not tracing_enabled_from_env():
        return {}
    run_tree = get_current_run_tree()
    if not run_tree:
        return {}
    try:
        headers = run_tree.to_headers()
    except Exception:
        return {}
    return {str(key): str(value) for key, value in headers.items() if value}


def a2a_parent_headers() -> dict[str, str]:
    """Headers to carry the current LangSmith parent over A2A boundaries."""
    return current_run_headers()


@contextmanager
def tracing_context_from_parent(parent: Mapping[str, str] | None):
    if not parent or not tracing_enabled_from_env():
        with nullcontext():
            yield
        return
    with ls.tracing_context(parent=parent):
        yield
