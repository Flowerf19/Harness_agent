# Kế hoạch tích hợp LLMMessageCog với hệ thống 3 tầng

## Tổng quan

Cần cập nhật [`src/cogs/llm_message.py`](src/cogs/llm_message.py:1) để sử dụng MemoryManager thay cho các dịch vụ riêng lẻ hiện tại, đồng thời tích hợp đầy đủ các tính năng của hệ thống 3 tầng.

## Mục tiêu tích hợp

1. **Thay thế các dịch vụ riêng lẻ**: Thay thế `conversation_manager`, `summary_service` bằng `memory_manager`
2. **Tích hợp luồng xử lý mới**: Sử dụng các tầng bộ nhớ một cách hiệu quả
3. **Bảo trì tính năng hiện tại**: Đảm bảo tất cả các tính năng hiện tại vẫn hoạt động
4. **Tối ưu hiệu suất**: Giảm số lần truy cập file và tăng tốc độ phản hồi

## Triển khai chi tiết

### 1. Cập nhật cấu trúc lớp LLMMessageCog

Thay đổi trong phương thức `__init__` để sử dụng MemoryManager:

```python
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

        # Initialize RelationshipService
        self.relationship_service = RelationshipService(self.llm_service, data_dir)

        # Initialize modular services
        self.message_processor = MessageProcessor()
        self.anti_spam = AntiSpamService()
        
        # Thay thế conversation_manager bằng memory_manager
        # self.conversation_manager = ConversationManager()  # Bỏ cái này

        logger.info(
            "🤖 LLMMessageCog initialized with MemoryManager and modular services"
        )
```

### 2. Cập nhật phương thức `_handle_message`

Thay đổi luồng xử lý để sử dụng MemoryManager:

```python
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
    await self._process_relationship_data(message, content, user_id)

    # Anti-spam check
    is_spam, cooldown_remaining = self.anti_spam.check_spam(user_id)
    if is_spam:
        spam_msg = f"🚫 **Anti-Spam**: Bạn đang gửi tin nhắn quá nhanh! Vui lòng đợi {cooldown_remaining}s."
        await message.reply(spam_msg)
        return

    # Check conversation lock using memory manager context
    if self._is_conversation_locked(user_id):
        duration = self._get_lock_duration()
        busy_msg = (
            f"⏳ Tôi đang trả lời người khác ({duration}s). Xin đợi một chút nhé!"
        )
        await message.reply(busy_msg)
        self._add_to_pending_queue(message, content)
        return

    # Process AI response with 3-tier memory
    await self._process_ai_response_with_memory(message, content, user_id)

def _is_conversation_locked(self, user_id: str) -> bool:
    """Check if conversation is locked using memory context"""
    # Implementation using memory manager context
    pass

def _get_lock_duration(self) -> int:
    """Get conversation lock duration"""
    # Implementation
    pass

def _add_to_pending_queue(self, message, content: str):
    """Add message to pending queue"""
    # Implementation
    pass
```

### 3. Cập nhật phương thức `_process_ai_response_with_memory`

```python
async def _process_ai_response_with_memory(self, message, content: str, user_id: str):
    """Process AI response using 3-tier memory system"""
    try:
        # Lock conversation
        self._set_conversation_lock(user_id)

        # Use MemoryManager to get comprehensive context
        context = self.memory_manager.get_context(user_id)
        
        # Extract relevant information from context
        working_memory_context = "\\n".join([
            f"{entry['role']}: {entry['content']}" 
            for entry in context["working_memory"]
        ])
        
        core_persona = context["core_persona"]
        user_relationships = self.relationship_service.get_user_relationships(user_id)

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
```

### 4. Cập nhật phương thức `_build_enhanced_context_with_memory`

```python
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
        user_display_name = self.relationship_service.get_user_display_name(user_id)
        
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

            interaction_stats = self.relationship_service.get_interaction_stats(user_id)
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
```

### 5. Cập nhật phương thức `cog_unload`

```python
def cog_unload(self):
    """Clean up when cog is unloaded"""
    # Stop background services
    self.memory_manager.stop_background_services()
    logger.info("🔄 Memory background services stopped")
```

