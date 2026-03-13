import json
import logging
import re
from pathlib import Path

from langsmith import traceable

from .models import UserProfile
from .storage.base_core_db import BaseCoreDB

logger = logging.getLogger(__name__)

# Đường dẫn đến file YAML chứa prompts
_PROMPTS_YAML_PATH = Path(__file__).parent / "prompts.yaml"


def get_core_update_prompt(current_profile: str, context: str, new_fact: str) -> str:
    """
    Đọc thẳng template từ file YAML và điền biến.
    Mọi tiêu đề [D], [E], [T] đều phải được định nghĩa sẵn trong file YAML.
    """
    try:
        with open(_PROMPTS_YAML_PATH, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        return prompt_template.format(
            current_profile=current_profile, context=context, new_fact=new_fact
        )
    except FileNotFoundError:
        logger.error(f"❌ Không tìm thấy file prompt tại {_PROMPTS_YAML_PATH}")
        raise
    except KeyError as e:
        logger.error(
            f"❌ Lỗi format biến trong YAML (Thiếu key hoặc quên bọc {{}} cho JSON): {e}"
        )
        raise


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

    @traceable(
        name="T3_Update_Core_Profile",
        run_type="chain",
        tags=["tier_3", "core_memory", "llm_update"],
    )
    async def update_profile_with_fact(
        self, user_id: str, new_fact: str, context: str = ""
    ) -> bool:
        """
        Luồng chạy chính khi có CRITICAL_INFO từ Tầng 1.
        Trả về True nếu cập nhật thành công, False nếu LLM lỗi.

        Args:
            user_id: ID của user
            new_fact: Thông tin mới cần cập nhật
            context: Ngữ cảnh hội thoại (các tin nhắn trước đó) giúp LLM hiểu rõ hơn
        """
        # 1. Kéo Hồ sơ cũ lên
        current_profile = await self.storage.get_profile(user_id)
        current_profile_json = current_profile.model_dump_json(indent=2)

        # 2. Chuẩn bị Prompt từ YAML
        prompt = get_core_update_prompt(
            current_profile=current_profile_json,
            new_fact=new_fact,
            context=context if context else "(Không có ngữ cảnh bổ sung)",
        )

        try:
            # 3. Gọi LLM làm việc (Temperature thấp để đảm bảo logic)
            response = await self.llm_client.generate_response(
                messages=[{"role": "user", "content": prompt}],
            )

            # 4. Gọt rửa và Parse JSON
            json_str = self._clean_json_output(response.content)
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
            logger.error(f"❌ T3 Updater: Lỗi parse JSON từ LLM response: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ T3 Updater: Lỗi không xác định khi update profile: {e}")
            return False
