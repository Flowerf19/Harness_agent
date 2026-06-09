"""
E2E (End-to-End) tests for the Twin-Soul architecture.

Tests the COMPLETE flow from user chat to T2 storage:
- User/channel chat → T1 observe → ActiveSummaryPolicy
  → SharedMemoryManager.consolidate_scope → T2 timeline fan-out → T1 cleanup
- InactivityTrigger → scans active scopes → drives ActiveSummaryPolicy.evaluate

These tests mock external services (Redis, LLM) but use real component logic
to verify correct data flow through the system.
"""
