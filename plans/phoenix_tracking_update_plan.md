# Kế Hoạch Cập Nhật Phoenix Tracking trong Discord Bot

## 1. Tổng Quan Thay Đổi

Mục tiêu của kế hoạch này là nâng cấp hệ thống tracking Arize Phoenix trong Discord Bot để đạt được mức độ logging "xịn" như LangSmith, bao gồm đầy đủ metadata, tags, tokens và latency. Các thay đổi chính bao gồm:

- **Cập nhật khởi tạo Phoenix Toolkit** trong `bot.py` với cấu hình tối ưu
- **Chuyển đổi LM Studio Service** sang sử dụng `LMStudioResponse` để tự động trích xuất metadata
- **Thêm metadata và tags** vào các decorators trong các service layers
- **Mở rộng tracking cho memory operations** với thông tin context phong phú
- **Đảm bảo tính nhất quán** và không gây breaking changes

## 2. Danh Sách File Cần Cập Nhật

### 2.1 `discord-bot/src/bot.py` - Khởi tạo Phoenix Toolkit ✅ HOÀN THÀNH

**Thay đổi đã thực hiện:**
- ✅ Cập nhật `init_toolkit()` với metadata và tags phù hợp
- ✅ Thêm cấu hình tracing cụ thể cho Discord Bot

**Chi tiết thay đổi:**
```python
# Đã cập nhật:
init_toolkit(
    project_name="Be_Bay_Bot",
    frameworks=["aiohttp", "langchain"],
    metadata={
        "bot_version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "platform": "discord"
    },
    tags=["discord-bot", "llm-integration", "relationship-tracking"]
)
```

### 2.2 `discord-bot/src/services/wrappers/lm_studio_service.py` - Trả về LMStudioResponse ✅ HOÀN THÀNH

**Thay đổi đã thực hiện:**
- ✅ Import `LMStudioResponse` từ Arize_Phoenix_tool_kit
- ✅ Chuyển đổi phương thức `generate_response` để trả về `LMStudioResponse`
- ✅ Tính toán và điền đầy đủ metadata (tokens, latency, model info)
- ✅ Thêm `@track_llm_call` decorator với metadata và tags

**Chi tiết thay đổi:**
- Thay đổi signature hàm từ `async def generate_response(...) -> str` thành `async def generate_response(...) -> LMStudioResponse`
- Thêm logic tính toán tokens dựa trên response từ LM Studio API
- Đo latency bằng `time.perf_counter()`
- Xử lý các định dạng response khác nhau từ LM Studio

### 2.3 `discord-bot/src/cogs/llm_message.py` - Handle LMStudioResponse ✅ HOÀN THÀNH

**Thay đổi đã thực hiện:**
- ✅ Cập nhật code để handle `LMStudioResponse` object thay vì string
- ✅ Trích xuất `.content` từ LMStudioResponse để gửi tin nhắn

### 2.4 `discord-bot/src/services/relationship/relationship_service.py` - Thêm Metadata/Tags vào Decorators ✅ HOÀN THÀNH

**Thay đổi đã thực hiện:**
- ✅ Cập nhật decorator cho `extract_relationship_info` với metadata và tags
- ✅ Cập nhật decorator cho `process_message` với metadata và tags
- ✅ Cập nhật decorator cho `generate_relationship_analysis` với metadata và tags

**Chi tiết thay đổi:**

**Hàm `extract_relationship_info`:**
```python
@track_general_step(
    step_name="Relationship: Extract Info",
    metadata={"service": "relationship", "operation": "extract_info"},
    tags=["relationship-extraction", "llm-processing"]
)
```

**Hàm `process_message`:**
```python
@track_general_step(
    step_name="Relationship: Process Message",
    metadata={"service": "relationship", "operation": "process_message"},
    tags=["message-processing", "relationship-tracking", "interaction-recording"]
)
```

**Hàm `generate_relationship_analysis`:**
```python
@track_general_step(
    step_name="Relationship: Generate Analysis",
    metadata={"service": "relationship", "operation": "generate_analysis"},
    tags=["ai-analysis", "relationship-insights", "user-profile"]
)
```

### 2.5 `discord-bot/src/services/relationship/bond_service.py` - Thêm Decorator cho Hàm Xử Lý ✅ HOÀN THÀNH

**Thay đổi đã thực hiện:**
- ✅ Thêm decorator `@track_general_step` cho 4 hàm xử lý chính
- ✅ Cung cấp metadata và tags phù hợp cho từng loại operation

