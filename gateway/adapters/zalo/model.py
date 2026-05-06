"""Zalo-specific extension models for the unified message format."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ZaloMessageExtension:
    """Extra fields that are specific to Zalo's rich message types."""

    msg_type: str = "text"
    """One of: ``"text"``, ``"photo"``, ``"sticker"``, ``"file"``."""

    sticker_id: Optional[int] = None
    """Zalo sticker identifier (only when ``msg_type == "sticker"``)."""

    photo_url: Optional[str] = None
    """URL of a photo (only when ``msg_type == "photo"``)."""

    file_url: Optional[str] = None
    """URL of a file attachment (only when ``msg_type == "file"``)."""

    def to_dict(self) -> dict:
        """Serialise to a dict suitable for ``UnifiedMessage.extensions``."""
        d: dict = {"msg_type": self.msg_type}
        if self.sticker_id is not None:
            d["sticker_id"] = self.sticker_id
        if self.photo_url is not None:
            d["photo_url"] = self.photo_url
        if self.file_url is not None:
            d["file_url"] = self.file_url
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ZaloMessageExtension":
        return cls(
            msg_type=data.get("msg_type", "text"),
            sticker_id=data.get("sticker_id"),
            photo_url=data.get("photo_url"),
            file_url=data.get("file_url"),
        )
