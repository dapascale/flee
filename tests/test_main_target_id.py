import json
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


def test_target_search_id_runs_even_if_inactive(tmp_path, monkeypatch):
    config_path = tmp_path / "searches.json"
    _write_searches(config_path, [_search(id="s1", active=False)])

    monkeypatch.setattr(main_module, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(main_module, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(main_module, "TARGET_SEARCH_ID", "s1")

    with patch.object(main_module, "check_one") as check_one:
        exit_code = main_module.main()

    check_one.assert_called_once()
    assert exit_code == 0


def test_target_search_id_not_found_fails(tmp_path, monkeypatch):
    config_path = tmp_path / "searches.json"
    _write_searches(config_path, [_search(id="s1", active=True)])

    monkeypatch.setattr(main_module, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(main_module, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(main_module, "TARGET_SEARCH_ID", "does-not-exist")

    with patch.object(main_module, "check_one") as check_one:
        exit_code = main_module.main()

    check_one.assert_not_called()
    assert exit_code == 1


def test_no_target_id_skips_inactive_searches(tmp_path, monkeypatch):
    config_path = tmp_path / "searches.json"
    _write_searches(
        config_path, [_search(id="active-one", active=True), _search(id="inactive-one", active=False)]
    )

    monkeypatch.setattr(main_module, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(main_module, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(main_module, "TARGET_SEARCH_ID", None)

    with patch.object(main_module, "check_one") as check_one:
        main_module.main()

    assert check_one.call_count == 1
