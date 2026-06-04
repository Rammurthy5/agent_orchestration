"""Golden test cases for evaluation pipelines.

Contains curated input/expected-output pairs for all eval categories.
These serve as the ground truth for regression and quality tracking.
"""

from __future__ import annotations

from agents.base.types import AgentID


# --- Hallucination / Grounding Cases ---

GROUNDING_CASES = [
    {
        "id": "grounding_001",
        "agent_id": AgentID.FLIGHTS,
        "query": "Flights from SFO to NRT",
        "tool_output": "United UA837 $450 nonstop, Delta DL275 $520 1-stop",
        "agent_answer": "The cheapest flight is United UA837 at $450, nonstop.",
        "expected_grounded": True,
    },
    {
        "id": "grounding_002",
        "agent_id": AgentID.FLIGHTS,
        "query": "Flights from SFO to NRT",
        "tool_output": "United UA837 $450 nonstop, Delta DL275 $520 1-stop",
        "agent_answer": "Spirit Airlines offers $200 flights from SFO to NRT.",
        "expected_grounded": False,
    },
    {
        "id": "grounding_003",
        "agent_id": AgentID.MARKETPLACE,
        "query": "Find laptops under $1000",
        "tool_output": "MacBook Air M2 $999, ThinkPad T14 $879, Dell XPS 13 $949",
        "agent_answer": "The ThinkPad T14 at $879 is the cheapest option.",
        "expected_grounded": True,
    },
    {
        "id": "grounding_004",
        "agent_id": AgentID.MARKETPLACE,
        "query": "Find laptops under $1000",
        "tool_output": "MacBook Air M2 $999, ThinkPad T14 $879, Dell XPS 13 $949",
        "agent_answer": "The HP Spectre at $750 is the best deal available.",
        "expected_grounded": False,
    },
    {
        "id": "grounding_005",
        "agent_id": AgentID.STAY,
        "query": "Hotels in Tokyo for 2 nights",
        "tool_output": "Park Hyatt $450/night, Shinjuku Granbell $120/night, APA Hotel $80/night",
        "agent_answer": "Budget option: APA Hotel at $80/night. Mid-range: Shinjuku Granbell at $120/night.",
        "expected_grounded": True,
    },
    {
        "id": "grounding_006",
        "agent_id": AgentID.STAY,
        "query": "Hotels in Tokyo for 2 nights",
        "tool_output": "Park Hyatt $450/night, Shinjuku Granbell $120/night, APA Hotel $80/night",
        "agent_answer": "I found Ritz-Carlton Tokyo at $300/night with complimentary breakfast.",
        "expected_grounded": False,
    },
    {
        "id": "grounding_007",
        "agent_id": AgentID.TWITTER,
        "query": "Trending topics in AI",
        "tool_output": "Trending: #GPT5, #OpenAI, #AIRegulation (10K tweets each)",
        "agent_answer": "Top trending AI topics: #GPT5, #OpenAI, and #AIRegulation.",
        "expected_grounded": True,
    },
    {
        "id": "grounding_008",
        "agent_id": AgentID.TWITTER,
        "query": "Trending topics in AI",
        "tool_output": "Trending: #GPT5, #OpenAI, #AIRegulation (10K tweets each)",
        "agent_answer": "#GoogleGemini is the top trending topic with 50K tweets.",
        "expected_grounded": False,
    },
]

# --- Tool Selection Cases ---

TOOL_SELECTION_CASES = [
    {
        "id": "tool_001",
        "agent_id": AgentID.FLIGHTS,
        "query": "Find flights from NYC to London on July 10",
        "expected_tool": "search_flights",
        "expected_params": {"origin": "NYC", "destination": "London", "date": "2026-07-10"},
    },
    {
        "id": "tool_002",
        "agent_id": AgentID.FLIGHTS,
        "query": "Compare routes from LAX to Tokyo",
        "expected_tool": "compare_routes",
        "expected_params": {"origin": "LAX", "destination": "Tokyo"},
    },
    {
        "id": "tool_003",
        "agent_id": AgentID.STAY,
        "query": "Hotels in Barcelona for 3 guests, July 15-18",
        "expected_tool": "search_hotels",
        "expected_params": {"location": "Barcelona", "guests": 3},
    },
    {
        "id": "tool_004",
        "agent_id": AgentID.STAY,
        "query": "Is the Park Hyatt available on August 1?",
        "expected_tool": "check_availability",
        "expected_params": {"hotel": "Park Hyatt", "date": "2026-08-01"},
    },
    {
        "id": "tool_005",
        "agent_id": AgentID.MARKETPLACE,
        "query": "Search for noise-canceling headphones under $300",
        "expected_tool": "search_products",
        "expected_params": {"query": "noise-canceling headphones", "max_price": 300},
    },
    {
        "id": "tool_006",
        "agent_id": AgentID.MARKETPLACE,
        "query": "Compare prices for iPhone 15 Pro",
        "expected_tool": "compare_prices",
        "expected_params": {"product": "iPhone 15 Pro"},
    },
    {
        "id": "tool_007",
        "agent_id": AgentID.TWITTER,
        "query": "What's trending in technology?",
        "expected_tool": "get_trends",
        "expected_params": {"topic": "technology"},
    },
    {
        "id": "tool_008",
        "agent_id": AgentID.TWITTER,
        "query": "Analyze sentiment of recent tweets about climate change",
        "expected_tool": "analyze_sentiment",
        "expected_params": {"topic": "climate change"},
    },
]

