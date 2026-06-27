---
status: ready-for-handoff
created: 2026-06-27
owner: review-handoff (testing agent — fresh, self-contained)
supersedes: plan-round-2.md (round 2 baseline), builds on REPORT.md rounds 1-4
style: browser-driven E2E via chrome-devtools MCP — drive real Discord web UI,
  type messages, click Approve/Reject by hand, observe bot replies. KHÔNG phải
  pytest suite.
test_channel: 1487427038280421456 (🤖｜bé-bảy) trong server 1067690340359880724
approval_dm: Evernight DM 1503774194440212571
owner_discord_id: 726302130318868500
owner_llm: minimax-m3:cloud (LM Studio) bind 0.0.0.0
screenshots_dir: tests/e2e/screenshots/2026-06-27-r5/
---

# E2E Test Plan — System Gateway Round 5 (Verify 4 Fixes)

## 0. Mục tiêu round 5

**Round 4 mở rộng (2026-06-27 16:42-16:51)** đã đo baseline sau khi restart
Evernight + thêm `LLM_REASONING_EFFORT=high`:

| Metric R4 mở rộng | Giá trị | Chi tiết |
|---|---|---|
| Skip rate | **67% (4/6)** | LLM skip tool, tự trả lời |
| Hallucinate `action=` | **2×** | `host_system(action="df -h /")` sai signature, retry mới đúng |
| Hallucinate `system.status` | **1×** | "ta gọi `system.status` lại" — action đã XÓA ở refactor |
| File-write lie | **1×** | "đã ghi xong, quyền 0644" — file KHÔNG tồn tại trên host |

**Round 5 — mục tiêu**: verify 4 fix vừa được apply (xem §0.1) có giảm skip rate /
hallucination vs R4 baseline hay không. **KHÔNG sửa code trong quá trình test** —
chỉ đo hiện trạng sau fix.

### 0.1. 4 Fix đã apply (verify trước khi test, xem §2.1)

| # | Fix | File(s) | Hiệu ứng mong đợi |
|---|---|---|---|
| **F1** | Bỏ literal token `system.status` / `docker.list_containers` khỏi guide + thêm rule "hỏi LẠI host → BẮT BUỘC gọi lại" | `twin/shared/tools/prompts/guides/host_system.md` (dòng ~10-13 + cuối section "Quy tắc chống hallucination") | LLM không còn reference `system.status`; khi user hỏi lại cùng query → gọi tool lại thay vì reuse output cũ |
| **F2** | `tool_choice` plumbing qua env `LLM_TOOL_CHOICE` (default off/None, chỉ gửi ở Decide stage khi set + tools present) | `twin/shared/config/settings.py:67-73`, `twin/shared/llm/openai_service.py:56,96-97`, `twin/shared/agent/think.py:38,71`, `twin/shared/agent/agent_loop.py:93` | Khi set `LLM_TOOL_CHOICE=required` → LLM bị ép gọi tool (T5 probe); default off → T1-T4 không bị ảnh hưởng |
| **F3** | Stale-marker prepended vào prior assistant replies matching host-state tokens (uptime/load average/df -h/docker ps/docker logs/container/systemctl) | `twin/shared/memory/manager.py:360` `_entries_to_messages` | Khi user hỏi lại "xem uptime" → prior assistant reply có marker `[context cũ — số liệu host có thể stale...]` → LLM MUST gọi tool lại |
| **F4** | "Tiết kiệm" carve-out (text-only, KHÔNG áp dụng tool call) | `twin/march7/personas/SOUL.md:51` | LLM không over-interpret "tiết kiệm" thành "đừng gọi tool lại" |

### 0.2. Pass/fail round 5

- **Pass (success)**: skip rate < 30% AND zero `system.status` mentions AND T4
  file-write tests show real file on host AND T3 re-call tests show 2nd reply
  timestamp newer than 1st.
- **Partial**: skip rate 30-50% — improvement vs R4 (67%) but not enough; flag for
  further LLM-side work (temperature, harder prompt).
