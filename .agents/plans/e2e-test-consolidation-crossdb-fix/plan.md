---
status: ready-for-handoff
created: 2026-07-03
owner: e2e-tester (Sonnet, browser-driven via chrome-devtools MCP)
style: browser-driven E2E via chrome-devtools MCP — drive real Discord web UI,
  type messages, observe bot replies, verify T1/T2/trace trên host. NOT a pytest suite.
change_under_test:
  - commit ebfa219 "feat: Enhance consolidation process for shipped entries" (Cách B:
    ConsolidationClient + consolidate_scope ship T1 entries qua A2A; evernight
    a2a_server + consolidate_via_tool nhận `entries`; trim T1 theo `entry_ids`
    trả về thay vì count — skip trim nếu không có entry_ids; `_preflight_context`
    search cả user_id + channel_id; TimelineSummaryStore validate embedding dim;
    bỏ dead code consolidate_payload)
  - kèm memory-layer-audit fixes #1-#9 (trigger storm guard, atomic token counter,
    BM25 gate sau fusion, channel profile pollution, dim-mismatch raise, recall warning)
baseline: round 2026-07-02 "Embedding qwen3 + consolidation fix" trong tests/e2e/REPORT.md
  — T1 FAIL (`status=skipped, messages=0` do cross-DB), T2/T3 unverifiable, C3/T5 PASS.
test_channel: 1487427038280421456 (🤖｜bé-bảy) trong server 1067690340359880724
evernight_dm: 1503774194440212571 (DM Evernight ↔ owner)
owner_discord_id: 726302130318868500
bot_llm: minimax-m3:cloud  |  embedding: qwen3-embedding:0.6b (Ollama)
trace_log_host: data/embedding_trace.jsonl (mounted ra host — tail trực tiếp)
screenshots_dir: tests/e2e/screenshots/2026-07-03-consolidation-crossdb-fix/
report: tests/e2e/REPORT.md (append section mới, KHÔNG overwrite)
headline: "Lần đầu tiên verify consolidation channel CHẠY THẬT qua Discord —
  ship entries fix cross-DB bug, T2 nhận summary, recall qwen3 + gate 0.45 hoạt động end-to-end."
---

# E2E Test Plan — Consolidation cross-DB fix (Cách B: ship entries)

## 0. Mục tiêu

Round trước (2026-07-02) FAIL vì march7 ghi T1 channel vào Redis DB0, evernight
đọc T1 từ DB1 → `status=skipped, messages=0` mãi mãi → T2 rỗng → recall không có
gì để kéo. Commit `ebfa219` fix bằng Cách B: **march7 tự đọc T1 của mình và ship
entries qua A2A**, evernight consolidate thẳng entries shipped (không đọc T1 của
nó nữa), trả về `entry_ids` đã summarize → march7 trim đúng entries đó (không
xóa oan). Fix kèm: recall giờ search cả `user_id` + `channel_id` → channel
summaries ĐƯỢC recall; gate 0.45 áp sau fusion (BM25 không bypass được).

| # | Thay đổi (commit ebfa219) | Kỳ vọng verify qua Discord |
|---|---|---|
| **C1** | Ship T1 entries qua A2A (consolidation_client + consolidate_scope) | Auto-consolidation kênh đạt `status=ok` (KHÔNG còn `skipped, messages=0`); evernight log `entries=N>0` |
| **C2** | Trim T1 theo `entry_ids` trả về (không trim-by-count) | T1 bị trim ĐÚNG số entry đã summarize; KHÔNG xóa oan entry mới đến giữa lúc consolidate; counter reset về 0 sau trim |
| **C3** | Recall dual-scope: search cả user_id + channel_id | Hỏi trúng topic đã seed ở kênh → recall kéo được channel summary (trước đây không bao giờ) |
| **C4** | Gate `T2_MIN_COSINE=0.45` áp sau fusion + recall warning | Hỏi lệch topic → cosine <0.45 → LỌC, không nhét rác vào reply |
| **C5** | Voice + leak regression (không đổi code giọng) | Bé Bảy "tui"+icon, no markdown, KHÔNG leak `[context cũ ...]` |

**Tiền đề đã confirm in-container** (chỉ re-confirm, không test lại): 331 unit
passed; containers restart sau commit, `Up healthy`. KHÔNG cần re-build.

## 0.1. Tester = Sonnet — verify bằng DOM text + host trace, KHÔNG chỉ nhìn ảnh

- Trích reply bằng `evaluate_script`:
  ```js
  () => Array.from(document.querySelectorAll('[id^=message-content]')).map(e => e.innerText)
  ```
