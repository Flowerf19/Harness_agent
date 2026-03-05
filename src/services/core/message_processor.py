import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger('discord_bot.MessageProcessor')

class MessageProcessor:
    """Handles message processing and duplicate prevention"""
    
    def __init__(self):
        self.processed_messages = set()
        self.processing_messages = set()
        self.message_locks = {}
        
    def create_message_key(self, message) -> str:
        """Create unique message identifier"""
        return f"{message.id}_{message.author.id}_{message.channel.id}"
    
    async def should_process_message(self, message) -> bool:
        """Check if message should be processed (anti-duplicate)"""
        message_key = self.create_message_key(message)
        
        # Check if already processed
        if message_key in self.processed_messages:
            logger.debug(f"🔄 Message {message_key} already processed")
            return False
            
        # Check if currently processing
        if message_key in self.processing_messages:
            logger.debug(f"🔄 Message {message_key} currently processing")
            return False
            
        return True
    
    async def process_with_lock(self, message, process_func):
        """Process message with lock protection"""
        message_key = self.create_message_key(message)
        
        # Create lock if not exists
        if message_key not in self.message_locks:
            self.message_locks[message_key] = asyncio.Lock()
        
        # Try to acquire lock
        if self.message_locks[message_key].locked():
            logger.debug(f"🔒 Message {message_key} lock already acquired")
            return
            
        async with self.message_locks[message_key]:
            # Double check
            if message_key in self.processed_messages:
                return
            
            # Mark as processing
            self.processing_messages.add(message_key)
            
            try:
                await process_func(message)
            finally:
                # Mark as processed and cleanup
                self.processed_messages.add(message_key)
                self.processing_messages.discard(message_key)
                self._cleanup_old_data()
    
    def _cleanup_old_data(self):
        """Clean up old processed messages and locks"""
        if len(self.processed_messages) > 500:
            old_messages = list(self.processed_messages)[:250]
            for old_msg in old_messages:
                self.processed_messages.discard(old_msg)
        
        if len(self.message_locks) > 100:
            old_locks = list(self.message_locks.keys())[:50]
            for old_lock_key in old_locks:
                if old_lock_key in self.message_locks and not self.message_locks[old_lock_key].locked():
                    del self.message_locks[old_lock_key]
    
    def get_debug_info(self) -> dict:
        """Get debug information"""
        locked_messages = [key for key, lock in self.message_locks.items() if lock.locked()]
        return {
            'processed_count': len(self.processed_messages),
            'processing_count': len(self.processing_messages),
            'locks_count': len(self.message_locks),
            'recent_processed': list(self.processed_messages)[-5:],
            'current_processing': list(self.processing_messages),
            'locked_messages': locked_messages[-5:]
        }