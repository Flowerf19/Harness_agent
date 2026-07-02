---
status: ready-for-handoff
created: 2026-07-02
owner: review-handoff (testing agent — fresh, self-contained)
style: browser-driven E2E via chrome-devtools MCP — drive real Discord web UI,
  type messages, observe bot replies + verify persona files on host. KHÔNG phải
  pytest suite.
commit_under_test: ed36f3b "Refactor personality update tool and enhance shared rules"
test_channel: 1487427038280421456 (🤖｜bé-bảy) trong server 1067690340359880724
evernight_dm: 1503774194440212571 (DM Evernight ↔ owner — dùng để chat + test Evernight voice)
owner_discord_id: 726302130318868500
owner_llm: minimax-m3:cloud (LM Studio) bind 0.0.0.0
screenshots_dir: tests/e2e/screenshots/2026-07-02-personality/
---

# E2E Test Plan — Personality Refactor + Shared RULES.md (commit ed36f3b)

## 0. Mục tiêu

Verify commit `ed36f3b` qua Discord web UI thật. Commit thay đổi 3 thứ:

| # | Thay đổi (ed36f3b) | File | Hiệu ứng cần verify |
|---|---|---|---|
| **C1** | `UpdatePersonalityTool` refactor: nhận `target_file`, ghi `IDENTITY.md`/`SOUL.md`/`RULES.md` (overwrite toàn file), validate tên file (chỉ tên, không path), reload persona cache sau ghi | `twin/shared/tools/modules/profile/update_personality_tool.py` | Bot gọi tool → file trên host thật đổi → reply kế tiếp phản ánh style mới |
| **C2** | Shared `RULES.md` chung cho cả 2 bot, nạp vào system prompt | `twin/shared/personas/RULES.md`, `twin/shared/llm/base_llm_service.py` | Reply KHÔNG markdown, KHÔNG emoji đồ họa, `[skip]` trong kênh chung khi không được nhắc |
| **C3** | `IDENTITY.md`/`SOUL.md` slim down (Bé Bảy = "tui" + icon gõ tay; Evernight = "ta" + ._. / -_-) | `twin/{march7,evernight}/personas/{IDENTITY,SOUL}.md` | Voice 2 bot phân biệt đúng sau refactor |

**KHÔNG sửa code trong quá trình test** — chỉ đo hiện trạng sau commit. **Restore persona files ở teardown** (test có thể overwrite persona thật).

### 0.1. Điểm khác biệt quan trọng vs các round system-gateway trước

- **`update_personality` KHÔNG qua approval DM.** Tool là local, auto-execute: bot gọi → ghi file ngay → `reload_persona_prompts()`. KHÔNG có DM approval, KHÔNG click Approve/Reject, KHÔNG 60s timeout. Verification = file trên host đổi + reply kế tiếp đổi.
- **Tool overwrite toàn bộ file.** Bot phải tự merge nội dung cũ. Nếu bot chỉ trả về nội dung partial → persona file bị truncate/hỏng. → **BẮT BUỘC snapshot + restore persona files ở teardown** (§6).
- **Volume mount `twin → /app/twin`** (cả march7 + evernight): host file = container file. Đọc/ghi `twin/march7/personas/SOUL.md` trên host = đọc/ghi trong container. Không cần `docker exec` để verify.
- **`RULES.md` sống ở `twin/shared/personas/RULES.md`** (không phải persona dir của bot). Sửa file này = ảnh hưởng cả 2 bot sau reload/restart.

### 0.2. Tester model constraint — glm5.2 KHÔNG hiểu ảnh (BẮT BUỘC)

Tester agent chạy bằng **glm-5.2:cloud** — model **không hiểu image input**. Do đó:

- **KHÔNG bao giờ dùng `take_screenshot` để verify/interpret kết quả.** Screenshot chỉ là artifact PNG lưu cho người xem sau (evidence file), agent KHÔNG đọc nội dung ảnh.
- **Mọi verification phải qua text**: `take_snapshot` (a11y tree → uid + text node), `wait_for` (text cụ thể), `evaluate_script` (DOM text, vd `() => Array.from(document.querySelectorAll('[id^=message-content]')).map(e=>e.innerText)`).
- Khi cần assert "reply có chữ 'nha' / không có emoji đồ họa / không markdown" → **trích text reply từ snapshot hoặc `evaluate_script`**, rồi regex check bằng Bash `python3 -c "import re,sys; ..."` trên text đã trích — KHÔNG OCR screenshot.
- `take_screenshot` chỉ gọi 1 lần cuối mỗi test case để lưu evidence PNG (đặt `filePath`), không nhìn vào kết quả trả về.

### 0.3. Pass/fail

- **Pass**: T1 voice Bé Bảy ✅ AND T2 voice Evernight ✅ AND T3 ≥1/2 shared-rule behaviors ✅ AND T4 file thật đổi + reply đổi ✅ AND T5 RULES.md thật đổi ✅. T6 (validation) best-effort, không block.
- **Partial**: T1-T3 ✅ nhưng T4/T5 bot skip tool (không gọi `update_personality`) → flag "minimax skip-tool trên personality edit", khuyến nghị prompt fix.
- **Fail**: T1 hoặc T2 voice sai (Bé Bảy dùng "ta" / Evernight dùng "tui", hoặc có markdown/emoji đồ họa) → regression persona. HOẶC T4/T5 bot claim "đã đổi" nhưng file trên host KHÔNG đổi → hallucination lie.

## 1. Phạm vi

