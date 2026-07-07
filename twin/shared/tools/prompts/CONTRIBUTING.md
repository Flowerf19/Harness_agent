# Contributing Tool Guides — Kiến trúc & Quy trình

File này giải thích **kiến trúc + quy trình đầy đủ** để contributor/agent tự
tạo tool mới hoặc refactor tool cũ đúng chuẩn hệ thống. Đây là companion
của `ARCHITECTURE.md` (file ngắn chứa dàn ý) — file này chứa bối cảnh, ví
dụ end-to-end, dependency injection, trạng thái hiện tại.

> **Muốn viết/sửa 1 file guide nhanh** → đọc `ARCHITECTURE.md`.
> **Muốn hiểu sâu kiến trúc + tự tạo tool mới** → đọc file này.

---

## 1. Bối cảnh kiến trúc

Hệ thống dùng **declarative tool catalog** (xem `ARCHITECTURE.md` §4 ở root +
`twin/shared/tools/declarations/system_tools.py`). Một tool gồm 3 phần
tách biệt:

| Phần | File | Vai trò |
|---|---|---|
| **Class Python** | `twin/shared/tools/modules/<cat>/<tool>_tool.py` | Execution logic |
| **Catalog entry** | `twin/shared/tools/declarations/system_tools.py` | Đăng ký + permissions + backend |
| **Guide markdown** | `twin/shared/tools/prompts/guides/<tool>.md` | Schema description + body guide cho LLM |

Tại sao tách execution (Python) và schema/prompt (markdown)?

1. **Trust boundary** (`ARCHITECTURE.md` §4 root): MCP server bên ngoài không
   tin được. Schema mà LLM thấy phải do code local sở hữu, không lấy từ
   `MCPClient.list_tools()`. Remote schema có thể bị prompt-injection.
2. **Single source of truth cho model-facing contract**: 11 tool × 1 file md
   dễ audit, dễ review, dễ áp policy "owner approval" / "visible_to".
3. **Stable schema session-long**: cache schema ở bootstrap
   (`DeclaredToolProxy._description`), chỉ restart mới cập nhật → token
   không phình giữa request, schema ổn định.

### 1.1 Hybrid MCP + system tool — tại sao?

- **MCP là giao thức chuẩn** để expose tool bên ngoài (vd Tavily search,
  translation server). Bên thứ 3 wrap tool MCP dễ dàng.
- **Local system tool** chạy logic thuộc sở hữu march7 (memory store,
  redis, codebox sandbox, gateway client). Không qua MCP vì cần quyền
  inject dependency (Config, redis client, approval_gate).
- **Schema được "nhân bản"**: Remote MCP metadata KHÔNG BAO GIỜ render vào
  LLM prompt (`ARCHITECTURE.md` §4 root). Code local tự viết schema từ
  understanding về MCP server — đây là cách hệ thống giữ trust boundary
  dù hybrid.

Hệ quả: contributor phải viết schema cho cả remote_mcp backend, không
chỉ rely vào `MCPClient.list_tools()`.

---

## 2. Luồng load: file guide.md đi đâu trong request

Một request user đi qua vòng Think/Act
(`twin/shared/agent/agent_loop.py`):

```
Think(Decide)  → LLM trả lời trực tiếp hoặc chọn tool
  ↓ catalog line (system prompt)         ← render_catalog()
  ↓ tool schemas (OpenAI function calling) ← DeclaredToolProxy.description

Think(Refine)  → LLM emit JSON {action, tool_name, args}
  ↓ full tool guide (re-prompt)         ← render_tool_guide()

Act            → registry.execute_tool → tool output

Think(Decide)  → trả lời từ observation hoặc chọn tool tiếp theo
```

| Giai đoạn | Load gì từ guide.md | Code reference |
|---|---|---|
| **Catalog line** (system prompt) | `splitlines()[0]` của block `<tool_description>` | `catalog.py:67-74` |
| **Schema description** (OpenAI function calling) | `splitlines()[0]` (cache ở bootstrap) | `bootstrap.py:42-46`, `catalog.py:135` |
| **Full guide** (Refine re-prompt) | Toàn bộ file sau khi strip 2 tag | `catalog.py:90-95` |

**Hệ quả cứng**:

- Dòng đầu block `<tool_description>` → LLM thấy ở **mọi** request (qua
  schema) và **mọi** agent (qua catalog). Phải tự đứng được.
