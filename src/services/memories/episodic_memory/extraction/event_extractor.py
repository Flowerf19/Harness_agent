# src/services/episodic_memory/extraction/event_extractor.py
import json
import logging
import re
from typing import List, Optional

from langsmith import traceable

from src.services.llm.llm_response import LLMResponse

from ..models import EpisodicPayload
from ..prompts import EPISODIC_EXTRACTION_PROMPT

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

    @traceable(
        name="T2_Extract_Episodic_Event",
        run_type="chain",
        tags=["tier_2", "extraction", "llm_call"],
    )
    async def extract_event(self, snapshot: List[dict]) -> Optional[EpisodicPayload]:
        """
        Gọi LLM để trích xuất sự kiện. Trả về object Pydantic an toàn 100%.
        """
        chat_text = self._format_chat_history(snapshot)
        prompt = EPISODIC_EXTRACTION_PROMPT.format(chat_history=chat_text)

        try:
            # GỌI LLM
            llm_response = await self.llm_client.generate_response(
                messages=[{"role": "user", "content": prompt}]
            )

            # --- SỬA LỖI TẠI ĐÂY ---
            # Bóc tách nội dung chữ (text) ra khỏi object LLMResponse
            if isinstance(llm_response, LLMResponse):
                raw_text = llm_response.content
            else:
                raw_text = str(llm_response)
            # -----------------------

            # Gọt rửa JSON bằng đoạn text đã lấy được
            json_str = self._clean_json_output(raw_text)

            # Parse chuỗi thành Dict
            data_dict = json.loads(json_str)

            # Dùng Pydantic (EpisodicPayload) để ÉP KIỂU VÀ VALIDATE
            payload = EpisodicPayload(**data_dict)

            logger.info(
                f"✅ T2 Extractor: Đã trích xuất thành công sự kiện: '{payload.event_title}'"
            )
            return payload

        except json.JSONDecodeError as e:
            logger.error(
                f"❌ T2 Extractor: LLM không trả về JSON hợp lệ. Lỗi: {e}\nRaw Output: {raw_text}"
            )
            return None
        except Exception as e:
            logger.error(f"❌ T2 Extractor: Lỗi Pydantic Validation hoặc LLM Call: {e}")
            return None
