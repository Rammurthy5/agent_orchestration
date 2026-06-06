"""ScrapeBadger MCP adapter — used by the Marketplace agent.

Connects to the ScrapeBadger MCP server using Streamable HTTP transport.
Configuration is loaded from .vscode/mcp.json (server name: "scrapebadger").

Marketplace sources:
  - Vinted UK: vinted_search_items(query, market="uk", ...)
  - eBay UK: google_shopping_search filtered to ebay.co.uk
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel

from adapters.base import BaseMCPAdapter
from adapters.mcp_config import get_server_config
from tools.marketplace import PriceComparison, ProductResult, ProductSearchParams


class ScrapeBadgerAdapter(BaseMCPAdapter):
    """MCP adapter for the ScrapeBadger MCP server.

    Searches Vinted UK and eBay UK for product listings.
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
        """Search both Vinted UK and eBay UK, returning combined results."""
        await self.ensure_initialized()

        vinted_results = await self._search_vinted(params)
        ebay_results = await self._search_ebay(params)

        return vinted_results + ebay_results

    async def _search_vinted(self, params: ProductSearchParams) -> list[ProductResult]:
        """Search Vinted UK marketplace."""
        args: dict[str, Any] = {"query": params.query, "market": "uk"}
        if params.max_price is not None:
            args["price_to"] = params.max_price

        raw = await self._call_tool("vinted_search_items", args)
        return self._parse_vinted_results(raw)

    async def _search_ebay(self, params: ProductSearchParams) -> list[ProductResult]:
        """Search eBay UK via Google Shopping filtered to ebay.co.uk."""
        query = f"{params.query} site:ebay.co.uk"
        args: dict[str, Any] = {"q": query, "gl": "uk", "hl": "en"}
        if params.max_price is not None:
            args["max_price"] = params.max_price

        raw = await self._call_tool("google_shopping_search", args)
        return self._parse_ebay_results(raw)

    async def compare_prices(self, product_id: str) -> PriceComparison:
        """Compare prices — returns a simple comparison from available data."""
        return PriceComparison(
            product_id=product_id,
            lowest_price=0,
            prices=[],
        )

    def _parse_vinted_results(self, raw: dict[str, Any]) -> list[ProductResult]:
        """Parse Vinted search response into ProductResult list."""
        results: list[ProductResult] = []

        if "result" in raw and isinstance(raw["result"], str):
            try:
                raw = json.loads(raw["result"])
            except json.JSONDecodeError:
                return results

        items = raw.get("items") or raw.get("results") or []
        if isinstance(items, list):
            for item in items[:10]:
                try:
                    price = item.get("price") or item.get("total_item_price") or {}
                    if isinstance(price, dict):
                        price_val = float(price.get("amount") or price.get("value") or 0)
                    elif isinstance(price, str):
                        price_val = float(price.replace("£", "").replace(",", "").strip() or "0")
                    else:
                        price_val = float(price)

                    item_id = str(item.get("id") or item.get("item_id") or "")
                    title = item.get("title") or "Unknown"
                    url = item.get("url") or f"https://www.vinted.co.uk/items/{item_id}"

                    results.append(ProductResult(
                        product_id=item_id,
                        name=title,
                        price_usd=price_val,  # Actually GBP for UK
                        source="Vinted UK",
                        rating=None,
                        url=url,
                    ))
                except (ValueError, TypeError):
                    continue

        return results

    def _parse_ebay_results(self, raw: dict[str, Any]) -> list[ProductResult]:
        """Parse Google Shopping (eBay UK filtered) response into ProductResult list."""
        results: list[ProductResult] = []

        if "result" in raw and isinstance(raw["result"], str):
            try:
                raw = json.loads(raw["result"])
            except json.JSONDecodeError:
                return results

        items = raw.get("shopping_results") or raw.get("results") or []
        if isinstance(items, list):
            for item in items[:10]:
                try:
                    price = item.get("extracted_price") or item.get("price", 0)
                    if isinstance(price, dict):
                        price = price.get("value", 0)
                    if isinstance(price, str):
                        price = float(price.replace("£", "").replace("$", "").replace(",", "").strip() or "0")

                    title = item.get("title", "Unknown")
                    product_link = item.get("product_link") or item.get("link")
                    url = product_link or f"https://www.ebay.co.uk/sch/i.html?_nkw={quote_plus(title)}"

                    results.append(ProductResult(
                        product_id=str(item.get("product_id") or item.get("gpcid") or ""),
                        name=title,
                        price_usd=float(price),  # Actually GBP for UK
                        source="eBay UK",
                        rating=item.get("rating"),
                        url=url,
                    ))
                except (ValueError, TypeError):
                    continue

        return results