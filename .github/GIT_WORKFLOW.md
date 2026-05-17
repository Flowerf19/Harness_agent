# GIT_WORKFLOW

## Branching

- Default branch: `main`.
- Feature branches: `feature/*` (repo hiện đang ở `feature/twin-soul-agents`).

## Commits

- Ưu tiên commit nhỏ, độc lập.
- Commit messages theo khuyến nghị trong [CODING_STYLE.md](CODING_STYLE.md).

## PR expectations

- Mô tả rõ: context, change list, cách test.
- Link tới issue (nếu có).
- Không đưa secrets vào PR.

## Review checklist

### Security

- [ ] Không log/commit secrets
- [ ] Bash Executor: lệnh có an toàn, có approval gate, có timeout
- [ ] Origin validation / boundary tuân thủ (xem [docker/ARCHITECTURE.md](../docker/ARCHITECTURE.md))

### Reliability

- [ ] External calls có timeout
- [ ] Retry/backoff hợp lý cho lỗi transient
- [ ] Shutdown/cancellation cleanly (async tasks)

### Architecture

- [ ] Không phá boundary March7 ↔ Evernight
- [ ] Memory tiers vẫn đúng (T1 Redis, T2 Qdrant, T3 Markdown)

### Tests

- [ ] Unit tests cập nhật
- [ ] Integration/E2E (nếu thay đổi pipeline)

### Docs

- [ ] `.github/*` cập nhật nếu thay đổi facts/workflow
