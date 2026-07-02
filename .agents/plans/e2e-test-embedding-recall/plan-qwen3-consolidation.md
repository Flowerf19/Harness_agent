---
status: ready-for-handoff
created: 2026-07-02
owner: e2e-tester (Sonnet, browser-driven via chrome-devtools MCP)
style: browser-driven E2E via chrome-devtools MCP — drive real Discord web UI,
  type messages, observe bot replies, verify T2/embedding on host. NOT a pytest suite.
change_under_test:
  - commit cda3330 (embedding e5-small → qwen3-embedding:0.6b, dim 1024, gate T2_MIN_COSINE=0.45,
    empty prefixes; consolidation reasoning_effort=low + max_tokens=4000; trace logger import fix)
  - working-tree (uncommitted): include_persona=False cho consolidation (bỏ persona khỏi system prompt)
test_channel: 1487427038280421456 (🤖｜bé-bảy) trong server 1067690340359880724
evernight_dm: 1503774194440212571 (DM Evernight ↔ owner)
owner_discord_id: 726302130318868500
bot_llm: minimax-m3:cloud (LM Studio/Ollama)  |  embedding: qwen3-embedding:0.6b (Ollama)
trace_log_host: data/embedding_trace.jsonl (giờ ĐÃ mount ra host — tail được trực tiếp)
screenshots_dir: tests/e2e/screenshots/2026-07-02-embedding-recall/
report: tests/e2e/REPORT.md (append section mới, KHÔNG overwrite)
scope_note: "Con 9 (Evernight) BỎ QUA phần T2 recall (per owner: 'chắc k có t2'). Evernight chỉ check voice nhẹ."
---

# E2E Test Plan — Embedding qwen3 + consolidation fix + persona-free summarizer

## 0. Mục tiêu

Verify chuỗi fix hôm nay đã: (a) cho consolidation chạy được (trước timeout 300s → nay ~4-6s),
(b) nạp T2 bằng summary THẬT, (c) recall của qwen3 kéo đúng summary liên quan và gate 0.45 chặn rác,
(d) không regression giọng Bé Bảy, không leak `[context cũ]`.

| # | Thay đổi | Kỳ vọng verify |
|---|---|---|
| **C1** | Embedding qwen3-embedding:0.6b, dim 1024, gate `T2_MIN_COSINE=0.45` | Recall kéo summary liên quan (cosine≥0.45); summary lệch chủ đề bị LỌC — KHÔNG nhét vào reply |
| **C2** | Consolidation reasoning=low + max_tokens=4000 + `include_persona=False` | Consolidation chạy tới `status=ok` (KHÔNG timeout), T2 có summary mới; system prompt summarizer RỖNG persona |
| **C3** | Không regression | Bé Bảy giọng "tui"+`:v/:3`, no markdown, KHÔNG nhắc "host tool" vô cớ, KHÔNG leak `[context cũ]` |

**Tiền đề đã verify in-container** (chỉ cần re-confirm, không phải test lại): store T2 sạch (0 key), index dim=1024,
gate lọc đúng (store 2→search 1), consolidation call 3.9s ra JSON đúng, system prompt persona-free = 0 ký tự.

## 0.1. Tester = Sonnet — verify bằng DOM text + host, KHÔNG chỉ nhìn ảnh

- Trích reply bằng `evaluate_script`:
  ```js
  () => Array.from(document.querySelectorAll('[id^=message-content]')).map(e => e.innerText)
  ```
- `take_screenshot(filePath=...)` mỗi phase 1 tấm lưu evidence.
- **Điểm mạnh của round này: trace log giờ ở host** → `tail -n 20 data/embedding_trace.jsonl` đọc trực tiếp
  cosine + matched_text của từng SEARCH, KHÔNG cần đoán.

## 0.2. Gotcha gửi tin Discord (chrome-devtools — ĐÃ verify, BẮT BUỘC)

