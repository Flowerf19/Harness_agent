import yaml

from twin.evernight.a2a.card import build_agent_card as build_evernight_card
from twin.evernight.a2a.handlers import EvernightA2AHandler
from twin.march7.a2a.card import build_agent_card as build_march7_card
from twin.march7.a2a.handlers import March7A2AHandler


def test_march7_agent_card_matches_registered_a2a_handlers():
    card_skill_ids = {skill["id"] for skill in build_march7_card().skills}
    registered_skill_ids = {
        "chat": March7A2AHandler.handle_chat_task,
        "get_snapshot": March7A2AHandler.handle_get_snapshot,
        "clear_session": March7A2AHandler.handle_clear_session,
    }

    assert card_skill_ids == set(registered_skill_ids)


def test_evernight_agent_card_matches_registered_a2a_handlers():
    card_skill_ids = {skill["id"] for skill in build_evernight_card().skills}
    registered_skill_ids = {
        "chat": EvernightA2AHandler.handle_chat_task,
        "consolidate": EvernightA2AHandler.handle_consolidate_task,
        "consolidate_discussion": EvernightA2AHandler.handle_consolidate_discussion_task,
    }

    assert card_skill_ids == set(registered_skill_ids)


def test_agent_a2a_ports_are_internal_only_in_compose():
    for compose_path, service_name, expected_port in (
        ("docker/march7/docker-compose.yml", "march7", "8000"),
        ("docker/evernight/docker-compose.yml", "evernight", "8001"),
    ):
        with open(compose_path, encoding="utf-8") as f:
            service = yaml.safe_load(f)["services"][service_name]

        assert service.get("ports") in (None, [])
        assert expected_port in {str(port) for port in service["expose"]}
