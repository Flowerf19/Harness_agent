# Kế hoạch di chuyển cấu hình hardcoded sang hệ thống settings.py

## Tổng quan
Kế hoạch này nhằm mục đích di chuyển các giá trị cấu hình hardcoded trong mã nguồn sang hệ thống cấu hình tập trung trong file `src/config/settings.py`. Điều này sẽ cải thiện khả năng bảo trì, linh hoạt và tuân thủ nguyên tắc 12-factor app.

## 1. Cập nhật file src/config/settings.py

### Các cấu hình mới cần thêm:

```python
# LM Studio settings
LM_STUDIO_API_URL = os.getenv("LM_STUDIO_API_URL", "http://localhost:1234")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Message limits
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "500"))
```

### Vị trí đặt trong class Config:
- Các cấu hình LM Studio nên được đặt sau các cấu hình LLM provider hiện có (sau dòng 25)
- LOG_LEVEL nên được đặt trong phần logging configuration (có thể tạo section mới)
- MAX_MESSAGES nên được đặt trong phần Discord bot configuration

## 2. Cập nhật src/services/channel_service.py

### Vấn đề hiện tại:
- Dòng 10: `self.gemini_api_url = os.getenv('GEMINI_API_URL', 'http://localhost:11434/api/generate')`
- Sử dụng URL mặc định không phù hợp với GEMINI_API_URL thực tế

### Giải pháp:
1. Import Config class từ `config.settings`
2. Thay thế việc sử dụng `os.getenv` trực tiếp bằng `Config.GEMINI_API_URL`
3. Loại bỏ URL mặc định không chính xác

### Mã sau khi cập nhật:
```python
from config.settings import Config

class ChannelService:
    def __init__(self):
        self.gemini_api_url = Config.GEMINI_API_URL
```

## 3. Cập nhật src/services/lm_studio_service.py

### Vấn đề hiện tại:
- Dòng 12-13: Sử dụng `os.getenv` trực tiếp thay vì Config class
- Đã import Config nhưng không sử dụng

### Giải pháp:
1. Thay thế `os.getenv("LM_STUDIO_API_URL", "http://localhost:1234")` bằng `Config.LM_STUDIO_API_URL`
2. Thay thế `os.getenv("LM_STUDIO_MODEL", "local-model")` bằng `Config.LM_STUDIO_MODEL`

### Mã sau khi cập nhật:
```python
class LMStudioService:
    def __init__(self):
        self.api_url = Config.LM_STUDIO_API_URL
        self.model = Config.LM_STUDIO_MODEL
        # ... rest of the code remains the same
```

## 4. Cập nhật src/bot.py

### Vấn đề hiện tại:
- Dòng 18: `level=logging.INFO` hardcoded
- Dòng 40: `max_messages=500` hardcoded

### Giải pháp:
1. Import Config class và logging module
2. Chuyển đổi LOG_LEVEL string thành logging level tương ứng
3. Sử dụng Config.MAX_MESSAGES cho tham số max_messages

### Mã sau khi cập nhật:

#### Phần logging configuration:
```python
from config.settings import Config
import logging

# Helper function to convert string log level to logging constant
def get_log_level(level_str):
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    return level_map.get(level_str.upper(), logging.INFO)

# Updated logging configuration
logging.basicConfig(
    level=get_log_level(Config.LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
```

#### Phần Discord bot initialization:
```python
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    case_insensitive=True,
    strip_after_prefix=True,
    max_messages=Config.MAX_MESSAGES,
)
```

## 5. Đảm bảo tính tương thích ngược

### Nguyên tắc:
- Tất cả các cấu hình mới đều có giá trị mặc định phù hợp
- Không thay đổi tên environment variables hiện có
- Duy trì hành vi mặc định giống như trước khi migration

### Giá trị mặc định đề xuất:
- `LM_STUDIO_API_URL`: `"http://localhost:1234"` (giá trị đang được sử dụng trong lm_studio_service.py)
- `LM_STUDIO_MODEL`: `"local-model"` (giá trị đang được sử dụng trong lm_studio_service.py)
- `LOG_LEVEL`: `"INFO"` (mức log hiện tại đang được sử dụng)
- `MAX_MESSAGES`: `500` (giá trị hiện tại đang được sử dụng)

### Kiểm tra tương thích:
- Nếu người dùng đã thiết lập các environment variables hiện có, chúng sẽ vẫn hoạt động
- Nếu không có environment variables, hệ thống sẽ sử dụng giá trị mặc định như hiện tại
- Không có breaking changes đối với API hoặc cấu trúc dự án

## 6. Thứ tự triển khai

1. Cập nhật `src/config/settings.py` đầu tiên
2. Cập nhật `src/services/lm_studio_service.py` 
3. Cập nhật `src/services/channel_service.py`
4. Cập nhật `src/bot.py`
5. Kiểm thử toàn bộ hệ thống

## 7. Lưu ý quan trọng

- Cần đảm bảo rằng tất cả các imports đều đúng đường dẫn (relative imports)
- Trong `src/bot.py`, cần xử lý việc convert string log level sang logging constant
- Kiểm tra kỹ các giá trị mặc định để đảm bảo chúng phù hợp với môi trường production
- Cập nhật documentation nếu có về các environment variables mới