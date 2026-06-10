"""Deterministic safety helpers for redaction and blocking.

This module keeps the policy intentionally small and explicit:
- redact routine PII in text and structured payloads
- block obvious secrets, credential payloads, and prompt-injection attempts
- provide stable refusal text for agents and persistence layers
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from agents.base.types import AgentID, AgentRequest, AgentResponse, Step, ToolCall

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SSN_RE = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}\b")
_ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|passphrase|access[_-]?token|refresh[_-]?token|private[_-]?key)\b\s*[:=]\s*([^\s,;]+)"
)
_SECRET_PREFIX_RE = re.compile(
    r"\b(?:sk-|rk-|pk-|ghp_|gho_|xoxb-|xoxp-|AIza[0-9A-Za-z_-]{10,})[A-Za-z0-9._=-]{8,}\b"
)
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s().-]\d{2,4}[\s().-]\d{2,4}[\s().-]\d{2,4})")
_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,4}\s+"
    r"(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|court|ct|place|pl|square|sq|way|close|crescent|cres|terrace|ter)\b",
    re.IGNORECASE,
)
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_PROMPT_INJECTION_RE = re.compile(
    r"(?i)\b(?:ignore|disregard|override|bypass|reveal|show|dump|exfiltrate)\b.*\b(?:instructions|policy|system prompt|developer message|tools?|hidden)\b"
)
_SECRET_RETENTION_RE = re.compile(
    r"(?i)\b(?:store|save|remember|retain|persist|log|print|echo|share)\b.*\b(?:api[_-]?key|secret|token|password|passphrase|access[_-]?token|refresh[_-]?token|private[_-]?key|session[_-]?id)\b"
)

_PII_TAGS = {
    "email": "<redacted-email>",
    "phone": "<redacted-phone>",
    "ssn": "<redacted-ssn>",
    "address": "<redacted-address>",
    "card": "<redacted-card>",
    "secret": "<redacted-secret>",
}

_SCOPE_REFUSALS: dict[str, str] = {
    AgentID.FLIGHTS.value: "I can only help with flights, routes, and airfare planning.",
    AgentID.STAY.value: "I can only help with hotels, lodging, and availability checks.",
    AgentID.MARKETPLACE.value: "I can only help with product search and price comparison.",
    AgentID.TWITTER.value: "I can only help with Twitter/X search, trends, and sentiment analysis.",
}


@dataclass(slots=True)
class SafetyDecision:
    """Result of a deterministic safety check."""

    allowed: bool
    redacted_text: str
    reason: str
    refusal_message: str | None = None
    tags: tuple[str, ...] = ()


def redact_text(text: str) -> str:
    """Redact routine PII and obvious secret-like payloads from text."""
    if not text:
        return text

    redacted = text
    redacted = _EMAIL_RE.sub(_PII_TAGS["email"], redacted)
    redacted = _SSN_RE.sub(_PII_TAGS["ssn"], redacted)
    redacted = _CARD_RE.sub(_redact_card, redacted)
    redacted = _PHONE_RE.sub(_PII_TAGS["phone"], redacted)
    redacted = _ADDRESS_RE.sub(_PII_TAGS["address"], redacted)
    redacted = _BEARER_RE.sub(_PII_TAGS["secret"], redacted)
    redacted = _ASSIGNMENT_SECRET_RE.sub(lambda _m: _PII_TAGS["secret"], redacted)
    redacted = _SECRET_PREFIX_RE.sub(_PII_TAGS["secret"], redacted)
    return redacted


def redact_value(value: Any) -> Any:
    """Recursively redact strings inside structured payloads."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return value


def redact_agent_request(request: AgentRequest) -> AgentRequest:
    """Return a copy of a request with PII redacted."""
    return request.model_copy(
        update={
            "query": redact_text(request.query),
            "metadata": redact_value(request.metadata),
        }
    )


def redact_agent_response(response: AgentResponse) -> AgentResponse:
    """Return a copy of a response with strings redacted."""
    redacted_steps: list[Step] = []
    for step in response.steps:
        redacted_tool_call = None
        if step.tool_call is not None:
            redacted_tool_call = ToolCall(
                tool_name=step.tool_call.tool_name,
                parameters=redact_value(step.tool_call.parameters),
                result=redact_text(step.tool_call.result) if step.tool_call.result else None,
                latency_ms=step.tool_call.latency_ms,
            )
        redacted_steps.append(
            Step(
                thought=redact_text(step.thought),
                action=step.action,
                observation=redact_text(step.observation) if step.observation else None,
                tool_call=redacted_tool_call,
                timestamp=step.timestamp,
            )
        )

    redacted_tool_calls: list[ToolCall] = []
    for tool_call in response.tool_calls:
        redacted_tool_calls.append(
            ToolCall(
                tool_name=tool_call.tool_name,
                parameters=redact_value(tool_call.parameters),
                result=redact_text(tool_call.result) if tool_call.result else None,
                latency_ms=tool_call.latency_ms,
            )
        )

    return response.model_copy(
        update={
            "answer": redact_text(response.answer),
            "steps": redacted_steps,
            "tool_calls": redacted_tool_calls,
        }
    )


def assess_query(query: str, agent_id: AgentID | str) -> SafetyDecision:
    """Assess a query for prompt injection and high-risk secret leakage."""
    tags: list[str] = []
    reason: str | None = None

    if _PROMPT_INJECTION_RE.search(query):
        tags.append("prompt_injection")
        reason = "prompt_injection_detected"
    elif _SECRET_RETENTION_RE.search(query):
        tags.append("secret_retention_request")
        reason = "secret_retention_request"
    elif _ASSIGNMENT_SECRET_RE.search(query) or _SECRET_PREFIX_RE.search(query) or _BEARER_RE.search(query):
        tags.append("credential_like_content")
        reason = "credential_like_content"

    redacted = redact_text(query)
    if not tags:
        return SafetyDecision(
            allowed=True,
            redacted_text=redacted,
            reason="ok",
        )

    refusal = _build_refusal_message(agent_id, reason or "unsafe_content")
    return SafetyDecision(
        allowed=False,
        redacted_text=redacted,
        reason=reason or "unsafe_content",
        refusal_message=refusal,
        tags=tuple(tags),
    )


def build_scope_refusal(agent_id: AgentID | str) -> str:
    """Build a consistent refusal for out-of-scope requests."""
    agent_key = agent_id.value if isinstance(agent_id, AgentID) else str(agent_id)
    return _SCOPE_REFUSALS.get(
        agent_key,
        "I can help with a narrower set of tasks in this domain.",
    )


def _build_refusal_message(agent_id: AgentID | str, reason: str) -> str:
    if reason == "prompt_injection_detected":
        return "I can't follow instructions that try to override system or tool rules."
    if reason == "secret_retention_request" or reason == "credential_like_content":
        return "I can't help process or retain secrets, tokens, passwords, or similar sensitive data."
    return build_scope_refusal(agent_id)


def _redact_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) < 13 or len(digits) > 19:
        return match.group(0)
    if _luhn_checksum(digits) != 0:
        return match.group(0)
    return _PII_TAGS["card"]


def _luhn_checksum(number: str) -> int:
    total = 0
    reverse_digits = list(map(int, reversed(number)))
    for index, digit in enumerate(reverse_digits):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10
