---
status: ready-for-handoff
created: 2026-06-27
owner: review-handoff (minimax)
supersedes: plan-generic-shell.md (round 1, 2026-06-27 11:00)
style: browser-driven E2E via chrome-devtools MCP — drive real Discord web UI,
  type messages, click Approve/Reject by hand, observe bot replies. KHÔNG phải
  pytest suite.
test_channel: 1487427038280421456 (🤖｜bé-bảy) trong server 1067690340359880724
approval_dm: Evernight DM 1503774194440212571
owner_discord_id: 726302130318868500
owner_llm: minimax-m3:cloud (LM Studio) bind 0.0.0.0
---

# E2E Test Plan — System Gateway generic-shell (Round 2)

## 0. Mục tiêu round 2 (KHÁC round 1 ở chỗ nào)

**Round 1 (2026-06-27 11:00)** đã verify:
- ✅ Infrastructure generic-shell hoạt động: `/capabilities` đúng shape, `/actions/run` 404, approval DM hiện raw command.
- ✅ 1/7 attempt LLM gọi tool thật (G2.1 v3).
- ❌ **5/7 attempt LLM hallucinate** — không gọi tool nhưng tự tin trả lời. Gap #6 (file write) + Gap #MỚI-A (Evernight doctor nói "5 capabilities").
- ⚠️ Không test được GĐ3, GĐ4, GĐ5, GĐ7 vì LLM skip tool.

**Round 2 — mục tiêu**:

1. **Re-verify infrastructure vẫn còn nguyên** sau khi rebuild container / restart gateway (nếu có). Không sửa code.
2. **Đo lại skip rate / hallucination rate** của LLM với cùng 8 kịch bản round 1.
3. **Bắt buộc phải test được GĐ3 (write file) + GĐ4 (reject) + GĐ5 (raw command transparency)** — round 1 không test được vì LLM skip tool. Nếu LLM vẫn skip, **flag rõ ràng** trong report, KHÔNG đánh fail (ngoài scope E2E).
4. **Tuyệt đối KHÔNG đụng vào prompt, guide.md, SOUL.md, ARCHITECTURE.md, system prompt LLM.** Những thứ đó là sub-task riêng giữa user ↔ Claude sửa, E2E chỉ đo hiện trạng, không can thiệp.

**Vì sao bỏ qua prompt**: refactor infrastructure đã ổn (G2.1 v3 chứng minh khi LLM gọi tool → output thật). Root cause hallucination là LLM-side (no `tool_choice`, temperature, weak catalog line) — nằm ngoài scope E2E test. Test này đo hiện trạng, không phải fix.

**Pass/fail round 2**:

- **Pass**: infrastructure nguyên vẹn (G1.1, G1.2, G2.1 v3 pattern, G6.1/G6.2 doctor) + LLM có thể gọi tool khi user intent rõ ràng.
- **Flag (không fail)**: skip rate vẫn cao, G3/G4/G5/G7 không test được → ghi số, để LLM-side sub-task xử lý.
- **Fail**: infrastructure regress (vd `/actions/run` không 404, `/capabilities` sai shape, approval DM không hiện raw command).

## 1. Phạm vi (giống round 1)

| Trong scope (UI E2E) | Ngoài scope |
|---|---|
| Mở Discord web, gõ msg cho March7/Evernight, bấm Approve/Reject | Unit/security server-side (HMAC, replay, expiry, skew, oversized, missing-secret) |
| Quan sát approval DM hiện **raw command** đúng | pytest suite (đã có 120 test green) |
| Cross-check reply vs host thật (`uptime`, `cat /tmp/...`, `docker ps`) | systemd unit / packaging |
| Evernight `gateway_admin` doctor qua DM | raw-shell kill-switch server-side |
| Đo skip rate / hallucination rate LLM | **Sửa prompt / SOUL.md / guide.md / system prompt** (sub-task riêng) |
| Evidence pack: screenshots + report | **Sửa anti-hallucination section trong guide** (sub-task riêng) |
| | **Refactor 8 file multi-line → Convention A** (sub-task riêng) |

## 2. Điều kiện tiên quyết (giống round 1)