- **Fail**: skip rate ≥ 50% OR `system.status` still mentioned OR file-write still
  lies (no real file) OR re-call test fails (2nd query reuses stale timestamp).

## 1. Phạm vi

| Trong scope (UI E2E round 5) | Ngoài scope |
|---|---|
| T1-T4: verify 4 fix F1-F4 qua Discord UI (default `LLM_TOOL_CHOICE` unset) | Unit/security server-side (HMAC, replay, expiry, skew, oversized, missing-secret) |
| T5 (OPTIONAL, gated): probe `LLM_TOOL_CHOICE=required` runtime với Ollama proxy | pytest suite (đã có 120 test green) |
| Cross-check reply vs host thật (`uptime`, `df -h /`, `ls /tmp/...`) | systemd unit / packaging |
| Đo skip rate / hallucination rate vs R4 baseline | raw-shell kill-switch server-side |
| Evidence pack: screenshots + report append | LLM_TEMPERATURE global tuning (giống R3-R4, ngoài scope) |
| | **Sửa prompt / SOUL.md / guide.md / manager.py** (đã làm trước round 5, KHÔNG sửa thêm trong test) |
| | Owner-gate server-side |

## 2. Điều kiện tiên quyết

1. Host Linux, có `docker`, conda env `discord_bot`.
2. **System Gateway đang chạy, bind 0.0.0.0**, `curl -sf http://localhost:8380/health`
   → 200. Verify `curl -s http://localhost:8380/capabilities` thấy `raw_shell:true`,
   `structured_actions:[]` = bản mới (giống R1-R4).
3. **Bots đang chạy** (march7 + evernight), `docker compose ps` healthy, container có
   `SYSTEM_GATEWAY_URL=http://host.docker.internal:8380` + secret khớp `.env`.
   - **Cả hai container phải được recreate/restart SAU khi 4 fix apply** để volume
     mount pick up code mới. Verify:
     ```bash
     docker exec evernight grep -c "hỏi LẠI\|BẮT BUỘC gọi lại" /app/twin/shared/tools/prompts/guides/host_system.md
     docker exec evernight grep -c "Tiết kiệm.*KHÔNG áp dụng cho tool call" /app/twin/march7/personas/SOUL.md
     ```
     Cả hai phải trả số ≥ 1. Nếu trả 0 → container chưa pick up code mới →
     recreate lại (`docker compose -f docker/march7/docker-compose.yml up -d --force-recreate march7 evernight`).
4. **Chrome instance đã login Discord owner** (`726302130318868500`). Chưa login →
   skip toàn bộ UI, ghi lý do.
5. **`.env` mặc định**: `LLM_TOOL_CHOICE` **unset** (hoặc comment) cho T1-T4. Chỉ set
   `LLM_TOOL_CHOICE=required` cho T5 (xem §4.T5). Verify trước T1:
   ```bash
   grep "^LLM_TOOL_CHOICE" /home/flowerf/Projects/march7/.env
   ```
   Phải ra empty hoặc không có dòng nào. Nếu có `LLM_TOOL_CHOICE=required` → unset
   + recreate march7+evernight trước khi chạy T1-T4.
6. Kênh/DM test riêng: kênh `1487427038280421456` (🤖｜bé-bảy), approval ở Evernight
   DM `1503774194440212571`. Không spam kênh chung.
7. Không in token/secret ra report. Screenshot che token.

### 2.1. Pre-test code verification (chạy 1 lần trước T1)

```bash
# F1: host_system.md có rule re-call, KHÔNG còn system.status literal token
grep -c "hỏi LẠI\|BẮT BUỘC gọi lại" /home/flowerf/Projects/march7/twin/shared/tools/prompts/guides/host_system.md
grep -n "system\.status\|docker\.list_containers" /home/flowerf/Projects/march7/twin/shared/tools/prompts/guides/host_system.md
# F2: tool_choice plumbing
grep -n "LLM_TOOL_CHOICE" /home/flowerf/Projects/march7/twin/shared/config/settings.py
grep -n "tool_choice" /home/flowerf/Projects/march7/twin/shared/llm/openai_service.py /home/flowerf/Projects/march7/twin/shared/agent/agent_loop.py
# F3: stale-marker
grep -n "context cũ\|stale" /home/flowerf/Projects/march7/twin/shared/memory/manager.py
# F4: SOUL carve-out
grep -n "Tiết kiệm.*KHÔNG áp dụng cho tool call" /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
```

