"""Base abstract class for LLM services."""

import abc
import logging
import os
import re
from typing import Dict, List, Optional

from langsmith import traceable


class BaseLLMService(abc.ABC):
    """
    Abstract base class defining the common interface for all LLM services.
    Đã được nâng cấp để hỗ trợ kiến trúc Memory 3 Tầng (List of Dicts) và Tracing.
    """

    def __init__(self):
        self.session = None
        self.logger = logging.getLogger(f"discord_bot.{self.__class__.__name__}")

        # Vẫn giữ lại việc load file tính cách gốc (Static Persona)
        # File này sẽ làm nền tảng, còn Core Memory (T3) sẽ bổ sung phần Dynamic Persona
        self.static_personality = self._load_prompt("personality.txt")
        self.static_guidelines = self._load_prompt("conversation_prompt.txt")

    def _load_prompt(self, filename: str) -> str:
        """Load prompt content from file."""
        try:
            prompts_dir = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                ),
                "prompts",
            )
            filepath = os.path.join(prompts_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    self.logger.info(f"✅ Loaded prompt: {filename}")
                    return content
            else:
                self.logger.warning(f"⚠️ Prompt file not found: {filepath}")
                return ""
        except Exception as e:
            self.logger.error(f"❌ Error loading prompt {filename}: {e}")
            return ""

    def _build_final_system_prompt(self, dynamic_core_prompt: str = "") -> str:
        """
        Trộn lẫn Tính cách tĩnh (từ file) và Trí nhớ Tiềm thức (Từ Tầng 3).
        """
        parts = []

        # 1. Nhét tính cách gốc của Bot vào trước
        if self.static_personality:
            parts.append(f"=== NHÂN CÁCH CỦA BẠN ===\n{self.static_personality}")
        if self.static_guidelines:
            parts.append(f"=== HƯỚNG DẪN HỘI THOẠI ===\n{self.static_guidelines}")

        # 2. Nhét hồ sơ người dùng (Từ Tầng 3 gửi sang) vào sau
        if dynamic_core_prompt:
            parts.append(dynamic_core_prompt)

        return "\n\n".join(parts)

    # 🔴 CHỮ KÝ HÀM MỚI QUAN TRỌNG NHẤT
    @abc.abstractmethod
    @traceable(
        name="LLM_Generation", run_type="llm", tags=["llm_wrapper", "generation"]
    )
    async def generate_response(
        self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate a response from the LLM based on structured messages.

        Args:
            messages: Mảng tin nhắn theo chuẩn [{"role": "user/assistant", "content": "..."}]
                      (Mảng này do MemoryManager.get_context() cung cấp).
            system_prompt: Dữ liệu Tiềm thức từ Tầng 3 (Dynamic Core Memory).

        Returns:
            Generated response text from the LLM
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