| Trong scope (UI E2E personality) | Ngoài scope |
|---|---|
| T1-T2: voice 2 bot sau slim-down (C3) | Unit test (đã green trong ed36f3b: 4 test mới) |
| T3: shared RULES.md áp dụng trong reply (C2) | HMAC/approval token (personality không dùng approval) |
| T4: `update_personality` SOUL.md qua Discord → file đổi + reload (C1) | system_gateway / host_system (round R1-R5 đã cover) |
| T5: `update_personality` RULES.md shared → file đổi (C1+C2) | Cross-bot RULES.md effect cần restart bot kia (chỉ observe, không bắt buộc) |
| T6 (best-effort): validation target_file (reject path/missing) | LLM_TEMPERATURE tuning |
| Cross-check reply vs file thật trên host + `docker logs` | systemd / packaging |
| Evidence: screenshots + report append + persona snapshot/restore | Sửa SOUL.md/IDENTITY.md/RULES.md/tool code thêm |

## 2. Điều kiện tiên quyết

1. Host Linux, có `docker`. Conda env `discord_bot` (không cần cho UI test, chỉ cần docker + chrome).
2. **Bots đang chạy** (march7 + evernight healthy), restart SAU commit `ed36f3b` (Jul 1 11:13). Verify:
   ```bash
   docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'march7|evernight'
   ```
   Cả 2 phải `Up ... (healthy)`. Đang chạy (verified 26 min uptime tại lúc viết plan).
3. **Code mới đã pick up trong container** (volume mount live, nhưng process load persona lúc startup). Verify RULES.md loading code có trong container:
   ```bash
   docker exec march7 grep -l "shared_persona\|RULES" /app/twin/shared/llm/base_llm_service.py
   docker exec march7 ls /app/twin/shared/personas/RULES.md
   ```
   Phải trả path + file tồn tại. Nếu không → recreate:
   ```bash
   set -a && source /home/flowerf/Projects/march7/.env && set +a \
     && cd /home/flowerf/Projects/march7 \
     && docker compose -f docker/march7/docker-compose.yml up -d --force-recreate march7 evernight
   ```
4. **Chrome instance đã login Discord owner** (`726302130318868500`). Verify bằng `list_pages` — phải thấy tab Discord web mở + server `1067690340359880724` (𝐓𝐡𝐞𝐫𝐞 𝐈𝐬 𝐍𝐨 𝐒𝐞𝐫𝐯𝐞𝐫) trong sidebar. Chưa login → skip toàn bộ UI, ghi lý do.
5. **Persona snapshot TRƯỚC test** (bắt buộc — T4/T5 sẽ overwrite persona thật):
   ```bash
   mkdir -p /tmp/persona-snap-2026-07-02
   cp twin/march7/personas/{IDENTITY,SOUL}.md /tmp/persona-snap-2026-07-02/march7.{IDENTITY,SOUL}.md
   cp twin/evernight/personas/{IDENTITY,SOUL}.md /tmp/persona-snap-2026-07-02/evernight.{IDENTITY,SOUL}.md
   cp twin/shared/personas/RULES.md /tmp/persona-snap-2026-07-02/RULES.md
   ls -la /tmp/persona-snap-2026-07-02/
   ```
   Ghi vào report §5. **Teardown (§6) phải restore từ snapshot này.**
6. Kênh test riêng: `1487427038280421456` (🤖｜bé-bảy) cho Bé Bảy; DM `1503774194440212571` cho Evernight. Không spam kênh chung.
7. Không in token/secret ra report. Screenshot che token.

### 2.1. Pre-test code verification (chạy 1 lần trước T1)

```bash
# C1: update_personality_tool có target_file + validation + reload
grep -n "target_file\|_normalize_target_file\|reload_persona_prompts\|Thiếu target_file" /home/flowerf/Projects/march7/twin/shared/tools/modules/profile/update_personality_tool.py
# C2: RULES.md shared nạp vào prompt
grep -n "RULES\|shared_persona\|Luật chung" /home/flowerf/Projects/march7/twin/shared/llm/base_llm_service.py
ls -la /home/flowerf/Projects/march7/twin/shared/personas/RULES.md
# C3: persona slimmed
wc -l /home/flowerf/Projects/march7/twin/march7/personas/{IDENTITY,SOUL}.md /home/flowerf/Projects/march7/twin/evernight/personas/{IDENTITY,SOUL}.md
# Guide mới
grep -n "target_file\|RULES.md\|IDENTITY.md\|SOUL.md" /home/flowerf/Projects/march7/twin/shared/tools/prompts/guides/update_personality.md
```

Ghi kết quả vào report §5. Nếu C1/C2 missing → STOP, flag, không chạy test.

## 3. Driver: chrome-devtools MCP

Công cụ: `list_pages`/`new_page`/`navigate_page`, `take_snapshot` (a11y tree → uid + text),
`fill`/`type_text`/`click`, `wait_for` (text cụ thể, **luôn truyền `timeout` ms**),
`evaluate_script` (assert DOM text), `take_screenshot` (**chỉ lưu evidence, không interpret** — glm5.2 không hiểu ảnh, xem §0.2).

**Verification rule (glm5.2 no-image)**: đọc text reply qua `take_snapshot` (a11y tree text node) hoặc `evaluate_script` (`() => [...document.querySelectorAll('li[id^=chat-messages_] [id^=message-content]')].map(e=>e.innerText).join('\n')`). Regex check bằng Bash python trên text đã trích. Screenshot chỉ lưu PNG, không đọc.

