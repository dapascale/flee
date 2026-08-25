"""
Thin wrapper around fast-flights (an unofficial, no-API-key Google
Flights client) that turns a SavedSearch into a query, runs it, and
returns a small normalized result our storage/notify code can use.

fast-flights works by decoding/encoding Google Flights' own protobuf
URL format -- there's no official API involved, and no account or key
required. That's what makes it free, but it also means Google could
change their format and break it. If that happens, see the README
for the SerpApi fallback.

The real library only accepts date/from_airport/to_airport/max_stops
per leg, and returns one flat itinerary per Flight (a single "name"
string, a single total "duration", an int "stops", no per-leg or
per-layover breakdown). Everything else -- airlines_include/exclude,
departure-hour window, max_duration_minutes -- is filtered here, after
the fact, by parsing those plain-text fields. max_layover_minutes
isn't offered as a config field at all: the library's response has no
layover-length data to filter on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from fast_flights import FlightData, Passengers, get_flights

from .config import SavedSearch


@dataclass
class FlightOffer:
    price: float
    airlines: str
    stops: int
    duration_minutes: Optional[int]
    raw_duration: str


def _expand_date_windows(search: SavedSearch) -> list[tuple[str, Optional[str]]]:
    """
    Turns a search's date_windows into concrete (depart_date, return_date)
    pairs -- one per window, each just the earliest possible departure
    (window.start) so every window costs exactly one query. Capped at
    MAX_DATE_WINDOWS entries already, by config.py's validation.
    """
    if search.date_windows is None:
        return [(search.depart_date, search.return_date)]

    pairs = []
    for window in search.date_windows:
        depart = window.start
        if search.trip_type == "round-trip":
            depart_dt = datetime.strptime(window.start, "%Y-%m-%d").date()
            return_dt = depart_dt + timedelta(days=window.trip_length_days)
            pairs.append((depart, return_dt.isoformat()))
        else:
            pairs.append((depart, None))
    return pairs


def _build_flight_data(
    search: SavedSearch, depart_date: str, return_date: Optional[str]
) -> list[FlightData]:
    legs = [
        FlightData(
            date=depart_date,
            from_airport=search.origin,
            to_airport=search.destination,
            max_stops=search.max_stops,
        )
    ]
    if search.trip_type == "round-trip":
        legs.append(
            FlightData(
                date=return_date,
                from_airport=search.destination,
                to_airport=search.origin,
                max_stops=search.max_stops,
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


def _parse_departure_hour(raw: str) -> Optional[int]:
    """fast-flights gives departure times like '10:30 AM' -- turn that into a 24h hour."""
    match = re.search(r"(\d{1,2}):\d{2}\s*(AM|PM)", raw, re.IGNORECASE)
    if not match:
        return None
    hour = int(match.group(1)) % 12
    if match.group(2).upper() == "PM":
        hour += 12
    return hour


def search_flights(search: SavedSearch) -> list[FlightOffer]:
    """
    Runs the search against Google Flights and returns matching offers,
    cheapest first.

    If the search uses date_windows instead of a fixed depart_date, this
    runs one query per window (capped at MAX_DATE_WINDOWS by config.py)
    and merges the results, so a flexible search costs a small, bounded
    number of requests instead of one per candidate day.
    """
    offers: list[FlightOffer] = []
    for depart_date, return_date in _expand_date_windows(search):
        offers.extend(_search_one_date_pair(search, depart_date, return_date))
    return sorted(offers, key=lambda o: o.price)


def _search_one_date_pair(
    search: SavedSearch, depart_date: str, return_date: Optional[str]
) -> list[FlightOffer]:
    result = get_flights(
        flight_data=_build_flight_data(search, depart_date, return_date),
        trip=search.trip_type,
        seat=search.cabin,
        passengers=Passengers(adults=search.adults, children=search.children),
        max_stops=search.max_stops,
    )

    offers: list[FlightOffer] = []
    for flight in result.flights:
        name = flight.name or ""

        if search.airlines_include and not any(
            code.lower() in name.lower() for code in search.airlines_include
        ):
            continue
        if search.airlines_exclude and any(
            code.lower() in name.lower() for code in search.airlines_exclude
        ):
            continue

        stops = flight.stops if isinstance(flight.stops, int) else 0
        if search.max_stops is not None and stops > search.max_stops:
            continue

        duration_minutes = _parse_duration_minutes(flight.duration)
        if (
            search.max_duration_minutes is not None
            and duration_minutes is not None
            and duration_minutes > search.max_duration_minutes
        ):
            continue

        departure_hour = _parse_departure_hour(flight.departure)
        if departure_hour is not None:
            if (
                search.earliest_departure_hour is not None
                and departure_hour < search.earliest_departure_hour
            ):
                continue
            if (
                search.latest_departure_hour is not None
                and departure_hour > search.latest_departure_hour
            ):
                continue

        try:
            price = float(str(flight.price).replace("$", "").replace(",", ""))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue  # "Price unavailable" comes back as "0"

        offers.append(
            FlightOffer(
                price=price,
                airlines=name,
                stops=stops,
                duration_minutes=duration_minutes,
                raw_duration=flight.duration,
            )
        )

    return offers