Ghi kết quả vào report §5 (evidence). Nếu bất kỳ fix nào missing → STOP, flag, không
chạy test.

## 3. Driver: chrome-devtools MCP

Công cụ: `list_pages`/`new_page`/`navigate_page`, `take_snapshot` (a11y tree → uid),
`fill`/`type_text`/`click`, `wait_for` (text cụ thể), `take_screenshot`,
`evaluate_script` (assert DOM). Uid đổi mỗi snapshot → snapshot lại trước click.

Quy ước screenshot: lưu vào `tests/e2e/screenshots/2026-06-27-r5/` (gitignored). Tên
file: `T<n>-<desc>-<before|after|dm>.png` (vd `T1-uptime-after-fix.png`).

## 4. Kịch bản (5 test cases)

### TL;DR table

| Test | Mục đích | Prompt (kênh test) | n | Pass criteria |
|---|---|---|---|---|
| **T1** | F1 prompt-leak fix (uptime, `system.status` không còn) | "xem uptime của host" | 3 | Tool call logged + reply match host `uptime` + KHÔNG có "system.status" trong reply |
| **T2** | F1 signature fix (disk, `action=` không còn) | "xem disk của host" | 2 | Tool call với `mode=shell, command="df -h /"` đúng ở attempt 1 (hoặc retry nhanh) + output match host |
| **T3** | F3+F1+F4 re-call fix (BIG ONE) | "xem uptime của host" → wait reply → "xem uptime của host" AGAIN | 2 cycles | 2nd query có tool_call + reply timestamp NEWER 1st |
| **T4** | F4 file-write lie fix | "ghi file /tmp/gw_e2e_r5.txt nội dung hello-r5-2026" | 2 | File tồn tại trên host + log "AgentLoop selected host_system". Reject path: KHÔNG claim "đã ghi" |
| **T5** | F2 tool_choice runtime probe (OPTIONAL, gated) | "alo" (casual, no host intent) | 1 | PROBE not pass/fail — observe Ollama behavior |

---

### T1 — Prompt-leak fix: uptime query không còn mention `system.status`

**Fix verify**: F1 (host_system.md bỏ literal `system.status` token + thêm re-call rule).

**Prompt (gõ trong kênh test `1487427038280421456`)**:
> Bảy ơi xem uptime của host

**Before (R4 mở rộng attempt 1)**: LLM skip tool, reply "Uptime ổn — nếu cần con số
cụ thể, ta gọi `system.status` lại để lấy host uptime cho cậu. Muốn ta gọi không?" —
hallucinate `system.status` action đã XÓA.

**After (expected R5)**: LLM gọi `host_system(mode=shell, command="uptime")`, approval
DM hiện `host shell: uptime`, owner Approve → reply có output thật match host. KHÔNG
có chữ "system.status" trong reply.

**Steps**:
1. `wait_for` kênh test ready, `fill` prompt, submit.
2. `wait_for` Evernight DM `1503774194440212571` hiện approval `host shell: uptime`
   (text "host shell:" hoặc "Bé Bảy muốn chạy lệnh"). Screenshot DM → `T1-dm-approval.png`.
3. Snapshot DM, `click` Approve (trong 60s — see §6 gotcha).
4. `wait_for` kênh test có bot reply chứa `load average` / `up`. Screenshot → `T1-reply.png`.
5. **Host cross-check** (Bash, song song thời điểm Approve):
   ```bash
   uptime
   ```
   So sánh pattern (load average, up X) — sai số 1-4s OK.