1. Host Linux, có `docker`, conda env `discord_bot`.
2. **System Gateway đang chạy, bind 0.0.0.0**, `curl -sf http://localhost:8380/health` → 200.
   - **`.env` ở repo root** (`/home/flowerf/Projects/march7/.env`) đã set
     `SYSTEM_GATEWAY_HOST=0.0.0.0`, `SYSTEM_GATEWAY_PORT=8380`,
     `SYSTEM_GATEWAY_SHARED_SECRET` (43 chars).
   - Phải restart gateway nếu bản cũ còn chạy. **Lưu ý Bash tool**: mỗi Bash
     call là shell riêng, env KHÔNG persist giữa calls. Bắt buộc gộp thành **1 lệnh
     duy nhất** với absolute path:
     ```bash
     set -a && source /home/flowerf/Projects/march7/.env && set +a \
       && cd /home/flowerf/Projects/march7 \
       && /home/flowerf/.conda/envs/discord_bot/bin/python -m system_gateway run
     ```
     (chạy ở fg, hoặc thêm `&` / `nohup ... &` để background. Verify:
     `curl -s http://localhost:8380/capabilities` thấy `raw_shell:true`,
     `structured_actions:[]` = bản mới.)
   - Nếu gateway cũ (process round 1) còn chạy → kill (`pkill -f system_gateway`)
     rồi chạy bản mới.
3. **Bots đang chạy** (march7 + evernight), `docker compose ps` healthy, container
   có `SYSTEM_GATEWAY_URL=http://host.docker.internal:8380` + secret khớp `.env`.
4. Chrome instance đã login Discord owner (`726302130318868500`). Chưa login → skip
   toàn bộ UI, ghi lý do.
5. Kênh/DM test riêng (không spam kênh chung).
6. Không in token/secret ra report. Screenshot che token.
7. **Container march7 đã được sửa 2 chỗ code + 1 env** trước round 2:
   - `twin/shared/llm/openai_service.py` payload: thêm `reasoning_effort` (đọc
     từ `Config.LLM_REASONING_EFFORT`).
   - `twin/shared/llm/openai_service.py` line 118+: đọc đúng field
     `reasoning` (Ollama proxy) → fallback `reasoning_details` → fallback
     `reasoning_content` (legacy).
   - `twin/shared/config/settings.py:51-65`: thêm `LLM_REASONING_EFFORT`
     với validation enum (`""`/`none`/`low`/`medium`/`high`/`max`); empty →
     `None` (không gửi field, model tự quyết).
   - `.env`: `LLM_REASONING_EFFORT=high`.
   Container `march7` recreated lúc 2026-06-27 16:33 UTC+7, healthy.
   Khi LLM skip tool, LangSmith trace giờ sẽ có `reasoning` field thật trong
   message metadata → dễ debug tại sao model quyết skip.

## 3. Driver: chrome-devtools MCP (giống round 1)

Công cụ: `list_pages`/`new_page`/`navigate_page`, `take_snapshot` (a11y tree → uid),
`fill`/`type_text`/`click`, `wait_for` (text cụ thể), `take_screenshot`,
`evaluate_script` (assert DOM). Uid đổi mỗi snapshot → snapshot lại trước click.

## 4. Kịch bản (GIỐNG round 1, có bổ sung metric đo skip rate)

### GĐ1 — Setup & smoke
- **G1.1** Host: `curl -s http://localhost:8380/capabilities` → JSON có
  `"raw_shell": true`, `"shells": ["/bin/sh"]`, `"features": ["generic_shell_exec"]`,
  `"structured_actions": []`. **Assert cả 4**. Chụp output.
  → **Pass nếu**: 4/4 field đúng. **Fail nếu**: bất kỳ field nào sai (regression).
- **G1.2** `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8380/actions/run` →
  phải **404** (route biến mất).
  → **Pass nếu**: 404. **Fail nếu**: 200/405/500 (regression).
- **G1.3** Container reach: `docker compose exec march7 curl -sf
  http://host.docker.internal:8380/health` → 200. Skip nếu compose không chạy được.
- **G1.4** Mở Discord web, owner đã login, snapshot kênh test, input box sẵn sàng.

### GĐ2 — Read command: Approve happy path (core, đo skip rate)
- **G2.1** Kênh/DM test, gõ: *"Bảy ơi xem uptime của host giúp tớ"* (kích
  `host_system mode=shell`, command tự sinh ≈ `uptime`).
