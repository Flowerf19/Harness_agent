import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


class TrustService:
    def __init__(self, storage):
        self.storage = storage

    def calculate_trust_score(
        self, user_id: str, relationships: Dict, interactions: Dict
    ) -> float:
        """Calculate trust score for a user based on relationship history and interactions"""
        # This is a placeholder implementation since the original code doesn't have explicit trust logic
        # In a real implementation, this would analyze relationship confidence, interaction patterns, etc.

        # Count positive vs negative relationships
        positive_count = 0
        negative_count = 0
        total_confidence = 0
        relationship_count = 0

        for rel_key, rel_data in relationships.items():
            if not isinstance(rel_data, dict):
                continue

            relationship_history = rel_data.get("relationship_history", [])
            if not isinstance(relationship_history, list) or not relationship_history:
                continue

            # Get latest relationship entry
            latest_rel = relationship_history[-1]
            if not isinstance(latest_rel, dict):
                continue

            confidence = latest_rel.get("confidence", 0.0)
            relationship_type = latest_rel.get("type", "unknown")

            # Check if this relationship involves the user
            person1 = rel_data.get("person1", "").lower()
            person2 = rel_data.get("person2", "").lower()
            user_display_name = user_id.lower()  # Simplified for now

            if user_display_name == person1 or user_display_name == person2:
                relationship_count += 1
                total_confidence += confidence

                # Classify relationship as positive or negative
                if relationship_type in ["friend", "romantic", "dating"]:
                    positive_count += 1
                elif relationship_type in ["dislike", "ex"]:
                    negative_count += 1

        # Calculate basic trust score
        if relationship_count == 0:
            return 0.5  # Neutral score

        avg_confidence = total_confidence / relationship_count
        positive_ratio = (
            positive_count / (positive_count + negative_count)
            if (positive_count + negative_count) > 0
            else 0.5
        )

        # Combine factors into trust score (0.0 to 1.0)
        trust_score = (avg_confidence * 0.6) + (positive_ratio * 0.4)
        return min(max(trust_score, 0.0), 1.0)

    def get_trust_analysis(
        self, user_id: str, user_names: Dict, relationships: Dict, interactions: Dict
    ) -> Dict:
        """Get detailed trust analysis for a user"""
        trust_score = self.calculate_trust_score(user_id, relationships, interactions)

        # Get interaction stats for additional context
        from .interaction_tracker import InteractionTracker

        interaction_tracker = InteractionTracker(self.storage)
        interaction_stats = interaction_tracker.get_interaction_stats(
            user_id, user_names
        )

        # Count active relationships
        active_relationships = 0
        for rel_data in relationships.values():
            if isinstance(rel_data, dict):
                person1 = rel_data.get("person1", "").lower()
                person2 = rel_data.get("person2", "").lower()
                if user_id.lower() == person1 or user_id.lower() == person2:
                    active_relationships += 1

        return {
            "user_id": user_id,
            "trust_score": round(trust_score, 2),
            "interaction_stats": interaction_stats,
            "analysis_timestamp": datetime.now().isoformat(),
            "factors": {
                "relationship_quality": "Based on relationship types and confidence scores",
                "interaction_frequency": f"Total interactions: {interaction_stats.get('total_interactions', 0)}",
                "social_connections": f"Active relationships: {active_relationships}",
            },
        }