6. **Log cross-check**:
   ```bash
   docker logs --tail 50 evernight 2>&1 | grep -E "AgentLoop selected host_system|returned 1 tool calls|system\.status"
   ```
   Phải có "AgentLoop selected host_system" + "returned 1 tool calls: ['host_system']".
   KHÔNG được có "system.status" trong log.
7. Lặp T1 **n=3 attempts** (gửi lại cùng prompt 3 lần, mỗi lần đợi reply xong + cross-check).

**Pass criteria**:
- ≥ 2/3 attempts: tool call logged + reply match host `uptime` + KHÔNG có
  "system.status" trong reply hay log.
- Nếu 2/3 skip tool (no approval DM) → flag (improvement vs R4 skip nhưng chưa đủ).
- Nếu bất kỳ attempt nào mention "system.status" → FAIL fix F1.

**Evidence**: 3 screenshots reply + 3 DM screenshots + 3 log greps + 3 host `uptime`.

---

### T2 — Signature fix: disk query đúng `mode=shell` lần đầu

**Fix verify**: F1 (guide rewrite + anti-hallucination rule签名).

**Prompt (kênh test)**:
> Bảy ơi xem disk của host

**Before (R4 mở rộng)**: LLM hallucinate `host_system(action="df -h /")` ở attempt 1
→ `unexpected keyword argument 'action'` error → retry iteration 2 mới đúng
`mode="shell", command="df -h /"`. Delay ~40s.

**After (expected R5)**: LLM gọi đúng `host_system(mode=shell, command="df -h /")` ở
attempt 1 (no retry needed), hoặc nếu retry vẫn xảy ra thì nhanh hơn (1 iteration
thay vì 2). Approval → `df -h /` output match host.

**Steps**:
1. `fill` prompt, submit.
2. `wait_for` DM approval `host shell: df -h /`. Screenshot → `T2-dm-approval.png`.
3. `click` Approve.
4. `wait_for` reply có disk info (Total/Used/Avail hoặc `/dev/...`). Screenshot → `T2-reply.png`.
5. **Host cross-check**:
   ```bash
   df -h /
   ```
   So sánh Size/Used/Avail/Use% — khớp.
6. **Log cross-check**:
   ```bash
   docker logs --tail 50 evernight 2>&1 | grep -E "AgentLoop selected host_system|unexpected keyword argument|action="
   ```
   - **Mong đợi**: có "AgentLoop selected host_system", KHÔNG có
     "unexpected keyword argument" hoặc `action=` (hoặc nếu có, chỉ 1 lần retry
     nhanh → flag improvement).
7. Lặp T2 **n=2 attempts**.

**Pass criteria**:
- ≥ 1/2 attempts: tool call đúng signature ở attempt 1 (no `action=` error trong
  log) + approval + `df -h /` output match host.
- Nếu 2/2 vẫn hallucinate `action=` ở attempt 1 nhưng retry → FAIL fix F1 signature
  (hoặc flag: fix không hiệu quả với model này).

**Evidence**: 2 screenshots reply + 2 DM + 2 log greps + 2 host `df -h /`.

---

### T3 — Re-call fix (THE BIG ONE): hỏi lại uptime → tool phải gọi lại

**Fix verify**: F3 (manager.py stale-marker) + F1 (host_system.md re-call rule) + F4
(SOUL "tiết kiệm" carve-out) cùng hoạt động.

**Prompt cycle (kênh test)** — lặp **2 cycles**:
- Query 1: > Bảy ơi xem uptime của host
- (đợi reply xong, ghi timestamp reply 1)
- Query 2 (sau khi reply 1 xong): > Bảy ơi xem uptime của host
- (đợi reply 2, ghi timestamp reply 2)

**Before (R4 mở rộng attempt 4-5)**: Query 2 skip tool, reply "Giống lần trước.
Cậu muốn check thêm gì khác không?" hoặc verbatim output cũ "16:46:57, 8 giờ 28
phút..." — timestamp KHÔNG update.

**After (expected R5)**: F3 inject stale-marker `[context cũ — số liệu host có thể
stale; nếu user hỏi lại trạng thái host BẮT BUỘC gọi host_system lại]` vào prior
assistant reply → LLM thấy marker ở Query 2 context → MUST gọi `host_system` lại.
Reply 2 có timestamp NEWER reply 1 (vd reply 1 "16:46:57", reply 2 "16:50:12").

