import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class SummaryService:
    """
    Service xử lý trí nhớ ngữ nghĩa (semantic memory) - core persona của người dùng.
    Chịu trách nhiệm quản lý, cập nhật và truy xuất bản tóm tắt hồ sơ cốt lõi của người dùng.
    """

    def __init__(self, llm_service, data_dir: str):
        self.llm_service = llm_service
        self.data_dir = data_dir
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")
        os.makedirs(self.user_summaries_dir, exist_ok=True)

    def _get_summary_file_path(self, user_id: str) -> str:
        """Lấy đường dẫn file summary cho user"""
        return os.path.join(self.user_summaries_dir, f"{user_id}_summary.txt")

    def _get_current_summary(self, user_id: str) -> str:
        """
        Lấy nội dung summary hiện tại của người dùng từ file.
        Nếu file không tồn tại, trả về chuỗi rỗng.
        """
        summary_file = self._get_summary_file_path(user_id)

        if not os.path.exists(summary_file):
            logger.debug(
                f"📄 Summary file not found for user {user_id}, returning empty string"
            )
            return ""

        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                logger.debug(
                    f"📄 Loaded summary for user {user_id}: {content[:100]}..."
                )
                return content
        except IOError as e:
            logger.error(f"Error reading summary file for {user_id}: {e}")
            return ""

    async def _update_core_persona(self, user_id: str, new_summary: str = ""):
        """
        Cập nhật core persona (summary) cho người dùng.
        Nếu new_summary được cung cấp, sử dụng nó. Nếu không, gọi LLM để tạo summary mới.
        """
        if new_summary:
            # Sử dụng summary được cung cấp
            updated_summary = new_summary
        else:
            # Gọi LLM để tạo summary mới từ episodic memory
            episodic_memory = self._load_episodic_memory(user_id)
            if not episodic_memory:
                logger.warning(
                    f"⚠️ No episodic memory found for {user_id}, cannot generate new summary"
                )
                return

            # TODO: Implement LLM call to generate summary from episodic memory
            # This would typically involve calling the LLM service with a prompt
            # that includes the episodic memory and asks for a consolidated summary
            updated_summary = await self._generate_summary_from_episodic(
                episodic_memory, user_id
            )

        if updated_summary:
            # Lưu summary mới
            summary_file = self._get_summary_file_path(user_id)
            try:
                with open(summary_file, "w", encoding="utf-8") as f:
                    f.write(updated_summary)
                logger.info(f"✅ Updated core persona for user {user_id}")
            except IOError as e:
                logger.error(f"Error writing summary file for {user_id}: {e}")

    def _load_episodic_memory(self, user_id: str) -> list:
        """Tải episodic memory của người dùng để tạo summary"""
        from .episodic_service import EpisodicService

        episodic_service = EpisodicService(self.data_dir)
        return episodic_service.get_episodic_memory(user_id, limit=50)

    async def _generate_summary_from_episodic(
        self, episodic_memory: list, user_id: str
    ) -> str:
        """
        Sinh summary mới từ episodic memory sử dụng LLM.
        Đây là placeholder - cần implement logic cụ thể với LLM service.
        """
        # TODO: Implement actual LLM call
        # For now, return a simple concatenation
        if not episodic_memory:
            return ""

        # Simple implementation - in real scenario, this would use LLM
        summaries = [event.get("summary", "") for event in episodic_memory[-5:]]
        combined = " ".join(summaries)
        return f"Core persona summary for user {user_id} based on recent interactions: {combined[:500]}"

    def get_core_persona(self, user_id: str) -> str:
        """Lấy core persona của người dùng"""
        return self._get_current_summary(user_id)

    def ensure_user_files_exist(self, user_id: str):
        """Đảm bảo file summary tồn tại cho người dùng"""
        summary_file = self._get_summary_file_path(user_id)
        if not os.path.exists(summary_file):
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write("")
            logger.debug(f"📄 Created default summary file for user {user_id}")
