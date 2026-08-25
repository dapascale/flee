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


@dataclass
class SavedSearch:
    id: str
    label: str
    origin: str
    destination: str
    depart_date: str
    trip_type: TripType = "round-trip"
    return_date: Optional[str] = None

    cabin: Literal["economy", "premium-economy", "business", "first"] = "economy"
    adults: int = 1
    children: int = 0

    # --- filters (all optional; None means "no restriction") ---
    max_stops: Optional[int] = None  # 0 = nonstop only
    airlines_include: Optional[list[str]] = None  # IATA codes, e.g. ["AA", "DL"]
    airlines_exclude: Optional[list[str]] = None
    earliest_departure_hour: Optional[int] = None  # 0-23
    latest_departure_hour: Optional[int] = None
    max_duration_minutes: Optional[int] = None
    max_layover_minutes: Optional[int] = None

    # --- alerting behavior ---
    max_price: Optional[float] = None
    notify_on: NotifyMode = "both"
    min_drop_amount: float = 1.0  # smallest price drop worth a notification
    channels: list[Channel] = field(default_factory=lambda: ["ntfy", "email"])
    active: bool = True

    def __post_init__(self):
        if self.trip_type == "round-trip" and not self.return_date:
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
    searches = [SavedSearch(**item) for item in data]

    ids = [s.id for s in searches]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate search ids in {path}: {dupes}")

    return searches
