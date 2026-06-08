"""Base MCP adapter for stdio transports.

Implements the MCP stdio JSON-RPC transport used by local subprocess-based
servers launched via tools like `npx`.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, TypeVar

from langsmith import traceable
from pydantic import BaseModel

from adapters.base import MCPError, MCPSessionError

T = TypeVar("T", bound=BaseModel)


class BaseMCPStdioAdapter:
    """Base adapter for MCP servers that speak JSON-RPC over stdio."""

    max_retries: int = 3
    initial_delay: float = 0.1
    max_delay: float = 5.0
    timeout: float = 30.0

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ):
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = Path(cwd) if cwd is not None else None
        self._process: asyncio.subprocess.Process | None = None
        self._initialized = False
        self._request_id = 0
        self._read_buffer = bytearray()
        self._stderr_lines: list[str] = []
        self._stderr_task: asyncio.Task[None] | None = None
        self._request_lock = asyncio.Lock()

    async def close(self) -> None:
        """Terminate the subprocess if it is running."""
        if self._process is None:
            return

        if self._process.stdin is not None and not self._process.stdin.is_closing():
            self._process.stdin.close()
            try:
                await self._process.stdin.wait_closed()
            except Exception:
                pass

        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()

        self._process = None
        self._initialized = False
        self._read_buffer.clear()
        self._stderr_lines.clear()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            self._stderr_task = None

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _ensure_process(self) -> None:
        if self._process is not None and self._process.returncode is None:
            return

        env = os.environ.copy()
        env.update(self.env)

        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cwd) if self.cwd is not None else None,
            env=env,
        )

        if self._process.stdin is None or self._process.stdout is None:
            raise MCPSessionError("MCP stdio process did not expose pipes")
        if self._stderr_task is None and self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._consume_stderr())

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return

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
            raise MCPSessionError(f"MCP initialize failed: {init_response['error']}")

        await self._raw_jsonrpc_notification("notifications/initialized", {})
        self._initialized = True

    @traceable(name="mcp.call")
    async def call(
        self,
        method: str,
        params: BaseModel,
        response_model: type[T],
    ) -> T:
        await self.ensure_initialized()

        last_error: Exception | None = None
        delay = self.initial_delay

        for attempt in range(1, self.max_retries + 1):
            try:
                result = await self._call_tool(method, params.model_dump())
                return response_model.model_validate(result)
            except (MCPError, MCPSessionError, asyncio.TimeoutError, OSError) as e:
                last_error = e
                if attempt == self.max_retries:
                    break
                await self._sleep(delay)
                delay = min(delay * 2, self.max_delay)

        raise MCPError(method, self._format_stdio_error(str(last_error)), self.max_retries)

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = await self._raw_jsonrpc_call(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )

        if "error" in response:
            raise MCPError(
                tool_name,
                self._format_stdio_error(
                    response["error"].get("message", str(response["error"]))
                ),
                1,
            )

        result = response.get("result", {})
        content = result.get("content", [])

        if content and isinstance(content, list):
            for block in content:
                if block.get("type") != "text":
                    continue
                text = block.get("text", "")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}
            return {"content": content}

        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.ensure_initialized()
        response = await self._raw_jsonrpc_call("tools/list", {})
        if "error" in response:
            raise MCPError("tools/list", str(response["error"]), 1)
        return response.get("result", {}).get("tools", [])

    async def _raw_jsonrpc_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        async with self._request_lock:
            await self._ensure_process()
            request_id = self._next_id()
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            await self._write_message(payload)

            while True:
                response = await self._read_message()
                if response.get("id") == request_id:
                    return response
                if response.get("method") is not None and response.get("id") is None:
                    continue
                if "result" in response or "error" in response:
                    return response

    async def _raw_jsonrpc_notification(self, method: str, params: dict[str, Any]) -> None:
        async with self._request_lock:
            await self._ensure_process()
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
            await self._write_message(payload)

    async def _write_message(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPSessionError("MCP stdio process is not ready")

        frame = self.encode_frame(payload)
        self._process.stdin.write(frame)
        await self._process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        if self._process is None or self._process.stdout is None:
            raise MCPSessionError("MCP stdio process is not ready")

        while True:
            message = self._try_parse_message()
            if message is not None:
                return message

            chunk = await asyncio.wait_for(self._process.stdout.read(4096), timeout=self.timeout)
            if not chunk:
                raise MCPSessionError(self._format_stdio_error("MCP stdio process closed stdout before responding"))
            self._read_buffer.extend(chunk)

    def _try_parse_message(self) -> dict[str, Any] | None:
        buffer = bytes(self._read_buffer)
        header_end = buffer.find(b"\r\n\r\n")
        delimiter_len = 4
        if header_end == -1:
            header_end = buffer.find(b"\n\n")
            delimiter_len = 2
        if header_end == -1:
            return None

        header_block = buffer[:header_end].decode("utf-8", errors="replace")
        headers: dict[str, str] = {}
        for line in header_block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        content_length = headers.get("content-length")
        if content_length is None:
            return None

        try:
            length = int(content_length)
        except ValueError as exc:
            raise MCPSessionError(f"Invalid Content-Length header: {content_length!r}") from exc

        body_start = header_end + delimiter_len
        body_end = body_start + length
        if len(buffer) < body_end:
            return None

        body = buffer[body_start:body_end]
        self._read_buffer = bytearray(buffer[body_end:])

        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MCPSessionError(self._format_stdio_error("Failed to decode MCP stdio JSON-RPC message")) from exc

    @staticmethod
    def encode_frame(payload: dict[str, Any]) -> bytes:
        """Encode a JSON-RPC payload as an MCP stdio frame."""
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def _consume_stderr(self) -> None:
        if self._process is None or self._process.stderr is None:
            return

        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    self._stderr_lines.append(text)
                    if len(self._stderr_lines) > 20:
                        self._stderr_lines = self._stderr_lines[-20:]
        except asyncio.CancelledError:
            return

    def _format_stdio_error(self, message: str) -> str:
        if not self._stderr_lines:
            return message
        tail = "\n".join(self._stderr_lines[-5:])
        return f"{message}\nMCP stderr:\n{tail}"
