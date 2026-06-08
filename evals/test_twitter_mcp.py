"""Twitter MCP adapter tests.

Covers the read-only Twitter transport path and the derived read actions
used by the Twitter agent.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from adapters.base import MCPError
from adapters.twitter_mcp import TwitterMCPAdapter
from tools.twitter import SentimentResult, TrendResult, TweetResult, TweetSearchParams


class FakeTransport:
    """Minimal transport stub for adapter-level tests."""

    def __init__(self, tweets: list[TweetResult] | None = None):
        self.tweets = tweets or []
        self.calls: list[tuple[str, object]] = []

    async def call(self, method, params, response_model):
        self.calls.append((method, params))
        if response_model.__name__ == "TweetSearchResult":
            return response_model(tweets=self.tweets)
        raise AssertionError(f"Unexpected response model: {response_model.__name__}")


def _make_tweet(tweet_id: str, text: str, author: str = "user", url: str | None = None) -> TweetResult:
    return TweetResult(
        tweet_id=tweet_id,
        text=text,
        author=author,
        likes=10,
        retweets=2,
        url=url,
    )


@pytest.mark.asyncio
async def test_search_tweets_uses_transport_and_returns_tweets() -> None:
    adapter = TwitterMCPAdapter(base_url="http://localhost:8101/mcp")
    fake_transport = FakeTransport(
        tweets=[
            _make_tweet("1", "Renewable energy is getting cheaper fast.", "alice", "https://x.com/a/1"),
            _make_tweet("2", "Solar and wind adoption keeps growing.", "bob", "https://x.com/b/2"),
        ]
    )
    adapter._transport = fake_transport

    results = await adapter.search_tweets(TweetSearchParams(query="renewable energy", count=10))

    assert len(results) == 2
    assert results[0].text.startswith("Renewable energy")
    assert fake_transport.calls[0][0] == "search_tweets"
    assert fake_transport.calls[0][1].query == "renewable energy"
    assert fake_transport.calls[0][1].count == 10


@pytest.mark.asyncio
async def test_analyze_sentiment_aggregates_read_tweets() -> None:
    adapter = TwitterMCPAdapter(base_url="http://localhost:8101/mcp")
    adapter.search_tweets = AsyncMock(
        return_value=[
            _make_tweet("1", "Great progress on clean energy and excellent policy support."),
            _make_tweet("2", "This policy looks bad for consumers."),
            _make_tweet("3", "Solar adoption is increasing."),
        ]
    )

    result = await adapter.analyze_sentiment("clean energy")

    assert result.sample_size == 3
    assert result.positive == pytest.approx(0.333, rel=1e-2)
    assert result.negative == pytest.approx(0.333, rel=1e-2)
    assert result.neutral == pytest.approx(0.333, rel=1e-2)


@pytest.mark.asyncio
async def test_get_trends_collects_topics_from_recent_tweets() -> None:
    adapter = TwitterMCPAdapter(base_url="http://localhost:8101/mcp")
    adapter.search_tweets = AsyncMock(
        return_value=[
            _make_tweet("1", "#MachineLearning is moving fast and machine adoption is rising."),
            _make_tweet("2", "Machine learning keeps getting better."),
            _make_tweet("3", "#MachineLearning and machine are everywhere."),
        ]
    )

    trends = await adapter.get_trends("AI")

    assert trends
    assert trends[0].name.lower() in {"machine", "learning"}
    assert any(item.name.lower() == "machine" for item in trends)


def test_twitter_adapter_is_read_only() -> None:
    adapter = TwitterMCPAdapter(base_url="http://localhost:8101/mcp")
    assert not hasattr(adapter, "post_tweet")


@pytest.mark.asyncio
async def test_search_tweets_falls_back_to_direct_x_api_when_mcp_fails() -> None:
    adapter = TwitterMCPAdapter(base_url="http://localhost:8101/mcp")
    adapter._consumer_key = "ck"
    adapter._consumer_secret = "cs"
    adapter._access_token = "at"
    adapter._access_token_secret = "ats"
    adapter._transport.call = AsyncMock(side_effect=MCPError("search_tweets", "URL error", 1))

    payload = {
        "data": [
            {
                "id": "111",
                "text": "Makerfield by-election is drawing local attention.",
                "author_id": "u1",
                "created_at": "2026-06-07T00:00:00.000Z",
                "public_metrics": {"like_count": 12, "retweet_count": 3},
            }
        ],
        "includes": {
            "users": [
                {"id": "u1", "username": "uknews", "name": "UK News"},
            ]
        },
    }

    response = httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", "https://api.twitter.com/2/tweets/search/recent"),
    )
    adapter._direct_client.get = AsyncMock(return_value=response)

    results = await adapter.search_tweets(TweetSearchParams(query="Makerfield by-election", count=10))

    assert len(results) == 1
    assert results[0].tweet_id == "111"
    assert results[0].author == "uknews"
    assert "Makerfield" in results[0].text


@pytest.mark.asyncio
async def test_search_tweets_refreshes_credentials_before_direct_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = TwitterMCPAdapter(base_url="http://localhost:8101/mcp")
    adapter._consumer_key = ""
    adapter._consumer_secret = ""
    adapter._access_token = ""
    adapter._access_token_secret = ""
    adapter._transport.call = AsyncMock(side_effect=MCPError("search_tweets", "URL error", 1))

    monkeypatch.setattr(
        "adapters.twitter_mcp.get_server_config",
        lambda name, workspace_root=None: SimpleNamespace(
            env={
                "API_KEY": "ck",
                "API_SECRET_KEY": "cs",
                "ACCESS_TOKEN": "at",
                "ACCESS_TOKEN_SECRET": "ats",
            }
        ),
    )

    payload = {
        "data": [
            {
                "id": "222",
                "text": "Makerfield by-election continues to trend locally.",
                "author_id": "u2",
                "created_at": "2026-06-07T00:00:00.000Z",
                "public_metrics": {"like_count": 8, "retweet_count": 1},
            }
        ],
        "includes": {
            "users": [
                {"id": "u2", "username": "localnews", "name": "Local News"},
            ]
        },
    }

    response = httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", "https://api.twitter.com/2/tweets/search/recent"),
    )
    adapter._direct_client.get = AsyncMock(return_value=response)

    results = await adapter.search_tweets(TweetSearchParams(query="Makerfield by-election", count=10))

    assert len(results) == 1
    assert results[0].tweet_id == "222"
    assert results[0].author == "localnews"


def test_twitter_adapter_resolves_workspace_root_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object | None]] = []

    def fake_get_server_config(name: str, workspace_root=None):
        calls.append((name, workspace_root))
        return None

    monkeypatch.setattr("adapters.twitter_mcp.get_server_config", fake_get_server_config)

    TwitterMCPAdapter(base_url="http://localhost:8101/mcp")

    assert calls[0][0] == "twitter-mcp"
    assert calls[0][1] is not None
    assert str(calls[0][1]).endswith("agent_orchestration")
