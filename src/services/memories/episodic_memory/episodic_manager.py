# src/services/memories/episodic_memory/episodic_manager.py
"""
Episodic Manager - Tầng 2 của hệ thống trí nhớ.
Quản lý bộ nhớ dài hạn sử dụng vector embeddings.
"""

import logging
from typing import List

from langsmith import traceable

from .extraction.event_extractor import EventExtractor
from .extraction.retrieval.context_formatter import ContextFormatter
from .extraction.retrieval.vector_engine import VectorEngine
from .storage.base_vector_db import BaseVectorDB

logger = logging.getLogger(__name__)


class EpisodicManager:
    """
    Facade Tổng Chỉ Huy của Tầng 2 (Episodic Memory).
    Điều phối luồng Ghi (Trích xuất -> Nhúng -> Lưu) và luồng Đọc (Nhúng Query -> Tìm kiếm -> Format).
    """

    def __init__(
        self,
        extractor: EventExtractor,
        vector_engine: VectorEngine,
        storage: BaseVectorDB,
    ):
        self.extractor = extractor
        self.vector_engine = vector_engine
        self.storage = storage

    @traceable(
        name="T2_Ingest_Snapshot",
        run_type="chain",
        tags=["tier_2", "episodic_memory", "write_pipeline"],
    )
    async def ingest_snapshot(self, user_id: str, snapshot: List[dict]) -> bool:
        """
        Luồng Ghi: Khi Tầng 1 báo đầy RAM, nó sẽ gửi snapshot sang đây.
        """
        logger.info(f"⏳ T2 EpisodicManager: Đang xử lý Snapshot cho user {user_id}...")

        # 1. Gọi LLM bóc tách đoạn chat lộn xộn thành JSON chuẩn mực
        payload = await self.extractor.extract_event(snapshot)
        if not payload:
            logger.warning(
                "⚠️ T2 EpisodicManager: Trích xuất sự kiện thất bại, hủy bỏ lưu trữ."
            )
            return False

        # 2. Nhúng `detailed_summary` thành mảng Vector
        record = await self.vector_engine.create_record(payload)
        if not record:
            logger.warning(
                "⚠️ T2 EpisodicManager: Nhúng Vector thất bại, hủy bỏ lưu trữ."
            )
            return False

        # 3. Lưu xuống Vector Database
        await self.storage.add_record(user_id, record)
        logger.info(
            f"✅ T2 EpisodicManager: Đã đóng gói thành công Ký ức: '{payload.event_title}'"
        )
        return True

    @traceable(
        name="T2_Retrieve_Context",
        run_type="chain",
        tags=["tier_2", "episodic_memory", "read_pipeline"],
    )
    async def retrieve_past_context(self, user_id: str, current_query: str) -> str:
        """
        Luồng Đọc: Tìm kiếm quá khứ dựa trên câu hỏi hiện tại.
        Trả về một chuỗi văn bản đã được format đẹp đẽ cho LLM.
        """
        # 1. Nhúng câu hỏi của User thành Vector
        query_vector = await self.vector_engine.embed_query(current_query)
        if not query_vector:
            return ""

        # 2. Tìm kiếm Top 3 ký ức giống nhất trong Database
        # Giới hạn ngưỡng threshold (VD: 0.5) để tránh lấy các ký ức không liên quan
        similar_records = await self.storage.search_similar(
            user_id=user_id, query_vector=query_vector, top_k=3, threshold=0.4
        )

        if not similar_records:
            return ""

        logger.info(
            f"🔍 T2 EpisodicManager: Đã tìm thấy {len(similar_records)} ký ức liên quan."
        )

        # 3. Format List[JSON] thành 1 chuỗi Text mượt mà
        formatted_context = ContextFormatter.format_for_llm(similar_records)
        return formatted_context
