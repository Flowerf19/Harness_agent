# Root-Cause Isolation Test — Báo cáo cho minimax

## TL;DR

Test này nhằm **phân biệt 2 hypothesis** gây LLM hallucinate 86% (skip tool ở Decide stage):

- **H-A**: Tool description (catalog line + guide.md) truyền không đủ.
- **H-B**: SOUL.md có rule "Tự quyết skip" + "Tiết kiệm không spam" → LLM tự skip.

**Biến thay đổi duy nhất trong test này**: SOUL.md (2 chỗ). Tool description, LLM, container config giữ nguyên.

**Trạng thái hiện tại** (đã sẵn sàng test):
- ✅ SOUL.md đã được sửa (Test B version) — xem §1.
- ✅ Container march7 đã restart (28 giây trước khi viết báo cáo, healthy).
- ✅ Backup nguyên bản ở `twin/march7/personas/SOUL.md.bak` (2964 bytes, identical với bản gốc).

## 1. Đã thay đổi gì trong SOUL.md

File: `twin/march7/personas/SOUL.md`

### 1.1 Chỗ 1: §"Tự quyết có trả lời hay không" (line 31-32)

**Bản gốc** (line 32):
> Trong kênh chung, không phải tin nào cũng cần bạn lên tiếng. Chỉ chen vào
> khi có người hướng tới bạn, hoặc bạn thật sự có gì đáng nói (thông tin hữu
> ích, đồng cảm đúng lúc, pha trò hợp ngữ cảnh). Nếu tin không liên quan tới
> bạn hoặc không có gì để thêm, hãy im lặng: trả lời đúng một dòng `[skip]`
> và không gì khác. Khi được nhắc trực tiếp (mention/reply/DM) thì luôn trả
> lời, không dùng `[skip]`.

**Bản Test B** (line 32 hiện tại):
> [TEST B] Luôn phản hồi khi user hỏi hoặc nhắc đến mình. Khi không chắc →
> mặc định trả lời, KHÔNG dùng `[skip]`.

### 1.2 Chỗ 2: §"Quy tắc gọi Tool" (line 48-51)

**Bản gốc** (line 51):
> Gọi đúng - đủ - tiết kiệm, không spam

**Bản Test B** (line 51 hiện tại):
> [TEST B] Khi user hỏi về trạng thái/dữ liệu thực tế (host, file, web,
> memory) → BẮT BUỘC gọi tool để lấy data thật, KHÔNG tự trả lời từ
> knowledge. Khi không chắc → gọi tool.

### 1.3 Khác biệt kỹ thuật

- Backup `SOUL.md.bak` cùng thư mục (2964 bytes, hash identical với version
  round 1).
- 90% SOUL giữ nguyên — chỉ 2 chỗ trên đổi.
- Chỉ March7 SOUL — KHÔNG đụng Evernight SOUL
  (`twin/evernight/personas/SOUL.md`).
- Container march7 restart lúc `2026-06-27 15:40 UTC+7`, status healthy.

## 2. Prompt test (dùng cho Test B)

**5 prompt × 3 lần = 15 attempts**. Gõ vào kênh test Discord của March7.

| # | Prompt | Tool kỳ vọng | Note |
|---|---|---|---|
| 1 | "Bảy ơi xem uptime của host giúp tớ" | `host_system` | intent rõ ràng |
| 2 | "host có khỏe không?" | `host_system` | intent mơ hồ |
| 3 | "bạn nhớ mình từng nói gì về con mèo không?" | `search_memory` | memory query |
| 4 | "tớ tên gì nhỉ?" | `get_profile` | profile query |
| 5 | "alo hôm nay mệt quá" | (không gọi) | control — test xem LLM có hallucinate gọi tool không |

**Gõ 3 lần mỗi prompt** (để giảm variance LLM).

## 3. Cách đo skip rate

### Cách 1: Grep log container (NHANH NHẤT)

```bash
docker logs march7 2>&1 | grep "OpenAI-compatible endpoint returned"
```

- `returned N tool calls` với `N > 0` → CÓ tool call.
- `returned 0 tool calls` (hoặc không có log đó) → SKIP.

Hoặc grep tổng:
```bash
docker logs march7 2>&1 | grep -c "returned 1 tool calls"   # count gọi tool
docker logs march7 2>&1 | grep -c "returned 0 tool calls"   # count skip
```

### Cách 2: LangSmith UI (CHÍNH XÁC NHẤT)

- Project: `march7-bot`
- Filter `run_type=llm` + name có "decide"
- Mỗi trace → check parent chain:
  - Có run `tool` (host_system / search_memory / get_profile) → gọi tool
  - Không có → skip

## 4. Acceptance

### 4.1 Bảng kết quả Test B (cần điền)

