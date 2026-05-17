import logging

import tiktoken

from ..constants import STRUCTURAL_OVERHEAD_TOKENS

logger = logging.getLogger(__name__)


class ApproximateEncoding:
    def encode(self, text: str) -> list[str]:
        return text.split()


class TokenCounter:
    """
    Bộ đếm Token chính xác cho LLM.
    Bao gồm cả token của văn bản thuần và token cấu trúc (JSON, ChatML tags).
    """

    def __init__(self, model_name: str = "cl100k_base"):
        # Mặc định dùng chuẩn cl100k_base của GPT-4 / Qwen
        try:
            self.encoding = tiktoken.get_encoding(model_name)
        except Exception:
            logger.warning(f"Không tìm thấy model {model_name}, dùng bộ đếm gần đúng.")
            self.encoding = ApproximateEncoding()

    def count_text(self, text: str) -> int:
        """Đếm số lượng token của một chuỗi văn bản thuần."""
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def count_entry_tokens(self, text: str) -> int:
        """
        Đếm token cho một tin nhắn chuẩn bị lưu vào RAM.
        LUÔN cộng thêm Overhead để bảo đảm không bị tràn Context Window.
        """
        base_tokens = self.count_text(text)
        return base_tokens + STRUCTURAL_OVERHEAD_TOKENS