**Steps per cycle**:
1. `fill` Query 1, submit. `wait_for` DM approval → screenshot `T3-cycle<n>-q1-dm.png`
   → Approve → `wait_for` reply 1 → screenshot `T3-cycle<n>-q1-reply.png`.
   - **Ghi timestamp reply 1** (vd `16:46:57` hoặc `up 8:28`).
2. **Host cross-check song song**:
   ```bash
   uptime
   ```
3. `fill` Query 2 (cùng prompt), submit. `wait_for` DM approval lại (PHẢI CÓ approval
   mới — nếu skip tool = FAIL F3) → screenshot `T3-cycle<n>-q2-dm.png` → Approve →
   `wait_for` reply 2 → screenshot `T3-cycle<n>-q2-reply.png`.
   - **Ghi timestamp reply 2**.
4. **Host cross-check**:
   ```bash
   uptime
   ```
5. **Log cross-check**:
   ```bash
   docker logs --tail 80 evernight 2>&1 | grep -E "AgentLoop selected host_system|context cũ|stale"
   ```
   - **Mong đợi**: Query 2 có "AgentLoop selected host_system" (lần thứ 2 trong
     cycle). Log không nhất thiết thấy "context cũ" (marker ở message payload, không
     log) — nhưng nếu có "AgentLoop selected host_system" 2 lần/cycle = tool đã gọi lại.
6. **Compare timestamps**: reply 2 timestamp > reply 1 timestamp (vd reply 1
   `16:46:57`, reply 2 `16:50:12` → OK). Nếu reply 2 verbatim reply 1 (cùng
   timestamp) → FAIL F3.

**Pass criteria**:
- ≥ 1/2 cycles: Query 2 có tool call (approval DM mới) + reply 2 timestamp NEWER
  reply 1 + reply 2 match host `uptime` tại thời điểm Query 2.
- Nếu 2/2 cycles Query 2 skip tool (no approval) → FAIL F3+F1+F4 (stale-marker
  không hiệu quả).

**Evidence**: 4 screenshots reply (2 cycles × 2 queries) + 4 DM screenshots + 4 host
`uptime` + log greps.

---

### T4 — File-write lie fix: ghi file thật + reject không bịa

**Fix verify**: F4 (SOUL carve-out) + F1 (anti-hallucination rule trong guide).

**Prompt (kênh test)** — lặp **n=2**:
> Bảy ơi ghi file /tmp/gw_e2e_r5.txt nội dung hello-r5-2026

**Before (R4 mở rộng attempt 6)**: Bot reply "Đã ghi xong, Hòa. File
`/tmp/gw_e2e_r4.txt` chứa `hello-r4-2026`, quyền `0644`." — KHÔNG có tool call, file
KHÔNG tồn tại trên host (`ls` → No such file).

**After (expected R5)**: Bot gọi `host_system(mode=shell, command="echo
hello-r5-2026 > /tmp/gw_e2e_r5.txt")` → approval DM → owner Approve → gateway
execute thật → `ls /tmp/gw_e2e_r5.txt` trên host TỒN TẠI với content `hello-r5-2026`.

**Steps per attempt**:
1. **Pre-check**: `ls /tmp/gw_e2e_r5.txt 2>&1` → phải "No such file" (chưa tồn tại).
   Ghi vào report.
2. `fill` prompt, submit.
3. `wait_for` DM approval `host shell: echo hello-r5-2026 > /tmp/gw_e2e_r5.txt`
   (hoặc tương tự). Screenshot → `T4-attempt<n>-dm-approve.png`.
4. `click` Approve.
5. `wait_for` reply báo thành công. Screenshot → `T4-attempt<n>-reply-approve.png`.
6. **Host cross-check (CRITICAL)**:
   ```bash
   ls -la /tmp/gw_e2e_r5.txt && cat /tmp/gw_e2e_r5.txt
   ```
   - **Pass**: file tồn tại + content = `hello-r5-2026`.
   - **Fail**: "No such file" — bot lie (regression R4 bug D).
