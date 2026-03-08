# src/services/core_memory/smart_updater.py
import json
import logging
import re
from typing import Optional

from Arize_Phoenix_tool_kit import track_general_step

from .models import UserProfile
from .prompts import CORE_UPDATE_PROMPT
from .storage.base_core_db import BaseCoreDB

logger = logging.getLogger(__name__)


class SmartUpdater:
    """
    Người Thư Ký của Tầng 3.
    Nhận thông tin mới, nhờ LLM hợp nhất với Profile cũ và lưu lại.
    """

    def __init__(self, llm_client, storage: BaseCoreDB):
        self.llm_client = llm_client
        self.storage = storage

    def _clean_json_output(self, raw_text: str) -> str:
        """Gọt rửa các ký tự thừa (markdown) do LLM sinh ra quanh chuỗi JSON."""
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```$", "", cleaned)
        return cleaned.strip()

    @track_general_step(
        step_name="T3_Update_Core_Profile", tags=["tier_3", "core_memory", "llm_update"]
    )
    async def update_profile_with_fact(self, user_id: str, new_fact: str) -> bool:
        """
        Luồng chạy chính khi có CRITICAL_INFO từ Tầng 1.
        Trả về True nếu cập nhật thành công, False nếu LLM lỗi.
        """
        # 1. Kéo Hồ sơ cũ lên
        current_profile = await self.storage.get_profile(user_id)
        current_profile_json = current_profile.model_dump_json(indent=2)

        # 2. Chuẩn bị Prompt
        prompt = CORE_UPDATE_PROMPT.format(
            current_profile=current_profile_json, new_fact=new_fact
        )

        try:
            # 3. Gọi LLM làm việc (Temperature thấp để đảm bảo logic)
            response_text = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # Set về 0 để LLM nghiêm túc nhất có thể
            )

            # 4. Gọt rửa và Parse JSON
            json_str = self._clean_json_output(response_text)
            data_dict = json.loads(json_str)

            # 5. Ép kiểu bằng Pydantic (Hàng rào thép bảo vệ cấu trúc)
            updated_profile = UserProfile(**data_dict)

            # 6. Lưu đè xuống DB
            await self.storage.save_profile(user_id, updated_profile)

            logger.info(
                f"✅ T3 Updater: Đã cập nhật thành công Core Profile cho user {user_id}"
            )
            return True

        except json.JSONDecodeError as e:
            logger.error(f"❌ T3 Updater: LLM không trả về JSON hợp lệ. Lỗi: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ T3 Updater: Lỗi cập nhật Profile: {e}")
            return False
