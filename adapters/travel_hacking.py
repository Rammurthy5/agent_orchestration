"""Travel Hacking Toolkit MCP adapter — used by Flights and Stay agents.

This adapter supports the toolkit-style split between flight and lodging MCP
servers while keeping the existing `travel-hacking` fallback for local setups.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse, urlunparse

from pydantic import BaseModel

from adapters.base import BaseMCPAdapter
from adapters.mcp_config import MCPServerConfig, get_server_config
from adapters.stdio import BaseMCPStdioAdapter
from tools.flights import FlightResult, FlightSearchParams, RouteComparison
from tools.stay import AvailabilityResult, HotelResult, HotelSearchParams

_REPO_ROOT = Path(__file__).resolve().parent.parent

_FLIGHT_SERVERS = ("skiplagged", "kiwi", "travel-hacking")
_STAY_SERVERS = ("airbnb", "trivago", "travel-hacking")
_AVAILABILITY_SERVERS = ("airbnb", "trivago", "travel-hacking")


@dataclass(slots=True)
class _TransportEntry:
    name: str
    transport: Any


class TravelHackingAdapter:
    """Adapter for toolkit-style travel MCP servers."""

    def __init__(self, base_url: str | None = None, auth_token: str | None = None, profile: str = "combined"):
        self._profile = profile
        self._transports: dict[str, _TransportEntry] = {}

        self._legacy_transport = self._build_legacy_transport(base_url, auth_token)
        for server_name in self._candidate_servers():
            if server_name == "travel-hacking":
                continue
            config = get_server_config(server_name, _REPO_ROOT)
            if config is None:
                continue
            self._transports[server_name] = _TransportEntry(
                name=server_name,
                transport=self._build_transport_from_config(config),
            )

        if "travel-hacking" not in self._transports:
            legacy_config = get_server_config("travel-hacking", _REPO_ROOT)
            if legacy_config is not None:
                self._transports["travel-hacking"] = _TransportEntry(
                    name="travel-hacking",
                    transport=self._build_transport_from_config(legacy_config, base_url, auth_token),
                )

    async def close(self) -> None:
        seen: set[int] = set()
        for entry in [*self._transports.values(), _TransportEntry("legacy", self._legacy_transport)]:
            transport = entry.transport
            key = id(transport)
            if key in seen:
                continue
            seen.add(key)
            await transport.close()

    async def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for transport in self._all_transports():
            for tool in await transport.list_tools():
                key = (tool.get("name", ""), tool.get("description", ""))
                if key in seen:
                    continue
                seen.add(key)
                tools.append(tool)
        return tools

    async def search_flights(self, params: FlightSearchParams) -> list[FlightResult]:
        """Search for flights matching the given parameters."""
        result = await self._call_first("search_flights", params, FlightSearchResult, _FLIGHT_SERVERS)
        return [self._with_booking_url(flight, params) for flight in result.flights]

    async def compare_routes(self, route_ids: list[str]) -> RouteComparison:
        """Compare multiple routes by cost and duration."""

        from pydantic import BaseModel

        class CompareParams(BaseModel):
            routes: list[str]

        return await self._call_first("compare_routes", CompareParams(routes=route_ids), RouteComparison, _FLIGHT_SERVERS)

    async def search_hotels(self, params: HotelSearchParams) -> list[HotelResult]:
        """Search for hotels matching the given parameters."""
        result = await self._call_first("search_hotels", params, HotelSearchResult, _STAY_SERVERS)
        return result.hotels

    async def check_availability(
        self, hotel_id: str, check_in: str, check_out: str
    ) -> AvailabilityResult:
        """Check real-time availability for a specific hotel."""

        from pydantic import BaseModel

        class AvailParams(BaseModel):
            hotel_id: str
            check_in: str
            check_out: str

        return await self._call_first(
            "check_availability",
            AvailParams(hotel_id=hotel_id, check_in=check_in, check_out=check_out),
            AvailabilityResult,
            _AVAILABILITY_SERVERS,
        )

    def _candidate_servers(self) -> tuple[str, ...]:
        if self._profile == "flights":
            return _FLIGHT_SERVERS
        if self._profile == "stay":
            return _STAY_SERVERS
        return (*_FLIGHT_SERVERS, *tuple(s for s in _STAY_SERVERS if s not in _FLIGHT_SERVERS))

    def _all_transports(self) -> list[Any]:
        transports = [entry.transport for entry in self._transports.values()]
        transports.append(self._legacy_transport)
        return transports

    def _build_legacy_transport(self, base_url: str | None, auth_token: str | None) -> BaseMCPAdapter:
        if not base_url:
            base_url = _first_nonempty(os.getenv("TRAVEL_HACKING_MCP_URL"), "http://localhost:8100/mcp")
        if not auth_token:
            auth_token = _first_nonempty(os.getenv("TRAVEL_HACKING_API_KEY"), "")
        return BaseMCPAdapter(base_url=base_url, auth_token=auth_token)

    def _build_transport_from_config(
        self,
        config: MCPServerConfig,
        base_url: str | None = None,
        auth_token: str | None = None,
    ) -> Any:
        if config.type == "stdio" and config.command:
            return BaseMCPStdioAdapter(
                command=config.command,
                args=config.args,
                env=config.env,
                cwd=_REPO_ROOT,
            )

        resolved_url = _first_nonempty(
            base_url,
            config.url,
            os.getenv("TRAVEL_HACKING_MCP_URL"),
            "http://localhost:8100/mcp",
        )
        resolved_url = _remap_loopback_url(resolved_url)
        resolved_token = _first_nonempty(
            auth_token,
            _authorization_token(config),
            os.getenv("TRAVEL_HACKING_API_KEY"),
            "",
        )
        return BaseMCPAdapter(base_url=resolved_url, auth_token=resolved_token)

    async def _call_first(self, method: str, params: Any, response_model: type[Any], server_names: tuple[str, ...]) -> Any:
        last_error: Exception | None = None
        for transport in self._transports_for(server_names):
            try:
                return await transport.call(method, params, response_model)
            except Exception as exc:
                last_error = exc

        try:
            return await self._legacy_transport.call(method, params, response_model)
        except Exception as exc:
            last_error = exc

        raise RuntimeError(f"travel tool {method} failed: {last_error}")

    def _transports_for(self, server_names: tuple[str, ...]) -> list[Any]:
        transports: list[Any] = []
        for name in server_names:
            entry = self._transports.get(name)
            if entry is not None:
                transports.append(entry.transport)
        return transports

    def _with_booking_url(self, flight: FlightResult, params: FlightSearchParams) -> FlightResult:
        if flight.booking_url:
            return flight
        departure_date = params.departure_date
        booking_url = (
            "https://www.google.com/travel/flights?q="
            + quote_plus(f"Flights from {params.origin} to {params.destination} on {departure_date}")
        )
        return flight.model_copy(update={"booking_url": booking_url})


def _authorization_token(config: MCPServerConfig) -> str:
    auth_header = config.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return auth_header


def _first_nonempty(*values: str | None) -> str:
    for value in values:
        if value:
            return value
    return ""


def _remap_loopback_url(url: str) -> str:
    """Rewrite localhost URLs for containerized runtimes.

    `.vscode/mcp.json` is shared between local and Docker runs. When the
    agents service runs in a container, `127.0.0.1` points at the container
    itself, so loopback MCP URLs need to be rewritten to the Docker host.
    """
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return url

    if not _running_in_container():
        return url

    netloc = "host.docker.internal"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _running_in_container() -> bool:
    return os.path.exists("/.dockerenv") or os.getenv("container") is not None


class FlightSearchResult(BaseModel):
    flights: list[FlightResult]


class HotelSearchResult(BaseModel):
    hotels: list[HotelResult]
