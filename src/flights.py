"""
Thin wrapper around fast-flights (an unofficial, no-API-key Google
Flights client) that turns a SavedSearch into a query, runs it, and
returns a small normalized result our storage/notify code can use.

fast-flights works by decoding/encoding Google Flights' own protobuf
URL format -- there's no official API involved, and no account or key
required. That's what makes it free, but it also means Google could
change their format and break it. If that happens, see the README
for the SerpApi fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fast_flights import FlightQuery, Passengers, create_query, get_flights

from .config import SavedSearch


@dataclass
class FlightOffer:
    price: float
    airlines: str
    stops: int
    duration_minutes: Optional[int]
    raw_duration: str


def _build_flight_queries(search: SavedSearch) -> list[FlightQuery]:
    legs = [
        FlightQuery(
            date=search.depart_date,
            from_airport=search.origin,
            to_airport=search.destination,
            max_stops=search.max_stops,
            airlines=search.airlines_include,
            earliest_departure_hour=search.earliest_departure_hour,
            latest_departure_hour=search.latest_departure_hour,
            max_duration_minutes=search.max_duration_minutes,
            max_layover_minutes=search.max_layover_minutes,
        )
    ]
    if search.trip_type == "round-trip":
        legs.append(
            FlightQuery(
                date=search.return_date,
                from_airport=search.destination,
                to_airport=search.origin,
                max_stops=search.max_stops,
                airlines=search.airlines_include,
                max_duration_minutes=search.max_duration_minutes,
                max_layover_minutes=search.max_layover_minutes,
            )
        )
    return legs


def _parse_duration_minutes(raw: str) -> Optional[int]:
    """fast-flights gives durations like '5 hr 30 min' -- turn that into minutes."""
    if not raw:
        return None
    hours, minutes = 0, 0
    parts = raw.replace("hr", "hr ").split()
    for i, token in enumerate(parts):
        if token.isdigit():
            if i + 1 < len(parts) and "hr" in parts[i + 1]:
                hours = int(token)
            elif i + 1 < len(parts) and "min" in parts[i + 1]:
                minutes = int(token)
    return hours * 60 + minutes if (hours or minutes) else None


def search_flights(search: SavedSearch, proxy: Optional[str] = None) -> list[FlightOffer]:
    """
    Runs the search against Google Flights and returns offers that already
    pass fast-flights' own filters. airlines_exclude and nonstop/stop-count
    edge cases are re-checked here since the library only supports an
    allow-list, not a block-list, for airlines.

    `proxy` lets you route the request through a VPN/proxy exit
    (e.g. http://127.0.0.1:PORT if you're running one locally on the
    box this script lives on) instead of the server's normal egress IP.
    """
    query = create_query(
        flights=_build_flight_queries(search),
        seat=search.cabin,
        trip=search.trip_type,
        passengers=Passengers(adults=search.adults, children=search.children),
        max_stops=search.max_stops,
        max_price=int(search.max_price) if search.max_price else None,
    )

    result = get_flights(query, proxy=proxy)  # result is a list of Flights (one per itinerary)

    offers: list[FlightOffer] = []
    for flight in result:
        if search.airlines_exclude and any(
            code in flight.airlines for code in search.airlines_exclude
        ):
            continue

        legs = flight.flights or []
        stops = max(len(legs) - 1, 0)
        if search.max_stops is not None and stops > search.max_stops:
            continue

        leg_durations = [_parse_duration_minutes(leg.duration) or 0 for leg in legs]
        total_minutes = sum(leg_durations) if leg_durations else None
        raw_duration = ", ".join(leg.duration for leg in legs if leg.duration)

        try:
            price = float(str(flight.price).replace("$", "").replace(",", ""))
        except (TypeError, ValueError):
            continue  # skip unparseable/"Price unavailable" entries

        offers.append(
            FlightOffer(
                price=price,
                airlines=flight.airlines,
                stops=stops,
                duration_minutes=total_minutes,
                raw_duration=raw_duration,
            )
        )

    return sorted(offers, key=lambda o: o.price)
