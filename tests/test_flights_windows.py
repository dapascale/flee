from src.config import DateWindow, SavedSearch
from src.flights import _expand_date_windows, _parse_departure_hour, _parse_duration_minutes


def _base(**overrides):
    defaults = dict(id="s1", label="test", origin="JFK", destination="MCO")
    defaults.update(overrides)
    return SavedSearch(**defaults)


def test_expand_fixed_date_round_trip():
    s = _base(depart_date="2026-12-01", return_date="2026-12-08")
    assert _expand_date_windows(s) == [("2026-12-01", "2026-12-08")]


def test_expand_windows_round_trip_computes_return_date():
    s = _base(
        depart_date=None,
        return_date=None,
        date_windows=[
            DateWindow(start="2026-12-01", trip_length_days=5),
            DateWindow(start="2026-12-15", trip_length_days=7),
        ],
    )
    assert _expand_date_windows(s) == [
        ("2026-12-01", "2026-12-06"),
        ("2026-12-15", "2026-12-22"),
    ]


def test_expand_windows_one_way_has_no_return_date():
    s = _base(
        depart_date=None,
        return_date=None,
        trip_type="one-way",
        date_windows=[DateWindow(start="2026-12-01")],
    )
    assert _expand_date_windows(s) == [("2026-12-01", None)]


def test_parse_duration_minutes():
    assert _parse_duration_minutes("5 hr 30 min") == 330
    assert _parse_duration_minutes("45 min") == 45
    assert _parse_duration_minutes("") is None


def test_parse_departure_hour():
    assert _parse_departure_hour("10:30 AM") == 10
    assert _parse_departure_hour("12:05 AM") == 0
    assert _parse_departure_hour("1:15 PM") == 13
    assert _parse_departure_hour("12:00 PM") == 12
    assert _parse_departure_hour("") is None
