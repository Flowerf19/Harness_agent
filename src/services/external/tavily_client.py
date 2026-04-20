"""
TavilyClient - Web Search API client cho AI agents.

Tavily là search API được tối ưu cho AI agents, cung cấp:
- Real-time web search
- AI-generated answers
- Clean, structured results

API Documentation: https://docs.tavily.com/
"""

import logging
from typing import Optional, Dict, Any

import aiohttp

from src.config.settings import Config

logger = logging.getLogger(__name__)


class TavilyApiError(Exception):
    """
    Exception raised khi Tavily API call fails.

    Attributes:
        message: Error message
        status_code: HTTP status code (if available)
        original_error: Original exception (if any)
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        super().__init__(f"Tavily API Error: {message}")

    def __repr__(self) -> str:
        return f"TavilyApiError(message={self.message}, status_code={self.status_code})"


class TavilyClient:
    """
    Tavily Web Search API Client.

    Sử dụng aiohttp để thực hiện async HTTP requests.
    Handles authentication, timeouts, và error handling.

    Example:
        client = TavilyClient()
        if client.is_configured():
            results = await client.search("Python async programming")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        max_results: Optional[int] = None,
        search_depth: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """
        Initialize TavilyClient.

        Args:
            api_key: Tavily API key (default: from Config)
            api_url: Tavily API URL (default: from Config)
            max_results: Default max results (default: from Config)
            search_depth: Default search depth "basic" or "advanced" (default: from Config)
            timeout: Request timeout in seconds (default: from Config)
        """
        self.api_key = api_key or Config.TAVILY_API_KEY
        self.api_url = api_url or Config.TAVILY_API_URL
        self.max_results = max_results or Config.TAVILY_MAX_RESULTS
        self.search_depth = search_depth or Config.TAVILY_SEARCH_DEPTH
        self.timeout = timeout or Config.TAVILY_TIMEOUT

        self._session: Optional[aiohttp.ClientSession] = None

        logger.info(
            f"TavilyClient initialized - configured: {self.is_configured()}, "
            f"max_results: {self.max_results}, depth: {self.search_depth}"
        )

    def is_configured(self) -> bool:
        """
        Check if Tavily API is properly configured.

        Returns:
            bool: True if API key is set
        """
        return bool(self.api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session.

        Returns:
            aiohttp.ClientSession: HTTP client session
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("TavilyClient session closed")

    async def search(
        self,
        query: str,
        search_depth: Optional[str] = None,
        max_results: Optional[int] = None,
        include_answer: bool = True,
        include_raw_content: bool = False,
        include_images: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute web search via Tavily API.

        Args:
            query: Search query string
            search_depth: "basic" or "advanced" (default: from config)
            max_results: Max number of results (default: from config)
            include_answer: Include AI-generated answer
            include_raw_content: Include raw page content
            include_images: Include image URLs

        Returns:
            Dict containing:
                - answer: AI-generated answer (if include_answer=True)
                - results: List of search results with title, url, content, score

        Raises:
            TavilyApiError: If API call fails
        """
        # Validate configuration
        if not self.is_configured():
            raise TavilyApiError("Tavily API key not configured")

        if not query or not query.strip():
            raise TavilyApiError("Search query cannot be empty")

        # Use defaults or override
        search_depth = search_depth or self.search_depth
        max_results = max_results or self.max_results

        # Build request
        url = f"{self.api_url}/search"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query.strip(),
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
            "include_images": include_images,
        }

        logger.info(f"🔍 Tavily search: query='{query[:50]}...', depth={search_depth}, max={max_results}")

        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as response:
                # Log response status
                logger.debug(f"Tavily API response: {response.status}")

                # Handle HTTP errors
                if response.status == 401:
                    raise TavilyApiError("Invalid API key", status_code=401)
                elif response.status == 429:
                    raise TavilyApiError("Rate limit exceeded", status_code=429)
                elif response.status >= 500:
                    raise TavilyApiError(f"Server error: {response.status}", status_code=response.status)
                elif response.status >= 400:
                    error_text = await response.text()
                    raise TavilyApiError(f"Request failed: {error_text}", status_code=response.status)

                # Parse response
                data = await response.json()

                # Validate response structure
                if "results" not in data:
                    raise TavilyApiError("Invalid response: missing 'results' field")

                result_count = len(data.get("results", []))
                logger.info(f"✅ Tavily search returned {result_count} results")

                return data

        except aiohttp.ClientTimeout:
            raise TavilyApiError(f"Request timeout after {self.timeout}s")
        except aiohttp.ClientError as e:
            raise TavilyApiError(f"Network error: {e}", original_error=e)
        except TavilyApiError:
            # Re-raise our own exceptions
            raise
        except Exception as e:
            raise TavilyApiError(f"Unexpected error: {e}", original_error=e)

    def __repr__(self) -> str:
        return f"<TavilyClient: configured={self.is_configured()}>"