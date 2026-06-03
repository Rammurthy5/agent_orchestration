"""Twitter MCP Server adapter — used by the Twitter agent."""

from pydantic import BaseModel

from adapters.base import BaseMCPAdapter
from tools.twitter import SentimentResult, TrendResult, TweetResult, TweetSearchParams


class TwitterMCPAdapter(BaseMCPAdapter):
    """MCP adapter for the twitter-mcp-server.

    Provides tweet search, sentiment analysis, and trending topics.
    """

    base_url = "http://localhost:8101/mcp"

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
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

