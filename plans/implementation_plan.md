# Kế hoạch triển khai hệ thống 3 tầng Bộ nhớ

## Tổng quan

Tài liệu này mô tả các bước cụ thể để triển khai hệ thống 3 tầng Bộ nhớ đã được thiết kế, bao gồm cả việc tạo nhánh Git và các bước triển khai từng thành phần.

## 1. Tạo nhánh Git

Trước khi bắt đầu triển khai, hãy tạo một nhánh mới để cô lập các thay đổi:

```bash
git checkout -b feature/three-tier-memory-system
```

## 2. Triển khai từng thành phần

### Bước 1: Tạo Activity Monitor

Tệp: `src/services/activity_monitor.py`

```python
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Callable, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TriggerCondition:
    user_id: str
    last_activity: datetime
    message_count: int
    session_start: datetime

class ActivityMonitor:
    """
    Theo dõi hoạt động người dùng và kích hoạt các trigger
    """
    
    def __init__(self, 
                 message_threshold: int = 20,
                 inactivity_timeout: int = 600,  # 10 minutes
                 check_interval: int = 30):      # 30 seconds
        self.message_threshold = message_threshold
        self.inactivity_timeout = inactivity_timeout
        self.check_interval = check_interval
        
        # Theo dõi trạng thái người dùng
        self.user_conditions: Dict[str, TriggerCondition] = {}
        
        # Callback cho các loại trigger
        self.message_count_callbacks: list[Callable] = []
        self.timeout_callbacks: list[Callable] = []
        self.priority_event_callbacks: list[Callable] = []
        
        # Cờ cho vòng lặp
        self.running = False
        self.monitor_task = None
    
    def start_monitoring(self):
        """Bắt đầu theo dõi hoạt động"""
        if not self.running:
            self.running = True
            self.monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info(f"👀 Activity monitor started (interval: {self.check_interval}s)")
    
    def stop_monitoring(self):
        """Dừng theo dõi hoạt động"""
        if self.running:
            self.running = False
            if self.monitor_task:
                self.monitor_task.cancel()
            logger.info("👀 Activity monitor stopped")
    
    async def _monitor_loop(self):
        """Vòng lặp theo dõi chính"""
        while self.running:
            try:
                await self._check_all_conditions()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("👀 Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in monitor loop: {e}")
                await asyncio.sleep(self.check_interval)
    
    def record_activity(self, user_id: str):
        """Ghi nhận hoạt động của người dùng"""
        current_time = datetime.now()
        
        if user_id not in self.user_conditions:
            self.user_conditions[user_id] = TriggerCondition(
                user_id=user_id,
                last_activity=current_time,
                message_count=0,
                session_start=current_time
            )
        else:
            self.user_conditions[user_id].last_activity = current_time
            self.user_conditions[user_id].message_count += 1
    
    def record_priority_event(self, user_id: str, event_type: str, event_data: Any = None):
        """Ghi nhận sự kiện ưu tiên cần xử lý ngay"""
        self.record_activity(user_id)  # Cập nhật thời gian hoạt động
        
        # Gọi các callback cho sự kiện ưu tiên
        for callback in self.priority_event_callbacks:
            try:
                callback(user_id, event_type, event_data)
            except Exception as e:
                logger.error(f"❌ Error in priority event callback: {e}")
    
    async def _check_all_conditions(self):
        """Kiểm tra điều kiện cho tất cả người dùng"""
        current_time = datetime.now()
        users_to_check = list(self.user_conditions.keys())
        
        for user_id in users_to_check:
            if user_id not in self.user_conditions:
                continue
                
            condition = self.user_conditions[user_id]
            
            # Kiểm tra điều kiện số lượng tin nhắn
            if condition.message_count >= self.message_threshold:
                await self._trigger_message_count(user_id, condition)
            
            # Kiểm tra điều kiện timeout
            time_since_activity = current_time - condition.last_activity
            if time_since_activity.total_seconds() >= self.inactivity_timeout:
                await self._trigger_timeout(user_id, condition)
    
    async def _trigger_message_count(self, user_id: str, condition: TriggerCondition):
        """Kích hoạt trigger khi đạt ngưỡng tin nhắn"""
        logger.info(f"📈 Message count trigger for {user_id}: {condition.message_count}/{self.message_threshold}")
        
        # Gọi các callback
        for callback in self.message_count_callbacks:
            try:
                await callback(user_id, condition)
            except Exception as e:
                logger.error(f"❌ Error in message count callback: {e}")
        
        # Reset bộ đếm tin nhắn sau khi kích hoạt
        condition.message_count = 0  # Có thể giữ lại một số tin nhắn gần nhất
    
    async def _trigger_timeout(self, user_id: str, condition: TriggerCondition):
        """Kích hoạt trigger khi timeout"""
        logger.info(f"⏰ Timeout trigger for {user_id}: inactive for {self.inactivity_timeout}s")
        
        # Gọi các callback
        for callback in self.timeout_callbacks:
            try:
                await callback(user_id, condition)
            except Exception as e:
                logger.error(f"❌ Error in timeout callback: {e}")
        
        # Xóa condition sau khi xử lý (hoặc có thể giữ lại để theo dõi lâu dài)
        # del self.user_conditions[user_id]
    
    def add_message_count_callback(self, callback: Callable):
        """Thêm callback cho trigger số lượng tin nhắn"""
        self.message_count_callbacks.append(callback)
    
    def add_timeout_callback(self, callback: Callable):
        """Thêm callback cho trigger timeout"""
        self.timeout_callbacks.append(callback)
    
    def add_priority_event_callback(self, callback: Callable):
        """Thêm callback cho trigger sự kiện ưu tiên"""
        self.priority_event_callbacks.append(callback)
    
    def get_user_status(self, user_id: str) -> Dict[str, Any]:
        """Lấy trạng thái trigger của người dùng"""
        if user_id not in self.user_conditions:
            return {
                "active": False,
                "message_count": 0,
                "time_since_activity": None,
                "next_trigger": None
            }
        
        condition = self.user_conditions[user_id]
        time_since_activity = datetime.now() - condition.last_activity
        
        next_trigger = None
        if condition.message_count >= self.message_threshold:
            next_trigger = "message_count"
        elif time_since_activity.total_seconds() >= self.inactivity_timeout:
            next_trigger = "timeout"
        
        return {
            "active": True,
            "message_count": condition.message_count,
            "time_since_activity": time_since_activity.total_seconds(),
            "next_trigger": next_trigger,
            "session_duration": (datetime.now() - condition.session_start).total_seconds()
        }
```

### Bước 2: Cập nhật MemoryBackgroundService

Tệp: `src/services/memory_background_service.py` (thay thế nội dung hiện tại)

