"""Routing evaluation tests — validate intent → agent classification.

Tests the Python-side routing dataset and validates classification logic.
Integration tests call the Go router via gRPC.
"""

from __future__ import annotations

import pytest

from agents.base.types import AgentID
from evals.golden_cases import ROUTING_CASES, SCOPE_REJECTION_CASES
from evals.runner import EvalCase, EvalSuite


# --- Keyword-based router (mirrors Go router logic for Python-side testing) ---

_ROUTE_KEYWORDS: dict[AgentID, set[str]] = {
    AgentID.FLIGHTS: {
        "flight", "flights", "fly", "airline", "airfare", "airport",
        "departure", "arrival", "nonstop", "layover", "booking",
    },
    AgentID.STAY: {
        "hotel", "hotels", "hostel", "accommodation", "resort", "stay",
        "room", "airbnb", "lodge", "motel", "inn",
    },
    AgentID.MARKETPLACE: {
        "buy", "price", "deal", "product", "shop", "compare",
        "laptop", "phone", "headphones", "purchase", "cost",
        "shoes", "ps5", "size", "brand", "review", "find",
        "cheap", "order", "retail", "store", "discount", "coupon",
    },
    AgentID.TWITTER: {
        "twitter", "tweet", "hashtag", "trending", "sentiment",
        "retweet", "social", "viral", "saying", "retweeted",
    },
}


def keyword_route(query: str) -> AgentID | None:
    """Route a query to an agent using keyword matching. Falls back to marketplace."""
    query_lower = query.lower()
    scores: dict[AgentID, int] = {}
    for agent_id, keywords in _ROUTE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[agent_id] = score
    if not scores:
        return AgentID.MARKETPLACE  # Fallback
    return max(scores, key=scores.get)


# --- Tests ---


@pytest.mark.parametrize("query,expected_agent", ROUTING_CASES)
def test_routing_classification(query: str, expected_agent: AgentID) -> None:
    """Verify keyword router classifies queries to the expected agent."""
    actual = keyword_route(query)
    assert actual == expected_agent, (
        f"Expected {expected_agent.value} but got {actual.value if actual else 'None'} "
        f"for query: {query!r}"
    )


@pytest.mark.parametrize("agent_id", list(AgentID))
def test_scope_rejection_not_routed(agent_id: AgentID) -> None:
    """Verify out-of-scope queries are NOT routed to the target agent.

    Note: marketplace is the fallback, so skip its rejection cases since
    unmatched queries are intentionally routed there.
    """
    if agent_id == AgentID.MARKETPLACE:
        pytest.skip("marketplace is the fallback agent for unmatched queries")
    rejection_queries = SCOPE_REJECTION_CASES.get(agent_id, [])
    for query in rejection_queries:
        routed = keyword_route(query)
        assert routed != agent_id, (
            f"Query {query!r} was incorrectly routed to {agent_id.value}"
        )


def test_all_agents_have_routing_cases() -> None:
    """Verify golden cases cover all agents."""
    covered_agents = {agent for _, agent in ROUTING_CASES}
    for agent_id in AgentID:
        assert agent_id in covered_agents, f"No routing cases for {agent_id.value}"


async def test_routing_eval_suite() -> None:
    """Run routing evals through the EvalSuite runner."""
    suite = EvalSuite(eval_type="routing", agent_id="router")

    for query, expected_agent in ROUTING_CASES:
        suite.add_case(input=query, expected=expected_agent.value)

    async def scorer(eval_case: EvalCase) -> tuple[str, float, dict]:
        actual = keyword_route(eval_case.input)
        actual_str = actual.value if actual else "none"
        score = 1.0 if actual_str == eval_case.expected else 0.0
        return actual_str, score, {}

    results = await suite.run(scorer, threshold=0.7)
    assert suite.pass_rate >= 0.9, f"Routing pass rate: {suite.pass_rate:.2f}"
    assert suite.average_score >= 0.9
