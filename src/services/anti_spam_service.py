import logging
from datetime import datetime, timedelta
from typing import Tuple

logger = logging.getLogger('discord_bot.AntiSpamService')

class AntiSpamService:
    """Handles anti-spam protection"""
    
    def __init__(self, max_messages_per_minute: int = 5, cooldown_duration: int = 30):
        self.user_message_times = {}
        self.spam_cooldowns = {}
        self.max_messages_per_minute = max_messages_per_minute
        self.spam_cooldown_duration = cooldown_duration
    
    def check_spam(self, user_id: str) -> Tuple[bool, int]:
        """Check if user is spamming. Returns (is_spam, remaining_cooldown)"""
        current_time = datetime.utcnow()
        
        # Check if user is in cooldown
        if user_id in self.spam_cooldowns:
            cooldown_end = self.spam_cooldowns[user_id]
            if current_time < cooldown_end:
                remaining = int((cooldown_end - current_time).total_seconds())
                return True, remaining
            else:
                del self.spam_cooldowns[user_id]
        
        # Initialize and clean old message times
        if user_id not in self.user_message_times:
            self.user_message_times[user_id] = []
        
        one_minute_ago = current_time - timedelta(minutes=1)
        self.user_message_times[user_id] = [
            msg_time for msg_time in self.user_message_times[user_id] 
            if msg_time > one_minute_ago
        ]
        
        # Add current message time
        self.user_message_times[user_id].append(current_time)
        
        # Check if exceeds limit
        if len(self.user_message_times[user_id]) > self.max_messages_per_minute:
            cooldown_end = current_time + timedelta(seconds=self.spam_cooldown_duration)
            self.spam_cooldowns[user_id] = cooldown_end
            logger.warning(f"🚫 User {user_id} spam detected! {self.spam_cooldown_duration}s cooldown")
            return True, self.spam_cooldown_duration
        
        return False, 0