## Tích hợp các tính năng nâng cao

### 1. Tự động cập nhật bộ nhớ

MemoryManager sẽ tự động xử lý các cập nhật định kỳ thông qua background service, không cần can thiệp từ LLMMessageCog.

### 2. Tìm kiếm trong bộ nhớ

Thêm lệnh để người dùng có thể tìm kiếm trong bộ nhớ của họ:

```python
@commands.command(name="search_memory")
async def search_memory(self, ctx, *, query: str):
    """Tìm kiếm trong bộ nhớ của bạn"""
    user_id = str(ctx.author.id)
    
    results = self.memory_manager.search_memory(user_id, query)
    
    embed = discord.Embed(title=f"Kết quả tìm kiếm cho: {query}", color=0x00ff00)
    
    # Thêm kết quả từ working memory
    if results["working_memory"]:
        wm_text = "\\n".join([
            f"• {entry['role']}: {entry['content'][:50]}..." 
            for entry in results["working_memory"][:3]
        ])
        embed.add_field(name="Working Memory", value=wm_text or "Không tìm thấy", inline=False)
    
    # Thêm kết quả từ episodic memory
    if results["episodic_memory"]:
        em_text = "\\n".join([
            f"• {event.get('summary', '')[:50]}..." 
            for event in results["episodic_memory"][:3]
        ])
        embed.add_field(name="Episodic Memory", value=em_text or "Không tìm thấy", inline=False)
    
    # Thêm thông tin từ core persona nếu tìm thấy
    if results["core_persona"]["found"]:
        cp_preview = results["core_persona"]["preview"]
        embed.add_field(name="Core Persona", value=cp_preview[:200] + "..." if len(cp_preview) > 200 else cp_preview, inline=False)
    
    await ctx.send(embed=embed)
```

### 3. Lệnh quản lý bộ nhớ

```python
@commands.command(name="memory_status")
async def memory_status(self, ctx):
    """Xem trạng thái bộ nhớ của bạn"""
    user_id = str(ctx.author.id)
    
    status = self.memory_manager.get_memory_status(user_id)
    
    embed = discord.Embed(title=f"Trạng thái bộ nhớ - {ctx.author.display_name}", color=0x00ffff)
    
    # Thêm thông tin working memory
    wm_stats = status["working_memory"]
    embed.add_field(name="Working Memory", value=f"""
    Tổng tin nhắn: {wm_stats['total_messages']}
    Mức độ quan trọng TB: {wm_stats['avg_importance']}
    Danh mục: {', '.join(wm_stats['categories'].keys())}
    """, inline=False)
    
    # Thêm thông tin các tầng khác
    embed.add_field(name="Core Persona", value="✅ Có" if status["core_persona_exists"] else "❌ Chưa có", inline=True)
    embed.add_field(name="Episodic Memory", value="✅ Có" if status["episodic_memory_exists"] else "❌ Chưa có", inline=True)
    embed.add_field(name="History", value="✅ Có" if status["history_exists"] else "❌ Chưa có", inline=True)
    
    await ctx.send(embed=embed)
```

## Lợi ích của việc tích hợp

1. **Đơn giản hóa mã nguồn**: Giảm sự phụ thuộc vào nhiều dịch vụ riêng lẻ
2. **Tích hợp liền mạch**: Các tầng bộ nhớ hoạt động đồng bộ với nhau
3. **Hiệu suất cao**: Giảm số lần truy cập file và tăng tốc độ xử lý
4. **Dễ bảo trì**: Thay đổi trong hệ thống bộ nhớ không ảnh hưởng đến LLMMessageCog
5. **Tính năng mở rộng**: Dễ dàng thêm các tính năng mới liên quan đến bộ nhớ

## Các điểm cần lưu ý khi triển khai

1. **Tương thích ngược**: Đảm bảo các phương thức hiện tại vẫn hoạt động
2. **Xử lý lỗi**: Có cơ chế fallback nếu MemoryManager gặp sự cố
3. **Hiệu suất**: Không làm chậm luồng xử lý chính của bot
4. **Thread safety**: Đảm bảo an toàn khi truy cập từ nhiều luồng