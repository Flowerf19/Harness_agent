# Bé Bảy (March7)

Bé Bảy là hệ Twin-Soul AI cho Discord. `march7` xử lý hội thoại công khai và
tool calling; `evernight` xử lý DM/prefix `!9`, các tác vụ nền, consolidation,
notification và self-heal. Hai agent trao đổi qua A2A.

## Tính năng

- Hội thoại Discord với unified gateway và tool calling.
- Hai agent độc lập: March7 cho chat chính, Evernight cho owner chat và worker
  nền.
- Bộ nhớ T1/T2/T3: Redis JSON, Redis Stack timeline/vector, và Markdown profile.
- Consolidation qua A2A: March7 gửi các entry T1 đã snapshot sang Evernight;
  Evernight ghi T2/T3 và trả về đúng `entry_ids` để March7 trim.
- System Gateway native cho các thao tác host có HMAC, policy, audit và owner
  approval.

## Kiến trúc

Docker Compose khởi động Redis Stack, Codebox, March7 và Evernight. A2A chỉ
mở trên mạng Docker nội bộ: March7 dùng port `8000`, Evernight dùng `8001`.

- `gateway/` chuyển event Discord thành unified model và định tuyến. Core không
  được phụ thuộc vào object của Discord.
- `twin/march7/` chứa agent chat và container wiring. Production entrypoint là
  `python -m gateway`; `python -m twin.march7` là entrypoint A2A standalone cho
  local development.
- `twin/evernight/` chứa worker consolidation/self-heal, owner chat và A2A.
- `twin/shared/` chứa A2A, LLM, tools và memory dùng chung.

Memory dùng chung code và Redis service nhưng không phải một scope duy nhất:
T1 tách theo agent/DB (`MARCH7_REDIS_DB=0`, `EVERNIGHT_REDIS_DB=1`), T2 dùng
RediSearch trên `TIMELINE_REDIS_DB=0`, còn T3 là Markdown dưới `memories/`.
T2 không tự động chèn vào prompt. Model gọi `search_memory` khi cần truy hồi,
có thể tìm song song user scope và channel scope.

## Yêu cầu

- Python `3.11+`.
- Docker và Docker Compose v2 cho runtime đầy đủ.
- Discord bot token, chat LLM provider và embedding provider.
- System Gateway trên host chỉ bắt buộc khi dùng `host_system` hoặc
  `gateway_admin`.

## Khởi động nhanh

Tạo `.env` từ mẫu và điền secret/token cần thiết, sau đó chạy:

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps
docker exec march7 curl -sf http://localhost:8000/.well-known/agent.json
docker exec evernight curl -sf http://localhost:8001/.well-known/agent.json
```

Chạy local không dùng Docker:

```bash
pip install -r requirements.txt
python -m gateway
python -m twin.evernight
```

Xem [docker/README.md](docker/README.md) và [.agents/PROJECT_CONTEXT.md](.agents/PROJECT_CONTEXT.md) để biết runtime chi tiết.

## Cấu hình

Các nhóm env quan trọng là `REDIS_URL`, `TIMELINE_REDIS_DB`,
`CODEBOX_API_URL`, `LLM_PROVIDER`, `OPENAI_API_URL`/`OPENAI_MODEL` hoặc
`GEMINI_*`, `EMBEDDING_PROVIDER`, `EMBEDDING_API_URL`,
`EMBEDDING_MODEL_NAME`, `EMBEDDING_VECTOR_SIZE`,
`DISCORD_MARCH7_TOKEN`, `DISCORD_EVERNIGHT_TOKEN`, `MARCH7_A2A_PORT`, và
`EVERNIGHT_A2A_PORT`. Container gọi dịch vụ trên host qua
`host.docker.internal`, không dùng `localhost`. Không in `.env` hoặc secret vào
log/chat. Chi tiết provider ở [twin/shared/llm/README.md](twin/shared/llm/README.md).

## Phát triển và kiểm thử

```bash
python -m pytest tests/unit -q
python -m pytest tests/gateway -q
python -m pytest services/system_gateway/tests -q -p no:phoenix
python -m pytest tests -q \
  --ignore=tests/unit/discord_send_response_test.py \
  --ignore=tests/unit/evernight_discord_adapter_test.py \
  --ignore=tests/unit/system_gateway_cli_test.py \
  -p no:phoenix
```

Baseline hiện tại của lệnh cuối: `487 passed, 6 skipped`. Hướng dẫn chọn test
nằm ở [.agents/TESTING_GUIDE.md](.agents/TESTING_GUIDE.md).

## Xử lý sự cố

- Kiểm tra container: `docker compose -f docker/docker-compose.yml ps` và
  `docker compose -f docker/docker-compose.yml logs -f march7 evernight`.
- T2 phải dùng Redis DB `0`; đổi dimension embedding hoặc kiểu index cần xử lý
  lại RediSearch index `timeline_summaries`.
- `docker compose down -v` xóa volume Redis và dữ liệu T1/T2; chỉ dùng khi
  muốn reset dữ liệu.
- System Gateway native chạy ngoài Docker trên `127.0.0.1:8380`; xem
  [services/system_gateway/README.md](services/system_gateway/README.md) để cài
  đặt và kiểm tra approval boundary.