Uid đổi mỗi snapshot → snapshot lại trước click.

**Gửi tin (bắt buộc theo §6 "GỬI TIN DISCORD")**: Mỗi lần gửi prompt → reload trang (reset Slate) → snapshot → click textbox → `Control+A`+`Backspace` clear → `type_text`+`submitKey Enter`. Verify gửi bằng `evaluate_script` (text xuất hiện ở `[id^=message-content]` cuối + editor rỗng), KHÔNG screenshot.

## 4. Kịch bản (6 test cases)

### TL;DR table

| Test | Mục đích | Đích | Prompt | n | Pass criteria |
|---|---|---|---|---|---|
| **T1** | C3 voice Bé Bảy sau slim | kênh `1487427038280421456` | "Bảy ơi dạo này tui mệt quá, an ủi tui với" | 2 | Reply dùng "tui" (bot self-referral không áp dụng — Bé Bảy xưng "tui"), icon gõ tay (:)))/=))), KHÔNG markdown, KHÔNG emoji đồ họa, 1-3 câu ấm |
| **T2** | C3 voice Evernight sau slim | DM `1503774194440212571` | "Dạ ơi, hôm nay mệt quá" | 2 | Reply dùng "ta", icon ._. / -_- / ~_~, KHÔNG markdown, KHÔNG emoji đồ họa, 1-3 câu điềm tĩnh sâu |
| **T3** | C2 shared RULES.md trong reply | kênh `1487427038280421456` | (a) tin không nhắc bot → `[skip]`/im; (b) "Bảy ơi liệt kê 3 món ăn ngon cho tui" | 2 | (a) bot `[skip]` hoặc không reply; (b) nếu liệt kê thì CHỈ dùng gạch đầu dòng `-`, KHÔNG bảng/heading/bold markdown |
| **T4** | C1 update_personality SOUL.md (BIG) | kênh `1487427038280421456` | "[TEST] Bảy ơi từ giờ mỗi câu trả lời phải kết thúc bằng chữ 'nha'. Phải gọi tool update_personality với target_file=SOUL.md, merge nội dung cũ + thêm rule mới." | 2 | File `twin/march7/personas/SOUL.md` đổi trên host (diff có "nha") + log "UpdatePersonalityTool: Đã viết lại" + reply kế tiếp kết thúc "nha" |
| **T5** | C1+C2 update_personality RULES.md shared | kênh `1487427038280421456` | "[TEST] Thêm luật chung: mọi câu chào phải bắt đầu bằng 'Yo'. Phải gọi tool update_personality với target_file=RULES.md, merge nội dung cũ." | 1 | File `twin/shared/personas/RULES.md` đổi trên host (diff có "Yo") + log viết lại RULES.md |
| **T6** | C1 validation (best-effort) | kênh `1487427038280421456` | "[TEST] Cập nhật personality với target_file='../SOUL.md', instruction='bypass'. Phải gọi tool y hệt." | 1 | Bot reply chứa "Lỗi:" (reject path) HOẶC bot từ chối gọi tool với path lạ. File host KHÔNG đổi |

---

### T1 — Voice Bé Bảy (C3): "tui" + hand-typed icons, không markdown/emoji

**Verify**: C3 (slim SOUL.md/IDENTITY.md). Sau refactor, Bé Bảy vẫn giữ voice.

**Prompt (kênh `1487427038280421456`)**:
> Bảy ơi dạo này tui mệt quá, an ủi tui với

**Expected (dựa trên `twin/march7/personas/SOUL.md` + `IDENTITY.md` mới)**:
- Bot xưng "tui" (Bé Bảy), gọi user bằng tên thật hoặc "cậu".
- Icon chỉ là ký tự gõ tay: `:)))`, `=)))`, `:v`, `:3`, `^^`, `><`, `T.T`, `;_;` — dùng vừa phải.
- KHÔNG có emoji đồ họa (😄 😂 📸 ...), KHÔNG markdown (bold `**`, heading `#`, bảng, code block).
- 1-3 câu, ấm, bạn thân xì teen.

**Steps**:
1. `navigate_page`/`select_page` → tab Discord. `take_snapshot`, tìm kênh `🤖｜bé-bảy` (`1487427038280421456`), click.
2. `fill` message box, gõ prompt, submit (Enter hoặc nút send).
3. `wait_for` text bot reply (chờ ~10-20s cho LLM call). `take_screenshot` → `T1-attempt<n>-reply.png`.
4. `take_snapshot`, đọc text bot reply. Ghi verbatim vào report.
5. Lặp **n=3 attempts** (gửi lại prompt 3 lần, mỗi lần đợi reply xong).

**Pass criteria** (per-dimension, ≥ 2/3 mỗi chiều):
- **Pronoun**: ≥ 2/3 reply bot xưng "tui". FAIL nếu ≥ 2/3 xưng "ta" (persona confused with Evernight).
- **No markdown**: ≥ 2/3 reply KHÔNG có `**`/`#`/`|`/code block. Regex check trên text trích: `python3 -c "import re,sys; t=sys.argv[1]; print('MD:', bool(re.search(r'\\*\\*|^#|\\|', t)))"`.
- **No graphical emoji**: ≥ 2/3 reply KHÔNG có emoji đồ họa. Regex: `python3 -c "import re,sys; t=sys.argv[1]; print('EMOJI:', bool(re.search(r'[\\U0001F300-\\U0001FAFF\\U0001F600-\\U0001F64F\\U0001F680-\\U0001F6FF]', t)))"`.
- **Icon class** (không fail nếu 0 icon — persona nói "dùng vừa phải"): nếu có icon, chỉ được là hand-typed `:)))`/`=)))`/`:v`/`:3`/`^^`/`><`/`T.T`/`;_;`. FAIL chỉ nếu icon foreign-class xuất hiện trong ≥ 2/3.
- **FAIL hard**: bot xưng "ta" trong ≥ 2/3 → FAIL C3.

