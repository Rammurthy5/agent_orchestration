"""Travel MCP adapter used by the Flights and Stay agents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel, Field, RootModel, create_model

from adapters.base import BaseMCPAdapter
from adapters.mcp_config import MCPServerConfig, get_server_config
from adapters.stdio import BaseMCPStdioAdapter
from tools.flights import FlightResult, FlightSearchParams, RouteComparison
from tools.stay import AvailabilityResult, HotelResult, HotelSearchParams

_REPO_ROOT = Path(__file__).resolve().parent.parent

_FLIGHT_SERVERS = ("kiwi", "skiplagged")
_STAY_SERVERS = ("trivago", "skiplagged")
_AVAILABILITY_SERVERS = _STAY_SERVERS


@dataclass(slots=True)
class _TransportEntry:
    name: str
    transport: Any


class TravelHackingAdapter:
    """Adapter for the travel MCP servers used by the specialized agents."""

    def __init__(self, base_url: str | None = None, auth_token: str | None = None, profile: str = "combined"):
        self._profile = profile
        self._transports: dict[str, _TransportEntry] = {}
        self._tool_name_cache: dict[tuple[str, str], str] = {}

        for server_name in self._candidate_servers():
            config = get_server_config(server_name, _REPO_ROOT)
            if config is None:
                continue
            self._transports[server_name] = _TransportEntry(
                name=server_name,
                transport=self._build_transport_from_config(config),
            )

    async def close(self) -> None:
        for entry in self._transports.values():
            await entry.transport.close()

    async def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for entry in self._transports.values():
            for tool in await entry.transport.list_tools():
                key = (tool.get("name", ""), tool.get("description", ""))
                if key in seen:
                    continue
                seen.add(key)
                tools.append(tool)
        return tools

    async def search_flights(self, params: FlightSearchParams) -> list[FlightResult]:
        """Search for flights matching the given parameters."""
        server_order = self._flight_server_order(params.preferred_backend)
        errors: list[str] = []
        for entry in self._entries_for(server_order):
            try:
                if entry.name == "kiwi":
                    flights = await self._search_flights_kiwi(entry, params)
                else:
                    result = await self._call_entry(entry, "search_flights", params, FlightSearchResult)
                    flights = self._flight_results_from_payload(result, params)
                return [self._with_booking_url(flight, params) for flight in flights]
            except Exception as exc:
                errors.append(f"{entry.name}: {exc}")

        if not errors:
            raise RuntimeError("travel tool search_flights failed: no MCP transports configured")

        raise RuntimeError("travel tool search_flights failed: " + "; ".join(errors))

    def _flight_server_order(self, preferred_backend: str | None) -> tuple[str, ...]:
        if not preferred_backend:
            return _FLIGHT_SERVERS
        normalized = preferred_backend.lower()
        prioritized = [s for s in _FLIGHT_SERVERS if normalized in s.lower()]
        rest = [s for s in _FLIGHT_SERVERS if normalized not in s.lower()]
        return tuple(prioritized + rest)

    async def compare_routes(self, route_ids: list[str]) -> RouteComparison:
        """Compare multiple routes by cost and duration."""

        from pydantic import BaseModel

        class CompareParams(BaseModel):
            routes: list[str]

        return await self._call_first("compare_routes", CompareParams(routes=route_ids), RouteComparison, _FLIGHT_SERVERS)

    async def search_hotels(self, params: HotelSearchParams) -> list[HotelResult]:
        """Search for hotels matching the given parameters."""
        errors: list[str] = []
        for entry in self._entries_for(_STAY_SERVERS):
            try:
                if entry.name == "trivago":
                    return await self._search_hotels_trivago(entry, params)

                result = await self._call_entry(entry, "search_hotels", params, HotelSearchResult)
                return self._hotel_results_from_payload(result, fallback_location=params.location)
            except Exception as exc:
                errors.append(f"{entry.name}: {exc}")

        if not errors:
            raise RuntimeError("travel tool search_hotels failed: no MCP transports configured")

        raise RuntimeError("travel tool search_hotels failed: " + "; ".join(errors))

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
        return (*_FLIGHT_SERVERS, *_STAY_SERVERS)

    def _build_transport_from_config(
        self,
        config: MCPServerConfig,
    ) -> Any:
        if config.type == "stdio" and config.command:
            return BaseMCPStdioAdapter(
                command=config.command,
                args=config.args,
                env=config.env,
                cwd=_REPO_ROOT,
            )

        return BaseMCPAdapter(base_url=config.url, auth_token=_authorization_token(config))

    async def _call_first(self, method: str, params: Any, response_model: type[Any], server_names: tuple[str, ...]) -> Any:
        errors: list[str] = []
        for entry in self._entries_for(server_names):
            try:
                return await self._call_entry(entry, method, params, response_model)
            except Exception as exc:
                errors.append(f"{entry.name}: {exc}")

        if not errors:
            raise RuntimeError(f"travel tool {method} failed: no MCP transports configured")

        raise RuntimeError(f"travel tool {method} failed: " + "; ".join(errors))

    async def _call_entry(
        self,
        entry: _TransportEntry,
        method: str,
        params: BaseModel,
        response_model: type[Any],
    ) -> Any:
        candidate_names = await self._resolve_tool_candidates(entry, method)
        last_error: Exception | None = None

        for tool_name in candidate_names:
            param_variants = self._build_call_param_variants(entry.name, method, tool_name, params)
            for call_params in param_variants:
                try:
                    return await entry.transport.call(tool_name, call_params, response_model)
                except Exception as exc:
                    last_error = exc
                    if not self._is_missing_tool_error(exc) and not self._is_invalid_args_error(exc):
                        break

        if last_error is not None:
            raise last_error

        raise RuntimeError(f"travel tool {method} failed: no tool candidates resolved for {entry.name}")

    async def _search_flights_kiwi(
        self,
        entry: _TransportEntry,
        params: FlightSearchParams,
    ) -> list[FlightResult]:
        candidate_names = await self._resolve_tool_candidates(entry, "search_flights")
        last_error: Exception | None = None

        for tool_name in candidate_names:
            param_variants = self._build_call_param_variants(entry.name, "search_flights", tool_name, params)
            for call_params in param_variants:
                try:
                    result = await entry.transport.call(tool_name, call_params, KiwiFlightSearchResult)
                    if isinstance(result, FlightSearchResult):
                        if result.flights:
                            return result.flights
                        raise RuntimeError("Kiwi flight search returned no results")
                    flights = [
                        flight
                        for flight in (
                            self._flight_result_from_kiwi(item)
                            for item in result.root
                        )
                        if flight is not None
                    ]
                    if flights:
                        return flights
                    raise RuntimeError("Kiwi flight search returned no results")
                except Exception as exc:
                    last_error = exc
                    if not self._is_missing_tool_error(exc) and not self._is_invalid_args_error(exc):
                        break

        if last_error is not None:
            raise last_error

        raise RuntimeError(f"travel tool search_flights failed: no tool candidates resolved for {entry.name}")

    async def _search_hotels_trivago(
        self,
        entry: _TransportEntry,
        params: HotelSearchParams,
    ) -> list[HotelResult]:
        try:
            tools = await entry.transport.list_tools()
        except Exception:
            result = await self._call_entry(entry, "search_hotels", params, HotelSearchResult)
            return self._hotel_results_from_payload(result, fallback_location=params.location)

        tool_names = {str(tool.get("name", "")) for tool in tools}
        if "trivago-search-suggestions" not in tool_names or "trivago-accommodation-search" not in tool_names:
            result = await self._call_entry(entry, "search_hotels", params, HotelSearchResult)
            return self._hotel_results_from_payload(result, fallback_location=params.location)

        suggestions = await entry.transport.call(
            "trivago-search-suggestions",
            TrivagoSearchSuggestionsParams(query=params.location),
            TrivagoSuggestionSearchResult,
        )
        suggestion = self._pick_trivago_suggestion(suggestions, params.location)
        if suggestion is None:
            detail = suggestions.error or "Trivago returned no matching suggestions"
            raise RuntimeError(detail)

        accommodations = await entry.transport.call(
            "trivago-accommodation-search",
            TrivagoAccommodationSearchParams(
                ns=suggestion.ns,
                id=suggestion.id,
                arrival=params.check_in,
                departure=params.check_out,
                adults=params.guests,
            ),
            TrivagoAccommodationSearchResult,
        )
        return self._hotel_results_from_payload(accommodations, fallback_location=params.location)

    def _entries_for(self, server_names: tuple[str, ...]) -> list[_TransportEntry]:
        transports: list[_TransportEntry] = []
        for name in server_names:
            entry = self._transports.get(name)
            if entry is not None:
                transports.append(entry)
        return transports

    async def _resolve_tool_candidates(self, entry: _TransportEntry, logical_name: str) -> list[str]:
        cache_key = (entry.name, logical_name)
        cached = self._tool_name_cache.get(cache_key)
        if cached:
            return self._dedupe_names([*self._tool_candidates(entry.name, logical_name), cached])

        try:
            tools = await entry.transport.list_tools()
        except Exception:
            candidates = self._dedupe_names(self._tool_candidates(entry.name, logical_name))
            self._tool_name_cache[cache_key] = candidates[0]
            return candidates

        resolved = self._select_tool_name(entry.name, logical_name, tools)
        self._tool_name_cache[cache_key] = resolved
        return self._dedupe_names([*self._tool_candidates(entry.name, logical_name), resolved])

    def _select_tool_name(self, server_name: str, logical_name: str, tools: list[dict[str, Any]]) -> str:
        candidates = self._tool_candidates(server_name, logical_name)
        normalized_candidates = {self._normalize_tool_name(name): name for name in candidates}

        for tool in tools:
            tool_name = str(tool.get("name", ""))
            normalized = self._normalize_tool_name(tool_name)
            if normalized in normalized_candidates:
                return tool_name

        best_name = logical_name
        best_score = -1
        for tool in tools:
            tool_name = str(tool.get("name", ""))
            description = str(tool.get("description", ""))
            score = self._score_tool_match(server_name, logical_name, tool_name, description)
            if score > best_score:
                best_score = score
                best_name = tool_name or best_name

        return best_name

    def _tool_candidates(self, server_name: str, logical_name: str) -> list[str]:
        alias_map: dict[str, dict[str, list[str]]] = {
            "kiwi": {
                "search_flights": ["search-flight"],
                "compare_routes": ["compare_routes", "compareRoutes", "compare"],
            },
            "skiplagged": {
                "search_flights": ["sk_flights_search", "search-flight"],
                "compare_routes": ["compare_routes", "compareRoutes", "compare"],
                "search_hotels": ["sk_hotels_search", "hotel_search", "search"],
                "check_availability": ["check_availability", "checkAvailability", "availability"],
            },
            "trivago": {
                "search_hotels": ["hotel_search", "trivago-accommodation-search", "search"],
                "check_availability": ["check_availability", "checkAvailability", "availability"],
            },
        }
        return alias_map.get(server_name, {}).get(logical_name, [logical_name])

    def _score_tool_match(self, server_name: str, logical_name: str, tool_name: str, description: str) -> int:
        normalized_name = self._normalize_tool_name(tool_name)
        normalized_description = self._normalize_tool_name(description)
        score = 0

        for candidate in self._tool_candidates(server_name, logical_name):
            normalized_candidate = self._normalize_tool_name(candidate)
            if normalized_name == normalized_candidate:
                score += 100
            if normalized_candidate in normalized_name:
                score += 25
            if normalized_candidate in normalized_description:
                score += 10

        logical_keywords: dict[str, dict[str, list[str]]] = {
            "kiwi": {
                "search_flights": ["flight", "kiwi", "airfare", "fare", "route"],
                "compare_routes": ["route", "compare", "flight"],
            },
            "skiplagged": {
                "search_flights": ["flight", "skiplagged", "fare", "trip"],
                "compare_routes": ["route", "compare", "flight"],
                "search_hotels": ["hotel", "stay", "room", "accommodation", "skiplagged"],
                "check_availability": ["availability", "hotel", "room"],
            },
            "trivago": {
                "search_hotels": ["hotel", "trivago", "stay", "room", "accommodation"],
                "check_availability": ["availability", "hotel", "room"],
            },
        }
        for keyword in logical_keywords.get(server_name, {}).get(logical_name, []):
            if keyword in normalized_name:
                score += 8
            if keyword in normalized_description:
                score += 4

        return score

    def _normalize_tool_name(self, value: str) -> str:
        return "".join(ch.lower() for ch in value if ch.isalnum())

    def _build_call_param_variants(self, server_name: str, logical_name: str, tool_name: str, params: BaseModel) -> list[BaseModel]:
        raw = params.model_dump()
        translated_variants = self._translate_param_variants(server_name, logical_name, tool_name, raw)
        models: list[BaseModel] = []
        for index, translated in enumerate(translated_variants):
            if translated == raw:
                models.append(params)
                continue
            field_defs = {key: (Any, ...) for key in translated}
            model_name = f"{self._normalize_tool_name(tool_name).title()}CallParams{index}"
            variant_model = create_model(model_name, **field_defs)
            models.append(variant_model(**translated))  # type: ignore[call-arg]
        return self._dedupe_models(models)

    def _translate_param_variants(
        self,
        server_name: str,
        logical_name: str,
        tool_name: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if logical_name == "search_flights":
            if server_name == "kiwi":
                return self._dedupe_param_variants([
                    self._flight_kiwi_payload(params),
                    dict(params),
                ])
            if server_name == "skiplagged":
                return self._dedupe_param_variants([
                    self._flight_skiplagged_payload(params),
                    dict(params),
                ])

        if logical_name == "search_hotels":
            if server_name == "trivago":
                return self._dedupe_param_variants([
                    self._hotel_trivago_payload(params),
                    self._hotel_trivago_legacy_payload(params),
                    self._hotel_location_payload(params, field="city", check_in_key="checkin", check_out_key="checkout"),
                    self._hotel_location_payload(params, field="destination", check_in_key="checkin", check_out_key="checkout"),
                    self._hotel_location_payload(params, field="city"),
                    self._hotel_location_payload(params, field="destination"),
                    dict(params),
                ])
            if server_name == "skiplagged":
                return self._dedupe_param_variants([
                    self._hotel_skiplagged_payload(params),
                    self._hotel_location_payload(params, field="city", check_in_key="checkin", check_out_key="checkout"),
                    self._hotel_location_payload(params, field="destination", check_in_key="checkin", check_out_key="checkout"),
                    self._hotel_location_payload(params, field="city"),
                    self._hotel_location_payload(params, field="destination"),
                    dict(params),
                ])

        if logical_name == "check_availability":
            if server_name in {"trivago", "skiplagged"}:
                return self._dedupe_param_variants([
                    self._availability_payload(params),
                    dict(params),
                ])

        return [dict(params)]

    def _flight_kiwi_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = dict(params)
        payload["flyFrom"] = payload.pop("origin", payload.get("flyFrom"))
        payload["flyTo"] = payload.pop("destination", payload.get("flyTo"))
        payload["departureDate"] = self._format_kiwi_date(
            payload.pop("departure_date", payload.get("departureDate"))
        )
        if payload.get("return_date") is not None:
            payload["returnDate"] = self._format_kiwi_date(payload.pop("return_date"))
        payload.pop("guests", None)
        payload.pop("limit", None)
        payload.pop("sort", None)
        return {k: v for k, v in payload.items() if v is not None}

    def _flight_skiplagged_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = dict(params)
        payload["origin"] = payload.pop("origin", payload.get("origin"))
        payload["destination"] = payload.pop("destination", payload.get("destination"))
        payload["departureDate"] = payload.pop("departure_date", payload.get("departureDate"))
        if payload.get("return_date") is not None:
            payload["returnDate"] = payload.pop("return_date")
        payload.setdefault("limit", 3)
        payload.setdefault("sort", "price")
        payload.pop("guests", None)
        return {k: v for k, v in payload.items() if v is not None}

    def _hotel_trivago_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._hotel_query_payload(params, location_key="city", check_in_key="checkin", check_out_key="checkout")

    def _hotel_trivago_legacy_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._hotel_query_payload(params, location_key="city", check_in_key="checkin", check_out_key="checkout")

    def _hotel_skiplagged_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        location = params.get("location")
        if location is not None:
            payload["city"] = location
        payload["checkin"] = params.get("checkIn") or params.get("check_in")
        payload["checkout"] = params.get("checkOut") or params.get("check_out")
        if params.get("guests") is not None:
            payload["numAdults"] = params["guests"]
        payload.setdefault("numRooms", 1)
        payload.setdefault("sort", "value")
        payload.setdefault("limit", 12)
        return {k: v for k, v in payload.items() if v is not None}

    def _hotel_location_payload(
        self,
        params: dict[str, Any],
        *,
        field: str,
        check_in_key: str = "checkIn",
        check_out_key: str = "checkOut",
    ) -> dict[str, Any]:
        return self._hotel_query_payload(
            params,
            location_key=field,
            check_in_key=check_in_key,
            check_out_key=check_out_key,
        )

    def _hotel_query_payload(
        self,
        params: dict[str, Any],
        *,
        location_key: str,
        check_in_key: str = "checkIn",
        check_out_key: str = "checkOut",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        location = params.get("location")
        if location is not None:
            payload[location_key] = location
        payload[check_in_key] = params.get("checkIn") or params.get("check_in")
        payload[check_out_key] = params.get("checkOut") or params.get("check_out")
        if params.get("guests") is not None:
            payload["adults"] = params["guests"]
        if params.get("max_price_per_night") is not None:
            payload["maxPricePerNight"] = params["max_price_per_night"]
        if params.get("maxPricePerNight") is not None:
            payload["maxPricePerNight"] = params["maxPricePerNight"]
        return {k: v for k, v in payload.items() if v is not None}

    def _availability_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = dict(params)
        payload["hotelId"] = payload.pop("hotel_id", payload.get("hotelId"))
        payload["checkIn"] = payload.pop("check_in", payload.get("checkIn"))
        payload["checkOut"] = payload.pop("check_out", payload.get("checkOut"))
        return {k: v for k, v in payload.items() if v is not None}

    def _dedupe_names(self, names: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for name in names:
            if not name:
                continue
            normalized = self._normalize_tool_name(name)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(name)
        return deduped

    def _dedupe_models(self, models: list[BaseModel]) -> list[BaseModel]:
        seen: set[tuple[tuple[str, Any], ...]] = set()
        deduped: list[BaseModel] = []
        for model in models:
            key = tuple(sorted(model.model_dump().items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(model)
        return deduped

    def _dedupe_param_variants(self, variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[tuple[str, Any], ...]] = set()
        deduped: list[dict[str, Any]] = []
        for variant in variants:
            key = tuple(sorted(variant.items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(variant)
        return deduped

    def _is_missing_tool_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "not found" in message
            or "method not found" in message
            or "tool_not_found" in message
            or "unknown tool" in message
        )

    def _is_invalid_args_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "invalid arguments" in message
            or "validation error" in message
            or "invalid_type" in message
            or "required" in message
            or "unexpected keyword" in message
            or "invalid value" in message
        )

    def _pick_trivago_suggestion(
        self,
        result: TrivagoSuggestionSearchResult,
        target_location: str,
    ) -> TrivagoSuggestion | None:
        if not result.suggestions:
            return None

        normalized_target = self._normalize_tool_name(target_location)
        for suggestion in result.suggestions:
            haystacks = [
                suggestion.location,
                suggestion.location_label,
            ]
            if any(normalized_target and normalized_target in self._normalize_tool_name(value) for value in haystacks if value):
                return suggestion
        return result.suggestions[0]

    def _flight_results_from_payload(
        self,
        result: FlightSearchResult,
        params: FlightSearchParams,
    ) -> list[FlightResult]:
        if result.flights:
            return result.flights

        if result.text:
            flights = self._flight_results_from_text(result.text, params)
            if flights:
                return flights

        detail = result.error or result.text
        if detail:
            raise RuntimeError(detail)

        raise RuntimeError("flight search returned no results")

    def _flight_result_from_kiwi(self, payload: dict[str, Any]) -> FlightResult | None:
        origin = self._string_value(payload, "flyFrom", "origin")
        destination = self._string_value(payload, "flyTo", "destination")
        departure_time = self._nested_string_value(payload, ("departure", "local"), ("departure", "utc"), ("departure_time",))
        arrival_time = self._nested_string_value(payload, ("arrival", "local"), ("arrival", "utc"), ("arrival_time",))
        price = self._numeric_value(payload, "price", "price_usd")
        if not origin or not destination or not departure_time or not arrival_time or price is None:
            return None

        duration_seconds = self._numeric_value(payload, "durationInSeconds", "totalDurationInSeconds") or 0.0
        airline = self._string_value(payload, "airline", "carrier", "carrierName") or "Kiwi"
        stops = len(payload.get("layovers", [])) if isinstance(payload.get("layovers"), list) else 0
        return FlightResult(
            airline=airline,
            origin=origin,
            destination=destination,
            departure_time=departure_time,
            arrival_time=arrival_time,
            duration_minutes=max(1, int(duration_seconds // 60)) if duration_seconds else 1,
            price_usd=price,
            stops=stops,
            booking_url=self._string_value(payload, "deepLink", "booking_url", "url", "bookingLink"),
        )

    def _flight_results_from_text(self, text: str, params: FlightSearchParams) -> list[FlightResult]:
        rows = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
        flights: list[FlightResult] = []

        for row in rows:
            columns = [column.strip() for column in row.split("|")[1:-1]]
            if len(columns) < 7:
                continue
            if columns[0] == "Price" or columns[0].startswith("---"):
                continue

            price = self._extract_price(columns[0])
            duration_minutes = self._extract_duration_minutes(columns[1])
            stops = self._extract_flight_stops(columns[2])
            airline = columns[4] if columns[4] and columns[4] != "-" else "Unknown"
            departure_time, arrival_time = self._extract_segment_times(columns[5])
            booking_url = self._extract_markdown_link(columns[6])

            if price is None or duration_minutes is None or departure_time is None or arrival_time is None:
                continue

            flights.append(
                FlightResult(
                    airline=airline,
                    origin=params.origin,
                    destination=params.destination,
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    duration_minutes=duration_minutes,
                    price_usd=price,
                    stops=stops,
                    booking_url=booking_url,
                )
            )

        return flights

    def _hotel_results_from_payload(self, result: HotelSearchResult, *, fallback_location: str) -> list[HotelResult]:
        if result.hotels:
            return result.hotels

        if result.accommodations:
            hotels = [
                hotel
                for hotel in (
                    self._hotel_result_from_accommodation(accommodation, fallback_location=fallback_location)
                    for accommodation in result.accommodations
                )
                if hotel is not None
            ]
            if hotels:
                return hotels

        if result.text:
            hotels = self._hotel_results_from_text(result.text, fallback_location=fallback_location)
            if hotels:
                return hotels

        detail = self._hotel_search_error_detail(result)
        if detail:
            raise RuntimeError(detail)

        raise RuntimeError("hotel search returned no results")

    def _hotel_result_from_accommodation(
        self,
        accommodation: dict[str, Any],
        *,
        fallback_location: str,
    ) -> HotelResult | None:
        name = self._string_value(
            accommodation,
            "name",
            "title",
            "hotelName",
            "accommodationName",
            "accommodation_name",
        )
        if not name:
            return None

        hotel_id = self._string_value(
            accommodation,
            "hotel_id",
            "hotelId",
            "id",
            "accommodationId",
            "accommodation_id",
        ) or name
        location = self._string_value(accommodation, "location", "city", "address", "region") or fallback_location
        price = self._numeric_value(
            accommodation,
            "price_per_night_usd",
            "pricePerNightUsd",
            "price",
            "amount",
            "nightlyRate",
            "nightly_rate",
        )
        rating = self._numeric_value(accommodation, "rating", "review_rating", "reviewRating", "stars")
        amenities = self._list_of_strings(accommodation.get("amenities"))

        return HotelResult(
            hotel_id=hotel_id,
            name=name,
            location=location,
            price_per_night_usd=price or 0.0,
            rating=rating,
            amenities=amenities,
            booking_url=self._string_value(
                accommodation,
                "booking_url",
                "bookingUrl",
                "bookingLink",
                "booking_link",
                "url",
                "link",
            ),
        )

    def _hotel_search_error_detail(self, result: HotelSearchResult) -> str | None:
        parts: list[str] = []
        if result.error:
            parts.append(result.error)
        if result.text and not self._hotel_results_from_text(result.text, fallback_location=""):
            parts.append(result.text)
        if result.validation_errors:
            parts.extend(str(item) for item in result.validation_errors)
        return "; ".join(part for part in parts if part) or None

    def _hotel_results_from_text(self, text: str, *, fallback_location: str) -> list[HotelResult]:
        rows = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
        hotels: list[HotelResult] = []

        for row in rows:
            columns = [column.strip() for column in row.split("|")[1:-1]]
            if len(columns) < 6:
                continue
            if columns[0] == "Hotel" or columns[0].startswith("---"):
                continue

            name_and_address = columns[0]
            name = re.sub(r"\*", "", name_and_address.split("<br/>", 1)[0]).strip()
            location = fallback_location
            if "<br/>" in name_and_address:
                location = name_and_address.split("<br/>", 1)[1].strip() or fallback_location

            rating = self._extract_rating(columns[1])
            price = self._extract_price(columns[2])
            amenities = [item.strip() for item in columns[4].split(",") if item.strip()]
            booking_url = self._extract_markdown_link(columns[5])
            booking_match = re.search(r"/hotel/([^/]+)/", booking_url or columns[5])
            hotel_id = booking_match.group(1) if booking_match else name

            if not name:
                continue

            hotels.append(
                HotelResult(
                    hotel_id=hotel_id,
                    name=name,
                    location=location,
                    price_per_night_usd=price or 0.0,
                    rating=rating,
                    amenities=amenities,
                    booking_url=booking_url,
                )
            )

        return hotels

    def _extract_rating(self, value: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", value)
        if match:
            return float(match.group(1))
        match = re.search(r"(\d+(?:\.\d+)?)\s*★", value)
        if match:
            return float(match.group(1))
        return None

    def _extract_price(self, value: str) -> float | None:
        match = re.search(r"\$\s*(\d+(?:\.\d+)?)", value)
        if not match:
            return None
        return float(match.group(1))

    def _extract_markdown_link(self, value: str) -> str | None:
        match = re.search(r"\((https?://[^)]+)\)", value)
        if match:
            return match.group(1)
        return None

    def _extract_duration_minutes(self, value: str) -> int | None:
        match = re.search(r"(?:(\d+)h)?\s*(?:(\d+)m)?", value)
        if not match:
            return None
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        total = hours * 60 + minutes
        return total or None

    def _extract_flight_stops(self, value: str) -> int:
        lowered = value.lower()
        if "nonstop" in lowered:
            return 0
        match = re.search(r"(\d+)", lowered)
        if match:
            return int(match.group(1))
        if "one" in lowered:
            return 1
        return 2 if lowered else 0

    def _extract_segment_times(self, value: str) -> tuple[str | None, str | None]:
        match = re.search(r"\(([^()]+?)\s*→\s*([^()]+?)\)", value)
        if not match:
            return None, None
        return match.group(1).strip(), match.group(2).strip()

    def _format_kiwi_date(self, value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
        if iso_match:
            year, month, day = iso_match.groups()
            return f"{day}/{month}/{year}"
        return value

    def _string_value(self, payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _nested_string_value(self, payload: dict[str, Any], *paths: tuple[str, ...]) -> str | None:
        for path in paths:
            value: Any = payload
            for segment in path:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(segment)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _numeric_value(self, payload: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
            if isinstance(value, dict):
                nested = self._numeric_value(value, "amount", "value", "price")
                if nested is not None:
                    return nested
        return None

    def _list_of_strings(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in (str(entry).strip() for entry in value) if item]

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


class FlightSearchResult(BaseModel):
    flights: list[FlightResult] = Field(default_factory=list)
    text: str | None = None
    error: str | None = None


class KiwiFlightSearchResult(RootModel[list[dict[str, Any]]]):
    pass


class HotelSearchResult(BaseModel):
    hotels: list[HotelResult] = Field(default_factory=list)
    accommodations: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    text: str | None = None
    validation_errors: list[Any] = Field(default_factory=list)


class TrivagoSearchSuggestionsParams(BaseModel):
    query: str


class TrivagoSuggestion(BaseModel):
    id: int
    ns: int
    location: str | None = None
    location_label: str | None = None


class TrivagoSuggestionSearchResult(BaseModel):
    suggestions: list[TrivagoSuggestion] = Field(default_factory=list)
    error: str | None = None


class TrivagoAccommodationSearchParams(BaseModel):
    ns: int
    id: int
    arrival: str
    departure: str
    adults: int = 1


class TrivagoAccommodationSearchResult(HotelSearchResult):
    pass
