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


def _resp(status_code: int, **kwargs) -> httpx.Response:
    """Create an httpx.Response with a dummy request attached (required for raise_for_status)."""
    resp = httpx.Response(status_code, **kwargs)
    resp._request = httpx.Request("POST", "https://mcp.scrapebadger.com/mcp")
    return resp


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
                        "query": "raincoats women XXL",
                    },
                ),
            )

        if self.calls == 1:
            return LLMResponse(content="I should search for raincoats on Vinted UK and eBay UK.")

        if self.calls == 3:
            return LLMResponse(content="NO - I have enough information to answer.")

        return LLMResponse(
            content="The best option is the JBC Collection XXL Navy jacket at £2.50 from Vinted UK. Link: https://www.vinted.co.uk/items/123"
        )


# --- Vinted UK response fixtures ---

VINTED_UK_MCP_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "content": [
            {
                "type": "text",
                "text": (
                    '{"items":[{"id":"8840648214","title":"JBC Collection size XXL Navy floral rain jacket",'
                    '"price":{"amount":"2.50","currency_code":"GBP"},'
                    '"url":"https://www.vinted.co.uk/items/8840648214-jbc-collection-size-xxl-navy-floral-rain-jacket"},'
                    '{"id":"8422686251","title":"JBC size 24 silver grey lightweight raincoat",'
                    '"price":{"amount":"3.99","currency_code":"GBP"},'
                    '"url":"https://www.vinted.co.uk/items/8422686251-jbc-size-24-silver-grey-lightweight-raincoat"}]}'
                ),
            }
        ]
    },
}

EBAY_UK_MCP_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 3,
    "result": {
        "content": [
            {
                "type": "text",
                "text": (
                    '{"shopping_results":[{"product_id":"eb001","title":"Women XXL Waterproof Raincoat",'
                    '"extracted_price":12.99,"source":"eBay UK","rating":4.2,'
                    '"product_link":"https://www.ebay.co.uk/itm/123456"}]}'
                ),
            }
        ]
    },
}


def test_scrapebadger_config_comes_from_workspace_file() -> None:
    """Verify the marketplace adapter reads .vscode/mcp.json."""
    workspace_root = Path(__file__).resolve().parents[1]
    config = get_server_config("scrapebadger", workspace_root)

    assert config is not None
    assert config.url == "https://mcp.scrapebadger.com/mcp"
    assert "Authorization" in config.headers


@pytest.mark.asyncio
async def test_marketplace_agent_searches_vinted_and_ebay_uk() -> None:
    """Run the marketplace agent — verify it searches Vinted UK and eBay UK."""
    fake_llm = FakeLLM()
    adapter = ScrapeBadgerAdapter()

    # Mock MCP transport: initialize, initialized notification, vinted call, ebay call
    adapter._client.post = AsyncMock(
        side_effect=[
            # initialize
_resp(
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
                headers={"mcp-session-id": "session-uk-1"},
            ),
            # initialized notification
_resp(204),
            # vinted_search_items call
_resp(200, json=VINTED_UK_MCP_RESPONSE),
            # google_shopping_search (eBay UK filtered) call
_resp(200, json=EBAY_UK_MCP_RESPONSE),
        ]
    )

    agent = MarketplaceAgent(llm=fake_llm, adapter=adapter)
    response = await agent.run(
        AgentRequest(
            query="Find raincoats for women size XXL",
            session_id="marketplace-vinted-ebay-e2e",
        )
    )

    assert response.agent_id == AgentID.MARKETPLACE
    assert response.answer
    assert response.tool_calls
    assert response.tool_calls[0].tool_name == "search_products"
    # Verify answer references Vinted UK content
    assert "Vinted UK" in response.answer or "vinted.co.uk" in response.answer


@pytest.mark.asyncio
async def test_marketplace_results_include_product_urls() -> None:
    """Verify that search results include clickable product URLs."""
    adapter = ScrapeBadgerAdapter()

    # Mock transport
    adapter._client.post = AsyncMock(
        side_effect=[
_resp(
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
                headers={"mcp-session-id": "session-url-test"},
            ),
_resp(204),
_resp(200, json=VINTED_UK_MCP_RESPONSE),
_resp(200, json=EBAY_UK_MCP_RESPONSE),
        ]
    )

    from tools.marketplace import ProductSearchParams
    results = await adapter.search_products(ProductSearchParams(query="raincoats XXL"))

    # All results must have URLs
    assert len(results) > 0
    for r in results:
        assert r.url is not None
        assert r.url.startswith("https://")

    # Vinted results have vinted.co.uk URLs
    vinted_results = [r for r in results if r.source == "Vinted UK"]
    assert len(vinted_results) > 0
    for r in vinted_results:
        assert "vinted.co.uk" in r.url

    # eBay results have ebay.co.uk URLs
    ebay_results = [r for r in results if r.source == "eBay UK"]
    assert len(ebay_results) > 0
    for r in ebay_results:
        assert "ebay.co.uk" in r.url


@pytest.mark.asyncio
async def test_marketplace_vinted_results_are_gbp() -> None:
    """Verify Vinted UK results have GBP prices."""
    adapter = ScrapeBadgerAdapter()

    adapter._client.post = AsyncMock(
        side_effect=[
_resp(
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
                headers={"mcp-session-id": "session-gbp-test"},
            ),
_resp(204),
_resp(200, json=VINTED_UK_MCP_RESPONSE),
_resp(200, json=EBAY_UK_MCP_RESPONSE),
        ]
    )

    from tools.marketplace import ProductSearchParams
    results = await adapter.search_products(ProductSearchParams(query="raincoats XXL"))

    vinted_results = [r for r in results if r.source == "Vinted UK"]
    assert vinted_results[0].price_usd == 2.50
    assert vinted_results[1].price_usd == 3.99


@pytest.mark.asyncio
async def test_marketplace_only_searches_vinted_and_ebay_uk() -> None:
    """Verify adapter only calls vinted_search_items and google_shopping_search (eBay UK)."""
    adapter = ScrapeBadgerAdapter()

    calls_made = []

    async def mock_post(url, **kwargs):
        body = kwargs.get("json") or kwargs.get("content")
        if isinstance(body, (str, bytes)):
            import json
            body = json.loads(body)

        if body and body.get("method") == "tools/call":
            tool_name = body["params"]["name"]
            calls_made.append(tool_name)

            if tool_name == "vinted_search_items":
                # Verify market is UK
                assert body["params"]["arguments"]["market"] == "uk"
                return _resp(200, json=VINTED_UK_MCP_RESPONSE)
            elif tool_name == "google_shopping_search":
                # Verify query contains site:ebay.co.uk
                assert "site:ebay.co.uk" in body["params"]["arguments"]["q"]
                assert body["params"]["arguments"]["gl"] == "uk"
                return _resp(200, json=EBAY_UK_MCP_RESPONSE)

        if body and body.get("method") == "initialize":
            return _resp(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "scrapebadger", "version": "test"},
                    },
                },
                headers={"mcp-session-id": "session-only-uk"},
            )

        return _resp(204)

    adapter._client.post = AsyncMock(side_effect=mock_post)

    from tools.marketplace import ProductSearchParams
    await adapter.search_products(ProductSearchParams(query="raincoats women XXL"))

    assert "vinted_search_items" in calls_made
    assert "google_shopping_search" in calls_made
    # Should NOT call amazon_search, amazon_get_offers, etc.
    assert "amazon_search" not in calls_made
    assert "amazon_get_offers" not in calls_made