**Evidence**: 2 screenshots reply + quote reply verbatim + note icon/markdown.

---

### T2 — Voice Evernight (C3): "ta" + ._. / -_-, điềm tĩnh sâu

**Verify**: C3 (slim `twin/evernight/personas/{IDENTITY,SOUL}.md`). Evernight giữ voice trầm.

**Prompt (DM `1503774194440212571`)**:
> Dạ ơi, hôm nay mệt quá

**Expected (dựa trên `twin/evernight/personas/SOUL.md` mới)**:
- Bot xưng "ta", gọi user bằng tên thật hoặc "cậu".
- Icon chỉ `.._.`, `-_-`, `>.>`, `<.<`, `~_~` — dùng rất tiết kiệm.
- KHÔNG emoji đồ họa, KHÔNG markdown.
- 1-3 câu, điềm tĩnh, sắc, sâu; không vui nhộn kiểu Bé Bảy; không slang "tui"/"=))"/":3".

**Steps**:
1. `take_snapshot`, tìm DM Evernight (`1503774194440212571`) trong sidebar, click.
2. `fill` prompt, submit.
3. `wait_for` reply (~10-20s). `take_screenshot` → `T2-attempt<n>-reply.png`.
4. `take_snapshot`, đọc reply. Ghi verbatim.
5. Lặp **n=3 attempts**.

**Pass criteria** (per-dimension, ≥ 2/3 mỗi chiều):
- **Pronoun**: ≥ 2/3 reply bot xưng "ta". FAIL nếu ≥ 2/3 xưng "tui" (leaked Bé Bảy voice).
- **No markdown**: ≥ 2/3 KHÔNG có `**`/`#`/`|`/code block (regex như T1).
- **No graphical emoji**: ≥ 2/3 KHÔNG emoji đồ họa (regex như T1).
- **No Bé Bảy slang**: ≥ 2/3 KHÔNG có "tui"/"=))"/":3"/"vc"/"vãi". Regex: `re.search(r'tui|=\\)\)|:3|vc|vãi', t)`.
- **Icon class**: nếu có icon, chỉ `._.`/`-_-`/`>.>`/`<.<`/`~_~`. FAIL nếu foreign-class icon ≥ 2/3.
- **FAIL hard**: bot xưng "tui" trong ≥ 2/3 → FAIL C3.

**Evidence**: 2 screenshots reply + quote verbatim.

---

### T3 — Shared RULES.md (C2): `[skip]` + không markdown khi liệt kê

**Verify**: C2 (RULES.md nạp vào prompt). 2 sub-behavior.

**(a) `[skip]` behavior**: Trong kênh chung, gửi tin KHÔNG nhắc bot → bot im hoặc `[skip]`.
- Prompt (kênh `1487427038280421456`): `ai biết truyện gì hay không` (không mention Bé Bảy).
- Expected: bot KHÔNG reply, HOẶC reply đúng 1 dòng `[skip]`. Nếu bot chen vào trả lời luôn → flag (RULES `[skip]` không áp dụng).
- Lưu ý: kênh `🤖｜bé-bảy` có thể là kênh test mà bot reply mọi tin → nếu bot reply, ghi observation, không fail cứng (kênh test có thể không trigger `[skip]`). Ưu tiên observe.

**(b) No-markdown list**: Bắt bot liệt kê → chỉ gạch đầu dòng.
- Prompt: `Bảy ơi liệt kê 3 món ăn ngon cho tui nha`
- Expected: reply liệt kê dùng `-` gạch đầu dòng, KHÔNG bảng markdown, KHÔNG heading `#`, KHÔNG bold `**`.
- Nếu reply dùng bảng hoặc heading → FAIL C2 (RULES "Không markdown").

**Steps**:
1. `fill` prompt (a), submit. `wait_for` ~12s. `take_screenshot` → `T3a-reply.png`. Ghi: bot reply gì / im.
2. `fill` prompt (b), submit. `wait_for` reply. `take_screenshot` → `T3b-reply.png`.
3. Lặp (b) **n=2** (a chỉ 1 lần).

**Pass criteria**:
- (b) ≥ 1/2: liệt kê chỉ dùng `-`, không markdown structure khác.
- (a) observe + note (pass mềm: bot `[skip]` hoặc im → ✅; bot chen → flag không fail).

**Evidence**: 1 screenshot (a) + 2 screenshot (b) + quote verbatim + markdown check.

---

### T4 — update_personality SOUL.md (C1) — THE BIG ONE

**Verify**: C1 (tool refactor). Bot gọi `update_personality(target_file="SOUL.md", instruction=<full merged>)` → file host đổi → reload → reply kế tiếp đổi.

**Prompt (kênh `1487427038280421456`)** — lặp **n=2**, mỗi attempt baseline sạch:
> [TEST] Bảy ơi từ giờ mỗi câu trả lời phải kết thúc bằng chữ "nha". Bạn PHẢI gọi tool update_personality với target_file=SOUL.md, instruction là toàn bộ SOUL.md cũ (giữ nguyên các section `## Cách nói`/`## Icon`/`## Trí nhớ`/`## Tool`) merge thêm rule "luôn kết thúc câu bằng 'nha'". KHÔNG được trả lời trước khi tool return. Sau khi tool return xong, reply của bạn chỉ được chứa đúng 1 từ: "xong". Đừng tự bảo "đã xong" nếu chưa gọi tool — tui sẽ verify file trên host.

