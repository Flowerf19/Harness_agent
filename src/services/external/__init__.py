"""
External Services - Third-party API clients.

This package contains clients for external APIs:
- TavilyClient: Web search API client for AI agents
"""

from src.services.external.tavily_client import TavilyClient, TavilyApiError

__all__ = [
    "TavilyClient",
    "TavilyApiError",
]