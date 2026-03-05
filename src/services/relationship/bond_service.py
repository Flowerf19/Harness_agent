import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BondService:
    def __init__(self, storage, interaction_tracker):
        self.storage = storage
        self.interaction_tracker = interaction_tracker

    def update_user_name(
        self,
        user_id: str,
        username: str,
        user_names: Dict,
        display_name: Optional[str] = None,
        real_name: Optional[str] = None,
    ) -> Dict:
        """Update user name information"""
        if user_id not in user_names:
            user_names[user_id] = {
                "username": username,
                "display_name": display_name,
                "real_name": real_name,
                "name_history": [username],
                "first_seen": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
            }
        else:
            # Update existing info
            user_names[user_id]["username"] = username
            if display_name:
                user_names[user_id]["display_name"] = display_name
            if real_name and real_name != user_names[user_id].get("real_name"):
                user_names[user_id]["real_name"] = real_name
                logger.info(f"📝 Real name updated for {user_id}: {real_name}")

            # Track name history
            if username not in user_names[user_id]["name_history"]:
                user_names[user_id]["name_history"].append(username)

            user_names[user_id]["last_updated"] = datetime.now().isoformat()

        return user_names

    def extract_mentioned_users(self, message_content: str) -> List[str]:
        """Extract mentioned user IDs from message content"""
        # Discord mention pattern: <@!123456789> or <@123456789>
        mention_pattern = r"<@!?(\d+)>"
        mentions = re.findall(mention_pattern, message_content)
        return mentions

    async def extract_relationship_info(
        self, message_content: str, author_id: str, llm_service
    ) -> List[Dict]:
        """Extract relationship information from message content using LLM"""
        try:
            # Create a prompt for the LLM to analyze relationships in the message
            prompt = f"""Phân tích tin nhắn sau để xác định các mối quan hệ giữa người dùng:

TIN NHẮN: {message_content}

Hãy xác định các cặp người dùng và mối quan hệ giữa họ. Trả lời theo định dạng JSON như sau:
{{
  "relationships": [
    {{
      "person1": "tên người 1",
      "person2": "tên người 2", 
      "relationship_type": "friend|crush|dislike|romantic|dating|ex|unknown",
      "confidence": 0.0-1.0,
      "context": "ngữ cảnh xác định mối quan hệ"
    }}
  ]
}}

Chỉ trả lời dưới dạng JSON, không giải thích thêm:"""

            # Call the LLM to analyze relationships
            llm_response = await llm_service.generate_response(
                prompt, "relationship_extraction"
            )

            # Parse the LLM response as JSON
            import json
            import re

            # Initialize response_json with default value
            response_json = {"relationships": []}

            # First, try to parse the entire response as JSON
            try:
                response_json = json.loads(llm_response)
            except json.JSONDecodeError:
                # If that fails, try to extract JSON from the response
                # Look for JSON between curly braces, handling nested objects
                # Using a more robust approach to find JSON objects

                # Find the first complete JSON object by tracking braces
                start_pos = llm_response.find("{")
                if start_pos != -1:
                    brace_count = 0
                    for i, char in enumerate(llm_response[start_pos:], start=start_pos):
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                json_str = llm_response[start_pos : i + 1]
                                try:
                                    response_json = json.loads(json_str)
                                    break
                                except json.JSONDecodeError:
                                    # If this JSON string fails, try to clean it up
                                    # Remove potential trailing commas before closing braces/brackets
                                    cleaned_json = re.sub(
                                        r",(\s*[}\]])", r"\1", json_str
                                    )
                                    try:
                                        response_json = json.loads(cleaned_json)
                                        break
                                    except json.JSONDecodeError:
                                        # Try to find smaller JSON objects within the response
                                        # Look for relationships array specifically
                                        rel_pattern = r'"relationships"\s*:\s*\[(?:[^[\]]|\[(?:[^[\]]|\[[^[\]]*\])*\])*\]'
                                        rel_match = re.search(
                                            rel_pattern, llm_response, re.DOTALL
                                        )
                                        if rel_match:
                                            # Extract the relationships part and wrap it in a basic object
                                            rel_content = rel_match.group()
                                            temp_json_str = "{" + rel_content + "}"
                                            try:
                                                response_json = json.loads(
                                                    temp_json_str
                                                )
                                                break
                                            except json.JSONDecodeError:
                                                # If all parsing attempts fail, return empty result
                                                response_json = {"relationships": []}
                                        else:
                                            # If still no JSON found, return empty result
                                            response_json = {"relationships": []}
                else:
                    # If no opening brace found, return empty result
                    response_json = {"relationships": []}

            relationships_found = []

            # Validate that response_json has the expected structure
            if not isinstance(response_json, dict):
                logger.warning("LLM response is not a dictionary, using fallback")
                return self._extract_relationship_info_fallback(
                    message_content, author_id
                )

            relationships_data = response_json.get("relationships", [])

            # Validate that relationships_data is a list
            if not isinstance(relationships_data, list):
                logger.warning(
                    "LLM response 'relationships' field is not a list, using fallback"
                )
                return self._extract_relationship_info_fallback(
                    message_content, author_id
                )

            # Additional validation: check if the list contains dictionaries
            if relationships_data:  # Only check if the list is not empty
                try:
                    if not isinstance(relationships_data[0], dict):
                        logger.warning(
                            "LLM response 'relationships' list doesn't contain dictionaries, using fallback"
                        )
                        return self._extract_relationship_info_fallback(
                            message_content, author_id
                        )
                except (IndexError, TypeError):
                    # Handle case where relationships_data might not be a proper list
                    logger.warning("Error accessing relationships data, using fallback")
                    return self._extract_relationship_info_fallback(
                        message_content, author_id
                    )

            for rel_data in relationships_data:
                # Validate that rel_data is a dictionary and has required fields
                if not isinstance(rel_data, dict):
                    logger.warning(
                        f"Skipping non-dictionary relationship data: {rel_data}"
                    )
                    continue

                if (
                    "person1" in rel_data
                    and "person2" in rel_data
                    and "relationship_type" in rel_data
                ):
                    # Validate that the required fields are strings
                    person1 = rel_data.get("person1")
                    person2 = rel_data.get("person2")
                    relationship_type = rel_data.get("relationship_type")

                    if not all(
                        isinstance(field, str)
                        for field in [person1, person2, relationship_type]
                    ):
                        logger.warning(
                            f"Skipping relationship with invalid field types: {rel_data}"
                        )
                        continue

                    relationships_found.append(
                        {
                            "person1": person1.strip(),
                            "person2": person2.strip(),
                            "relationship_type": relationship_type,
                            "reported_by": author_id,
                            "timestamp": datetime.now().isoformat(),
                            "context": rel_data.get("context", ""),
                            "confidence": rel_data.get(
                                "confidence", 0.7
                            ),  # Default confidence if not provided
                        }
                    )
                else:
                    logger.debug(
                        f"Skipping relationship data missing required fields: {rel_data}"
                    )

            return relationships_found

        except json.JSONDecodeError:
            logger.error(
                "Failed to parse LLM response as JSON in extract_relationship_info"
            )
            # Fallback to simple regex if LLM fails
            return self._extract_relationship_info_fallback(message_content, author_id)
        except Exception as e:
            logger.error(f"Error extracting relationship info with LLM: {e}")
            # Fallback to simple regex if LLM fails
            return self._extract_relationship_info_fallback(message_content, author_id)

    def _extract_relationship_info_fallback(
        self, message_content: str, author_id: str
    ) -> List[Dict]:
        """Fallback method using regex patterns if LLM fails"""
        relationships_found = []
        content_lower = message_content.lower()

        # Patterns để detect relationship statements
        relationship_patterns = [
            # X và Y là bạn
            r"(\w+)\s+(?:và|với)\s+(\w+)\s+(?:là|are)\s+(?:bạn|friends?|buddies?)",
            # X bạn với Y
            r"(\w+)\s+(?:bạn|friend)\s+(?:với|with)\s+(\w+)",
            # X và Y quen nhau
            r"(\w+)\s+(?:và|với)\s+(\w+)\s+(?:quen\s+nhau|know\s+each\s+other)",
            # X thích Y
            r"(\w+)\s+(?:thích|likes?|has\s+a\s+crush\s+on)\s+(\w+)",
            # X ghét Y
            r"(\w+)\s+(?:ghét|hates?|dislikes?)\s+(\w+)",
            # X là người yêu của Y
            r"(\w+)\s+(?:là\s+)?(?:người\s+yêu|boyfriend|girlfriend|partner)\s+(?:của\s+)?(\w+)",
            # X đang hẹn hò với Y
            r"(\w+)\s+(?:đang\s+)?(?:hẹn\s+hò|dating)\s+(?:với\s+)?(\w+)",
            # X chia tay với Y
            r"(\w+)\s+(?:chia\s+tay|broke\s+up)\s+(?:với\s+)?(\w+)",
        ]

        for pattern in relationship_patterns:
            matches = re.finditer(pattern, content_lower)
            for match in matches:
                person1, person2 = match.groups()

                # Determine relationship type based on pattern
                relationship_type = "unknown"
                if "bạn" in match.group() or "friend" in match.group():
                    relationship_type = "friend"
                elif (
                    "thích" in match.group()
                    or "likes" in match.group()
                    or "crush" in match.group()
                ):
                    relationship_type = "crush"
                elif "ghét" in match.group() or "hate" in match.group():
                    relationship_type = "dislike"
                elif (
                    "người yêu" in match.group()
                    or "boyfriend" in match.group()
                    or "girlfriend" in match.group()
                ):
                    relationship_type = "romantic"
                elif "hẹn hò" in match.group() or "dating" in match.group():
                    relationship_type = "dating"
                elif "chia tay" in match.group() or "broke up" in match.group():
                    relationship_type = "ex"

                relationships_found.append(
                    {
                        "person1": person1.strip(),
                        "person2": person2.strip(),
                        "relationship_type": relationship_type,
                        "reported_by": author_id,
                        "timestamp": datetime.now().isoformat(),
                        "context": match.group(),
                        "confidence": 0.5,  # Lower confidence for regex-based detection
                    }
                )

        return relationships_found

    def _add_relationship(
        self,
        person1: str,
        person2: str,
        relationship_type: str,
        reported_by: str,
        context: str,
        confidence: float,
        relationships: Dict,
    ) -> Dict:
        """Add or update a relationship"""
        # Normalize names and create a consistent key
        person1_lower = person1.lower().strip()
        person2_lower = person2.lower().strip()

        # Create sorted key to avoid duplicates (A->B vs B->A)
        if person1_lower < person2_lower:
            rel_key = f"{person1_lower}_{person2_lower}"
            persons = (person1, person2)
        else:
            rel_key = f"{person2_lower}_{person1_lower}"
            persons = (person2, person1)

        timestamp = datetime.now().isoformat()

        if rel_key not in relationships:
            relationships[rel_key] = {
                "person1": persons[0],
                "person2": persons[1],
                "relationship_history": [],
            }

        # Add relationship entry
        relationship_entry = {
            "type": relationship_type,
            "reported_by": reported_by,
            "context": context,
            "confidence": confidence,
            "timestamp": timestamp,
        }

        relationships[rel_key]["relationship_history"].append(relationship_entry)

        # Keep only recent relationship updates (last 20)
        if len(relationships[rel_key]["relationship_history"]) > 20:
            relationships[rel_key]["relationship_history"] = relationships[rel_key][
                "relationship_history"
            ][-20:]

        return relationships

    def get_user_relationships(
        self, user_identifier: str, user_names: Dict, relationships: Dict
    ) -> List[Dict]:
        """Get all relationships for a user (by ID, username, or real name)"""
        relationships_list = []

        # Find user ID from identifier
        user_id = self._resolve_user_identifier(user_identifier, user_names)
        if not user_id:
            return relationships_list

        user_display_name = self._get_user_display_name(user_id, user_names).lower()

        for rel_key, rel_data in relationships.items():
            # Validate that rel_data is a proper dictionary with required keys
            if not isinstance(rel_data, dict):
                logger.warning(f"Skipping invalid relationship data: {rel_data}")
                continue

            person1 = rel_data.get("person1", "").lower()
            person2 = rel_data.get("person2", "").lower()

            if user_display_name == person1 or user_display_name == person2:
                # Get the latest relationship status
                relationship_history = rel_data.get("relationship_history", [])
                if relationship_history and isinstance(relationship_history, list):
                    latest_rel = relationship_history[-1]
                    if not isinstance(latest_rel, dict):
                        logger.warning(
                            f"Skipping invalid relationship entry: {latest_rel}"
                        )
                        continue

                    other_person = (
                        rel_data.get("person2", "")
                        if user_display_name == person1
                        else rel_data.get("person1", "")
                    )

                    relationships_list.append(
                        {
                            "other_person": other_person,
                            "relationship_type": latest_rel.get("type", "unknown"),
                            "reported_by": latest_rel.get("reported_by", ""),
                            "context": latest_rel.get("context", ""),
                            "timestamp": latest_rel.get("timestamp", ""),
                            "confidence": latest_rel.get("confidence", 0.0),
                        }
                    )

        return relationships_list

    def search_relationships_by_keyword(
        self, keyword: str, user_names: Dict, relationships: Dict
    ) -> List[Dict]:
        """Search relationships by keyword in context"""
        results = []
        keyword_lower = keyword.lower()

        for rel_key, rel_data in relationships.items():
            # Validate that rel_data is a proper dictionary with required keys
            if not isinstance(rel_data, dict):
                logger.warning(
                    f"Skipping invalid relationship data in search: {rel_data}"
                )
                continue

            relationship_history = rel_data.get("relationship_history", [])
            if not isinstance(relationship_history, list):
                logger.warning(f"Invalid relationship history in search: {rel_data}")
                continue

            for rel_entry in relationship_history:
                # Validate that rel_entry is a proper dictionary with required keys
                if not isinstance(rel_entry, dict):
                    logger.warning(f"Skipping invalid relationship entry: {rel_entry}")
                    continue

                context = rel_entry.get("context", "")
                if keyword_lower in context.lower():
                    results.append(
                        {
                            "person1": rel_data.get("person1", ""),
                            "person2": rel_data.get("person2", ""),
                            "relationship_type": rel_entry.get("type", "unknown"),
                            "context": context,
                            "timestamp": rel_entry.get("timestamp", ""),
                            "reported_by": self._get_user_display_name(
                                rel_entry.get("reported_by", ""), user_names
                            ),
                        }
                    )

        # Sort by timestamp (newest first)
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results[:10]  # Return top 10 results

    def _resolve_user_identifier(
        self, identifier: str, user_names: Dict
    ) -> Optional[str]:
        """Resolve user identifier (ID, username, or real name) to user ID"""
        # Handle None case
        if identifier is None:
            return None

        # Handle mention format <@ID> or <@!ID>
        if identifier.startswith("<@") and identifier.endswith(">"):
            # Extract user ID from mention
            user_id = identifier[2:-1]  # Remove <@ and >
            if user_id.startswith("!"):
                user_id = user_id[1:]  # Remove ! if present (<@!ID>)
            # Check if this ID exists in our records
            if user_id in user_names:
                return user_id
            # If not in our records, return the extracted ID anyway
            return user_id

        # Direct ID match
        if identifier in user_names:
            return identifier

        # Search by username or real name
        identifier_lower = identifier.lower().strip()

        for user_id, user_info in user_names.items():
            # Check username
            if user_info.get("username", "").lower() == identifier_lower:
                return user_id

            # Check display name
            if user_info.get("display_name", "").lower() == identifier_lower:
                return user_id

            # Check real name
            if user_info.get("real_name", "").lower() == identifier_lower:
                return user_id

            # Check name history
            for name in user_info.get("name_history", []):
                if name.lower() == identifier_lower:
                    return user_id

        return None

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
