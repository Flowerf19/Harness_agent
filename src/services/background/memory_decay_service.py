import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MemoryDecayService:
    """
    Dịch vụ xử lý memory decay và cập nhật episodic memory.
    """

    def __init__(
        self,
        llm_service,
        data_dir: str,
        relationship_service=None,
        working_memory_service=None,
        cleanup_service=None,
        scheduler_service=None,
    ):
        self.llm_service = llm_service
        self.data_dir = data_dir
        self.relationship_service = relationship_service
        self.working_memory_service = working_memory_service
        self.cleanup_service = cleanup_service
        self.scheduler_service = scheduler_service

        # Đường dẫn lưu trữ
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")

        # Lock cho file I/O để ngăn chặn race condition
        self.memory_lock = asyncio.Lock()

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

    async def on_message_count_trigger(self, user_id: str, condition):
        """Xử lý khi đạt ngưỡng tin nhắn"""
        logger.info(f"🔄 Processing message count trigger for {user_id}")
        await self._update_episodic_memory(user_id)

    async def on_timeout_trigger(self, user_id: str, condition):
        """Xử lý khi timeout (hội thoại dừng)"""
        logger.info(f"🔄 Processing timeout trigger for {user_id}")
        await self._update_episodic_memory(user_id)

        # Có thể kích hoạt cập nhật core persona nếu cần
        # await self._update_core_persona_if_needed(user_id)

    async def on_priority_event_trigger(
        self, user_id: str, event_type: str, event_data: Any
    ):
        """Xử lý khi có sự kiện ưu tiên"""
        logger.info(f"🔄 Processing priority event {event_type} for {user_id}")

        if event_type == "personal_info_update":
            # Cập nhật episodic memory trước để đảm bảo thông tin mới được ghi nhận
            await self._update_episodic_memory(user_id)
            # Sau đó cập nhật core persona với thông tin mới
            if hasattr(self, "summary_scheduler"):
                await self.summary_scheduler.update_core_persona(user_id)
        elif event_type == "relationship_change":
            # Cập nhật thông tin mối quan hệ
            await self._update_episodic_memory(user_id)
            # Sau đó cập nhật core persona với thông tin mới
            if hasattr(self, "summary_scheduler"):
                await self.summary_scheduler.update_core_persona(user_id)
        # Thêm các loại sự kiện khác nếu cần

    async def _update_episodic_memory(self, user_id: str, messages: list = None):
        """Cập nhật episodic memory cho người dùng với cơ chế 'Xóa An Toàn'"""
        try:
            logger.info(f"🔄 Updating episodic memory for user {user_id}")

            # Sử dụng messages được truyền vào hoặc lấy từ file
            if messages is not None:
                # Task 5: Sử dụng Overlapping Window khi có messages được truyền vào
                if self.scheduler_service:
                    recent_history = self.scheduler_service.get_messages_for_processing(
                        user_id, messages
                    )
                else:
                    recent_history = messages[-20:]  # fallback
            else:
                # Lấy lịch sử hội thoại thô từ file (fallback)
                history = await self._get_user_history(user_id)
                if not history:
                    logger.info(f"📝 No history to process for {user_id}")
                    return False
                # Task 5: Sử dụng Overlapping Window khi lấy từ file
                if self.scheduler_service:
                    recent_history = self.scheduler_service.get_messages_for_processing(
                        user_id, history
                    )
                else:
                    recent_history = history[-20:]  # fallback

            # Tạo prompt để trích xuất facts/events
            conversation_text = "\n".join(
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
            if self.cleanup_service:
                await self.cleanup_service.cleanup_working_memory(
                    user_id, recent_history
                )

            # Task 5: Cập nhật index sau khi xử lý thành công
            if self.scheduler_service:
                if messages is not None:
                    self.scheduler_service.last_processed_index[user_id] = len(messages)
                else:
                    history = await self._get_user_history(user_id)
                    self.scheduler_service.last_processed_index[user_id] = len(history)

            logger.info(
                f"✅ Episodic memory updated for {user_id} with {len(extracted_data['events'])} events"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Error updating episodic memory for {user_id}: {e}")
            import traceback

            logger.error(f"📋 Traceback: {traceback.format_exc()}")
            return False  # KHÔNG cleanup khi có lỗi

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