`fill`+Enter và `type_text`+Enter FAIL khi Slate editor stale. Cách gửi ổn định:
1. `navigate_page` reload URL kênh/DM → `wait_for` text có sẵn
2. `take_snapshot` → tìm uid textbox ("Nhắn #..." / "Message ...")
3. `click` textbox → `press_key "Control+a"` → `press_key "Backspace"`
4. `type_text` + `submitKey: "Enter"`
5. Chờ reply: poll `evaluate_script` message-content mới nhất (bot minimax mất ~3-15s)

## 1. Setup / confirm tiền đề (host, trước khi drive UI)

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'march7|evernight'   # cả 2 healthy
docker exec march7-redis redis-cli --scan --pattern 'timeline:summary:*' | wc -l   # kỳ vọng 0 (sạch)
docker exec march7-redis redis-cli FT.INFO timeline_summaries | grep -A1 -i '^dim' | tail -1  # 1024
tail -n 3 data/embedding_trace.jsonl 2>/dev/null   # model qwen3-embedding:0.6b, dim 1024
```
Discord web: profile Chrome đã login. Nếu bị đá ra login → STOP, báo owner (KHÔNG tự đăng nhập).

## 2. Test cases

### T1 — Seed T2 bằng consolidation THẬT (C2) — enabling step, BẮT BUỘC trước T2/T3

Gửi cho Bé Bảy (kênh test) **4-6 tin nhắn nhiều topic khác biệt** để đẩy T1 > 2000 token → auto-consolidate.
Đề xuất nội dung (mỗi tin cách ~10s, chờ reply):
1. `Bảy ơi tui tên Hòa, tui mê ăn phở với bún chả lắm`
2. `tui đang làm một dự án web bằng React với TypeScript, hơi khó`
3. `tui mới nhận nuôi một con mèo tên Mun, nó đen thui à`
4. `cuối tuần tui hay đi leo núi ở Bà Đen cho khỏe`
5. (nếu chưa trigger) `Bảy ơi kể tui nghe gì đó vui đi, tui buồn ngủ quá`

**Verify (host)** — consolidation chạy được, KHÔNG timeout:
```bash
docker logs evernight --since 3m 2>&1 | grep -iE 'Consolidat|status=|timeout|Error'
# kỳ vọng: "Consolidation completed ... status=ok, messages=N" (KHÔNG "status=failed"/timeout)
docker exec march7-redis redis-cli --scan --pattern 'timeline:summary:*' | wc -l   # kỳ vọng > 0
tail -n 15 data/embedding_trace.jsonl | grep -i passage   # EMBED passage summary (nếu prefix rỗng: input là summary thô)
```
**PASS khi**: có `status=ok` + T2 keys > 0. **FAIL khi**: `status=failed`/timeout, hoặc T2 vẫn 0 sau khi T1 vượt ngưỡng.
> Nếu T1 chưa đủ 2000 token sau 5 tin → gửi thêm 2-3 tin dài. Ghi rõ mất bao nhiêu tin mới trigger.

### T2 — Recall HIT: qwen3 kéo đúng summary liên quan (C1) — n=2

Sau khi T2 có summary, mở turn MỚI hỏi trúng 1 topic đã seed:
- Prompt A: `Bảy ơi cuối tuần này tui nên nấu món gì ngon?`  → kỳ vọng recall summary **ẩm thực (phở/bún chả)**
- Prompt B: `Bảy ơi tui đang debug cái project hoài không xong`  → kỳ vọng recall summary **React/TypeScript**

**Verify (host, quan trọng nhất)** — trace log SEARCH cho query đó:
```bash
tail -n 20 data/embedding_trace.jsonl | python3 -c '
import sys,json
for l in sys.stdin:
  d=json.loads(l)
  if d.get("event_type")=="SEARCH":
    print(round(d.get("cosine_similarity") or 0,3), "|", (d.get("query_text") or "")[:30], "->", (d.get("matched_text") or "")[:45])'
