"""Base agent types and Pydantic models for the orchestration platform."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentID(str, Enum):
    """Identifies which specialized agent handles a task."""

    FLIGHTS = "flights"
    MARKETPLACE = "marketplace"
    STAY = "stay"
    TWITTER = "twitter"


class AgentRequest(BaseModel):
    """Incoming request to an agent."""

    query: str
    session_id: str
    metadata: dict[str, str] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """A single tool invocation within a ReAct step."""

    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None
    latency_ms: int | None = None


class Step(BaseModel):
    """A single ReAct reasoning step."""

    thought: str
    action: str | None = None
    observation: str | None = None
    tool_call: ToolCall | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentResponse(BaseModel):
    """Response returned by an agent after execution."""

    agent_id: AgentID
    answer: str
    steps: list[Step] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    latency_ms: int | None = None


class ReflectionResult(BaseModel):
    """Result of the reflect step — determines whether to continue or finalize."""

    should_continue: bool
    reason: str
