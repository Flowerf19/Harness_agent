# GLOSSARY

## Twin-Soul Agents

- **March7**: agent hội thoại chính (chat/tool calling/memory T1/T3).
- **Evernight**: agent background (consolidation/self-heal/triggers).

## Memory tiers

- **T1 (Active Memory)**: ngữ cảnh ngắn hạn; Redis.
- **T2 (Wiki Pages / Episodic Memory)**: tri thức dài hạn; Qdrant vector DB.
- **T3 (Core Memory)**: hồ sơ user; Markdown files.

## Consolidation

Quá trình gom hội thoại (T1 snapshot) thành tri thức T2 (wiki pages), thường do Evernight chạy khi user inactivity.

## A2A

Agent-to-Agent protocol (HTTP JSON-RPC + SSE) để March7 và Evernight gọi nhau qua network boundary.

## Gateway / Adapter / Handler / Router

- **Adapter**: tích hợp nền tảng (Discord).
- **Handler**: áp rules/filtering, context platform.
- **Router**: quyết định gửi message/tác vụ sang agent nào.

## Codebox

Service sandbox chạy code Python.

## Bash Executor

Tool chạy lệnh bash trên host; yêu cầu approval; rủi ro cao nếu bị prompt injection.
