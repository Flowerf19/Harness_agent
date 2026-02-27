import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.activity_monitor import ActivityMonitor

logger = logging.getLogger(__name__)


class MemoryBackgroundService:
    """
    Dịch vụ chạy nền để xử lý cập nhật Episodic Memory và Core Persona
    """

    def __init__(self, llm_service, data_dir: str, relationship_service=None):
        self.llm_service = llm_service
        self.data_dir = data_dir
        self.relationship_service = (
            relationship_service  # Thêm relationship service để tích hợp
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

    async def _update_episodic_memory(self, user_id: str):
        """Cập nhật episodic memory cho người dùng"""
        try:
            logger.info(f"🔄 Updating episodic memory for user {user_id}")

            # Lấy lịch sử hội thoại thô từ file
            history = self._get_user_history(user_id)
            if not history:
                logger.info(f"📝 No history to process for {user_id}")
                return

            # Lấy 20 tin nhắn gần nhất để xử lý
            recent_history = history[-20:] if len(history) > 20 else history

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

            # Gọi LLM để trích xuất facts
            llm_response = await self.llm_service.generate_response(
                extraction_prompt, f"episodic_extraction_{user_id}"
            )

            # Parse kết quả từ LLM
            extracted_data = self._parse_llm_extraction_result(llm_response)

            # Log chi tiết về kết quả trích xuất
            logger.debug(f"🔍 Raw LLM response for {user_id}: {llm_response[:200]}...")
            logger.debug(
                f"📊 Parsed extraction data for {user_id}: {extracted_data is not None}"
            )

            if extracted_data and "events" in extracted_data:
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

                # Thêm facts vào episodic memory
                await self._append_to_episodic_memory(user_id, extracted_data["events"])

                # Xóa bớt tin nhắn cũ ở tầng 1 (working memory) sau khi đã trích xuất
                await self._cleanup_working_memory(user_id, len(recent_history))

                logger.info(
                    f"✅ Episodic memory updated for {user_id} with {len(extracted_data['events'])} events"
                )
            else:
                logger.warning(f"⚠️ No valid events extracted for {user_id}")
                logger.debug(
                    f"🔍 Detailed extraction result for {user_id}: {extracted_data}"
                )

        except Exception as e:
            logger.error(f"❌ Error updating episodic memory for {user_id}: {e}")
            import traceback

            logger.error(f"📋 Traceback: {traceback.format_exc()}")

    def _parse_llm_extraction_result(self, llm_response: str) -> Optional[Dict]:
        """Parse kết quả trích xuất từ LLM"""
        import json
        import re

        # Loại bỏ các ký tự không cần thiết ở đầu và cuối
        cleaned_response = llm_response.strip()

        # Thử parse trực tiếp nếu là JSON hợp lệ
        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            pass

        # Thử tìm và parse khối JSON trong chuỗi phản hồi
        # Sử dụng biểu thức chính xác hơn để tìm khối JSON
        try:
            # Tìm tất cả các khối JSON có thể có trong phản hồi
            # Bắt đầu từ dấu { và kết thúc bằng } tương ứng
            brace_level = 0
            start_pos = -1
            json_candidate = ""

            for i, char in enumerate(cleaned_response):
                if char == "{":
                    if brace_level == 0:
                        start_pos = i
                    brace_level += 1
                elif char == "}":
                    brace_level -= 1
                    if brace_level == 0 and start_pos != -1:
                        # Tìm thấy khối JSON hoàn chỉnh
                        json_candidate = cleaned_response[start_pos : i + 1]

                        # Thử parse khối JSON này
                        try:
                            parsed = json.loads(json_candidate)
                            if isinstance(parsed, dict) and "events" in parsed:
                                return parsed
                        except json.JSONDecodeError:
                            # Nếu không parse được, tiếp tục tìm khối khác
                            continue

            # Nếu không tìm được khối JSON hoàn chỉnh, thử tìm khối JSON đầu tiên
            json_match = re.search(r"\{(?:[^{}]|(?R))*\}", cleaned_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
        except Exception:
            # Nếu có lỗi trong quá trình tìm kiếm JSON nâng cao, trở lại phương pháp đơn giản
            pass

        # Nếu phương pháp nâng cao không thành công, thử phương pháp cũ
        try:
            # Tìm khối JSON giữa dấu ngoặc nhọn
            json_match = re.search(r"\{.*\}", cleaned_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                # Làm sạch chuỗi JSON (loại bỏ trailing commas)
                json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)

                # Thử parse lại
                try:
                    parsed = json.loads(json_str)
                    return parsed
                except json.JSONDecodeError:
                    # Nếu vẫn lỗi, thử thêm các ký tự bị thiếu
                    if not json_str.endswith("}"):
                        json_str += "}"
                    if not json_str.startswith("{"):
                        json_str = "{" + json_str

                    try:
                        parsed = json.loads(json_str)
                        return parsed
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        # Cơ chế fallback: tạo dữ liệu mặc định nếu không thể parse
        logger.warning(
            f"⚠️ Could not parse LLM response, using fallback structure: {cleaned_response[:200]}..."
        )

        # Trích xuất thông tin từ phản hồi văn bản nếu không có JSON
        fallback_events = []

        # Nếu có bất kỳ nội dung nào, tạo một sự kiện chung
        if cleaned_response and len(cleaned_response.strip()) > 0:
            fallback_events.append(
                {
                    "type": "general_interaction",
                    "category": "conversation",
                    "summary": "General conversation interaction",
                    "details": cleaned_response[:500],  # Giới hạn độ dài
                    "timestamp": datetime.now().isoformat(),
                    "confidence": 0.5,
                }
            )

        return {
            "events": fallback_events,
            "key_themes": ["general_interaction"],
            "important_facts": [cleaned_response[:200]] if cleaned_response else [],
        }

    def _get_user_history(self, user_id: str) -> List[Dict]:
        """Lấy lịch sử hội thoại của người dùng"""
        history_file = os.path.join(self.user_summaries_dir, f"{user_id}_history.json")

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
                existing_events.append(event)

            # Giới hạn số lượng sự kiện để tránh file quá lớn
            if len(existing_events) > 200:  # Giới hạn 200 sự kiện gần nhất
                existing_events = existing_events[-200:]

            # Ghi lại file
            with open(episodic_file, "w", encoding="utf-8") as f:
                json.dump(existing_events, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"❌ Error appending to episodic memory for {user_id}: {e}")

    async def _cleanup_working_memory(self, user_id: str, processed_count: int):
        """Dọn dẹp working memory sau khi đã trích xuất"""
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

            # Giữ lại phần chưa xử lý (nếu có)
            remaining_history = (
                history[processed_count:] if len(history) > processed_count else []
            )

            # Ghi lại file với phần còn lại
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(remaining_history, f, ensure_ascii=False, indent=2)

            logger.info(
                f"🧹 Cleaned up {processed_count} messages from working memory for {user_id}"
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

            # Đếm số lượng sự kiện mới
            with open(episodic_file, "r", encoding="utf-8") as f:
                events = json.load(f)

            if not isinstance(events, list):
                return False

            # Điều kiện: có hơn 10 sự kiện kể từ lần cập nhật core persona cuối cùng
            # (giả sử chúng ta theo dõi lần cập nhật cuối cùng trong metadata)

            # Đơn giản hóa: cập nhật nếu có hơn 10 sự kiện
            if len(events) > 10:
                logger.info(
                    f"🔄 Core persona update triggered for {user_id}: {len(events)} events recorded"
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
            if not os.path.exists(episodic_file):
                logger.info(f"📝 No episodic memory to process for {user_id}")
                # Ensure the file exists and create a basic summary if needed
                self.ensure_user_files_exist(user_id)

                # Check if we have a very basic summary that needs initialization
                current_summary = self._get_current_summary(user_id)
                if not current_summary or current_summary == "":
                    # Create a basic summary for new users
                    default_summary = self._get_empty_summary()
                    self._save_summary(user_id, default_summary)
                    logger.info(f"📝 Initialized basic summary for new user {user_id}")
                return

            with open(episodic_file, "r", encoding="utf-8") as f:
                events = json.load(f)

            if not isinstance(events, list) or not events:
                logger.info(f"📝 No events to process for {user_id}")
                return

            # Lấy core persona hiện tại
            current_summary = self._get_current_summary(user_id)

            # Lấy các sự kiện gần đây để cập nhật
            recent_events = (
                events[-50:] if len(events) > 50 else events
            )  # Lấy 50 sự kiện gần nhất

            # Lấy thông tin mối quan hệ từ RelationshipService nếu có
            relationship_info = ""
            if self.relationship_service:
                try:
                    user_relationships = (
                        self.relationship_service.get_user_relationships(user_id)
                    )
                    if user_relationships:
                        relationship_info = "THÔNG TIN MỐI QUAN HỆ GẦN ĐÂY:\n"
                        for rel in user_relationships[:5]:  # Lấy 5 mối quan hệ gần đây
                            relationship_info += f"- {rel['other_person']}: {rel['relationship_type']} (nói đến: {rel['context']})\n"
                        relationship_info += "\n"
                except Exception as e:
                    logger.warning(f"⚠️ Could not retrieve relationship info: {e}")

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

            # Format prompt với dữ liệu thực tế
            formatted_prompt = f"""
{base_prompt}

=== THÔNG TIN HIỆN TẠI ===
{current_summary or "[Chưa có hồ sơ]"}

{relationship_info}
=== SỰ KIỆN MỚI (10 sự kiện gần nhất) ===
{json.dumps(recent_events[-10:], indent=2, ensure_ascii=False)}
"""

            update_prompt = formatted_prompt

            # Gọi LLM để cập nhật hồ sơ
            new_summary = await self.llm_service.generate_response(
                update_prompt, f"core_persona_update_{user_id}"
            )

            if new_summary and len(new_summary.strip()) > 50:
                # Lưu lại hồ sơ mới
                self._save_summary(user_id, new_summary.strip())

                # Lưu lại thời gian cập nhật để theo dõi
                await self._mark_persona_updated(user_id)

                logger.info(f"✅ Core persona updated for {user_id}")
            else:
                logger.warning(f"⚠️ Failed to generate new summary for {user_id}")

        except Exception as e:
            logger.error(f"❌ Error updating core persona for {user_id}: {e}")

    def _get_current_summary(self, user_id: str) -> str:
        """Lấy summary hiện tại của người dùng"""
        summary_file = os.path.join(self.user_summaries_dir, f"{user_id}_summary.txt")

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

    def _save_summary(self, user_id: str, summary: str):
        """Lưu summary của người dùng"""
        summary_file = os.path.join(self.user_summaries_dir, f"{user_id}_summary.txt")

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
