"""
E2E (End-to-End) tests for the Twin-Soul architecture.

Tests the COMPLETE flow from user chat to T2 storage:
- User/channel chat → T1 observe → SummaryPolicy → SUMMARY_REQUESTED
  → Evernight DiscussionConsolidator (A2A) → T2 fan-out → SUMMARY_COMPLETED
  → T1 cleanup
- InactivityTrigger → scans active scopes → drives SummaryPolicy.evaluate

These tests mock external services (Redis, LLM) but use real component logic
to verify correct data flow through the system.
"""
