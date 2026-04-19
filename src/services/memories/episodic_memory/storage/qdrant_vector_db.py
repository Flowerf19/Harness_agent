# src/services/episodic_memory/storage/qdrant_vector_db.py
import logging
from typing import List, Tuple, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from ..models import EpisodicRecord
from .base_vector_db import BaseVectorDB

logger = logging.getLogger(__name__)


class QdrantVectorDB(BaseVectorDB):
    """
    Vector DB sử dụng Qdrant cho Episodic Memory.
    Hỗ trợ cả local mode và cloud mode (với API key).
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: Optional[str] = None,
        collection_name: str = "episodic_memory",
        vector_size: int = 1024,  # Qwen3-Embedding-0.6B default
    ):
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.vector_size = vector_size

        # Khởi tạo Async Qdrant client
        self._client = AsyncQdrantClient(
            url=url,
            api_key=api_key,
        )

    async def initialize(self) -> None:
        """Tạo collection nếu chưa tồn tại."""
        try:
            collections = await self._client.get_collections()
            existing_names = [c.name for c in collections.collections]

            if self.collection_name not in existing_names:
                await self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info(
                    f"✅ QdrantVectorDB: Đã tạo collection '{self.collection_name}'"
                )
            else:
                logger.info(
                    f"✅ QdrantVectorDB: Collection '{self.collection_name}' đã tồn tại"
                )
        except Exception as e:
            logger.error(f"❌ QdrantVectorDB: Lỗi khởi tạo collection: {e}")
            raise

    async def close(self) -> None:
        """Đóng kết nối Qdrant client."""
        await self._client.close()
        logger.info("🔴 QdrantVectorDB: Đã đóng kết nối")

    async def add_record(self, user_id: str, record: EpisodicRecord) -> None:
        if not record.embedding:
            logger.warning("⚠️ QdrantVectorDB: Từ chối lưu record không có vector!")
            return

        try:
            # Tạo point ID duy nhất kết hợp user_id và record_id
            # Dùng UUID của record làm point ID
            point_id = record.record_id

            # Payload chứa toàn bộ EpisodicRecord data + user_id để filter
            payload = {
                "user_id": user_id,
                "record_id": record.record_id,
                "timestamp": record.timestamp.isoformat(),
                "payload": record.payload.model_dump(),
            }

            await self._client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=record.embedding,
                        payload=payload,
                    )
                ],
            )
            logger.debug(
                f"💾 QdrantVectorDB: Đã lưu sự kiện '{record.payload.event_title}' cho user {user_id}"
            )
        except Exception as e:
            logger.error(f"❌ QdrantVectorDB: Lỗi lưu record: {e}")
            raise

    async def search_similar(
        self,
        user_id: str,
        query_vector: List[float],
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> List[Tuple[EpisodicRecord, float]]:
        try:
            # Search với filter theo user_id (qdrant-client 1.17+ API)
            results = await self._client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id),
                        )
                    ]
                ),
                limit=top_k,
                score_threshold=threshold,
            )

            # Convert results về List[Tuple[EpisodicRecord, float]]
            # query_points trả về QueryResponse với .points
            records_with_scores: List[Tuple[EpisodicRecord, float]] = []
            for hit in results.points:
                try:
                    payload = hit.payload
                    record = EpisodicRecord(
                        record_id=payload.get("record_id"),
                        timestamp=payload.get("timestamp"),
                        payload=payload.get("payload"),
                        embedding=query_vector,  # Không lưu embedding full trong payload
                    )
                    records_with_scores.append((record, hit.score))
                except Exception as parse_err:
                    logger.warning(
                        f"⚠️ QdrantVectorDB: Lỗi parse record từ payload: {parse_err}"
                    )
                    continue

            return records_with_scores

        except Exception as e:
            logger.error(f"❌ QdrantVectorDB: Lỗi search: {e}")
            return []

    async def get_recent_records(
        self, user_id: str, limit: int = 5
    ) -> List[EpisodicRecord]:
        try:
            # Scroll với filter theo user_id, sắp xếp theo timestamp giảm dần
            # Qdrant scroll không hỗ trợ sort, nên ta lấy nhiều hơn rồi sort trong Python
            results, _ = await self._client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id),
                        )
                    ]
                ),
                limit=100,  # Lấy nhiều hơn để sort
                with_payload=True,
                with_vectors=False,
            )

            # Sort theo timestamp giảm dần
            records: List[EpisodicRecord] = []
            for point in results:
                try:
                    payload = point.payload
                    record = EpisodicRecord(
                        record_id=payload.get("record_id"),
                        timestamp=payload.get("timestamp"),
                        payload=payload.get("payload"),
                    )
                    records.append(record)
                except Exception as parse_err:
                    logger.warning(
                        f"⚠️ QdrantVectorDB: Lỗi parse record từ payload: {parse_err}"
                    )
                    continue

            # Sort giảm dần theo timestamp
            records.sort(key=lambda x: x.timestamp, reverse=True)
            return records[:limit]

        except Exception as e:
            logger.error(f"❌ QdrantVectorDB: Lỗi get_recent_records: {e}")
            return []

    async def delete_record(self, user_id: str, record_id: str) -> None:
        try:
            # Xóa point theo ID
            # Point ID = record_id, nên ta chỉ cần xóa trực tiếp
            await self._client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[record_id],
                ),
            )
            logger.debug(
                f"🗑️ QdrantVectorDB: Đã xóa record {record_id} cho user {user_id}"
            )
        except UnexpectedResponse as e:
            if e.status_code == 404:
                logger.warning(
                    f"⚠️ QdrantVectorDB: Record {record_id} không tồn tại"
                )
            else:
                logger.error(f"❌ QdrantVectorDB: Lỗi xóa record: {e}")
        except Exception as e:
            logger.error(f"❌ QdrantVectorDB: Lỗi xóa record: {e}")