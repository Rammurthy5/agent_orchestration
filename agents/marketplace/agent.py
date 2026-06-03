"""Marketplace agent — product search, price comparison, recommendations."""

from __future__ import annotations

import json
import time

from langsmith import traceable

from adapters.scrape_badger import ScrapeBadgerAdapter
from agents.base import (
    AgentID,
    AgentRequest,
    BaseAgent,
    ReflectionResult,
    Step,
    ToolCall,
)
from agents.base.llm import LLMClient, ToolSpec
from agents.marketplace.tools import AVAILABLE_TOOLS
from tools.marketplace import ProductSearchParams


class MarketplaceAgent(BaseAgent):
    """Specialized agent for product search and price comparison."""

    agent_id = AgentID.MARKETPLACE

    def __init__(self, llm: LLMClient | None = None, adapter: ScrapeBadgerAdapter | None = None):
        super().__init__(llm=llm)
        self.adapter = adapter or ScrapeBadgerAdapter()

    def _domain_keywords(self) -> list[str]:
        return [
            "buy", "price", "product", "shop", "marketplace",
            "deal", "discount", "order", "cart", "purchase",
            "compare", "listing", "seller", "retail", "store",
        ]

    def _build_tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=t["name"], description=t["description"], parameters=t["parameters"])
            for t in AVAILABLE_TOOLS
        ]

    @traceable(name="marketplace.reasoning")
    async def reasoning(self, request: AgentRequest, steps: list[Step]) -> str:
        messages = self._build_messages(request, steps)
        response = await self.llm.complete(messages)
        return response.content

    @traceable(name="marketplace.tool_selection")
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

    @traceable(name="marketplace.execute")
    async def execute(self, tool_call: ToolCall) -> str:
        start = time.perf_counter()
        try:
            if tool_call.tool_name == "search_products":
                params = ProductSearchParams(**tool_call.parameters)
                results = await self.adapter.search_products(params)
                observation = json.dumps([r.model_dump() for r in results], default=str)
            elif tool_call.tool_name == "compare_prices":
                product_id = tool_call.parameters.get("product_id", "")
                result = await self.adapter.compare_prices(product_id)
                observation = result.model_dump_json()
            else:
                observation = f"Unknown tool: {tool_call.tool_name}"
        except Exception as e:
            observation = f"Tool error: {e}"
        finally:
            tool_call.latency_ms = int((time.perf_counter() - start) * 1000)

        return observation

    @traceable(name="marketplace.reflect")
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

    @traceable(name="marketplace.final_answer")
    async def final_answer(self, steps: list[Step], request: AgentRequest) -> str:
        messages = self._build_messages(
            request,
            steps,
            extra="Synthesize a final answer for the user based on the tool results above.",
        )
        response = await self.llm.complete(messages)
        return response.content

