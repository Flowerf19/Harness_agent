---
status: complete
created: 2026-07-18
last_updated: 2026-07-18
---

# MiniMax M3 Time And Tool E2E

## Summary

Switch the Docker chat runtime from `glm-5.2:cloud` to the Ollama-exposed
`minimax-m3:cloud`, restart March7 and Evernight, then verify through the
existing Discord channel `1487427038280421456` that stage-owned server time is
visible to the model and that a fresh weather request calls `web_search`
instead of reusing stale weather text from T1 context.

### GOAL-001: Deploy MiniMax M3

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Verify Ollama exposes the exact model ID `minimax-m3:cloud`. | ✓ | 2026-07-18 |
| TASK-002 | Update only the active `OPENAI_MODEL` runtime setting. | ✓ | 2026-07-18 |
| TASK-003 | Recreate/restart March7 and Evernight and verify both report healthy with the new model. | ✓ | 2026-07-18 |

### GOAL-002: Verify time-aware tool behavior

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-004 | Use Chrome DevTools to open Discord channel `1487427038280421456` without clearing its existing history. | ✓ | 2026-07-18 |
| TASK-005 | Send a deterministic current-time probe and verify the response against server time. | ✓ | 2026-07-18 |
| TASK-006 | Send a weather freshness probe and verify `web_search` selection/execution from Docker logs. | ✓ | 2026-07-18 |
| TASK-007 | Confirm the weather response is based on fresh tool output rather than an older T1 answer. | ✓ | 2026-07-18 |

## Results (2026-07-18)

- Deploy: `docker exec march7/evernight printenv OPENAI_MODEL` → `minimax-m3:cloud`; both containers `Up ... (healthy)`.
- Time probe: server clock `16:33 UTC` → bot replied "Giờ là 16 giờ 34 phút ngày 18/07/2026" (+~40s reply latency). Date correct, time matches stage-injected server clock.
- Weather probe: bot replied fresh Hà Nội forecast dated 18/7. Log evidence:
  - `openai_service.py:173` — endpoint returned 1 tool call `['web_search']`
  - `agent_loop.py:138` — AgentLoop selected web_search (iteration 1/10)
  - `act.py:76` — Tool 'web_search' executed successfully
  - Confirms fresh lookup, not stale T1 reuse.

## Test Plan

- Confirm `docker exec march7` and `docker exec evernight` see
  `OPENAI_MODEL=minimax-m3:cloud`.
- Confirm both container health checks pass after restart.
- Capture pre-test Docker log time so tool evidence is scoped to these probes.
- Ask the bot for the exact current server date/time and compare its answer to
  the host/server clock with a reasonable response-latency tolerance.
- Ask for current weather explicitly, in a way that requires fresh lookup even
  if an older weather answer is present in T1.
- Require log evidence of `web_search` selection and successful execution; a
  plausible final answer without a tool call does not pass.

## Assumptions

- The existing Chrome session is authenticated to Discord and can access the
  specified channel.
- The channel's existing T1/history data must remain intact.
- Sending the two explicit test messages and receiving bot replies is approved.
- MiniMax M3 is served by the existing Ollama OpenAI-compatible endpoint.
