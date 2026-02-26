"""
Công cụ debug cho hệ thống 3 tầng bộ nhớ
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def debug_memory_status(memory_manager, user_id: str) -> Dict[str, Any]:
    """
    Hiển thị trạng thái của tất cả các tầng bộ nhớ cho người dùng
    """
    try:
        # Lấy trạng thái từ memory manager
        status = memory_manager.get_memory_status(user_id)

        # Lấy thêm thông tin chi tiết
        working_context = memory_manager.get_working_memory_context(
            user_id, max_entries=10
        )
        core_persona = memory_manager.get_core_persona(user_id)
        episodic_memory = memory_manager.get_episodic_memory(user_id, limit=10)

        # Lấy thông tin từ relationship service nếu có
        relationship_info = {}
        if hasattr(memory_manager, "relationship_service"):
            relationship_info = {
                "relationships": memory_manager.relationship_service.get_user_relationships(
                    user_id
                ),
                "interaction_stats": memory_manager.relationship_service.get_interaction_stats(
                    user_id
                ),
            }

        result = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "memory_status": status,
            "working_memory_sample": working_context,
            "episodic_memory_sample": episodic_memory,
            "core_persona_present": bool(core_persona),
            "relationship_info": relationship_info,
        }

        logger.info(
            f"Debug memory status for {user_id}: {json.dumps(result, indent=2, ensure_ascii=False)}"
        )
        return result

    except Exception as e:
        logger.error(f"Error getting memory status for {user_id}: {e}")
        return {"error": str(e), "user_id": user_id}


def debug_working_memory(memory_manager, user_id: str) -> Dict[str, Any]:
    """
    Hiển thị nội dung working memory hiện tại
    """
    try:
        # Lấy context từ working memory
        working_context = memory_manager.get_working_memory_context(
            user_id, max_entries=20
        )

        # Lấy thống kê
        stats = memory_manager.working_memory.get_statistics(user_id)

        result = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "entries_count": len(working_context),
            "statistics": stats,
            "entries": working_context,
        }

        logger.info(
            f"Debug working memory for {user_id}: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}..."
        )
        return result

    except Exception as e:
        logger.error(f"Error getting working memory for {user_id}: {e}")
        return {"error": str(e), "user_id": user_id}


def debug_episodic_memory(memory_manager, user_id: str) -> Dict[str, Any]:
    """
    Hiển thị các sự kiện trong episodic memory
    """
    try:
        # Lấy episodic memory
        episodic_memory = memory_manager.get_episodic_memory(user_id, limit=50)

        # Đếm theo loại sự kiện
        type_counts = {}
        category_counts = {}

        for event in episodic_memory:
            event_type = event.get("type", "unknown")
            category = event.get("category", "unknown")

            type_counts[event_type] = type_counts.get(event_type, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1

        result = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "events_count": len(episodic_memory),
            "type_distribution": type_counts,
            "category_distribution": category_counts,
            "recent_events": episodic_memory[-10:] if episodic_memory else [],
        }

        logger.info(
            f"Debug episodic memory for {user_id}: {len(episodic_memory)} events"
        )
        return result

    except Exception as e:
        logger.error(f"Error getting episodic memory for {user_id}: {e}")
        return {"error": str(e), "user_id": user_id}


def debug_core_persona(memory_manager, user_id: str) -> Dict[str, Any]:
    """
    Hiển thị nội dung core persona hiện tại
    """
    try:
        # Lấy core persona
        core_persona = memory_manager.get_core_persona(user_id)

        # Phân tích nội dung
        sections = {}
        if core_persona:
            lines = core_persona.split("\n")
            current_section = "unknown"

            for line in lines:
                line = line.strip()
                if line.startswith("===") and line.endswith("==="):
                    current_section = line.replace("===", "").strip()
                    sections[current_section] = []
                elif line and not line.startswith("==="):
                    sections[current_section].append(line)

        result = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "has_persona": bool(core_persona),
            "persona_length": len(core_persona) if core_persona else 0,
            "sections_found": list(sections.keys()) if sections else [],
            "persona_content": core_persona[:1000] + "..."
            if core_persona and len(core_persona) > 1000
            else core_persona,
        }

        logger.info(
            f"Debug core persona for {user_id}: {'Found' if core_persona else 'Not found'}"
        )
        return result

    except Exception as e:
        logger.error(f"Error getting core persona for {user_id}: {e}")
        return {"error": str(e), "user_id": user_id}


def debug_relationships(memory_manager, user_id: str) -> Dict[str, Any]:
    """
    Hiển thị các mối quan hệ của người dùng
    """
    try:
        if not hasattr(memory_manager, "relationship_service"):
            return {"error": "Relationship service not available", "user_id": user_id}

        # Lấy thông tin mối quan hệ
        relationships = memory_manager.relationship_service.get_user_relationships(
            user_id
        )
        interaction_stats = memory_manager.relationship_service.get_interaction_stats(
            user_id
        )

        # Lấy tên hiển thị
        display_name = memory_manager.relationship_service.get_user_display_name(
            user_id
        )

        result = {
            "user_id": user_id,
            "display_name": display_name,
            "timestamp": datetime.now().isoformat(),
            "relationship_count": len(relationships),
            "relationships": relationships,
            "interaction_stats": interaction_stats,
        }

        logger.info(
            f"Debug relationships for {user_id} ({display_name}): {len(relationships)} relationships"
        )
        return result

    except Exception as e:
        logger.error(f"Error getting relationships for {user_id}: {e}")
        return {"error": str(e), "user_id": user_id}


def debug_triggers(memory_manager, user_id: str) -> Dict[str, Any]:
    """
    Hiển thị trạng thái trigger của người dùng
    """
    try:
        # Lấy thông tin từ activity monitor nếu có
        if hasattr(memory_manager.background_service, "activity_monitor"):
            trigger_status = (
                memory_manager.background_service.activity_monitor.get_user_status(
                    user_id
                )
            )
        else:
            trigger_status = {"error": "Activity monitor not available"}

        # Lấy thông tin từ working memory
        working_stats = memory_manager.working_memory.get_statistics(user_id)

        result = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "trigger_status": trigger_status,
            "working_memory_stats": working_stats,
        }

        logger.info(f"Debug triggers for {user_id}: {trigger_status}")
        return result

    except Exception as e:
        logger.error(f"Error getting trigger status for {user_id}: {e}")
        return {"error": str(e), "user_id": user_id}


def get_all_debug_info(memory_manager, user_id: str) -> Dict[str, Any]:
    """
    Lấy tất cả thông tin debug cho người dùng
    """
    result = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "memory_status": debug_memory_status(memory_manager, user_id),
        "working_memory": debug_working_memory(memory_manager, user_id),
        "episodic_memory": debug_episodic_memory(memory_manager, user_id),
        "core_persona": debug_core_persona(memory_manager, user_id),
        "relationships": debug_relationships(memory_manager, user_id),
        "triggers": debug_triggers(memory_manager, user_id),
    }

    return result
