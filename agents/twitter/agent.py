"""Twitter agent — social trend analysis, tweet generation, sentiment extraction."""

from __future__ import annotations

import json
import time

from langsmith import traceable

from adapters.twitter_mcp import TwitterMCPAdapter
from agents.base import (
    AgentID,
    AgentRequest,
    BaseAgent,
    ReflectionResult,
    Step,
    ToolCall,
)
from agents.base.llm import LLMClient, ToolSpec
from agents.twitter.tools import AVAILABLE_TOOLS
from tools.twitter import TweetSearchParams


class TwitterAgent(BaseAgent):
    """Specialized agent for social media analysis and content generation."""

    agent_id = AgentID.TWITTER

    def __init__(self, llm: LLMClient | None = None, adapter: TwitterMCPAdapter | None = None):
        super().__init__(llm=llm)
        self.adapter = adapter or TwitterMCPAdapter()

    def _domain_keywords(self) -> list[str]:
        return [
            "twitter", "tweet", "hashtag", "trending", "retweet",
            "follower", "timeline", "social media", "x.com", "post",
            "viral", "thread", "mention", "sentiment", "influencer",
        ]

    def _build_tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=t["name"], description=t["description"], parameters=t["parameters"])
            for t in AVAILABLE_TOOLS
        ]

    @traceable(name="twitter.reasoning")
    async def reasoning(self, request: AgentRequest, steps: list[Step]) -> str:
        messages = self._build_messages(request, steps)
        response = await self.llm.complete(messages)
        return response.content

    @traceable(name="twitter.tool_selection")
    async def tool_selection(
        self, thought: str, request: AgentRequest, steps: list[Step]
    ) -> ToolCall | None:
        messages = self._build_messages(
            request, steps, extra=f"Based on this thought: {thought}\nSelect a tool or respond."
        )
        response = await self.llm.complete(messages, tools=self._build_tool_specs())

        if response.tool_call is None:
            return None

        return ToolCall(
            tool_name=response.tool_call.name,
            parameters=response.tool_call.arguments,
        )

    @traceable(name="twitter.execute")
    async def execute(self, tool_call: ToolCall) -> str:
        start = time.perf_counter()
        try:
            if tool_call.tool_name == "search_tweets":
                params = TweetSearchParams(**tool_call.parameters)
                results = await self.adapter.search_tweets(params)
                observation = json.dumps([r.model_dump() for r in results], default=str)
            elif tool_call.tool_name == "analyze_sentiment":
                tweet_ids = tool_call.parameters.get("tweet_ids", [])
                result = await self.adapter.analyze_sentiment(tweet_ids)
                observation = result.model_dump_json()
            elif tool_call.tool_name == "get_trends":
                location = tool_call.parameters.get("location", "")
                results = await self.adapter.get_trends(location)
                observation = json.dumps([r.model_dump() for r in results], default=str)
            else:
                observation = f"Unknown tool: {tool_call.tool_name}"
        except Exception as e:
            observation = f"Tool error: {e}"
        finally:
            tool_call.latency_ms = int((time.perf_counter() - start) * 1000)

        return observation

    @traceable(name="twitter.reflect")
    async def reflect(self, steps: list[Step], request: AgentRequest) -> ReflectionResult:
        if not steps:
            return ReflectionResult(should_continue=True, reason="No steps yet")

        messages = self._build_messages(
            request,
            steps,
            extra="Do you have enough information to answer? Reply YES or NO with a reason.",
        )
        response = await self.llm.complete(messages)
        should_continue = "NO" not in response.content.upper()[:10]
        return ReflectionResult(should_continue=should_continue, reason=response.content)

    @traceable(name="twitter.final_answer")
    async def final_answer(self, steps: list[Step], request: AgentRequest) -> str:
        messages = self._build_messages(
            request,
            steps,
            extra="Synthesize a final answer for the user based on the tool results above.",
        )
        response = await self.llm.complete(messages)
        return response.content

