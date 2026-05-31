"""Travel Hacking Toolkit MCP adapter — used by Flights and Stay agents."""

from adapters.base import BaseMCPAdapter


class TravelHackingAdapter(BaseMCPAdapter):
    """MCP adapter for the travel-hacking-toolkit server.

    Provides flight search, route comparison, hotel search, and availability checking.
    """

    base_url = "http://localhost:8100/mcp"

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        super().__init__(base_url=base_url, auth_token=auth_token)
