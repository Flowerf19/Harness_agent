# src/services/episodic_memory/models.py
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EpisodicPayload(BaseModel):
    """
    Khuôn đúc chuẩn ép LLM phải trả về định dạng JSON này.
    Tuyệt đối không lưu text thô lộn xộn nữa.
    """

    event_title: str = Field(
        ..., description="Tiêu đề ngắn gọn tóm tắt sự kiện (Dưới 10 từ)"
    )
    detailed_summary: str = Field(
        ..., description="Tóm tắt chi tiết bối cảnh, diễn biến và kết quả của sự kiện"
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Danh sách các danh từ riêng, công nghệ, dự án, tên người liên quan",
    )
    user_sentiment: str = Field(
        default="Neutral",
        description="Trạng thái cảm xúc của user: Vui vẻ, Bức xúc, Hào hứng, Trung lập...",
    )
    resolution_status: str = Field(
        default="Resolved",
        description="Trạng thái vấn đề: Resolved (Đã xong), Unresolved (Chưa xong), Ongoing (Đang tiến hành)",
    )


class EpisodicRecord(BaseModel):
    """
    Bản ghi hoàn chỉnh sẽ được lưu thẳng vào Vector Database.
    Gộp Payload (Chữ) và Vector (Số) lại với nhau.
    """

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=get_utc_now)
    payload: EpisodicPayload = Field(...)

    # Mảng Vector được tạo ra bởi Qwen Embedding (sẽ được gán sau khi qua Semantic Engine)
    embedding: Optional[List[float]] = Field(default=None)
