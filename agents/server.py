"""Python gRPC server implementing the AgentService.

The Go orchestrator connects to this server to execute tasks on specialized agents.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent import futures

import grpc

from agents.base import AgentID, AgentRequest, BaseAgent
from agents.base.types import OutOfScopeError
from agents.flights import FlightsAgent
from agents.marketplace import MarketplaceAgent
from agents.stay import StayAgent
from agents.twitter import TwitterAgent
from agents.gen.orchestrator.v1 import orchestrator_pb2, orchestrator_pb2_grpc

logger = logging.getLogger(__name__)


class AgentServiceServicer(orchestrator_pb2_grpc.AgentServiceServicer):
    """gRPC servicer that dispatches requests to the appropriate Python agent."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {
            AgentID.FLIGHTS: FlightsAgent(),
            AgentID.MARKETPLACE: MarketplaceAgent(),
            AgentID.STAY: StayAgent(),
            AgentID.TWITTER: TwitterAgent(),
        }

    def Execute(self, request: orchestrator_pb2.ExecuteRequest, context: grpc.ServicerContext):
        """Run the full ReAct loop for the specified agent."""
        agent_id = request.agent_id
        agent = self._agents.get(agent_id)
        if agent is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"agent {agent_id!r} not found")
            return orchestrator_pb2.ExecuteResponse()

        logger.info("executing agent", extra={"agent_id": agent_id, "session_id": request.session_id})

        agent_request = AgentRequest(
            query=request.query,
            session_id=request.session_id,
            metadata=dict(request.metadata),
        )

        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(agent.run(agent_request))
        except NotImplementedError:
            # Agent methods not yet wired to LLM — return placeholder
            return orchestrator_pb2.ExecuteResponse(
                agent_id=agent_id,
                answer=f"[{agent_id}] Agent not yet implemented",
                latency_ms=0,
            )
        except OutOfScopeError as e:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Query out of scope for agent {agent_id!r}: {e.query}",
            )
            return orchestrator_pb2.ExecuteResponse()
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, str(e))
            return orchestrator_pb2.ExecuteResponse()
        finally:
            loop.close()

        # Convert agent response to protobuf
        pb_steps = []
        for step in response.steps:
            pb_tool_call = None
            if step.tool_call:
                pb_tool_call = orchestrator_pb2.ToolCall(
                    tool_name=step.tool_call.tool_name,
                    result=step.tool_call.result or "",
                    latency_ms=step.tool_call.latency_ms or 0,
                )
            pb_steps.append(orchestrator_pb2.Step(
                thought=step.thought,
                action=step.action or "",
                observation=step.observation or "",
                tool_call=pb_tool_call,
            ))

        pb_tool_calls = []
        for tc in response.tool_calls:
            pb_tool_calls.append(orchestrator_pb2.ToolCall(
                tool_name=tc.tool_name,
                result=tc.result or "",
                latency_ms=tc.latency_ms or 0,
            ))

        return orchestrator_pb2.ExecuteResponse(
            agent_id=response.agent_id.value,
            answer=response.answer,
            steps=pb_steps,
            tool_calls=pb_tool_calls,
            latency_ms=response.latency_ms or 0,
        )

    def ExecuteStream(self, request: orchestrator_pb2.ExecuteStreamRequest, context: grpc.ServicerContext):
        """Stream ReAct steps as they happen.

        TODO: Implement streaming once agents support step-by-step callbacks.
        """
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "streaming not yet implemented")


def serve(port: int = 50052) -> None:
    """Start the Python agent gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    orchestrator_pb2_grpc.add_AgentServiceServicer_to_server(
        AgentServiceServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info(f"Agent service started on port {port}")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()
