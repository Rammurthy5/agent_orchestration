"""Twitter MCP Server adapter — used by the Twitter agent."""

from adapters.base import BaseMCPAdapter


class TwitterMCPAdapter(BaseMCPAdapter):
    """MCP adapter for the twitter-mcp-server.

    Provides tweet search, sentiment analysis, and trending topics.
    """

    base_url = "http://localhost:8101/mcp"

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        super().__init__(base_url=base_url, auth_token=auth_token)
