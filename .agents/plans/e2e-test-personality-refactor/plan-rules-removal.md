---
status: ready-for-handoff
created: 2026-07-02
owner: e2e-tester (Sonnet, browser-driven via chrome-devtools MCP)
style: browser-driven E2E via chrome-devtools MCP — drive real Discord web UI,
  type messages, observe bot replies, verify persona files on host. NOT a pytest suite.
change_under_test: working-tree changes on branch feat/agent-action-loop (NOT a commit yet)
test_channel: 1487427038280421456 (🤖｜bé-bảy) trong server 1067690340359880724
evernight_dm: 1503774194440212571 (DM Evernight ↔ owner)
owner_discord_id: 726302130318868500
bot_llm: minimax-m3:cloud (LM Studio)
screenshots_dir: tests/e2e/screenshots/2026-07-02-rules-removal/
report: tests/e2e/REPORT.md (append a new section, do NOT overwrite)
---

# E2E Test Plan — RULES.md removal + old SOUL/IDENTITY restore

## 0. Mục tiêu

Verify các thay đổi working-tree (partial revert của commit ed36f3b) qua Discord web thật.
Bot containers ĐÃ restart lúc ~15:53 (Jul 2) và đã pick up thay đổi (verified in-container).

| # | Thay đổi | Kỳ vọng cần verify |
|---|---|---|
| **C1** | Bỏ `twin/shared/personas/RULES.md` + code load nó (`base_llm_service.static_rules`) | Bot vẫn chạy bình thường, KHÔNG lỗi; rule chung (cấm markdown, dùng "-") vẫn còn vì đã inline lại trong SOUL |
| **C2** | Khôi phục SOUL.md + IDENTITY.md CŨ (đầy đủ, có "QUY TẮC QUAN TRỌNG") cho cả 2 bot | **Voice enforcement mạnh trở lại**: Bé Bảy "tui"+icon; **Evernight "ta"+icon** (đây là điểm slim-SOUL trước đây FAIL — T2 cũ 0/3) |
| **C3** | Guide `update_personality.md` viết lại: bỏ RULES.md, làm rõ khi nào sửa IDENTITY vs SOUL | Khi bot gọi `update_personality`, Refine chọn đúng target_file (best-effort — bot hay refuse) |

**Giả thuyết chính (headline)**: khôi phục SOUL cũ đầy đủ sẽ FIX regression giọng Evernight
(round trước slim-SOUL → Evernight 0/3 dùng "ta"/icon). T2 giờ phải PASS.

**KHÔNG sửa code trong lúc test.** Nếu T4 làm đổi persona file → BẮT BUỘC restore ở teardown.

## 0.1. Tester = Sonnet (hiểu ảnh) — nhưng ưu tiên verify bằng DOM text

- Sonnet đọc được screenshot, nhưng để assert chính xác (có chữ "tui"/"ta", có markdown/emoji không) →
  **trích text reply bằng `evaluate_script`** rồi kiểm bằng regex, đừng chỉ nhìn ảnh.
  ```js
  () => Array.from(document.querySelectorAll('[id^=message-content]')).map(e => e.innerText)
  ```
- `take_screenshot(filePath=...)` mỗi test case 1 lần để lưu evidence PNG.

## 0.2. Gotcha gửi tin Discord (chrome-devtools — ĐÃ verify 2026-07-02, BẮT BUỘC)

`fill`+Enter và `type_text`+Enter FAIL khi Slate editor stale-state. Cách gửi ổn định:
1. `navigate_page` reload URL kênh/DM → `wait_for` text đã có sẵn trên trang
2. `take_snapshot` → tìm uid của textbox ("Nhắn #..." / "Message ...")
3. `click` textbox → `press_key "Control+a"` → `press_key "Backspace"` (xoá sạch stale)
4. `type_text` với `submitKey: "Enter"`
5. Chờ reply: `wait_for` hoặc poll `evaluate_script` lấy message-content mới nhất
6. Verify bằng text đã trích (KHÔNG chỉ nhìn ảnh)

Bot minimax mất ~3-15s trả lời; poll tối đa ~40s mỗi tin.

## 1. Setup / tiền đề (đã xong, chỉ cần confirm)

- march7 + evernight `Up ... (healthy)` — verify: `docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'march7|evernight'`
- In-container đã confirm: RULES.md gone, SOUL có "QUY TẮC QUAN TRỌNG", base_llm 0 ref static_rules.
- Discord web: profile Chrome đã từng login. Navigate tới:
  - Kênh test: `https://discord.com/channels/1067690340359880724/1487427038280421456`
  - DM Evernight: `https://discord.com/channels/@me/1503774194440212571`
  Nếu bị đá ra login → STOP, báo owner (không tự đăng nhập).

## 2. Snapshot persona (TRƯỚC T4 — phòng bot overwrite hỏng file)

```bash
mkdir -p /tmp/persona-snap-rules-removal
cp twin/march7/personas/SOUL.md twin/march7/personas/IDENTITY.md \
   twin/evernight/personas/SOUL.md twin/evernight/personas/IDENTITY.md \
   /tmp/persona-snap-rules-removal/
git -C /home/flowerf/Projects/march7 status --short twin/  # kỳ vọng: chỉ 4 file persona đang M (do restore), không thêm gì
```

## 3. Test cases

### T1 — Voice Bé Bảy (kênh test) — n=2

