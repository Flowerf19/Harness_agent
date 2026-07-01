"""
UpdatePersonalityTool - Rewrite persona Markdown files or shared RULES.md.

Tool for updating bot's personality/behavior files.
OVERWRITES entire file - bot must provide full merged content.

Bot workflow:
1. Read current content from system prompt (=== NHÂN CÁCH === / === HƯỚNG DẪN ===)
2. Merge with new info
3. Call this tool with target_file and full Markdown content
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class UpdatePersonalityTool(BaseTool):
    """
    Tool for updating bot persona files.

    target_file controls the target:
    - RULES.md: Shared behavior rules for both bots
    - IDENTITY.md: Character identity
    - SOUL.md: Bot-specific communication style
    - Any other .md filename in the current bot persona directory, when provided

    Attributes:
        base_memory_path: Path to the current bot persona directory

    Example:
        tool = UpdatePersonalityTool()
        # target_file="IDENTITY.md" → current bot identity
        # target_file="SOUL.md" → current bot speech style
        # target_file="RULES.md" → shared rules
    """

    def __init__(
        self,
        base_memory_path: str = "memories",
        llm_service: Any = None,
        shared_persona_path: str | None = None,
    ):
        self.base_memory_path = base_memory_path
        self.llm_service = llm_service
        self.shared_persona_path = shared_persona_path
        logger.debug(f"UpdatePersonalityTool initialized with base_path={base_memory_path}")

    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================

    @property
    def name(self) -> str:
        return "update_personality"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "Markdown content replacing the target file.",
                },
                "target_file": {
                    "type": "string",
                    "description": "Markdown filename only, no path.",
                },
            },
            "required": ["instruction", "target_file"],
        }

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[5]

    def _resolve_base_path(self, path: str | None, default: Path) -> Path:
        if not path:
            return default
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._repo_root() / candidate
        return candidate

    def _persona_dir(self) -> Path:
        return self._resolve_base_path(self.base_memory_path, self._repo_root() / "memories")

    def _shared_persona_dir(self) -> Path:
        return self._resolve_base_path(
            self.shared_persona_path,
            self._repo_root() / "twin" / "shared" / "personas",
        )

    def _normalize_target_file(self, target_file: str | None) -> str:
        target = (target_file or "").strip()
        if not target:
            raise ValueError("Thiếu target_file.")
        if not target.lower().endswith(".md"):
            target = f"{target}.md"
        if Path(target).name != target or "/" in target or "\\" in target:
            raise ValueError("target_file chỉ được là tên file, không được chứa path.")
        if target.startswith(".") or target in {".md", "..md"}:
            raise ValueError("target_file không hợp lệ.")
        if not target.endswith(".md"):
            raise ValueError("target_file phải là file Markdown .md.")
        if target.lower() == "rules.md":
            return "RULES.md"
        if target.lower() == "identity.md":
            return "IDENTITY.md"
        if target.lower() == "soul.md":
            return "SOUL.md"
        return target

    def _target_path(self, filename: str) -> Path:
        if filename == "RULES.md":
            return self._shared_persona_dir() / filename
        return self._persona_dir() / filename

    def _read_current_content(self, file_path: str) -> str:
        """Read current file content for bot to merge."""
        try:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            return ""
        except Exception as e:
            logger.warning(f"Không thể đọc file {file_path}: {e}")
            return ""

    # ==========================================
    # EXECUTION
    # ==========================================

    async def execute(self, instruction: str, target_file: str | None = None) -> str:
        """
        Rewrite personality file with new content.

        Args:
            instruction: Full content for the file (Markdown)

        Returns:
            str: Success message with target file info
        """
        if not instruction:
            return "Lỗi: Thiếu instruction."

        target = "(unknown)"
        try:
            target = self._normalize_target_file(target_file)
            file_path = self._target_path(target)
            os.makedirs(file_path.parent, exist_ok=True)
            content = instruction if instruction.endswith("\n") else f"{instruction}\n"
            with file_path.open("w", encoding="utf-8") as f:
                f.write(content)
            if self.llm_service and hasattr(self.llm_service, "reload_persona_prompts"):
                self.llm_service.reload_persona_prompts()
            scope = "luật chung" if target == "RULES.md" else "persona"
            logger.info("✅ UpdatePersonalityTool: Đã viết lại %s", file_path)
            return f"Đã cập nhật {target} ({scope}) thành công. Áp dụng ngay cho bot hiện tại từ tin nhắn tiếp theo."

        except ValueError as e:
            return f"Lỗi: {e}"
        except Exception as e:
            logger.error(f"Lỗi khi ghi file {target}: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi ghi file: {e}", original_error=e)

    def __repr__(self) -> str:
        return f"<UpdatePersonalityTool: base_path={self.base_memory_path}>"
