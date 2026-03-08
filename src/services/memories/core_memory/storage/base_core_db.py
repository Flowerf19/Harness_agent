# src/services/core_memory/storage/base_core_db.py
from abc import ABC, abstractmethod
from typing import Optional

from ..models import UserProfile


class BaseCoreDB(ABC):
    """Giao diện chuẩn cho kho lưu trữ Core Memory."""

    @abstractmethod
    async def get_profile(self, user_id: str) -> UserProfile:
        """Lấy hồ sơ của user. Nếu chưa có thì trả về hồ sơ trống mặc định."""
        pass

    @abstractmethod
    async def save_profile(self, user_id: str, profile: UserProfile) -> None:
        """Lưu đè hồ sơ mới của user xuống DB."""
        pass
