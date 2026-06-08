"""Twitter agent tool declarations."""

AVAILABLE_TOOLS = [
    {
        "name": "search_tweets",
        "description": "Search for tweets matching a query or hashtag",
        "parameters": {
            "query": "Search query or hashtag",
            "count": "Number of tweets to return (10-100)",
        },
    },
    {
        "name": "analyze_sentiment",
        "description": "Analyze sentiment for a topic using recent tweets",
        "parameters": {
            "topic": "Topic or query to analyze",
        },
    },
    {
        "name": "get_trends",
        "description": "Infer current trending topics for a topic or search query",
        "parameters": {
            "topic": "Topic or query to summarize",
        },
    },
]


def get_tool_names() -> list[str]:
    """Return names of all available twitter tools."""
    return [t["name"] for t in AVAILABLE_TOOLS]
