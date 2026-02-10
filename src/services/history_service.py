import json
import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class HistoryService:
    def __init__(self, summaries_dir: Optional[str] = None):
        # FIXED: Use absolute path if not provided
        if summaries_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Go to src/
            self.summaries_dir = os.path.join(base_dir, 'data', 'user_summaries')
        else:
            # Convert relative path to absolute if needed
            if not os.path.isabs(summaries_dir):
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                self.summaries_dir = os.path.join(base_dir, 'data', 'user_summaries')
            else:
                self.summaries_dir = summaries_dir
        
        logger.info(f"📁 HistoryService using directory: {self.summaries_dir}")
        os.makedirs(self.summaries_dir, exist_ok=True)

    def get_history_file_path(self, user_id: str) -> str:
        """Get history file path for user"""
        return os.path.join(self.summaries_dir, f"{user_id}_history.json")
    
    def get_summary_file_path(self, user_id: str) -> str:
        """Get summary file path for user"""
        return os.path.join(self.summaries_dir, f"{user_id}_summary.json")

    def get_history(self, user_id: str, max_turns: int = 10) -> List[Dict]:
        """Get conversation history for user"""
        history_file = self.get_history_file_path(user_id)
        
        logger.debug(f"📖 Loading history from: {history_file}")
        
        if not os.path.exists(history_file):
            logger.debug(f"📝 History file not found: {history_file}")
            return []
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            logger.debug(f"📊 Loaded {len(history)} messages for user {user_id}")
            
            # Return last N turns
            return history[-max_turns*2:] if history else []
            
        except Exception as e:
            logger.error(f"Error reading history for {user_id}: {e}")
            return []

    def append_message(self, user_id: str, role: str, content: str):
        """Add message to history"""
        history_file = self.get_history_file_path(user_id)
        
        logger.debug(f"💾 Saving message to: {history_file}")
        
        # Load existing history
        history = []
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception as e:
                logger.error(f"Error loading history: {e}")
                history = []
        
        # Add new message
        history.append({
            "role": role,
            "content": content
        })
        
        # Keep only last 50 messages to prevent file bloat
        if len(history) > 50:
            history = history[-50:]
        
        # Save updated history
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(history_file), exist_ok=True)
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"💾 Saved {len(history)} messages for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving history: {e}")

    def load_summary(self, user_id: str) -> str:
        """REALTIME: Load user summary - sync với SummaryService"""
        # Try TXT file first (SummaryService format)
        txt_summary_file = os.path.join(self.summaries_dir, f"{user_id}_summary.txt")
        if os.path.exists(txt_summary_file):
            try:
                with open(txt_summary_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    logger.debug(f"📖 Loaded TXT summary for {user_id}: {len(content)} chars")
                    return content
            except Exception as e:
                logger.error(f"Error loading TXT summary for {user_id}: {e}")
        
        # Fallback to JSON file (old format)
        json_summary_file = os.path.join(self.summaries_dir, f"{user_id}_summary.json")
        if os.path.exists(json_summary_file):
            try:
                with open(json_summary_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug(f"📖 Loaded JSON summary for {user_id}")
                return data.get('summary', '')
            except Exception as e:
                logger.error(f"Error loading JSON summary for {user_id}: {e}")
        
        logger.debug(f"📖 No summary found for {user_id}")
        return ""

    def save_summary(self, user_id: str, summary: str):
        """Save user summary"""
        summary_file = self.get_summary_file_path(user_id)
        
        try:
            data = {
                'user_id': user_id,
                'summary': summary,
                'last_updated': __import__('time').time()
            }
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving summary for {user_id}: {e}")

    def format_history_for_prompt(self, history: List[Dict]) -> str:
        """Format history for LLM prompt"""
        if not history:
            return "Chưa có lịch sử trò chuyện."
        
        formatted_lines = []
        for msg in history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            if role == 'user':
                formatted_lines.append(f"User: {content}")
            elif role == 'bot':
                formatted_lines.append(f"March: {content}")
        
        return "\n".join(formatted_lines)

    def clear_history(self, user_id: str):
        """Clear history for user"""
        history_file = self.get_history_file_path(user_id)
        
        if os.path.exists(history_file):
            try:
                os.remove(history_file)
                logger.info(f"Cleared history for user {user_id}")
            except Exception as e:
                logger.error(f"Error clearing history for {user_id}: {e}")
    
    def clear_summary(self, user_id: str):
        """Clear summary for user"""
        summary_file = self.get_summary_file_path(user_id)
        
        if os.path.exists(summary_file):
            try:
                os.remove(summary_file)
                logger.info(f"Cleared summary for user {user_id}")
            except Exception as e:
                logger.error(f"Error clearing summary for {user_id}: {e}")
    
    def _save_cleaned_history(self, user_id: str, cleaned_history: List[Dict]):
        """Save cleaned history (for compatibility)"""
        history_file = self.get_history_file_path(user_id)
        
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(cleaned_history, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved cleaned history for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving cleaned history: {e}")