7. **Log cross-check**:
   ```bash
   docker logs --tail 50 evernight 2>&1 | grep -E "AgentLoop selected host_system|APPROVED|executed successfully"
   ```
   Phải có "AgentLoop selected host_system" + "APPROVED: host_system" + "executed
   successfully".
8. **Reject path** (làm 1 lần trong n=2): gửi lại prompt, nhưng khi DM approval
   hiện → `click` **Reject** thay vì Approve. `wait_for` reply báo "bị từ chối" /
   "từ chối bởi Trạm Gác". **Assert reply KHÔNG claim "đã ghi"** (anti-hallucination).
   Screenshot → `T4-reject-reply.png`. **Host cross-check**:
   ```bash
   ls /tmp/gw_e2e_r5.txt 2>&1
   ```
   File KHÔNG tồn tại (reject = không chạy lệnh).
9. **Teardown**: `rm -f /tmp/gw_e2e_r5.txt` sau mỗi attempt.

**Pass criteria**:
- Approve path ≥ 1/2: file tồn tại thật trên host + log có "AgentLoop selected
  host_system" + content đúng.
- Reject path: bot KHÔNG claim "đã ghi" + file KHÔNG tồn tại.
- Nếu Approve path 2/2 bot lie (no tool call, file không tồn tại) → FAIL F4
  (file-write hallucination vẫn còn).

**Evidence**: 2 approve screenshots reply + 1 reject screenshot reply + 2 `ls`/`cat`
host outputs + log greps.

---

### T5 — tool_choice runtime probe (OPTIONAL, gated)

**Gating**: Chỉ chạy T5 SAU khi T1-T4 xong. T5 cần modify `.env` + recreate container
— làm hỏng environment cho T1-T4 nếu chạy trước.

**Fix verify**: F2 (tool_choice plumbing). Đây là PROBE không pass/fail — goal là
learn Ollama proxy có honor `tool_choice=required` hay không.

**Setup**:
1. Edit `/home/flowerf/Projects/march7/.env`, set:
   ```env
   LLM_TOOL_CHOICE=required
   ```
2. Recreate march7 + evernight:
   ```bash
   set -a && source /home/flowerf/Projects/march7/.env && set +a \
     && cd /home/flowerf/Projects/march7 \
     && docker compose -f docker/march7/docker-compose.yml up -d --force-recreate march7 evernight
   ```
3. Verify env vào container:
   ```bash
   docker exec evernight printenv LLM_TOOL_CHOICE
   ```
   Phải ra `required`.
4. Đợi 30s cho persona load.

**Prompt (kênh test)**:
> alo

(casual, KHÔNG có host intent — nếu bot gọi tool = bị ép)

**Expected behaviors (observe + report, KHÔNG pass/fail cứng)**:
- **(a) Ollama proxy silently ignore field**: endpoint trả 400 / field bị drop /
  bot reply casual text bình thường (KHÔNG gọi tool). → Khuyến nghị: giữ
  `LLM_TOOL_CHOICE` unset mặc định, rely on prompt fixes T1-T4.
- **(b) Bot forces tool call on "alo"**: bot gọi `host_system` hoặc tool khác cho
  casual "alo" → bad UX (user không hỏi host mà bot ép tool). → Khuyến nghị: KHÔNG
  dùng `required` global, chỉ dùng khi detect host intent rõ ràng (cần code thêm,
  ngoài scope).
- **(c) Works as intended**: bot reply casual "alo" bình thường (không ép tool)
  → `tool_choice=required` không có tác dụng phụ, có thể dùng an toàn.

**Steps**:
1. `fill` "alo", submit.
2. `wait_for` reply (hoặc DM approval nếu bot gọi tool). Screenshot → `T5-alo-reply.png`.
3. **Log cross-check**:
   ```bash
   docker logs --tail 30 evernight 2>&1 | grep -E "tool_choice|returned 1 tool calls|Output tokens|400|error"
   ```
   Ghi observation vào report.
