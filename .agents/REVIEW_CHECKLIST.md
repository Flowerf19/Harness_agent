# REVIEW_CHECKLIST

Checklist review cho thay đổi trong repo này.

## Security

- [ ] Không log/commit secrets
- [ ] Bash Executor: lệnh có an toàn, có approval gate, có timeout
- [ ] Origin validation / boundary tuân thủ (xem `docker/ARCHITECTURE.md`)

## Reliability

- [ ] External calls có timeout
- [ ] Retry/backoff hợp lý cho lỗi transient
- [ ] Shutdown/cancellation cleanly (async tasks)

## Architecture

- [ ] Không phá boundary March7 ↔ Evernight
- [ ] Memory tiers vẫn đúng (T1 Redis, T2 Qdrant, T3 Markdown)

## Tests

- [ ] Unit tests cập nhật
- [ ] Integration/E2E (nếu thay đổi pipeline)

## Docs

- [ ] `.agents/*` cập nhật nếu thay đổi facts/workflow
