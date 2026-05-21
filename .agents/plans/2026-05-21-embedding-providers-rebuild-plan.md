## Plan: Tái cấu trúc Embedding Provider để hỗ trợ song song Open Protocol và Gemini Protocol

> **Status: IN_PROGRESS**

TL;DR: Tái cấu trúc hệ thống embedding provider của dự án thành hai provider riêng biệt theo mô hình Cha-Con (kế thừa từ `BaseEmbeddingService` trừu tượng): `OpenAIEmbeddingService` (Open Protocol / Qwen / OpenAI) và `GeminiEmbeddingService` (Gemini Protocol :embedContent). Khởi tạo dưới dạng Singleton-like instance thông qua một factory function dùng chung.

**Steps**
1. [ ] Tạo thư mục mới `twin/shared/embeddings/` và file interface `BaseEmbeddingService` tại `twin/shared/embeddings/base_embedding_service.py`.
2. [ ] Di chuyển `OpenAIEmbeddingService` sang `twin/shared/embeddings/openai_embedding_service.py` và sửa cho kế thừa từ `BaseEmbeddingService`.
3. [ ] Xóa file `openai_embedding_service.py` cũ trong `twin/shared/llm/` và gỡ export khỏi `twin/shared/llm/__init__.py`.
4. [ ] Tạo `GeminiEmbeddingService` trong `twin/shared/embeddings/gemini_embedding_service.py`.
5. [ ] Tạo hàm factory `create_embedding_service` trong `twin/shared/embeddings/__init__.py`.
6. [ ] Cập nhật March7 và Evernight containers (`container.py`) sử dụng hàm factory mới.
7. [ ] Viết unit tests kiểm thử cả hai service tại `tests/unit/test_embedding_services.py`.
8. [ ] Chạy pytest nghiệm thu toàn bộ.

**Relevant files**
- `/home/flowerf/Projects/march7/twin/shared/embeddings/base_embedding_service.py` [NEW]
- `/home/flowerf/Projects/march7/twin/shared/embeddings/openai_embedding_service.py` [NEW]
- `/home/flowerf/Projects/march7/twin/shared/embeddings/gemini_embedding_service.py` [NEW]
- `/home/flowerf/Projects/march7/twin/shared/embeddings/__init__.py` [NEW]
- `/home/flowerf/Projects/march7/twin/shared/llm/openai_embedding_service.py` [DELETE]
- `/home/flowerf/Projects/march7/twin/shared/llm/__init__.py` [MODIFY]
- `/home/flowerf/Projects/march7/twin/march7/container.py` [MODIFY]
- `/home/flowerf/Projects/march7/twin/evernight/container.py` [MODIFY]
- `/home/flowerf/Projects/march7/tests/unit/test_embedding_services.py` [NEW]

**Verification**
1. Chạy pytest: `pytest tests/unit/test_embedding_services.py -v`
2. Kiểm thử thủ công khởi tạo service.
