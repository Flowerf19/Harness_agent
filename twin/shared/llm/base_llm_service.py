"""Base abstract class for LLM services."""

import abc
import logging
import os
import re
from typing import Dict, List, Optional, Union

from .llm_response import LLMResponse

# Sentinel strings returned (not raised) by LLM services when generation fails
# hard — e.g. the upstream endpoint resets the stream or returns a non-200.
# Agents must treat these as failures (show a friendly message, skip memory),
# never as a real reply. Kept here as the single source of truth.
LLM_ERROR_RESPONSE = "Error generating response."
LLM_ERROR_BAD_FORMAT = "Error: Unexpected response format."
LLM_ERROR_RESPONSES = frozenset({LLM_ERROR_RESPONSE, LLM_ERROR_BAD_FORMAT})


class BaseLLMService(abc.ABC):
    """
    Abstract base class defining the common interface for all LLM services.
    Đã được nâng cấp để hỗ trợ kiến trúc Memory 3 Tầng (List of Dicts) và Tracing.
    """

    def __init__(self, persona_path: str = "memories"):
        self.session = None
        self.logger = logging.getLogger(f"discord_bot.{self.__class__.__name__}")
        self.tool_registry = None

        # persona_path: "memories" (legacy shared) or "twin/march7/personas" or "twin/evernight/personas"
        self._persona_path = persona_path

        # Load file tính cách từ Markdown (Static Persona)
        self.static_identity = self._load_prompt("IDENTITY.md")
        self.static_soul = self._load_prompt("SOUL.md")
        self.static_tools = self._load_prompt("TOOL.md")

    def set_tool_registry(self, tool_registry) -> None:
        """Inject ToolRegistry vào LLM Service để lấy tool schemas."""
        self.tool_registry = tool_registry
        self.logger.debug("ToolRegistry đã được inject vào LLM Service")

    def _load_prompt(self, filename: str) -> str:
        """Load prompt content from persona_path."""
        try:
            base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            filepath = os.path.join(base_dir, self._persona_path, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    self.logger.debug(f"✅ Loaded prompt: {filename} from {self._persona_path}")
                    return content
            else:
                self.logger.warning(f"⚠️ Prompt file not found: {filepath}")
                return ""
        except Exception as e:
            self.logger.error(f"❌ Error loading prompt {filename}: {e}")
            return ""

    def _build_final_system_prompt(self, dynamic_core_prompt: str = "") -> str:
        """
        Trộn lẫn Tính cách tĩnh (từ file .md) và Trí nhớ Tiềm thức (Từ Tầng 3).
        Tool schemas được inject qua Native Function Calling (API Tool Calling).

        Args:
            dynamic_core_prompt: Hồ sơ user từ T3
        """
        parts = []

        # 1. Nhét tính cách gốc của Bot vào trước (IDENTITY.md và SOUL.md)
        if self.static_identity:
            parts.append(f"=== NHÂN CÁCH CỦA BẠN ===\n{self.static_identity}")
        if self.static_soul:
            parts.append(f"=== HƯỚNG DẪN HỘI THOẠI ===\n{self.static_soul}")

        # 2. Nhét hướng dẫn sử dụng Tool (TOOL.md)
        if self.static_tools:
            parts.append(f"=== HƯỚNG DẪN SỬ DỤNG TOOL ===\n{self.static_tools}")

        # 3. Nhét hồ sơ người dùng (Từ Tầng 3 gửi sang) vào sau
        if dynamic_core_prompt:
            parts.append(dynamic_core_prompt)

        return "\n\n".join(parts)

    # 🔴 CHỮ KÝ HÀM MỚI QUAN TRỌNG NHẤT
    # Note: Không dùng @traceable ở abstract method vì subclass đã có trace riêng
    # Nếu dùng ở cả 2 sẽ tạo nested spans không cần thiết
    @abc.abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        use_native_tools: bool = False,
        max_tokens: Optional[int] = None,
    ) -> Union[str, LLMResponse]:
        """
        Generate a response from the LLM based on structured messages.

        Args:
            messages: List of message dicts with "role" and "content" keys
            system_prompt: Dynamic core memory context from T3
            use_native_tools: If True, use Native Function Calling (API Tool Calling)
            max_tokens: Per-call output token cap; falls back to Config.LLM_MAX_TOKENS
                when None. Reasoning models need a larger budget for structured calls.

        Returns:
            LLMResponse with content, token metadata, and tool_calls if present
        """
        pass

    async def close(self) -> None:
        if self.session:
            await self.session.close()

    def split_response_into_parts(self, response: str) -> List[str]:
        """
        Chia nhỏ tin nhắn dài để lách luật 2000 ký tự của Discord.
        (Giữ nguyên logic cũ vì nó đang hoạt động tốt).
        """
        response = response.strip()
        if not response:
            return []

        lines = response.split("\n")
        result = []
        for line in lines:
            if len(line) <= 2000:
                if line.strip():
                    result.append(line)
            else:
                parts = re.split(r"([.!?]+\s*)", line)
                combined_parts = []
                for i in range(0, len(parts), 2):
                    if i + 1 < len(parts):
                        part = (parts[i] + parts[i + 1]).strip()
                    else:
                        part = parts[i].strip()
                    if part:
                        combined_parts.append(part)
                result.extend(combined_parts)
        return result