```
**PASS khi**: summary được kéo là **đúng topic** hỏi (cosine ≥ 0.45), và reply của Bảy có nhắc tự nhiên tới ký ức đó
(vd gợi ý phở/bún chả; hoặc an ủi chuyện code React). **FAIL khi**: kéo summary lệch topic, hoặc cosine < 0.45 mà vẫn nhét.

### T3 — Gate chặn rác: hỏi lệch hết mọi topic (C1) — n=1

Prompt: `Bảy ơi thời tiết hôm nay thế nào?` (không liên quan food/code/mèo/leo núi).
**Verify**: trace SEARCH cho query này → mọi summary có cosine < 0.45 → bị **LỌC** (search trả rỗng / không summary nào vào prompt).
**PASS khi**: reply KHÔNG chèn bừa summary food/code/mèo; KHÔNG nhắc "host tool"; sạch chủ đề.

### T4 — Voice + leak regression (C3) — gộp quan sát từ T1-T3

Trên toàn bộ reply Bé Bảy T1-T3, verify:
- Xưng **"tui"**, icon `:v`/`:3`/`=)))`, **KHÔNG** markdown (`**`,`#`,`|`,```` ``` ````), **KHÔNG** emoji đồ hoạ.
- **KHÔNG** xuất hiện marker `[context cũ ...]` trong bất kỳ reply nào (bug pre-existing `manager.py:399-402` — nếu thấy, ghi nhận nhưng KHÔNG tính vào C1/C2/C3).
- **KHÔNG** nhắc "host tool"/"system_gateway" vô cớ (dấu hiệu rác embedding cũ — nếu sạch = xác nhận fix).

### T5 — Evernight voice nhẹ (DM) — n=1, BỎ QUA T2 recall (per owner)

Prompt DM Evernight: `Dạ ơi, đêm nay ta thấy trống trải`.
**PASS khi**: Evernight xưng **"ta"**, giọng điềm tĩnh/tối, no markdown. **KHÔNG test T2 recall của Evernight** (owner: "9 chắc k có t2").

## 3. Teardown

- T2 seed từ T1 là dữ liệu THẬT (không phải rác) → **giữ lại** cũng được (giúp verify recall lần sau).
  Nếu muốn về sạch: `docker exec march7-redis redis-cli FT.DROPINDEX timeline_summaries DD` rồi
  `docker restart march7 evernight` (index tạo lại rỗng dim 1024).
- KHÔNG sửa persona/code trong lúc test. Không có file nào bị mutate (test chỉ chat).

## 4. Deliverable

Append section mới vào `tests/e2e/REPORT.md`:
- Tiêu đề: `## Embedding qwen3 + consolidation fix (2026-07-02, commit cda3330 + include_persona WIP)`
- Bảng TL;DR: T1(consolidation ok?) / T2(recall hit x/2) / T3(gate chặn rác) / T4(voice+leak) / T5(Evernight voice).
- **Bằng chứng trace host**: dán vài dòng SEARCH (cosine + query→matched) chứng minh recall đúng + gate lọc.
- So sánh với round e5-small trước (mọi query cosine 0.85-0.92, kéo cùng rác host_system) — chứng minh qwen3 phân biệt được.
- Consolidation timing thật (log evernight) vs 300s timeout cũ.
- Screenshot mỗi phase.

## 5. Pass/Fail tổng

- **PASS**: T1 consolidation `status=ok` ✅ AND T2 recall ≥1/2 đúng topic ✅ AND T3 gate chặn rác ✅ AND T4 voice sạch + no leak ✅.
- **FAIL (regression/chưa fix)**: consolidation vẫn timeout/failed; HOẶC recall kéo rác lệch topic; HOẶC gate không chặn (cosine<0.45 vẫn nhét); HOẶC Bé Bảy lại nhắc "host tool" vô cớ / leak `[context cũ]`.
- **Điểm mấu chốt**: T2 recall kéo ĐÚNG topic + T3 gate chặn sạch = xác nhận qwen3+gate đã thay thế được recall rác của e5-small.
