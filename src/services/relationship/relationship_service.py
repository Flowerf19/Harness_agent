import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiofiles
from Arize_Phoenix_tool_kit import track_general_step

from .bond_service import BondService
from .interaction_tracker import InteractionTracker
from .relationship_storage import RelationshipStorage
from .trust_service import TrustService

logger = logging.getLogger(__name__)


class RelationshipService:
    def __init__(self, llm_service, data_dir: str):
        self.llm_service = llm_service
        self.data_dir = data_dir

        # Initialize storage and services
        self.storage = RelationshipStorage(data_dir)
        self.interaction_tracker = InteractionTracker(self.storage)
        self.bond_service = BondService(self.storage, self.interaction_tracker)
        self.trust_service = TrustService(self.storage)

        # Load existing data
        self.relationships = self.storage._load_relationships()
        self.user_names = self.storage._load_user_names()
        self.interactions = self.storage._load_interactions()
        self.conversation_history = self.storage._load_conversation_history()

        logger.info(
            f"🔗 RelationshipService initialized with {len(self.relationships)} relationships"
        )

    async def update_server_relationships_summary(self):
        """Auto-generate and update server_relationships.txt with AI-generated summary"""
        summary_data = self.get_all_users_summary()
        await self.storage.update_server_relationships_summary(
            self.llm_service, summary_data
        )

    async def auto_update_server_summary_on_change(self):
        """Call this after any relationship/interactions update to keep server_relationships.txt fresh."""
        await self.update_server_relationships_summary()

    def update_user_name(
        self,
        user_id: str,
        username: str,
        display_name: Optional[str] = None,
        real_name: Optional[str] = None,
    ):
        """Update user name information"""
        self.user_names = self.bond_service.update_user_name(
            user_id, username, self.user_names, display_name, real_name
        )
        self.storage._save_user_names(self.user_names)

    def get_user_display_name(self, user_id: str) -> str:
        """Get the best display name for a user (real name > display name > username)"""
        return self.interaction_tracker._get_user_display_name(user_id, self.user_names)

    def extract_mentioned_users(self, message_content: str) -> List[str]:
        """Extract mentioned user IDs from message content"""
        return self.bond_service.extract_mentioned_users(message_content)

    @track_general_step(step_name="Relationship: Extract Info")
    async def extract_relationship_info(
        self, message_content: str, author_id: str
    ) -> List[Dict]:
        """Extract relationship information from message content using LLM"""
        return await self.bond_service.extract_relationship_info(
            message_content, author_id, self.llm_service
        )

    @track_general_step(step_name="Relationship: Process Message")
    async def process_message(
        self,
        author_id: str,
        author_username: str,
        message_content: str,
        mentioned_user_ids: Optional[List[str]] = None,
        channel_id: Optional[str] = None,
    ):
        """Process a message to extract and update relationship information"""

        # Update author's name info
        self.update_user_name(author_id, author_username)

        # Extract mentions from message if not provided
        if mentioned_user_ids is None:
            mentioned_user_ids = self.extract_mentioned_users(message_content)

        # Record mentions/interactions
        if mentioned_user_ids:
            self.interaction_tracker._record_interactions(
                author_id, mentioned_user_ids, "mention", message_content
            )
            # Reload interactions after recording
            self.interactions = self.storage._load_interactions()

        # Extract relationship info from message content
        relationships_found = await self.extract_relationship_info(
            message_content, author_id
        )

        # Process found relationships
        for rel_info in relationships_found:
            self.relationships = self.bond_service._add_relationship(
                rel_info["person1"],
                rel_info["person2"],
                rel_info["relationship_type"],
                rel_info["reported_by"],
                rel_info["context"],
                rel_info["confidence"],
                self.relationships,
            )

        # Save relationships after adding
        self.storage._save_relationships(self.relationships)

        # Record conversation for history
        self.interaction_tracker._record_conversation(
            author_id, message_content, mentioned_user_ids, channel_id
        )
        # Reload conversation history after recording
        self.conversation_history = self.storage._load_conversation_history()

        logger.debug(
            f"🔗 Processed message from {author_username}: {len(relationships_found)} relationships, {len(mentioned_user_ids)} mentions"
        )

    def get_user_relationships(self, user_identifier: str) -> List[Dict]:
        """Get all relationships for a user (by ID, username, or real name)"""
        return self.bond_service.get_user_relationships(
            user_identifier, self.user_names, self.relationships
        )

    def get_interaction_stats(self, user_identifier: str) -> Dict:
        """Get interaction statistics for a user"""
        user_id = self.bond_service._resolve_user_identifier(
            user_identifier, self.user_names
        )
        if not user_id:
            return {}
        return self.interaction_tracker.get_interaction_stats(user_id, self.user_names)

    def get_conversation_summary(
        self, user1_identifier: str, user2_identifier: str, days_back: int = 7
    ) -> str:
        """Get conversation summary between two users"""
        user1_id = self.bond_service._resolve_user_identifier(
            user1_identifier, self.user_names
        )
        user2_id = self.bond_service._resolve_user_identifier(
            user2_identifier, self.user_names
        )
        return self.interaction_tracker.get_conversation_summary(
            user1_id, user2_id, self.user_names, days_back
        )

    @track_general_step(step_name="Relationship: Generate Analysis")
    async def generate_relationship_analysis(self, user_identifier: str) -> str:
        """Generate AI analysis of user's relationships"""
        user_id = self.bond_service._resolve_user_identifier(
            user_identifier, self.user_names
        )
        if not user_id:
            return "Không tìm thấy thông tin người dùng."

        user_name = self.get_user_display_name(user_id)
        relationships = self.get_user_relationships(user_identifier)
        interaction_stats = self.get_interaction_stats(user_identifier)

        if not relationships and not interaction_stats.get("total_interactions", 0):
            return f"Chưa có thông tin về mối quan hệ của {user_name}."

        # Prepare data for AI analysis
        analysis_prompt = f"""Phân tích mối quan hệ của {user_name} dựa trên thông tin sau:

THÔNG TIN NGƯỜI DÙNG: {user_name} (ID: {user_id})

CÁC MỐI QUAN HỆ:
"""

        for rel in relationships:
            analysis_prompt += f"- {rel['other_person']}: {rel['relationship_type']} (độ tin cậy: {rel['confidence']}, được báo cáo bởi: {self.get_user_display_name(rel['reported_by'])})\n"

        analysis_prompt += f"""
THỐNG KÊ TƯƠNG TÁC:
- Mentions gửi đi: {interaction_stats.get("mentions_sent", 0)}
- Mentions nhận được: {interaction_stats.get("mentions_received", 0)}
- Tổng tương tác: {interaction_stats.get("total_interactions", 0)}

NGƯỜI LIÊN LẠC THƯỜNG XUYÊN:
"""

        for contact in interaction_stats.get("top_contacts", []):
            analysis_prompt += (
                f"- {contact['name']}: {contact['interaction_count']} lần tương tác\n"
            )

        analysis_prompt += """
Hãy phân tích và đưa ra nhận xét về:
1. Tính cách xã hội của người này
2. Mối quan hệ chính và tần suất tương tác
3. Đánh giá tổng quan về network xã hội
4. Gợi ý về cách cải thiện mối quan hệ (nếu có)

Trả lời bằng tiếng Việt, ngắn gọn và dễ hiểu:"""

        try:
            analysis = await self.llm_service.generate_response(
                analysis_prompt, user_id
            )
            return f"📊 **Phân tích mối quan hệ của {user_name}:**\n\n{analysis}"
        except Exception as e:
            logger.error(f"Error generating relationship analysis: {e}")
            return f"Không thể tạo phân tích cho {user_name} lúc này."

    def _resolve_user_identifier(self, identifier: str) -> Optional[str]:
        """Resolve user identifier (ID, username, or real name) to user ID"""
        return self.bond_service._resolve_user_identifier(identifier, self.user_names)

    def search_relationships_by_keyword(self, keyword: str) -> List[Dict]:
        """Search relationships by keyword in context"""
        return self.bond_service.search_relationships_by_keyword(
            keyword, self.user_names, self.relationships
        )

    def get_user_mentions_to(
        self, user_identifier: str, target_identifier: str
    ) -> List[Dict]:
        """Get mentions from one user to another"""
        user_id = self._resolve_user_identifier(user_identifier)
        target_id = self._resolve_user_identifier(target_identifier)
        return self.interaction_tracker.get_user_mentions_to(user_id, target_id)

    def get_all_users_summary(self) -> Dict:
        """Get summary of all tracked users"""
        summary = {
            "total_users": len(self.user_names),
            "total_relationships": len(self.relationships),
            "total_interactions": sum(
                len(data.get("interactions", []))
                for data in self.interactions.values()
                if isinstance(data, dict)
                and "interactions" in data
                and isinstance(data.get("interactions"), list)
            ),
            "users": [],
        }

        for user_id, user_info in self.user_names.items():
            user_summary = {
                "user_id": user_id,
                "display_name": self.get_user_display_name(user_id),
                "username": user_info.get("username", ""),
                "real_name": user_info.get("real_name", ""),
                "first_seen": user_info.get("first_seen", ""),
                "relationship_count": len(self.get_user_relationships(user_id)),
                "interaction_stats": self.get_interaction_stats(user_id),
            }
            summary["users"].append(user_summary)

        # Sort users by total interactions
        summary["users"].sort(
            key=lambda x: x["interaction_stats"].get("total_interactions", 0),
            reverse=True,
        )

        return summary