- `take_screenshot(filePath=...)` mỗi phase 1 tấm lưu evidence.
- **Vũ khí chính round này: trace log ở host** → `tail -n 30 data/embedding_trace.jsonl`
  đọc trực tiếp `event_type`, `cosine_similarity`, `query_text`, `matched_text`,
  `scope_ids`, `sources` của từng SEARCH — không đoán. Đây là khác biệt sống còn
  vs round trước (toàn EMBED, 0 dòng SEARCH vì T2 rỗng).

## 0.2. Gotcha gửi tin Discord (chrome-devtools — ĐÃ verify 2026-07-02, BẮT BUỘC)

`fill`+Enter và `type_text`+Enter FAIL khi Slate editor stale-state. Cách gửi ổn định:
1. `navigate_page` reload URL kênh/DM → `wait_for` text có sẵn trên trang
2. `take_snapshot` → tìm uid textbox ("Nhắn #..." / "Message ...")
3. `click` textbox → `press_key "Control+a"` → `press_key "Backspace"` (xoá stale)
4. `type_text` + `submitKey: "Enter"`
5. Chờ reply: poll `evaluate_script` message-content mới nhất (bot minimax ~3-15s, poll tối đa ~40s/tin)
6. Verify bằng text đã trích (KHÔNG chỉ nhìn ảnh)

## 1. Setup / confirm tiền đề (host, trước khi drive UI)

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'march7|evernight'   # cả 2 healthy
git -C /home/flowerf/Projects/march7 log --oneline -1   # kỳ vọng ebfa219 ở HEAD (hoặc newer)
# T2 sạch trước test (để chứng minh summary mới là do round này sinh ra):
docker exec march7-redis redis-cli FT.DROPINDEX timeline_summaries DD 2>/dev/null
docker exec march7-redis redis-cli FT.CREATE timeline_summaries ...   # KHÔNG — chỉ DROP rồi restart
docker restart march7 evernight   # index tự tạo lại rỗng dim 1024
sleep 8
docker exec march7-redis redis-cli --scan --pattern 'timeline:summary:*' | wc -l   # kỳ vọng 0
docker exec march7-redis redis-cli FT.INFO timeline_summaries 2>/dev/null | grep -i attr   # dim 1024
tail -n 3 data/embedding_trace.jsonl 2>/dev/null   # model qwen3-embedding:0.6b, dim 1024
```
Discord web: profile Chrome đã login. Navigate tới kênh test
`https://discord.com/channels/1067690340359880724/1487427038280421456`.
Nếu bị đá ra login → STOP, báo owner (KHÔNG tự đăng nhập).

> **Lưu ý DROPINDEX**: chỉ làm nếu owner OK xóa T2 cũ. Nếu owner muốn giữ T2 cũ,
> bỏ bước DROP, nhưng ghi rõ baseline `timeline:summary:*` count trước T1 để
> tính delta sau consolidation. **Hỏi owner trước khi DROP** nếu chưa có sẵn T2.

## 2. Test cases

### T1 — Channel consolidation CHẠY THẬT (C1 + C2) ★ HEADLINE — BẮT BUỘC trước T2/T3

Gửi cho Bé Bảy (kênh test) **5-7 tin nhắn nhiều topic khác biệt**, mỗi tin cách
~10-15s, chờ reply, để đẩy `unsummarized_tokens` > 2000 → auto-consolidate.
Đề xuất nội dung (topic tách bạch để T2/T3 dễ verify recall):
1. `Bảy ơi tui tên Hòa, tui mê ăn phở với bún chả lắm`
2. `tui đang làm một dự án web bằng React với TypeScript, hơi khó`
3. `tui mới nhận nuôi một con mèo tên Mun, nó đen thui à`
4. `cuối tuần tui hay đi leo núi ở Bà Đen cho khỏe`
5. `Bảy ơi kể tui nghe gì đó vui đi` (nếu chưa trigger, gửi thêm 1-2 tin dài)

