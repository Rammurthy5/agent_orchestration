"""Marketplace tool implementations.

These functions are invoked by the Marketplace agent via the MCP adapter.
"""

from __future__ import annotations

from pydantic import BaseModel


class ProductSearchParams(BaseModel):
    """Parameters for product search."""

    query: str
    max_price: float | None = None
    category: str | None = None


class ProductResult(BaseModel):
    """A single product search result."""

    product_id: str
    name: str
    price_usd: float
    source: str
    rating: float | None = None
    url: str | None = None


class PriceComparison(BaseModel):
    """Price comparison across sources for a product."""

    product_id: str
    prices: list[dict[str, float]]
    lowest_price: float | None = None
    source: str | None = None


async def search_products(params: ProductSearchParams) -> list[ProductResult]:
    """Search products via MCP adapter. Must be called through adapters/scrape_badger.py."""
    raise NotImplementedError("Must be called through ScrapeBadgerAdapter")


async def compare_prices(product_id: str) -> PriceComparison:
    """Compare prices across sources. Must be called through adapters/scrape_badger.py."""
    raise NotImplementedError("Must be called through ScrapeBadgerAdapter")