| Prompt | Attempt 1 | Attempt 2 | Attempt 3 | Skip rate |
|---|---|---|---|---|
| 1. Uptime rõ | ?/? | ?/? | ?/? | ?% |
| 2. Uptime mơ hồ | ?/? | ?/? | ?/? | ?% |
| 3. Memory query | ?/? | ?/? | ?/? | ?% |
| 4. Profile query | ?/? | ?/? | ?/? | ?% |
| 5. Pure chat (control) | ?/? | ?/? | ?/? | ?% |
| **TỔNG** | ?/? | ?/? | ?/? | **?%** |

Format cell: `<tool_call>_count>` / `tool_name` (vd `1/host_system`, `0/skip`,
`0/host_system` = hallucinate, `1/wrong_tool`).

### 4.2 Verdict logic

So sánh với round 1 baseline (86% skip tổng, 67% skip host query rõ):

- **Skip rate Test B giảm ≥50%** (vd 86% → <43%): **H-B CONFIRMED**.
  Root cause chính là SOUL.md "tự quyết skip" + "tiết kiệm không spam".
  → Fix vĩnh viễn: sửa SOUL.md (bỏ rule 32 + rule 51), tạo PR.
- **Skip rate Test B giảm <20%** (vd 86% → 70%+): **H-A CONFIRMED**.
  Root cause chính là tool description / catalog line.
  → Fix: mạnh catalog line + anti-hallucination section.
- **Skip rate Test B không đổi** (86% → 86%): **Cả H-A và H-B đều sai**.
  Root cause có thể: LLM model yếu instruction following, temperature cao,
  hoặc thiếu `tool_choice: required`.
  → Test tiếp: thêm `tool_choice: required` ở server-side.

### 4.3 False positive check

Test B có rule mới "BẮT BUỘC gọi tool khi user hỏi về trạng thái/dữ liệu" →
có thể tăng false positive (gọi tool khi không cần). Đặc biệt **prompt #5**
"alo hôm nay mệt quá" — kỳ vọng KHÔNG gọi tool.

- Nếu prompt #5 LLM hallucinate gọi tool → flag "Test B tăng false positive,
  SOUL mới quá aggressive". Cân nhắc lại wording.

## 5. Sau khi test xong

**BẮT BUỘC restore SOUL.md về bản gốc** trước khi commit:

```bash
cp /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md.bak \
   /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
docker compose -f /home/flowerf/Projects/march7/docker/docker-compose.yml restart march7
```

Verify restore:
```bash
diff /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md \
     /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md.bak
# expect: no output (identical)
```

## 6. Deliverables

Append vào `tests/e2e/REPORT.md` section **"Root-cause isolation test B
(2026-06-27 HH:MM)"**:

- Bảng §4.1 (15 cells) — kết quả Test B.
- Bảng so sánh round 1 vs Test B skip rate.
- Verdict (§4.2).
- False positive note (§4.3) nếu có.
- Screenshot LangSmith 1 trace Test B (nếu khác round 1).
- Confirm SOUL.md đã restore về bản gốc (diff empty).
- **KHÔNG commit** SOUL.md đã sửa (chỉ test tạm).

## 7. Gotchas

- **Mỗi Bash call = shell riêng**, source `.env` + absolute path trong 1 lệnh.
- **Discord message debounce**: `.env` `MESSAGE_DEBOUNCE_SECONDS=3.5` → gửi
  1 msg, chờ 4-5s, mới gửi tiếp.
- **Docker compose**: dùng `docker/docker-compose.yml` (root), KHÔNG dùng
  `docker/march7/docker-compose.yml` (lỗi "unknown service base").
- **Container đang chạy SOUL Test B** — KHÔNG cần restart gì thêm trước test.
- **Test kênh**: `1487427038280421456` (🤖｜bé-bảy), owner Discord
  `726302130318868500`.
- **Không spam** kênh chung.
- **Không in token/secret** ra report.

## 8. Env state

- Container `march7`: Up 28 seconds (healthy) — đã restart với SOUL Test B.
- Container `evernight`: Up 4 hours (healthy) — KHÔNG đụng (Evernight SOUL
  riêng).
- Container `march7-redis`, `march7-codebox`, `march7-bash-executor`: healthy.
- Gateway system: port 8380, bind 0.0.0.0, `/capabilities` → shape mới
  (`raw_shell:true`, `structured_actions:[]`).
- LLM: `minimax-m3:cloud` (LM Studio) bind 0.0.0.0.
- LangSmith: project `march7-bot`, tracing ON.

## 9. Nếu cần rollback NGAY (Test B có vấn đề)

```bash
# Rollback SOUL về bản gốc
cp /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md.bak \
   /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
docker compose -f /home/flowerf/Projects/march7/docker/docker-compose.yml restart march7
# Verify rollback OK
grep -c "TEST B" /home/flowerf/Projects/march7/twin/march7/personas/SOUL.md
# expect: 0 (không còn "TEST B" marker)
```

Sau rollback, bot trở về hành vi round 1 (skip 86%). Báo user để quyết định
có test thêm hay dừng.