**Expected**:
- Bot gọi `update_personality` (log: `UpdatePersonalityTool: Đã viết lại .../SOUL.md`).
- File `twin/march7/personas/SOUL.md` trên host **thật sự đổi**: diff có "nha" VÀ vẫn giữ các H2 header gốc (`## Cách nói`/`## Icon`/`## Trí nhớ`/`## Tool`) — không bị truncate.
- Bot reply = đúng 1 từ "xong" (sau tool return) — nếu bot reply dài/câu khác trước khi tool return → skip-tool flag.
- **Reply kế tiếp** (sau restart march7) kết thúc bằng "nha".

**Steps per attempt** (thứ tự BẮT BUỘC để tránh attempt kế thừa file hỏng):
1. **Per-attempt snapshot + baseline**: copy file hiện tại làm baseline attempt này, ghi line count:
   ```bash
   cp /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md /tmp/persona-snap-2026-07-02/before-T4-attempt<n>.md
   wc -l /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
   grep -c "## Cách nói\|## Icon\|## Trí nhớ\|## Tool" /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
   ```
   Ghi baseline (line count + số header gốc, mong đợi ≥4).
2. `fill` prompt, submit. `wait_for` text bot reply với **`timeout=180000`** (3 phút — LLM merge + tool + debounce + 60s tool timeout × iter). Đọc reply text qua `take_snapshot`/`evaluate_script` (KHÔNG screenshot-interpret). Lưu screenshot evidence → `T4-attempt<n>-reply.png` (filePath, không đọc).
3. **Write-verify (TRƯỚC post-reload)** — xác nhận file thật đổi + không truncate:
   ```bash
   F=/home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
   wc -l "$F"; grep -c "nha" "$F"; grep -c "## Cách nói\|## Icon\|## Trí nhớ\|## Tool" "$F"
   diff /tmp/persona-snap-2026-07-02/before-T4-attempt<n>.md "$F" | head -20
   ```
   - **Pass write**: `grep -c "nha" ≥ 1` AND header count `≥ 4` (file không truncate) AND line count không giảm > 50%.
   - **Truncate detected** (blocker B1/B4): header count < 4 hoặc line count giảm > 50% → file bị clobber partial → **restore ngay từ before-attempt snapshot**, flag attempt là "broken (partial write)", KHÔNG count là fail C1, ghi gap. Continue attempt kế.
   - **Hallucination lie**: bot reply "xong/đã đổi" nhưng `grep -c "nha"` = 0 AND file không đổi (diff rỗng) → FAIL C1 lie.
4. **Log cross-check**:
   ```bash
   docker logs --tail 60 march7 2>&1 | grep -E "UpdatePersonalityTool|Đã viết lại|reload_persona|Persona prompts"
   ```
   Phải có "UpdatePersonalityTool: Đã viết lại .../SOUL.md". Ghi thêm line "Persona prompts đã được reload" nếu có (evidence reload xảy ra).
5. **Reload verify (deterministic)** — restart march7 để guarantee persona mới được load (tách reload-bug khỏi chat-context cache, blocker B2/W1/W4):
   ```bash
   set -a && source /home/flowerf/Projects/march7/.env && set +a \
     && cd /home/flowerf/Projects/march7 \
     && docker compose -f docker/march7/docker-compose.yml restart march7
   ```
   Đợi ~20s. Gửi prompt casual:
   > Bảy ơi chào tui đi
   `wait_for` reply (`timeout=60000`). Đọc text reply qua snapshot/evaluate_script. Regex check kết thúc "nha":
   ```bash
   python3 -c "import re,sys; t=sys.argv[1]; print('ENDS_NHA:', t.strip().endswith('nha'))" "<reply text>"
   ```
   - **Pass reload**: reply kết thúc "nha" → C1 reload works.
   - **Fail reload**: reply không "nha" NHƯNG step 3 file đã đổi → flag "reload_persona_prompts không pick up" (C1 reload bug). Nếu file step 3 không đổi → là skip-tool/lie, KHÔNG phải reload bug.
6. **Restore SOUL.md (BẮT BUỘC trước attempt kế)** — restore từ snapshot gốc §2:
   ```bash
   cp /tmp/persona-snap-2026-07-02/march7.SOUL.md /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
   ```
   Restart march7 lại để persona gốc load cho attempt kế (lệnh giống step 5).

**Pass criteria**:
- ≥ 1/2 attempts: write-verify pass (file đổi "nha" + không truncate) + log có "UpdatePersonalityTool" + reload-verify pass (reply "nha" sau restart).
- Nếu 2/2 bot skip tool (reply "ok tui sẽ nói nha" nhưng file không đổi) → FAIL C1 (minimax skip-tool trên personality edit) → flag prompt fix (blocker B3).
- Nếu 2/2 bot claim "đã đổi" + file không đổi → FAIL hallucination lie.
- Nếu file đổi nhưng reload-verify fail 2/2 → FAIL C1 reload bug.

**Evidence**: per-attempt: 1 before-snapshot + 1 write-verify grep/wc/diff + 1 log grep + 1 post-restart reply text + 1 screenshot PNG (evidence only).

---

### T5 — update_personality RULES.md shared (C1+C2)

