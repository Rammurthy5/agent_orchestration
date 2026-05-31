"""ScrapeBadger MCP adapter — used by the Marketplace agent."""

from adapters.base import BaseMCPAdapter


class ScrapeBadgerAdapter(BaseMCPAdapter):
    """MCP adapter for the ScrapeBadger MCP server.

    Provides product search and price comparison capabilities.
    """

    base_url = "http://localhost:8102/mcp"

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        super().__init__(base_url=base_url, auth_token=auth_token)
