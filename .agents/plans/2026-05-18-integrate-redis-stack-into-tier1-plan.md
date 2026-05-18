## Plan: Tích hợp Redis Stack vào T1 và quyết định đồng bộ với T2

TL;DR: Mục tiêu là đưa T1 từ cơ chế scan/list hiện tại sang truy vấn có chỉ mục (Redis Stack) cho các luồng đọc nóng, nhưng không “đồng bộ 1:1” với T2 vì vai trò hai tầng khác nhau. Cách làm an toàn là áp dụng theo pha: chuẩn hóa schema + dual-write + shadow-read + cutover có đo lường, giữ nguyên boundary March7↔Evernight và không làm đổi semantics cleanup/consolidation.

**Steps**
1. Xác nhận baseline kỹ thuật và ràng buộc runtime
   - Đọc và chốt các nguồn sự thật: `.agents/ARCHITECTURE.md`, `.agents/PROJECT_CONTEXT.md`, `docker/ARCHITECTURE.md`.
   - Chốt phạm vi: chỉ đổi T1 trong `twin/march7/memories/activate_memory/*`; không đổi hợp đồng A2A `get_snapshot`/`clear_session`.
   - Kiểm tra phiên bản Redis/Redis Stack thực tế đang chạy bằng `redis INFO server` + `MODULE LIST` trong môi trường Docker hiện tại.
   - Test-first: thêm test smoke xác nhận môi trường test có/không có module Search và app fallback đúng.

2. Thiết kế schema/index cho T1 (khác T2, không copy nguyên mẫu)
   - Định nghĩa keyspace T1 có namespace riêng (vd `t1:msg:{user_id}:{message_id}`) + metadata phục vụ context window: `role`, `content`, `created_at_ts`, `token_count`, `session_id`.
   - Thiết kế index tối thiểu cho truy vấn T1: lọc theo `user_id/session_id`, sort theo `created_at_ts` để lấy N tin gần nhất cho context builder.
   - Không thêm vector/semantic ở T1 giai đoạn đầu (YAGNI), vì semantic đã thuộc T2 (`twin/shared/memories/t2/*`).
   - Test-first: viết test schema contract cho serialize/deserialize `MemoryEntry` và thứ tự kết quả truy vấn gần nhất.

3. Bổ sung storage adapter T1-RedisStack và giữ backward compatibility
   - Tạo adapter mới cạnh `redis_storage.py` (vd `redis_stack_storage.py`) implement cùng interface của `BaseStorage`.
   - Hỗ trợ dual path:
     - Nếu Search module sẵn sàng: dùng JSON + FT index.
     - Nếu không: fallback về adapter Redis hiện tại hoặc RAM (`LocalMemoryDB`) như behavior cũ.
   - Update wiring ở `twin/march7/container.py::_get_t1_storage()` bằng phase flag `T1_STORAGE_PHASE` (`redis_stack` / `legacy`).
   - Test-first: unit test cho initialize index idempotent, add/list/reset session, force cleanup.

4. Shadow-read + cutover an toàn
   - Pha A (dual-write, read-old): ghi cả storage cũ và storage mới; đọc vẫn từ cũ.
   - Pha B (dual-write, shadow-read): đọc chính từ cũ, đọc phụ từ mới để so sánh parity (count, order, last N messages), chỉ log mismatch.
   - Pha C (read-new): chuyển đọc chính sang Redis Stack; giữ dual-write thêm 1 chu kỳ release.
   - Pha D: tắt write-old sau khi metrics ổn định.
   - Test-first: integration test parity cho cùng input conversation → context output giống nhau.

5. Giữ đúng boundary với T2/Evernight (trả lời câu hỏi “có nên đồng bộ như T2 không?”)
   - Không đồng bộ data model/TTL/scoring 1:1 với T2:
     - T1 = working memory ngắn hạn, tối ưu append + recent-window.
     - T2 = episodic/wiki dài hạn, semantic retrieval + relevance.
   - Chỉ đồng bộ ở mức chuẩn kỹ thuật vận hành:
     - convention key naming,
     - index bootstrap idempotent,
     - health check và logging format,
     - feature-flag rollout pattern.
   - Giữ logic overflow queue và consolidation trigger trong `MemoryManager` không đổi semantics.
   - Test-first: regression test cho overflow event `TOKEN_LIMIT_REACHED` và enqueue behavior.

