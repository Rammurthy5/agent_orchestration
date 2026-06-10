"""Tests for MCP Streamable HTTP transport and configuration loader."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

from adapters.base import BaseMCPAdapter, MCPError, MCPSessionError
from adapters.mcp_config import MCPConfig, MCPServerConfig, load_mcp_config, get_server_config
from adapters.stdio import BaseMCPStdioAdapter
from tools.flights import FlightResult, FlightSearchParams
from tools.stay import HotelSearchParams


def _mock_response(status_code: int, *, json_data: dict | None = None, headers: dict | None = None) -> httpx.Response:
    """Build an httpx response with an attached request for raise_for_status()."""
    return httpx.Response(
        status_code,
        json=json_data,
        headers=headers,
        request=httpx.Request("POST", "http://localhost:9000/mcp"),
    )


# --- Config Loader Tests ---


class TestMCPConfigLoader:
    def test_load_from_workspace(self, tmp_path):
        """Load config from .vscode/mcp.json."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        config_data = {
            "servers": {
                "scrapebadger": {
                    "type": "http",
                    "url": "https://mcp.scrapebadger.com/mcp",
                    "headers": {"Authorization": "Bearer test-key-123"},
                },
                "local-server": {
                    "type": "stdio",
                    "command": "node",
                    "args": ["server.js"],
                },
            }
        }
        (vscode_dir / "mcp.json").write_text(json.dumps(config_data))

        config = load_mcp_config(tmp_path)
        assert "scrapebadger" in config.servers
        assert config.servers["scrapebadger"].url == "https://mcp.scrapebadger.com/mcp"
        assert config.servers["scrapebadger"].headers["Authorization"] == "Bearer test-key-123"
        assert config.servers["scrapebadger"].type == "http"
        assert config.servers["local-server"].type == "stdio"
        assert config.servers["local-server"].command == "node"

    def test_load_toolkit_style_mcp_json(self, tmp_path, monkeypatch):
        """Load toolkit-style .mcp.json using mcpServers and env interpolation."""
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        (workspace_root / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "local-server": {
                            "command": "npx",
                            "args": ["-y", "example-server"],
                            "env": {},
                        },
                        "liteapi": {
                            "type": "http",
                            "url": "https://mcp.liteapi.travel/api/mcp",
                            "headers": {
                                "Authorization": "Bearer ${LITEAPI_API_KEY:-unset}",
                            },
                        },
                    }
                }
            )
        )

        monkeypatch.setenv("LITEAPI_API_KEY", "live-key")

        config = load_mcp_config(workspace_root)

        assert "local-server" in config.servers
        assert config.servers["local-server"].type == "stdio"
        assert config.servers["local-server"].args[-1] == "example-server"
        assert config.servers["liteapi"].headers["Authorization"] == "Bearer live-key"

    def test_missing_config_returns_empty(self, tmp_path):
        """Missing mcp.json returns empty config."""
        config = load_mcp_config(tmp_path)
        assert config.servers == {}

    def test_get_server_config(self, tmp_path):
        """get_server_config returns specific server."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        (vscode_dir / "mcp.json").write_text(json.dumps({
            "servers": {
                "test-server": {"type": "http", "url": "http://localhost:9000/mcp"}
            }
        }))

        server = get_server_config("test-server", tmp_path)
        assert server is not None
        assert server.url == "http://localhost:9000/mcp"

        missing = get_server_config("nonexistent", tmp_path)
        assert missing is None

    def test_find_workspace_root_can_use_explicit_override(self, tmp_path, monkeypatch):
        """AGENT_ORCHESTRATION_ROOT should win when cwd is unrelated."""
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir(parents=True)
        (workspace_root / ".mcp.json").write_text(json.dumps({
            "servers": {
                "twitter-mcp": {
                    "command": "npx",
                    "args": ["-y", "@enescinar/twitter-mcp"],
                    "env": {"API_KEY": "api-key"},
                }
            }
        }))

        monkeypatch.setenv("AGENT_ORCHESTRATION_ROOT", str(workspace_root))
        (tmp_path / "elsewhere").mkdir()
        monkeypatch.chdir(tmp_path / "elsewhere")

        config = get_server_config("twitter-mcp")
        assert config is not None
        assert config.command == "npx"
        assert config.env["API_KEY"] == "api-key"


class TestMCPServerConfig:
    def test_defaults(self):
        config = MCPServerConfig(name="test")
        assert config.type == "http"
        assert config.url == ""
        assert config.headers == {}
        assert config.command is None

    def test_http_server(self):
        config = MCPServerConfig(
            name="scrapebadger",
            type="http",
            url="https://mcp.scrapebadger.com/mcp",
            headers={"Authorization": "Bearer abc123"},
        )
        assert config.url == "https://mcp.scrapebadger.com/mcp"
        assert "Authorization" in config.headers


class TestTravelAdapterConfig:
    def test_flights_profile_prefers_kiwi_then_skiplagged(self):
        from adapters.travel_hacking import TravelHackingAdapter

        def fake_get_server_config(name: str, workspace_root=None):
            if name == "kiwi":
                return MCPServerConfig(
                    name="kiwi",
                    type="http",
                    url="https://mcp.kiwi.com",
                )
            if name == "skiplagged":
                return MCPServerConfig(
                    name="skiplagged",
                    type="http",
                    url="https://mcp.skiplagged.com/mcp",
                )
            return None

        with patch("adapters.travel_hacking.get_server_config", side_effect=fake_get_server_config):
            adapter = TravelHackingAdapter(profile="flights")

        assert list(adapter._transports.keys()) == ["kiwi", "skiplagged"]
        assert adapter._transports["kiwi"].transport.base_url == "https://mcp.kiwi.com"
        assert adapter._transports["skiplagged"].transport.base_url == "https://mcp.skiplagged.com/mcp"

    def test_stay_profile_prefers_trivago_then_skiplagged(self):
        from adapters.travel_hacking import TravelHackingAdapter

        def fake_get_server_config(name: str, workspace_root=None):
            if name == "trivago":
                return MCPServerConfig(
                    name="trivago",
                    type="http",
                    url="https://mcp.trivago.com/mcp",
                )
            if name == "skiplagged":
                return MCPServerConfig(
                    name="skiplagged",
                    type="http",
                    url="https://mcp.skiplagged.com/mcp",
                )
            return None

        with patch("adapters.travel_hacking.get_server_config", side_effect=fake_get_server_config):
            adapter = TravelHackingAdapter(profile="stay")

        assert list(adapter._transports.keys()) == ["trivago", "skiplagged"]
        assert adapter._transports["trivago"].transport.base_url == "https://mcp.trivago.com/mcp"
        assert adapter._transports["skiplagged"].transport.base_url == "https://mcp.skiplagged.com/mcp"

    @pytest.mark.asyncio
    async def test_search_flights_adds_booking_url_when_missing(self):
        from adapters.travel_hacking import FlightSearchResult, TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            def __init__(self):
                self.calls: list[dict[str, object]] = []

            async def list_tools(self):
                return [
                    {
                        "name": "search-flight",
                        "description": "Search flights between airports",
                    }
                ]

            async def call(self, method, params, response_model):
                assert method == "search-flight"
                payload = params.model_dump()
                self.calls.append(payload)
                assert payload["flyFrom"] == "JFK"
                assert payload["flyTo"] == "LAX"
                assert payload["departureDate"] == "10/07/2026"
                return FlightSearchResult(
                    flights=[
                        FlightResult(
                            airline="SkyAir",
                            origin="JFK",
                            destination="LAX",
                            departure_time="2026-07-10T08:00:00Z",
                            arrival_time="2026-07-10T11:00:00Z",
                            duration_minutes=360,
                            price_usd=199.0,
                            stops=0,
                        )
                    ]
                )

            async def close(self):
                return None

        transport = FakeTransport()
        adapter = TravelHackingAdapter(profile="flights")
        adapter._transports = {
            "kiwi": _TransportEntry(name="kiwi", transport=transport),
        }

        results = await adapter.search_flights(FlightSearchParams(origin="JFK", destination="LAX", departure_date="2026-07-10"))

        assert results[0].booking_url is not None
        assert "google.com/travel/flights" in results[0].booking_url
        assert transport.calls[0]["flyFrom"] == "JFK"
        assert transport.calls[0]["flyTo"] == "LAX"
        assert transport.calls[0]["departureDate"] == "10/07/2026"

    @pytest.mark.asyncio
    async def test_search_flights_uses_skiplagged_tool_shape(self):
        from adapters.travel_hacking import FlightSearchResult, TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            async def list_tools(self):
                return [
                    {
                        "name": "sk_flights_search",
                        "description": "Search flights on Skiplagged",
                    }
                ]

            async def call(self, method, params, response_model):
                assert method == "sk_flights_search"
                payload = params.model_dump()
                assert payload["origin"] == "LHR"
                assert payload["destination"] == "CDG"
                assert payload["departureDate"] == "2026-07-15"
                assert payload["limit"] == 3
                assert payload["sort"] == "price"
                return FlightSearchResult(
                    flights=[
                        FlightResult(
                            airline="SkyAir",
                            origin="LHR",
                            destination="CDG",
                            departure_time="2026-07-15T08:00:00Z",
                            arrival_time="2026-07-15T09:00:00Z",
                            duration_minutes=60,
                            price_usd=99.0,
                            stops=0,
                        )
                    ]
                )

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="flights")
        adapter._transports = {
            "skiplagged": _TransportEntry(name="skiplagged", transport=FakeTransport()),
        }

        results = await adapter.search_flights(
            FlightSearchParams(origin="LHR", destination="CDG", departure_date="2026-07-15")
        )

        assert results[0].booking_url is not None
        assert "google.com/travel/flights" in results[0].booking_url

    @pytest.mark.asyncio
    async def test_search_flights_retries_alias_when_primary_tool_is_missing(self):
        from adapters.travel_hacking import FlightSearchResult, TravelHackingAdapter, _TransportEntry

        class AliasTransport:
            def __init__(self):
                self.calls: list[str] = []

            async def list_tools(self):
                return []

            async def call(self, method, params, response_model):
                self.calls.append(method)
                assert method == "search-flight"
                return FlightSearchResult(
                    flights=[
                        FlightResult(
                            airline="SkyAir",
                            origin="JFK",
                            destination="LAX",
                            departure_time="2026-07-10T08:00:00Z",
                            arrival_time="2026-07-10T11:00:00Z",
                            duration_minutes=360,
                            price_usd=199.0,
                            stops=0,
                        )
                    ]
                )

            async def close(self):
                return None

        transport = AliasTransport()
        adapter = TravelHackingAdapter(profile="flights")
        adapter._transports = {
            "kiwi": _TransportEntry(name="kiwi", transport=transport),
        }

        results = await adapter.search_flights(
            FlightSearchParams(origin="JFK", destination="LAX", departure_date="2026-07-10")
        )

        assert transport.calls[0] == "search-flight"
        assert "search_flights" not in transport.calls
        assert results[0].booking_url is not None

    @pytest.mark.asyncio
    async def test_search_flights_skips_bad_logical_name_fallbacks(self):
        from adapters.travel_hacking import FlightSearchResult, KiwiFlightSearchResult, TravelHackingAdapter, _TransportEntry

        class AliasTransport:
            def __init__(self):
                self.calls: list[str] = []

            async def list_tools(self):
                raise RuntimeError("tools/list unavailable")

            async def call(self, method, params, response_model):
                self.calls.append(method)
                if method not in {"search-flight", "sk_flights_search"}:
                    raise AssertionError(f"unexpected method {method}")
                if response_model is KiwiFlightSearchResult:
                    return response_model.model_validate(
                        [
                            {
                                "flyFrom": "JFK",
                                "flyTo": "LAX",
                                "departure": {"local": "2026-07-10T06:00:00-04:00"},
                                "arrival": {"local": "2026-07-10T08:49:00-07:00"},
                                "durationInSeconds": 20940,
                                "price": 227,
                                "deepLink": "https://on.kiwi.com/example",
                            }
                        ]
                    )
                return FlightSearchResult(
                    flights=[
                        FlightResult(
                            airline="SkyAir",
                            origin="JFK",
                            destination="LAX",
                            departure_time="2026-07-10T08:00:00Z",
                            arrival_time="2026-07-10T11:00:00Z",
                            duration_minutes=360,
                            price_usd=199.0,
                            stops=0,
                        )
                    ]
                )

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="flights")
        adapter._transports = {
            "kiwi": _TransportEntry(name="kiwi", transport=AliasTransport()),
            "skiplagged": _TransportEntry(name="skiplagged", transport=AliasTransport()),
        }

        results = await adapter.search_flights(
            FlightSearchParams(origin="JFK", destination="LAX", departure_date="2026-07-10")
        )

        assert results

    @pytest.mark.asyncio
    async def test_search_flights_normalizes_kiwi_raw_list_response(self):
        from adapters.travel_hacking import KiwiFlightSearchResult, TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            async def list_tools(self):
                return [{"name": "search-flight", "description": "Search flights"}]

            async def call(self, method, params, response_model):
                assert method == "search-flight"
                assert response_model is KiwiFlightSearchResult
                return response_model.model_validate(
                    [
                        {
                            "flyFrom": "JFK",
                            "flyTo": "LAX",
                            "departure": {"local": "2026-07-10T06:00:00-04:00"},
                            "arrival": {"local": "2026-07-10T08:49:00-07:00"},
                            "durationInSeconds": 20940,
                            "price": 227,
                            "deepLink": "https://on.kiwi.com/example",
                        }
                    ]
                )

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="flights")
        adapter._transports = {
            "kiwi": _TransportEntry(name="kiwi", transport=FakeTransport()),
        }

        results = await adapter.search_flights(
            FlightSearchParams(origin="JFK", destination="LAX", departure_date="2026-07-10")
        )

        assert len(results) == 1
        assert results[0].origin == "JFK"
        assert results[0].destination == "LAX"
        assert results[0].price_usd == 227
        assert results[0].booking_url == "https://on.kiwi.com/example"

    @pytest.mark.asyncio
    async def test_search_flights_parses_markdown_text_results(self):
        from adapters.travel_hacking import FlightSearchResult, TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            async def list_tools(self):
                return [{"name": "sk_flights_search", "description": "Search flights"}]

            async def call(self, method, params, response_model):
                assert method == "sk_flights_search"
                return response_model.model_validate(
                    {
                        "text": (
                            "# Flight search results (JFK → LAX)\n\n"
                            "| Price | Duration | Stops | Type | Airlines | Segments | Booking |\n"
                            "| --- | --- | --- | --- | --- | --- | --- |\n"
                            "| $179 | 5h 55m | Nonstop | — | Delta Air Lines | "
                            "Outbound:<br/>JFK → LAX (2026-07-10 07:00:00-04:00 → 2026-07-10 09:55:00-07:00) | "
                            "[Book](https://skiplagged.com/flights/JFK/LAX/2026-07-10#trip=DL742) |\n"
                        )
                    }
                )

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="flights")
        adapter._transports = {
            "skiplagged": _TransportEntry(name="skiplagged", transport=FakeTransport()),
        }

        results = await adapter.search_flights(
            FlightSearchParams(origin="JFK", destination="LAX", departure_date="2026-07-10")
        )

        assert len(results) == 1
        assert results[0].airline == "Delta Air Lines"
        assert results[0].price_usd == 179
        assert results[0].duration_minutes == 355
        assert results[0].booking_url == "https://skiplagged.com/flights/JFK/LAX/2026-07-10#trip=DL742"

    @pytest.mark.asyncio
    async def test_search_hotels_resolves_generic_remote_tool_name(self):
        from adapters.travel_hacking import HotelSearchResult, TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            async def list_tools(self):
                return [
                    {
                        "name": "search",
                        "description": "Find hotel rooms and accommodations",
                    }
                ]

            async def call(self, method, params, response_model):
                assert method == "search"
                return HotelSearchResult(
                    hotels=[
                        {
                            "hotel_id": "h1",
                            "name": "Hotel One",
                            "location": "Munich",
                            "price_per_night_usd": 250,
                            "rating": 4.5,
                        }
                    ]
                )

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="stay")
        adapter._transports = {
            "trivago": _TransportEntry(name="trivago", transport=FakeTransport()),
        }

        results = await adapter.search_hotels(
            HotelSearchParams(
                location="Munich",
                check_in="2026-06-12",
                check_out="2026-06-13",
                guests=2,
            )
        )

        assert len(results) == 1
        assert results[0].name == "Hotel One"
        assert results[0].booking_url is None

    @pytest.mark.asyncio
    async def test_search_hotels_retries_parameter_variants_when_primary_shape_is_invalid(self):
        from adapters.travel_hacking import HotelSearchResult, TravelHackingAdapter, _TransportEntry

        class ShapeAwareTransport:
            def __init__(self):
                self.calls: list[dict[str, object]] = []

            async def list_tools(self):
                return [{"name": "search", "description": "Find hotels"}]

            async def call(self, method, params, response_model):
                assert method == "search"
                payload = params.model_dump()
                self.calls.append(payload)
                if "destination" not in payload:
                    raise RuntimeError("MCP error -32602: Invalid arguments for tool search")
                return HotelSearchResult(
                    hotels=[
                        {
                            "hotel_id": "h1",
                            "name": "Hotel One",
                            "location": "London",
                            "price_per_night_usd": 180,
                            "rating": 4.2,
                        }
                    ]
                )

            async def close(self):
                return None

        transport = ShapeAwareTransport()
        adapter = TravelHackingAdapter(profile="stay")
        adapter._transports = {
            "trivago": _TransportEntry(name="trivago", transport=transport),
        }

        results = await adapter.search_hotels(
            HotelSearchParams(
                location="London",
                check_in="2026-06-10",
                check_out="2026-06-12",
                guests=2,
            )
        )

        assert len(transport.calls) >= 2
        assert any("destination" in call for call in transport.calls)
        assert results[0].name == "Hotel One"

    @pytest.mark.asyncio
    async def test_search_hotels_retries_alias_when_primary_tool_is_missing(self):
        from adapters.travel_hacking import HotelSearchResult, TravelHackingAdapter, _TransportEntry

        class AliasTransport:
            def __init__(self):
                self.calls: list[str] = []

            async def list_tools(self):
                return []

            async def call(self, method, params, response_model):
                self.calls.append(method)
                assert method == "hotel_search"
                return HotelSearchResult(
                    hotels=[
                        {
                            "hotel_id": "h1",
                            "name": "Hotel One",
                            "location": "London",
                            "price_per_night_usd": 180,
                            "rating": 4.2,
                        }
                    ]
                )

            async def close(self):
                return None

        transport = AliasTransport()
        adapter = TravelHackingAdapter(profile="stay")
        adapter._transports = {
            "trivago": _TransportEntry(name="trivago", transport=transport),
        }

        results = await adapter.search_hotels(
            HotelSearchParams(
                location="London",
                check_in="2026-06-10",
                check_out="2026-06-12",
                guests=2,
            )
        )

        assert transport.calls[0] == "hotel_search"
        assert "search_hotels" not in transport.calls
        assert results[0].name == "Hotel One"

    @pytest.mark.asyncio
    async def test_search_hotels_uses_skiplagged_destination_shape(self):
        from adapters.travel_hacking import HotelSearchResult, TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            async def list_tools(self):
                return [{"name": "sk_hotels_search", "description": "Find hotel rooms"}]

            async def call(self, method, params, response_model):
                assert method == "sk_hotels_search"
                payload = params.model_dump()
                assert payload["city"] == "Munich"
                assert payload["checkin"] == "2026-06-12"
                assert payload["checkout"] == "2026-06-13"
                assert payload["numAdults"] == 2
                assert payload["numRooms"] == 1
                return HotelSearchResult(
                    hotels=[
                        {
                            "hotel_id": "h1",
                            "name": "Hotel One",
                            "location": "Munich",
                            "price_per_night_usd": 250,
                            "rating": 4.5,
                        }
                    ]
                )

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="stay")
        adapter._transports = {
            "skiplagged": _TransportEntry(name="skiplagged", transport=FakeTransport()),
        }

        results = await adapter.search_hotels(
            HotelSearchParams(
                location="Munich",
                check_in="2026-06-12",
                check_out="2026-06-13",
                guests=2,
            )
        )

        assert len(results) == 1
        assert results[0].name == "Hotel One"

    @pytest.mark.asyncio
    async def test_search_hotels_uses_trivago_suggestions_and_accommodation_search(self):
        from adapters.travel_hacking import TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            def __init__(self):
                self.calls: list[tuple[str, dict[str, object]]] = []

            async def list_tools(self):
                return [
                    {"name": "trivago-search-suggestions", "description": "Find place suggestions"},
                    {"name": "trivago-accommodation-search", "description": "Search accommodations"},
                ]

            async def call(self, method, params, response_model):
                payload = params.model_dump()
                self.calls.append((method, payload))

                if method == "trivago-search-suggestions":
                    return response_model.model_validate(
                        {
                            "suggestions": [
                                {
                                    "id": 123,
                                    "ns": 77,
                                    "location": "Munich",
                                    "location_label": "Munich, Bavaria, Germany",
                                }
                            ]
                        }
                    )

                assert method == "trivago-accommodation-search"
                assert payload["id"] == 123
                assert payload["ns"] == 77
                assert payload["arrival"] == "2026-06-12"
                assert payload["departure"] == "2026-06-13"
                assert payload["adults"] == 2
                return response_model.model_validate(
                    {
                        "accommodations": [
                            {
                                "id": "h1",
                                "name": "Hotel One",
                                "location": "Munich",
                                "price": 250,
                                "rating": 4.5,
                                "amenities": ["wifi"],
                                "bookingLink": "https://example.com/hotel-one",
                            }
                        ]
                    }
                )

            async def close(self):
                return None

        transport = FakeTransport()
        adapter = TravelHackingAdapter(profile="stay")
        adapter._transports = {
            "trivago": _TransportEntry(name="trivago", transport=transport),
        }

        results = await adapter.search_hotels(
            HotelSearchParams(
                location="Munich",
                check_in="2026-06-12",
                check_out="2026-06-13",
                guests=2,
            )
        )

        assert [call[0] for call in transport.calls] == [
            "trivago-search-suggestions",
            "trivago-accommodation-search",
        ]
        assert len(results) == 1
        assert results[0].name == "Hotel One"
        assert results[0].booking_url == "https://example.com/hotel-one"

    @pytest.mark.asyncio
    async def test_search_hotels_parses_markdown_text_results(self):
        from adapters.travel_hacking import HotelSearchResult, TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            async def list_tools(self):
                return [{"name": "sk_hotels_search", "description": "Find hotel rooms"}]

            async def call(self, method, params, response_model):
                assert method == "sk_hotels_search"
                return response_model.model_validate(
                    HotelSearchResult(
                        text=(
                            "# Hotels in Munich\n\n"
                            "| Hotel | Rating | Price/night | Total | Amenities | Booking |\n"
                            "| --- | --- | --- | --- | --- | --- |\n"
                            "| **Hotel One**<br/>Munich | 4★ · 8.6/10 | $145 | $184 | Free internet, Breakfast | "
                            "[View deal](https://skiplagged.com/hotel/43249/hotel-one/2026-06-12/2026-06-13) |\n"
                        )
                    ).model_dump()
                )

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="stay")
        adapter._transports = {
            "skiplagged": _TransportEntry(name="skiplagged", transport=FakeTransport()),
        }

        results = await adapter.search_hotels(
            HotelSearchParams(
                location="Munich",
                check_in="2026-06-12",
                check_out="2026-06-13",
                guests=2,
            )
        )

        assert len(results) == 1
        assert results[0].hotel_id == "43249"
        assert results[0].name == "Hotel One"
        assert results[0].price_per_night_usd == 145
        assert results[0].amenities == ["Free internet", "Breakfast"]
        assert results[0].booking_url == "https://skiplagged.com/hotel/43249/hotel-one/2026-06-12/2026-06-13"

    @pytest.mark.asyncio
    async def test_search_hotels_uses_trivago_city_and_lowercase_dates(self):
        from adapters.travel_hacking import HotelSearchResult, TravelHackingAdapter, _TransportEntry

        class FakeTransport:
            async def list_tools(self):
                return [{"name": "hotel_search", "description": "Search hotels on Trivago"}]

            async def call(self, method, params, response_model):
                assert method == "hotel_search"
                payload = params.model_dump()
                assert payload["city"] == "Munich"
                assert payload["checkin"] == "2026-06-12"
                assert payload["checkout"] == "2026-06-13"
                assert payload["adults"] == 2
                assert payload["maxPricePerNight"] == 500
                return HotelSearchResult(
                    hotels=[
                        {
                            "hotel_id": "h1",
                            "name": "Hotel One",
                            "location": "Munich",
                            "price_per_night_usd": 250,
                            "rating": 4.5,
                        }
                    ]
                )

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="stay")
        adapter._transports = {
            "trivago": _TransportEntry(name="trivago", transport=FakeTransport()),
        }

        results = await adapter.search_hotels(
            HotelSearchParams(
                location="Munich",
                check_in="2026-06-12",
                check_out="2026-06-13",
                guests=2,
                max_price_per_night=500,
            )
        )

        assert len(results) == 1
        assert results[0].name == "Hotel One"

    @pytest.mark.asyncio
    async def test_search_flights_reports_all_backend_failures(self):
        from adapters.travel_hacking import TravelHackingAdapter, _TransportEntry

        class FailingTransport:
            def __init__(self, label: str):
                self.label = label

            async def call(self, method, params, response_model):
                raise RuntimeError(f"{self.label} unreachable")

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="flights")
        adapter._transports = {
            "kiwi": _TransportEntry(name="kiwi", transport=FailingTransport("kiwi")),
            "skiplagged": _TransportEntry(name="skiplagged", transport=FailingTransport("skiplagged")),
        }

        with pytest.raises(RuntimeError) as exc:
            await adapter.search_flights(
                FlightSearchParams(origin="JFK", destination="LAX", departure_date="2026-07-10")
            )

        message = str(exc.value)
        assert "kiwi: kiwi unreachable" in message
        assert "skiplagged: skiplagged unreachable" in message

    @pytest.mark.asyncio
    async def test_search_hotels_reports_all_backend_failures(self):
        from adapters.travel_hacking import TravelHackingAdapter, _TransportEntry

        class FailingTransport:
            def __init__(self, label: str):
                self.label = label

            async def call(self, method, params, response_model):
                raise RuntimeError(f"{self.label} unreachable")

            async def close(self):
                return None

        adapter = TravelHackingAdapter(profile="stay")
        adapter._transports = {
            "trivago": _TransportEntry(name="trivago", transport=FailingTransport("trivago")),
            "skiplagged": _TransportEntry(name="skiplagged", transport=FailingTransport("skiplagged")),
        }

        with pytest.raises(RuntimeError) as exc:
            await adapter.search_hotels(
                HotelSearchParams(
                    location="Munich",
                    check_in="2026-06-12",
                    check_out="2026-06-13",
                    guests=2,
                )
            )

        message = str(exc.value)
        assert "trivago: trivago unreachable" in message
        assert "skiplagged: skiplagged unreachable" in message


# --- Streamable HTTP Transport Tests ---


class TestStreamableHTTPTransport:
    @pytest.fixture
    def adapter(self):
        return BaseMCPAdapter(base_url="http://localhost:9000/mcp", auth_token="test-token")

    def test_init(self, adapter):
        assert adapter.base_url == "http://localhost:9000/mcp"
        assert adapter._auth_token == "test-token"
        assert adapter._session_id is None
        assert adapter._initialized is False

    def test_build_headers_no_session(self, adapter):
        headers = adapter._build_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert "Mcp-Session-Id" not in headers

    def test_build_headers_with_session(self, adapter):
        adapter._session_id = "session-abc"
        headers = adapter._build_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Mcp-Session-Id"] == "session-abc"

    def test_next_id_increments(self, adapter):
        assert adapter._next_id() == 1
        assert adapter._next_id() == 2
        assert adapter._next_id() == 3

    def test_parse_sse_response_simple(self, adapter):
        """Parse a simple SSE stream with one message event."""
        sse_body = (
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"hello"}]}}\n'
            "\n"
        )
        result = adapter._parse_sse_response(sse_body, request_id=1)
        assert result["id"] == 1
        assert "result" in result

    def test_parse_sse_response_multiple_events(self, adapter):
        """Parse SSE with multiple events, find the right one by ID."""
        sse_body = (
            "event: progress\n"
            'data: {"progress": 50}\n'
            "\n"
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n'
            "\n"
        )
        result = adapter._parse_sse_response(sse_body, request_id=2)
        assert result["id"] == 2

    def test_parse_sse_response_not_found(self, adapter):
        """Raise MCPError when no matching response found."""
        sse_body = "event: heartbeat\ndata: {}\n\n"
        with pytest.raises(MCPError):
            adapter._parse_sse_response(sse_body, request_id=99)

    async def test_ensure_initialized_calls_handshake(self, adapter):
        """Verify initialize handshake is called on first use."""
        mock_response = _mock_response(
            200,
            json_data={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test-server", "version": "1.0"},
                },
            },
            headers={"mcp-session-id": "sess-123"},
        )
        notification_response = _mock_response(202)

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_response
            return notification_response

        adapter._client = AsyncMock()
        adapter._client.post = mock_post

        await adapter.ensure_initialized()
        assert adapter._initialized is True
        assert adapter._session_id == "sess-123"

    async def test_ensure_initialized_only_once(self, adapter):
        """Initialize handshake should only happen once."""
        adapter._initialized = True
        adapter._client = AsyncMock()
        await adapter.ensure_initialized()
        adapter._client.post.assert_not_called()

    async def test_call_tool_success(self, adapter):
        """Verify tools/call returns parsed content."""
        adapter._initialized = True

        mock_response = _mock_response(
            200,
            json_data={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [
                        {"type": "text", "text": '{"products": [{"name": "Laptop", "price": 999}]}'}
                    ]
                },
            },
        )

        async def mock_post(*args, **kwargs):
            return mock_response

        adapter._client = AsyncMock()
        adapter._client.post = mock_post

        class Params(BaseModel):
            query: str

        class Result(BaseModel):
            products: list[dict]

        result = await adapter.call("search_products", Params(query="laptop"), Result)
        assert len(result.products) == 1
        assert result.products[0]["name"] == "Laptop"

    async def test_call_tool_error_response(self, adapter):
        """Verify error response raises MCPError."""
        adapter._initialized = True

        mock_response = _mock_response(
            200,
            json_data={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "Method not found"},
            },
        )

        async def mock_post(*args, **kwargs):
            return mock_response

        adapter._client = AsyncMock()
        adapter._client.post = mock_post

        class Params(BaseModel):
            query: str

        class Result(BaseModel):
            data: str

        with pytest.raises(MCPError, match="Method not found"):
            await adapter.call("unknown_method", Params(query="test"), Result)

    async def test_call_retries_on_connection_error(self, adapter):
        """Verify retry logic on transient failures."""
        adapter._initialized = True
        adapter._sleep = AsyncMock()

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("Connection refused")
            return _mock_response(
                200,
                json_data={
                    "jsonrpc": "2.0",
                    "id": call_count,
                    "result": {"content": [{"type": "text", "text": '{"status": "ok"}'}]},
                },
            )

        adapter._client = AsyncMock()
        adapter._client.post = mock_post

        class Params(BaseModel):
            pass

        class Result(BaseModel):
            status: str

        result = await adapter.call("test_method", Params(), Result)
        assert result.status == "ok"
        assert call_count == 3

    async def test_list_tools(self, adapter):
        """Verify tools/list returns tool definitions."""
        adapter._initialized = True

        mock_response = _mock_response(
            200,
            json_data={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "tools": [
                        {"name": "search_products", "description": "Search for products"},
                        {"name": "compare_prices", "description": "Compare prices"},
                    ]
                },
            },
        )

        async def mock_post(*args, **kwargs):
            return mock_response

        adapter._client = AsyncMock()
        adapter._client.post = mock_post

        tools = await adapter.list_tools()
        assert len(tools) == 2
        assert tools[0]["name"] == "search_products"


# --- ScrapeBadger Adapter Integration ---


class TestScrapeBadgerConfigLoading:
    def test_loads_from_mcp_json(self, tmp_path):
        """ScrapeBadger adapter picks up config from mcp.json."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        (vscode_dir / "mcp.json").write_text(json.dumps({
            "servers": {
                "scrapebadger": {
                    "type": "http",
                    "url": "https://mcp.scrapebadger.com/mcp",
                    "headers": {"Authorization": "Bearer sb_live_test123"},
                }
            }
        }))

        with patch("adapters.scrape_badger.get_server_config") as mock_config:
            mock_config.return_value = MCPServerConfig(
                name="scrapebadger",
                type="http",
                url="https://mcp.scrapebadger.com/mcp",
                headers={"Authorization": "Bearer sb_live_test123"},
            )
            from adapters.scrape_badger import ScrapeBadgerAdapter

            adapter = ScrapeBadgerAdapter()
            assert adapter.base_url == "https://mcp.scrapebadger.com/mcp"
            assert adapter._auth_token == "sb_live_test123"

    def test_falls_back_to_env(self, monkeypatch):
        """Falls back to env vars when mcp.json not found."""
        monkeypatch.setenv("SCRAPE_BADGER_MCP_URL", "http://custom:9000/mcp")
        monkeypatch.setenv("SCRAPE_BADGER_API_KEY", "env-key")

        with patch("adapters.scrape_badger.get_server_config", return_value=None):
            from adapters.scrape_badger import ScrapeBadgerAdapter

            adapter = ScrapeBadgerAdapter()
            assert adapter.base_url == "http://custom:9000/mcp"
            assert adapter._auth_token == "env-key"


