"""Stay agent tool declarations."""

AVAILABLE_TOOLS = [
    {
        "name": "search_hotels",
        "description": "Search for hotels in a location with date and guest filters",
        "parameters": {
            "location": "City or area name",
            "check_in": "ISO date string",
            "check_out": "ISO date string",
            "guests": "Number of guests",
            "max_price_per_night": "Budget cap per night (optional)",
        },
    },
    {
        "name": "check_availability",
        "description": "Check real-time availability for a specific hotel",
        "parameters": {
            "hotel_id": "Hotel identifier",
            "check_in": "ISO date string",
            "check_out": "ISO date string",
        },
    },
]


def get_tool_names() -> list[str]:
    """Return names of all available stay tools."""
    return [t["name"] for t in AVAILABLE_TOOLS]