**Verify (host) — quan trọng nhất, đây là điểm FAIL của round trước:**
```bash
# (a) Evernight nhận entries shipped (KHÔNG còn "entries=0"):
docker logs evernight --since 5m 2>&1 | grep -iE 'Consolidat|entries=|status=' | tail -20
# kỳ vọng: "handling consolidate_discussion ... entries=N" với N>0, rồi "status=ok"
#           (KHÔNG "status=skipped, messages=0" như round trước)

# (b) March7 ship entries + trim đúng:
docker logs march7 --since 5m 2>&1 | grep -iE 'Consolidating via A2A|entries=|Trimmed T1|skipping trim' | tail -20
# kỳ vọng: "Consolidating via A2A client scope=channel/... entries=N>0"
#           + "Trimmed T1 after consolidation: M entries" (M <= N, = số entry_ids trả về)
#           KHÔNG "skipping trim ... no_entry_ids" (nếu thấy = consolidator không trả entry_ids = bug C2)

# (c) T2 giờ CÓ summary (điểm FAIL tuyệt đối của round trước):
docker exec march7-redis redis-cli --scan --pattern 'timeline:summary:*' | wc -l   # kỳ vọng > 0

# (d) T1 bị trim đúng — counter reset, không xóa oan entry mới:
docker exec march7-redis redis-cli -n 0 HGET "active_state:channel:1487427038280421456" unsummarized_tokens
# kỳ vọng: số THẤP (gần 0 hoặc = token của vài tin sau khi consolidate đã trim), KHÔNG còn 2800 như round trước
docker exec march7-redis redis-cli -n 0 ZCARD "active_index:channel:1487427038280421456"
# kỳ vọng: < số tin tổng đã gửi (đã trim phần đã summarize); ghi lại con số để chứng minh trim thật
```
**PASS khi**: (a) `status=ok` + `entries=N>0` ✅ AND (c) T2 keys > 0 ✅ AND (d)
counter giảm/số entry giảm (trim thật) ✅.
**FAIL khi**: vẫn `status=skipped, messages=0` (Cách B chưa wire) HOẶC `entries=0`
(march7 không ship) HOẶC T2 vẫn 0 sau khi T1 vượt ngưỡng HOẶC `no_entry_ids` (trim bỏ qua = C2 chưa fix).
> Ghi rõ: mất bao nhiêu tin mới trigger, latency consolidation thật (từ log evernight
> `handling` → `status=ok`), so với "3-5ms skip" của round trước.

### T2 — Recall HIT: dual-scope kéo đúng channel summary (C3) — n=2

Sau khi T2 có summary (T1 PASS), mở turn MỚI hỏi trúng topic đã seed:
- **Prompt A**: `Bảy ơi cuối tuần này tui nên nấu món gì ngon?` → kỳ vọng recall
  summary **ẩm thực (phở/bún chả)** — đây là CHANNEL scope (đã seed ở kênh),
  trước đây KHÔNG bao giờ recall được vì T2 lưu user_id=channel mà search theo
  user_id người nói. Đây là verify trực tiếp fix C3.
- **Prompt B**: `Bảy ơi tui đang debug cái project hoài không xong` → kỳ vọng
  recall summary **React/TypeScript**.

**Verify (host, quan trọng nhất) — trace SEARCH giờ PHẢI có dòng:**
```bash
tail -n 40 data/embedding_trace.jsonl | python3 -c '
import sys,json
for l in sys.stdin:
  try: d=json.loads(l)
  except: continue
  if d.get("event_type")=="SEARCH":
    print(round(d.get("cosine_similarity") or 0,3),
          "| query:", (d.get("query_text") or "")[:35],
          "-> matched:", (d.get("matched_text") or "")[:50],
          "| scope_ids:", d.get("scope_ids"), "source:", d.get("sources"))'
```
**PASS khi**: (1) có dòng SEARCH thật (round trước 0 dòng — đây là khác biệt sống còn);
(2) summary kéo là **đúng topic** hỏi (cosine ≥ 0.45); (3) `scope_ids` chứa
channel_id `1487427038280421456` (chứng minh dual-scope chạy) ; (4) reply Bé Bảy
nhắc tự nhiên tới ký ức đó (gợi ý phở/bún chả; hoặc an ủi chuyện code React).
**FAIL khi**: kéo summary lệch topic, HOẶC cosine < 0.45 mà vẫn nhét, HOẶC không
có dòng SEARCH nào (T2 vẫn rỗng = T1 fail âm thầm), HOẶC scope_ids chỉ có user_id
(C3 dual-scope chưa wire).

### T3 — Gate chặn rác sau fusion (C4) — n=1

