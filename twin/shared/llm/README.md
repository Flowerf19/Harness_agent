# LLM Providers & Embeddings

Cấu hình env vars cho chat + embedding của `march7`/`evernight`. Code lookup: hỏi codegraph (`codegraph_search chat providers`, `codegraph_files twin/shared/llm`...).

## Chat providers

| `LLM_PROVIDER` | Protocol | Env vars |
|---|---|---|
| `gemini` | Gemini native | `GEMINI_API_KEY`, `GEMINI_MODEL` (vd `gemini-2.5-flash`), optional `GEMINI_API_URL` |
| `openai_compat` (alias: `openai`) | OpenAI-compatible `POST /chat/completions` | `OPENAI_API_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` |

`OPENAI_API_URL` chấp nhận mọi endpoint OpenAI-compat: OpenAI gốc, OpenRouter, Ollama (`http://host.docker.internal:11434/v1`), LM Studio (`http://host.docker.internal:1234/v1`, legacy), Qwen DashScope compatible-mode, ...

## Embedding providers

| `EMBEDDING_PROVIDER` | Protocol | Env vars |
|---|---|---|
| `openai_compat` (alias: `openai`, `qwen`) | `POST /embeddings` | `EMBEDDING_API_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL_NAME`, `EMBEDDING_VECTOR_SIZE` |
| `gemini` (alias: `google`) | Gemini `:embedContent` | `GEMINI_API_KEY` (reuse chat), optional `GEMINI_EMBEDDING_MODEL` (default `gemini-embedding-001`), `GEMINI_EMBEDDING_API_URL`, `EMBEDDING_VECTOR_SIZE` |

Voyage / Cohere v2-compat / LM Studio / OpenRouter → dùng `openai_compat` với URL+model riêng, không cần class mới.

> [!IMPORTANT]
> **Gemini MRL truncation**: `gemini-embedding-001` native 3072-dim. Service truyền `outputDimensionality=EMBEDDING_VECTOR_SIZE` (Matryoshka Representation Learning) rồi L2-normalize để khớp T2 VECTOR index (`timeline_summaries`). Giữ `EMBEDDING_VECTOR_SIZE=1024`. Khi đổi size: `FT.DROPINDEX timeline_summaries` + restart (xem `../../../.agents/AGENT_RULES.md`).

## Ví dụ cấu hình

### Ollama (local-first chat + embeddings)

```env
LLM_PROVIDER=openai_compat
OPENAI_API_URL=http://host.docker.internal:11434/v1
OPENAI_API_KEY=dummy-key
OPENAI_MODEL=<model-name-in-ollama>

EMBEDDING_PROVIDER=openai_compat
EMBEDDING_API_URL=http://host.docker.internal:11434/v1
EMBEDDING_API_KEY=dummy-key
EMBEDDING_MODEL_NAME=<embedding-model>
EMBEDDING_VECTOR_SIZE=1024
```

> [!NOTE]
> Ollama phải bind `0.0.0.0` để container gọi qua `host.docker.internal`. LM Studio trên port `1234` là legacy; vẫn dùng cùng pattern nếu cần.

### Gemini cả chat + embeddings

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash

EMBEDDING_PROVIDER=gemini
EMBEDDING_VECTOR_SIZE=1024
```

### Mix: OpenAI chat + Gemini embeddings

```env
LLM_PROVIDER=openai_compat
OPENAI_API_URL=https://api.openai.com/v1
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini

EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=...
EMBEDDING_VECTOR_SIZE=1024
```

> [!NOTE]
> Docker Compose: từ container → container dùng service name (vd `http://redis:6379`); container → host dùng `host.docker.internal` nếu môi trường hỗ trợ.

## Thêm provider mới

Thêm provider mới bằng cách: định nghĩa service chat/embedding tuân theo interface hiện có, cập nhật factory để chọn provider theo `LLM_PROVIDER`/`EMBEDDING_PROVIDER`, và thêm env vars cần thiết vào bảng cấu hình. Codegraph lookup: `codegraph_search chat providers`.
