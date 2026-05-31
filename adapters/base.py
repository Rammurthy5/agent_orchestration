"""Base MCP adapter with retries, auth, telemetry, and response validation."""

from __future__ import annotations

import time
from typing import Any, TypeVar

import httpx
from langsmith import traceable
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class MCPError(Exception):
    """Raised when an MCP call fails after all retries."""

    def __init__(self, method: str, message: str, attempts: int):
        self.method = method
        self.attempts = attempts
        super().__init__(f"MCP {method} failed after {attempts} attempts: {message}")


class BaseMCPAdapter:
    """Base adapter for MCP server communication.

    Handles: retries (exponential backoff), auth injection, telemetry, response validation.
    Subclasses must set `base_url` and optionally override `_auth_headers`.
    """

    base_url: str
    max_retries: int = 3
    initial_delay: float = 0.1
    max_delay: float = 5.0
    timeout: float = 30.0

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        if base_url:
            self.base_url = base_url
        self._auth_token = auth_token
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @traceable(name="mcp.call")
    async def call(
        self,
        method: str,
        params: BaseModel,
        response_model: type[T],
    ) -> T:
        """Call an MCP method with retries and response validation.

        Args:
            method: The MCP method name to invoke.
            params: Pydantic model with request parameters.
            response_model: Pydantic model to validate the response against.

        Returns:
            Validated response as an instance of response_model.

        Raises:
            MCPError: If all retry attempts fail.
        """
        last_error: Exception | None = None
        delay = self.initial_delay

        for attempt in range(1, self.max_retries + 1):
            try:
                result = await self._do_call(method, params)
                return response_model.model_validate(result)
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt == self.max_retries:
                    break
                await self._sleep(delay)
                delay = min(delay * 2, self.max_delay)

        raise MCPError(method, str(last_error), self.max_retries)

    async def _do_call(self, method: str, params: BaseModel) -> dict[str, Any]:
        """Execute the raw HTTP call to the MCP server."""
        url = f"{self.base_url}/{method}"
        headers = self._auth_headers()

        response = await self._client.post(
            url,
            json=params.model_dump(),
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    def _auth_headers(self) -> dict[str, str]:
        """Return authentication headers. Override in subclasses for custom auth."""
        headers: dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    @staticmethod
    async def _sleep(seconds: float) -> None:
        """Async sleep for backoff. Separated for testability."""
        import asyncio

        await asyncio.sleep(seconds)