# --- Trajectory Cases ---

TRAJECTORY_CASES = [
    {
        "id": "traj_001",
        "agent_id": AgentID.FLIGHTS,
        "query": "Find the cheapest flight from SFO to NRT next week",
        "steps": [
            {
                "thought": "I need to search for flights from SFO to NRT for next week.",
                "action": "search_flights",
                "observation": "Found: United $450, Delta $520, ANA $480",
            },
            {
                "thought": "United at $450 is the cheapest. I have enough info to answer.",
                "action": None,
                "observation": None,
            },
        ],
        "expected_min_score": 0.8,
    },
    {
        "id": "traj_002",
        "agent_id": AgentID.MARKETPLACE,
        "query": "Find the best laptop for programming under $1500",
        "steps": [
            {
                "thought": "I should search for programming laptops in the price range.",
                "action": "search_products",
                "observation": "Found: MacBook Pro M3 $1499, ThinkPad X1 $1349, Dell XPS 15 $1299",
            },
            {
                "thought": "Multiple options found. Let me compare prices to find the best value.",
                "action": "compare_prices",
                "observation": "ThinkPad X1: best RAM/storage ratio. MacBook Pro: best performance.",
            },
            {
                "thought": "Based on the comparison, MacBook Pro M3 offers best performance for programming within budget.",
                "action": None,
                "observation": None,
            },
        ],
        "expected_min_score": 0.85,
    },
    {
        "id": "traj_003",
        "agent_id": AgentID.STAY,
        "query": "Find budget hotels in Paris near the Eiffel Tower",
        "steps": [
            {
                "thought": "I need to search for hotels in Paris with location preference near Eiffel Tower.",
                "action": "search_hotels",
                "observation": "Found: Hotel Le Petit Paris $89/night (0.5km), Ibis Eiffel $75/night (0.3km)",
            },
            {
                "thought": "Ibis Eiffel is closest and cheapest. Good budget option.",
                "action": None,
                "observation": None,
            },
        ],
        "expected_min_score": 0.8,
    },
]

# --- Routing Cases (comprehensive) ---

ROUTING_CASES = [
    # Flights
    ("Find cheapest flights to Tokyo", AgentID.FLIGHTS),
    ("Book a flight from JFK to LAX", AgentID.FLIGHTS),
    ("What airline flies direct to London?", AgentID.FLIGHTS),
    ("Round trip airfare to Barcelona", AgentID.FLIGHTS),
    ("Show me departure times from LAX to SFO", AgentID.FLIGHTS),
    # Stay
    ("Find me a hotel in Paris", AgentID.STAY),
    ("Best accommodation near the beach", AgentID.STAY),
    ("Budget hostel in Bangkok", AgentID.STAY),
    ("5-star resort in Bali for honeymoon", AgentID.STAY),
    ("Airbnb alternatives in London", AgentID.STAY),
    # Marketplace
    ("Compare prices for a laptop", AgentID.MARKETPLACE),
    ("I want to buy a new phone", AgentID.MARKETPLACE),
    ("Best deal on headphones", AgentID.MARKETPLACE),
    ("Find running shoes under $100", AgentID.MARKETPLACE),
    ("Price comparison for PS5", AgentID.MARKETPLACE),
    # Twitter
    ("Trending hashtags on Twitter", AgentID.TWITTER),
    ("Analyze sentiment of tweets about crypto", AgentID.TWITTER),
    ("Generate a tweet about sustainability", AgentID.TWITTER),
    ("What are people saying about the election?", AgentID.TWITTER),
    ("Most retweeted post this week", AgentID.TWITTER),
]

# --- Scope Rejection Cases ---

SCOPE_REJECTION_CASES = {
    AgentID.FLIGHTS: [
        "Book a hotel in Paris",
        "What's the best laptop deal?",
        "Trending hashtags today",
        "Help me cook pasta",
        "What is quantum computing?",
    ],
    AgentID.STAY: [
        "Find flights to London",
        "Compare phone prices",
        "Trending tweets today",
        "Explain machine learning",
        "Best restaurants in NYC",
    ],
    AgentID.MARKETPLACE: [
        "Find flights to Tokyo",
        "Book a hotel room",
        "Twitter trending topics",
        "What is the weather?",
        "Translate this to French",
    ],
    AgentID.TWITTER: [
        "Find flights to London",
        "Book a hotel room",
        "Find laptops under $1000",
        "What's the meaning of life?",
        "Help me with my homework",
    ],
}

# --- Latency Budgets (ms) ---

LATENCY_BUDGETS = {
    "orchestration_p95": 100,     # Go routing overhead
    "agent_total_p95": 10_000,    # Full ReAct loop
    "tool_call_p95": 5_000,       # Single MCP tool call
    "memory_search_p95": 200,     # PgVector similarity search
    "grpc_overhead_p95": 50,      # gRPC serialization
}
