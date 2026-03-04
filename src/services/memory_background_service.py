import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from services.activity_monitor import ActivityMonitor

logger = logging.getLogger(__name__)


class MemoryBackgroundService:
    """
    Dịch vụ chạy nền để xử lý cập nhật Episodic Memory và Core Persona
    """

    def __init__(
        self,
        llm_service,
        data_dir: str,
        relationship_service=None,
        working_memory_service=None,
    ):
        self.llm_service = llm_service
        self.data_dir = data_dir
        self.relationship_service = (
            relationship_service  # Thêm relationship service để tích hợp
        )
        self.working_memory_service = (
            working_memory_service  # Thêm working memory service
        )

        # Đường dẫn lưu trữ
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")

        # Tạo activity monitor
        self.activity_monitor = ActivityMonitor()

        # Cài đặt callback cho các trigger
        self.activity_monitor.add_message_count_callback(self._on_message_count_trigger)
        self.activity_monitor.add_timeout_callback(self._on_timeout_trigger)
        self.activity_monitor.add_priority_event_callback(
            self._on_priority_event_trigger
        )

        # Theo dõi thời gian hoạt động của người dùng
        self.last_activity = {}
        self.working_memory_threshold = 20  # Số lượng tin nhắn trước khi cập nhật
        self.inactivity_timeout = 600  # 10 phút không hoạt động (tính bằng giây)

        # Cờ để kiểm soát vòng lặp
        self.running = False
        self.task = None

        # Lock cho file I/O để ngăn chặn race condition
        self.memory_lock = asyncio.Lock()

        # Task 5: Thêm biến lưu vết cho Overlapping Window
        self.last_processed_index: Dict[str, int] = {}  # user_id -> index

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

    def ensure_user_files_exist(self, user_id: str):
        """Ensure user data files exist"""
        import json
        import os
        from datetime import datetime

        # Create directory if not exists
        os.makedirs(self.user_summaries_dir, exist_ok=True)

        # Create episodic memory file if not exists
        episodic_file = os.path.join(
            self.user_summaries_dir, f"{user_id}_episodic.json"
        )
        if not os.path.exists(episodic_file):
            with open(episodic_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            logger.debug(f"📄 Created default episodic memory file for user {user_id}")

        # Create metadata file if not exists
        metadata_file = os.path.join(
            self.user_summaries_dir, f"{user_id}_metadata.json"
        )
        if not os.path.exists(metadata_file):
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "created_at": datetime.now().isoformat(),
                        "last_persona_update": None,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.debug(f"📄 Created default metadata file for user {user_id}")

    def start(self):
        """Khởi động dịch vụ nền và activity monitor"""
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._background_worker())
            self.activity_monitor.start_monitoring()  # Bắt đầu theo dõi
            logger.info("🔄 MemoryBackgroundService started with activity monitoring")

    def stop(self):
        """Dừng dịch vụ nền và activity monitor"""
        if self.running:
            self.running = False
            if self.task:
                self.task.cancel()
            self.activity_monitor.stop_monitoring()  # Dừng theo dõi
            logger.info("🔄 MemoryBackgroundService stopped")

    async def _background_worker(self):
        """Vòng lặp xử lý nền chính"""
        while self.running:
            try:
                # Kiểm tra và cập nhật core personas định kỳ
                await self._check_and_update_core_personas()

                # Chờ 60 giây trước lần kiểm tra tiếp theo
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                logger.info("🔄 Background worker cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in background worker: {e}")
                await asyncio.sleep(60)  # Chờ 60 giây trước khi thử lại

    def record_user_activity(self, user_id: str):
        """Ghi nhận hoạt động của người dùng"""
        self.activity_monitor.record_activity(user_id)

    async def record_priority_event(
        self, user_id: str, event_type: str, event_data: Any = None
    ):
        """Ghi nhận sự kiện ưu tiên"""
        await self.activity_monitor.record_priority_event(
            user_id, event_type, event_data
        )

    async def _on_message_count_trigger(self, user_id: str, condition):
        """Xử lý khi đạt ngưỡng tin nhắn"""
        logger.info(f"🔄 Processing message count trigger for {user_id}")
        await self._update_episodic_memory(user_id)

    async def _on_timeout_trigger(self, user_id: str, condition):
        """Xử lý khi timeout (hội thoại dừng)"""
        logger.info(f"🔄 Processing timeout trigger for {user_id}")
        await self._update_episodic_memory(user_id)

        # Có thể kích hoạt cập nhật core persona nếu cần
        # await self._update_core_persona_if_needed(user_id)

    async def _on_priority_event_trigger(
        self, user_id: str, event_type: str, event_data: Any
    ):
        """Xử lý khi có sự kiện ưu tiên"""
        logger.info(f"🔄 Processing priority event {event_type} for {user_id}")

        if event_type == "personal_info_update":
            # Cập nhật episodic memory trước để đảm bảo thông tin mới được ghi nhận
            await self._update_episodic_memory(user_id)
            # Sau đó cập nhật core persona với thông tin mới
            await self._update_core_persona(user_id)
        elif event_type == "relationship_change":
            # Cập nhật thông tin mối quan hệ
            await self._update_episodic_memory(user_id)
            # Sau đó cập nhật core persona với thông tin mới
            await self._update_core_persona(user_id)
        # Thêm các loại sự kiện khác nếu cần

    def _get_messages_for_processing(
        self, user_id: str, all_messages: list, window_size: int = 20, overlap: int = 5
    ) -> list:
        """
        Lấy messages để xử lý với overlapping window.

        Args:
            user_id: ID người dùng
            all_messages: Tất cả messages hiện có
            window_size: Số lượng messages tối đa để xử lý (default: 20)
            overlap: Số lượng messages lùi lại từ lần trước (default: 5)

        Returns:
            Danh sách messages cần xử lý
        """
        last_index = self.last_processed_index.get(user_id, 0)

        # Lùi lại 'overlap' tin từ lần trước (nhưng không âm)
        start_index = max(0, last_index - overlap)

        # Lấy messages từ start_index
        messages_to_process = all_messages[start_index:]

        # Giới hạn số lượng
        if len(messages_to_process) > window_size:
            messages_to_process = messages_to_process[:window_size]

        return messages_to_process

    async def _update_episodic_memory(self, user_id: str, messages: list = None):
        """Cập nhật episodic memory cho người dùng với cơ chế 'Xóa An Toàn'"""
        try:
            logger.info(f"🔄 Updating episodic memory for user {user_id}")

            # Sử dụng messages được truyền vào hoặc lấy từ file
            if messages is not None:
                # Task 5: Sử dụng Overlapping Window khi có messages được truyền vào
                recent_history = self._get_messages_for_processing(user_id, messages)
            else:
                # Lấy lịch sử hội thoại thô từ file (fallback)
                history = await self._get_user_history(user_id)
                if not history:
                    logger.info(f"📝 No history to process for {user_id}")
                    return False
                # Task 5: Sử dụng Overlapping Window khi lấy từ file
                recent_history = self._get_messages_for_processing(user_id, history)

            # Tạo prompt để trích xuất facts/events
            conversation_text = "\\n".join(
                [
                    f"{msg['role']}: {msg['content']}"
                    for msg in recent_history
                    if msg.get("content")
                ]
            )

            # Load prompt từ file external để trích xuất episodic memory
            episodic_prompt_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data",
                "prompts",
                "episodic_extraction_prompt.txt",
            )

            if os.path.exists(episodic_prompt_file):
                with open(episodic_prompt_file, "r", encoding="utf-8") as f:
                    base_extraction_prompt = f.read().strip()
            else:
                # Fallback minimal prompt
                base_extraction_prompt = (
                    "Trích xuất sự kiện từ hội thoại và trả về JSON."
                )

            extraction_prompt = base_extraction_prompt.replace(
                "{conversation_text}", conversation_text
            )

            # Bước 1: Gọi LLM với response_format để ép JSON output
            llm_response = await self.llm_service.generate_response(
                extraction_prompt,
                f"episodic_extraction_{user_id}",
                response_format={"type": "json_object"},  # Ép JSON output
            )
            if not llm_response:
                logger.error("LLM call failed, skipping cleanup")
                return False

            # Bước 2: Parse JSON
            extracted_data = self._parse_llm_response(llm_response)
            if not extracted_data or "events" not in extracted_data:
                logger.error("JSON parsing failed, skipping cleanup")
                return False

            event_count = len(extracted_data["events"])
            logger.info(
                f"✅ Episodic memory update for {user_id}: {event_count} events extracted"
            )

            # Log thông tin chi tiết về các sự kiện (chỉ lấy một số thông tin cơ bản để không quá dài)
            for i, event in enumerate(
                extracted_data["events"][:3]
            ):  # Chỉ log 3 sự kiện đầu tiên
                logger.debug(
                    f"📋 Event {i + 1} for {user_id} - Type: {event.get('type', 'unknown')}, Category: {event.get('category', 'unknown')}, Summary: {event.get('summary', '')[:100]}"
                )

            # Bước 3: Thêm cờ integrated_to_persona = false
            for event in extracted_data["events"]:
                event["integrated_to_persona"] = False

            # Bước 4: Ghi file episodic.json (có Lock)
            success = await self._append_to_episodic_memory(
                user_id, extracted_data["events"]
            )
            if not success:
                logger.error("Failed to write episodic.json, skipping cleanup")
                return False

            # Bước 5: CHỈ KHI TẤT CẢ THÀNH CÔNG -> Cleanup history
            await self._cleanup_working_memory(user_id, recent_history)

            # Task 5: Cập nhật index sau khi xử lý thành công
            if messages is not None:
                self.last_processed_index[user_id] = len(messages)
            else:
                history = await self._get_user_history(user_id)
                self.last_processed_index[user_id] = len(history)

            logger.info(
                f"✅ Episodic memory updated for {user_id} with {len(extracted_data['events'])} events"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Error updating episodic memory for {user_id}: {e}")
            import traceback

            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            return False  # KHÔNG cleanup khi có lỗi

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

    async def _get_user_history(self, user_id: str) -> List[Dict]:
        return []

    async def _append_to_episodic_memory(self, user_id: str, events: List[Dict]):
        """Thêm các sự kiện vào episodic memory (file nhật ký)"""
        async with self.memory_lock:
            try:
                # Tạo file episodic memory riêng biệt
                episodic_file = os.path.join(
                    self.user_summaries_dir, f"{user_id}_episodic.json"
                )

                # Ensure the file exists
                if not os.path.exists(episodic_file):
                    # Create the file with an empty array
                    os.makedirs(self.user_summaries_dir, exist_ok=True)
                    with open(episodic_file, "w", encoding="utf-8") as f:
                        json.dump([], f, ensure_ascii=False, indent=2)
                    logger.debug(f"📄 Created default episodic file for user {user_id}")

                # Đọc dữ liệu hiện tại
                existing_events = []
                if os.path.exists(episodic_file):
                    try:
                        with open(episodic_file, "r", encoding="utf-8") as f:
                            existing_events = json.load(f)
                            if not isinstance(existing_events, list):
                                existing_events = []
                    except (IOError, json.JSONDecodeError):
                        existing_events = []

                # Thêm các sự kiện mới
                for event in events:
                    event["added_at"] = datetime.now().isoformat()
                    event["integrated_to_persona"] = (
                        False  # Thêm trường để theo dõi tích hợp vào persona
                    )
                    existing_events.append(event)

                # Giới hạn số lượng sự kiện để tránh file quá lớn
                if len(existing_events) > 200:  # Giới hạn 200 sự kiện gần nhất
                    existing_events = existing_events[-200:]

                # Ghi lại file
                with open(episodic_file, "w", encoding="utf-8") as f:
                    json.dump(existing_events, f, ensure_ascii=False, indent=2)

                return True

            except Exception as e:
                logger.error(
                    f"❌ Error appending to episodic memory for {user_id}: {e}"
                )
                return False

    async def _cleanup_working_memory(self, user_id: str, messages_to_remove: list):
        """Dọn dẹp working memory sau khi đã trích xuất - chỉ xóa các tin nhắn cụ thể"""
        async with self.memory_lock:
            try:
                history_file = os.path.join(
                    self.user_summaries_dir, f"{user_id}_history.json"
                )

                # Ensure the file exists
                if not os.path.exists(history_file):
                    # Create the file with an empty array
                    os.makedirs(self.user_summaries_dir, exist_ok=True)
                    with open(history_file, "w", encoding="utf-8") as f:
                        json.dump([], f, ensure_ascii=False, indent=2)
                    logger.debug(f"📄 Created default history file for user {user_id}")
                    return

                # Đọc lịch sử hiện tại
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)

                if not isinstance(history, list):
                    return

                # Chuyển messages_to_remove thành set để tìm kiếm nhanh hơn
                # So sánh dựa trên nội dung và role
                messages_to_remove_set = set()
                for msg in messages_to_remove:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        messages_to_remove_set.add((msg["role"], msg["content"]))

                # Lọc ra các tin nhắn không nằm trong danh sách cần xóa
                remaining_history = []
                removed_count = 0
                for msg in history:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        if (msg["role"], msg["content"]) not in messages_to_remove_set:
                            remaining_history.append(msg)
                        else:
                            removed_count += 1
                    else:
                        # Giữ lại các tin nhắn không hợp lệ (phòng trường hợp lỗi)
                        remaining_history.append(msg)

                # Ghi lại file với phần còn lại
                with open(history_file, "w", encoding="utf-8") as f:
                    json.dump(remaining_history, f, ensure_ascii=False, indent=2)

                logger.info(
                    f"🧹 Cleaned up {removed_count} messages from working memory for {user_id}"
                )

            except Exception as e:
                logger.error(f"❌ Error cleaning up working memory for {user_id}: {e}")

    async def _check_and_update_core_personas(self):
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
                    await self._update_core_persona(user_id)

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

    async def _update_core_persona(self, user_id: str):
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
                    self.ensure_user_files_exist(user_id)

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
            delta = await self._call_llm(prompt, user_id)

            if not delta:
                logger.warning(f"⚠️ Failed to generate delta for {user_id}")
                return

            # 4. Áp dụng delta vào persona hiện tại
            updated_persona = self._apply_delta(current_persona, delta)

            # 5. Lưu lại
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

    async def _get_user_history(self, user_id: str) -> List[Dict]:
        """Lấy lịch sử hội thoại của người dùng"""
        # Kiểm tra xem có working_memory_service không (được inject từ MemoryManager)
        if (
            hasattr(self, "working_memory_service")
            and self.working_memory_service is not None
        ):
            return await self.working_memory_service.get_persistent_history(user_id)
        else:
            # Fallback to old implementation
            async with self.memory_lock:
                history_file = os.path.join(
                    self.user_summaries_dir, f"{user_id}_history.json"
                )

                # Ensure the file exists
                if not os.path.exists(history_file):
                    # Create the file with an empty array
                    os.makedirs(self.user_summaries_dir, exist_ok=True)
                    with open(history_file, "w", encoding="utf-8") as f:
                        json.dump([], f, ensure_ascii=False, indent=2)
                    logger.debug(f"📄 Created default history file for user {user_id}")
                    return []

                try:
                    with open(history_file, "r", encoding="utf-8") as f:
                        history = json.load(f)
                        return history if isinstance(history, list) else []
                except Exception as e:
                    logger.error(f"❌ Error loading history for {user_id}: {e}")
                    return []
