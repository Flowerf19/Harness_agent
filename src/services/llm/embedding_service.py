# src/services/llm/embedding_service.py
import asyncio
import logging
import os
from typing import List

import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Đường dẫn cache cho models
MODEL_CACHE_DIR = os.path.join(os.path.dirname(__file__), "../../models")


class LocalEmbeddingService:
    """
    Trạm Nhúng Vector (Embedding Service).
    Sử dụng mô hình local (VD: Qwen/Qwen3-Embedding-0.6B) để biến Text thành Vector.
    """

    def __init__(self, model_name: str = "Qwen/Qwen3-Embedding-0.6B"):
        self.model_name = model_name
        self.model = None
        self.cache_dir = os.path.abspath(MODEL_CACHE_DIR)

    def _get_device(self) -> str:
        """Kiểm tra và trả về device phù hợp (CUDA/ROCm hoặc CPU)."""
        if torch.cuda.is_available():
            device = "cuda"
            logger.info(f"🎮 GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            logger.info("💻 Using CPU device")
        return device

    async def initialize(self):
        """Khởi tạo model với cache_dir và device phù hợp."""
        # Tạo thư mục cache nếu chưa có
        os.makedirs(self.cache_dir, exist_ok=True)

        device = self._get_device()
        logger.info(f"🔍 Using device: {device}")
        logger.info(f"📁 Model cache directory: {self.cache_dir}")
        logger.info(f"⏳ Đang tải mô hình Embedding local: '{self.model_name}'...")

        try:
            # Qwen models thường yêu cầu trust_remote_code=True
            self.model = SentenceTransformer(
                self.model_name,
                cache_folder=self.cache_dir,
                device=device,
                trust_remote_code=True,
            )
            logger.info("✅ Tải mô hình Embedding thành công!")
        except Exception as e:
            logger.error(f"❌ Lỗi tải mô hình Embedding: {e}")
            raise

    def _ensure_initialized(self):
        """Đảm bảo model đã được khởi tạo."""
        if self.model is None:
            raise RuntimeError("Model chưa được khởi tạo. Hãy gọi initialize() trước.")

    async def get_embedding(self, text: str) -> List[float]:
        """
        Chuyển đổi văn bản thành Vector (Mảng số thực).
        Hàm này chạy Async để không làm block luồng chính của Discord.
        """
        if not text or not text.strip():
            return []

        loop = asyncio.get_event_loop()
        try:
            # Chạy hàm encode đồng bộ (tốn CPU) trong một Executor (luồng nền)
            vector = await loop.run_in_executor(None, self._encode, text)
            return vector
        except Exception as e:
            logger.error(f"❌ Lỗi khi nhúng vector cho chuỗi '{text[:20]}...': {e}")
            return []

    def _encode(self, text: str) -> List[float]:
        """Hàm đồng bộ thực thi việc nhúng qua CPU/GPU."""
        self._ensure_initialized()
        # Trả về một mảng Python List chuẩn (thay vì Numpy Array) để dễ lưu JSON
        # Tắt thanh tiến trình (progress bar) để tránh log quá nhiều
        return self.model.encode(text, show_progress_bar=False).tolist()