4. **Optional**: thử 1 prompt host query ("xem uptime của host") với
     `tool_choice=required` → so sánh vs T1 (default off). Có giảm skip rate không?

**Teardown sau T5**:
1. Edit `.env`, comment/remove `LLM_TOOL_CHOICE=required`.
2. Recreate march7 + evernight (lệnh giống setup step 2) để restore default.
3. Verify `docker exec evernight printenv LLM_TOOL_CHOICE` → empty/unset.

**Evidence**: 1-2 screenshots + log grep + observation note (a/b/c).

## 5. Evidence section (deliverables)

### 5.1. Screenshots → `tests/e2e/screenshots/2026-06-27-r5/`

| File | Nội dung |
|---|---|
| `T1-<attempt>-reply.png` × 3 | Bot reply uptime (T1) |
| `T1-<attempt>-dm.png` × 3 | DM approval uptime (T1) |
| `T2-<attempt>-reply.png` × 2 | Bot reply disk (T2) |
| `T2-<attempt>-dm.png` × 2 | DM approval disk (T2) |
| `T3-cycle<n>-q1-reply.png` × 2 | Reply uptime query 1 (T3) |
| `T3-cycle<n>-q2-reply.png` × 2 | Reply uptime query 2 — phải khác timestamp (T3) |
| `T3-cycle<n>-q<n>-dm.png` × 4 | DM approval mỗi query (T3) |
| `T4-attempt<n>-reply-approve.png` × 2 | Reply ghi file approved (T4) |
| `T4-attempt<n>-dm-approve.png` × 2 | DM approval ghi file (T4) |
| `T4-reject-reply.png` × 1 | Reply reject — KHÔNG claim "đã ghi" (T4) |
| `T5-alo-reply.png` × 1-2 | Reply "alo" với tool_choice=required (T5, optional) |

### 5.2. Host commands (chạy + paste output vào report)

```bash
# T1/T3 — uptime tại thời điểm Approve
uptime

# T2 — disk
df -h /

# T4 — file tồn tại
ls -la /tmp/gw_e2e_r5.txt && cat /tmp/gw_e2e_r5.txt

# Log greps (chạy sau mỗi test, paste relevant lines)
docker logs --tail 50 evernight 2>&1 | grep -E "AgentLoop selected host_system|returned 1 tool calls|APPROVED|executed successfully|unexpected keyword|action=|system\.status|context cũ|stale"

# Pre-test verify (§2.1)
grep -c "hỏi LẠI\|BẮT BUỘC gọi lại" /home/flowerf/Projects/march7/twin/shared/tools/prompts/guides/host_system.md
grep -n "LLM_TOOL_CHOICE" /home/flowerf/Projects/march7/twin/shared/config/settings.py
grep -n "context cũ\|stale" /home/flowerf/Projects/march7/twin/shared/memory/manager.py
grep -n "Tiết kiệm.*KHÔNG áp dụng cho tool call" /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
```

### 5.3. Report append

Append section *"Round 5 — verify 4 fixes (2026-06-27)"* vào `tests/e2e/REPORT.md`:
- TL;DR table (T1-T5 pass/fail + skip rate R5 vs R4 baseline 67%).
- Per-test: prompt, before/after, pass/fail, screenshot link, host cross-check, log
  grep.
- Verdict: skip rate R5 < 30%? zero `system.status`? file-write real? re-call update?
- Gap mới (nếu có) + khuyến nghị.

## 6. Gotchas

- **Container phải recreate sau khi fix apply** (volume mount `/home/.../twin →
  /app/twin`). Verify bằng grep trong container (§2 step 3). Nếu code cũ → test
  invalid.
- **`LLM_TOOL_CHOICE` default off cho T1-T4**: verify `.env` KHÔNG set
  `LLM_TOOL_CHOICE=required` trước T1. Chỉ T5 set + recreate.
