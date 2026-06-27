# System Gateway generic-shell refactor — handoff note

Ngày: 2026-06-27. Branch: `feat/agent-action-loop`. Refactor collapse 5
structured read-only actions → 1 generic `mode=shell` (LLM viết lệnh OS,
owner duyệt raw command, gateway chạy). Plan gốc:
`/home/flowerf/.claude/plans/transient-bubbling-moon.md`.

## Fact kiến trúc QUAN TRỌNG (đừng lặp sai)

1. **Gateway ≠ A2A.** Tool `host_system` gọi System Gateway **trực tiếp** qua
   `HostGatewayClient` (HTTP HMAC, port 8380), KHÔNG qua A2A (`tasks/send`
   port 8000). A2A là interface nội bộ riêng.
2. **Approval DM path**: Discord adapter (`gateway/adapters/discord/adapter.py:134`,
   `handler.py:50`, `evernight_adapter.py:193`) gọi
   `set_current_approval_context(...)` trước khi vào agent → tool gọi
   `approval_gate.check_approval` → `dm_client.request_approval` → POST
   sang Evernight `/dm` type=approval → `DMApproveView` (nút Approve/Reject) →
   DM pop. **A2A `tasks/send` KHÔNG set approval context** →
   `get_current_approval_context()` = None → "No approval context, rejecting"
   → **KHÔNG pop DM**.
   → **Không test DM popup qua A2A.** Chỉ test qua Discord UI thật.
3. **Tool description = guide.md single-source.** `DeclaredToolProxy.__init__`
   override `description = read_tool_description(...)` = **dòng đầu tiên**
   (`splitlines()[0]`) của block `<tool_description>` trong
   `twin/shared/tools/prompts/guides/<tool>.md`. Dòng đầu này →
   (a) schema `description` trong `tools=[...]` gửi LLM ở **Decide**, và
   (b) catalog line trong system prompt. **Body đầy đủ** của guide chỉ nạp ở
   **Refine** qua `render_tool_guide`.
   - `DeclaredToolProxy._description` **cache ở bootstrap** → sửa guide.md
     phải **restart container** mới cập nhật schema description. Catalog line
     thì `render_catalog` đọc fresh mỗi call (no restart).
   - → Fix Decide-stage: sửa **dòng đầu `<tool_description>`** (1 dòng hoàn
     chỉnh, không wrap 2 dòng — sẽ bị truncate).

## Bug đã fix trong session này

### A. guide ↔ schema desync (root cause "trước refactor hoạt động, sau không pop DM")
- Refactor đổi `parameters_schema` enum `["capabilities","action","shell"]` →
  `["capabilities","shell"]`, xóa branch `mode=action` + `_run_action` +
  `GatewayActionRequest`.
- Nhưng `host_system.md` vẫn dạy `mode=action action=system.status`.
- → Bot (theo guide) gọi `mode=action` → `execute()` rơi
  `return "Lỗi: mode phải là capabilities hoặc shell."` **TRƯỚC** `check_approval`
  → không tới gate → **không pop DM**. LLM-side regression, không phải tool.
- **Fixed**: `host_system.md` dạy `mode=shell` only, schema enum khớp.

### B. `<tool_description>` bị truncate
- Dòng đầu guide rewrite thành 2 dòng vật lý → `read_tool_description` lấy
  `splitlines()[0]` → schema description ở Decide bị cắt giữa câu
  ("...chạy lệnh shell trên"). Suy yếu chọn tool.
- **Fixed**: dòng đầu giờ 1 dòng chỉ thị hoàn chỉnh:
  `"Tool MỌI câu hỏi/thao tác sự thật về host (...) qua System Gateway: gọi
  mode=shell với lệnh OS phù hợp, owner duyệt đúng lệnh đó — BẮT BUỘC gọi tool
  này cho query host, KHÔNG bịa số liệu host từ trí nhớ."`
- Đã verify schema description march7 load đúng (sau restart).

## Trạng thái verify

- Unit: 33 test approval + host_system + adapter xanh. Full gateway suite 120
  xanh (trước session). `tool_prompt_catalog_test`, `agent_loop_test`,
  `chat_turn_runner_test` xanh (33).
- Manual gateway: `curl /capabilities` → `raw_shell:true`,
  `structured_actions:[]`, `features:["generic_shell_exec"]`. `/shell/run` HMAC
  → HTTP 200 trả uptime thật. `/actions/run` → 404.
- **KHÔNG verify được** DM pop + Approve happy-path — cần UI Discord.

## Issue mở (cần agent test UI xác nhận / fix tiếp)

1. **Decide-stage skip rate**: A2A đo ~40% nhưng **bị ô nhiễm** (A2A luôn
   reject approval → bot tích lũy "host_system hỏng" → skip/refuse ở run sau;
   thậm chí Refine trả `action:respond` "kẹt trạm gác, chạy uptime tay đi").
   → Phải đo qua Discord UI (approval hoạt động). Persona `SOUL.md`
   `## Quy tắc gọi Tool` ("Gọi đúng-đủ-tiết kiệm", "Kiểm tra Core Memory TRƯỚC
   khi gọi tool") có thể bias skip → nếu skip rate cao ở UI, cân nhắc sửa
   SOUL.md (KHÔNG thêm rule system-prompt — user chọn guide.md single-source).
2. **Refine JSON "Extra data"**: LLM thỉnh thoảng emit 2 JSON object dính nhau
   (`{"action":"respond",...}\n{"actio...}`) → `parse_refine_decision`
   (`contract.py`) lỗi "Extra data" → `stopped_by="error"`. Bug robustness
   parser, ngoài scope refactor. Note để fix sau.
3. **Còn docs chưa update** (Task #6 dở): `gateway_admin.md` (doctor không
   list 5 capability), `services/system_gateway/README.md`, `ARCHITECTURE.md`
   (§routes, §action list), `.agents/PROJECT_CONTEXT.md`. `host_system.md`
   ĐÃ xong.

## Env / runtime gotcha (cho agent test)

- **Mỗi Bash call = shell riêng, env KHÔNG persist.** Source .env + absolute
  path trong **1 lệnh**:
  ```bash
  set -a && source /home/flowerf/Projects/march7/.env && set +a \
    && cd /home/flowerf/Projects/march7 && <cmd>
  ```
- **Restart gateway bản mới** trước test (code mới):
  ```bash
  set -a && source /home/flowerf/Projects/march7/.env && set +a \
    && cd /home/flowerf/Projects/march7 \
    && /home/flowerf/.conda/envs/discord_bot/bin/python -m system_gateway run
  ```
  Verify bản mới: `curl -s http://localhost:8380/capabilities` thấy
  `structured_actions:[]`.
- **Sửa Python code hoặc guide.md → restart march7 container** (schema
  description cache ở bootstrap). `docker compose -f docker/docker-compose.yml
  restart march7`. Không dùng `docker/march7/docker-compose.yml` riêng (lỗi
  "unknown service 'base'") — dùng root `docker/docker-compose.yml`.
- **Không in secret/token ra report.** `tests/e2e/screenshots/` gitignored.

## Plan test UI

`.agents/plans/e2e-test-system-gateway/plan-generic-shell.md` — 8 kịch bản
GĐ1-GĐ8 browser-driven qua chrome-devtools MCP. Critical:
- GĐ2 (read: Approve uptime → output thật, cross-check host).
- GĐ3 (write: ghi `/tmp/gw_e2e.txt` → file tồn tại thật trên host — regression
  Gap #6).
- GĐ5 (approval DM hiện raw command đầy đủ).
- GĐ7.2 (đo skip rate — quan sát, ghi số).