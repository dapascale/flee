"""
Loads and validates saved searches from a JSON file.

Each saved search is one "tracked" flight search + its filters + how
you want to be notified about it. You can have as many of these as
you want in the same config file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


TripType = Literal["round-trip", "one-way"]
NotifyMode = Literal["under_max_price", "price_drop", "both"]
Channel = Literal["ntfy", "email"]

MAX_DATE_WINDOWS = 4


@dataclass
class DateWindow:
    """
    One concrete candidate departure date to check, as part of a
    "flexible" search -- e.g. up to MAX_DATE_WINDOWS of these let you
    sample a few spots across a month (early/mid/late) without scanning
    every single day, which would multiply query volume against Google
    Flights unboundedly. Expanded to a depart/return pair (start,
    start + trip_length_days) before querying -- see flights.py's
    _expand_date_windows(). trip_length_days is ignored for one-way
    searches. `label` is just a human-readable note (e.g. "early
    March"), never used for querying.
    """

    start: str
    trip_length_days: Optional[int] = None
    label: Optional[str] = None


@dataclass
class SavedSearch:
    id: str
    label: str
    origin: str
    destination: str
    trip_type: TripType = "round-trip"
    depart_date: Optional[str] = None
    return_date: Optional[str] = None
    date_windows: Optional[list[DateWindow]] = None

    cabin: Literal["economy", "premium-economy", "business", "first"] = "economy"
    adults: int = 1
    children: int = 0

    # --- filters (all optional; None means "no restriction") ---
    # Google Flights' data only gives us airline *names* (e.g. "Delta"),
    # not IATA codes, and no per-leg layover length -- so airline filters
    # match by case-insensitive substring, and there's no max_layover_minutes
    # (the underlying data has nothing to filter on).
    max_stops: Optional[int] = None  # 0 = nonstop only
    airlines_include: Optional[list[str]] = None  # name substrings, e.g. ["Delta"]
    airlines_exclude: Optional[list[str]] = None
    earliest_departure_hour: Optional[int] = None  # 0-23
    latest_departure_hour: Optional[int] = None
    max_duration_minutes: Optional[int] = None

    # --- alerting behavior ---
    max_price: Optional[float] = None
    notify_on: NotifyMode = "both"
    min_drop_amount: float = 1.0  # smallest price drop worth a notification
    channels: list[Channel] = field(default_factory=lambda: ["ntfy", "email"])
    active: bool = True

    def __post_init__(self):
        has_fixed_date = self.depart_date is not None
        has_windows = self.date_windows is not None

        if has_fixed_date == has_windows:
            raise ValueError(
                f"[{self.id}] set exactly one of depart_date or date_windows"
            )
        if has_windows:
            if not (1 <= len(self.date_windows) <= MAX_DATE_WINDOWS):
                raise ValueError(
                    f"[{self.id}] date_windows must have 1-{MAX_DATE_WINDOWS} entries"
                )
            if self.trip_type == "round-trip" and any(
                w.trip_length_days is None for w in self.date_windows
            ):
                raise ValueError(
                    f"[{self.id}] round-trip date_windows need trip_length_days"
                )
        if has_fixed_date and self.trip_type == "round-trip" and not self.return_date:
            raise ValueError(f"[{self.id}] round-trip search needs a return_date")
        if self.max_stops is not None and self.max_stops < 0:
            raise ValueError(f"[{self.id}] max_stops can't be negative")
        if self.notify_on == "under_max_price" and self.max_price is None:
            raise ValueError(
                f"[{self.id}] notify_on='under_max_price' requires max_price to be set"
            )


def load_searches(path: str | Path) -> list[SavedSearch]:
    path = Path(path)
    data = json.loads(path.read_text())
    searches = []
    for item in data:
        item = dict(item)
        if item.get("date_windows") is not None:
            item["date_windows"] = [DateWindow(**w) for w in item["date_windows"]]
        searches.append(SavedSearch(**item))

    ids = [s.id for s in searches]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate search ids in {path}: {dupes}")

    return searches
