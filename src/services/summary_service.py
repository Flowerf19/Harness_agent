import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SummaryService:
    def _parse_summary_fields(self, summary_text: str) -> dict:
        """Parse summary text thành dict các trường chính (theo format chuẩn)."""
        import re

        fields = [
            ("Tên", r"Tên:\s*(.*)"),
            ("Tuổi", r"Tuổi:\s*(.*)"),
            ("Sinh nhật", r"Sinh nhật:\s*(.*)"),
            ("Công nghệ", r"Công nghệ:\s*(.*)"),
            ("Giải trí", r"Giải trí:\s*(.*)"),
            ("Khác", r"Khác:\s*(.*)"),
            ("Giao tiếp", r"Giao tiếp:\s*(.*)"),
            ("Tâm trạng", r"Tâm trạng:\s*(.*)"),
            ("Đặc điểm", r"Đặc điểm:\s*(.*)"),
            ("Bạn bè", r"Bạn bè:\s*(.*)"),
            ("Gia đình", r"Gia đình:\s*(.*)"),
            ("Đồng nghiệp", r"Đồng nghiệp:\s*(.*)"),
            ("Người quan trọng", r"Người quan trọng:\s*(.*)"),
            ("Ghi chú về tương tác", r"Ghi chú về tương tác:\s*(.*)"),
            ("Chủ đề đã thảo luận", r"Chủ đề đã thảo luận:\s*(.*)"),
            ("Mức độ thân thiết", r"Mức độ thân thiết:\s*(.*)"),
            ("Ghi chú đặc biệt", r"Ghi chú đặc biệt:\s*(.*)"),
            ("Hiện tại", r"Hiện tại:\s*(.*)"),
            ("Kế hoạch", r"Kế hoạch:\s*(.*)"),
        ]
        result = {}
        for key, pattern in fields:
            m = re.search(pattern, summary_text, re.MULTILINE)
            if m:
                value = m.group(1).strip()
                # Xử lý giá trị đặc biệt như "None" hoặc "[Không có]"
                if value.lower() == "none" or "[không có]" in value.lower():
                    result[key] = "[Không có]"
                else:
                    result[key] = value
            else:
                result[key] = "[Không có]"
        return result

    def _merge_summary_fields(self, old_summary: str, new_summary: str) -> str:
        """Chỉ cập nhật trường có thông tin mới, giữ lại trường cũ nếu trường mới rỗng hoặc 'Không có'."""
        # Parse fields
        old_fields = self._parse_summary_fields(old_summary or "")
        new_fields = self._parse_summary_fields(new_summary or "")
        # Nếu trường mới rỗng hoặc 'Không có' thì giữ trường cũ
        merged = {}
        for k in old_fields:
            v_new = new_fields.get(k, "[Không có]")
            # Nếu trường mới có thông tin (không phải "[Không có]" hoặc "None"), thì cập nhật
            if v_new and v_new != "[Không có]" and v_new.lower() != "none":
                merged[k] = v_new
            else:
                # Nếu trường mới không có thông tin, giữ lại trường cũ (trừ khi trường cũ cũng là "[Không có]")
                old_val = old_fields.get(k, "[Không có]")
                merged[k] = old_val if old_val != "[Không có]" else "[Không có]"
        # Build summary text lại theo format chuẩn
        # (Có thể cần chỉnh lại cho đúng format từng phần)
        lines = []
        lines.append("=== THÔNG TIN CƠ BẢN ===")
        lines.append(f"Tên: {merged['Tên']}")
        lines.append(f"Tuổi: {merged['Tuổi']}")
        lines.append(f"Sinh nhật: {merged['Sinh nhật']}")
        lines.append("=== SỞ THÍCH & ĐAM MÊ ===")
        lines.append(f"• Công nghệ: {merged['Công nghệ']}")
        lines.append(f"• Giải trí: {merged['Giải trí']}")
        lines.append(f"• Khác: {merged['Khác']}")
        lines.append("=== TÍNH CÁCH & PHONG CÁCH ===")
        lines.append(f"• Giao tiếp: {merged['Giao tiếp']}")
        lines.append(f"• Tâm trạng: {merged['Tâm trạng']}")
        lines.append(f"• Đặc điểm: {merged['Đặc điểm']}")
        lines.append("=== MỐI QUAN HỆ VỚI NGƯỜI KHÁC ===")
        lines.append(f"• Bạn bè: {merged['Bạn bè']}")
        lines.append(f"• Gia đình: {merged['Gia đình']}")
        lines.append(f"• Đồng nghiệp: {merged['Đồng nghiệp']}")
        lines.append(f"• Người quan trọng: {merged['Người quan trọng']}")
        lines.append(f"• Ghi chú về tương tác: {merged['Ghi chú về tương tác']}")
        lines.append("=== LỊCH SỬ TƯƠNG TÁC ===")
        lines.append(f"• Chủ đề đã thảo luận: {merged['Chủ đề đã thảo luận']}")
        lines.append(f"• Mức độ thân thiết: {merged['Mức độ thân thiết']}")
        lines.append(f"• Ghi chú đặc biệt: {merged['Ghi chú đặc biệt']}")
        lines.append("=== DỰ ÁN & MỤC TIÊU ===")
        lines.append(f"• Hiện tại: {merged['Hiện tại']}")
        lines.append(f"• Kế hoạch: {merged['Kế hoạch']}")
        return "\n".join(lines)

    def __init__(self, llm_service, prompts_dir: str, config_dir: str):
        self.llm_service = llm_service
        self.prompts_dir = prompts_dir
        self.config_dir = config_dir

        # FIXED: Use absolute path for summaries directory
        base_dir = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )  # Go to src/
        self.summaries_dir = os.path.join(base_dir, "data", "user_summaries")

        logger.info(f"📁 SummaryService using directory: {self.summaries_dir}")

        # Ensure directories exist
        os.makedirs(self.summaries_dir, exist_ok=True)
        os.makedirs(self.prompts_dir, exist_ok=True)
        os.makedirs(self.config_dir, exist_ok=True)

        # Tracking for updates
        self._last_update = {}

    def get_user_history(self, user_id: str) -> List[Dict]:
        """FIXED: Get user conversation history với absolute path"""
        history_file = os.path.join(self.summaries_dir, f"{user_id}_history.json")

        logger.debug(f"🔍 Looking for history file: {history_file}")

        # Check if file exists with absolute path
        if not os.path.exists(history_file):
            logger.info(f"📝 History file not found: {history_file}")
            return []

        try:
            # Check file size first
            file_size = os.path.getsize(history_file)
            logger.debug(f"📄 History file size: {file_size} bytes")

            if file_size == 0:
                logger.warning(f"📝 History file is empty: {history_file}")
                return []

            with open(history_file, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug(f"📄 Raw file content length: {len(content)} chars")

                if not content.strip():
                    logger.warning(f"📝 History file has no content: {history_file}")
                    return []

                # Parse JSON
                history = json.loads(content)

                if not isinstance(history, list):
                    logger.error(
                        f"📝 History file format invalid (not a list): {history_file}"
                    )
                    return []

                logger.info(
                    f"✅ Successfully loaded {len(history)} messages for user {user_id}"
                )
                return history

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode error for {user_id}: {e}")
            logger.error(
                f"❌ File content preview: {content[:200] if 'content' in locals() else 'N/A'}"
            )
            return []
        except Exception as e:
            logger.error(f"❌ Error loading history for {user_id}: {e}")
            return []

    def get_user_summary(self, user_id: str) -> str:
        """Get user summary với absolute path và better caching"""
        summary_file = os.path.join(self.summaries_dir, f"{user_id}_summary.txt")

        if not os.path.exists(summary_file):
            logger.debug(f"📝 Summary file not found: {summary_file}")
            return ""

        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if content and len(content) > 10:
                logger.debug(f"📖 Loaded summary for {user_id}: {len(content)} chars")
                return content
            else:
                logger.debug(f"📝 Empty summary for {user_id}")
                return ""

        except Exception as e:
            logger.error(f"Error loading summary for {user_id}: {e}")
            return ""

    def save_user_summary(self, user_id: str, summary: str):
        """Save user summary với absolute path"""
        summary_file = os.path.join(self.summaries_dir, f"{user_id}_summary.txt")

        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(summary_file), exist_ok=True)

            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(summary.strip())
            logger.info(f"📝 Summary saved for user {user_id} at: {summary_file}")
        except Exception as e:
            logger.error(f"Error saving summary for {user_id}: {e}")

    def should_update_summary(
        self, user_id: str, message_content: str, current_summary: str
    ) -> bool:
        """REALTIME: Enhanced check for immediate summary updates
        Note: Semantic understanding of important information is handled by LLM
        """
        message_content.lower()

        # FORCE UPDATE cho template summary
        if self._is_template_summary(current_summary):
            logger.info(f"🔄 Template summary detected for {user_id} - FORCE UPDATE")
            return True

        # REALTIME: Tăng tần suất update
        import random

        return random.random() < 0.3  # Tăng từ 10% lên 30%

    def _is_template_summary(self, summary: str) -> bool:
        """Check if summary is a template (has [Không có] or None entries)"""
        if not summary:
            return True

        # Đếm số lượng trường trống hoặc template
        empty_field_patterns = [
            r"Tên:\s*\[Không có\]",
            r"Tuổi:\s*\[Không có\]",
            r"Sinh nhật:\s*\[Không có\]",
            r"Công nghệ:\s*\[Không có\]",
            r"Giải trí:\s*\[Không có\]",
            r"Khác:\s*\[Không có\]",
            r"Giao tiếp:\s*\[Không có\]",
            r"Tâm trạng:\s*\[Không có\]",
            r"Đặc điểm:\s*\[Không có\]",
            r"Bạn bè:\s*\[Không có\]",
            r"Gia đình:\s*\[Không có\]",
            r"Đồng nghiệp:\s*\[Không có\]",
            r"Người quan trọng:\s*\[Không có\]",
            r"Ghi chú về tương tác:\s*\[Không có\]",
            r"Chủ đề đã thảo luận:\s*\[Không có\]",
            r"Mức độ thân thiết:\s*\[Không có\]",
            r"Ghi chú đặc biệt:\s*\[Không có\]",
            r"Hiện tại:\s*\[Không có\]",
            r"Kế hoạch:\s*\[Không có\]",
            # Các trường với giá trị "None"
            r"Tên:\s*None",
            r"Tuổi:\s*None",
            r"Sinh nhật:\s*None",
            r"Công nghệ:\s*None",
            r"Giải trí:\s*None",
            r"Khác:\s*None",
            r"Giao tiếp:\s*None",
            r"Tâm trạng:\s*None",
            r"Đặc điểm:\s*None",
            r"Bạn bè:\s*None",
            r"Gia đình:\s*None",
            r"Đồng nghiệp:\s*None",
            r"Người quan trọng:\s*None",
            r"Ghi chú về tương tác:\s*None",
            r"Chủ đề đã thảo luận:\s*None",
            r"Mức độ thân thiết:\s*None",
            r"Ghi chú đặc biệt:\s*None",
            r"Hiện tại:\s*None",
            r"Kế hoạch:\s*None",
        ]

        # Đếm số lượng trường trống trong summary
        import re

        empty_count = 0
        for pattern in empty_field_patterns:
            matches = re.findall(pattern, summary, re.IGNORECASE)
            empty_count += len(matches)

        # Nếu có >= 15 trường trống/template trên tổng số 19 trường, thì счит là template
        if empty_count >= 15:
            logger.info(
                f"🔍 Template summary detected ({empty_count} empty/placeholder fields out of 19)"
            )
            return True

        return False

    async def update_summary_smart(self, user_id: str) -> Optional[str]:
        """REALTIME: Force update để đảm bảo summary được cập nhật ngay"""
        try:
            # Get history from our own method with better logging
            logger.info(f"🔄 Starting REALTIME summary update for user {user_id}")
            history = self.get_user_history(user_id)

            logger.info(
                f"📊 History stats for user {user_id}: {len(history)} total messages"
            )

            # REALTIME: Giảm threshold để update nhanh hơn
            if len(history) < 4:  # Giảm từ 6 xuống 4
                logger.info(
                    f"📝 User {user_id}: Not enough messages ({len(history)}/4) for summary"
                )
                return None

            # Check content diversity
            user_messages = [msg for msg in history if msg.get("role") == "user"]
            unique_content = set(
                msg.get("content", "").strip().lower() for msg in user_messages
            )

            logger.info(
                f"📊 User {user_id}: {len(user_messages)} user messages, {len(unique_content)} unique"
            )

            if len(unique_content) < 2:  # Giữ nguyên 2
                logger.info(
                    f"📝 User {user_id}: Not enough diverse content for summary"
                )
                return None

            # Check content quality
            total_chars = sum(len(msg.get("content", "")) for msg in user_messages)
            logger.info(f"📊 User {user_id}: {total_chars} total characters")

            if total_chars < 15:  # Giảm từ 20 xuống 15
                logger.info(
                    f"📝 User {user_id}: Content too short for meaningful summary"
                )
                return None

            # Load existing summary
            existing_summary = self.get_user_summary(user_id)

            # REALTIME: Check if force update needed
            is_template = self._is_template_summary(existing_summary)

            if is_template:
                logger.info(
                    f"🔄 TEMPLATE DETECTED for user {user_id}: Force updating..."
                )
            else:
                # REALTIME: Giảm interval để update thường xuyên hơn
                current_msg_count = len(history)
                last_update_count = self._last_update.get(user_id, 0)

                if (
                    current_msg_count - last_update_count < 1 and existing_summary
                ):  # Giảm từ 2 xuống 1
                    logger.debug(
                        f"📝 User {user_id}: Recent update ({current_msg_count - last_update_count} new messages)"
                    )
                    return existing_summary

            # Prepare conversation for summary
            recent_history = history[-20:]  # Tăng lên 20 messages để có context đầy đủ
            conversation_text = "\n".join(
                [
                    f"{msg['role']}: {msg['content']}"
                    for msg in recent_history
                    if msg.get("content")  # Filter empty content
                ]
            )

            logger.info(
                f"📝 User {user_id}: Generating summary from {len(recent_history)} recent messages"
            )

            # Build summary prompt
            summary_prompt_template = self._load_summary_prompt()

            # REALTIME: Enhanced prompt để force tạo summary mới
            summary_prompt = f"""{summary_prompt_template}

QUAN TRỌNG: Tạo summary hoàn toàn mới dựa trên cuộc hội thoại thực tế.
KHÔNG sử dụng "[Không có]" - chỉ ghi thông tin có thật.

Cuộc hội thoại cần phân tích:
{conversation_text}

Hãy tạo tóm tắt chi tiết và chính xác:"""

            # Generate summary
            logger.info(
                f"🤖 Sending REALTIME summary request to LLM for user {user_id}"
            )
            new_summary = await self.llm_service.generate_response(
                summary_prompt, user_id
            )

            # Thêm cơ chế fallback nếu LLM không khả dụng
            if (
                new_summary is None
                or "error" in new_summary.lower()
                or len(new_summary.strip()) < 15
            ):
                logger.warning(
                    f"⚠️ Generated summary too short or error for user {user_id}: '{new_summary}'"
                )
                # Trả về summary hiện tại nếu không thể tạo mới
                return (
                    existing_summary if existing_summary and not is_template else None
                )

            # Validate summary is not template-like
            if self._is_template_summary(new_summary):
                logger.warning(
                    f"⚠️ Generated summary is still template-like for user {user_id}"
                )
                return existing_summary if not is_template else None

            # Merge summary fields: chỉ update trường có thông tin mới, giữ lại trường cũ nếu trường mới rỗng/không có
            merged_summary = self._merge_summary_fields(
                existing_summary, new_summary.strip()
            )
            self.save_user_summary(user_id, merged_summary)

            # Update tracking
            self._last_update[user_id] = len(history)

            logger.info(
                f"✅ REALTIME Summary updated for user {user_id} ({len(history)} total messages)"
            )
            logger.info(f"📄 New summary preview: {new_summary.strip()[:100]}...")
            return new_summary.strip()

        except Exception as e:
            logger.error(f"❌ Error updating summary for {user_id}: {e}", exc_info=True)
            # Trả về summary hiện tại nếu có lỗi xảy ra
            existing_summary = self.get_user_summary(user_id)
            return existing_summary if existing_summary else None

    def _load_summary_prompt(self) -> str:
        """Load summary prompt from file"""
        prompt_file = os.path.join(self.prompts_dir, "summary_prompt.txt")

        if not os.path.exists(prompt_file):
            return "Phân tích cuộc hội thoại và tạo tóm tắt thông tin người dùng."

        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading summary prompt: {e}")
            return "Phân tích cuộc hội thoại và tạo tóm tắt thông tin người dùng."

    def clear_user_summary(self, user_id: str):
        """Clear user summary"""
        summary_file = os.path.join(self.summaries_dir, f"{user_id}_summary.txt")

        if os.path.exists(summary_file):
            try:
                os.remove(summary_file)
                logger.info(f"Summary cleared for user {user_id}")
            except Exception as e:
                logger.error(f"Error clearing summary for {user_id}: {e}")
