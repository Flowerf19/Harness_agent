"""System Gateway capability constants."""

ACTION_SYSTEM_STATUS = "system.status"
ACTION_DISK_USAGE = "system.disk_usage"
ACTION_DOCKER_LIST_CONTAINERS = "docker.list_containers"
ACTION_DOCKER_CONTAINER_LOGS = "docker.container_logs"
ACTION_SERVICE_STATUS = "service.status"

READ_ONLY_ACTIONS = (
    ACTION_SYSTEM_STATUS,
    ACTION_DISK_USAGE,
    ACTION_DOCKER_LIST_CONTAINERS,
    ACTION_DOCKER_CONTAINER_LOGS,
    ACTION_SERVICE_STATUS,
)
