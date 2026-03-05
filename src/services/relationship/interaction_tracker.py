import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class InteractionTracker:
    def __init__(self, storage):
        self.storage = storage

    def _record_interactions(
        self,
        author_id: str,
        target_user_ids: List[str],
        interaction_type: str,
        context: str = "",
    ):
        """Record interactions between users"""
        timestamp = datetime.now().isoformat()
        interactions = self.storage._load_interactions()

        for target_id in target_user_ids:
            # Create interaction key
            interaction_key = f"{author_id}_{target_id}"

            if interaction_key not in interactions:
                interactions[interaction_key] = {
                    "from_user": author_id,
                    "to_user": target_id,
                    "interactions": [],
                }

            # Add interaction
            interactions[interaction_key]["interactions"].append(
                {
                    "type": interaction_type,
                    "timestamp": timestamp,
                    "context": context[:200],  # Limit context length
                }
            )

            # Keep only recent interactions (last 100)
            if len(interactions[interaction_key]["interactions"]) > 100:
                interactions[interaction_key]["interactions"] = interactions[
                    interaction_key
                ]["interactions"][-100:]

        self.storage._save_interactions(interactions)

    def _record_conversation(
        self,
        author_id: str,
        message_content: str,
        mentioned_users: List[str],
        channel_id: Optional[str],
    ):
        """Record conversation history between users"""
        timestamp = datetime.now().isoformat()
        conversation_history = self.storage._load_conversation_history()

        # Record conversation entry
        conversation_entry = {
            "author_id": author_id,
            "message": message_content[:500],  # Limit message length
            "mentioned_users": mentioned_users,
            "channel_id": channel_id,
            "timestamp": timestamp,
        }

        # Group conversations by participants
        participants = sorted([author_id] + mentioned_users)
        conversation_key = "_".join(participants)

        if conversation_key not in conversation_history:
            conversation_history[conversation_key] = {
                "participants": participants,
                "messages": [],
            }

        conversation_history[conversation_key]["messages"].append(conversation_entry)

        # Keep only recent messages (last 50 per conversation)
        if len(conversation_history[conversation_key]["messages"]) > 50:
            conversation_history[conversation_key]["messages"] = conversation_history[
                conversation_key
            ]["messages"][-50:]

        self.storage._save_conversation_history(conversation_history)

    def get_interaction_stats(self, user_id: str, user_names: Dict) -> Dict:
        """Get interaction statistics for a user"""
        interactions = self.storage._load_interactions()

        # Count mentions and interactions
        mentions_sent = 0
        mentions_received = 0
        frequent_contacts = Counter()

        for interaction_key, interaction_data in interactions.items():
            # Validate that interaction_data is a proper dictionary with required keys
            if not isinstance(interaction_data, dict):
                logger.warning(f"Skipping invalid interaction data: {interaction_data}")
                continue

            from_user = interaction_data.get("from_user")
            to_user = interaction_data.get("to_user")
            interactions_list = interaction_data.get("interactions", [])

            if not isinstance(interactions_list, list):
                logger.warning(
                    f"Interaction data has invalid interactions list: {interaction_data}"
                )
                continue

            if from_user == user_id:
                mentions_sent += len(interactions_list)
                if to_user:
                    frequent_contacts[to_user] += len(interactions_list)
            elif to_user == user_id:
                mentions_received += len(interactions_list)

        # Get top contacts
        top_contacts = []
        for contact_id, count in frequent_contacts.most_common(5):
            contact_name = self._get_user_display_name(contact_id, user_names)
            top_contacts.append(
                {
                    "name": contact_name,
                    "user_id": contact_id,
                    "interaction_count": count,
                }
            )

        return {
            "mentions_sent": mentions_sent,
            "mentions_received": mentions_received,
            "total_interactions": mentions_sent + mentions_received,
            "top_contacts": top_contacts,
        }

    def get_conversation_summary(
        self, user1_id: str, user2_id: str, user_names: Dict, days_back: int = 7
    ) -> str:
        """Get conversation summary between two users"""
        if not user1_id or not user2_id:
            return "Không tìm thấy thông tin người dùng."

        # Find conversation between these users
        participants = sorted([user1_id, user2_id])
        conversation_key = "_".join(participants)
        conversation_history = self.storage._load_conversation_history()

        if conversation_key not in conversation_history:
            return f"Không có lịch sử trò chuyện giữa {self._get_user_display_name(user1_id, user_names)} và {self._get_user_display_name(user2_id, user_names)}."

        # Filter messages from the last N days
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_messages = []

        conversation_data = conversation_history.get(conversation_key, {})
        messages = conversation_data.get("messages", [])

        for msg in messages:
            # Validate that msg is a proper dictionary with required keys
            if not isinstance(msg, dict):
                logger.warning(f"Skipping invalid message data: {msg}")
                continue

            timestamp = msg.get("timestamp")
            if timestamp:
                try:
                    msg_date = datetime.fromisoformat(timestamp)
                    if msg_date >= cutoff_date:
                        recent_messages.append(msg)
                except ValueError:
                    logger.warning(f"Invalid timestamp format: {timestamp}")
                    continue

        if not recent_messages:
            return f"Không có cuộc trò chuyện nào trong {days_back} ngày qua giữa {self._get_user_display_name(user1_id, user_names)} và {self._get_user_display_name(user2_id, user_names)}."

        # Format conversation for summary
        conversation_text = ""
        for msg in recent_messages[-10:]:  # Last 10 messages
            author_name = self._get_user_display_name(msg["author_id"], user_names)
            conversation_text += f"{author_name}: {msg['message']}\n"

        return f"Cuộc trò chuyện gần đây giữa {self._get_user_display_name(user1_id, user_names)} và {self._get_user_display_name(user2_id, user_names)}:\n\n{conversation_text}"

    def get_user_mentions_to(self, user_id: str, target_id: str) -> List[Dict]:
        """Get mentions from one user to another"""
        if not user_id or not target_id:
            return []

        interaction_key = f"{user_id}_{target_id}"
        interactions = self.storage._load_interactions()

        if interaction_key in interactions:
            interaction_data = interactions[interaction_key]
            if isinstance(interaction_data, dict):
                return interaction_data.get("interactions", [])
            else:
                logger.warning(
                    f"Invalid interaction data for key {interaction_key}: {interaction_data}"
                )
                return []

        return []

    def _get_user_display_name(self, user_id: str, user_names: Dict) -> str:
        """Get the best display name for a user (real name > display name > username)"""
        # Handle None case
        if user_id is None:
            return "Unknown User"

        if user_id not in user_names:
            return f"User_{user_id[-4:]}"  # Fallback với 4 số cuối của ID

        user_info = user_names[user_id]

        # Ưu tiên: tên thật > display name > username
        if user_info.get("real_name"):
            return user_info["real_name"]
        elif user_info.get("display_name"):
            return user_info["display_name"]
        else:
            return user_info["username"]
