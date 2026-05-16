# TASK_WORKFLOW

Workflow khuyến nghị khi agent thực hiện một task trong repo này.

## 1) Discovery

- Xác định subsystem liên quan: `gateway/` hay `twin/march7/` hay `twin/evernight/` hay `twin/shared/`.
- Tìm tests liên quan trong `tests/unit`, `tests/integration`, `tests/e2e`.
- Đọc docs liên quan: `docker/ARCHITECTURE.md`, `README_BASH_EXECUTOR.md`.

## 2) Design

- Ghi rõ assumptions.
- Nếu phát hiện “facts” mới về repo (ports, env vars, boundaries), cập nhật `MEMORY.md`.

## 3) Implementation

- Sửa nhỏ, từng bước.
- Giữ backward compatibility nếu liên quan memory schema.
- Thêm/điều chỉnh tests.

## 4) Verification

- Chạy tests phù hợp theo `TESTING_GUIDE.md`.
- Với thay đổi runtime flow: kiểm tra docker logs/health endpoints (nếu môi trường có).

## 5) PR hygiene

- PR mô tả: vấn đề, giải pháp, cách test.
- Dán log ngắn (không chứa secrets) khi cần.