6. Migrate dữ liệu T1 hiện hữu (nếu cần)
   - Viết script migrate một chiều: đọc T1 legacy keys theo user/session, ghi sang keyspace mới có timestamp ổn định.
   - Chạy dry-run ở staging, validate checksum số bản ghi theo user.
   - Không migrate dữ liệu đã quá TTL để tránh tăng tải vô ích.
   - Test-first: test migration mapping (idempotent, không duplicate trên lần chạy lại).

7. Quan sát, rollback, và hardening
   - Thêm metric/telemetry:
     - latency lấy context T1,
     - tỷ lệ lỗi query/index,
     - mismatch shadow-read,
     - thời gian cleanup/reset session.
    - Định nghĩa rollback tức thời bằng phase flag:
       - rollback cứng: `T1_STORAGE_PHASE=legacy`
   - Bổ sung runbook sự cố vào docs.
   - Test-first: integration test mô phỏng Redis Stack unavailable → fallback hoạt động.

8. Cập nhật tài liệu + checklist release
   - Cập nhật `README.MD` (memory tier notes), `.agents/ARCHITECTURE.md` (T1 implementation detail), `.agents/PROJECT_CONTEXT.md` (env flags mới), `docker/ARCHITECTURE.md` nếu có thay đổi vận hành.
   - Chuẩn bị checklist release theo batch nhỏ: canary user cohort → full rollout.

**Relevant files**
- `/home/flowerf/Projects/march7/twin/march7/container.py` — wiring storage T1, feature flags, fallback path.
- `/home/flowerf/Projects/march7/twin/march7/memories/activate_memory/storage/base_storage.py` — contract interface cho adapter mới.
- `/home/flowerf/Projects/march7/twin/march7/memories/activate_memory/storage/redis_storage.py` — behavior legacy để dual-write/fallback.
- `/home/flowerf/Projects/march7/twin/march7/memories/activate_memory/storage/ram_storage.py` — fallback local path cần giữ nguyên.
- `/home/flowerf/Projects/march7/twin/march7/memories/activate_memory/activate_memory_service.py` — luồng add/get_context/cleanup chịu ảnh hưởng gián tiếp.
- `/home/flowerf/Projects/march7/twin/march7/memories/memory_manager.py` — overflow trigger/cleanup semantics phải regression-safe.
- `/home/flowerf/Projects/march7/twin/shared/memories/t2/store.py` — tham chiếu pattern index bootstrap/idempotent của T2 (chỉ tái dùng pattern vận hành, không copy model).
- `/home/flowerf/Projects/march7/tests/unit/` — unit tests cho adapter và service T1.
- `/home/flowerf/Projects/march7/tests/integration/` — parity + fallback integration tests.
- `/home/flowerf/Projects/march7/.agents/ARCHITECTURE.md` — cập nhật thiết kế sau triển khai.
- `/home/flowerf/Projects/march7/.agents/PROJECT_CONTEXT.md` — cập nhật biến môi trường/rollout.
- `/home/flowerf/Projects/march7/README.MD` — cập nhật mô tả kiến trúc memory tiers.

**Verification**
1. `pytest tests/unit/ -v -k "t1 or memory or redis"` → tất cả test T1 mới/cũ pass.
2. `pytest tests/integration/ -v -k "overflow or consolidation or memory"` → parity và fallback pass.
3. `docker compose -f docker/docker-compose.yml up -d --build` → services khởi động thành công.
4. `docker compose -f docker/docker-compose.yml logs -f march7 evernight` → không có lỗi FT/JSON/index init trong boot.
5. (Staging) chạy shadow-read metrics 24h → mismatch rate trong ngưỡng chấp nhận (ví dụ <1%).

**Decisions**
- Included: kế hoạch tích hợp Redis Stack cho T1 theo rollout an toàn, test-first, có fallback.
- Excluded: thay đổi data model T2, thay đổi boundary A2A, thay đổi logic consolidation Evernight.
- Trả lời câu hỏi: **Không nên đồng bộ T1 dùng “y như T2” ở mức nghiệp vụ**; chỉ nên đồng bộ **pattern hạ tầng** (index bootstrap, flags, observability, rollback).
- Assumptions: Redis Stack module (`FT`, `JSON`) có thể bật trong runtime đích; nếu không có, hệ thống phải fallback path hiện tại.
