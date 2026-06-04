"""Python gRPC server implementing the AgentService.

The Go orchestrator connects to this server to execute tasks on specialized agents.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from concurrent import futures

import grpc
from grpc_reflection.v1alpha import reflection

from agents.base import AgentID, AgentRequest, BaseAgent, Memory
from agents.base.llm import LLMClient
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
        self._llm = LLMClient()
        self._memory = Memory(
            dsn=os.getenv("DATABASE_URL", "postgresql://localhost:5432/orchestrator")
        )
        self._agents: dict[str, BaseAgent] = {
            AgentID.FLIGHTS: FlightsAgent(llm=self._llm),
            AgentID.MARKETPLACE: MarketplaceAgent(llm=self._llm),
            AgentID.STAY: StayAgent(llm=self._llm),
            AgentID.TWITTER: TwitterAgent(llm=self._llm),
        }
        # Persistent event loop for async agent execution
        self._loop = asyncio.new_event_loop()
        import threading
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()

    async def start(self) -> None:
        await self._memory.connect()
        logger.info("Agent service connected to memory")

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

        loop = self._loop
        try:
            future = asyncio.run_coroutine_threadsafe(agent.run(agent_request), loop)
            response = future.result(timeout=60)
            # Store conversation in memory (best-effort, non-blocking on failure)
            try:
                from agents.base.memory import ConversationEntry
                
                store_future = asyncio.run_coroutine_threadsafe(
                    self._memory.store_conversation(
                        ConversationEntry(
                            session_id=request.session_id,
                            agent_id=agent_id,
                            query=request.query,
                            response=response.answer,
                            latency_ms=response.latency_ms,
                        )
                    ),
                    loop,
                )
                store_future.result(timeout=5)
            except Exception as mem_err:
                logger.warning("memory store failed", extra={"error": str(mem_err)})
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
        except (ConnectionError, OSError) as e:
            # LLM or external service unavailable — graceful degradation
            logger.warning("agent execution failed (connectivity)", extra={
                "agent_id": agent_id, "error": str(e),
            })
            return orchestrator_pb2.ExecuteResponse(
                agent_id=agent_id,
                answer=f"[{agent_id}] Service temporarily unavailable",
                latency_ms=0,
            )
        except Exception as e:
            import httpx
            if isinstance(e, (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)):
                logger.warning("agent LLM call failed", extra={
                    "agent_id": agent_id, "error": str(e),
                })
                return orchestrator_pb2.ExecuteResponse(
                    agent_id=agent_id,
                    answer=f"[{agent_id}] Service temporarily unavailable",
                    latency_ms=0,
                )
            context.abort(grpc.StatusCode.INTERNAL, str(e))
            return orchestrator_pb2.ExecuteResponse()

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

    async def shutdown(self) -> None:
        await self._memory.close()
        logger.info("Agent service memory connection closed")

def serve(port: int = 50052) -> None:
    """Start the Python agent gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = AgentServiceServicer()
    orchestrator_pb2_grpc.add_AgentServiceServicer_to_server(
        servicer, server
    )
    # after the loop thread starts
    asyncio.run_coroutine_threadsafe(servicer.start(), servicer._loop).result(timeout=5)
    # Enable server reflection for grpcurl / debugging tools
    service_names = (
        orchestrator_pb2.DESCRIPTOR.services_by_name["AgentService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)
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
