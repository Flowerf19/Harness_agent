# Root-Cause Isolation Test — SOUL.md vs tool description

## 0. Mục tiêu

Round 1 E2E cho thấy LLM hallucinate 86% (skip tool hoàn toàn ở Decide stage).
LangSmith confirm: flow chỉ có `Decide → Resolve`, KHÔNG có `Refine`/`Act` →
nghĩa là LLM quyết định "không cần tool" ngay từ đầu.

Có 2 hypothesis:

- **H-A**: `tool description` (catalog line + guide.md) truyền không đủ → LLM
  không hiểu cần gọi tool.
- **H-B**: `SOUL.md` / system prompt có rule gây skip
  ("Tự quyết có trả lời hay không", "Gọi đúng-đủ-tiết kiệm không spam")
  → LLM tự skip để "tiết kiệm".

## 1. Cách test phân biệt

Biến 1 yếu tố (SOUL), giữ yếu tố kia (tool description). So sánh skip rate.

| | Test A (baseline) | Test B (tạm thay SOUL) |
|---|---|---|
| **Tool description** | host_system.md nguyên round 1 | giống Test A |
| **SOUL.md** | nguyên round 1 (line 32 + 51 có rule skip) | **tạm thay** phiên bản "no-skip" |
| **Container** | restart với code mới | restart với code mới |
| **LLM** | `minimax-m3:cloud` | giống Test A |
| **Prompt test** | 3-5 câu identical | giống Test A |

## 2. SOUL.md "no-skip" (dùng cho Test B)

Giữ nguyên 90% SOUL, **chỉ thay 2 chỗ** để vô hiệu hóa rule skip:

### 2.1 Tại line 32 (rule "Tự quyết skip")

**Bản gốc**:
> Trong kênh chung, không phải tin nào cũng cần bạn lên tiếng. Chỉ chen vào
> khi có người hướng tới bạn, hoặc bạn thật sự có gì đáng nói (thông tin hữu
> ích, đồng cảm đúng lúc, pha trò hợp ngữ cảnh). Nếu tin không liên quan tới
> bạn hoặc không có gì để thêm, hãy im lặng: trả lời đúng một dòng `[skip]`
> và không gì khác.

**Bản Test B**:
> ~~Trong kênh chung, không phải tin nào cũng cần bạn lên tiếng. Chỉ chen vào
> khi có người hướng tới bạn, hoặc bạn thật sự có gì đáng nói (thông tin hữu
> ích, đồng cảm đúng lúc, pha trò hợp ngữ cảnh). Nếu tin không liên quan tới
> bạn hoặc không có gì để thêm, hãy im lặng: trả lời đúng một dòng `[skip]`
> và không gì khác.~~ **[TEST B] Luôn phản hồi khi user hỏi hoặc nhắc đến
> mình. Khi không chắc → mặc định trả lời, KHÔNG dùng `[skip]`.**

### 2.2 Tại line 48-52 (rule "Gọi Tool")

**Bản gốc**:
> ## Quy tắc gọi Tool
> - Dùng micro-catalog để chọn tool; khi đã chọn, hệ thống sẽ nạp guide chi tiết của tool đó
> - Kiểm tra Core Memory TRƯỚC khi gọi tool
> - Gọi đúng - đủ - tiết kiệm, không spam

**Bản Test B**:
> ## Quy tắc gọi Tool
> - Dùng micro-catalog để chọn tool; khi đã chọn, hệ thống sẽ nạp guide chi tiết của tool đó
> - Kiểm tra Core Memory TRƯỚC khi gọi tool
> - ~~Gọi đúng - đủ - tiết kiệm, không spam~~ **[TEST B] Khi user hỏi về trạng
>   thái/dữ liệu thực tế (host, file, web, memory) → BẮT BUỘC gọi tool để lấy
>   data thật, KHÔNG tự trả lời từ knowledge. Khi không chắc → gọi tool.**

### 2.3 Cách apply Test B

**Cách 1 — Sửa file + restart container** (5 phút):
```bash
# 1. Backup SOUL gốc
cp /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md \
   /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md.bak

# 2. Edit theo §2.1 + §2.2 (dùng Edit tool, 2 chỗ)
# 3. Restart container
docker compose -f docker/docker-compose.yml restart march7

# 4. Sau test → restore
cp /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md.bak \
   /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
docker compose -f docker/docker-compose.yml restart march7
```

**Cách 2 — Env var override** (nếu code support):
Tôi chưa thấy env var override cho SOUL → Cách 1 là chắc chắn nhất.

## 3. Prompt test (giống nhau cho A và B)

Dùng **5 prompt** đa dạng intent, từ rõ ràng đến mơ hồ:

