# src/services/memories/core_memory/storage/markdown_storage.py
"""
Markdown-based storage implementation for Core Memory.
Stores user profiles as individual markdown files.
"""
import os
import tempfile
import logging
from pathlib import Path
from typing import Optional

from .base_core_db import BaseCoreDB
from ..models import UserProfile, CoreMemoryDoc
from src.config.settings import Config

logger = logging.getLogger(__name__)


class MarkdownStorage(BaseCoreDB):
    """
    Markdown-based storage for Core Memory.
    
    Mỗi user có một file markdown riêng: `{storage_path}/{user_id}.md`
    Hỗ trợ atomic write để tránh data corruption.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Khởi tạo MarkdownStorage.
        
        Args:
            storage_path: Đường dẫn thư mục lưu trữ. Nếu None, sử dụng config.
        """
        self.storage_path = Path(storage_path or Config.CORE_MEMORY_STORAGE_PATH)
        self._ensure_storage_directory()
    
    def _ensure_storage_directory(self) -> None:
        """Tạo thư mục lưu trữ nếu chưa tồn tại."""
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Storage directory ensured: {self.storage_path}")
        except OSError as e:
            logger.error(f"Failed to create storage directory: {e}")
            raise
    
    def _get_profile_path(self, user_id: str) -> Path:
        """
        Lấy đường dẫn file profile của user.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Path object trỏ đến file markdown của user
        """
        return self.storage_path / f"{user_id}.md"
    
    def get_profile_doc(self, user_id: str) -> CoreMemoryDoc:
        """
        Đọc raw markdown document của user.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            CoreMemoryDoc chứa raw markdown content.
            Nếu chưa có profile, trả về doc rỗng.
        """
        profile_path = self._get_profile_path(user_id)
        
        if not profile_path.exists():
            logger.info(f"No profile found for user {user_id}, returning empty doc")
            return CoreMemoryDoc(user_id=user_id)
        
        try:
            content = profile_path.read_text(encoding='utf-8')
            
            # Parse metadata từ markdown (version, last_updated)
            version = 1
            last_updated = ""
            
            lines = content.split('\n')
            body_start = 0
            
            # Parse frontmatter nếu có (format: <!-- meta: key=value -->)
            for i, line in enumerate(lines):
                if line.startswith('<!-- meta:'):
                    # Parse metadata comment
                    meta_line = line[10:].rstrip(' -->').strip()
                    if '=' in meta_line:
                        key, value = meta_line.split('=', 1)
                        if key.strip() == 'version':
                            version = int(value.strip())
                        elif key.strip() == 'last_updated':
                            last_updated = value.strip()
                    body_start = i + 1
                elif line.startswith('# ') or line.startswith('## '):
                    # Reached content body
                    break
            
            # Extract body content
            body_content = '\n'.join(lines[body_start:]).strip()
            
            return CoreMemoryDoc(
                user_id=user_id,
                last_updated=last_updated or profile_path.stat().st_mtime.__str__(),
                content=body_content,
                version=version
            )
            
        except Exception as e:
            logger.error(f"Error reading profile for user {user_id}: {e}")
            return CoreMemoryDoc(user_id=user_id)
    
    def save_profile_doc(self, doc: CoreMemoryDoc) -> bool:
        """
        Lưu CoreMemoryDoc xuống file markdown với atomic write.
        
        Atomic write: write to temp file first, then rename.
        Điều này đảm bảo không bị corrupt nếu crash giữa chừng.
        
        Args:
            doc: CoreMemoryDoc để lưu
            
        Returns:
            True nếu lưu thành công, False nếu thất bại
        """
        profile_path = self._get_profile_path(doc.user_id)
        
        try:
            # Build markdown content với metadata
            content_parts = [
                f"<!-- meta: version={doc.version} -->",
                f"<!-- meta: last_updated={doc.last_updated} -->",
                "",
                doc.content
            ]
            full_content = '\n'.join(content_parts)
            
            # Atomic write: write to temp file, then rename
            # Sử dụng same directory để đảm bảo same filesystem (rename atomic)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.storage_path,
                suffix='.tmp',
                prefix=f'{doc.user_id}_'
            )
            
            try:
                # Write to temp file
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    f.write(full_content)
                
                # Atomic rename
                os.replace(temp_path, profile_path)
                logger.info(f"Successfully saved profile for user {doc.user_id}")
                return True
                
            except Exception as e:
                # Cleanup temp file on error
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
                
        except Exception as e:
            logger.error(f"Failed to save profile for user {doc.user_id}: {e}")
            return False
    
    def profile_exists(self, user_id: str) -> bool:
        """
        Kiểm tra xem user đã có profile chưa.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            True nếu user đã có profile file
        """
        return self._get_profile_path(user_id).exists()
    
    def delete_profile(self, user_id: str) -> bool:
        """
        Xóa profile của user.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            True nếu xóa thành công hoặc file không tồn tại.
            False nếu có lỗi khi xóa.
        """
        profile_path = self._get_profile_path(user_id)
        
        if not profile_path.exists():
            logger.info(f"No profile to delete for user {user_id}")
            return True
        
        try:
            profile_path.unlink()
            logger.info(f"Deleted profile for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete profile for user {user_id}: {e}")
            return False
    
    # ============ BaseCoreDB Interface Implementation ============
    
    async def get_profile(self, user_id: str) -> UserProfile:
        """
        Lấy hồ sơ của user dưới dạng UserProfile.
        Implement từ BaseCoreDB interface.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            UserProfile object. Nếu chưa có profile, trả về profile rỗng.
        """
        doc = self.get_profile_doc(user_id)
        return doc.to_user_profile()
    
    async def save_profile(self, user_id: str, profile: UserProfile) -> None:
        """
        Lưu UserProfile xuống storage.
        Implement từ BaseCoreDB interface.
        
        Note: Method này convert UserProfile sang markdown format.
        Để có control tốt hơn, nên dùng save_profile_doc() trực tiếp.
        
        Args:
            user_id: Discord user ID
            profile: UserProfile object để lưu
        """
        # Convert UserProfile to markdown
        content = self._profile_to_markdown(profile)
        
        doc = CoreMemoryDoc(
            user_id=user_id,
            content=content
        )
        
        success = self.save_profile_doc(doc)
        if not success:
            raise RuntimeError(f"Failed to save profile for user {user_id}")
    
    def _profile_to_markdown(self, profile: UserProfile) -> str:
        """
        Convert UserProfile object sang markdown format.
        
        Args:
            profile: UserProfile object
            
        Returns:
            Markdown string representation
        """
        sections = []
        
        # Định danh
        if profile.name or profile.demographics:
            sections.append("## Định danh")
            if profile.name:
                sections.append(profile.name)
            if profile.demographics:
                sections.append(f"- Nhân khẩu học: {profile.demographics}")
            sections.append("")
        
        # Vai trò xã hội
        if profile.occupation:
            sections.append("## Vai trò xã hội")
            sections.append(f"- Nghề nghiệp: {profile.occupation}")
            sections.append("")
        
        # Mối quan hệ
        if profile.relationships:
            sections.append("## Mối quan hệ")
            for item in profile.relationships:
                sections.append(f"- {item}")
            sections.append("")
        
        # Sở thích
        if profile.interests:
            sections.append("## Sở thích & Đam mê")
            for item in profile.interests:
                sections.append(f"- {item}")
            sections.append("")
        
        # Kế hoạch & Mục tiêu
        if profile.goals_and_plans:
            sections.append("## Kế hoạch & Mục tiêu")
            for item in profile.goals_and_plans:
                sections.append(f"- {item}")
            sections.append("")
        
        # Thói quen
        if profile.preferences:
            sections.append("## Thói quen")
            for item in profile.preferences:
                sections.append(f"- {item}")
            sections.append("")
        
        # Ràng buộc
        if profile.constraints:
            sections.append("## Ràng buộc")
            for item in profile.constraints:
                sections.append(f"- {item}")
            sections.append("")
        
        # Khác
        if profile.other_facts:
            sections.append("## Khác")
            for item in profile.other_facts:
                sections.append(f"- {item}")
            sections.append("")
        
        return '\n'.join(sections).strip()