# src/services/memories/core_memory/smart_updater.py
import logging
import re
import json
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

    def _clean_llm_output(self, content: str) -> str:
        """
        Dọn dẹp output từ LLM - loại bỏ code block markers và whitespace thừa.
        (Safety net - với skip_tools_prompt=True, LLM không nên output JSON tool calls)
        """
        # 1. Xóa markdown code block markers (LLM đôi khi wrap output trong ```markdown)
        content = content.replace("```markdown", "").replace("```json", "").replace("```", "").strip()
        
        # 2. Xóa pattern "json" standalone (language identifier)
        content = re.sub(r'^json\s*$', "", content, flags=re.MULTILINE)
        
        # 3. Clean up whitespace
        content = re.sub(r'\n\s*\n+', '\n', content).strip()
        
        return content

    async def update_profile_with_fact(self, user_id: str, new_fact: str, context: str = "") -> bool:
        """Hàm chính để trigger việc cập nhật Trí nhớ Lõi"""
        # 1. Lấy dữ liệu cũ
        current_profile = self.storage.get_profile(user_id)
        
        # 2. Lắp ráp Prompt
        prompt = self._get_core_update_prompt(current_profile, new_fact, context)

        try:
            # 3. Giao LLM xử lý (skip_tools_prompt=True để LLM không output tool call)
            response = await self.llm_client.generate_response(
                messages=[{"role": "user", "content": prompt}],
                skip_tools_prompt=True,
            )
            
            # 4. Gọt text và lọc tag markdown + JSON
            content = response.content if hasattr(response, 'content') else str(response)
            new_markdown = self._clean_llm_output(content)
            
            # 5. Validate: Nếu output rỗng hoặc vẫn là JSON -> FAIL
            if not new_markdown or new_markdown.startswith('{') or '"tool"' in new_markdown or new_markdown.startswith('json'):
                logger.error(f"❌ SmartUpdater: LLM output không hợp lệ (JSON hoặc rỗng): {content[:200]}")
                return False
            
            # 6. Lưu xuống DB
            success = self.storage.save_profile(user_id, new_markdown)
            if success:
                logger.info(f"✅ Đã cập nhật T3 (Core Memory) thành công cho user {user_id}")
            return success

        except Exception as e:
            logger.error(f"❌ Lỗi khi LLM update T3: {e}")
            return False