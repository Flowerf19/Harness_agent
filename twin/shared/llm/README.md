# LLM Providers & Embeddings

Cấu hình env vars cho chat + embedding của `march7`/`evernight`. Code lookup: hỏi codegraph (`codegraph_search GeminiService`, `codegraph_files twin/shared/llm`...).

## Chat providers

| `LLM_PROVIDER` | Protocol | Env vars |
|---|---|---|
| `gemini` | Gemini native | `GEMINI_API_KEY`, `LLM_MODEL` (vd `gemini-2.5-flash`), optional `GEMINI_API_URL` |
| `openai_compat` (alias: `openai`) | OpenAI-compatible `POST /chat/completions` | `OPENAI_API_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` |

`OPENAI_API_URL` chấp nhận mọi endpoint OpenAI-compat: OpenAI gốc, OpenRouter, LM Studio (`http://host.docker.internal:1234/v1`), Qwen DashScope compatible-mode, ...

## Embedding providers

| `EMBEDDING_PROVIDER` | Protocol | Env vars |
|---|---|---|
| `openai_compat` (alias: `openai`, `qwen`) | `POST /embeddings` | `EMBEDDING_API_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL_NAME`, `EMBEDDING_VECTOR_SIZE` |
| `gemini` (alias: `google`) | Gemini `:embedContent` | `GEMINI_API_KEY` (reuse chat), optional `GEMINI_EMBEDDING_MODEL` (default `gemini-embedding-001`), `GEMINI_EMBEDDING_API_URL`, `EMBEDDING_VECTOR_SIZE` |

Voyage / Cohere v2-compat / LM Studio / OpenRouter → dùng `openai_compat` với URL+model riêng, không cần class mới.

> [!IMPORTANT]
> **Gemini MRL truncation**: `gemini-embedding-001` native 3072-dim. Service truyền `outputDimensionality=EMBEDDING_VECTOR_SIZE` (Matryoshka Representation Learning) rồi L2-normalize → truncate xuống `768` để khớp T2 VECTOR index có sẵn. Giữ `EMBEDDING_VECTOR_SIZE=768`. Khi đổi size: `FT.DROPINDEX idx:t2:mem` + `FT.DROPINDEX idx:t2:topic` + restart (xem `../../../.agents/AGENT_RULES.md`).

## Ví dụ cấu hình

### LM Studio (chat + embeddings cùng endpoint)

```env
LLM_PROVIDER=openai_compat
OPENAI_API_URL=http://host.docker.internal:1234/v1
OPENAI_API_KEY=dummy-key
OPENAI_MODEL=<model-name-in-lm-studio>

EMBEDDING_PROVIDER=openai_compat
EMBEDDING_API_URL=http://host.docker.internal:1234/v1
EMBEDDING_API_KEY=dummy-key
EMBEDDING_MODEL_NAME=<embedding-model>
EMBEDDING_VECTOR_SIZE=768
```

### Gemini cả chat + embeddings

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
LLM_MODEL=gemini-2.5-flash

EMBEDDING_PROVIDER=gemini
EMBEDDING_VECTOR_SIZE=768
```

### Mix: OpenAI chat + Gemini embeddings

```env
LLM_PROVIDER=openai_compat
OPENAI_API_URL=https://api.openai.com/v1
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini

EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=...
EMBEDDING_VECTOR_SIZE=768
```

> [!NOTE]
> Docker Compose: từ container → container dùng service name (vd `http://redis:6379`); container → host dùng `host.docker.internal` nếu môi trường hỗ trợ.

## Thêm provider mới

Kế thừa `BaseEmbeddingService` (hoặc `BaseLLMService` cho chat) + thêm 1 nhánh vào factory. Codegraph lookup: `codegraph_node BaseEmbeddingService` / `codegraph_search create_embedding_service`.
