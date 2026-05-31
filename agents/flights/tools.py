"""Flights agent tool declarations."""

from agents.base.types import ToolCall

AVAILABLE_TOOLS = [
    {
        "name": "search_flights",
        "description": "Search for flights between two airports on given dates",
        "parameters": {
            "origin": "IATA airport code (e.g. JFK)",
            "destination": "IATA airport code (e.g. NRT)",
            "departure_date": "ISO date string",
            "return_date": "ISO date string (optional)",
        },
    },
    {
        "name": "compare_routes",
        "description": "Compare multiple route options by cost and duration",
        "parameters": {
            "routes": "List of route IDs to compare",
        },
    },
]


def get_tool_names() -> list[str]:
    """Return names of all available flight tools."""
    return [t["name"] for t in AVAILABLE_TOOLS]
