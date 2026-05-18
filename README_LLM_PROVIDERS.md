# LLM Providers & Embeddings

Tài liệu cấu hình LLM chat provider và embedding provider cho `march7`/`evernight`.

## Chat providers (supported)

Hiện tại chỉ hỗ trợ 2 protocol:

### 1) Gemini (`LLM_PROVIDER=gemini`)

- Implementation: `twin/shared/llm/gemini_service.py` (`GeminiService`)
- Env vars:
  - `LLM_PROVIDER=gemini`
  - `GEMINI_API_KEY=...`
  - `LLM_MODEL=...` (ví dụ `gemini-2.5-flash`)
  - (optional) `GEMINI_API_URL=...`

### 2) OpenAI-compatible (`LLM_PROVIDER=openai_compat`)

"Open protocol" ở đây nghĩa là API **OpenAI-compatible** `POST /chat/completions`.

- Implementation: `twin/shared/llm/openai_service.py` (`OpenAIService`)
- Env vars:
  - `LLM_PROVIDER=openai_compat` (hoặc `openai`)
  - `OPENAI_API_URL=...`
  - `OPENAI_API_KEY=...`
  - `OPENAI_MODEL=...`

`OPENAI_API_URL` có thể trỏ tới:
- OpenAI (`https://api.openai.com/v1`)
- OpenRouter / router khác (OpenAI-compatible)
- LM Studio / local server (vd `http://host.docker.internal:1234/v1`)
- Qwen compatible-mode / endpoint OpenAI-compatible khác

## Embeddings (OpenAI-compatible `/embeddings`)

Embeddings được gọi qua API OpenAI-compatible:

- Implementation: `twin/shared/llm/openai_embedding_service.py` (`OpenAIEmbeddingService`)

Biến môi trường:
- `EMBEDDING_PROVIDER=openai_compat`
  - Backward-compat: `qwen` vẫn được chấp nhận như alias.
- `EMBEDDING_API_URL=...`
- `EMBEDDING_API_KEY=...`
- `EMBEDDING_MODEL_NAME=...` (vd `text-embedding-v3`)

## Ví dụ cấu hình

### LM Studio (chat + embeddings)

- `LLM_PROVIDER=openai_compat`
- `OPENAI_API_URL=http://host.docker.internal:1234/v1`
- `OPENAI_API_KEY=dummy-key`
- `OPENAI_MODEL=<model-name-in-lm-studio>`

- `EMBEDDING_PROVIDER=openai_compat`
- `EMBEDDING_API_URL=http://host.docker.internal:1234/v1`
- `EMBEDDING_API_KEY=dummy-key`
- `EMBEDDING_MODEL_NAME=<embedding-model>`

### Gemini (chat) + OpenAI-compatible (embeddings)

- `LLM_PROVIDER=gemini`
- `GEMINI_API_KEY=...`
- `LLM_MODEL=gemini-...`

- `EMBEDDING_PROVIDER=openai_compat`
- `EMBEDDING_API_URL=...`
- `EMBEDDING_API_KEY=...`
- `EMBEDDING_MODEL_NAME=...`

> [!NOTE]
> Nếu dự án chạy bằng Docker Compose, hãy đảm bảo URL tương ứng với network context:
> - Từ container sang container: dùng service name (vd `http://redis:6379` cho Redis).
> - Từ container gọi host: thường dùng `host.docker.internal` (nếu môi trường hỗ trợ).

> [!TIP]
> Giữ cùng một endpoint OpenAI-compatible cho chat và embeddings khi có thể để đơn giản hóa vận hành.
