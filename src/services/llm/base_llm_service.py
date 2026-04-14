"""Base abstract class for LLM services."""

import abc
import logging
import os
import re
from typing import Dict, List, Optional, Union

from langsmith import traceable

from .llm_response import LLMResponse


class BaseLLMService(abc.ABC):
    """
    Abstract base class defining the common interface for all LLM services.
    Đã được nâng cấp để hỗ trợ kiến trúc Memory 3 Tầng (List of Dicts) và Tracing.
    """

    def __init__(self):
        self.session = None
        self.logger = logging.getLogger(f"discord_bot.{self.__class__.__name__}")
        self.tool_manager = None  # [MỚI] ToolManager sẽ được inject sau (Legacy)
        self.mcp_client = None    # [MỚI] MCP Client sẽ được inject sau (New)

        # Load file tính cách từ Markdown (Static Persona)
        # File này sẽ làm nền tảng, còn Core Memory (T3) sẽ bổ sung phần Dynamic Persona
        self.static_identity = self._load_prompt("IDENTITY.md", "memories")
        self.static_soul = self._load_prompt("SOUL.md", "memories")
        self.static_tools = self._load_prompt("TOOLS.md", "memories")  # [MỚI] Load TOOLS.md

    def set_tool_manager(self, tool_manager) -> None:
        """[MỚI] Inject ToolManager vào LLM Service (Legacy)."""
        self.tool_manager = tool_manager
        self.logger.info("✅ ToolManager đã được inject vào LLM Service (Legacy)")

    def set_mcp_client(self, mcp_client) -> None:
        """[MỚI] Inject MCP Client vào LLM Service."""
        self.mcp_client = mcp_client
        self.logger.info("✅ MCP Client đã được inject vào LLM Service")

    def _load_prompt(self, filename: str, folder: str = "prompts") -> str:
        """Load prompt content from file.
        
        Args:
            filename: Tên file cần load (VD: "IDENTITY.md", "SOUL.md")
            folder: Thư mục chứa file (VD: "memories", "prompts")
        """
        try:
            base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))
            ))
            filepath = os.path.join(base_dir, folder, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    self.logger.info(f"✅ Loaded prompt: {filename} from {folder}")
                    return content
            else:
                self.logger.warning(f"⚠️ Prompt file not found: {filepath}")
                return ""
        except Exception as e:
            self.logger.error(f"❌ Error loading prompt {filename}: {e}")
            return ""

    def _build_final_system_prompt(self, dynamic_core_prompt: str = "", skip_tools_prompt: bool = False) -> str:
        """
        Trộn lẫn Tính cách tĩnh (từ file .md) và Trí nhớ Tiềm thức (Từ Tầng 3).
        [MỚI] Bổ sung Tool Schemas từ TOOLS.md hoặc ToolManager.
        
        Args:
            dynamic_core_prompt: Hồ sơ user từ T3
            skip_tools_prompt: Nếu True, không inject TOOLS.md vào system prompt (dùng cho SmartUpdater)
        """
        parts = []

        # 0. [MỚI] Nhét Tool Schemas lên đầu tiên (có thể skip)
        # Prefer TOOLS.md file, fallback to ToolManager hardcode
        if not skip_tools_prompt:
            if self.static_tools:
                parts.append(self.static_tools)
            elif self.tool_manager:
                tool_prompt = self.tool_manager.get_tool_schemas_prompt()
                parts.append(tool_prompt)

        # 1. Nhét tính cách gốc của Bot vào trước (IDENTITY.md và SOUL.md)
        if self.static_identity:
            parts.append(f"=== NHÂN CÁCH CỦA BẠN ===\n{self.static_identity}")
        if self.static_soul:
            parts.append(f"=== HƯỚNG DẪN HỘI THOẠI ===\n{self.static_soul}")

        # 2. Nhét hồ sơ người dùng (Từ Tầng 3 gửi sang) vào sau
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
        skip_tools_prompt: bool = False,
        use_native_tools: bool = False
    ) -> Union[str, LLMResponse]:
        """
        Generate a response from the LLM based on structured messages.
        
        Args:
            messages: List of message dicts with "role" and "content" keys
            system_prompt: Dynamic core memory context from T3
            skip_tools_prompt: If True, skip TOOLS.md in system prompt (for SmartUpdater)
            use_native_tools: If True, use Native Function Calling (API Tool Calling)
        
        Returns:
            LLMResponse with content, token metadata, and tool_calls if present

        Args:
            messages: Mảng tin nhắn theo chuẩn [{"role": "user/assistant", "content": "..."}]
                      (Mảng này do MemoryManager.get_context() cung cấp).
            system_prompt: Dữ liệu Tiềm thức từ Tầng 3 (Dynamic Core Memory).
            skip_tools_prompt: Nếu True, không inject TOOLS.md vào system prompt (dùng cho SmartUpdater).

        Returns:
            LLMResponse object with content and token metadata.
            Falls back to string for backwards compatibility on errors.
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
