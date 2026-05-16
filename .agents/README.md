# Agent Docs Index (.agents)

Bộ tài liệu trong thư mục `.agents/` được viết **chỉ để agent đọc** (Copilot/LLM agent), nhằm giúp:

- Hiểu dự án chạy như thế nào (Docker/local/test env)
- Nắm kiến trúc Twin-Soul (Gateway + March7 + Evernight)
- Làm việc đúng workflow (task → code → test → PR)
- Tránh sai lầm phổ biến (secrets, Bash Executor, boundary A2A)

## Thứ tự đọc khuyến nghị

1) `AGENT_RULES.md` — luật an toàn và boundary
2) `PROJECT_CONTEXT.md` — cách chạy dự án (Docker/local/conda-test)
3) `ARCHITECTURE.md` — kiến trúc + luồng chạy + memory tiers
4) `TASK_WORKFLOW.md` — cách triển khai task trong repo này
5) `TESTING_GUIDE.md` — cách chọn/chạy tests
6) `CODING_STYLE.md` — coding conventions (rất chi tiết)
7) `GIT_WORKFLOW.md` + `REVIEW_CHECKLIST.md` — chuẩn commit/PR/review
8) `MEMORY.md` — “facts” bền vững về repo (đã verify)
9) `GLOSSARY.md` — thuật ngữ

## 5 phút để bắt đầu (agent)

- Cách chạy khuyến nghị: đọc `PROJECT_CONTEXT.md` (Docker Compose primary).
- Docker ownership map: xem `docker/ARCHITECTURE.md`.
- Bash Executor cực nhạy: đọc `README_BASH_EXECUTOR.md` trước khi đề xuất dùng.

## Nguồn tham chiếu chính (human docs)

- `README.MD` — overview + quick start
- `docker/README.md` — vận hành Docker/Compose
- `docker/ARCHITECTURE.md` — boundary/ownership services
- `README_BASH_EXECUTOR.md` — security + setup Bash Executor
