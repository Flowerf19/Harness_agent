import asyncio
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class SummaryScheduler:
    """
    Dịch vụ lên lịch và cập nhật core persona định kỳ.
    """

    def __init__(
        self,
        llm_service,
        data_dir: str,
        relationship_service=None,
        memory_decay_service=None,
    ):
        self.llm_service = llm_service
        self.data_dir = data_dir
        self.relationship_service = relationship_service
        self.memory_decay_service = memory_decay_service

        # Đường dẫn lưu trữ
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")

        # Lock cho file I/O để ngăn chặn race condition
        self.memory_lock = asyncio.Lock()

    async def check_and_update_core_personas(self):
        """Kiểm tra và cập nhật core personas định kỳ"""
        # Cập nhật định kỳ hàng tuần hoặc khi có > 50 sự kiện mới
        try:
            # Lấy tất cả file episodic
            episodic_files = [
                f
                for f in os.listdir(self.user_summaries_dir)
                if f.endswith("_episodic.json")
            ]

            for episodic_file in episodic_files:
                user_id = episodic_file.replace("_episodic.json", "")

                # Kiểm tra điều kiện cập nhật core persona
                should_update = await self._should_update_core_persona(user_id)

                if should_update:
                    await self.update_core_persona(user_id)

        except Exception as e:
            logger.error(f"❌ Error checking core personas: {e}")

    async def _should_update_core_persona(self, user_id: str) -> bool:
        """Kiểm tra xem có nên cập nhật core persona không"""
        try:
            # Lấy file episodic memory
            episodic_file = os.path.join(
                self.user_summaries_dir, f"{user_id}_episodic.json"
            )

            if not os.path.exists(episodic_file):
                return False

            # Đếm số lượng sự kiện CHƯA được tích hợp vào persona
            async with self.memory_lock:
                with open(episodic_file, "r", encoding="utf-8") as f:
                    events = json.load(f)

            if not isinstance(events, list):
                return False

            # Lọc các sự kiện chưa được tích hợp
            events_to_process = [
                e for e in events if not e.get("integrated_to_persona", False)
            ]

            # Điều kiện: có hơn hoặc bằng 10 sự kiện chưa được tích hợp
            if len(events_to_process) >= 10:
                logger.info(
                    f"🔄 Core persona update triggered for {user_id}: {len(events_to_process)} unprocessed events"
                )
                return True

            # Ngoài ra, có thể thêm điều kiện thời gian (ví dụ: cập nhật hàng tuần)
            # Để đơn giản, tạm thời chỉ dùng điều kiện số lượng sự kiện

            return False

        except Exception as e:
            logger.error(
                f"❌ Error checking core persona update condition for {user_id}: {e}"
            )
            return False

    async def update_core_persona(self, user_id: str):
        """Cập nhật core persona cho người dùng"""
        try:
            logger.info(f"🔄 Updating core persona for user {user_id}")

            # Lấy episodic memory (sự kiện mới)
            episodic_file = os.path.join(
                self.user_summaries_dir, f"{user_id}_episodic.json"
            )

            async with self.memory_lock:
                if not os.path.exists(episodic_file):
                    logger.info(f"📝 No episodic memory to process for {user_id}")
                    # Ensure the file exists and create a basic summary if needed
                    if self.memory_decay_service:
                        self.memory_decay_service.ensure_user_files_exist(user_id)

                    # Check if we have a very basic summary that needs initialization
                    current_summary = await self._get_current_summary(user_id)
                    if not current_summary or current_summary == "":
                        # Create a basic summary for new users
                        default_summary = self._get_empty_summary()
                        await self._save_summary(user_id, default_summary)
                        logger.info(
                            f"📝 Initialized basic summary for new user {user_id}"
                        )
                    return

                with open(episodic_file, "r", encoding="utf-8") as f:
                    events = json.load(f)

            if not isinstance(events, list) or not events:
                logger.info(f"📝 No events to process for {user_id}")
                return

            # Lọc ra TẤT CẢ các sự kiện có "integrated_to_persona" == false
            events_to_process = [
                e for e in events if not e.get("integrated_to_persona", False)
            ]

            if not events_to_process:
                logger.info(f"📝 No new events to integrate for {user_id}")
                return

            # 1. Đọc persona hiện tại
            if self.memory_decay_service:
                current_persona = await self.memory_decay_service._get_semantic_memory(
                    user_id
                )
            else:
                current_persona = await self._get_semantic_memory(user_id)

            # 2. Chuẩn bị prompt cho LLM
            delta_prompt_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "prompts",
                "delta_update_prompt.txt",
            )

            if os.path.exists(delta_prompt_file):
                with open(delta_prompt_file, "r", encoding="utf-8") as f:
                    base_prompt = f.read().strip()
            else:
                # Fallback minimal prompt
                base_prompt = """Dưới đây là hồ sơ hiện tại của người dùng:
{current_persona}

Và đây là các sự kiện mới cần tích hợp:
{new_events}

Nhiệm vụ: Cập nhật hồ sơ JSON bằng cách:
1. Thêm thông tin mới chưa có
2. Cập nhật thông tin đã thay đổi
3. KHÔNG viết lại toàn bộ, chỉ trả về các THAY ĐỔI dưới dạng:
{
    "add": {"field": "value", ...},
    "update": {"field": "new_value", ...},
    "remove": ["field1", "field2"]
}

Trả về JSON hợp lệ:"""

            prompt = base_prompt.replace(
                "{current_persona}",
                json.dumps(current_persona, ensure_ascii=False, indent=2),
            ).replace(
                "{new_events}",
                json.dumps(events_to_process, ensure_ascii=False, indent=2),
            )

            # 3. Gọi LLM
            if self.memory_decay_service:
                delta = await self.memory_decay_service._call_llm(prompt, user_id)
            else:
                delta = await self._call_llm(prompt, user_id)

            if not delta:
                logger.warning(f"⚠️ Failed to generate delta for {user_id}")
                return

            # 4. Áp dụng delta vào persona hiện tại
            if self.memory_decay_service:
                updated_persona = self.memory_decay_service._apply_delta(
                    current_persona, delta
                )
            else:
                updated_persona = self._apply_delta(current_persona, delta)

            # 5. Lưu lại
            if self.memory_decay_service:
                await self.memory_decay_service._save_semantic_memory(
                    user_id, updated_persona
                )
            else:
                await self._save_semantic_memory(user_id, updated_persona)

            # Sau khi xử lý thành công, đổi cờ thành true cho các sự kiện đã xử lý
            async with self.memory_lock:
                # Đọc lại file episodic để đảm bảo dữ liệu mới nhất
                with open(episodic_file, "r", encoding="utf-8") as f:
                    all_events = json.load(f)

                # Cập nhật cờ integrated_to_persona cho các sự kiện đã xử lý
                event_ids_to_update = {
                    e.get("event_id") for e in events_to_process if e.get("event_id")
                }
                for event in all_events:
                    if event.get("event_id") in event_ids_to_update:
                        event["integrated_to_persona"] = True

                # Ghi lại file episodic.json
                with open(episodic_file, "w", encoding="utf-8") as f:
                    json.dump(all_events, f, ensure_ascii=False, indent=2)

            logger.info(
                f"✅ Core persona updated for {user_id} and {len(events_to_process)} events marked as integrated"
            )

            # Load prompt từ file external
            prompt_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "prompts",
                "summary_prompt.txt",
            )

            if os.path.exists(prompt_file):
                with open(prompt_file, "r", encoding="utf-8") as f:
                    base_prompt = f.read().strip()
            else:
                # Fallback minimal prompt
                base_prompt = "Cập nhật hồ sơ người dùng dựa trên thông tin hiện tại và sự kiện mới."

            # Get relationship info if relationship service is available
            relationship_info = ""
            if self.relationship_service:
                try:
                    user_relationships = (
                        self.relationship_service.get_user_relationships(user_id)
                    )
                    if user_relationships:
                        relationship_info = (
                            "=== THÔNG TIN MỐI QUAN HỆ ===\n"
                            + json.dumps(
                                user_relationships, ensure_ascii=False, indent=2
                            )
                        )
                    else:
                        relationship_info = "=== THÔNG TIN MỐI QUAN HỆ ===\n[Không có thông tin mối quan hệ]"
                except Exception as e:
                    logger.warning(
                        f"⚠️ Failed to get relationship info for {user_id}: {e}"
                    )
                    relationship_info = "=== THÔNG TIN MỐI QUAN HỆ ===\n[Không thể tải thông tin mối quan hệ]"
            else:
                relationship_info = "=== THÔNG TIN MỐI QUAN HỆ ===\n[Dịch vụ mối quan hệ không khả dụng]"

            # Format prompt với dữ liệu thực tế
            formatted_prompt = f"""
{base_prompt}

=== THÔNG TIN HIỆN TẠI ===
{current_summary or "[Chưa có hồ sơ]"}

{relationship_info}
=== SỰ KIỆN MỚI (10 sự kiện gần nhất) ===
{json.dumps(events_to_process[-10:], indent=2, ensure_ascii=False)}
"""

            update_prompt = formatted_prompt

            # Gọi LLM để cập nhật hồ sơ
            new_summary = await self.llm_service.generate_response(
                update_prompt, f"core_persona_update_{user_id}"
            )

            if new_summary and len(new_summary.strip()) > 50:
                # Lưu lại hồ sơ mới
                await self._save_summary(user_id, new_summary.strip())

                # Lưu lại thời gian cập nhật để theo dõi
                await self._mark_persona_updated(user_id)

                # Sau khi xử lý thành công, đổi cờ thành true cho các sự kiện đã xử lý
                async with self.memory_lock:
                    # Đọc lại file episodic để đảm bảo dữ liệu mới nhất
                    with open(episodic_file, "r", encoding="utf-8") as f:
                        all_events = json.load(f)

                    # Cập nhật cờ integrated_to_persona cho các sự kiện đã xử lý
                    event_ids_to_update = {
                        e.get("event_id")
                        for e in events_to_process
                        if e.get("event_id")
                    }
                    for event in all_events:
                        if event.get("event_id") in event_ids_to_update:
                            event["integrated_to_persona"] = True

                    # Ghi lại file episodic.json
                    with open(episodic_file, "w", encoding="utf-8") as f:
                        json.dump(all_events, f, ensure_ascii=False, indent=2)

                logger.info(
                    f"✅ Core persona updated for {user_id} and {len(events_to_process)} events marked as integrated"
                )
            else:
                logger.warning(f"⚠️ Failed to generate new summary for {user_id}")

        except Exception as e:
            logger.error(f"❌ Error updating core persona for {user_id}: {e}")

    async def _get_current_summary(self, user_id: str) -> str:
        """Lấy summary hiện tại của người dùng"""
        async with self.memory_lock:
            summary_file = os.path.join(
                self.user_summaries_dir, f"{user_id}_summary.txt"
            )

            # Ensure the file exists
            if not os.path.exists(summary_file):
                # Create the file with default content
                os.makedirs(self.user_summaries_dir, exist_ok=True)
                default_summary = self._get_empty_summary()
                with open(summary_file, "w", encoding="utf-8") as f:
                    f.write(default_summary)
                logger.debug(f"📄 Created default summary file for user {user_id}")
                return default_summary

            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"❌ Error loading summary for {user_id}: {e}")
                return ""

    async def _save_summary(self, user_id: str, summary: str):
        """Lưu summary của người dùng"""
        async with self.memory_lock:
            summary_file = os.path.join(
                self.user_summaries_dir, f"{user_id}_summary.txt"
            )

            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(summary_file), exist_ok=True)
                with open(summary_file, "w", encoding="utf-8") as f:
                    f.write(summary)
                logger.info(f"📝 Summary saved for user {user_id}")
            except Exception as e:
                logger.error(f"❌ Error saving summary for {user_id}: {e}")

    async def _mark_persona_updated(self, user_id: str):
        """Đánh dấu thời gian cập nhật core persona"""
        async with self.memory_lock:
            # Có thể lưu vào một file metadata riêng để theo dõi
            metadata_file = os.path.join(
                self.user_summaries_dir, f"{user_id}_metadata.json"
            )

            metadata = {}
            if os.path.exists(metadata_file):
                try:
                    with open(metadata_file, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                except (IOError, json.JSONDecodeError):
                    metadata = {}

            metadata["last_persona_update"] = datetime.now().isoformat()

            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(metadata_file), exist_ok=True)
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"❌ Error saving metadata for {user_id}: {e}")

    def _get_empty_summary(self) -> str:
        """Get empty summary template"""
        return """=== THÔNG TIN CƠ BẢN ===
Tên: [Không có]
Tuổi: [Không có]
Sinh nhật: [Không có]

=== SỞ THÍCH & ĐAM MÊ ===
• Công nghệ: [Không có]
• Giải trí: [Không có]
• Khác: [Không có]

=== TÍNH CÁCH & PHONG CÁCH ===
• Giao tiếp: [Không có]
• Tâm trạng: [Không có]
• Đặc điểm: [Không có]

=== MỐI QUAN HỆ VỚI NGƯỜI KHÁC ===
• Bạn bè: [Không có]
• Gia đình: [Không có]
• Đồng nghiệp: [Không có]
• Người quan trọng: [Không có]
• Ghi chú về tương tác: [Không có]

=== LỊCH SỬ TƯƠNG TÁC ===
• Chủ đề đã thảo luận: [Không có]
• Mức độ thân thiết: [Không có]
• Ghi chú đặc biệt: [Không có]

=== DỰ ÁN & MỤC TIÊU ===
• Hiện tại: [Không có]
• Kế hoạch: [Không có]"""

    # Helper methods that might be used if memory_decay_service is not available
    async def _get_semantic_memory(self, user_id: str) -> dict:
        """Lấy semantic memory (persona) hiện tại của người dùng."""
        async with self.memory_lock:
            semantic_file = os.path.join(
                self.user_summaries_dir, f"{user_id}_semantic_memory.json"
            )

            if not os.path.exists(semantic_file):
                # Tạo persona mặc định
                default_persona = {
                    "user_id": user_id,
                    "profile": {
                        "name": "",
                        "preferences": [],
                        "facts": [],
                        "relationships": [],
                    },
                    "last_updated": datetime.now().isoformat(),
                    "version": 1,
                }
                return default_persona

            try:
                with open(semantic_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Error loading semantic memory for {user_id}: {e}")
                return {
                    "user_id": user_id,
                    "profile": {
                        "name": "",
                        "preferences": [],
                        "facts": [],
                        "relationships": [],
                    },
                    "last_updated": datetime.now().isoformat(),
                    "version": 1,
                }

    async def _save_semantic_memory(self, user_id: str, persona: dict):
        """Lưu semantic memory (persona) của người dùng."""
        async with self.memory_lock:
            semantic_file = os.path.join(
                self.user_summaries_dir, f"{user_id}_semantic_memory.json"
            )

            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(semantic_file), exist_ok=True)
                persona["last_updated"] = datetime.now().isoformat()
                with open(semantic_file, "w", encoding="utf-8") as f:
                    json.dump(persona, f, ensure_ascii=False, indent=2)
                logger.info(f"📝 Semantic memory saved for user {user_id}")
            except Exception as e:
                logger.error(f"❌ Error saving semantic memory for {user_id}: {e}")

    async def _call_llm(self, prompt: str, user_id: str = None) -> dict:
        """Gọi LLM và parse kết quả."""
        try:
            response = await self.llm_service.generate_response(
                prompt,
                f"delta_update_{user_id}" if user_id else "delta_update",
                response_format={"type": "json_object"},
            )
            if response:
                return self._parse_llm_response(response)
            return None
        except Exception as e:
            logger.error(f"❌ Error calling LLM: {e}")
            return None

    def _parse_llm_response(self, response: str) -> dict:
        """Parse JSON response từ LLM."""
        import json
        import re

        try:
            # Nếu LLM trả về JSON thuần túy
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback: tìm JSON trong response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
        logger.error(f"Failed to parse LLM response as JSON: {response[:200]}")
        return None

    def _apply_delta(self, current: dict, delta: dict) -> dict:
        """Áp dụng delta vào persona hiện tại."""
        result = current.copy()

        # Thêm mới
        if "add" in delta:
            for key, value in delta["add"].items():
                if key not in result:
                    result[key] = value
                elif isinstance(result[key], list) and isinstance(value, list):
                    result[key].extend(value)
                elif isinstance(result[key], dict) and isinstance(value, dict):
                    result[key].update(value)

        # Cập nhật
        if "update" in delta:
            for key, value in delta["update"].items():
                result[key] = value

        # Xóa
        if "remove" in delta:
            for key in delta["remove"]:
                result.pop(key, None)

        return result
