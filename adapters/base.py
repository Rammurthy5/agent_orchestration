"""Base MCP adapter with Streamable HTTP transport, retries, auth, and telemetry.

Implements the MCP Streamable HTTP transport specification:
- JSON-RPC 2.0 messages over HTTP POST
- Server-Sent Events (SSE) for streaming responses
- Session management via Mcp-Session-Id header
- Proper initialize/initialized handshake
"""

from __future__ import annotations

import json
import time
import uuid
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


class MCPSessionError(Exception):
    """Raised when MCP session initialization fails."""

    pass


class BaseMCPAdapter:
    """Base adapter implementing MCP Streamable HTTP transport.

    Handles:
    - JSON-RPC 2.0 request/response over HTTP
    - SSE streaming response parsing
    - Session lifecycle (initialize → tool calls → close)
    - Retries with exponential backoff
    - Auth header injection
    - Response validation with Pydantic

    Subclasses set `base_url` or pass it to __init__.
    """

    base_url: str = ""
    max_retries: int = 3
    initial_delay: float = 0.1
    max_delay: float = 5.0
    timeout: float = 30.0

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        if base_url:
            self.base_url = base_url
        self._auth_token = auth_token
        self._client = httpx.AsyncClient(timeout=self.timeout)
        self._session_id: str | None = None
        self._initialized: bool = False
        self._request_id: int = 0

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    def _next_id(self) -> int:
        """Generate the next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id

    async def ensure_initialized(self) -> None:
        """Perform the MCP initialize handshake if not already done."""
        if self._initialized:
            return

        # Send initialize request
        init_response = await self._raw_jsonrpc_call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "agent-orchestration",
                    "version": "0.1.0",
                },
            },
        )

        if "error" in init_response:
            raise MCPSessionError(
                f"MCP initialize failed: {init_response['error']}"
            )

        # Send initialized notification (no response expected)
        await self._raw_jsonrpc_notification("notifications/initialized", {})
        self._initialized = True

    @traceable(name="mcp.call")
    async def call(
        self,
        method: str,
        params: BaseModel,
        response_model: type[T],
    ) -> T:
        """Call an MCP tool with retries and response validation.

        Args:
            method: The tool name to invoke.
            params: Pydantic model with tool arguments.
            response_model: Pydantic model to validate the response content against.

        Returns:
            Validated response as an instance of response_model.

        Raises:
            MCPError: If all retry attempts fail.
        """
        await self.ensure_initialized()

        last_error: Exception | None = None
        delay = self.initial_delay

        for attempt in range(1, self.max_retries + 1):
            try:
                result = await self._call_tool(method, params.model_dump())
                return response_model.model_validate(result)
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt == self.max_retries:
                    break
                await self._sleep(delay)
                delay = min(delay * 2, self.max_delay)

        raise MCPError(method, str(last_error), self.max_retries)

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tools/call JSON-RPC request."""
        response = await self._raw_jsonrpc_call(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )

        if "error" in response:
            raise MCPError(
                tool_name,
                response["error"].get("message", str(response["error"])),
                1,
            )

        # Extract content from MCP tool result
        result = response.get("result", {})
        content = result.get("content", [])

        # Parse text content blocks into a dict
        if content and isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"text": text}
            # If no text block, return raw content
            return {"content": content}

        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools on the MCP server."""
        await self.ensure_initialized()
        response = await self._raw_jsonrpc_call("tools/list", {})
        if "error" in response:
            raise MCPError("tools/list", str(response["error"]), 1)
        return response.get("result", {}).get("tools", [])

    async def _raw_jsonrpc_call(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and parse the response.

        Handles both direct JSON responses and SSE-streamed responses.
        """
        request_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        headers = self._build_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json, text/event-stream"

        response = await self._client.post(
            self.base_url,
            json=payload,
            headers=headers,
        )

        # Capture session ID from response headers
        if "mcp-session-id" in response.headers:
            self._session_id = response.headers["mcp-session-id"]

        response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # Parse SSE response
            return self._parse_sse_response(response.text, request_id)
        else:
            # Direct JSON response
            return response.json()

    async def _raw_jsonrpc_notification(
        self, method: str, params: dict[str, Any]
    ) -> None:
        """Send a JSON-RPC 2.0 notification (no id, no response expected)."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        headers = self._build_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json, text/event-stream"

        response = await self._client.post(
            self.base_url,
            json=payload,
            headers=headers,
        )

        # Capture session ID
        if "mcp-session-id" in response.headers:
            self._session_id = response.headers["mcp-session-id"]

        # Notifications may return 200 or 202
        if response.status_code not in (200, 202, 204):
            response.raise_for_status()

    def _parse_sse_response(
        self, body: str, request_id: int
    ) -> dict[str, Any]:
        """Parse SSE event stream and extract the JSON-RPC response matching our request ID."""
        events = []
        current_event: dict[str, str] = {}

        for line in body.split("\n"):
            if line.startswith("event:"):
                current_event["event"] = line[6:].strip()
            elif line.startswith("data:"):
                current_event["data"] = line[5:].strip()
            elif line == "" and current_event:
                events.append(current_event)
                current_event = {}

        # Flush last event if no trailing newline
        if current_event:
            events.append(current_event)

        # Find the message event containing our response
        for event in events:
            data = event.get("data", "")
            if not data:
                continue
            try:
                parsed = json.loads(data)
                # Match by request ID
                if parsed.get("id") == request_id:
                    return parsed
                # Also accept if it's the only response
                if "result" in parsed or "error" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # If no matching event found, raise
        raise MCPError(
            "sse_parse",
            f"No JSON-RPC response found in SSE stream for id={request_id}",
            1,
        )

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with auth and session ID."""
        headers: dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    # Keep backward compat alias
    def _auth_headers(self) -> dict[str, str]:
        return self._build_headers()

    @staticmethod
    async def _sleep(seconds: float) -> None:
        """Async sleep for backoff. Separated for testability."""
        import asyncio

        await asyncio.sleep(seconds)
