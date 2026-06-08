"""Twitter MCP adapter — used by the Twitter agent.

The upstream `@enescinar/twitter-mcp` package runs as a stdio MCP server via
`npx`, so this adapter prefers the workspace `.vscode/mcp.json` entry named
`twitter-mcp`. A Streamable HTTP fallback is kept for older local setups.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlparse
from pathlib import Path

import httpx
from pydantic import BaseModel

from adapters.base import BaseMCPAdapter
from adapters.mcp_config import get_server_config
from adapters.stdio import BaseMCPStdioAdapter
from tools.twitter import (
    SentimentResult,
    TrendResult,
    TweetResult,
    TweetSearchParams,
)

_POSITIVE_WORDS = {
    "good",
    "great",
    "love",
    "excellent",
    "amazing",
    "awesome",
    "win",
    "bullish",
    "strong",
    "up",
    "happy",
    "positive",
    "best",
    "support",
    "surge",
}

_NEGATIVE_WORDS = {
    "bad",
    "hate",
    "terrible",
    "awful",
    "weak",
    "down",
    "bearish",
    "sad",
    "negative",
    "worst",
    "loss",
    "decline",
    "drop",
}

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "about",
    "your",
    "what",
    "when",
    "where",
    "who",
    "how",
    "why",
    "been",
    "will",
    "are",
    "can",
    "you",
    "tweet",
    "tweets",
    "twitter",
}

_REPO_ROOT = Path(__file__).resolve().parent.parent


class TwitterMCPAdapter:
    """Adapter for the Twitter MCP integration."""

    def __init__(self, base_url: str | None = None, auth_token: str | None = None):
        config = get_server_config("twitter-mcp", _REPO_ROOT) or get_server_config("twitter", _REPO_ROOT)
        self._consumer_key = ""
        self._consumer_secret = ""
        self._access_token = ""
        self._access_token_secret = ""
        self._refresh_twitter_credentials()
        self._direct_client = httpx.AsyncClient(timeout=30.0)

        if config and config.type == "stdio" and config.command:
            self._transport = BaseMCPStdioAdapter(
                command=config.command,
                args=config.args,
                env=config.env,
            )
            return

        if config and config.url and not base_url:
            base_url = config.url
            if not auth_token and "Authorization" in config.headers:
                auth_header = config.headers["Authorization"]
                auth_token = auth_header[7:] if auth_header.startswith("Bearer ") else auth_header

        base_url = base_url or os.getenv("TWITTER_MCP_URL", "http://localhost:8101/mcp")
        auth_token = auth_token or os.getenv("TWITTER_MCP_API_KEY", "")
        self._transport = BaseMCPAdapter(base_url=base_url, auth_token=auth_token)

    async def close(self) -> None:
        await self._transport.close()
        await self._direct_client.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        return await self._transport.list_tools()

    async def search_tweets(self, params: TweetSearchParams) -> list[TweetResult]:
        normalized = params
        if params.count < 10:
            normalized = TweetSearchParams(query=params.query, count=10)
        elif params.count > 100:
            normalized = TweetSearchParams(query=params.query, count=100)

        try:
            result = await self._transport.call("search_tweets", normalized, TweetSearchResult)
            return result.tweets
        except Exception:
            return await self._search_tweets_direct(normalized)

    async def analyze_sentiment(self, topic: str) -> SentimentResult:
        """Analyze topic sentiment using real tweets from the MCP server."""
        tweets = await self.search_tweets(TweetSearchParams(query=topic, count=20))
        if not tweets:
            return SentimentResult(positive=0.0, negative=0.0, neutral=1.0, sample_size=0)

        positive = 0
        negative = 0
        neutral = 0

        for tweet in tweets:
            score = self._sentiment_score(tweet.text)
            if score > 0:
                positive += 1
            elif score < 0:
                negative += 1
            else:
                neutral += 1

        total = len(tweets)
        return SentimentResult(
            positive=round(positive / total, 3),
            negative=round(negative / total, 3),
            neutral=round(neutral / total, 3),
            sample_size=total,
        )

    async def get_trends(self, topic: str) -> list[TrendResult]:
        """Infer current topic trends from recent matching tweets."""
        tweets = await self.search_tweets(TweetSearchParams(query=topic, count=25))
        if not tweets:
            return []

        counts: Counter[str] = Counter()
        for tweet in tweets:
            for token in self._extract_trend_tokens(tweet.text):
                counts[token] += 1

        results: list[TrendResult] = []
        for name, volume in counts.most_common(5):
            results.append(TrendResult(name=name, tweet_volume=volume, url=None))
        return results

    def _sentiment_score(self, text: str) -> int:
        lowered = text.lower()
        positive = sum(1 for word in _POSITIVE_WORDS if word in lowered)
        negative = sum(1 for word in _NEGATIVE_WORDS if word in lowered)
        return positive - negative

    def _extract_trend_tokens(self, text: str) -> list[str]:
        tokens = re.findall(r"#?[A-Za-z0-9_]{3,}", text)
        filtered: list[str] = []
        for token in tokens:
            normalized = token.lstrip("#").lower()
            if normalized in _STOPWORDS:
                continue
            if len(normalized) < 3:
                continue
            filtered.append(token if token.startswith("#") else normalized)
        return filtered

    async def _search_tweets_direct(self, params: TweetSearchParams) -> list[TweetResult]:
        self._refresh_twitter_credentials()
        if not (self._consumer_key and self._consumer_secret and self._access_token and self._access_token_secret):
            raise RuntimeError(
                "Twitter credentials are incomplete for direct search fallback "
                "(need API_KEY, API_SECRET_KEY, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)"
            )

        url = "https://api.twitter.com/2/tweets/search/recent"
        query_params: dict[str, str] = {
            "query": params.query,
            "max_results": str(params.count),
            "tweet.fields": "author_id,created_at,public_metrics",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        auth_header = self._build_oauth1_header("GET", url, query_params)
        response = await self._direct_client.get(url, params=query_params, headers={"Authorization": auth_header})
        response.raise_for_status()
        payload = response.json()
        return self._parse_recent_search(payload)

    def _parse_recent_search(self, payload: dict[str, Any]) -> list[TweetResult]:
        users = {
            user.get("id"): user
            for user in payload.get("includes", {}).get("users", [])
            if isinstance(user, dict) and user.get("id")
        }
        results: list[TweetResult] = []
        for item in payload.get("data", []) or []:
            if not isinstance(item, dict):
                continue
            author_id = item.get("author_id")
            user = users.get(author_id, {})
            username = user.get("username") or user.get("name") or "unknown"
            tweet_id = str(item.get("id") or "")
            results.append(
                TweetResult(
                    tweet_id=tweet_id,
                    text=str(item.get("text") or ""),
                    author=str(username),
                    likes=int(item.get("public_metrics", {}).get("like_count", 0) or 0),
                    retweets=int(item.get("public_metrics", {}).get("retweet_count", 0) or 0),
                    timestamp=item.get("created_at"),
                    url=f"https://x.com/{username}/status/{tweet_id}" if tweet_id else None,
                )
            )
        return results

    def _build_oauth1_header(self, method: str, url: str, params: dict[str, str]) -> str:
        oauth_params = {
            "oauth_consumer_key": self._consumer_key,
            "oauth_token": self._access_token,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_nonce": secrets.token_hex(16),
            "oauth_version": "1.0",
        }
        signature_params = {**params, **oauth_params}
        normalized = "&".join(
            f"{self._oauth_escape(k)}={self._oauth_escape(v)}"
            for k, v in sorted(signature_params.items())
        )
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}{urlparse(url).path}"
        base_string = "&".join(
            [
                method.upper(),
                self._oauth_escape(base_url),
                self._oauth_escape(normalized),
            ]
        )
        signing_key = f"{self._oauth_escape(self._consumer_secret)}&{self._oauth_escape(self._access_token_secret)}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
        ).decode()
        oauth_params["oauth_signature"] = signature
        header_params = ", ".join(
            f'{self._oauth_escape(k)}="{self._oauth_escape(v)}"' for k, v in oauth_params.items()
        )
        return f"OAuth {header_params}"

    def _refresh_twitter_credentials(self) -> None:
        config = get_server_config("twitter-mcp", _REPO_ROOT) or get_server_config("twitter", _REPO_ROOT)
        config_env = config.env if config else {}
        self._consumer_key = (
            config_env.get("API_KEY")
            or os.getenv("TWITTER_API_KEY")
            or os.getenv("API_KEY")
            or self._consumer_key
            or ""
        )
        self._consumer_secret = (
            config_env.get("API_SECRET_KEY")
            or os.getenv("TWITTER_API_SECRET_KEY")
            or os.getenv("API_SECRET_KEY")
            or self._consumer_secret
            or ""
        )
        self._access_token = (
            config_env.get("ACCESS_TOKEN")
            or os.getenv("TWITTER_ACCESS_TOKEN")
            or os.getenv("ACCESS_TOKEN")
            or self._access_token
            or ""
        )
        self._access_token_secret = (
            config_env.get("ACCESS_TOKEN_SECRET")
            or os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
            or os.getenv("ACCESS_TOKEN_SECRET")
            or self._access_token_secret
            or ""
        )

    @staticmethod
    def _oauth_escape(value: str) -> str:
        return quote(str(value), safe="~-._")


class TweetSearchResult(BaseModel):
    tweets: list[TweetResult]