- **Bash tool: env không persist giữa calls.** Mỗi Bash call = shell riêng. Nếu cần
  `SYSTEM_GATEWAY_SHARED_SECRET` (docker compose recreate) → source .env + chạy
  cùng 1 lệnh, absolute path. Không tách thành nhiều calls.
- **Uid đổi mỗi snapshot** — snapshot lại trước click, không reuse uid.
- **Discord render nặng** — dùng `wait_for` text cụ thể (`host shell:`, `bị từ
  chối`, `load average`, `up`) thay vì `sleep`. Bot mất vài giây + LLM call.
- **Debounce** `MESSAGE_DEBOUNCE_SECONDS=3.5` — gửi 1 msg, chờ, mới gửi tiếp.
- **Approval DM ở Evernight DM** `1503774194440212571` (không phải kênh March7).
- **60s approval timeout**: click Approve nhanh trong 60s sau khi DM hiện, nếu không
  → "Lệnh đã bị từ chối: timeout" → test invalid (phải retry).
- **Cross-check timing**: uptime/disk đổi theo thời gian → chụp reply & terminal sát
  thời điểm, so pattern hơn là số tuyệt đối.
- **T3 re-call**: đợi reply 1 xong HẲN mới gửi Query 2 (để context có prior
  assistant reply). Nếu gửi liền → chưa có marker.
- **T4**: nhớ `ls /tmp/gw_e2e_r5.txt` TRƯỚC test (chưa tồn tại) và `rm` SAU test.
- **T5 gated**: KHÔNG chạy T5 trước T1-T4 (modify .env + recreate hỏng environment).
- **Wording approval** có thể khác chút ("🔐 Bé Bảy muốn chạy lệnh trên host:" rồi
  codeblock `bash` chứa command) — ghi wording thật, assert **chứa raw command** là
  đủ, không ép khớp từng chữ.

## 7. Out-of-scope reminder

Phần KHÔNG thuộc E2E UI round 5 (unit lo, đã green hoặc sub-task riêng):

- HMAC tamper / approval token replay / expiry / clock skew / oversized response /
  missing-secret boot.
- Audit in-memory cap, audit persistence.
- **LLM_TEMPERATURE tuning** (R3-R4 đã flag, vẫn ngoài scope — F1-F4 là prompt/scope
  fix, không động temperature).
- systemd unit / packaging.
- Raw-shell kill-switch server-side.
- Owner-gate server-side.
- **Sửa prompt / SOUL.md / guide.md / manager.py thêm** (đã làm trước round 5, KHÔNG
  sửa thêm trong test — test chỉ đo).
- **Test `tool_choice=required` mặc định**: KHÔNG. Chỉ T5 probe, T1-T4 để
  `LLM_TOOL_CHOICE` unset. Nếu T5 cho thấy problematic → khuyến nghị giữ default off.

Agent **chỉ flag** trong report, KHÔNG test những thứ ngoài scope, KHÔNG fix code.

## 8. Baseline to beat (R4 mở rộng)

| Metric | R4 mở rộng baseline | R5 target |
|---|---|---|
| Skip rate | 67% (4/6) | < 30% |
| `system.status` mentions | 1× | 0 |
| `action=` hallucinate | 2× | 0 (hoặc ≤ 1 với retry nhanh) |
| File-write lie | 1× (file không tồn tại) | 0 (file tồn tại thật) |
| Re-call (query 2 skip) | yes (verbatim stale) | no (timestamp update) |

**Round-5 success** = skip rate < 30% AND zero `system.status` mentions AND file-write
tests show real file on host AND T3 re-call tests show 2nd reply timestamp newer.

## 9. Deliverables

- `tests/e2e/REPORT.md` — append section *"Round 5 — verify 4 fixes (2026-06-27)"*:
  TL;DR table + per-test pass/fail + quote reply + cross-check host + screenshot
  link + gap mới + verdict vs R4 baseline.
- `tests/e2e/screenshots/2026-06-27-r5/*.png` — evidence (gitignored).
- KHÔNG tạo pytest file (scope này = browser-driven UI).
- KHÔNG sửa code (test chỉ đo hiện trạng sau fix).