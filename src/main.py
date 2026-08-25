"""
Entry point. Run this on a schedule (cron/systemd timer -- see README)
to check every active saved search once and notify on whatever's
warranted.

    python -m src.main

Reads:
  config/searches.json  (or CONFIG_PATH env var)
Writes:
  data/state.json        (or STATE_PATH env var) -- price history per search
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from dataclasses import asdict

from .config import SavedSearch, load_searches
from .flights import search_flights
from .notify import notify_all
from .storage import SearchResults, Store, now_iso

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/searches.json")
STATE_PATH = os.environ.get("STATE_PATH", "data/state.json")
RESULTS_PATH = os.environ.get("RESULTS_PATH", "data/results.json")
SECONDS_BETWEEN_SEARCHES = float(os.environ.get("SECONDS_BETWEEN_SEARCHES", "5"))
TARGET_SEARCH_ID = os.environ.get("TARGET_SEARCH_ID") or None
MAX_SAVED_OFFERS = 15


def format_alert(search: SavedSearch, price: float, airlines: str, stops: int, reason: str) -> tuple[str, str]:
    stops_txt = "nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
    title = f"✈ {search.label}: ${price:,.0f}"
    body = (
        f"{search.origin} → {search.destination}"
        + (f" → {search.origin}" if search.trip_type == "round-trip" else "")
        + f"\n{search.depart_date}"
        + (f" – {search.return_date}" if search.return_date else "")
        + f"\n${price:,.0f} on {airlines} ({stops_txt})"
        + f"\n{reason}"
    )
    return title, body


def check_one(search: SavedSearch, store: Store, results_store: Store) -> None:
    state = store.get(search.id)

    offers = search_flights(search)
    state.last_checked_at = now_iso()

    results_store.update(
        search.id,
        SearchResults(
            checked_at=state.last_checked_at,
            offers=[asdict(o) for o in offers[:MAX_SAVED_OFFERS]],
        ),
    )

    if not offers:
        store.update(search.id, state)
        return

    best = offers[0]

    if state.lowest_price_seen is None or best.price < state.lowest_price_seen:
        state.lowest_price_seen = best.price

    # Gate every re-notification by min_drop_amount, so a search doesn't ping
    # you again over a $1 wobble in the same fare. On the very first check
    # there's nothing to compare against yet, so we bootstrap a baseline
    # silently unless the price already clears max_price (worth telling you
    # about immediately).
    is_first_check = state.last_notified_price is None
    # Distinct from is_first_check: a silent baseline still sets
    # last_notified_price without ever actually notifying (e.g. the price
    # was over max_price at the time). If max_price is later raised, or
    # notify_on is changed, the very first real notification shouldn't be
    # blocked by a drop-amount gate meant for *re*-notifications.
    has_notified_before = state.last_notified_at is not None
    drop_amount = 0.0 if is_first_check else (state.last_notified_price - best.price)
    moved_enough = drop_amount >= search.min_drop_amount

    under_max = search.max_price is not None and best.price <= search.max_price

    should_notify = False
    reason = ""

    if search.notify_on in ("under_max_price", "both") and under_max and (not has_notified_before or moved_enough):
        should_notify = True
        reason = f"At or under your ${search.max_price:,.0f} target."

    if search.notify_on in ("price_drop", "both") and not is_first_check and moved_enough and drop_amount > 0:
        should_notify = True
        reason = f"Dropped ${drop_amount:,.0f} from last alert."

    if should_notify:
        title, body = format_alert(search, best.price, best.airlines, best.stops, reason)
        try:
            notify_all(search.channels, title, body)
        except Exception as e:  # noqa: BLE001
            # notify_all already attempts every channel independently and
            # only raises after collecting all failures -- a broken email
            # config shouldn't erase that ntfy succeeded, and shouldn't
            # skip persisting state below (which would otherwise make this
            # search re-attempt, and re-send successful channels, on every
            # future check until the broken channel is fixed).
            print(f"  ! {search.id} notify partially failed: {e}", file=sys.stderr)
        state.last_notified_price = best.price
        state.last_notified_at = now_iso()
    elif is_first_check:
        # Silent baseline so future price_drop comparisons have a reference point.
        state.last_notified_price = best.price

    store.update(search.id, state)


def main() -> int:
    searches = load_searches(CONFIG_PATH)
    store = Store(STATE_PATH)
    results_store = Store(RESULTS_PATH, SearchResults)

    if TARGET_SEARCH_ID:
        # A specific "check now" request runs regardless of the active
        # flag -- that's a deliberate one-off action, not the scheduled
        # sweep, so being paused shouldn't silently no-op it.
        active = [s for s in searches if s.id == TARGET_SEARCH_ID]
        if not active:
            print(f"No search with id '{TARGET_SEARCH_ID}'", file=sys.stderr)
            return 1
    else:
        active = [s for s in searches if s.active]
    print(f"Checking {len(active)} search(es)...")

    exit_code = 0
    for i, search in enumerate(active):
        try:
            check_one(search, store, results_store)
            print(f"  ✓ {search.id} ({search.label})")
        except Exception:  # noqa: BLE001
            exit_code = 1
            print(f"  ✗ {search.id} ({search.label}) failed:", file=sys.stderr)
            traceback.print_exc()

        if i < len(active) - 1:
            time.sleep(SECONDS_BETWEEN_SEARCHES)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