Prompt: `Bảy ơi thời tiết hôm nay thế nào?` (không liên quan food/code/mèo/leo núi).
**Verify**: trace SEARCH cho query này → mọi summary cosine < 0.45 → **LỌC**
(search trả rỗng / `merged` rỗng / không summary vào prompt). Kiểm cả BM25 path:
nếu có kết quả BM25 trùng từ "hôm nay" nhưng cosine thấp → phải bị gate loại sau
fusion (fix audit #6).
**PASS khi**: reply KHÔNG chèn bừa summary food/code/mèo; KHÔNG nhắc "host tool";
sạch chủ đề. Trace xác nhận kết quả低 cosine bị filter.

### T4 — Voice + leak regression (C5) — gộp quan sát T1-T3

Trên toàn bộ reply Bé Bảy T1-T3, verify:
- Xưng **"tui"**, icon `:v`/`:3`/`=)))`/`^^`, **KHÔNG** markdown (`**`,`#`,`|`,```` ``` ````), **KHÔNG** emoji đồ hoạ.
- **KHÔNG** xuất hiện marker `[context cũ ...]` trong bất kỳ reply nào (bug pre-existing
  `manager.py:399-402` — nếu thấy, ghi nhận nhưng KHÔNG tính vào C1-C4; đây là bug
  leak chưa fix, nằm ngoài scope commit ebfa219).
- **KHÔNG** nhắc "host tool"/"system_gateway"/"hồ sơ T3" vô cớ (dấu hiệu rác embedding
  cũ — round trước ghi nhận 2 lần bot tự nhắc "hồ sơ T3"; nếu sạch = fix tốt hơn).

### T5 — Evernight voice (DM) — n=1, BỎ QUA T2 recall (per owner: "9 chắc k có t2")

Prompt DM Evernight: `Dạ ơi, đêm nay ta thấy trống trải`.
**PASS khi**: Evernight xưng **"ta"**, giọng điềm tĩnh/tối, no markdown. **KHÔNG test T2 recall của Evernight.**

## 3. Teardown

- T2 seed từ T1 là dữ liệu THẬT → **giữ lại** cũng được (giúp verify recall lần sau).
  Nếu muốn về sạch: `docker exec march7-redis redis-cli FT.DROPINDEX timeline_summaries DD`
  rồi `docker restart march7 evernight`.
- KHÔNG sửa code/persona trong lúc test. Không file nào bị mutate ngoài ý muốn
  (test chỉ chat). Nếu bot tự gọi `update_personality` và ghi file → restore từ
  git: `git -C /home/flowerf/Projects/march7 checkout -- twin/*/personas/`.

## 4. Deliverable

Append section mới vào `tests/e2e/REPORT.md` (KHÔNG overwrite):
- Tiêu đề: `## Consolidation cross-DB fix — ship entries (2026-07-03, commit ebfa219)`
- Bảng TL;DR: T1(consolidation ok? entries shipped? T2>0? trim?) / T2(recall hit x/2 + scope_ids) / T3(gate) / T4(voice+leak) / T5(Evernight).
- **Bằng chứng trace host**: dán vài dòng SEARCH (cosine + query→matched + scope_ids + source) — đây là điểm mà round trước HOÀN TOÀN KHÔNG CÓ (0 dòng SEARCH). Đây là bằng chứng sống còn của round.
- Log evernight `entries=N>0` + `status=ok` (vs `entries=0, status=skipped` round trước).
- Log march7 `Trimmed T1: M entries` + counter HGET trước/sau (chứng minh trim-by-entry_ids, không xóa oan).
- So sánh trực tiếp vs round 2026-07-02 cùng section: trước `status=skipped, messages=0`, T2=0, 0 SEARCH; sau `status=ok`, T2>0, có SEARCH đúng topic.
- Consolidation timing thật (latency `handling`→`status=ok`) vs skip 3-5ms round trước.
- Screenshot mỗi phase (T1-seed, T2-recall, T3-gate, T5-evernight).

## 5. Pass/Fail tổng

- **PASS**: T1 `status=ok` + entries shipped >0 + T2 keys >0 + trim thật ✅
  AND T2 recall ≥1/2 đúng topic + có dòng SEARCH + scope_ids chứa channel ✅
  AND T3 gate chặn rác ✅ AND T4 voice sạch + no leak ✅.
- **FAIL (fix chưa lên / regression)**: consolidation vẫn `skipped/entries=0`;
  HOẶC T2 vẫn 0; HOẶC recall kéo rác lệch topic / cosine<0.45 vẫn nhét;
  HOẶC scope_ids không có channel (C3 chưa wire); HOẶC `no_entry_ids` (trim bỏ qua = C2 hỏng);
  HOẶC T1 bị xóa oan entry chưa summarize (data loss).
- **Điểm mấu chốt**: round này khác round trước ở chỗ **phải có dòng SEARCH thật
  trong trace + T2 keys > 0**. Nếu hai điều kiện đó thoả — bug cross-DB đã fix thật.
  T2 kéo đúng topic + T3 gate sạch = xác nhận Cách B + dual-scope recall + gate
  đã thay thế được skip-vĩnh-viễn của round trước.