```python
import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from services.activity_monitor import ActivityMonitor

logger = logging.getLogger(__name__)

class MemoryBackgroundService:
    """
    Dịch vụ chạy nền để xử lý cập nhật Episodic Memory và Core Persona
    """
    
    def __init__(self, llm_service, data_dir: str):
        self.llm_service = llm_service
        self.data_dir = data_dir
        
        # Đường dẫn lưu trữ
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")
        
        # Tạo activity monitor
        self.activity_monitor = ActivityMonitor()
        
        # Cài đặt callback cho các trigger
        self.activity_monitor.add_message_count_callback(self._on_message_count_trigger)
        self.activity_monitor.add_timeout_callback(self._on_timeout_trigger)
        self.activity_monitor.add_priority_event_callback(self._on_priority_event_trigger)
        
        # Theo dõi thời gian hoạt động của người dùng
        self.last_activity = {}
        self.working_memory_threshold = 20  # Số lượng tin nhắn trước khi cập nhật
        self.inactivity_timeout = 600  # 10 phút không hoạt động (tính bằng giây)
        
        # Cờ để kiểm soát vòng lặp
        self.running = False
        self.task = None
        
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
    
    def record_priority_event(self, user_id: str, event_type: str, event_data: Any = None):
        """Ghi nhận sự kiện ưu tiên"""
        self.activity_monitor.record_priority_event(user_id, event_type, event_data)
    
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
    
    async def _on_priority_event_trigger(self, user_id: str, event_type: str, event_data: Any):
        """Xử lý khi có sự kiện ưu tiên"""
        logger.info(f"🔄 Processing priority event {event_type} for {user_id}")
        
        if event_type == "personal_info_update":
            # Cập nhật core persona ngay lập tức
            await self._update_core_persona(user_id)
        elif event_type == "relationship_change":
            # Cập nhật thông tin mối quan hệ
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
            conversation_text = "\\n".join([
                f"{msg['role']}: {msg['content']}" 
                for msg in recent_history 
                if msg.get('content')
            ])
            
            # Prompt để LLM trích xuất các sự kiện/fact quan trọng
            extraction_prompt = f"""
Bạn là một chuyên gia phân tích hội thoại. Hãy trích xuất các sự kiện, fact quan trọng từ đoạn hội thoại sau:

HỘI THOẠI CẦN PHÂN TÍCH:
{conversation_text}

Hãy trích xuất các thông tin sau theo định dạng JSON:
{{
  "events": [
    {{
      "type": "fact|event|behavior|preference|milestone|change",
      "category": "personal_info|interests|habits|goals|relationships|activities|status_change",
      "summary": "Tóm tắt ngắn gọn sự kiện/fact",
      "details": "Chi tiết cụ thể về sự kiện/fact",
      "timestamp": "Thời gian (nếu có thể xác định)",
      "confidence": 0.0-1.0
    }}
  ],
  "key_themes": ["chủ đề chính được thảo luận"],
  "important_facts": ["các fact quan trọng cần nhớ"]
}}

Chỉ trả lời dưới dạng JSON, không giải thích thêm:
"""
            
            # Gọi LLM để trích xuất facts
            llm_response = await self.llm_service.generate_response(
                extraction_prompt, f"episodic_extraction_{user_id}"
            )
            
            # Parse kết quả từ LLM
            extracted_data = self._parse_llm_extraction_result(llm_response)
            
            if extracted_data and 'events' in extracted_data:
                # Thêm facts vào episodic memory
                await self._append_to_episodic_memory(user_id, extracted_data['events'])
                
                # Xóa bớt tin nhắn cũ ở tầng 1 (working memory) sau khi đã trích xuất
                await self._cleanup_working_memory(user_id, len(recent_history))
                
                logger.info(f"✅ Episodic memory updated for {user_id} with {len(extracted_data['events'])} events")
            else:
                logger.warning(f"⚠️ No valid events extracted for {user_id}")
                
        except Exception as e:
            logger.error(f"❌ Error updating episodic memory for {user_id}: {e}")
    
    def _parse_llm_extraction_result(self, llm_response: str) -> Optional[Dict]:
        """Parse kết quả trích xuất từ LLM"""
        import re
        import json
        
        try:
            # Thử parse trực tiếp nếu là JSON hợp lệ
            return json.loads(llm_response)
        except json.JSONDecodeError:
            # Nếu không phải JSON hợp lệ, tìm khối JSON trong chuỗi
            try:
                # Tìm khối JSON giữa dấu ngoặc nhọn
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    # Làm sạch chuỗi JSON (loại bỏ trailing commas)
                    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                    return json.loads(json_str)
            except:
                pass
        
        return None
    
    def _get_user_history(self, user_id: str) -> List[Dict]:
        """Lấy lịch sử hội thoại của người dùng"""
        history_file = os.path.join(self.user_summaries_dir, f"{user_id}_history.json")
        
        if not os.path.exists(history_file):
            return []
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                return history if isinstance(history, list) else []
        except Exception as e:
            logger.error(f"❌ Error loading history for {user_id}: {e}")
            return []
    
    async def _append_to_episodic_memory(self, user_id: str, events: List[Dict]):
        """Thêm các sự kiện vào episodic memory (file nhật ký)"""
        try:
            # Tạo file episodic memory riêng biệt
            episodic_file = os.path.join(self.user_summaries_dir, f"{user_id}_episodic.json")
            
            # Đọc dữ liệu hiện tại
            existing_events = []
            if os.path.exists(episodic_file):
                try:
                    with open(episodic_file, 'r', encoding='utf-8') as f:
                        existing_events = json.load(f)
                        if not isinstance(existing_events, list):
                            existing_events = []
                except:
                    existing_events = []
            
            # Thêm các sự kiện mới
            for event in events:
                event['added_at'] = datetime.now().isoformat()
                existing_events.append(event)
            
            # Giới hạn số lượng sự kiện để tránh file quá lớn
            if len(existing_events) > 200:  # Giới hạn 200 sự kiện gần nhất
                existing_events = existing_events[-200:]
            
            # Ghi lại file
            with open(episodic_file, 'w', encoding='utf-8') as f:
                json.dump(existing_events, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"❌ Error appending to episodic memory for {user_id}: {e}")
    
    async def _cleanup_working_memory(self, user_id: str, processed_count: int):
        """Dọn dẹp working memory sau khi đã trích xuất"""
        try:
            history_file = os.path.join(self.user_summaries_dir, f"{user_id}_history.json")
            
            if not os.path.exists(history_file):
                return
            
            # Đọc lịch sử hiện tại
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            if not isinstance(history, list):
                return
            
            # Giữ lại phần chưa xử lý (nếu có)
            remaining_history = history[processed_count:] if len(history) > processed_count else []
            
            # Ghi lại file với phần còn lại
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(remaining_history, f, ensure_ascii=False, indent=2)
                
            logger.info(f"🧹 Cleaned up {processed_count} messages from working memory for {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error cleaning up working memory for {user_id}: {e}")
    
    async def _check_and_update_core_personas(self):
        """Kiểm tra và cập nhật core personas định kỳ"""
        # Cập nhật định kỳ hàng tuần hoặc khi có > 50 sự kiện mới
        try:
            # Lấy tất cả file episodic
            episodic_files = [f for f in os.listdir(self.user_summaries_dir) if f.endswith('_episodic.json')]
            
            for episodic_file in episodic_files:
                user_id = episodic_file.replace('_episodic.json', '')
                
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
            episodic_file = os.path.join(self.user_summaries_dir, f"{user_id}_episodic.json")
            
            if not os.path.exists(episodic_file):
                return False
            
            # Đếm số lượng sự kiện mới
            with open(episodic_file, 'r', encoding='utf-8') as f:
                events = json.load(f)
            
            if not isinstance(events, list):
                return False
            
            # Điều kiện: có hơn 50 sự kiện kể từ lần cập nhật core persona cuối cùng
            # (giả sử chúng ta theo dõi lần cập nhật cuối cùng trong metadata)
            
            # Đơn giản hóa: cập nhật nếu có hơn 50 sự kiện
            if len(events) > 50:
                logger.info(f"🔄 Core persona update triggered for {user_id}: {len(events)} events recorded")
                return True
            
            # Ngoài ra, có thể thêm điều kiện thời gian (ví dụ: cập nhật hàng tuần)
            # Để đơn giản, tạm thời chỉ dùng điều kiện số lượng sự kiện
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking core persona update condition for {user_id}: {e}")
            return False
    
    async def _update_core_persona(self, user_id: str):
        """Cập nhật core persona cho người dùng"""
        try:
            logger.info(f"🔄 Updating core persona for user {user_id}")
            
            # Lấy episodic memory (sự kiện mới)
            episodic_file = os.path.join(self.user_summaries_dir, f"{user_id}_episodic.json")
            if not os.path.exists(episodic_file):
                logger.info(f"📝 No episodic memory to process for {user_id}")
                return
            
            with open(episodic_file, 'r', encoding='utf-8') as f:
                events = json.load(f)
            
            if not isinstance(events, list) or not events:
                logger.info(f"📝 No events to process for {user_id}")
                return
            
            # Lấy core persona hiện tại
            current_summary = self._get_current_summary(user_id)
            
            # Lấy các sự kiện gần đây để cập nhật
            recent_events = events[-50:] if len(events) > 50 else events  # Lấy 50 sự kiện gần nhất
            
            # Tạo prompt để cập nhật hồ sơ
            update_prompt = f"""
Bạn là chuyên gia cập nhật hồ sơ người dùng. Hãy cập nhật hồ sơ cốt lõi của người dùng dựa trên các sự kiện mới sau:

HỒ SƠ HIỆN TẠI:
{current_summary or '[Chưa có hồ sơ]'}

SỰ KIỆN MỚI (theo thứ tự thời gian):
{json.dumps(recent_events[-10:], indent=2, ensure_ascii=False)}  # Lấy 10 sự kiện gần nhất

Hãy tạo lại hồ sơ người dùng theo định dạng chuẩn sau, cập nhật thông tin mới và giữ lại thông tin vẫn còn chính xác:

=== THÔNG TIN CƠ BẢN ===
Tên: [Tên thật hoặc biệt danh]
Tuổi: [Tuổi hiện tại]
Sinh nhật: [Ngày sinh nếu có]

=== SỞ THÍCH & ĐAM MÊ ===
• Công nghệ: [Ngôn ngữ lập trình, dự án, level skill]
• Giải trí: [Phim, nhạc, game, thể loại yêu thích]
• Khác: [Các sở thích khác được đề cập]

=== TÍNH CÁCH & PHONG CÁCH ===
• Giao tiếp: [Cách user nói chuyện - hài hước, nghiêm túc, etc]
• Tâm trạng: [Thường vui, hay lo lắng, tích cực, etc]
• Đặc điểm: [Những điều đặc biệt về user]

=== DỰ ÁN & MỤC TIÊU ===
• Hiện tại: [Đang làm gì, học gì, quan tâm gì]
• Kế hoạch: [Mục tiêu, ước mơ đã chia sẻ]

=== LỊCH SỬ TƯƠNG TÁC ===
• Chủ đề đã thảo luận: [Những gì đã nói chuyện]
• Mức độ thân thiết: [Mới quen, đã quen, thân thiết]
• Ghi chú đặc biệt: [Điều gì cần nhớ đặc biệt]

=== MỐI QUAN HỆ VỚI NGƯỜI KHÁC ===
• Bạn bè: [Tên các user khác mà user này đã nhắc đến, kèm thông tin về mối quan hệ]
• Gia đình: [Thành viên gia đình được nhắc đến]
• Đồng nghiệp: [Đồng nghiệp, đối tác làm việc được đề cập]
• Người quan trọng: [Người yêu, crush, người đặc biệt được nhắc đến]
• Ghi chú về tương tác: [Cách user nói về người khác, mức độ thân thiết]

QUAN TRỌNG:
- CẬP NHẬT thông tin nếu có thay đổi (ví dụ: tuổi mới, sở thích mới)
- GIỮ lại thông tin vẫn còn chính xác
- LOẠI BỎ thông tin lỗi thời hoặc không còn đúng
- CHỈ ghi thông tin CÓ THẬT trong các sự kiện
"""
            
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
        
        if not os.path.exists(summary_file):
            return ""
        
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"❌ Error loading summary for {user_id}: {e}")
            return ""
    
    def _save_summary(self, user_id: str, summary: str):
        """Lưu summary của người dùng"""
        summary_file = os.path.join(self.user_summaries_dir, f"{user_id}_summary.txt")
        
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary)
            logger.info(f"📝 Summary saved for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error saving summary for {user_id}: {e}")
    
    async def _mark_persona_updated(self, user_id: str):
        """Đánh dấu thời gian cập nhật core persona"""
        # Có thể lưu vào một file metadata riêng để theo dõi
        metadata_file = os.path.join(self.user_summaries_dir, f"{user_id}_metadata.json")
        
        metadata = {}
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except:
                metadata = {}
        
        metadata['last_persona_update'] = datetime.now().isoformat()
        
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Error saving metadata for {user_id}: {e}")
```

