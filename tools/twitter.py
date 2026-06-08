"""Twitter/social tool implementations.

These functions are invoked by the Twitter agent via the MCP adapter.
"""

from __future__ import annotations

from pydantic import BaseModel


class TweetSearchParams(BaseModel):
    """Parameters for tweet search."""

    query: str
    count: int = 20

    @property
    def limit(self) -> int:
        """Backward-compatible alias for older code paths."""
        return self.count


class TweetResult(BaseModel):
    """A single tweet result."""

    tweet_id: str = ""
    text: str = ""
    author: str = ""
    likes: int = 0
    retweets: int = 0
    timestamp: str | None = None
    url: str | None = None


class SentimentResult(BaseModel):
    """Sentiment analysis result for a set of tweets."""

    positive: float
    negative: float
    neutral: float
    sample_size: int


class TrendResult(BaseModel):
    """A trending topic."""

    name: str
    tweet_volume: int | None = None
    url: str | None = None


async def search_tweets(params: TweetSearchParams) -> list[TweetResult]:
    """Search tweets via MCP adapter. Must be called through adapters/twitter_mcp.py."""
    raise NotImplementedError("Must be called through TwitterMCPAdapter")


async def analyze_sentiment(topic: str) -> SentimentResult:
    """Analyze sentiment via MCP adapter. Must be called through adapters/twitter_mcp.py."""
    raise NotImplementedError("Must be called through TwitterMCPAdapter")


async def get_trends(topic: str) -> list[TrendResult]:
    """Get trends via MCP adapter. Must be called through adapters/twitter_mcp.py."""
    raise NotImplementedError("Must be called through TwitterMCPAdapter")
