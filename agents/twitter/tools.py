"""Twitter agent tool declarations."""

AVAILABLE_TOOLS = [
    {
        "name": "search_tweets",
        "description": "Search for tweets matching a query or hashtag",
        "parameters": {
            "query": "Search query or hashtag",
            "limit": "Maximum number of tweets to return",
        },
    },
    {
        "name": "analyze_sentiment",
        "description": "Analyze sentiment of a collection of tweets",
        "parameters": {
            "tweet_ids": "List of tweet IDs to analyze",
        },
    },
    {
        "name": "get_trends",
        "description": "Get current trending topics for a location",
        "parameters": {
            "location": "Location name or WOEID",
        },
    },
]


def get_tool_names() -> list[str]:
    """Return names of all available twitter tools."""
    return [t["name"] for t in AVAILABLE_TOOLS]
