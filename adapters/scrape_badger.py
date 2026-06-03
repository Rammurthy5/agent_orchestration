"""ScrapeBadger MCP adapter — used by the Marketplace agent."""

from pydantic import BaseModel

from adapters.base import BaseMCPAdapter
from tools.marketplace import PriceComparison, ProductResult, ProductSearchParams


class ScrapeBadgerAdapter(BaseMCPAdapter):
    """MCP adapter for the ScrapeBadger MCP server.

    Provides product search and price comparison capabilities.
    """

    base_url = "http://localhost:8102/mcp"

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
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