### Bước 3: Tạo WorkingMemoryService

Tệp: `src/services/working_memory_service.py`

```python
import logging
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum
import heapq

logger = logging.getLogger(__name__)

class MessageCategory(Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    QUERY = "query"
    RESPONSE = "response"
    RELATIONSHIP = "relationship"
    GOAL = "goal"
    STATUS_UPDATE = "status_update"
    GENERAL = "general"

@dataclass
class WorkingMemoryEntry:
    role: str  # 'user' hoặc 'assistant'
    content: str
    timestamp: datetime
    importance_score: float = 0.5  # 0.0 - 1.0
    category: MessageCategory = MessageCategory.GENERAL
    access_count: int = 0
    is_sensitive: bool = False
    entities: List[str] = field(default_factory=list)  # Các thực thể được trích xuất
    keywords: List[str] = field(default_factory=list)  # Từ khóa quan trọng

class WorkingMemoryService:
    """
    Dịch vụ quản lý Working Memory (Tầng 1 - Ngắn hạn)
    """
    
    def __init__(self, max_capacity: int = 20, trigger_threshold: int = 20):
        self.max_capacity = max_capacity  # Số lượng tin nhắn tối đa
        self.trigger_threshold = trigger_threshold  # Ngưỡng kích hoạt cập nhật
        self.memories: Dict[str, List[WorkingMemoryEntry]] = {}  # Lưu theo user_id
        self.trigger_callbacks = []  # Danh sách callback khi đạt ngưỡng
        
    def add_message(self, user_id: str, role: str, content: str) -> WorkingMemoryEntry:
        """
        Thêm tin nhắn vào working memory với đánh giá mức độ quan trọng
        """
        # Tính toán mức độ quan trọng
        importance_score, category, entities, keywords = self._evaluate_importance(content, role)
        
        entry = WorkingMemoryEntry(
            role=role,
            content=content,
            timestamp=datetime.now(),
            importance_score=importance_score,
            category=category,
            entities=entities,
            keywords=keywords
        )
        
        # Thêm vào danh sách của người dùng
        if user_id not in self.memories:
            self.memories[user_id] = []
        
        self.memories[user_id].append(entry)
        
        # Kiểm tra điều kiện trigger
        self._check_trigger_conditions(user_id)
        
        logger.debug(f"📥 Added message to working memory for {user_id}: {content[:50]}...")
        
        return entry
    
    def _evaluate_importance(self, content: str, role: str) -> tuple[float, MessageCategory, List[str], List[str]]:
        """
        Đánh giá mức độ quan trọng của tin nhắn
        """
        importance = 0.5  # Mức mặc định
        category = MessageCategory.GENERAL
        entities = []
        keywords = []
        
        content_lower = content.lower()
        
        # Các mẫu để nhận diện thông tin quan trọng
        personal_info_patterns = [
            (r"(tên|name).*?(là|is|:)\s*(\w+)", MessageCategory.FACT, ["name"]),
            (r"(\d+)\s*(tuổi|age|năm)", MessageCategory.FACT, ["age"]),
            (r"(thích|like|love|yêu).*?(\w+)", MessageCategory.PREFERENCE, ["preference"]),
            (r"(bạn|anh|chị|em)\s*(\w+)", MessageCategory.RELATIONSHIP, ["relationship"]),
            (r"(muốn|mong|ước|plan|want|need).*?(đi|làm|có)", MessageCategory.GOAL, ["goal"]),
        ]
        
        # Kiểm tra các mẫu thông tin cá nhân
        for pattern, cat, kw_list in personal_info_patterns:
            import re
            matches = re.finditer(pattern, content_lower)
            for match in matches:
                importance += 0.2  # Tăng mức độ quan trọng
                if importance > 1.0:
                    importance = 1.0
                category = cat
                keywords.extend(kw_list)
                # Trích xuất thực thể nếu có
                if len(match.groups()) > 2:
                    entities.append(match.group(3))
        
        # Tăng mức độ quan trọng nếu là tin nhắn của người dùng
        if role == "user":
            importance += 0.1
            if importance > 1.0:
                importance = 1.0
        
        # Tăng mức độ quan trọng nếu có cảm xúc mạnh
        emotional_words = ["rất", "cực kỳ", "thật sự", "đáng yêu", "tuyệt vời", "buồn", "vui", "giận"]
        for word in emotional_words:
            if word in content_lower:
                importance += 0.05
                if importance > 1.0:
                    importance = 1.0
        
        # Trích xuất từ khóa quan trọng
        keywords.extend(self._extract_keywords(content))
        
        return min(importance, 1.0), category, list(set(entities)), list(set(keywords))
    
    def _extract_keywords(self, content: str) -> List[str]:
        """
        Trích xuất từ khóa từ nội dung
        """
        # Đơn giản hóa: tách từ và loại bỏ stop words cơ bản
        import re
        words = re.findall(r'\b\w+\b', content.lower())
        
        # Stop words cơ bản trong tiếng Việt và Anh
        stop_words = {
            'và', 'hoặc', 'nhưng', 'rồi', 'với', 'của', 'trong', 'tại', 'về', 'qua', 'trên', 'dưới',
            'the', 'a', 'an', 'and', 'or', 'but', 'with', 'of', 'in', 'at', 'to', 'for', 'on'
        }
        
        keywords = [word for word in words if len(word) > 2 and word not in stop_words]
        return list(set(keywords))  # Trả về duy nhất
    
    def get_context(self, user_id: str, max_entries: int = 5) -> List[WorkingMemoryEntry]:
        """
        Lấy ngữ cảnh gần đây từ working memory, ưu tiên thông tin quan trọng
        """
        if user_id not in self.memories or not self.memories[user_id]:
            return []
        
        # Lấy các entry và sắp xếp theo mức độ quan trọng và thời gian
        user_memory = self.memories[user_id]
        
        # Sắp xếp theo: (importance_score giảm dần, timestamp giảm dần)
        sorted_entries = sorted(
            user_memory,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True
        )
        
        # Trả về số lượng tối đa được yêu cầu
        return sorted_entries[:max_entries]
    
    def get_recent_conversation(self, user_id: str, max_entries: int = 3) -> List[WorkingMemoryEntry]:
        """
        Lấy cuộc trò chuyện gần đây theo thứ tự thời gian
        """
        if user_id not in self.memories or not self.memories[user_id]:
            return []
        
        # Lấy các entry gần đây nhất
        user_memory = self.memories[user_id]
        recent_entries = user_memory[-max_entries:]  # Lấy từ cuối danh sách
        
        # Tăng số lần truy cập cho các entry này
        for entry in recent_entries:
            entry.access_count += 1
        
        return recent_entries
    
    def search_by_category(self, user_id: str, category: MessageCategory, limit: int = 5) -> List[WorkingMemoryEntry]:
        """
        Tìm kiếm các entry theo danh mục
        """
        if user_id not in self.memories:
            return []
        
        matching_entries = [
            entry for entry in self.memories[user_id]
            if entry.category == category
        ]
        
        # Sắp xếp theo mức độ quan trọng và thời gian
        sorted_entries = sorted(
            matching_entries,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True
        )
        
        return sorted_entries[:limit]
    
    def search_by_keywords(self, user_id: str, keywords: List[str], limit: int = 5) -> List[WorkingMemoryEntry]:
        """
        Tìm kiếm các entry theo từ khóa
        """
        if user_id not in self.memories:
            return []
        
        matching_entries = []
        keywords_lower = [kw.lower() for kw in keywords]
        
        for entry in self.memories[user_id]:
            # Kiểm tra trong nội dung và từ khóa của entry
            content_lower = entry.content.lower()
            entry_keywords_lower = [k.lower() for k in entry.keywords]
            
            if any(keyword in content_lower or keyword in entry_keywords_lower for keyword in keywords_lower):
                matching_entries.append(entry)
        
        # Sắp xếp theo mức độ quan trọng và thời gian
        sorted_entries = sorted(
            matching_entries,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True
        )
        
        return sorted_entries[:limit]
    
    def _check_trigger_conditions(self, user_id: str):
        """
        Kiểm tra các điều kiện để kích hoạt các hành động
        """
        if user_id not in self.memories:
            return
        
        message_count = len(self.memories[user_id])
        
        # Kích hoạt nếu đạt ngưỡng số lượng tin nhắn
        if message_count >= self.trigger_threshold:
            self._trigger_callback("MESSAGE_THRESHOLD_REACHED", user_id, message_count)
    
    def register_trigger_callback(self, callback_func):
        """
        Đăng ký hàm callback để xử lý các trigger
        """
        self.trigger_callbacks.append(callback_func)
    
    def _trigger_callback(self, trigger_type: str, user_id: str, data: any):
        """
        Kích hoạt các callback đã đăng ký
        """
        for callback in self.trigger_callbacks:
            try:
                callback(trigger_type, user_id, data)
            except Exception as e:
                logger.error(f"Error in trigger callback: {e}")
    
    def cleanup_old_entries(self, user_id: str, keep_count: int = 10):
        """
        Dọn dẹp các entry cũ, giữ lại số lượng nhất định
        """
        if user_id not in self.memories:
            return
        
        user_memory = self.memories[user_id]
        
        if len(user_memory) <= keep_count:
            return  # Không cần dọn dẹp
        
        # Ưu tiên giữ lại các entry quan trọng
        sorted_entries = sorted(
            user_memory,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True
        )
        
        # Giữ lại số lượng mong muốn
        self.memories[user_id] = sorted_entries[:keep_count]
        
        logger.debug(f"🧹 Cleaned up working memory for {user_id}, kept {len(self.memories[user_id])} entries")
    
    def get_statistics(self, user_id: str) -> Dict:
        """
        Lấy thống kê về working memory của người dùng
        """
        if user_id not in self.memories:
            return {
                "total_messages": 0,
                "categories": {},
                "avg_importance": 0.0,
                "most_common_keywords": []
            }
        
        user_memory = self.memories[user_id]
        
        # Thống kê theo danh mục
        categories = {}
        total_importance = 0
        all_keywords = []
        
        for entry in user_memory:
            # Thống kê danh mục
            cat = entry.category.value
            categories[cat] = categories.get(cat, 0) + 1
            
            # Tổng mức độ quan trọng
            total_importance += entry.importance_score
            
            # Thu thập từ khóa
            all_keywords.extend(entry.keywords)
        
        # Tính trung bình mức độ quan trọng
        avg_importance = total_importance / len(user_memory) if user_memory else 0.0
        
        # Lấy từ khóa phổ biến nhất
        from collections import Counter
        keyword_counts = Counter(all_keywords)
        most_common_keywords = [item[0] for item in keyword_counts.most_common(5)]
        
        return {
            "total_messages": len(user_memory),
            "categories": categories,
            "avg_importance": round(avg_importance, 2),
            "most_common_keywords": most_common_keywords
        }
    
    def clear_memory(self, user_id: str):
        """
        Xóa toàn bộ working memory của người dùng
        """
        if user_id in self.memories:
            del self.memories[user_id]
            logger.info(f"🗑️ Cleared working memory for {user_id}")
```

