"""Marketplace agent tool declarations.

Tools map to real ScrapeBadger MCP server endpoints.
Searches Vinted UK and eBay UK only.
"""

AVAILABLE_TOOLS = [
    {
        "name": "search_products",
        "description": "Search for products on Vinted UK and eBay UK. Returns product names, prices in GBP, source (Vinted UK or eBay UK), and links.",
        "parameters": {
            "query": {"type": "string", "description": "Product search query"},
            "max_price": {"type": "number", "description": "Maximum price in GBP (optional)"},
        },
    },
]


def get_tool_names() -> list[str]:
    """Return names of all available marketplace tools."""
    return [t["name"] for t in AVAILABLE_TOOLS]