**Các hàm đã thêm decorator:**
1. `extract_relationship_info` - Step name: "Bond: Extract Relationship Info"
2. `_extract_relationship_info_fallback` - Step name: "Bond: Fallback Extraction"
3. `update_bond_score` - Step name: "Bond: Update Score"
4. `get_bond_info` - Step name: "Bond: Get Info"

### 2.6 Memory Services - Thêm Tracking cho Memory Operations ✅ HOÀN THÀNH

**Các file đã cập nhật:**
- ✅ `discord-bot/src/services/memory/memory_manager.py`
- ✅ `discord-bot/src/services/memory/episodic_service.py`
- ✅ `discord-bot/src/services/memory/summary_service.py`
- ✅ `discord-bot/src/services/memory/semantic_service.py`

#### 2.6.1 `memory_manager.py` ✅ HOÀN THÀNH

**Các hàm đã cập nhật decorator:**
1. `add_message` - Thêm metadata với user_id tracking
2. `get_context` - Metadata cho context retrieval
3. `get_working_memory_context` - Step name: "Memory: Get Working Memory Context"
4. `get_core_persona` - Step name: "Memory: Get Core Persona"
5. `trigger_episodic_update` - Step name: "Memory: Trigger Episodic Update"
6. `trigger_persona_update` - Step name: "Memory: Trigger Persona Update"
7. `force_update_all_memories` - Step name: "Memory: Force Update All"

#### 2.6.2 `episodic_service.py` ✅ HOÀN THÀNH

**Các hàm đã thêm decorator:**
1. `update_episodic_memory` - Step name: "Episodic: Update Memory"
2. `get_episodic_context` - Step name: "Episodic: Get Context"

#### 2.6.3 `summary_service.py` ✅ HOÀN THÀNH

**Các hàm đã thêm decorator:**
1. `update_summary` - Step name: "Summary: Update"
2. `get_summary_context` - Step name: "Summary: Get Context"

#### 2.6.4 `semantic_service.py` ✅ HOÀN THÀNH

**Các hàm đã thêm decorator:**
1. `update_semantic_memory` - Step name: "Semantic: Update Memory"
2. `get_semantic_context` - Step name: "Semantic: Get Context"

## 3. Code Snippets Mẫu

### 3.1 Mẫu Decorator cho LLM Calls

```python
from Arize_Phoenix_tool_kit import track_llm_call

@track_llm_call(
    model_name=Config.LM_STUDIO_MODEL,
    prompt_arg="prompt",
    metadata={
        "service": "lm_studio",
        "endpoint": Config.LM_STUDIO_API_URL,
        "temperature": 0.7,
        "max_tokens": 1000
    },
    tags=["llm-generation", "discord-response", "conversation-context"]
)
async def generate_response(self, prompt: str, user_id: str = None, conversation_context: str = "") -> LMStudioResponse:
    # Implementation here
    pass
```

### 3.2 Mẫu Decorator cho General Steps

```python
from Arize_Phoenix_tool_kit import track_general_step

@track_general_step(
    step_name="Relationship: Process Message",
    metadata={
        "service": "relationship",
        "operation": "process_message",
        "user_id": lambda *args, **kwargs: args[1] if len(args) > 1 else kwargs.get('author_id')
    },
    tags=["message-processing", "relationship-tracking", "interaction-recording"]
)
async def process_message(self, author_id: str, author_username: str, message_content: str, ...):
    # Implementation here
    pass
```

### 3.3 Mẫu LMStudioResponse Return

```python
from Arize_Phoenix_tool_kit import LMStudioResponse
import time

async def generate_response(self, prompt: str, user_id: str = None, conversation_context: str = "") -> LMStudioResponse:
    start_time = time.perf_counter()
    
    # ... existing implementation ...
    
    # Parse response and calculate tokens
    prompt_tokens = len(prompt.split())  # Simple token estimation
    completion_tokens = len(response_content.split())
    total_tokens = prompt_tokens + completion_tokens
    latency_ms = (time.perf_counter() - start_time) * 1000
    
    return LMStudioResponse(
        content=response_content,
        model=self.model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        finish_reason="stop"
    )
```

## 4. Thứ Tự Thực Hiện

### Giai đoạn 1: Chuẩn bị và Cấu hình Cơ bản ✅ HOÀN THÀNH
1. ✅ **Cập nhật `bot.py`** - Khởi tạo Phoenix Toolkit với metadata/tags
2. ✅ **Tạo utility functions** để xử lý dynamic metadata (không cần thiết)

### Giai đoạn 2: Cập nhật LLM Layer ✅ HOÀN THÀNH
3. ✅ **Cập nhật `lm_studio_service.py`** - Chuyển sang trả về `LMStudioResponse`
4. ✅ **Cập nhật `llm_message.py`** - Handle LMStudioResponse object
5. ✅ **Kiểm thử LLM calls** để đảm bảo metadata được trích xuất đúng