### Bước 4: Tạo MemoryManager

Tệp: `src/services/memory_manager.py`

```python
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime
import asyncio
import os
import json

from services.working_memory_service import WorkingMemoryService
from services.memory_background_service import MemoryBackgroundService
from services.summary_service import SummaryService

logger = logging.getLogger(__name__)

class MemoryManager:
    """
    Lớp quản lý tập trung cho cả 3 tầng bộ nhớ:
    - Working Memory (Tầng 1 - Ngắn hạn)
    - Episodic Memory (Tầng 2 - Nhật ký)
    - Core Persona (Tầng 3 - Hồ sơ cốt lõi)
    """
    
    def __init__(self, llm_service, data_dir: str):
        self.llm_service = llm_service
        self.data_dir = data_dir
        
        # Khởi tạo các tầng bộ nhớ
        self.working_memory = WorkingMemoryService(max_capacity=20, trigger_threshold=20)
        self.background_service = MemoryBackgroundService(llm_service, data_dir)
        self.core_persona = SummaryService(llm_service, 
                                         data_dir=data_dir,
                                         prompts_dir=f"{data_dir}/prompts",
                                         config_dir=f"{data_dir}/config")
        
        # Khởi tạo relationship service
        from services.relationship_service import RelationshipService
        self.relationship_service = RelationshipService(llm_service, data_dir)
        
        # Context cho từng người dùng
        self.user_contexts: Dict[str, Dict] = {}
        
        # Callback cho các trigger
        self.trigger_callbacks: List[Callable] = []
        
        # Đăng ký callback cho working memory
        self.working_memory.register_trigger_callback(self._on_working_memory_trigger)
        
        logger.info("🧠 MemoryManager initialized with 3 memory tiers")
    
    def initialize_user_context(self, user_id: str):
        """Khởi tạo context cho người dùng mới"""
        if user_id not in self.user_contexts:
            self.user_contexts[user_id] = {
                "last_activity": datetime.now(),
                "session_start": datetime.now(),
                "message_count": 0,
                "needs_persona_update": False,
                "last_episodic_update": None,
                "last_persona_update": None
            }
    
    def add_message(self, user_id: str, role: str, content: str):
        """
        Thêm tin nhắn vào hệ thống bộ nhớ
        """
        # Khởi tạo context nếu chưa có
        self.initialize_user_context(user_id)
        
        # Cập nhật thông tin context
        self.user_contexts[user_id]["last_activity"] = datetime.now()
        self.user_contexts[user_id]["message_count"] += 1
        
        # Thêm vào working memory
        entry = self.working_memory.add_message(user_id, role, content)
        
        # Ghi nhận hoạt động cho background service
        self.background_service.record_user_activity(user_id)
        
        logger.debug(f"🧠 Added message to memory for {user_id}: {content[:50]}...")
    
    def get_context(self, user_id: str) -> Dict:
        """
        Lấy toàn bộ context cho người dùng bao gồm cả 3 tầng bộ nhớ
        """
        # Lấy thông tin từ working memory
        working_context = self.working_memory.get_context(user_id, max_entries=5)
        
        # Lấy thông tin từ core persona
        core_summary = self.core_persona.get_user_summary(user_id)
        
        # Tạo context tổng hợp
        context = {
            "working_memory": [
                {
                    "role": entry.role,
                    "content": entry.content,
                    "importance": entry.importance_score,
                    "category": entry.category.value,
                    "timestamp": entry.timestamp.isoformat()
                } for entry in working_context
            ],
            "core_persona": core_summary,
            "user_stats": self.working_memory.get_statistics(user_id),
            "session_info": self.user_contexts.get(user_id, {})
        }
        
        return context
    
    def get_working_memory_context(self, user_id: str, max_entries: int = 5) -> List[Dict]:
        """
        Lấy context từ working memory
        """
        entries = self.working_memory.get_context(user_id, max_entries)
        return [
            {
                "role": entry.role,
                "content": entry.content,
                "importance": entry.importance_score,
                "category": entry.category.value
            } for entry in entries
        ]
    
    def get_core_persona(self, user_id: str) -> str:
        """
        Lấy core persona của người dùng
        """
        return self.core_persona.get_user_summary(user_id)
    
    def get_episodic_memory(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Lấy episodic memory của người dùng
        """
        # Đọc từ file episodic memory
        episodic_file = os.path.join(self.data_dir, "user_summaries", f"{user_id}_episodic.json")
        
        if not os.path.exists(episodic_file):
            return []
        
        try:
            with open(episodic_file, 'r', encoding='utf-8') as f:
                events = json.load(f)
                # Trả về các sự kiện gần nhất
                return events[-limit:] if len(events) > limit else events
        except Exception as e:
            logger.error(f"Error loading episodic memory for {user_id}: {e}")
            return []
    
    def trigger_episodic_update(self, user_id: str):
        """
        Kích hoạt cập nhật episodic memory cho người dùng
        """
        logger.info(f"🔄 Triggering episodic memory update for {user_id}")
        
        # Gọi trực tiếp phương thức cập nhật từ background service
        asyncio.create_task(self.background_service._update_episodic_memory(user_id))
    
    def trigger_persona_update(self, user_id: str):
        """
        Kích hoạt cập nhật core persona cho người dùng
        """
        logger.info(f"🔄 Triggering core persona update for {user_id}")
        
        # Gọi trực tiếp phương thức cập nhật từ background service
        asyncio.create_task(self.background_service._update_core_persona(user_id))
    
    def _on_working_memory_trigger(self, trigger_type: str, user_id: str, data: any):
        """
        Xử lý các trigger từ working memory
        """
        logger.info(f"🔔 Working memory trigger: {trigger_type} for {user_id} with data: {data}")
        
        if trigger_type == "MESSAGE_THRESHOLD_REACHED":
            # Kích hoạt cập nhật episodic memory khi đạt ngưỡng tin nhắn
            self.trigger_episodic_update(user_id)
    
    def register_trigger_callback(self, callback: Callable):
        """
        Đăng ký callback cho các trigger
        """
        self.trigger_callbacks.append(callback)
    
    def start_background_services(self):
        """
        Khởi động các dịch vụ nền
        """
        self.background_service.start()
        logger.info("🔄 Background services started")
    
    def stop_background_services(self):
        """
        Dừng các dịch vụ nền
        """
        self.background_service.stop()
        logger.info("🔄 Background services stopped")
    
    def get_memory_status(self, user_id: str) -> Dict:
        """
        Lấy trạng thái tổng quát của bộ nhớ cho người dùng
        """
        working_stats = self.working_memory.get_statistics(user_id)
        
        # Kiểm tra sự tồn tại của các file bộ nhớ
        user_summary_path = os.path.join(self.data_dir, "user_summaries", f"{user_id}_summary.txt")
        user_history_path = os.path.join(self.data_dir, "user_summaries", f"{user_id}_history.json")
        user_episodic_path = os.path.join(self.data_dir, "user_summaries", f"{user_id}_episodic.json")
        
        return {
            "working_memory": working_stats,
            "core_persona_exists": os.path.exists(user_summary_path),
            "episodic_memory_exists": os.path.exists(user_episodic_path),
            "history_exists": os.path.exists(user_history_path),
            "session_info": self.user_contexts.get(user_id, {}),
            "last_activity": self.user_contexts.get(user_id, {}).get("last_activity", None)
        }
    
    def reset_user_memory(self, user_id: str):
        """
        Đặt lại bộ nhớ cho người dùng
        """
        # Xóa khỏi working memory
        self.working_memory.clear_memory(user_id)
        
        # Xóa context người dùng
        if user_id in self.user_contexts:
            del self.user_contexts[user_id]
        
        # Xóa các file bộ nhớ
        user_summary_path = os.path.join(self.data_dir, "user_summaries", f"{user_id}_summary.txt")
        user_history_path = os.path.join(self.data_dir, "user_summaries", f"{user_id}_history.json")
        user_episodic_path = os.path.join(self.data_dir, "user_summaries", f"{user_id}_episodic.json")
        
        for path in [user_summary_path, user_history_path, user_episodic_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"🗑️ Removed memory file: {path}")
                except Exception as e:
                    logger.error(f"Error removing memory file {path}: {e}")
    
    async def force_update_all_memories(self, user_id: str):
        """
        Buộc cập nhật tất cả các tầng bộ nhớ
        """
        logger.info(f"🔄 Force updating all memories for {user_id}")
        
        # Cập nhật episodic memory
        await self.background_service._update_episodic_memory(user_id)
        
        # Cập nhật core persona
        await self.background_service._update_core_persona(user_id)
        
        logger.info(f"✅ All memories updated for {user_id}")
    
    def search_memory(self, user_id: str, query: str) -> Dict:
        """
        Tìm kiếm trong tất cả các tầng bộ nhớ
        """
        results = {}
        
        # Tìm trong working memory
        keywords = [query.lower()]  # Đơn giản hóa: chỉ tìm theo từ khóa
        working_results = self.working_memory.search_by_keywords(user_id, keywords, limit=5)
        results["working_memory"] = [
            {
                "content": entry.content,
                "role": entry.role,
                "importance": entry.importance_score,
                "category": entry.category.value,
                "timestamp": entry.timestamp.isoformat()
            } for entry in working_results
        ]
        
        # Tìm trong episodic memory
        episodic_memory = self.get_episodic_memory(user_id, limit=20)
        query_lower = query.lower()
        episodic_results = [
            event for event in episodic_memory
            if query_lower in event.get("summary", "").lower() or 
               query_lower in event.get("details", "").lower()
        ][:5]
        results["episodic_memory"] = episodic_results
        
        # Trong core persona, tìm kiếm đơn giản trong nội dung
        core_persona = self.get_core_persona(user_id)
        if query_lower in core_persona.lower():
            results["core_persona"] = {
                "found": True,
                "preview": core_persona[:200] + "..." if len(core_persona) > 200 else core_persona
            }
        else:
            results["core_persona"] = {"found": False}
        
        return results
    
    def record_priority_event(self, user_id: str, event_type: str, event_data: any = None):
        """
        Ghi nhận sự kiện ưu tiên
        """
        self.background_service.record_priority_event(user_id, event_type, event_data)
```