class TestTwitterMCPConfigLoading:
    def test_loads_stdio_server_from_workspace(self, tmp_path):
        """Twitter adapter should prefer the twitter-mcp stdio server in mcp.json."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        (vscode_dir / "mcp.json").write_text(json.dumps({
            "servers": {
                "twitter-mcp": {
                    "command": "npx",
                    "args": ["-y", "@enescinar/twitter-mcp"],
                    "env": {
                        "API_KEY": "api-key",
                        "API_SECRET_KEY": "api-secret",
                        "ACCESS_TOKEN": "access-token",
                        "ACCESS_TOKEN_SECRET": "access-secret",
                    },
                }
            }
        }))

        config = get_server_config("twitter-mcp", tmp_path)
        assert config is not None
        assert config.type == "stdio"
        assert config.command == "npx"
        assert config.args == ["-y", "@enescinar/twitter-mcp"]

    def test_twitter_adapter_uses_stdio_transport(self):
        """TwitterMCPAdapter should initialize from the twitter-mcp stdio config."""
        from adapters.twitter_mcp import TwitterMCPAdapter

        with patch("adapters.twitter_mcp.get_server_config") as mock_config:
            mock_config.side_effect = lambda name, workspace_root=None: (
                MCPServerConfig(
                    name="twitter-mcp",
                    type="stdio",
                    command="npx",
                    args=["-y", "@enescinar/twitter-mcp"],
                    env={
                        "API_KEY": "api-key",
                        "API_SECRET_KEY": "api-secret",
                        "ACCESS_TOKEN": "access-token",
                        "ACCESS_TOKEN_SECRET": "access-secret",
                    },
                )
                if name == "twitter-mcp"
                else None
            )

            adapter = TwitterMCPAdapter()

            assert mock_config.call_args_list[0].args[0] == "twitter-mcp"
            assert isinstance(adapter._transport, BaseMCPStdioAdapter)
            assert adapter._transport.command == "npx"
            assert adapter._transport.args == ["-y", "@enescinar/twitter-mcp"]
            assert adapter._transport.env["API_KEY"] == "api-key"

    def test_stdio_frame_round_trip(self):
        """Frame encoding and parsing should round-trip JSON-RPC payloads."""
        payload = {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}
        frame = BaseMCPStdioAdapter.encode_frame(payload)
        adapter = BaseMCPStdioAdapter(command="npx")
        adapter._read_buffer = bytearray(frame)

        parsed = adapter._try_parse_message()
        assert parsed == payload
        assert adapter._read_buffer == bytearray()