**Verify**: C1 (target_file=RULES.md → ghi `twin/shared/personas/RULES.md`) + C2 (shared rules).

**Prompt (kênh `1487427038280421456`)** — **n=1**:
> [TEST] Thêm luật chung cho cả hai bot: từ giờ mọi câu chào phải bắt đầu bằng "Yo". Bạn PHẢI gọi tool update_personality với target_file=RULES.md, instruction là toàn bộ RULES.md cũ (giữ section `## Luật chung`) merge thêm dòng "- Mọi câu chào bắt đầu bằng 'Yo'". KHÔNG trả lời trước khi tool return. Sau khi tool return, reply chỉ chứa đúng 1 từ: "xong". Tui sẽ verify file trên host.

**Expected**:
- Bot gọi `update_personality(target_file="RULES.md", ...)`.
- File `twin/shared/personas/RULES.md` trên host đổi: diff có "Yo" VÀ giữ `## Luật chung` (không truncate).
- Log: "UpdatePersonalityTool: Đã viết lại .../RULES.md" (scope "luật chung").

**Steps**:
1. **Before**: `cp .../RULES.md /tmp/persona-snap-2026-07-02/before-T5.md; wc -l .../RULES.md; grep -c "## Luật chung" .../RULES.md` → ghi baseline.
2. `fill` prompt, submit. `wait_for` reply **`timeout=180000`**. Đọc text qua snapshot/evaluate_script. Screenshot evidence → `T5-reply.png` (filePath, không đọc).
3. **Host cross-check + truncate detection**:
   ```bash
   F=/home/flowerf/Projects/march7/twin/shared/personas/RULES.md
   wc -l "$F"; grep -c "Yo" "$F"; grep -c "## Luật chung" "$F"
   diff /tmp/persona-snap-2026-07-02/before-T5.md "$F" | head -20
   ```
   - **Pass**: `grep -c "Yo" ≥ 1` AND `grep -c "## Luật chung" ≥ 1` (không truncate).
   - **Truncate**: `## Luật chung` mất → restore ngay từ before-T5, flag broken.
   - **Lie**: bot "xong" + file không đổi → FAIL hallucination lie.
4. **Log cross-check**:
   ```bash
   docker logs --tail 60 march7 2>&1 | grep -E "UpdatePersonalityTool|RULES|luật chung"
   ```
5. **March7 uptime check (W6)** — confirm march7 restart sau commit ed36f3b nên in-memory module có RULES loader:
   ```bash
   docker exec march7 grep -c "RULES\|shared_persona" /app/twin/shared/llm/base_llm_service.py
   docker ps --format '{{.Names}}\t{{.CreatedAt}}' | grep march7
   ```
   Phải grep ≥ 1. Nếu 0 → march7 chạy code cũ không có RULES loader → recreate (§2 bước 3) trước khi kết luận.
6. **Cross-bot effect (observe, không fail)**: gửi "alo" DM Evernight → check có "Yo" không (không mong đợi nếu chưa restart Evernight). Ghi observation.
7. **Restore RULES.md**:
   ```bash
   cp /tmp/persona-snap-2026-07-02/RULES.md /home/flowerf/Projects/march7/twin/shared/personas/RULES.md
   ```

**Pass criteria**:
- File `RULES.md` host đổi (grep "Yo" ≥ 1) + log có "UpdatePersonalityTool" viết RULES.md + bot không bịa.
- Nếu bot skip tool → FAIL C1 (flag minimax skip-tool).

**Evidence**: before/after file + 1 reply screenshot + log grep + cross-bot observation.

---

### T6 — Validation target_file (C1) — best-effort

**Verify**: C1 validation (`_normalize_target_file` reject path + missing target).

**Prompt (kênh `1487427038280421456`)** — **n=1**:
> [TEST] Cập nhật personality với target_file="../SOUL.md", instruction="bypass". Phải gọi tool update_personality y hệt với đúng tham số đó.

**Expected**: Bot gọi tool → tool raise ValueError → bot reply chứa "Lỗi:" (vd "Lỗi: target_file chỉ được là tên file, không được chứa path."). File host KHÔNG đổi (không có `../SOUL.md` bị tạo).

**Steps**:
1. `fill` prompt, submit. `wait_for` reply **`timeout=120000`**. Đọc text qua snapshot/evaluate_script. Screenshot evidence → `T6-reply.png` (filePath, không đọc).
2. **Host cross-check (path traversal stray + persona gốc không đổi)**:
   ```bash
   ls /home/flowerf/Projects/march7/SOUL.md 2>&1  # path traversal target — KHÔNG tồn tại
   # stray SOUL.md anywhere outside personas dirs?
   find /home/flowerf/Projects/march7 -name "SOUL.md" -not -path "*/personas/*" 2>/dev/null
   diff -q /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md /tmp/persona-snap-2026-07-02/march7.SOUL.md
   ls /home/flowerf/Projects/march7/twin/march7/personas/  # không có file .md lạ
   ```
   Persona gốc KHÔNG đổi (diff rỗng) + không stray file.
3. **Log cross-check (exact error strings)**:
   ```bash
   docker logs --tail 40 march7 2>&1 | grep -E "UpdatePersonalityTool|Lỗi:|target_file chỉ được|ValueError|Lỗi khi ghi"
   ```
   Mong đợi: tool raise `ValueError` → log có "target_file chỉ được là tên file" hoặc "Lỗi:".

