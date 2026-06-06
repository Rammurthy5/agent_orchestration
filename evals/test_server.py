"""Tests for the Python AgentService server logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import grpc
import pytest

from agents.base.types import AgentID, AgentResponse
from agents.gen.orchestrator.v1 import orchestrator_pb2
from agents.server import AgentServiceServicer


class AbortError(Exception):
    def __init__(self, code, details):
        super().__init__(details)
        self.code = code
        self.details = details


class DummyContext:
    def abort(self, code, details):
        raise AbortError(code, details)


@pytest.fixture
def servicer():
    return AgentServiceServicer()


def _request(agent_id: str, query: str, session_id: str = "test-session"):
    return SimpleNamespace(agent_id=agent_id, query=query, session_id=session_id, metadata={})


def test_execute_unknown_agent(servicer):
    """Unknown agent_id returns NOT_FOUND."""
    with pytest.raises(AbortError) as exc_info:
        servicer.Execute(_request("nonexistent", "hello"), DummyContext())
    assert exc_info.value.code == grpc.StatusCode.NOT_FOUND


@pytest.mark.parametrize(
    "agent_id,query",
    [
        ("flights", "Find flights to Tokyo"),
        ("marketplace", "Find best laptop deals"),
        ("stay", "Hotels in Paris"),
        ("twitter", "Trending hashtags"),
    ],
)
def test_execute_known_agents(servicer, agent_id: str, query: str):
    """Known agent IDs should return a response."""
    enum_id = AgentID(agent_id)
    servicer._agents[enum_id].run = AsyncMock(
        return_value=AgentResponse(agent_id=enum_id, answer="ok")
    )
    servicer._memory.store_conversation = AsyncMock()

    resp = servicer.Execute(_request(agent_id, query), DummyContext())
    assert resp.agent_id == agent_id


def test_execute_stream_unimplemented(servicer):
    """ExecuteStream returns UNIMPLEMENTED for now."""
    with pytest.raises(AbortError) as exc_info:
        servicer.ExecuteStream(
            orchestrator_pb2.ExecuteStreamRequest(
                agent_id="flights",
                query="test",
                session_id="test",
            ),
            DummyContext(),
        )
    assert exc_info.value.code == grpc.StatusCode.UNIMPLEMENTED


def test_execute_preserves_session_id(servicer):
    """Session ID is propagated to the agent."""
    servicer._agents[AgentID.FLIGHTS].run = AsyncMock(
        return_value=AgentResponse(agent_id=AgentID.FLIGHTS, answer="ok")
    )
    servicer._memory.store_conversation = AsyncMock()
    resp = servicer.Execute(_request("flights", "Find flights", "my-unique-session"), DummyContext())
    assert resp.agent_id == "flights"


def test_descriptor_includes_agent_service():
    """The generated protobuf descriptor should include AgentService."""
    services = orchestrator_pb2.DESCRIPTOR.services_by_name
    assert "AgentService" in services
    assert services["AgentService"].full_name == "orchestrator.v1.AgentService"
