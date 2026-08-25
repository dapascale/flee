import pytest

from src.config import DateWindow, SavedSearch


def _base(**overrides):
    defaults = dict(
        id="s1",
        label="test",
        origin="JFK",
        destination="MCO",
        depart_date="2026-12-01",
        return_date="2026-12-08",
    )
    defaults.update(overrides)
    return SavedSearch(**defaults)


def test_fixed_date_search_is_valid():
    s = _base()
    assert s.depart_date == "2026-12-01"


def test_round_trip_without_return_date_rejected():
    with pytest.raises(ValueError, match="return_date"):
        _base(return_date=None)


def test_date_windows_and_fixed_date_mutually_exclusive():
    with pytest.raises(ValueError, match="exactly one"):
        _base(date_windows=[DateWindow(start="2026-12-01", trip_length_days=5)])


def test_neither_fixed_date_nor_windows_rejected():
    with pytest.raises(ValueError, match="exactly one"):
        _base(depart_date=None, return_date=None)


def test_date_windows_valid():
    s = _base(
        depart_date=None,
        return_date=None,
        date_windows=[
            DateWindow(start="2026-12-01", trip_length_days=5),
            DateWindow(start="2026-12-15", trip_length_days=5),
        ],
    )
    assert len(s.date_windows) == 2


def test_too_many_date_windows_rejected():
    windows = [
        DateWindow(start="2026-12-01", trip_length_days=5)
        for _ in range(5)
    ]
    with pytest.raises(ValueError, match="1-4 entries"):
        _base(depart_date=None, return_date=None, date_windows=windows)


def test_empty_date_windows_rejected():
    with pytest.raises(ValueError, match="1-4 entries"):
        _base(depart_date=None, return_date=None, date_windows=[])


def test_round_trip_date_window_needs_trip_length():
    with pytest.raises(ValueError, match="trip_length_days"):
        _base(
            depart_date=None,
            return_date=None,
            date_windows=[DateWindow(start="2026-12-01")],
        )


def test_one_way_date_window_does_not_need_trip_length():
    s = _base(
        depart_date=None,
        return_date=None,
        trip_type="one-way",
        date_windows=[DateWindow(start="2026-12-01")],
    )
    assert s.date_windows[0].trip_length_days is None
