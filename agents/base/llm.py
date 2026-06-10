"""LLM client abstraction for agent reasoning.

Provides an async interface to OpenAI-compatible chat completion APIs.
All agents use this for reasoning, tool selection, and reflection steps.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from langsmith import traceable
from pydantic import BaseModel


class Message(BaseModel):
    """A single message in the conversation."""

    role: str  # system, user, assistant, tool
    content: str


class ToolSpec(BaseModel):
    """Tool specification for function calling."""

    name: str
    description: str
    parameters: dict[str, Any]


class LLMResponse(BaseModel):
    """Parsed LLM completion response."""

    content: str
    tool_call: LLMToolCall | None = None
    usage: dict[str, Any] | None = None


class LLMToolCall(BaseModel):
    """An LLM-requested tool invocation."""

    name: str
    arguments: dict[str, Any]


class LLMClient:
    """Async client for OpenAI-compatible chat completions.

    Env vars:
        LLM_API_BASE: API base URL (default: https://api.openai.com/v1)
        LLM_API_KEY: API key for auth
        LLM_MODEL: Model name (default: gpt-4o)
    """

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.api_base = api_base or os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "gpt-5.4-mini")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self._client.aclose()

    @traceable(name="llm.complete")
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Send a chat completion request and return the parsed response."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": self._normalize_tool_schema(t.parameters),
                    },
                }
                for t in tools
            ]

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = await self._client.post(
            f"{self.api_base}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        message = choice["message"]

        tool_call = None
        if message.get("tool_calls"):
            tc = message["tool_calls"][0]["function"]
            tool_call = LLMToolCall(
                name=tc["name"],
                arguments=json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"],
            )

        return LLMResponse(
            content=message.get("content") or "",
            tool_call=tool_call,
            usage=data.get("usage"),
        )

    def _normalize_tool_schema(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Normalize tool parameter declarations into a valid JSON schema object."""
        if isinstance(parameters, dict) and parameters.get("type") == "object":
            return parameters

        properties: dict[str, Any] = {}
        for key, value in parameters.items():
            if isinstance(value, dict):
                properties[key] = value
            else:
                properties[key] = {
                    "type": "string",
                    "description": str(value),
                }

        return {
            "type": "object",
            "properties": properties,
        }