### Giai đoạn 3: Cập nhật Relationship Services ✅ HOÀN THÀNH
6. ✅ **Cập nhật `relationship_service.py`** - Thêm metadata/tags vào decorators
7. ✅ **Cập nhật `bond_service.py`** - Thêm decorators cho các hàm xử lý chính

### Giai đoạn 4: Cập nhật Memory Services ✅ HOÀN THÀNH
8. ✅ **Cập nhật `memory_manager.py`** - Thêm metadata/tags với dynamic user context
9. ✅ **Cập nhật `episodic_service.py`** - Thêm decorators cho 2 hàm
10. ✅ **Cập nhật `summary_service.py`** - Thêm decorators cho 2 hàm
11. ✅ **Cập nhật `semantic_service.py`** - Thêm decorators cho 2 hàm

### Giai đoạn 5: Kiểm thử và Validation ⏳ CHỜ KIỂM TRA
12. ⏳ **Kiểm thử end-to-end** toàn bộ flow
13. ⏳ **Xác minh dữ liệu tracking** trong Phoenix UI

## 5. Testing Plan

### 5.1 Unit Tests
- **LLM Response Format**: Kiểm tra `LMStudioResponse` được trả về đúng format với đầy đủ fields
- **Decorator Metadata**: Xác minh metadata và tags được ghi nhận đúng trong spans
- **Token Calculation**: Kiểm tra logic tính toán tokens (prompt, completion, total)
- **Latency Measurement**: Xác minh latency_ms được đo chính xác

### 5.2 Integration Tests
- **End-to-End Message Flow**: Gửi tin nhắn qua Discord và kiểm tra toàn bộ chain tracking
- **Relationship Extraction**: Kiểm tra tracking cho quá trình extract relationship info
- **Memory Operations**: Xác minh tracking cho các operation thêm/xem memory
- **Error Handling**: Kiểm tra tracking khi có exceptions (spans should have error status)

### 5.3 Validation trong Phoenix UI
- **Metadata Visibility**: Xác minh metadata hiển thị đúng trong Phoenix dashboard
- **Tags Filtering**: Kiểm tra khả năng filter spans theo tags
- **Token Metrics**: Xác minh metrics về tokens được tính toán và hiển thị đúng
- **Latency Charts**: Kiểm tra biểu đồ latency cho các LLM calls
- **Trace Hierarchy**: Xác minh mối quan hệ parent-child giữa các spans

### 5.4 Performance Testing
- **Overhead Measurement**: Đo impact của tracking lên performance (nên < 5% overhead)
- **Memory Usage**: Kiểm tra memory usage không tăng đáng kể do tracking
- **Concurrent Requests**: Test với nhiều requests đồng thời để đảm bảo stability

## 6. Lưu Ý Quan Trọng

- **Backward Compatibility**: Đảm bảo các thay đổi không ảnh hưởng đến functionality hiện tại
- **Error Handling**: Tracking không được làm crash application nếu có lỗi
- **Performance Impact**: Giữ overhead ở mức tối thiểu
- **Configuration Flexibility**: Cho phép disable tracking trong môi trường development nếu cần
- **Data Privacy**: Đảm bảo không ghi log thông tin nhạy cảm của người dùng

## 7. Rollback Plan

Nếu có vấn đề xảy ra:
1. Revert các thay đổi trong file plans
2. Disable Phoenix tracking bằng cách comment dòng `init_toolkit()` trong `bot.py`
3. Deploy version cũ và investigate nguyên nhân
4. Fix issues và deploy lại với testing kỹ lưỡng hơn

---

## 8. Trạng Thái Implementation

| Giai đoạn | Trạng thái | Ghi chú |
|-----------|------------|---------|
| Giai đoạn 1: Chuẩn bị và Cấu hình | ✅ Hoàn thành | bot.py đã cập nhật |
| Giai đoạn 2: Cập nhật LLM Layer | ✅ Hoàn thành | lm_studio_service.py, llm_message.py |
| Giai đoạn 3: Cập nhật Relationship Services | ✅ Hoàn thành | relationship_service.py, bond_service.py |
| Giai đoạn 4: Cập nhật Memory Services | ✅ Hoàn thành | memory_manager.py, episodic_service.py, summary_service.py, semantic_service.py |
| Giai đoạn 5: Kiểm thử và Validation | ⏳ Chờ kiểm tra | Cần test end-to-end |

**Tổng kết:** Tất cả các thay đổi code đã hoàn thành. Cần thực hiện kiểm thử end-to-end và xác minh trong Phoenix UI.