- Phần còn lại → LLM chỉ thấy ở Refine, **sau khi đã chọn tool**. Chỗ
  giải thích chi tiết param, ví dụ, anti-hallucination rule.

**Không có `tool_choice`**: code không bao giờ force LLM phải gọi tool —
root cause chính gây LLM hallucination (xem §10).

---

## 3. Quyết định trước khi viết

Trả lời 5 câu trước khi viết:

### 3.1 Tool name

- Snake_case, ngắn gọn (≤25 ký tự), mô tả hành động chính.
- VD tốt: `search_memory`, `host_system`, `run_python_code`,
  `update_user_profile`.
- Tránh: tên generic (`do_thing`), tên dài
  (`send_discord_dm_with_embed`).

### 3.2 Backend (`local` hay `remote_mcp`)

| Backend | Khi nào | Wrap như thế nào |
|---|---|---|
| `local` | Tool chạy trong process Python (memory store, redis, codebox, gateway client) | Class kế thừa `BaseTool`, async `execute(...)` |
| `remote_mcp` | Tool gọi MCP server bên ngoài trust boundary (vd Tavily) | Class kế thừa `BaseTool`, nhận `MCPClient` qua `__init__`, `execute(...)` gọi `client.call_tool(...)` |

**Lưu ý quan trọng** (`ARCHITECTURE.md` §4 root): Remote `tools/list`
metadata là untrusted, **không bao giờ** render vào system prompt / lazy
guide / schema description. Luôn tự viết schema local.

### 3.3 `visible_to` — agent nào thấy tool trong schema

- `None` (mặc định) → mọi agent thấy.
- `frozenset({"evernight"})` → chỉ Evernight.
- `frozenset()` (rỗng) → **hard-hidden** khỏi tất cả agents (vd legacy).

### 3.4 `allowed_to` — agent nào execute được

- `None` (mặc định) → mọi agent.
- Thường set giống `visible_to` (nếu khác → cho phép thấy rộng hơn
  execute).
- Agent không thấy (`visible_to` loại ra) thì không execute được.

### 3.5 Approval (Trạm Gác)

- Tool chạm host / ghi file / đổi config / xóa data → **CÓ**. Pattern:
  nhận `approval_gate: ApprovalGate` qua `__init__`, gọi
  `await self.approval_gate.check_approval(self.name, "mô tả lệnh")`
  trước execute.
- Tool chỉ đọc (memory, profile, capabilities) → **KHÔNG**.

---

## 4. Quy ước viết (chi tiết)

### 4.1 Công thức 1 dòng description

```
Tool <phạm vi ngắn gọn> qua <cơ chế>: <cách gọi điển hình> — BẮT BUỘC <khi nào phải dùng>, KHÔNG <khi nào không dùng>.
```

≤300 ký tự, 1 dòng vật lý.

Công thức này cover 4 việc LLM cần quyết trong 1 dòng:

1. Phạm vi tool.
2. Cơ chế (gateway / MCP / local / sandbox).
3. Cách gọi điển hình (mode, schema).
4. Anti-hallucination hint ngắn.

### 4.2 Giọng văn

- Tiếng Việt, xưng "cậu"/"bạn" cho user, "tool này" cho bản thân —
  nhất quán với SOUL.md/IDENTITY.md.
- Động từ rõ ràng: "đọc", "ghi", "tìm", "cập nhật". Tránh "xử lý",
  "thực hiện".
- Tool khác → backtick: `search_memory`.
- Param → backtick: `mode`, `command`.
- KHÔNG viết tiếng Anh — LLM phải switch context, dễ ignore rule.

### 4.3 "Khi nên dùng" vs "Khi không nên dùng"

| Mục | Mục đích | Số lượng |
|---|---|---|
| Khi nên dùng | Intent cue cho LLM Decide — "user nói X thì chọn tool này" | 3-5 bullet |
| Khi không nên dùng | Chống LLM chọn nhầm — "thay bằng tool Y nếu..." | 2-4 bullet |

Mỗi bullet bắt đầu bằng động từ hoặc cụm user-intent, không bắt đầu
bằng "Tool".

### 4.4 Khi nào thêm "Quy tắc chống hallucination"

Chỉ thêm cho tool có **≥1** đặc điểm:

- LLM có khả năng cao tự tin bịa output (vd `host_system` — bịa uptime).
- LLM có khả năng cao tự thêm info ngoài tool output (vd
  `gateway_admin` doctor nói "5 capabilities").
