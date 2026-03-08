# src/services/episodic_memory/storage/local_vector_db.py
import json
import logging
import os
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

from ..models import EpisodicRecord
from .base_vector_db import BaseVectorDB

logger = logging.getLogger(__name__)


class LocalVectorDB(BaseVectorDB):
    """
    Vector DB in-memory chạy bằng Numpy.
    Có cơ chế tự động save/load xuống file JSON để giữ tính vĩnh cửu (Persistence).
    """

    def __init__(self, storage_file: str = "memory_data/episodic_vectors.json"):
        self.storage_file = storage_file
        # Cấu trúc: { user_id: [EpisodicRecord, ...] }
        self._db: Dict[str, List[EpisodicRecord]] = defaultdict(list)
        self._load_from_disk()

    def _save_to_disk(self):
        """Lưu toàn bộ DB xuống JSON. Pydantic model_dump() làm việc này cực dễ."""
        try:
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            export_data = {
                uid: [record.model_dump() for record in records]
                for uid, records in self._db.items()
            }
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ LocalVectorDB: Lỗi lưu file: {e}")

    def _load_from_disk(self):
        """Tải DB từ JSON lên RAM lúc khởi động."""
        if not os.path.exists(self.storage_file):
            return
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                import_data = json.load(f)
                for uid, raw_records in import_data.items():
                    # model_validate ép kiểu ngược từ JSON thành Object chuẩn
                    self._db[uid] = [
                        EpisodicRecord.model_validate(r) for r in raw_records
                    ]
            logger.info(f"✅ LocalVectorDB: Đã tải dữ liệu cho {len(self._db)} users.")
        except Exception as e:
            logger.error(f"❌ LocalVectorDB: Lỗi đọc file (File có thể bị hỏng): {e}")

    async def add_record(self, user_id: str, record: EpisodicRecord) -> None:
        if not record.embedding:
            logger.warning("⚠️ LocalVectorDB: Từ chối lưu record không có vector!")
            return

        self._db[user_id].append(record)
        self._save_to_disk()
        logger.debug(
            f"💾 LocalVectorDB: Đã lưu sự kiện '{record.payload.event_title}' cho user {user_id}"
        )

    async def search_similar(
        self,
        user_id: str,
        query_vector: List[float],
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> List[Tuple[EpisodicRecord, float]]:

        records = self._db.get(user_id, [])
        if not records:
            return []

        # 1. Chuẩn bị Vector Toán học
        try:
            q_vec = np.array(query_vector, dtype=np.float32)
            db_vecs = np.array([r.embedding for r in records], dtype=np.float32)

            # CHỐNG LỖI: Kiểm tra số chiều (Dimensionality Mismatch)
            if q_vec.shape[0] != db_vecs.shape[1]:
                logger.error(
                    f"❌ LocalVectorDB: Sai số chiều! Query: {q_vec.shape[0]}, DB: {db_vecs.shape[1]}"
                )
                return []

        except Exception as e:
            logger.error(f"❌ LocalVectorDB: Lỗi chuyển đổi Numpy: {e}")
            return []

        # 2. Tính Cosine Similarity hàng loạt siêu nhanh
        # Công thức: dot(A, B) / (norm(A) * norm(B))
        q_norm = np.linalg.norm(q_vec)
        db_norms = np.linalg.norm(db_vecs, axis=1)

        # CHỐNG LỖI: Tránh chia cho 0 nếu vector rỗng toàn số 0
        valid_indices = (db_norms != 0) & (q_norm != 0)

        similarities = np.zeros(len(records), dtype=np.float32)
        if valid_indices.any():
            dot_products = np.dot(db_vecs[valid_indices], q_vec)
            similarities[valid_indices] = dot_products / (
                db_norms[valid_indices] * q_norm
            )

        # 3. Lọc và Sắp xếp
        results = []
        for idx, sim in enumerate(similarities):
            sim_score = float(sim)
            if sim_score >= threshold:
                results.append((records[idx], sim_score))

        # Sort giảm dần theo điểm
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def get_recent_records(
        self, user_id: str, limit: int = 5
    ) -> List[EpisodicRecord]:
        records = self._db.get(user_id, [])
        # Sắp xếp mới nhất lên đầu
        sorted_records = sorted(records, key=lambda x: x.timestamp, reverse=True)
        return sorted_records[:limit]

    async def delete_record(self, user_id: str, record_id: str) -> None:
        if user_id in self._db:
            initial_len = len(self._db[user_id])
            self._db[user_id] = [
                r for r in self._db[user_id] if r.record_id != record_id
            ]
            if len(self._db[user_id]) < initial_len:
                self._save_to_disk()
