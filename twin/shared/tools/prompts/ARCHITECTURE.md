<tool_description>
Tool kiến trúc + spec cho 11 guide.md khác trong thư mục: đọc file này để hiểu cấu trúc block, schema, catalog entry — KHÔNG tự ý tạo tool mới, hỏi Evernight trước.
</tool_description>

## guide

File **dàn ý ngắn** cho người muốn viết/sửa tool guide trong thư mục
`twin/shared/tools/prompts/guides/`. File này **không phải tool guide** —
không có entry trong `SYSTEM_TOOL_SPECS`, code `ToolPromptCatalog` không
load.

**Muốn hiểu kiến trúc đầy đủ** (3 phần tool, schema đi đâu trong 3 Think
stage, ví dụ end-to-end tạo tool mới, dependency injection) → đọc
`CONTRIBUTING.md` cùng thư mục.

### Cấu trúc bắt buộc của 1 file guide

```markdown
<tool_description>
[1 dòng duy nhất, công thức §"Mẫu description"]
</tool_description>

## <tool_name>

[1-2 câu tóm tắt]

### Khi nên dùng
- [intent cụ thể]

### Khi không nên dùng
- [thay bằng tool X nếu...]

### Quy tắc chống hallucination     [chỉ tool có risk]
- [BẮT BUỘC / CẤM khi...]

### Input                            [chỉ tool >3 params]
- `param`: mô tả. ràng buộc nếu có.
```

**Quy tắc cứng**:

- Block `<tool_description>` **đúng 1 dòng vật lý**, ≤300 ký tự. Không
  wrap, không markdown header bên trong. Code load dùng
  `splitlines()[0]` (`catalog.py:135`) — phần thừa rơi vào full guide,
  LLM đọc trùng.
- Block là **schema description LLM thấy ở mọi request** (qua OpenAI
  function calling) và **catalog line trong system prompt** — phải tự
  đứng được.
- Phần ngoài block (full guide) LLM chỉ thấy ở **Refine**, sau khi đã
  chọn tool — chỗ giải thích chi tiết param, ví dụ, anti-hallucination.
- `## <tool_name>` bắt buộc ngay sau block (cách 1 dòng trống).
- `### Khi nên dùng` + `### Khi không nên dùng` bắt buộc mọi tool.

### Mẫu description (1 dòng, ≤300 ký tự)

```
Tool <phạm vi> qua <cơ chế>: <cách gọi> — BẮT BUỘC <khi nào>, KHÔNG <khi nào>.
```

4 việc LLM cần quyết trong 1 dòng:

1. Phạm vi tool.
2. Cơ chế (gateway / MCP / local / sandbox).
3. Cách gọi điển hình (mode, schema, param quan trọng).
4. Anti-hallucination hint ngắn.

Ví dụ (từ `host_system.md`):

```
Tool MỌI câu hỏi/thao tác sự thật về host (uptime, disk, docker, service, log, đọc/ghi file) qua System Gateway: gọi mode=shell với lệnh OS phù hợp, owner duyệt đúng lệnh đó — BẮT BUỘC gọi tool này cho query host, KHÔNG bịa số liệu host từ trí nhớ.
```

### Khi nào thêm section optional

| Section | Thêm khi |
|---|---|
| `### Quy tắc chống hallucination` | Tool có risk: LLM dễ bịa (host_system), nhớ user (search_memory), destructive (manage_user_profile), thêm info ngoài output (gateway_admin doctor) |
| `### Input` | Tool >3 params hoặc param có ràng buộc đặc biệt (enum, clamp, format) |

### Quyết định trước khi viết (TL;DR — chi tiết ở CONTRIBUTING.md §3)

- **Backend**: `local` (chạy trong process) hay `remote_mcp` (gọi MCP server
  ngoài trust boundary — vd Tavily).
- **visible_to / allowed_to**: `None` = mọi agent, `frozenset({"evernight"})`
  = chỉ Evernight, `frozenset()` = hard-hidden.
- **Approval**: tool chạm host / ghi file / đổi config → inject
  `approval_gate` qua `__init__`, gọi `check_approval(...)` trước execute.

### Anti-pattern

❌ Block `<tool_description>` nhiều dòng — code lấy dòng 0, phần thừa rơi
vào full guide, LLM đọc trùng.
❌ Markdown header bên trong block — schema description vô nghĩa.
❌ Thiếu anti-hallucination hint ở description — LLM dễ chọn nhưng cũng
dễ bịa.
❌ "Khi nên dùng" / "Khi không nên dùng" ý lẫn lộn — LLM không biết cue
nào áp dụng.
❌ Schema description tiếng Anh — không khớp SOUL.md, LLM switch context,
dễ ignore rule.
❌ `MCPClient.list_tools()` để build schema — vi phạm trust boundary.
❌ Tool gọi LLM / Discord UI bên trong `execute()` — tool là pure execution.

### Checklist trước commit

- [ ] Block desc đúng 1 dòng vật lý, ≤300 ký tự, có "BẮT BUỘC" / "KHÔNG".
- [ ] Có `## <tool_name>`, `### Khi nên dùng`, `### Khi không nên dùng`.
- [ ] Có `### Quy tắc chống hallucination` nếu tool có risk (factual /
      memory / destructive).
- [ ] Có `### Input` nếu tool >3 params hoặc param đặc biệt.
- [ ] Mọi param trong guide khớp `parameters_schema` của class.
- [ ] Mọi tool tham chiếu bằng backtick `` `tool_name` ``.
- [ ] Restart container (`docker compose -f docker/docker-compose.yml restart march7`)
      sau commit — schema description cache ở bootstrap. Catalog line
      (system prompt) không cần restart.

### File mẫu

`host_system.md` — đầy đủ 4 section, anti-hallucination mạnh, là chuẩn.
3 file đã theo spec: `host_system.md`, `consolidate_memory.md`,
`gateway_admin.md`. 8 file còn lại đang dùng convention multi-line cũ:
`search_memory.md`, `get_profile.md`, `update_user_profile.md`,
`manage_user_profile.md`, `update_personality.md`, `web_search.md`,
`run_python_code.md`, `execute_host_bash.md`.

Chi tiết từng file cần refactor theo bảng §11 `CONTRIBUTING.md`.