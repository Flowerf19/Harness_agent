"""
E2E (End-to-End) tests for Sub-Agent (Evernight) architecture.

Tests the COMPLETE flow from user chat to T2 storage:
- User chat → T1 fills → MemoryJobQueue → Evernight consolidates → T2 stored
- Nightly trigger → Scans T1 → Consolidates remaining → T1 cleared

These tests mock external services (Redis, LLM) but use real component logic
to verify correct data flow through the system.
"""