### Bước 5: Cập nhật LLMMessageCog

Tệp: `src/cogs/llm_message.py` (cập nhật lớp hiện tại)

```python
import logging
import os

import discord  # type: ignore
from discord.ext import commands  # type: ignore

from config.settings import Config
from services.anti_spam_service import AntiSpamService
from services.message_processor import MessageProcessor
from services.gemini_service import GeminiService
from services.lm_studio_service import LMStudioService
from services.ollama_service import OllamaService
from services.qwen_service import QwenService
from services.relationship_service import RelationshipService
from services.memory_manager import MemoryManager

logger = logging.getLogger("discord_bot.LLMMessageCog")

class LLMMessageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Initialize LLM Service based on config
        if Config.LLM_PROVIDER == "ollama":
            self.llm_service = OllamaService()
            logger.info(f"🤖 initialized with Ollama ({Config.OLLAMA_MODEL})")
        elif Config.LLM_PROVIDER == "lm_studio":
            self.llm_service = LMStudioService()
            logger.info("🤖 initialized with LM Studio")
        elif Config.LLM_PROVIDER == "qwen":
            self.llm_service = QwenService()
            logger.info("🤖 initialized with Qwen")
        else:
            self.llm_service = GeminiService()
            logger.info("🤖 initialized with Gemini")

        # Initialize MemoryManager (thay thế cho các dịch vụ riêng lẻ)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        prompts_dir = os.path.join(base_dir, "data", "prompts")
        config_dir = os.path.join(base_dir, "data", "config")
        
        self.memory_manager = MemoryManager(self.llm_service, data_dir)
        
        # Start background services
        self.memory_manager.start_background_services()

        # Initialize modular services
        self.message_processor = MessageProcessor()
        self.anti_spam = AntiSpamService()

        logger.info(
            "🤖 LLMMessageCog initialized with MemoryManager and modular services"
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        """Main message handler - only one listener!"""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # Check if should process (anti-duplicate)
        if not await self.message_processor.should_process_message(message):
            return

        # Process with lock protection
        await self.message_processor.process_with_lock(message, self._handle_message)

    async def _handle_message(self, message):
        """Internal message handling logic with 3-tier memory system"""
        # Ignore commands
        if message.content.startswith("!") or message.content.startswith("/"):
            return

        # Check if should respond
        if not self._should_respond_to_message(message):
            return

        # Clean content
        content = self._clean_message_content(message)
        if not content.strip():
            return

        user_id = str(message.author.id)

        # Process relationship data (always, regardless of response)
        # Semantic understanding of important information is handled by LLM
        await self._process_relationship_data(message, content, user_id)

        # Anti-spam check
        is_spam, cooldown_remaining = self.anti_spam.check_spam(user_id)
        if is_spam:
            spam_msg = f"🚫 **Anti-Spam**: Bạn đang gửi tin nhắn quá nhanh! Vui lòng đợi {cooldown_remaining}s."
            await message.reply(spam_msg)
            return

        # Process AI response with 3-tier memory
        await self._process_ai_response_with_memory(message, content, user_id)

    async def _process_ai_response_with_memory(self, message, content: str, user_id: str):
        """Process AI response using 3-tier memory system"""
        try:
            # Lock conversation (giữ lại cơ chế lock từ phiên bản hiện tại)
            self._set_conversation_lock(user_id)

            # Use MemoryManager to get comprehensive context
            context = self.memory_manager.get_context(user_id)
            
            # Extract relevant information from context
            working_memory_context = "\\n".join([
                f"{entry['role']}: {entry['content']}" 
                for entry in context["working_memory"]
            ])
            
            core_persona = context["core_persona"]
            user_relationships = self.memory_manager.relationship_service.get_user_relationships(user_id)

            # Build enhanced context for AI
            enhanced_context = self._build_enhanced_context_with_memory(
                user_id, core_persona, user_relationships, working_memory_context
            )

            # Generate and send response
            async with message.channel.typing():
                response = await self.llm_service.generate_response(
                    content, user_id, enhanced_context
                )
                
                if response and len(response.strip()) > 0:
                    await self.send_response_in_parts(message, response, user_id)

                    # Add both user message and bot response to memory system
                    self.memory_manager.add_message(user_id, "user", content)
                    self.memory_manager.add_message(user_id, "assistant", response)

                    # The memory manager handles all persistence automatically
                    # No need to manually save to history anymore

                else:
                    await message.reply(
                        "Xin lỗi, tôi không thể tạo phản hồi cho tin nhắn này."
                    )

        except Exception as e:
            logger.error(f"❌ Error processing AI response: {e}")
            await message.reply("Xin lỗi, đã có lỗi xảy ra khi tạo phản hồi.")

        finally:
            # Always release lock
            self._release_conversation_lock()

    def _should_respond_to_message(self, message) -> bool:
        """Determine if bot should respond to message"""
        # Always respond in DMs
        if isinstance(message.channel, discord.DMChannel):
            return True

        # In guild channels
        if hasattr(message, "guild") and message.guild:
            is_mentioned = self.bot.user.mentioned_in(message)

            # Check admin cog for channel configuration
            admin_cog = self.bot.get_cog("AdminChannels")
            is_bot_channel = (
                admin_cog.is_bot_channel(message.guild.id, message.channel.id)
                if admin_cog
                else True
            )

            # Respond if: in bot channel OR mentioned
            return is_bot_channel or is_mentioned

        return False

    def _clean_message_content(self, message) -> str:
        """Remove bot mentions from message content"""
        content = message.content
        if self.bot.user.mentioned_in(message):
            content = content.replace(f"<@{self.bot.user.id}>", "").strip()
            content = content.replace(f"<@!{self.bot.user.id}>", "").strip()
        return content

    def _build_enhanced_context_with_memory(
        self, user_id: str, core_persona: str, user_relationships: list, working_memory_context: str
    ) -> str:
        """Build enhanced context using 3-tier memory system"""
        enhanced_context = ""
        
        # Add core persona (Tier 3 - Core Persona)
        if core_persona:
            enhanced_context += f"=== NGƯỜI ĐANG NÓI CHUYỆN (USER ID: {user_id}) ===\\n{core_persona}\\n\\n"
        else:
            enhanced_context += f"=== NGƯỜI ĐANG NÓI CHUYỆN (USER ID: {user_id}) ===\\n[Chưa có thông tin]\\n\\n"

        # Add relationship information
        try:
            user_display_name = self.memory_manager.relationship_service.get_user_display_name(user_id)
            
            if user_relationships or len(user_relationships) > 0:
                enhanced_context += (
                    f"=== MỐI QUAN HỆ VÀ TƯƠNG TÁC CỦA {user_display_name} ===\\n"
                )

                if user_relationships:
                    enhanced_context += "Mối quan hệ:\\n"
                    for rel in user_relationships[:5]:  # Top 5 relationships
                        enhanced_context += (
                            f"- {rel['other_person']}: {rel['relationship_type']}\\n"
                        )

                interaction_stats = self.memory_manager.relationship_service.get_interaction_stats(user_id)
                if interaction_stats.get("top_contacts"):
                    enhanced_context += "\\nNgười liên lạc thường xuyên:\\n"
                    for contact in interaction_stats["top_contacts"][:3]:  # Top 3 contacts
                        enhanced_context += f"- {contact['name']}: {contact['interaction_count']} lần tương tác\\n"

                enhanced_context += "\\n"
        except Exception as e:
            logger.error(f"Error getting relationship context: {e}")

        # Add working memory context (Tier 1 - Working Memory)
        if working_memory_context:
            enhanced_context += (
                f"=== LỊCH SỬ HỘI THOẠI GẦN ĐÂY (TỪ WORKING MEMORY) ===\\n{working_memory_context}\\n\\n"
            )

        # Add instructions for AI
        enhanced_context += f"=== QUAN TRỌNG ===\\nBạn đang nói chuyện với USER ID {user_id}. Dựa trên thông tin từ Core Persona và Working Memory để tạo phản hồi phù hợp."

        return enhanced_context

    def _set_conversation_lock(self, user_id: str):
        """Set conversation lock (giữ lại từ phiên bản hiện tại)"""
        # Implementation cần được chuyển từ ConversationManager sang
        # hoặc giữ lại cơ chế lock đơn giản
        pass

    def _release_conversation_lock(self):
        """Release conversation lock (giữ lại từ phiên bản hiện tại)"""
        pass

    async def send_response_in_parts(self, message, response: str, user_id: str):
        """Send response with realistic typing simulation"""
        import asyncio
        import random

        # Split response by line breaks first to preserve them
        lines = response.split("\\n")

        # Check if typing simulation is enabled
        if not Config.ENABLE_TYPING_SIMULATION:
            # Send response normally without typing effect, but preserve line breaks
            for i, line in enumerate(lines):
                # Only send non-empty lines to avoid "Cannot send an empty message" error
                if line.strip():  # This checks if the line has non-whitespace content
                    if i == 0:
                        await message.reply(line)
                    else:
                        await message.channel.send(line)
                else:
                    # If we want to preserve empty lines for formatting, we can send a space or skip
                    # For now, we'll skip empty lines to prevent the error
                    continue
            return

        # Send each line with typing simulation
        for i, line in enumerate(lines):
            # Skip empty lines to avoid "Cannot send an empty message" error
            if line.strip():  # Only process lines that have non-whitespace content
                # Show typing indicator
                async with message.channel.typing():
                    # Realistic typing delay based on message length
                    typing_delay = self._calculate_typing_delay(line)
                    await asyncio.sleep(typing_delay)

                # Send the message
                if i == 0:
                    await message.reply(line)
                else:
                    await message.channel.send(line)

                # Short pause between messages (except for last one)
                if i < len(lines) - 1:
                    await asyncio.sleep(random.uniform(0.3, Config.PART_BREAK_DELAY))

    def _calculate_typing_delay(self, text: str) -> float:
        """Calculate realistic typing delay based on text length and complexity"""
        import random

        # Convert WPM to characters per second (average 5 chars per word)
        chars_per_second = (Config.TYPING_SPEED_WPM * 5) / 60

        # Add some variation for realistic feel
        chars_per_second *= random.uniform(0.8, 1.2)

        # Adjust for text complexity
        complexity_factors = {
            "emoji": len([c for c in text if ord(c) > 127])
            * 0.2,  # Emoji/unicode slow down
            "punctuation": len([c for c in text if c in ".,!?;:"])
            * 0.1,  # Punctuation pause
            "spaces": text.count(" ") * 0.05,  # Word boundaries
            "thinking": 0.5
            if any(word in text.lower() for word in ["hmm", "ờm", "à", "ủa"])
            else 0,
        }

        # Calculate base delay
        text_length = len(text)
        base_delay = text_length / chars_per_second

        # Add complexity delays
        complexity_delay = sum(complexity_factors.values())

        # Add some randomness for natural feel
        random_factor = random.uniform(0.8, 1.3)

        # Final delay with reasonable bounds
        total_delay = (base_delay + complexity_delay) * random_factor

        # Ensure delay is within configured bounds
        return max(Config.MIN_TYPING_DELAY, min(Config.MAX_TYPING_DELAY, total_delay))

    async def _process_relationship_data(self, message, content: str, user_id: str):
        """Process relationship data from message"""
        try:
            # Get author info
            author_username = message.author.display_name or message.author.name

            # Extract mentioned users
            mentioned_user_ids = []
            for mention in message.mentions:
                mentioned_user_ids.append(str(mention.id))
                # Update mentioned user's name info too
                self.memory_manager.relationship_service.update_user_name(
                    str(mention.id),
                    mention.display_name or mention.name,
                    mention.display_name
                    if mention.display_name != mention.name
                    else None,
                    mention.global_name if hasattr(mention, "global_name") else None,
                )

            # Process the message through relationship service
            # Note: Real name extraction and other semantic understanding is handled by LLM
            await self.memory_manager.relationship_service.process_message(
                user_id,
                author_username,
                content,
                mentioned_user_ids,
                str(message.channel.id) if message.channel else None,
            )

            # Check if this message contains priority information that should trigger immediate updates
            if self._contains_priority_information(content):
                self.memory_manager.record_priority_event(
                    user_id, 
                    "personal_info_update", 
                    {"content": content, "type": "potential_personal_info"}
                )

            logger.debug(
                f"🔗 Processed relationship data for {author_username} (ID: {user_id})"
            )

        except Exception as e:
            logger.error(f"❌ Error processing relationship data: {e}")
    
    def _contains_priority_information(self, content: str) -> bool:
        """Kiểm tra xem tin nhắn có chứa thông tin ưu tiên không"""
        priority_indicators = [
            "tên", "name", "tuổi", "age", "sinh nhật", "birthday",
            "thích", "like", "yêu", "love", "gì", "ơi", "ơi", "ơi",
            "bạn", "crush", "người yêu", "gf", "bf", "boyfriend", "girlfriend"
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in priority_indicators)

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        # Stop background services
        self.memory_manager.stop_background_services()
        logger.info("🔄 Memory background services stopped")

async def setup(bot):
    await bot.add_cog(LLMMessageCog(bot))
```

