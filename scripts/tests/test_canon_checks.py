from scripts.canon_checks import (
    check_as_of_week_fields,
    check_league_memory_present,
    check_preseason_type_marker,
)


def test_league_memory_present_pass():
    errors = []
    check_league_memory_present(
        {"league_memory": {"culture": {}, "lexicon": {}, "running_jokes": {}}}, errors
    )
    assert errors == []


def test_league_memory_present_missing_key():
    errors = []
    check_league_memory_present({}, errors)
    assert len(errors) == 1
    assert "league_memory" in errors[0]


def test_as_of_week_fields_pass():
    errors = []
    entry = {
        "team_name": "Test",
        "current_elo": 1500,
        "peak_elo": 1500,
        "all_time_record": "0-0",
    }
    check_as_of_week_fields(entry, errors)
    assert errors == []


def test_as_of_week_fields_missing():
    errors = []
    check_as_of_week_fields({"team_name": "Test"}, errors)
    assert len(errors) == 3


def test_as_of_week_fields_season_end_leak():
    errors = []
    entry = {
        "team_name": "Test",
        "current_elo": 1500,
        "peak_elo": 1500,
        "all_time_record": "0-0",
        "championships": 1,
    }
    check_as_of_week_fields(entry, errors)
    assert len(errors) == 1
    assert "championships" in errors[0]


def test_preseason_type_marker_pass():
    errors = []
    check_preseason_type_marker({"meta": {"type": "preseason"}}, errors)
    assert errors == []


def test_preseason_type_marker_wrong_type():
    errors = []
    check_preseason_type_marker({"meta": {"type": "week"}}, errors)
    assert len(errors) == 1
    assert "meta.type" in errors[0]


def test_preseason_type_marker_missing_meta():
    errors = []
    check_preseason_type_marker({}, errors)
    assert len(errors) == 1
