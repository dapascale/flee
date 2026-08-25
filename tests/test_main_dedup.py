from unittest.mock import patch

from src.config import SavedSearch
from src.flights import FlightOffer
from src.main import check_one
from src.storage import SearchResults, Store


def _search(**overrides):
    defaults = dict(
        id="s1",
        label="test",
        origin="JFK",
        destination="MCO",
        depart_date="2026-12-01",
        return_date="2026-12-08",
        max_price=300,
        notify_on="both",
        min_drop_amount=15,
        channels=[],
    )
    defaults.update(overrides)
    return SavedSearch(**defaults)


def _offer(price):
    return [FlightOffer(price=price, airlines="Delta", stops=0, duration_minutes=180, raw_duration="3 hr")]


def _stores(tmp_path):
    return Store(tmp_path / "state.json"), Store(tmp_path / "results.json", SearchResults)


def test_first_check_sets_baseline_silently_when_over_max_price(tmp_path):
    store, results_store = _stores(tmp_path)
    search = _search()

    with patch("src.main.search_flights", return_value=_offer(350)), patch(
        "src.main.notify_all"
    ) as notify:
        check_one(search, store, results_store)

    notify.assert_not_called()
    assert store.get(search.id).last_notified_price == 350


def test_first_check_notifies_immediately_when_under_max_price(tmp_path):
    store, results_store = _stores(tmp_path)
    search = _search()

    with patch("src.main.search_flights", return_value=_offer(250)), patch(
        "src.main.notify_all"
    ) as notify:
        check_one(search, store, results_store)

    notify.assert_called_once()
    assert store.get(search.id).last_notified_price == 250


def test_no_renotify_on_price_wobble_below_min_drop(tmp_path):
    store, results_store = _stores(tmp_path)
    search = _search()
    # all above max_price (300) and each within min_drop_amount (15) of the
    # first-check baseline (350), so nothing should ever fire
    prices = [350, 352, 348, 351, 349, 353, 347]

    with patch("src.main.notify_all") as notify:
        for price in prices:
            with patch("src.main.search_flights", return_value=_offer(price)):
                check_one(search, store, results_store)

    notify.assert_not_called()


def test_renotify_when_price_drops_enough(tmp_path):
    store, results_store = _stores(tmp_path)
    search = _search()

    with patch("src.main.notify_all") as notify:
        with patch("src.main.search_flights", return_value=_offer(350)):
            check_one(search, store, results_store)  # baseline, no notify
        with patch("src.main.search_flights", return_value=_offer(280)):
            check_one(search, store, results_store)  # under max_price, dropped 70 -> notify

    assert notify.call_count == 1
    assert store.get(search.id).last_notified_price == 280


def test_partial_notify_failure_still_persists_state(tmp_path):
    # Regression test: notify_all raises when e.g. email is misconfigured,
    # even though ntfy (attempted first, inside notify_all) succeeded.
    # check_one must not let that exception skip persisting state --
    # otherwise a broken email config causes the same search to re-fire
    # a real ntfy push on every future check, forever.
    store, results_store = _stores(tmp_path)
    search = _search(max_price=300, notify_on="under_max_price")

    with patch("src.main.search_flights", return_value=_offer(250)), patch(
        "src.main.notify_all", side_effect=RuntimeError("email failed: bad credentials")
    ):
        check_one(search, store, results_store)  # should not raise

    state = store.get(search.id)
    assert state.last_notified_price == 250
    assert state.last_notified_at is not None
    assert state.last_checked_at is not None


def test_results_store_saves_offers_on_every_check(tmp_path):
    store, results_store = _stores(tmp_path)
    search = _search()

    with patch("src.main.search_flights", return_value=_offer(350)), patch("src.main.notify_all"):
        check_one(search, store, results_store)

    results = results_store.get(search.id)
    assert results.checked_at is not None
    assert results.offers == [
        {"price": 350, "airlines": "Delta", "stops": 0, "duration_minutes": 180, "raw_duration": "3 hr"}
    ]


def test_notifies_after_max_price_raised_even_without_price_drop(tmp_path):
    # Regression test: first check is over max_price, sets a silent
    # baseline (never actually notified). max_price is then raised so
    # the *same* price now qualifies -- this must notify even though
    # the price itself hasn't moved by min_drop_amount, since the user
    # has never actually been notified about this search yet.
    store, results_store = _stores(tmp_path)
    search = _search(max_price=300, min_drop_amount=50)

    with patch("src.main.search_flights", return_value=_offer(350)), patch("src.main.notify_all") as notify:
        check_one(search, store, results_store)  # over max_price -> silent baseline

    notify.assert_not_called()
    assert store.get(search.id).last_notified_at is None

    search.max_price = 400  # raised; same $350 price now qualifies

    with patch("src.main.search_flights", return_value=_offer(350)), patch("src.main.notify_all") as notify:
        check_one(search, store, results_store)

    notify.assert_called_once()
    assert store.get(search.id).last_notified_at is not None


def test_results_store_saves_empty_offers_when_none_found(tmp_path):
    store, results_store = _stores(tmp_path)
    search = _search()

    with patch("src.main.search_flights", return_value=[]), patch("src.main.notify_all"):
        check_one(search, store, results_store)

    results = results_store.get(search.id)
    assert results.checked_at is not None
    assert results.offers == []
