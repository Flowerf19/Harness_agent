# src/services/core_memory/storage/local_yaml_db.py
import asyncio
import logging
import os
from typing import Dict

import yaml

from ..models import UserProfile
from .base_core_db import BaseCoreDB

logger = logging.getLogger(__name__)


class LocalYamlDB(BaseCoreDB):
    """
    Kho lưu trữ Profile chạy bằng YAML File.
    - Đọc từ RAM: Gần như 0 mili-giây.
    - Ghi: Bất đồng bộ (Async) an toàn qua Lock.
    - YAML dễ đọc và chỉnh sửa thủ công hơn JSON.
    """

    def __init__(self, storage_file: str = "data/memories/core_profiles.yaml"):
        self.storage_file = storage_file
        # Cache RAM: { "user_id": UserProfile }
        self._cache: Dict[str, UserProfile] = {}
        self._lock = asyncio.Lock()

        self._load_from_disk()

    def _load_from_disk(self):
        """Khởi động: Load toàn bộ YAML vào RAM."""
        if not os.path.exists(self.storage_file):
            return

        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                for uid, profile_dict in data.items():
                    # Ép kiểu YAML thành object Pydantic
                    self._cache[uid] = UserProfile.model_validate(profile_dict)
            logger.info(
                f"✅ LocalYamlDB: Đã tải Core Profile cho {len(self._cache)} users."
            )
        except Exception as e:
            logger.error(f"❌ LocalYamlDB: Lỗi đọc file cấu hình: {e}")

    async def _save_to_disk_async(self):
        """Lưu Cache xuống File một cách an toàn."""
        async with self._lock:
            try:
                os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)

                export_data = {
                    uid: profile.model_dump(
                        exclude_none=True
                    )  # Chỉ lưu các trường có dữ liệu
                    for uid, profile in self._cache.items()
                }

                with open(self.storage_file, "w", encoding="utf-8") as f:
                    yaml.dump(
                        export_data,
                        f,
                        allow_unicode=True,
                        default_flow_style=False,
                        sort_keys=False,
                    )
            except Exception as e:
                logger.error(f"❌ LocalYamlDB: Lỗi ghi file cấu hình: {e}")

    async def get_profile(self, user_id: str) -> UserProfile:
        """
        Lấy Profile hiện tại.
        Nếu user này hoàn toàn mới, tự động tạo 1 Profile trắng (Default).
        """
        if user_id not in self._cache:
            self._cache[user_id] = UserProfile()

        # Trả về 1 bản copy để tránh các class khác vô tình sửa trực tiếp vào cache RAM
        return self._cache[user_id].model_copy()

    async def save_profile(self, user_id: str, profile: UserProfile) -> None:
        """Cập nhật Profile và đồng bộ xuống đĩa."""
        self._cache[user_id] = profile
        logger.debug(f"💾 LocalYamlDB: Đang ghi đè Profile mới cho user {user_id}")
        await self._save_to_disk_async()
