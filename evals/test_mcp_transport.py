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
        vscode_dir = workspace_root / ".vscode"
        vscode_dir.mkdir(parents=True)
        (vscode_dir / "mcp.json").write_text(json.dumps({
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


class TestTravelHackingAdapterConfig:
    def test_flights_profile_prefers_skiplagged(self):
        from adapters.travel_hacking import TravelHackingAdapter

        def fake_get_server_config(name: str, workspace_root=None):
            if name == "skiplagged":
                return MCPServerConfig(
                    name="skiplagged",
                    type="http",
                    url="https://mcp.skiplagged.com/mcp",
                )
            return None

        with patch("adapters.travel_hacking.get_server_config", side_effect=fake_get_server_config):
            adapter = TravelHackingAdapter(profile="flights")

        assert "skiplagged" in adapter._transports
        assert adapter._transports["skiplagged"].transport.base_url == "https://mcp.skiplagged.com/mcp"

    def test_stay_profile_prefers_airbnb(self):
        from adapters.travel_hacking import TravelHackingAdapter

        def fake_get_server_config(name: str, workspace_root=None):
            if name == "airbnb":
                return MCPServerConfig(
                    name="airbnb",
                    type="stdio",
                    command="npx",
                    args=["-y", "@openbnb/mcp-server-airbnb"],
                )
            return None

        with patch("adapters.travel_hacking.get_server_config", side_effect=fake_get_server_config):
            adapter = TravelHackingAdapter(profile="stay")

        assert "airbnb" in adapter._transports
        assert adapter._transports["airbnb"].transport.command == "npx"

    def test_blank_travel_hacking_env_uses_default_url(self, monkeypatch):
        from adapters.travel_hacking import TravelHackingAdapter

        monkeypatch.setenv("TRAVEL_HACKING_MCP_URL", "")
        monkeypatch.setenv("TRAVEL_HACKING_API_KEY", "")

        adapter = TravelHackingAdapter(base_url=None, auth_token=None, profile="stay")

        assert adapter._legacy_transport.base_url == "http://localhost:8100/mcp"

    def test_loopback_travel_hacking_url_rewrites_in_container(self, monkeypatch):
        from adapters.travel_hacking import TravelHackingAdapter

        monkeypatch.setenv("AGENT_ORCHESTRATION_ROOT", "/app")
        monkeypatch.setattr("adapters.travel_hacking._running_in_container", lambda: True)

        def fake_get_server_config(name: str, workspace_root=None):
            if name == "travel-hacking":
                return MCPServerConfig(
                    name="travel-hacking",
                    type="http",
                    url="http://127.0.0.1:8100/mcp",
                )
            return None

        with patch("adapters.travel_hacking.get_server_config", side_effect=fake_get_server_config):
            adapter = TravelHackingAdapter(profile="stay")

        assert adapter._transports["travel-hacking"].transport.base_url == "http://host.docker.internal:8100/mcp"

    @pytest.mark.asyncio
    async def test_search_flights_adds_booking_url_when_missing(self):
        from adapters.travel_hacking import FlightSearchResult, TravelHackingAdapter

        class FakeTransport:
            async def call(self, method, params, response_model):
                assert method == "search_flights"
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

        adapter = TravelHackingAdapter(base_url="http://localhost:8100/mcp", profile="flights")
        adapter._transports = {}
        adapter._legacy_transport = FakeTransport()

        results = await adapter.search_flights(FlightSearchParams(origin="JFK", destination="LAX", departure_date="2026-07-10"))

        assert results[0].booking_url is not None
        assert "google.com/travel/flights" in results[0].booking_url


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
