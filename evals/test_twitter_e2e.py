"""End-to-end tests for the Twitter agent using a deterministic LLM stub.

These tests exercise the read-only Twitter MCP path through the full ReAct
loop without opening a socket or calling the external service.
"""

from __future__ import annotations

from agents.base.llm import LLMResponse, LLMToolCall, Message, ToolSpec
from agents.base.types import AgentID, AgentRequest
from agents.twitter import TwitterAgent
from tools.twitter import SentimentResult, TrendResult, TweetResult


class FakeLLM:
    """Deterministic LLM stub for a single Twitter ReAct turn."""

    def __init__(self, tool_name: str, tool_args: dict[str, object], final_answer: str):
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.final_answer = final_answer
        self.calls = 0

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls += 1

        if tools is not None:
            return LLMResponse(
                content="",
                tool_call=LLMToolCall(name=self.tool_name, arguments=self.tool_args),
            )

        prompt = messages[-1].content if messages else ""
        if "Do you have enough information" in prompt:
            return LLMResponse(content="NO - I still need the tool output.")
        if "Synthesize a final answer" in prompt:
            return LLMResponse(content=self.final_answer)

        return LLMResponse(content=f"I should use {self.tool_name}.")


class FakeTwitterAdapter:
    """Read-only adapter stub used for Twitter agent E2E tests."""

    def __init__(
        self,
        tweets: list[TweetResult] | None = None,
        sentiment: SentimentResult | None = None,
        trends: list[TrendResult] | None = None,
    ):
        self.tweets = tweets or []
        self.sentiment = sentiment or SentimentResult(
            positive=0.0,
            negative=0.0,
            neutral=1.0,
            sample_size=0,
        )
        self.trends = trends or []
        self.search_queries: list[str] = []
        self.sentiment_topics: list[str] = []
        self.trend_topics: list[str] = []

    async def search_tweets(self, params):
        self.search_queries.append(params.query)
        return self.tweets

    async def analyze_sentiment(self, topic: str):
        self.sentiment_topics.append(topic)
        return self.sentiment

    async def get_trends(self, topic: str):
        self.trend_topics.append(topic)
        return self.trends


def _tweet(tweet_id: str, text: str, url: str) -> TweetResult:
    return TweetResult(
        tweet_id=tweet_id,
        text=text,
        author="reader",
        likes=12,
        retweets=3,
        url=url,
    )


def _trend(name: str, volume: int) -> TrendResult:
    return TrendResult(name=name, tweet_volume=volume, url=f"https://x.com/search?q={name}")


async def test_twitter_agent_reads_recent_tweets_and_uses_urls() -> None:
    fake_llm = FakeLLM(
        tool_name="search_tweets",
        tool_args={"query": "renewable energy", "count": 10},
        final_answer="People are discussing renewable energy and solar adoption. Source links were included.",
    )
    adapter = FakeTwitterAdapter(
        tweets=[
            _tweet("1", "Renewable energy is getting cheaper fast.", "https://x.com/reader/status/1"),
            _tweet("2", "Solar and wind adoption keeps growing.", "https://x.com/reader/status/2"),
        ]
    )

    agent = TwitterAgent(llm=fake_llm, adapter=adapter)
    response = await agent.run(
        AgentRequest(query="Find recent tweets about renewable energy", session_id="twitter-e2e-1")
    )

    assert response.agent_id == AgentID.TWITTER
    assert response.tool_calls
    assert response.tool_calls[0].tool_name == "search_tweets"
    assert "Renewable energy" in response.steps[0].observation
    assert "x.com/reader/status/1" in response.steps[0].observation
    assert "renewable energy" in response.answer.lower()


async def test_twitter_agent_summarizes_sentiment_from_tweets() -> None:
    fake_llm = FakeLLM(
        tool_name="analyze_sentiment",
        tool_args={"topic": "climate change"},
        final_answer="The sentiment is mixed but leans positive overall.",
    )
    adapter = FakeTwitterAdapter(
        sentiment=SentimentResult(positive=0.6, negative=0.2, neutral=0.2, sample_size=10)
    )

    agent = TwitterAgent(llm=fake_llm, adapter=adapter)
    response = await agent.run(
        AgentRequest(query="Analyze sentiment of tweets about climate change", session_id="twitter-e2e-2")
    )

    assert response.agent_id == AgentID.TWITTER
    assert response.tool_calls
    assert response.tool_calls[0].tool_name == "analyze_sentiment"
    assert "positive" in response.steps[0].observation
    assert "mixed" in response.answer.lower()