- Tool chạm "trí nhớ"/"lịch sử" user (vd `search_memory` — bịa user
  đã nói).
- Tool destructive (vd `manage_user_profile` — overwrite T3).

Format mỗi rule:

```
- [HÀNH ĐỘNG BẮT BUỘC / CẤM] khi [điều kiện cụ thể], [lý do ngắn 1 câu].
```

### 4.5 Khi nào thêm "Input"

Chỉ thêm khi:

- Tool có >3 params, hoặc
- Param có ràng buộc đặc biệt (vd `mode` enum, `timeout` clamp 5-120,
  `user_id` bắt buộc Discord ID dạng số).

**Không** liệt kê param hiển nhiên (vd `user_id` nếu đã giải thích ở
"Khi nên dùng").

---

## 5. Class Python skeleton

File: `twin/shared/tools/modules/<category>/<tool_name>_tool.py`

```python
"""<ToolName>Tool - <one-line purpose>."""
from __future__ import annotations

import logging
from typing import Any, Optional

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class <ToolName>Tool(BaseTool):
    """<Mô tả ngắn gọn 1-2 câu>."""

    def __init__(
        self,
        # Tên param phải khớp key trong dependencies dict (bootstrap.py:105-122).
        dependency_a: Any,
        dependency_b: Optional[Any] = None,
    ):
        self.dependency_a = dependency_a
        self.dependency_b = dependency_b

    @property
    def name(self) -> str:
        return "<tool_name>"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param_required": {
                    "type": "string",
                    "description": "Mô tả param bắt buộc.",
                },
                "param_optional": {
                    "type": "integer",
                    "description": "Mô tả param optional.",
                    "default": 10,
                },
            },
            "required": ["param_required"],
        }

    async def execute(
        self,
        param_required: str,
        param_optional: int = 10,
    ) -> str:
        """Thực thi tool, trả về chuỗi human-readable cho LLM."""
        if not param_required or not param_required.strip():
            return "Lỗi: Thiếu param_required."
        if self.dependency_a is None:
            return "Lỗi: dependency_a chưa được cấu hình."

        try:
            result = await self.dependency_a.do_thing(param_required)
        except Exception as e:
            logger.error("<ToolName>: execute failed: %s", e, exc_info=True)
            return f"Lỗi: {e}"

        return self._format_result(result)

    @staticmethod
    def _format_result(result: Any) -> str:
        if not result:
            return "Không có kết quả."
        return f"Kết quả: {result}"
```

### 5.1 Quy tắc class

- Kế thừa `BaseTool`, implement `name` + `parameters_schema` (cả 2
  abstract).
- `execute` async, signature khớp `required` params trong schema.
- Trả `str` (human-readable cho LLM), không trả `dict` / `None`.
- Validate input đầu hàm, trả `"Lỗi: <message>"` (tiếng Việt) thay vì
  raise.
- Catch exception, log + trả chuỗi lỗi — không để bubble lên agent loop
  (trừ khi cần `ToolExecutionError` để retry logic).
- **KHÔNG** gọi LLM bên trong tool (tool là pure execution).
- **KHÔNG** gọi Discord/UI trực tiếp — chỉ qua approval gate nếu cần.

### 5.2 Dependency injection

`build_tool_registry` (`bootstrap.py:105-122`) inject dependency qua
`__init__` kwargs. Tên param phải khớp key:

```python
dependencies = {
    "core_manager": core_manager,
    "memory_manager": memory_manager,
    "profile_store": profile_store,
    "llm_service": llm_service,
    "tavily_mcp_client": tavily_mcp_client,
    "codebox_client": codebox_client,
    "host_gateway_client": host_gateway_client,
    "approval_gate": approval_gate,
    # ... thêm nếu cần
}
```

Nếu tool cần dependency mới không có trong dict → phải thêm vào dict
trước.

---

## 6. Catalog entry

File: `twin/shared/tools/declarations/system_tools.py`

Thêm vào tuple `SYSTEM_TOOL_SPECS`:

```python
ToolSpec(
    module="twin.shared.tools.modules.<category>.<tool_name>_tool",
    class_name="<ToolName>Tool",
    guide_path="guides/<tool_name>.md",
    visible_to=None,                    # hoặc frozenset({"evernight"})
    allowed_to=None,                    # hoặc frozenset({"evernight"})
    backend="local",                    # hoặc "remote_mcp"
),
```

