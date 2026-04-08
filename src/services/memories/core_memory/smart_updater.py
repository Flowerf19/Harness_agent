# src/services/memories/core_memory/smart_updater.py
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Trỏ đường dẫn tới file prompts.md nằm cùng thư mục
_PROMPTS_MD_PATH = Path(__file__).parent / "prompts.yaml"

class SmartUpdater:
    def __init__(self, llm_client, storage):
        self.llm_client = llm_client
        self.storage = storage

    def _get_core_update_prompt(self, current_profile: str, new_fact: str, context: str) -> str:
        """Đọc file markdown template và bơm biến vào"""
        try:
            with open(_PROMPTS_MD_PATH, "r", encoding="utf-8") as f:
                prompt_template = f.read()

            return prompt_template.format(
                current_profile=current_profile,
                new_fact=new_fact,
                context=context if context else "(Không có ngữ cảnh bổ sung)"
            )
        except FileNotFoundError:
            logger.error(f"❌ Không tìm thấy file prompt tại {_PROMPTS_MD_PATH}")
            raise
        except KeyError as e:
            logger.error(f"❌ Lỗi format biến trong MD (Thiếu key {e}): Vui lòng check lại file prompts.md")
            raise

    async def update_profile_with_fact(self, user_id: str, new_fact: str, context: str = "") -> bool:
        """Hàm chính để trigger việc cập nhật Trí nhớ Lõi"""
        # 1. Lấy dữ liệu cũ
        current_profile = self.storage.get_profile(user_id)
        
        # 2. Lắp ráp Prompt
        prompt = self._get_core_update_prompt(current_profile, new_fact, context)

        try:
            # 3. Giao LLM xử lý
            response = await self.llm_client.generate_response(
                messages=[{"role": "user", "content": prompt}],
            )
            
            # 4. Gọt text và lọc tag markdown
            content = response.content if hasattr(response, 'content') else str(response)
            new_markdown = content.replace("```markdown", "").replace("```", "").strip()
            
            # 5. Lưu xuống DB
            success = self.storage.save_profile(user_id, new_markdown)
            if success:
                logger.info(f"✅ Đã cập nhật T3 (Core Memory) thành công cho user {user_id}")
            return success

        except Exception as e:
            logger.error(f"❌ Lỗi khi LLM update T3: {e}")
            return False