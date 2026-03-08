# src/services/episodic_memory/extraction/event_extractor.py
import json
import logging
import re
from typing import List, Optional

from Arize_Phoenix_tool_kit import track_general_step

from ..models import EpisodicPayload
from .prompts import EPISODIC_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class EventExtractor:
    """
    Trạm bóp nặn dữ liệu (Data Extractor).
    Biến đoạn chat thô (Snapshot) thành cấu trúc JSON chuẩn mực nhờ LLM.
    """

    def __init__(self, llm_client):
        """
        :param llm_client: Client gọi LLM của bạn (VD: LMStudioClient hoặc OpenAI client)
                           Cần có hàm sinh text tương tự `generate(prompt)`
        """
        self.llm_client = llm_client

    def _clean_json_output(self, raw_text: str) -> str:
        """Gọt rửa các ký tự thừa (markdown) do LLM sinh ra quanh chuỗi JSON."""
        cleaned = raw_text.strip()
        # Xóa ```json và ``` nếu có
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```$", "", cleaned)
        return cleaned.strip()

    def _format_chat_history(self, snapshot: List[dict]) -> str:
        """Chuyển mảng tin nhắn thành chuỗi văn bản cho Prompt đọc."""
        formatted_lines = []
        for msg in snapshot:
            # Giả sử msg là dict có dạng {"role": "user", "content": "hello"}
            # Hoặc là object MemoryEntry (msg.role, msg.content)
            role = (
                msg.get("role", "unknown")
                if isinstance(msg, dict)
                else getattr(msg, "role", "unknown")
            )
            content = (
                msg.get("content", "")
                if isinstance(msg, dict)
                else getattr(msg, "content", "")
            )
            formatted_lines.append(f"[{role.upper()}]: {content}")
        return "\n".join(formatted_lines)

    @track_general_step(
        step_name="T2_Extract_Episodic_Event", tags=["tier_2", "extraction", "llm_call"]
    )
    async def extract_event(self, snapshot: List[dict]) -> Optional[EpisodicPayload]:
        """
        Gọi LLM để trích xuất sự kiện. Trả về object Pydantic an toàn 100%.
        """
        chat_text = self._format_chat_history(snapshot)
        prompt = EPISODIC_EXTRACTION_PROMPT.format(chat_history=chat_text)

        try:
            # GỌI LLM (Thay bằng hàm thực tế của llm_client bạn đang dùng)
            # Ví dụ: response_text = await self.llm_client.agenerate(prompt)
            # Lưu ý: Cố gắng set temperature = 0.1 để output mang tính phân tích chính xác
            response_text = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}], temperature=0.1
            )

            # Gọt rửa JSON
            json_str = self._clean_json_output(response_text)

            # Parse chuỗi thành Dict
            data_dict = json.loads(json_str)

            # Dùng Pydantic (EpisodicPayload) để ÉP KIỂU VÀ VALIDATE
            # Nếu LLM thiếu trường, Pydantic sẽ văng lỗi ngay lập tức, không cho rác vào DB
            payload = EpisodicPayload(**data_dict)

            logger.info(
                f"✅ T2 Extractor: Đã trích xuất thành công sự kiện: '{payload.event_title}'"
            )
            return payload

        except json.JSONDecodeError as e:
            logger.error(
                f"❌ T2 Extractor: LLM không trả về JSON hợp lệ. Lỗi: {e}\nRaw Output: {response_text}"
            )
            return None
        except Exception as e:
            logger.error(f"❌ T2 Extractor: Lỗi Pydantic Validation hoặc LLM Call: {e}")
            return None