`ToolSpec.__post_init__` raise `ValueError` nếu:

- `backend="remote_mcp"` mà `guide_path` là `None`.
- `backend` không thuộc `{"local", "remote_mcp"}`.

---

## 7. Ví dụ end-to-end: tạo tool `translate_text`

### 7.1 Bài toán

User thỉnh thoảng yêu cầu dịch đoạn văn. Hiện LLM phải dùng
`web_search` rồi parse — không ổn. Cần tool `translate_text`.

### 7.2 Quyết định

| Câu hỏi | Trả lời |
|---|---|
| Name | `translate_text` |
| Backend | `remote_mcp` (gọi translation MCP server) |
| `visible_to` | `None` (mọi agent) |
| `allowed_to` | `None` |
| Approval? | Không (chỉ đọc/gọi external) |

### 7.3 Class Python

File: `twin/shared/tools/modules/execution/translate_text_tool.py`

```python
class TranslateTextTool(BaseTool):
    """Translate text via MCP translation server."""

    def __init__(self, translate_mcp_client: Optional[Any] = None):
        self.translate_mcp_client = translate_mcp_client

    @property
    def name(self) -> str:
        return "translate_text"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Văn bản cần dịch."},
                "target_lang": {
                    "type": "string",
                    "enum": ["en", "vi", "ja", "fr"],
                    "default": "en",
                    "description": "Mã ngôn ngữ đích (ISO 639-1).",
                },
            },
            "required": ["text"],
        }

    async def execute(self, text: str, target_lang: str = "en") -> str:
        if not text or not text.strip():
            return "Lỗi: Thiếu text."
        if self.translate_mcp_client is None:
            return "Lỗi: translate_mcp_client chưa được cấu hình."

        try:
            result = await self.translate_mcp_client.call_tool(
                "translate",
                {"text": text.strip(), "target": target_lang},
            )
        except Exception as e:
            logger.error("TranslateTextTool: failed: %s", e, exc_info=True)
            return f"Lỗi khi dịch: {e}"

        return f"Bản dịch ({target_lang}): {result}"
```

### 7.4 Catalog entry

```python
ToolSpec(
    module="twin.shared.tools.modules.execution.translate_text_tool",
    class_name="TranslateTextTool",
    guide_path="guides/translate_text.md",
    backend="remote_mcp",
),
```

### 7.5 Guide markdown

File: `twin/shared/tools/prompts/guides/translate_text.md`

```markdown
<tool_description>
Tool dịch văn bản sang ngôn ngữ khác qua translation MCP server: truyền text + target_lang, nhận bản dịch — BẮT BUỘC dùng tool này khi user yêu cầu dịch, KHÔNG tự dịch bằng LLM knowledge.
</tool_description>

## translate_text

Dịch văn bản sang ngôn ngữ đích qua translation MCP server bên ngoài.

### Khi nên dùng
- User yêu cầu dịch một đoạn văn, một câu, hoặc một từ.
- Cần dịch chính xác ngôn ngữ hiện đại (không phải ngôn ngữ cổ/đặc thù).
- Đã biết target language (ISO 639-1: en, vi, ja, fr).

### Khi không nên dùng
- User chỉ hỏi "nghĩa của từ X là gì" → trả lời trực tiếp.
- Cần dịch ngôn ngữ không có trong enum → báo user không hỗ trợ.
- Cần dịch cả đoạn code/config giữ nguyên syntax → không dùng.

### Quy tắc chống hallucination — BẮT BUỘC gọi tool
- Khi user yêu cầu dịch, **BẮT BUỘC** gọi `translate_text` rồi trả bản dịch từ tool output. KHÔNG tự dịch bằng LLM knowledge — translation model chuyên dụng chính xác hơn LLM.
- Nếu tool lỗi/không available → nói rõ "không dịch được vì <lý do>".
- Nếu reply chứa bản dịch mà không có tool call thành công → hallucination, KHÔNG được làm.
```

### 7.6 Verification

