# TESTING_GUIDE

Repo dùng `pytest` và phân tầng tests.

## Cấu trúc tests

- `tests/unit/`: logic đơn lẻ (queue, wiki, a2a, transport…)
- `tests/integration/`: pipeline có phụ thuộc services (Redis)
- `tests/e2e/`: full flow (chat overflow → consolidation → store)
- `tests/manual/`: scripts kiểm tra thủ công

## Gợi ý chọn tests theo thay đổi

- Sửa overflow/queue/consolidation: ưu tiên `tests/unit/*overflow*`, `tests/integration/*consolid*`, `tests/e2e/*consolid*`.
- Sửa wiki storage/merge/search: `tests/unit/wiki_*`, `tests/manual/test_search_wiki.py`.
- Sửa gateway/discord adapter: `tests/gateway/*`.

## Phụ thuộc dịch vụ

- Integration/E2E thường cần:
  - Redis
- Khuyến nghị dùng Docker để provision dễ dàng: xem [docker/README.md](../docker/README.md).
