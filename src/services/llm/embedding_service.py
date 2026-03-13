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
        Tự động fallback từ GPU sang CPU nếu gặp lỗi tương thích.
        """
        # Tạo thư mục cache nếu chưa có
        os.makedirs(self.cache_dir, exist_ok=True)

        device = self._get_device()
        logger.info(f"🔍 Using device: {device}")
        logger.info(f"📁 Model cache directory: {self.cache_dir}")
        logger.info(f"⏳ Đang tải mô hình Embedding local: '{self.model_name}'...")

        # Thử khởi tạo trên device được phát hiện
        self.device = device
        try:
            # Qwen models thường yêu cầu trust_remote_code=True
            self.model = SentenceTransformer(
                self.model_name,
                cache_folder=self.cache_dir,
                device=device,
                trust_remote_code=True,
            )
            logger.info(f"✅ Tải mô hình Embedding thành công trên {device}!")
        except Exception as e:
            error_msg = str(e).lower()
            is_gpu_error = any(
                keyword in error_msg
                for keyword in [
                    "hip error",
                    "cuda error",
                    "invalid device",
                    "out of memory",
                ]
            )

            # Nếu lỗi liên quan đến GPU và đang dùng GPU, thử fallback sang CPU
            if is_gpu_error and device == "cuda":
                logger.warning(f"⚠️ Lỗi GPU khi tải model: {e}")
                logger.warning("🔄 Đang fallback sang CPU...")

                try:
                    self.model = SentenceTransformer(
                        self.model_name,
                        cache_folder=self.cache_dir,
                        device="cpu",
                        trust_remote_code=True,
                    )
                    self.device = "cpu"
                    logger.info(
                        "✅ Tải mô hình Embedding thành công trên CPU (fallback)!"
                    )
                    logger.info(
                        "💡 Mẹo: Kiểm tra cài đặt GPU/ROCm nếu muốn tăng tốc độ."
                    )
                except Exception as cpu_e:
                    logger.error(f"❌ Lỗi tải mô hình Embedding trên CPU: {cpu_e}")
                    raise
            else:
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
        Tự động fallback sang CPU nếu gặp lỗi GPU.
        """
        self._ensure_initialized()

        try:
            # Trả về một mảng Python List chuẩn (thay vì Numpy Array) để dễ lưu JSON
            # Tắt thanh tiến trình (progress bar) để tránh log quá nhiều
            return self.model.encode(text, show_progress_bar=False).tolist()
        except Exception as e:
            error_msg = str(e).lower()
            is_gpu_error = any(
                keyword in error_msg
                for keyword in [
                    "hip error",
                    "cuda error",
                    "invalid device function",
                    "out of memory",
                ]
            )

            # Nếu lỗi GPU và đang dùng GPU, thử fallback sang CPU
            if is_gpu_error and self.device == "cuda":
                logger.warning(f"⚠️ Lỗi GPU khi encode: {e}")
                logger.warning("🔄 Đang fallback sang CPU cho lần encode này...")

                try:
                    # Di chuyển model sang CPU
                    self.model = self.model.to("cpu")
                    self.device = "cpu"
                    logger.info(
                        "✅ Đã chuyển model sang CPU. Các lần encode tiếp theo sẽ dùng CPU."
                    )

                    # Thử encode lại trên CPU
                    return self.model.encode(text, show_progress_bar=False).tolist()
                except Exception as cpu_e:
                    logger.error(f"❌ Lỗi encode trên CPU: {cpu_e}")
                    raise
            else:
                raise
