"""Twitter agent — social trend analysis, tweet generation, sentiment extraction."""

from agents.base import (
    AgentID,
    AgentRequest,
    BaseAgent,
    ReflectionResult,
    Step,
    ToolCall,
)


class TwitterAgent(BaseAgent):
    """Specialized agent for social media analysis and content generation."""

    agent_id = AgentID.TWITTER

    def _domain_keywords(self) -> list[str]:
        return [
            "twitter", "tweet", "hashtag", "trending", "retweet",
            "follower", "timeline", "social media", "x.com", "post",
            "viral", "thread", "mention", "sentiment", "influencer",
        ]

    async def reasoning(self, request: AgentRequest, steps: list[Step]) -> str:
        raise NotImplementedError

    async def tool_selection(
        self, thought: str, request: AgentRequest, steps: list[Step]
    ) -> ToolCall | None:
        raise NotImplementedError

    async def execute(self, tool_call: ToolCall) -> str:
        raise NotImplementedError

    async def reflect(self, steps: list[Step], request: AgentRequest) -> ReflectionResult:
        raise NotImplementedError

    async def final_answer(self, steps: list[Step], request: AgentRequest) -> str:
        raise NotImplementedError
