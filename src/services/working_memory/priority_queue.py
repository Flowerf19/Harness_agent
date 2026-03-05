import logging
from datetime import datetime
from typing import Tuple

from src.services.working_memory.context_manager import (
    MessageCategory,
    WorkingMemoryEntry,
)

logger = logging.getLogger(__name__)


class PriorityQueue:
    """
    Service for handling priority queue operations for working memory entries.
    Evaluates importance scores and categorizes messages based on content analysis.
    """

    def __init__(self):
        pass

    def evaluate_importance(
        self, content: str, role: str
    ) -> Tuple[float, MessageCategory]:
        """
        Evaluate the importance of a message based on:
        - Role (user/assistant)
        - Message length
        - Content analysis (simple keyword-based)

        Simple but effective logic:
        1. Prioritize sensitive information detection
        2. Detect questions
        3. Categorize content based on characteristic keywords
        """
        importance = 0.5  # Default level
        category = MessageCategory.GENERAL

        # Convert content to lowercase for case-insensitive comparison
        content_lower = content.lower()

        # Increase importance if it's a user message (+0.2)
        if role == "user":
            importance += 0.2

        # Increase importance if message is long (+0.1)
        if len(content) > 50:  # Messages longer than 50 characters
            importance += 0.1

        # === SIMPLE CONTENT ANALYSIS ===

        # 1. Sensitive information (highest priority) (+0.4)
        sensitive_keywords = ["mật khẩu", "password", "token", "key", "secret"]
        if any(keyword in content_lower for keyword in sensitive_keywords):
            return min(importance + 0.4, 1.0), MessageCategory.FACT

        # 2. Questions (+0.2)
        if "?" in content:
            return min(importance + 0.2, 1.0), MessageCategory.QUERY

        # 3. Personal information (+0.3)
        personal_keywords = [
            "tôi tên",
            "tên tôi",
            "tuổi",
            "sinh năm",
            "sống ở",
            "làm việc tại",
            "nghề",
        ]
        if any(keyword in content_lower for keyword in personal_keywords):
            return min(importance + 0.3, 1.0), MessageCategory.FACT

        # 4. Preferences (+0.25)
        preference_keywords = ["thích", "yêu", "đam mê", "sở thích", "hobby", "ước mơ"]
        if any(keyword in content_lower for keyword in preference_keywords):
            return min(importance + 0.25, 1.0), MessageCategory.PREFERENCE

        # 5. Goals (+0.25)
        goal_keywords = ["mục tiêu", "kế hoạch", "dự định", "muốn", "hy vọng", "sẽ"]
        if any(keyword in content_lower for keyword in goal_keywords):
            return min(importance + 0.25, 1.0), MessageCategory.GOAL

        # 6. Relationships (+0.2)
        relationship_keywords = [
            "gia đình",
            "bạn bè",
            "đồng nghiệp",
            "sếp",
            "người thân",
        ]
        if any(keyword in content_lower for keyword in relationship_keywords):
            return min(importance + 0.2, 1.0), MessageCategory.RELATIONSHIP

        # Return default values
        return min(importance, 1.0), category

    def update_entry_priority(self, entry: WorkingMemoryEntry, content: str, role: str):
        """
        Update an entry's importance score and category based on content analysis.
        """
        importance_score, category = self.evaluate_importance(content, role)
        entry.importance_score = importance_score
        entry.category = category
        return entry