```bash
# 1. Schema description 1 dòng
python -c "
import re
from pathlib import Path
text = Path('twin/shared/tools/prompts/guides/translate_text.md').read_text()
m = re.search(r'<tool_description>(.*?)</tool_description>', text, re.DOTALL)
block = m.group(1).strip()
assert len(block.splitlines()) == 1
print('✅ description 1 line')
"

# 2. Catalog có entry
python -c "
from twin.shared.tools.declarations.system_tools import SYSTEM_TOOL_SPECS
specs = [s for s in SYSTEM_TOOL_SPECS if s.class_name == 'TranslateTextTool']
assert specs and specs[0].backend == 'remote_mcp'
print('✅ catalog entry OK')
"

# 3. Class import được
python -c "
from twin.shared.tools.modules.execution.translate_text_tool import TranslateTextTool
t = TranslateTextTool()
assert t.name == 'translate_text'
schema = t.parameters_schema
assert 'text' in schema['required']
print('✅ class OK')
"

# 4. Restart container
docker compose -f docker/docker-compose.yml restart march7
```

Sau 4 bước pass, tool `translate_text` đã available cho LLM.

---

## 8. Quy trình sửa guide hiện có

1. Đọc file guide hiện tại.
2. Cross-check với `parameters_schema` của class tương ứng trong
   `twin/shared/tools/modules/`.
3. Nếu khác → sửa schema OR sửa guide (đảm bảo khớp).
4. Nếu convention đang multi-line (block chứa cả body) → refactor về
   Convention A theo `ARCHITECTURE.md` §"Cấu trúc bắt buộc".
5. Chạy verification script (xem §10).
6. Restart container.

---

## 9. Anti-pattern (chi tiết)

❌ **Block `<tool_description>` nhiều dòng** — code lấy `splitlines()[0]`,
phần thừa rơi vào full guide, LLM đọc trùng.

❌ **Markdown header trong block** — schema description vô nghĩa.

❌ **Thiếu anti-hallucination hint ở description** — LLM dễ chọn nhưng
cũng dễ bịa.

❌ **"Khi nên dùng" / "Khi không nên dùng" ý lẫn lộn** — LLM không biết
cue nào áp dụng.

❌ **Schema description tiếng Anh** — không khớp SOUL.md, LLM switch
context, dễ ignore rule.

❌ **Dùng `MCPClient.list_tools()` build schema** — vi phạm trust boundary.

❌ **Tool gọi LLM bên trong `execute()`** — tool là pure execution.

❌ **Tool gọi Discord/UI trực tiếp** — chỉ qua approval gate.

❌ **Hardcode secret/token trong tool** — inject qua `__init__` từ Config.

---

## 10. Trạng thái hiện tại (2026-06-27)

### 10.1 Bảng 11 tool

| Tool | Backend | visible_to | Anti-halluc section? |
|---|---|---|---|
| `search_memory` | local | all | ❌ TODO |
| `consolidate_memory` | local | evernight | ✅ |
| `get_profile` | local | all | ❌ TODO |
| `update_user_profile` | local | all | ❌ TODO |
| `manage_user_profile` | local | evernight | ❌ TODO |
| `update_personality` | local | all | ❌ TODO |
| `web_search` (Tavily) | remote_mcp | all | ❌ TODO |
| `run_python_code` | local | all | ❌ TODO |
| `host_system` | local | all | ✅ |
| `gateway_admin` | local | evernight | ❌ TODO |
| `execute_host_bash` | local | (hidden) | (legacy) |

### 10.2 File cần refactor theo spec

8 file đang dùng convention multi-line block (block chứa cả body guide):
`search_memory.md`, `get_profile.md`, `update_user_profile.md`,
`manage_user_profile.md`, `update_personality.md`, `web_search.md`,
`run_python_code.md`, `execute_host_bash.md`.

### 10.3 File đã đúng spec

3 file: `host_system.md`, `consolidate_memory.md`, `gateway_admin.md`.

### 10.4 File mẫu tham chiếu

- `host_system.md` — đầy đủ 4 section, anti-hallucination mạnh. Dùng
  làm template khi viết tool mới.

---

## 11. Known gap (cần fix sau)

1. **Không có `tool_choice`**: code không force LLM gọi tool → LLM dễ
   skip và bịa. Root cause hallucination chính (`minimax-m3:cloud`
   chọn 1/7 lần). Fix: thử `tool_choice: required` khi user intent rõ
   ràng, hoặc tăng weight catalog line + anti-halluc section.
2. **Refine parser yếu**: `parse_refine_decision` (`contract.py`) lỗi
   "Extra data" khi LLM emit 2 JSON dính nhau. Bug robustness, ngoài
   scope tool guide spec.
3. **8 file chưa refactor**: cần rewrite theo Convention A — backlog.
4. **Anti-halluc section ở 6 tool còn lại**: cần bổ sung sau khi
   refactor structure.