Prompt (kênh `🤖｜bé-bảy`): `Bảy ơi dạo này tui mệt quá, an ủi tui vài câu đi` (gửi 2 lần, cách ~20s).
**PASS khi**: reply xưng **"tui"**, có icon gõ tay (`:v` / `:3` / `=)))` / `^^`), **KHÔNG** markdown (`**`, `#`, `|`, ```` ``` ````), **KHÔNG** emoji đồ hoạ (😄😂…), giọng ấm/xì-teen.
Regex fail nếu: reply dùng "ta" để tự xưng, hoặc có emoji đồ hoạ, hoặc có bảng/heading markdown.

### T2 — Voice Evernight (DM Evernight) — n=3  ★ HEADLINE

Prompt (DM Evernight): `Dạ ơi, hôm nay ta thấy hơi mệt` (gửi 3 lần, cách ~20s).
**PASS khi (≥2/3)**: Evernight tự xưng **"ta"** (KHÔNG "tui"), giọng điềm tĩnh/tối, icon nếu có chỉ là `._.` `-_-` `>.>` `<.<` `~_~`, **KHÔNG** slang Bé Bảy (`tui`/`=))`/`:3`/`khum`), **KHÔNG** markdown/emoji đồ hoạ.
**Đây là test quan trọng nhất** — so với round trước (slim SOUL) Evernight 0/3 dùng "ta". Ghi rõ tỉ lệ x/3.
Cũng check: reply KHÔNG leak marker `[context cũ ...]` (bug memory leak pre-existing — nếu thấy, ghi nhận là bug cũ, không tính vào pass/fail của change này).

### T3 — Rule chung vẫn áp dụng dù bỏ RULES.md (kênh test) — n=1

Prompt: `Bảy ơi liệt kê giúp tui 3 món ăn sáng ngon đi`.
**PASS khi**: liệt kê bằng gạch đầu dòng `-` hoặc câu tách dòng, **KHÔNG** bảng/heading/bold markdown, **KHÔNG** code block. → chứng minh rule "không markdown / liệt kê bằng -" (giờ nằm trong SOUL cũ) vẫn hiệu lực sau khi bỏ RULES.md.

### T4 — update_personality routing (best-effort, GUARDED) — n=1–2

> ⚠️ Bot minimax hay REFUSE `update_personality` qua chat (round trước T4/T5 đều refuse). Đây KHÔNG phải regression của change này. Mục tiêu T4 chỉ là quan sát:
> (a) bot có gọi tool không; (b) nếu có, Refine có chọn đúng `target_file` (SOUL.md cho đổi giọng) theo guide mới không.

Prompt (kênh test): `[TEST] Bảy ơi, thêm cho tui một quy tắc vào cách nói của cậu: thỉnh thoảng kết câu bằng "nghen". Dùng tool update_personality, ghi vào SOUL.md, merge giữ nguyên nội dung cũ.`
Quan sát:
- Nếu bot **refuse / không gọi tool** → ghi "confirm known gap: minimax refuse personality edit qua chat", KHÔNG fail change này.
- Nếu bot **gọi tool** → check `docker logs march7 --tail 40` có `AgentLoop selected update_personality` + `executed successfully`, và `git diff twin/march7/personas/SOUL.md` xem có thêm "nghen" + target đúng SOUL.md (không phải IDENTITY.md).

## 4. Teardown (BẮT BUỘC)

```bash
# Restore persona nếu T4 làm đổi bất kỳ file nào
cp /tmp/persona-snap-rules-removal/SOUL.md      twin/march7/personas/SOUL.md
cp /tmp/persona-snap-rules-removal/IDENTITY.md  twin/march7/personas/IDENTITY.md
cp /tmp/persona-snap-rules-removal/*evernight* 2>/dev/null  # nếu có
git -C /home/flowerf/Projects/march7 status --short twin/   # phải về đúng 4 file M như trước T4
```
Chỉ restore file bị đổi ngoài ý muốn; 4 file persona đang ở trạng thái "đã khôi phục bản cũ" là ĐÚNG, giữ nguyên.
Nếu T4 ghi file thật → sau restore, restart lại march7 để nạp lại bản đúng: `docker compose -f docker/docker-compose.yml restart march7`.

## 5. Deliverable

Append 1 section mới vào `tests/e2e/REPORT.md` (KHÔNG overwrite phần cũ):
- Tiêu đề: `## RULES.md removal + old SOUL/IDENTITY restore (2026-07-02, working-tree feat/agent-action-loop)`
- Bảng TL;DR: T1/T2/T3/T4 PASS/FAIL + tỉ lệ.
- So sánh T2 với round slim-SOUL trước (0/3 "ta") — chứng minh có fix regression hay không.
- Text reply thật đã trích (evidence), path screenshot PNG.
- Verdict + gap còn lại (memory leak marker nếu gặp; personality-edit refuse nếu gặp).

## 6. Pass/Fail tổng

- **PASS**: T1 ✅ AND T2 ≥2/3 ✅ AND T3 ✅ (T4 best-effort, không block).
- **FAIL (regression)**: T1 Bé Bảy dùng "ta"/emoji đồ hoạ, HOẶC T2 Evernight vẫn 0/3 "ta" (slim-SOUL chưa được fix), HOẶC T3 có markdown table/heading.
- **Điểm mấu chốt**: nếu T2 giờ PASS mà round trước FAIL → xác nhận việc khôi phục SOUL cũ đã fix regression giọng Evernight.
