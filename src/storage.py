"""
Tiny JSON-file state store. Tracks, per saved search:
  - the cheapest price we've ever seen
  - the cheapest price we last *notified* about (so we don't ping you
    every single hour about the same $312 fare)
  - when we last checked

No database needed for this scale -- it's one file per install.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SearchState:
    lowest_price_seen: Optional[float] = None
    last_notified_price: Optional[float] = None
    last_checked_at: Optional[str] = None
    last_notified_at: Optional[str] = None


@dataclass
class SearchResults:
    """The actual flight offers found on a search's last check (not a
    history -- each check overwrites the previous snapshot), so the UI
    has something to show besides a single rolling low price."""

    checked_at: Optional[str] = None
    offers: list = field(default_factory=list)


class Store:
    def __init__(self, path: str | Path, cls: type = SearchState):
        self.path = Path(path)
        self._cls = cls
        self._data: dict[str, dict] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text())

    def get(self, search_id: str):
        raw = self._data.get(search_id, {})
        return self._cls(**raw)

    def update(self, search_id: str, state: SearchState) -> None:
        self._data[search_id] = asdict(state)
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