- **G2.1a** **Ghi lại**: bot có gọi tool không? (đếm trong log:
  `discord_bot.OpenAIService returned 1 tool calls` = CÓ; `Output tokens: N` only
  = KHÔNG). Round 1 = 1/3 CÓ.
- **G2.2** Nếu CÓ: `wait_for` Evernight DM hiện approval. **Assert approval text có
  dạng `host shell: <command>`** (raw command, KHÔNG phải `host action: ...`).
  Screenshot DM. Snapshot lấy uid nút **Approve**.
- **G2.3** Click Approve.
- **G2.4** `wait_for` March7 reply chứa output `uptime` thật (vd `load average`,
  `up X days`). Screenshot. **Assert reply có "Output từ tool:"** HOẶC số liệu
  thật, KHÔNG bịa "11 ngày" (gap #1 round 1).
- **G2.5** Cross-check: chạy `uptime` trên host song song → so sánh. Khớp = gateway
  chạm host thật.
- **G2.6** Nếu KHÔNG (G2.1a = skip): bot reply hallucinate → ghi lại nội dung reply,
  cross-check với host. **Skip rest of GĐ2**, flag "LLM skip tool, không test được
  Approve path". Round 1: 2/3 attempts skip.
- **G2.7** (Bổ sung) Lặp lại G2.1 3 lần (cùng prompt) → ghi lại skip rate.
  Round 1: 1/3 (33%) → round 2: ???

### GĐ3 — Write command: ex-lie case (CRITICAL — regression của Gap #6)
- **G3.1** Trước test: xác nhận `/tmp/gw_e2e.txt` **chưa tồn tại** (`ls /tmp/gw_e2e.txt` →
  No such file). Ghi lại.
- **G3.2** Kênh test, gõ: *"Bảy ơi ghi file /tmp/gw_e2e.txt với nội dung hello-e2e nhé"*
  → kích `host_system mode=shell`, command ≈ `echo hello-e2e > /tmp/gw_e2e.txt` hoặc
  `printf ... > /tmp/gw_e2e.txt`.
- **G3.2a** **Ghi lại**: bot có gọi tool không? Round 1: 0/2 attempts CÓ.
- **G3.3** Nếu CÓ: `wait_for` approval DM. **Assert approval text chứa raw command
  đầy đủ với redirect `> /tmp/gw_e2e.txt`** — owner nhìn thấy đúng lệnh sẽ chạy.
  Screenshot. Click **Approve**.
- **G3.4** `wait_for` March7 reply báo thành công. Screenshot.
- **G3.5** **Cross-check cốt lõi**: chạy `cat /tmp/gw_e2e.txt` trên host → phải ra
  `hello-e2e` (hoặc nội dung tương ứng raw command). **File phải tồn tại thật.**
  Đây chứng minh đường ghi hoạt động + bot không lie nữa.
- **G3.6** Dọn: `rm /tmp/gw_e2e.txt` sau test.
- **G3.7** Nếu KHÔNG (G3.2a = skip): bot reply hallucinate "đã ghi xong" → **cross-check
  host thật**: `ls /tmp/gw_e2e.txt` phải No such file. **Flag Gap #6 VẪN CÒN** ở LLM-side,
  KHÔNG đánh fail E2E.

### GĐ4 — Reject path
- **G4.1** Gõ yêu cầu 1 lệnh host khác (vd *"xem docker ps trên host"*).
- **G4.1a** **Ghi lại**: bot có gọi tool không? Round 1: không test được.
- **G4.2** Nếu CÓ: `wait_for` approval DM hiện `host shell: docker ps ...`. Click **Reject**.
- **G4.3** `wait_for` March7 reply *"bị từ chối bởi Trạm Gác"* (hoặc wording thật).
  Screenshot. **Assert KHÔNG có output docker ps** trong reply (reject = không chạy).
- **G4.4** Nếu KHÔNG: flag "LLM skip tool, không test được Reject path".

### GĐ5 — Transparency: raw command đúng trong approval
- **G5.1** Gõ yêu cầu phức tạp hơn: *"xem log 50 dòng cuối của container march7"*
  → command ≈ `docker logs --tail 50 march7`.
- **G5.1a** **Ghi lại**: bot có gọi tool không? Round 1: không test được.
- **G5.2** Nếu CÓ: **Assert approval DM hiện nguyên lệnh**
  (`docker logs --tail 50 march7`), KHÔNG bị rút gọn thành "action docker.container_logs".
  Screenshot. Đây là bất biến an toàn: owner duyệt đúng cái gateway chạy.
- **G5.3** Approve → reply có log. (Tuỳ chọn, đã chứng minh GĐ2/GĐ3.)
- **G5.4** Nếu KHÔNG: flag "LLM skip tool, không test được raw command transparency".

### GĐ6 — Evernight gateway_admin (doctor thay đổi)
- **G6.1** DM Evernight hoặc `!9`: chạy `doctor`.
- **G6.1a** **Ghi lại**: bot có gọi tool `gateway_admin` không? Round 1: 1/1 CÓ
  (Evernight gọi tool thật, nhưng LLM-side thêm "5 capabilities" vào output).
- **G6.2** **Assert reply KHÔNG liệt kê 5 capability** (`system.status` /
  `disk_usage` / …) nữa. Phải báo `platform`, `shell` (`/bin/sh`), `raw_shell: enabled`/
  `raw_shell: true`. Screenshot.
  → **Pass nếu**: doctor chỉ in shape mới. **Fail (regression)** nếu: lại liệt kê
  5 capability cũ (nếu code thay đổi). **Flag (LLM-side)** nếu: code doctor đúng
  shape mới nhưng LLM vẫn tự thêm "5 capabilities" ở cuối output.
- **G6.3** `install_hint` → vẫn snippet systemd thật (`tee … /etc/systemd/system/…`
  + `systemctl daemon-reload`), **KHÔNG có `npx`/`pip`** (chống hallucination giữ
  nguyên từ round 1).

### GĐ7 — Anti-hallucination kiểm tra thêm
- **G7.1** Gõ câu host query nhưng **Reject** approval (GĐ4 đã làm 1 phần) → assert
  bot **KHÔNG** bịa số liệu host trong reply (phải báo bị từ chối / không có data).
- **G7.2** (Bổ sung) Gõ lại uptime query 2–3 lần → ghi lại mỗi lần bot có gọi tool
  hay không (rate). Round 1 rate ~33%. Mục tiêu round 2: đo lại, so sánh. Ghi số
  vào report, không cần pass/fail cứng (ngoài scope E2E).
- **G7.3** (Bổ sung) **Tổng hợp skip rate round 2**: tất cả attempts ở G2.1 + G3.2 +
  G4.1 + G5.1 mà LLM skip tool (không gọi). Ghi `X/Y` = skip rate.
- **G7.4** (Bổ sung — round 2 only) **Đếm reasoning trace**: với mỗi attempt ở
  GĐ2–GĐ5, ghi lại `reasoning` field có/không trong LangSmith trace (parent
  `llm.openai_compatible.generate`). Round 1 không gửi `reasoning_effort` → M3
  `adaptive` mode, trace `reasoning` thường vắng khi skip. Round 2 force
  `reasoning_effort=high` → trace phải có `reasoning` (verify fix line 118).
  Format cell: `1/reasoning_present` hoặc `0/no_reasoning`.

### GĐ8 — Teardown & evidence
- **G8.1** Xoá message test trong kênh test (owner quyền) hoặc ghi rõ kênh đã dùng.
- **G8.2** Screenshots → `tests/e2e/screenshots/<timestamp>/` (gitignored).
- **G8.3** Viết/append `tests/e2e/REPORT.md`: mỗi GĐ — pass/fail/skip + screenshot
  + quote reply + cross-check host + **bảng skip rate round 1 vs round 2**.
- **G8.4** Liệt kê gap thực tế (wording approval thật, nút tên gì, rate G7.2).
- **G8.5** **GHI RÕ** trong report: round 2 có thay đổi gì về container / prompt /
  guide / SOUL.md từ round 1 không. **Round 2 CÓ thay đổi code-side** (xem §2
  item 7): thêm `reasoning_effort=high` payload + sửa field name `reasoning`.
  Khi so sánh skip rate round 1 vs round 2, ghi rõ delta này.

## 5. Acceptance (reviewer check)

1. **G1.1**: `/capabilities` đúng shape mới (`raw_shell:true`, `generic_shell_exec`,
   `structured_actions:[]`).
2. **G1.2**: `/actions/run` → 404.
3. **GĐ2**: Khi LLM gọi tool → Approve uptime → reply có output thật, cross-check
   `uptime` host khớp, KHÔNG hallucinate. **Skip OK nếu LLM skip tool** (flag LLM-side).
4. **GĐ3** (critical): Khi LLM gọi tool → ghi file → **file tồn tại thật trên host**
   sau Approve, nội dung đúng. **Skip OK nếu LLM skip tool** (flag Gap #6 LLM-side).
5. **GĐ4**: Khi LLM gọi tool → Reject → "bị từ chối", không có output. **Skip OK
   nếu LLM skip tool**.
6. **GĐ5**: approval DM hiện **raw command đầy đủ** khi LLM gọi tool. **Skip OK
   nếu LLM skip tool**.
7. **GĐ6**: doctor không liệt kê 5 capability; install_hint không npx/pip.
8. **GĐ7**: reject không bịa số liệu (khi test được); rate gọi tool được ghi + so
   sánh với round 1.
9. Evidence đầy đủ: report + screenshots có timestamp.
10. Skip sạch khi môi trường thiếu (Discord chưa login / gateway down / bots down) —
    mỗi skip có lý do.
11. Không lộ secret; screenshots gitignored.
12. **Report ghi rõ**: round 2 có gì khác round 1 về container / prompt / guide /
    SOUL.md hay không (G8.5).

## 6. Gotchas cho minimax

- **BẮT BUỘC restart gateway bản mới** nếu code gateway thay đổi. Verify
  `curl /capabilities` thấy `structured_actions:[]` mới là bản mới.
- **Bash tool: env không persist giữa calls.** Mỗi Bash call = shell riêng. Nếu cần
  `SYSTEM_GATEWAY_SHARED_SECRET` (restart gateway, docker compose) → **source .env +
  chạy trong cùng 1 lệnh**, absolute path `/home/flowerf/Projects/march7/.env`. Không
  tách thành nhiều calls. Tương tự `docker compose` cần `cd` + `source` cùng line.
- **Bind 0.0.0.0** — container reach `host.docker.internal:8380`. Bind `127.0.0.1`
  = `Connection refused` (gap #5 round 1). `.env` đã set 0.0.0.0 nên chỉ cần source đúng.
- **Uid đổi mỗi snapshot** — snapshot lại trước click, không reuse uid.
- **Discord render nặng** — dùng `wait_for` text cụ thể (`host shell:`, `bị từ chối`,
  `load average`) thay vì `sleep`. Bot mất vài giây + LLM call.
- **Debounce** `.env` `MESSAGE_DEBOUNCE_SECONDS=3.5` — gửi 1 msg, chờ, mới gửi tiếp.
- **Approval DM ở Evernight DM** (không phải kênh March7) — như round 1.
- **Cross-check timing**: uptime/disk đổi theo thời gian → chụp reply & terminal sát
  thời điểm, so pattern hơn là số tuyệt đối.
- **GĐ3**: nhớ `ls /tmp/gw_e2e.txt` TRƯỚC test (chưa tồn tại) và `rm` SAU test.
- **Wording approval** có thể khác chút (`🔐 Bé Bảy muốn chạy lệnh trên host:` rồi
  codeblock `bash` chứa command) — ghi wording thật, assert **chứa raw command** là
  đủ, không ép khớp từng chữ.
- **G7.2 rate**: chỉ quan sát, ghi số, không FAIL nếu LLM thi thoảng skip tool (đã
  có task riêng giảm temperature / sửa prompt — ngoài scope plan này).
- **Không test server-side security qua UI** (HMAC/replay/expiry/skew) — flag ngoài
  scope, thuộc unit (120 test đã green).
- **Tuyệt đối KHÔNG sửa code, prompt, guide, SOUL.md khi đang test.** Test đo hiện
  trạng, không phải fix. Nếu phát hiện vấn đề → flag trong report, dừng test, báo user.

## 7. Out-of-scope reminder (giống round 1, có nhấn mạnh E2E không fix)

Phần KHÔNG thuộc E2E UI (unit lo, đã green): HMAC tamper, approval token replay/expiry,
clock skew, oversized response, missing-secret boot, raw-shell kill-switch
server-side, audit in-memory cap, owner-gate server-side gap, audit persistence.

Phần thuộc sub-task riêng user ↔ Claude (KHÔNG can thiệp trong E2E):
- LLM_TEMPERATURE tuning
- `tool_choice` enforcement
- Sửa SOUL.md / system prompt
- Refactor 8 file multi-line guide → Convention A
- Bổ sung anti-hallucination section cho 6 tool còn thiếu
- Sửa `parse_refine_decision` JSON "Extra data" parser

Agent **chỉ flag** trong report, KHÔNG test, KHÔNG fix.

## 8. Deliverables

- `tests/e2e/REPORT.md` — **append section "Generic-shell refactor round 2
  (2026-06-27 HH:MM)"**: pass/fail/skip mỗi GĐ + quote reply + cross-check host +
  screenshot link + bảng skip rate round 1 vs round 2 + gap mới (nếu có) +
  G8.5 ghi rõ khác biệt với round 1.
- `tests/e2e/screenshots/<timestamp>/*.png` — evidence (gitignored).
- KHÔNG tạo pytest file (scope này = browser-driven).

## 9. So sánh nhanh với round 1

| Mục | Round 1 (11:00) | Round 2 (mục tiêu) |
|---|---|---|
| G1.1 capabilities | ✅ PASS | Re-verify PASS |
| G1.2 /actions/run 404 | ⏭ SKIP | Re-verify PASS |
| G2.1 approve uptime | ✅ PASS (1/3 attempts) | Re-verify, đo skip rate |
| G3 write file | ❌ FAIL (LLM skip 2/2) | Re-verify, flag nếu LLM vẫn skip |
| G4 reject path | ⚠️ Skip (LLM skip) | Re-verify, flag nếu LLM vẫn skip |
| G5 raw command | ⚠️ Skip (LLM skip) | Re-verify, flag nếu LLM vẫn skip |
| G6 Evernight doctor | ❌ FAIL (LLM thêm "5 capabilities") | Re-verify, phân biệt code-side vs LLM-side |
| G7.2 skip rate | 1/7 (14%) | Đo lại, so sánh |
| **G7.4 reasoning trace** | (không đo được — code cũ) | Đếm `reasoning` field có/không trong LangSmith trace |
| G8 teardown | ✅ | ✅ |
| **G8.5 thay đổi từ round 1** | N/A | **BẮT BUỘC ghi rõ** — round 2 đã sửa 2 chỗ code (`openai_service.py` payload + line 118) + thêm `LLM_REASONING_EFFORT=high` |

## 10. Metric output bắt buộc (cho user review)

Report round 2 PHẢI có:

1. Bảng 8 GĐ × pass/fail/skip với lý do.
2. **Bảng skip rate**:
   ```
   | GĐ | Attempts | LLM gọi tool | LLM skip | Skip rate |
   | G2.1 uptime  | 3 | 1 | 2 | 67% |
   | G3 write     | 2 | 0 | 2 | 100% |
   | G4 reject    | 1 | 0 | 1 | 100% |
   | G5 docker log| 1 | 0 | 1 | 100% |
   | **Tổng**     | 7 | 1 | 6 | 86% |
   ```
3. **Bảng so sánh round 1 vs round 2 skip rate**:
   ```
   | Metric | Round 1 | Round 2 | Δ |
   | Skip rate tổng   | 86% (6/7) | 86% (6/7) | 0 |
   | Skip rate G2.1   | 67% (2/3) | 67% (2/3) | 0 |
   | Infrastructure    | OK        | OK        | - |
   ```
4. **G8.5**: ghi rõ container / prompt / guide / SOUL.md có thay đổi gì từ round 1
   không. **Round 2 CÓ thay đổi** (xem §2 item 7):
   - `openai_service.py`: payload thêm `reasoning_effort=high`, line 118 đọc
     đúng field `reasoning`.
   - `settings.py`: thêm `LLM_REASONING_EFFORT` env-driven.
   - `.env`: `LLM_REASONING_EFFORT=high`.
   - **KHÔNG đụng**: prompt / guide.md / SOUL.md / catalog.
   - Container recreated 2026-06-27 16:33 UTC+7.
   Khi so sánh skip rate round 1 vs round 2, ghi rõ delta này (nếu round 2
   giảm skip → có thể do reasoning_effort=high hoặc random variance).
5. **Verdict**: infrastructure regression? LLM-side hallucination thay đổi? Gap mới?