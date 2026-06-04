"""ScrapeBadger MCP adapter — used by the Marketplace agent.

Connects to the ScrapeBadger MCP server using Streamable HTTP transport.
Configuration is loaded from .vscode/mcp.json (server name: "scrapebadger").
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from adapters.base import BaseMCPAdapter
from adapters.mcp_config import get_server_config
from tools.marketplace import PriceComparison, ProductResult, ProductSearchParams


class ScrapeBadgerAdapter(BaseMCPAdapter):
    """MCP adapter for the ScrapeBadger MCP server.

    Provides product search and price comparison capabilities via MCP Streamable HTTP.
    Reads connection details from .vscode/mcp.json or environment variables.
    """

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        # Load from mcp.json if not explicitly provided
        if not base_url or not auth_token:
            config = get_server_config("scrapebadger")
            if config:
                base_url = base_url or config.url
                if not auth_token and "Authorization" in config.headers:
                    # Extract token from "Bearer <token>" header
                    auth_header = config.headers["Authorization"]
                    if auth_header.startswith("Bearer "):
                        auth_token = auth_header[7:]
                    else:
                        auth_token = auth_header

        # Fallback to environment variables
        base_url = base_url or os.getenv("SCRAPE_BADGER_MCP_URL", "https://mcp.scrapebadger.com/mcp")
        auth_token = auth_token or os.getenv("SCRAPE_BADGER_API_KEY", "")

        super().__init__(base_url=base_url, auth_token=auth_token)

    async def search_products(self, params: ProductSearchParams) -> list[ProductResult]:
        """Search for products matching the given parameters."""
        result = await self.call("search_products", params, ProductSearchResult)
        return result.products

    async def compare_prices(self, product_id: str) -> PriceComparison:
        """Compare prices for a product across multiple sources."""

        class PriceParams(BaseModel):
            product_id: str

        return await self.call(
            "compare_prices", PriceParams(product_id=product_id), PriceComparison
        )


class ProductSearchResult(BaseModel):
    products: list[ProductResult]

