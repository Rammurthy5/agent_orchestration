"""End-to-end test for the marketplace agent using workspace MCP config."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from adapters.mcp_config import get_server_config
from adapters.scrape_badger import ScrapeBadgerAdapter
from agents.base.llm import LLMResponse, LLMToolCall, Message, ToolSpec
from agents.base.types import AgentID, AgentRequest
from agents.marketplace import MarketplaceAgent


class FakeLLM:
    """Deterministic LLM stub for a single marketplace ReAct turn."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls += 1

        if tools is not None:
            return LLMResponse(
                content="",
                tool_call=LLMToolCall(
                    name="search_products",
                    arguments={
                        "query": "noise-cancelling headphones",
                        "max_price": 300,
                    },
                ),
            )

        if self.calls == 1:
            return LLMResponse(content="I should search for the best matching product.")

        if self.calls == 3:
            return LLMResponse(content="NO - I have enough information to answer.")

        return LLMResponse(
            content="The best option is the SoundCore Space A40 at $79.99 from example-store."
        )


def test_scrapebadger_config_comes_from_workspace_file() -> None:
    """Verify the marketplace adapter reads .vscode/mcp.json."""
    workspace_root = Path(__file__).resolve().parents[1]
    config = get_server_config("scrapebadger", workspace_root)

    assert config is not None
    assert config.url == "https://mcp.scrapebadger.com/mcp"
    assert "Authorization" in config.headers


@pytest.mark.asyncio
async def test_marketplace_agent_e2e_uses_workspace_mcp_config() -> None:
    """Run the marketplace agent through its full ReAct loop with MCP transport mocked."""
    fake_llm = FakeLLM()
    adapter = ScrapeBadgerAdapter()
    adapter._client.post = AsyncMock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "scrapebadger", "version": "test"},
                    },
                },
                headers={"mcp-session-id": "session-1"},
            ),
            httpx.Response(204),
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    '{"products":[{"product_id":"p1","name":"SoundCore Space A40",'
                                    '"price_usd":79.99,"source":"example-store",'
                                    '"rating":4.7,"url":"https://example.com/p1"}]}'
                                ),
                            }
                        ]
                    },
                },
            ),
        ]
    )

    agent = MarketplaceAgent(llm=fake_llm, adapter=adapter)
    response = await agent.run(
        AgentRequest(
            query="Find the best price for noise-cancelling headphones under $300",
            session_id="marketplace-e2e",
        )
    )

    assert response.agent_id == AgentID.MARKETPLACE
    assert response.answer
    assert response.tool_calls
    assert response.tool_calls[0].tool_name == "search_products"
    assert "SoundCore Space A40" in response.answer
    assert adapter.base_url == "https://mcp.scrapebadger.com/mcp"
    assert adapter._session_id == "session-1"
