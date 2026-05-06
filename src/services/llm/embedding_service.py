# src/services/llm/embedding_service.py
import asyncio
import logging
import os
from typing import List

import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Tắt log verbose của các thư viện bên thứ ba
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Đường dẫn cache cho models
# Ưu tiên HF_HOME env var (đã được mount với quyền ghi trong Docker)
# Fallback về thư mục models/ nếu không có HF_HOME
MODEL_CACHE_DIR = os.environ.get(
    "HF_HOME",
    os.path.join(os.path.dirname(__file__), "../../models")
)


class LocalEmbeddingService:
    """
    Trạm Nhúng Vector (Embedding Service).
    Sử dụng mô hình local (VD: Qwen/Qwen3-Embedding-0.6B) để biến Text thành Vector.
    """

    def __init__(self, model_name: str = "Qwen/Qwen3-Embedding-0.6B"):
        self.model_name = model_name
        self.model = None
        self.cache_dir = os.path.abspath(MODEL_CACHE_DIR)
        self.device = None  # Lưu device thực tế đang sử dụng
        self._cache = {}

    def _get_device(self) -> str:
        """
        Kiểm tra và trả về device phù hợp (CUDA/ROCm hoặc CPU).
        Phát hiện chính xác loại GPU đang sử dụng và ghi log tương ứng.
        """
        if torch.cuda.is_available():
            device = "cuda"
            # Kiểm tra xem đang sử dụng ROCm (AMD) hay CUDA (NVIDIA)
            is_rocm = hasattr(torch.version, "hip") and torch.version.hip is not None

            gpu_name = torch.cuda.get_device_name(0)

            if is_rocm:
                logger.info(f"🎮 AMD GPU (ROCm) detected: {gpu_name}")
                logger.info(f"   HIP version: {torch.version.hip}")
            else:
                cuda_version = getattr(torch.version, "cuda", "N/A")
                logger.info(f"🎮 NVIDIA GPU (CUDA) detected: {gpu_name}")
                logger.info(f"   CUDA version: {cuda_version}")
        else:
            device = "cpu"
            logger.info("💻 Using CPU device")
        return device

    async def initialize(self):
        """
        Khởi tạo model với cache_dir và device phù hợp.
        Nếu model không có trong cache, sẽ tự động tải xuống.
        """
        # Tạo thư mục cache nếu chưa có
        os.makedirs(self.cache_dir, exist_ok=True)

        device = self._get_device()
        logger.info(f"🔍 Using device: {device}")
        logger.info(f"📁 Model cache directory: {self.cache_dir}")
        logger.info(f"⏳ Đang tải mô hình Embedding local: '{self.model_name}'...")

        # Khởi tạo model trên device được phát hiện
        self.device = device
        try:
            # Qwen models thường yêu cầu trust_remote_code=True
            # Nếu model chưa có trong cache, SentenceTransformer sẽ tự động tải xuống
            self.model = SentenceTransformer(
                self.model_name,
                cache_folder=self.cache_dir,
                device=device,
                trust_remote_code=True,
            )
            logger.info(f"✅ Tải mô hình Embedding thành công trên {device}!")
        except Exception as e:
            logger.error(f"❌ Lỗi tải mô hình Embedding: {e}")
            raise

    def _ensure_initialized(self):
        """Đảm bảo model đã được khởi tạo."""
        if self.model is None:
            raise RuntimeError("Model chưa được khởi tạo. Hãy gọi initialize() trước.")

    async def get_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            return []

        # 1. Kiểm tra xem câu này đã nhúng chưa
        if text in self._cache:
            return self._cache[text]

        loop = asyncio.get_event_loop()
        try:
            # 2. Chạy nhúng vector nếu chưa có trong cache
            vector = await loop.run_in_executor(None, self._encode, text)

            # 3. Lưu lại kết quả, giữ tối đa 100 câu gần nhất để không tràn RAM
            self._cache[text] = vector
            if len(self._cache) > 100:
                self._cache.pop(next(iter(self._cache)))

            return vector
        except Exception as e:
            self.logger.error(f"Error generating embedding: {e}")
            return []

    def _encode(self, text: str) -> List[float]:
        """
        Hàm đồng bộ thực thi việc nhúng qua CPU/GPU.
        """
        self._ensure_initialized()

        # Trả về một mảng Python List chuẩn (thay vì Numpy Array) để dễ lưu JSON
        # Tắt thanh tiến trình (progress bar) để tránh log quá nhiều
        return self.model.encode(text, show_progress_bar=False).tolist()