1. **Host query rõ ràng**: "Bảy ơi xem uptime của host giúp tớ" — rõ ràng cần `host_system`.
2. **Host query mơ hồ**: "host có khỏe không?" — ý đồ tương tự nhưng wording mơ hồ.
3. **Memory query**: "bạn nhớ mình từng nói gì về con mèo không?" — cần `search_memory`.
4. **Profile query**: "tớ tên gì nhỉ?" — cần `get_profile`.
5. **Pure chat (control)**: "alo hôm nay mệt quá" — KHÔNG nên gọi tool, test xem LLM có hallucinate gọi tool không.

Mỗi prompt chạy **3 lần** để giảm variance → tổng 15 attempts/test.

## 4. Cách đo skip rate

Trên Discord UI (chrome-devtools MCP), gõ từng prompt. Sau mỗi reply:
- Snapshot LangSmith trace (filter `project=march7-bot`, `run_type=llm`, name pattern
  chứa "decide" hoặc "refine" hoặc "resolve").
- Đếm: có run `refine` không? Có run `tool` không? Có run `act` không?
- `has_refine = bool(refine run)`; `has_tool = bool(tool run)`.
- Skip = `not has_tool` (LLM không gọi tool).

Hoặc đơn giản hơn: grep log `discord_bot.OpenAIService`:
```
"OpenAI-compatible endpoint returned N tool calls"
```
- N > 0 → CÓ tool call.
- N = 0 → SKIP.

## 5. Acceptance (reviewer check)

| Metric | Test A (baseline) | Test B (no-skip SOUL) | Verdict |
|---|---|---|---|
| Skip rate tổng (15 attempts) | 86% (expected) | ??? | So sánh |
| Skip rate host query rõ (3 attempts) | 67% | ??? | So sánh |
| Skip rate memory query (3) | ??? | ??? | So sánh |
| Skip rate profile query (3) | ??? | ??? | So sánh |
| False positive (gọi tool khi không cần) | 0% | ??? | Test B có thể tăng vì "BẮT BUỘC gọi" |

**Verdict logic**:

- **Nếu Test B skip rate giảm ≥50%** (vd từ 86% → <43%): **H-B CONFIRMED** —
  SOUL.md "tự quyết skip" + "tiết kiệm không spam" là root cause chính.
  → Fix: sửa SOUL.md (bỏ rule 32 + rule 51).
- **Nếu Test B skip rate giảm <20%** (vd 86% → 70%+): **H-A CONFIRMED** —
  Tool description / catalog line là root cause chính.
  → Fix: mạnh catalog line + anti-hallucination section hơn.
- **Nếu Test B skip rate không đổi** (86% → 86%): **CẢ H-A VÀ H-B đều sai**,
  root cause có thể là:
  - LLM model yếu (instruction following kém)
  - Temperature quá cao
  - Thiếu `tool_choice` enforcement
  → Test tiếp: `tool_choice: required`.

## 6. Out-of-scope reminder

- **KHÔNG sửa tool description** trong test này. Biến cố định.
- **KHÔNG đụng vào Evernight SOUL** (`twin/evernight/personas/SOUL.md`) — chỉ
  March7.
- **KHÔNG đụng IDENTITY.md**, **KHÔNG đụng guide.md**.
- Backup SOUL trước khi sửa. Restore sau test.
- Log kết quả vào `tests/e2e/REPORT.md` section "Root-cause isolation".

## 7. Gotchas

- **Mỗi Bash call = shell riêng**, source `.env` + absolute path trong 1 lệnh.
- **Restart container** sau khi sửa SOUL (system prompt cache ở bootstrap).
- **Docker compose**: dùng `docker/docker-compose.yml` (root), KHÔNG dùng
  `docker/march7/docker-compose.yml` (lỗi "unknown service base").
- **SOUL.md cache**: nếu code load SOUL ở startup, restart là đủ. Nếu reload
  mỗi request → không cần restart.
- **Discord message debounce**: `.env` `MESSAGE_DEBOUNCE_SECONDS=3.5` → gửi
  1 msg, chờ 4-5s, mới gửi tiếp.
- **Test A trước, Test B sau**: để cùng state, đỡ variance từ LLM session.

## 8. Deliverables

- `tests/e2e/REPORT.md` — section "Root-cause isolation test (2026-06-27 HH:MM)":
  - Bảng 5 prompt × 3 attempt × 2 test = 30 cells.
  - Bảng skip rate A vs B + verdict.
- Screenshot LangSmith 1 trace Test A (skip) + 1 trace Test B (nếu khác).
- Backup file `SOUL.md.bak` còn nguyên (để restore).
- **KHÔNG commit** SOUL.md đã sửa (chỉ test tạm, restore trước khi commit).