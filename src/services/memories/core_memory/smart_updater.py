import logging
import re
from pathlib import Path

import yaml
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

    def _clean_yaml_output(self, raw_text: str) -> str:
        """Trích xuất lõi YAML từ markdown của LLM"""
        match = re.search(r"```yaml\n(.*?)\n```", raw_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1)

        # Nếu LLM quên bọc markdown tag, xóa các backtick thừa nếu có
        return raw_text.replace("```yaml", "").replace("```", "").strip()

    def _fix_yaml_string_issues(self, yaml_str: str) -> str:
        """
        Sửa các lỗi YAML phổ biến do LLM tạo ra:
        1. Unclosed quotes - dấu ngoặc kép mở nhưng không đóng
        2. Multiline strings trong quotes không đúng format
        3. Unicode characters gây lỗi parse
        4. Truncated YAML (LLM bị cắt do token limit)
        """
        # 1. Lọc các Unicode control characters gây lỗi (ngoại trừ \n, \t)
        yaml_str = self._sanitize_unicode(yaml_str)

        # 2. Xử lý truncated YAML - tìm cấu trúc YAML hợp lệ
        yaml_str = self._fix_truncated_yaml(yaml_str)

        lines = yaml_str.split("\n")
        fixed_lines = []

        for line in lines:
            # Đếm số dấu ngoặc kép trong dòng
            quote_count = line.count('"')

            # Nếu số lẻ -> có unclosed quote
            if quote_count % 2 == 1:
                # Kiểm tra xem dòng có kết thúc bằng chữ cái/number không (có thể thiếu đóng quote)
                stripped = line.rstrip()
                if stripped and not stripped.endswith('"'):
                    # Thêm dấu ngoặc kép đóng vào cuối
                    line = stripped + '"'

            fixed_lines.append(line)

        return "\n".join(fixed_lines)

    def _sanitize_unicode(self, text: str) -> str:
        """
        Loại bỏ các Unicode control characters gây lỗi YAML parser.
        Giữ lại: \n (newline), \t (tab)
        """
        import unicodedata

        result = []
        for char in text:
            # Giữ lại các ký tự in được và whitespace thông thường
            if char in ("\n", "\t", "\r"):
                result.append(char)
            elif unicodedata.category(char) not in ("Cc", "Cf", "Cs", "Co", "Cn"):
                # Cc = Control, Cf = Format, Cs = Surrogate, Co = Private Use, Cn = Unassigned
                result.append(char)
            # Bỏ qua các control characters khác
        return "".join(result)

    def _fix_truncated_yaml(self, yaml_str: str) -> str:
        """
        Cố gắng sửa YAML bị cắt giữa chừng do LLM token limit.
        Tìm block YAML hợp lệ cuối cùng và đóng các cấu trúc chưa hoàn chỉnh.
        """
        lines = yaml_str.strip().split("\n")
        if not lines:
            return yaml_str

        # Đếm số dấu ngoặc và bracket để detect truncated structures
        open_braces = yaml_str.count("[") - yaml_str.count("]")
        open_brackets = yaml_str.count("{") - yaml_str.count("}")

        # Nếu có unclosed brackets/braces -> có thể là truncated JSON-like YAML
        # Thử đóng chúng
        result = yaml_str.rstrip()
        if open_braces > 0:
            result += "]" * open_braces
        if open_brackets > 0:
            result += "}" * open_brackets

        # Nếu dòng cuối có vẻ bị cắt (không kết thúc properly)
        last_line = lines[-1].strip() if lines else ""
        if last_line and not last_line.endswith(('"', "'", "]", "}", ":", "- ")):
            # Kiểm tra nếu dòng cuối là một list item bị cắt
            if last_line.startswith("- ") and last_line.count('"') % 2 == 1:
                # Đóng quote cho list item
                result = result.rstrip() + '"'

        return result

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
            # 3. Gọi LLM làm việc (Nên bỏ temperature vào đây như tớ đã hướng dẫn ở bước trước)
            response = await self.llm_client.generate_response(
                messages=[{"role": "user", "content": prompt}],
            )

            # 4. Gọt rửa và Parse YAML thay vì JSON
            yaml_str = self._clean_yaml_output(response.content)
            # 4.1. Sửa các lỗi YAML phổ biến do LLM tạo ra
            yaml_str = self._fix_yaml_string_issues(yaml_str)
            data_dict = yaml.safe_load(yaml_str)

            if not isinstance(data_dict, dict):
                logger.error(
                    "❌ T3 Updater: Dữ liệu YAML trả về không phải là Dictionary."
                )
                return False

            # 5. Ép kiểu bằng Pydantic (Hàng rào thép bảo vệ cấu trúc)
            updated_profile = UserProfile(**data_dict)

            # 6. Lưu đè xuống DB
            await self.storage.save_profile(user_id, updated_profile)

            logger.info(
                f"✅ T3 Updater: Đã cập nhật thành công Core Profile bằng YAML cho user {user_id}"
            )
            return True

        except yaml.YAMLError as e:
            logger.error(f"❌ T3 Updater: Lỗi parse YAML từ LLM response: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ T3 Updater: Lỗi không xác định khi update profile: {e}")
            return False
