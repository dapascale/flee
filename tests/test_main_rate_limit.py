import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src import main as main_module


def _write_searches(path, searches):
    path.write_text(json.dumps(searches))


def _search(id="s1", active=True):
    return {
        "id": id,
        "label": "test",
        "origin": "JFK",
        "destination": "MCO",
        "depart_date": "2026-12-01",
        "return_date": "2026-12-08",
        "active": active,
        "channels": [],
    }


def _write_state(path, search_id, last_checked_at):
    path.write_text(json.dumps({search_id: {"last_checked_at": last_checked_at}}))


def _setup(tmp_path, monkeypatch, min_seconds=3 * 3600):
    config_path = tmp_path / "searches.json"
    _write_searches(config_path, [_search(id="s1", active=True)])
    monkeypatch.setattr(main_module, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(main_module, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(main_module, "TARGET_SEARCH_ID", None)
    monkeypatch.setattr(main_module, "MIN_SECONDS_BETWEEN_SWEEPS", min_seconds)
    return tmp_path / "state.json"


def test_sweep_skipped_if_last_check_too_recent(tmp_path, monkeypatch):
    state_path = _setup(tmp_path, monkeypatch)
    recent = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    _write_state(state_path, "s1", recent)

    with patch.object(main_module, "check_one") as check_one:
        exit_code = main_module.main()

    check_one.assert_not_called()
    assert exit_code == 0


def test_sweep_runs_if_last_check_old_enough(tmp_path, monkeypatch):
    state_path = _setup(tmp_path, monkeypatch)
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    _write_state(state_path, "s1", old)

    with patch.object(main_module, "check_one") as check_one:
        main_module.main()

    check_one.assert_called_once()


def test_sweep_runs_if_never_checked_before(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)  # no state.json written at all

    with patch.object(main_module, "check_one") as check_one:
        main_module.main()

    check_one.assert_called_once()


def test_target_search_id_bypasses_rate_limit(tmp_path, monkeypatch):
    state_path = _setup(tmp_path, monkeypatch)
    recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    _write_state(state_path, "s1", recent)
    monkeypatch.setattr(main_module, "TARGET_SEARCH_ID", "s1")

    with patch.object(main_module, "check_one") as check_one:
        main_module.main()

    check_one.assert_called_once()