## 3. Các bước thực hiện

1. **Tạo nhánh mới**:
   ```bash
   git checkout -b feature/three-tier-memory-system
   ```

2. **Triển khai từng tệp theo thứ tự**:
   - Tạo `src/services/activity_monitor.py`
   - Cập nhật `src/services/memory_background_service.py`
   - Tạo `src/services/working_memory_service.py`
   - Tạo `src/services/memory_manager.py`
   - Cập nhật `src/cogs/llm_message.py`

3. **Kiểm thử từng bước**:
   - Chạy bot để đảm bảo không có lỗi cú pháp
   - Kiểm tra tính năng cơ bản
   - Kiểm tra các trigger hoạt động đúng

4. **Commit và push**:
   ```bash
   git add .
   git commit -m "feat: Implement three-tier memory system"
   git push origin feature/three-tier-memory-system
   ```

## 4. Lưu ý quan trọng

- Các tệp hiện tại sẽ cần được cập nhật để sử dụng MemoryManager thay vì các dịch vụ riêng lẻ
- Cần kiểm tra kỹ các import để đảm bảo không có lỗi
- Một số chức năng có thể cần được điều chỉnh để phù hợp với cấu trúc mới
- Cần đảm bảo backward compatibility nếu có các thành phần khác phụ thuộc vào các dịch vụ cũ

## 5. Chuyển sang chế độ Code

Để thực hiện triển khai thực tế, bạn cần chuyển sang chế độ Code để tôi có thể tạo và chỉnh sửa các tệp Python thực tế.