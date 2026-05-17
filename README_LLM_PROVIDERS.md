# LLM Providers & Embeddings

Tài liệu này mô tả cách cấu hình **LLM providers** và **embeddings** cho March7/Evernight.

## 1) LLM providers (chỉ còn 2)

Project hiện tại chỉ hỗ trợ 2 provider theo **protocol** để tránh code phình:

### A. Gemini (`LLM_PROVIDER=gemini`)

- Implementation: `twin/shared/llm/gemini_service.py` (`GeminiService`)
- Env vars:
  - `LLM_PROVIDER=gemini`
  - `GEMINI_API_KEY=...`
  - `LLM_MODEL=...` (ví dụ `gemini-2.5-flash`)
  - (optional) `GEMINI_API_URL=...`

### B. OpenAI-compatible (`LLM_PROVIDER=openai_compat`)

"Open protocol" ở đây nghĩa là API **OpenAI-compatible** `POST /chat/completions`.

- Implementation: `twin/shared/llm/openai_service.py` (`OpenAIService`)
- Env vars:
  - `LLM_PROVIDER=openai_compat` (hoặc `openai`)
  - `OPENAI_API_URL=...`
  - `OPENAI_API_KEY=...`
  - `OPENAI_MODEL=...`

Bạn có thể trỏ `OPENAI_API_URL` tới:
- OpenAI (`https://api.openai.com/v1`)
- OpenRouter / router khác (OpenAI-compatible)
- LM Studio / local server (vd `http://host.docker.internal:1234/v1`)
- Qwen compatible-mode / endpoint OpenAI-compatible khác

## 2) Embeddings (OpenAI-compatible `/embeddings`)

Embeddings được gọi qua API OpenAI-compatible:

- Implementation: `twin/shared/llm/openai_embedding_service.py` (`OpenAIEmbeddingService`)

Env vars:
- `EMBEDDING_PROVIDER=openai_compat`
  - Backwards-compat: `qwen` vẫn được chấp nhận như alias.
- `EMBEDDING_API_URL=...`
- `EMBEDDING_API_KEY=...`
- `EMBEDDING_MODEL_NAME=...` (vd `text-embedding-v3`)

## 3) Mapping nhanh (ví dụ)

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
