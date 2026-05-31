"""Marketplace agent tool declarations."""

AVAILABLE_TOOLS = [
    {
        "name": "search_products",
        "description": "Search for products matching a query with optional filters",
        "parameters": {
            "query": "Product search query",
            "max_price": "Maximum price filter (optional)",
            "category": "Product category filter (optional)",
        },
    },
    {
        "name": "compare_prices",
        "description": "Compare prices for a specific product across sources",
        "parameters": {
            "product_id": "Product identifier to compare",
        },
    },
]


def get_tool_names() -> list[str]:
    """Return names of all available marketplace tools."""
    return [t["name"] for t in AVAILABLE_TOOLS]