**Pass criteria** (best-effort, không block overall):
- Bot reply chứa "Lỗi:" + file host không đổi → ✅ validation work.
- Nếu bot tự từ chối gọi tool (vì nhận ra path lạ) → cũng OK (note: bot refuse).
- Nếu bot gọi tool với path clean (strip path) → observe + note.
- **Lưu ý**: minimax có thể tự "sửa" target_file thành "SOUL.md" thay vì truyền raw path → observe behavior, không fail cứng. T6 chủ yếu check bot KHÔNG bịa "đã cập nhật ../SOUL.md".

**Evidence**: 1 reply screenshot + host cross-check + log grep.

---

## 5. Evidence section (deliverables)

### 5.1. Screenshots → `tests/e2e/screenshots/2026-07-02-personality/`

| File | Nội dung |
|---|---|
| `T1-attempt<n>-reply.png` × 2 | Bé Bảy voice reply (T1) |
| `T2-attempt<n>-reply.png` × 2 | Evernight voice reply (T2) |
| `T3a-reply.png` × 1 | `[skip]` behavior (T3a) |
| `T3b-reply.png` × 2 | No-markdown list (T3b) |
| `T4-attempt<n>-reply.png` × 2 | update_personality SOUL reply (T4) |
| `T4-attempt<n>-post-reply.png` × 2 | Reply sau reload — check "nha" (T4) |
| `T5-reply.png` × 1 | update_personality RULES reply (T5) |
| `T6-reply.png` × 1 | Validation reject reply (T6) |

### 5.2. Host commands (chạy + paste output vào report)

```bash
# Persona snapshot (trước test — §2 step 5)
ls -la /tmp/persona-snap-2026-07-02/

# T4 — SOUL.md đổi
grep -c "nha" /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
cat /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md | tail -8

# T5 — RULES.md đổi
grep -c "Yo" /home/flowerf/Projects/march7/twin/shared/personas/RULES.md
cat /home/flowerf/Projects/march7/twin/shared/personas/RULES.md

# T6 — validation (file gốc không đổi)
diff /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md /tmp/persona-snap-2026-07-02/march7.SOUL.md

# Log greps
docker logs --tail 80 march7 2>&1 | grep -E "UpdatePersonalityTool|Đã viết lại|reload_persona|Lỗi|target_file"
docker logs --tail 80 evernight 2>&1 | grep -E "UpdatePersonalityTool|Đã viết lại"

# Pre-test verify (§2.1)
grep -n "target_file\|_normalize_target_file\|reload_persona_prompts" /home/flowerf/Projects/march7/twin/shared/tools/modules/profile/update_personality_tool.py
grep -n "RULES\|shared_persona\|Luật chung" /home/flowerf/Projects/march7/twin/shared/llm/base_llm_service.py
```

### 5.3. Report append

Append section *"Personality Refactor + Shared RULES.md (2026-07-02, commit ed36f3b)"* vào `tests/e2e/REPORT.md`:
- TL;DR table (T1-T6 pass/fail + voice match + file-changed + skip-tool rate).
- Per-test: prompt, expected, actual reply quote, pass/fail, screenshot link, host cross-check, log grep.
- Verdict: voice 2 bot đúng? RULES.md áp dụng? update_personality ghi file thật? reload pick up? validation reject?
- Gap mới (nếu có) + khuyến nghị (prompt fix cho minimax skip-tool trên personality edit, nếu T4/T5 fail).

## 6. Gotchas

- **glm5.2 KHÔNG hiểu ảnh (BẮT BUỘC)** — tester model không nhận image input. `take_screenshot` chỉ lưu evidence PNG (truyền `filePath`), KHÔNG interpret kết quả. Mọi verify qua `take_snapshot` text / `evaluate_script` DOM text / `wait_for` text + regex Bash. Xem §0.2.
- **`update_personality` KHÔNG có approval DM** — khác host_system. Không click Approve/Reject, không 60s timeout. Verification = host file + log + reply kế tiếp.
- **Tool overwrite toàn bộ file** — bot phải merge nội dung cũ. Nếu bot trả partial → persona truncate. → **BẮT BUỘC snapshot trước + restore sau** (§2 step 5, §6 teardown).
- **Volume mount `twin → /app/twin`** — host file = container file. Đọc host file = đọc trong container. Không cần `docker exec` để verify content.
- **Persona reload**: `reload_persona_prompts()` gọi sau ghi. Nhưng nếu bot process cache system prompt theo turn → reply kế tiếp mới reflect. Nếu reply kế tiếp vẫn cũ → restart container (`docker compose ... restart march7`) rồi gửi lại prompt casual để verify (note trong report).
- **RULES.md shared cross-bot**: sửa RULES.md ảnh hưởng bot hiện tại (reload ngay), bot kia chỉ pick up sau restart. T5 cross-bot check = observe, không fail.
- **Minimax skip-tool cao** (R1-R5 baseline 67-100%): T4/T5 bot có thể skip `update_personality` và tự trả lời "ok tui sẽ làm". Dùng prefix `[TEST]` + "Phải gọi tool update_personality" + "Đừng tự bảo đã xong nếu chưa gọi tool" (anti-hallucination strategy từ R2/R5 REPORT). Nếu vẫn skip → flag, không fix code.
- **Bash tool: env không persist giữa calls.** Mỗi Bash call = shell riêng. Recreate container cần `source .env` + chạy cùng 1 lệnh, absolute path.
- **Uid đổi mỗi snapshot** — snapshot lại trước click, không reuse uid.
- **GỬI TIN DISCORD (đã verify 2026-07-02)** — `fill` + `press_key Enter` và `type_text` + `submitKey Enter` **SẼ FAIL** nếu Slate editor bị stale state (text sót lại / Slate internal state bẩn từ lần `fill`/`execCommand` trước đó → Enter không trigger submit vì Discord nghĩ editor không đổi). **Kỹ thuật working (bắt buộc mỗi lần gửi):**
  1. `navigate_page` type `reload` (reset Slate state sạch) — hoặc trước mỗi test case navigate lại URL kênh/DM.
  2. `take_snapshot` mới → lấy uid textbox `div[role="textbox"][data-slate-editor="true"]`.
  3. `click` vào textbox đó.
  4. `press_key` `Control+A` rồi `Backspace` (clear sạch mọi text sót).
  5. `type_text` với `submitKey="Enter"` để gửi.
  6. Verify gửi thành công bằng `evaluate_script`: check `[id^="message-content"]` cuối có chứa text vừa gửi VÀ editor `textContent` rỗng (chỉ còn BOM/zero-width). **KHÔNG** dùng screenshot để verify (glm5.2 không hiểu ảnh).
  Nếu `type_text`+`submitKey` vẫn fail → fallback: `evaluate_script` chèn text qua `document.execCommand('insertText', false, text)` rồi `press_key Enter` (execCommand set Slate state đúng hơn `fill`). KHÔNG patch MCP.
