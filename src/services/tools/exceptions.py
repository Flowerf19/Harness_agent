"""
Custom exceptions cho hệ thống Tool.

Các exception đặc biệt được dùng để điều khiển flow ngoài
phạm vi tool execution bình thường (VD: propagate lên handler).
"""

from src.services.tools.base_tool import ToolExecutionError


class BashExecutorUnavailableError(ToolExecutionError):
    """
    Raised khi không kết nối được đến Bash Executor trên host.

    Exception này được thiết kế để KHÔNG bị ChatCoordinator nuốt,
    mà propagate thẳng lên DiscordGatewayHandler để hiện UI
    [Khởi động] button cho user.

    Attributes:
        executor_url: URL của Bash Executor bị fail
    """

    def __init__(self, executor_url: str, message: str | None = None):
        self.executor_url = executor_url
        super().__init__(
            tool_name="execute_host_bash",
            message=message or f"Không kết nối được đến Bash Executor tại {executor_url}",
        )
