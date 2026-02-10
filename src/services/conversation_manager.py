import logging
from datetime import datetime
from typing import Optional, List, Dict
import json
import os

logger = logging.getLogger('discord_bot.ConversationManager')

class ConversationManager:
    """Manages conversation locks, queuing, and history"""
    
    def __init__(self):
        self.currently_responding_to: Optional[str] = None
        self.response_start_time: Optional[datetime] = None
        self.pending_messages: List[Dict] = []
        self.conversation_history = {}
        self.max_history_length = 10
    
    def set_conversation_lock(self, user_id: str):
        """Lock conversation to specific user"""
        self.currently_responding_to = user_id
        self.response_start_time = datetime.utcnow()
        logger.info(f"🔒 Conversation locked to user {user_id}")
    
    def release_conversation_lock(self):
        """Release conversation lock"""
        if self.currently_responding_to:
            logger.info(f"🔓 Conversation unlocked from user {self.currently_responding_to}")
        self.currently_responding_to = None
        self.response_start_time = None
    
    def is_conversation_locked(self, user_id: str) -> bool:
        """Check if conversation is locked to someone else"""
        return self.currently_responding_to is not None and self.currently_responding_to != user_id
    
    def get_lock_duration(self) -> int:
        """Get how long conversation has been locked (in seconds)"""
        if self.response_start_time:
            return int((datetime.utcnow() - self.response_start_time).total_seconds())
        return 0
    
    def add_to_pending_queue(self, message, content: str):
        """Add message to pending queue"""
        self.pending_messages.append({
            'message': message,
            'content': content,
            'timestamp': datetime.utcnow()
        })
        logger.info(f"⏳ User {message.author.id} added to pending queue")
    
    def clear_pending_queue(self) -> int:
        """Clear pending queue and return count"""
        count = len(self.pending_messages)
        self.pending_messages.clear()
        return count
    
    def add_to_history(self, user_id: str, user_message: str, bot_response: str):
        """Add conversation to in-memory history"""
        timestamp = datetime.utcnow().isoformat()
        
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        self.conversation_history[user_id].append({
            'user': user_message,
            'bot': bot_response,
            'timestamp': timestamp
        })
        
        # Keep only recent history in memory
        if len(self.conversation_history[user_id]) > self.max_history_length:
            self.conversation_history[user_id] = self.conversation_history[user_id][-self.max_history_length:]
    
    def get_conversation_context(self, user_id: str) -> str:
        """Get recent conversation context"""
        if user_id not in self.conversation_history:
            return ""
        
        context_parts = []
        for entry in self.conversation_history[user_id][-3:]:  # Last 3 exchanges
            context_parts.append(f"User: {entry['user']}")
            context_parts.append(f"Bot: {entry['bot']}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    def save_to_persistent_history(self, user_id: str, user_message: str, bot_response: str):
        """Save conversation to persistent file storage"""
        try:
            # Get data directory
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            history_dir = os.path.join(current_dir, 'data', 'user_summaries')
            os.makedirs(history_dir, exist_ok=True)
            
            history_file = os.path.join(history_dir, f"{user_id}_history.json")
            timestamp = datetime.utcnow().isoformat()
            
            # Load existing history
            history = []
            if os.path.exists(history_file):
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except:
                    history = []
            
            # Add new messages
            history.extend([
                {
                    'role': 'user',
                    'content': user_message,
                    'timestamp': timestamp
                },
                {
                    'role': 'assistant',
                    'content': bot_response,
                    'timestamp': timestamp
                }
            ])
            
            # Keep only recent history
            if len(history) > 100:
                history = history[-100:]
            
            # Save back to file
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
                
            logger.info(f"💾 Saved conversation history for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error saving persistent history for {user_id}: {e}")
    
    def get_queue_status(self) -> dict:
        """Get queue status information"""
        pending_users = [pm['message'].author.id for pm in self.pending_messages[-3:]]
        return {
            'currently_responding_to': self.currently_responding_to,
            'lock_duration': self.get_lock_duration(),
            'pending_count': len(self.pending_messages),
            'pending_users': pending_users
        }