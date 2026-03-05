"""Base abstract class for LLM services."""

import abc
import logging
import os
import re
from typing import List, Optional


class BaseLLMService(abc.ABC):
    """Abstract base class defining the common interface for all LLM services.

    This class provides a standardized interface that all LLM wrapper implementations
    must follow, ensuring consistency across different LLM providers while allowing
    for provider-specific implementations.
    """

    def __init__(self):
        """Initialize the LLM service with common attributes."""
        self.session = None
        self.logger = logging.getLogger(f"discord_bot.{self.__class__.__name__}")

        # Load common prompts
        self.personality_prompt = self._load_prompt("personality.txt")
        self.conversation_prompt = self._load_prompt("conversation_prompt.txt")

    def _load_prompt(self, filename: str) -> str:
        """Load prompt content from file.

        Args:
            filename: Name of the prompt file to load

        Returns:
            Content of the prompt file as string, or empty string if file not found
        """
        try:
            prompts_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data",
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

    @abc.abstractmethod
    async def generate_response(
        self, prompt: str, user_id: Optional[str] = None, conversation_context: str = ""
    ) -> str:
        """Generate a response from the LLM based on the given prompt and context.

        Args:
            prompt: The user's input prompt
            user_id: Optional user ID for personalization
            conversation_context: Optional conversation history context

        Returns:
            Generated response text from the LLM
        """
        pass

    def _build_system_prompt(self) -> str:
        """Build system prompt from personality and conversation guidelines.

        This method combines the personality prompt and conversation guidelines
        into a single system prompt that can be used by the LLM.

        Returns:
            Combined system prompt string
        """
        parts = []

        if self.personality_prompt:
            parts.append(f"=== NHÂN CÁCH ===\n{self.personality_prompt}")

        if self.conversation_prompt:
            parts.append(f"=== HƯỚNG DẪN HỘI THOẠI ===\n{self.conversation_prompt}")

        return "\n\n".join(parts)

    def _build_user_message(
        self,
        user_message: str,
        user_id: Optional[str] = None,
        conversation_context: str = "",
    ) -> str:
        """Build user message with context for LLM input.

        This method formats the user message with conversation context and instructions
        in a standardized way that works well with most LLMs.

        Args:
            user_message: The raw user message
            user_id: Optional user ID (for potential future use)
            conversation_context: Optional conversation history

        Returns:
            Formatted user message with context
        """
        prompt_parts = []

        # Add conversation context if available
        if conversation_context:
            prompt_parts.append(
                f"=== LỊCH SỬ HỘI THOẠI GẦN ĐÂY ===\n{conversation_context}"
            )

        # Add user message
        prompt_parts.append(f"=== TIN NHẮN NGƯỜI DÙNG ===\n{user_message}")

        # Add instructions
        prompt_parts.append(
            "=== NHIỆM VỤ ===\nHãy trả lời tin nhắn người dùng theo đúng nhân cách và hướng dẫn trên. Nếu có lịch sử hội thoại, hãy tham khảo để trả lời phù hợp với ngữ cảnh."
        )

        user_message_content = "\n\n".join(prompt_parts)
        self.logger.debug(
            f"Built user message with context: {len(user_message_content)} chars"
        )
        return user_message_content

    async def close(self) -> None:
        """Close the HTTP session if it exists.

        This method should be called when the service is no longer needed
        to properly clean up resources.
        """
        if self.session:
            await self.session.close()

    def split_response_into_parts(self, response: str) -> List[str]:
        """Split response into multiple natural parts for sequential sending.

        This method splits a long response into smaller, natural segments that
        can be sent sequentially to avoid Discord's message length limits.

        Args:
            response: The full response text from the LLM

        Returns:
            List of response segments
        """
        response = response.strip()

        if not response:
            return []

        # Simple approach: split by newlines first to preserve line breaks
        lines = response.split("\n")

        # Then for very long lines, optionally split by sentences
        result = []
        for line in lines:
            if len(line) <= 2000:  # Discord message limit
                if line.strip():  # Only add non-empty lines
                    result.append(line)
            else:
                # For very long lines, split by natural breaks (sentences, questions, exclamations)
                parts = re.split(r"([.!?]+\s*)", line)

                # Combine sentence with its punctuation
                combined_parts = []
                for i in range(0, len(parts), 2):
                    if i + 1 < len(parts):
                        part = (parts[i] + parts[i + 1]).strip()
                    else:
                        part = parts[i].strip()

                    if part:
                        combined_parts.append(part)

                # Add the split parts
                result.extend(combined_parts)

        return result