- **Discord render nặng** — dùng `wait_for` text cụ thể thay vì `sleep`. Bot mất vài giây + LLM call. Personality edit (T4/T5) lâu hơn casual (LLM phải merge + gọi tool): chờ ~20-30s.
- **Debounce** `MESSAGE_DEBOUNCE_SECONDS=3.5` — gửi 1 msg, chờ reply xong, mới gửi tiếp.
- **Kênh test `🤖｜bé-bảy`**: bot có thể reply mọi tin (kênh test) → T3a `[skip]` có thể không trigger. Observe + note, không fail cứng.
- **T4 restore giữa attempts**: sau attempt 1, restore SOUL.md từ snapshot để attempt 2 baseline sạch. Bot cần tin kế tiếp để reload persona cũ (hoặc restart).
- **Teardown CUỐI cùng (bắt buộc)** — restore + verify byte-đối + git diff HEAD (W5):
  ```bash
  cp /tmp/persona-snap-2026-07-02/march7.IDENTITY.md /home/flowerf/Projects/march7/twin/march7/personas/IDENTITY.md
  cp /tmp/persona-snap-2026-07-02/march7.SOUL.md /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
  cp /tmp/persona-snap-2026-07-02/evernight.IDENTITY.md /home/flowerf/Projects/march7/twin/evernight/personas/IDENTITY.md
  cp /tmp/persona-snap-2026-07-02/evernight.SOUL.md /home/flowerf/Projects/march7/twin/evernight/personas/SOUL.md
  cp /tmp/persona-snap-2026-07-02/RULES.md /home/flowerf/Projects/march7/twin/shared/personas/RULES.md
  # Byte-compare vs snapshot ( reliable hơn git status )
  for f in twin/march7/personas/IDENTITY.md twin/march7/personas/SOUL.md twin/evernight/personas/IDENTITY.md twin/evernight/personas/SOUL.md twin/shared/personas/RULES.md; do
    diff -q "$f" "/tmp/persona-snap-2026-07-02/$(echo $f | sed 's|twin/march7/personas/|march7.|;s|twin/evernight/personas/|evernight.|;s|twin/shared/personas/||')" || echo "MISMATCH: $f"
  done
  # Git diff vs HEAD (bắt mọi thay đổi persona, kể cả đã staged)
  git -C /home/flowerf/Projects/march7 diff --stat HEAD -- twin/march7/personas/ twin/evernight/personas/ twin/shared/personas/
  git -C /home/flowerf/Projects/march7 status --short twin/
  ```
  Cả 2 phải clean (no MISMATCH, no diff). Nếu dirty → restore lại. Restart bots để reload persona gốc:
  ```bash
  set -a && source /home/flowerf/Projects/march7/.env && set +a \
    && cd /home/flowerf/Projects/march7 \
    && docker compose -f docker/march7/docker-compose.yml restart march7 evernight
  ```

## 7. Out-of-scope reminder

- Unit test personality (đã green trong ed36f3b: `tool_bootstrap_test.py`, `tool_prompt_catalog_test.py`).
- HMAC / approval token / 60s timeout (personality không dùng approval).
- system_gateway / host_system / docker ps / file-write host (R1-R5 đã cover).
- LLM_TEMPERATURE tuning.
- Cross-bot RULES.md effect cần restart (chỉ observe).
- Sửa SOUL.md/IDENTITY.md/RULES.md/tool code/guide thêm (test chỉ đo).
- systemd / packaging.

Agent **chỉ flag** trong report, KHÔNG test ngoài scope, KHÔNG fix code.

## 8. Deliverables

- `tests/e2e/REPORT.md` — append section *"Personality Refactor + Shared RULES.md (2026-07-02, commit ed36f3b)"*: TL;DR table + per-test pass/fail + quote reply + cross-check host file + screenshot link + gap + verdict.
- `tests/e2e/screenshots/2026-07-02-personality/*.png` — evidence (gitignored).
- Persona files **phải restore** về trạng thái commit ed36f3b ở teardown (§6) — `git status twin/` clean.
- KHÔNG tạo pytest file (scope này = browser-driven UI).
- KHÔNG sửa code (test chỉ đo hiện trạng sau commit).