# CODING_STYLE

Tài liệu này mô tả conventions khi chỉnh sửa code trong repo.

## Python style (baseline)

- Ưu tiên code rõ ràng, ít “magic”.
- Tránh side effects ở import time.
- Docstrings ngắn, mô tả “why” hơn “what”.

## Async conventions

- I/O (HTTP/Discord/Redis/Qdrant) ưu tiên async.
- Mọi call ra ngoài cần có **timeout**.
- Khi có background tasks: xử lý cancellation và shutdown cleanly.

## Typing

- Dùng type hints cho public functions/methods.
- Ưu tiên `str | None` thay vì `Optional[str]` (Python 3.10+).
- Dùng `dataclass` cho config/models đơn giản.

## Logging

- Log đủ ngữ cảnh để debug (user_id, agent_name, request_id nếu có).
- Tuyệt đối không log secrets (tokens, full env files, credentials).
- Khi bắt exception: log stack trace khi hữu ích.

## Error handling / retries

- External services có thể fail: Discord, LLM providers, Redis, Qdrant.
- Với lỗi transient: cân nhắc retry có backoff.
- Với lỗi cấu hình: fail fast + log actionable message.

## Project structure conventions

- `gateway/`: platform adapters + routing.
- `twin/march7/`, `twin/evernight/`: agent-owned code.
- `twin/shared/`: code dùng chung (A2A, tools, memories, llm).

## Formatting / linting / type-check

Hiện repo **không thấy** cấu hình `pyproject.toml`, `ruff.toml`, `setup.cfg`, `.pre-commit-config.yaml` ở root.

- Không tự ý áp dụng formatter/linter mới trên toàn repo nếu user không yêu cầu.
- Nếu cần thêm tooling (ruff/black/mypy/pre-commit), tạo PR riêng hoặc commit riêng.

## Commit message conventions (khuyến nghị)

- Dùng format: `type(scope): message`
  - types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- Message 1 dòng, cụ thể.
