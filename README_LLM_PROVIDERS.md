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

## Embeddings

Embedding service được tổ chức theo pattern factory + base/implementation, đặt trong [`twin/shared/llm/embedding/`](twin/shared/llm/embedding/):

```
twin/shared/llm/embedding/
├── base_embedding_service.py     # BaseEmbeddingService (ABC) + shared session/LRU cache
├── openai_embedding_service.py   # OpenAIEmbeddingService — chuẩn OpenAI /embeddings
├── gemini_embedding_service.py   # GeminiEmbeddingService — native :embedContent
└── embedding_factory.py          # create_embedding_service() route theo EMBEDDING_PROVIDER
```

Cả 2 implementation expose cùng interface `async get_embedding(text) -> list[float]`, dùng được như drop-in (T2 chỉ duck-type).

### Provider lựa chọn

| `EMBEDDING_PROVIDER` | Class | Endpoint |
|---|---|---|
| `openai_compat` (alias: `openai`, `qwen`) | `OpenAIEmbeddingService` | `POST {url}/embeddings` |
| `gemini` (alias: `google`) | `GeminiEmbeddingService` | `POST {url}/{model}:embedContent?key=...` |

Các provider khác (Voyage, Cohere v2-compat, LM Studio, OpenRouter, ...) đều OpenAI-compatible — dùng `openai_compat` với URL/model riêng là đủ, không cần class mới.

### 1) OpenAI-compatible (`EMBEDDING_PROVIDER=openai_compat`)

- `EMBEDDING_API_URL=...`
- `EMBEDDING_API_KEY=...`
- `EMBEDDING_MODEL_NAME=...` (vd `text-embedding-v3`, `text-embedding-3-small`)
- `EMBEDDING_VECTOR_SIZE=1024` (phải khớp với output thực của model + T2 FT index)

### 2) Gemini native (`EMBEDDING_PROVIDER=gemini`)

- `GEMINI_API_KEY=...` (reuse với chat provider)
- `GEMINI_EMBEDDING_MODEL=gemini-embedding-001` (optional, default đã set)
- `GEMINI_EMBEDDING_API_URL=https://generativelanguage.googleapis.com/v1beta/models` (optional)
- `EMBEDDING_VECTOR_SIZE=1024` (xem note bên dưới)

> [!IMPORTANT]
> `gemini-embedding-001` natively trả về **3072-dim**. Service tự truyền `outputDimensionality=EMBEDDING_VECTOR_SIZE` (Matryoshka Representation Learning) và L2-normalize vector sau khi truncate, nên có thể giữ `EMBEDDING_VECTOR_SIZE=1024` để khớp T2 FT index có sẵn — không phải drop index. Nếu đổi vector size sau đó: `FT.DROPINDEX idx:t2:page` rồi restart (xem `.agents/AGENT_RULES.md` gotchas).

## Ví dụ cấu hình

### LM Studio (chat + embeddings)

```env
LLM_PROVIDER=openai_compat
OPENAI_API_URL=http://host.docker.internal:1234/v1
OPENAI_API_KEY=dummy-key
OPENAI_MODEL=<model-name-in-lm-studio>

EMBEDDING_PROVIDER=openai_compat
EMBEDDING_API_URL=http://host.docker.internal:1234/v1
EMBEDDING_API_KEY=dummy-key
EMBEDDING_MODEL_NAME=<embedding-model>
EMBEDDING_VECTOR_SIZE=1024
```

### Gemini cho cả chat + embeddings

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
LLM_MODEL=gemini-2.5-flash

EMBEDDING_PROVIDER=gemini
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_VECTOR_SIZE=1024
```

### Mix: OpenAI chat + Gemini embeddings (hoặc ngược lại)

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
> Nếu dự án chạy bằng Docker Compose, hãy đảm bảo URL tương ứng với network context:
> - Từ container sang container: dùng service name (vd `http://redis:6379` cho Redis).
> - Từ container gọi host: thường dùng `host.docker.internal` (nếu môi trường hỗ trợ).

> [!TIP]
> Muốn thêm provider mới (vd Voyage native, Cohere native)? Tạo class kế thừa `BaseEmbeddingService` trong [twin/shared/llm/embedding/](twin/shared/llm/embedding/), thêm 1 nhánh vào `create_embedding_service` trong [embedding_factory.py](twin/shared/llm/embedding/embedding_factory.py).
