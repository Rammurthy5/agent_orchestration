"""Twitter MCP Server adapter — used by the Twitter agent.

Connects via MCP Streamable HTTP transport.
Configuration from .vscode/mcp.json (server name: "twitter") or env vars.
"""

import os

from pydantic import BaseModel

from adapters.base import BaseMCPAdapter
from adapters.mcp_config import get_server_config
from tools.twitter import SentimentResult, TrendResult, TweetResult, TweetSearchParams


class TwitterMCPAdapter(BaseMCPAdapter):
    """MCP adapter for the twitter-mcp-server.

    Provides tweet search, sentiment analysis, and trending topics.
    """

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        if not base_url:
            config = get_server_config("twitter")
            if config:
                base_url = config.url
                if not auth_token and "Authorization" in config.headers:
                    auth_header = config.headers["Authorization"]
                    auth_token = auth_header[7:] if auth_header.startswith("Bearer ") else auth_header

        base_url = base_url or os.getenv("TWITTER_MCP_URL", "http://localhost:8101/mcp")
        auth_token = auth_token or os.getenv("TWITTER_MCP_API_KEY", "")
        super().__init__(base_url=base_url, auth_token=auth_token)

    async def search_tweets(self, params: TweetSearchParams) -> list[TweetResult]:
        """Search for tweets matching the given parameters."""
        result = await self.call("search_tweets", params, TweetSearchResult)
        return result.tweets

    async def analyze_sentiment(self, tweet_ids: list[str]) -> SentimentResult:
        """Analyze sentiment of a collection of tweets."""

        class SentimentParams(BaseModel):
            tweet_ids: list[str]

        return await self.call(
            "analyze_sentiment", SentimentParams(tweet_ids=tweet_ids), SentimentResult
        )

    async def get_trends(self, location: str) -> list[TrendResult]:
        """Get current trending topics for a location."""

        class TrendParams(BaseModel):
            location: str

        result = await self.call("get_trends", TrendParams(location=location), TrendSearchResult)
        return result.trends


class TweetSearchResult(BaseModel):
    tweets: list[TweetResult]


class TrendSearchResult(BaseModel):
    trends: list[TrendResult]

