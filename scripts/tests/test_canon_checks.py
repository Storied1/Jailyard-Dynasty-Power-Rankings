from scripts.canon_checks import (
    check_arc_and_joke_semantics,
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


# ---------------------------------------------------------------------------
# Semantic validation of the enriched recompute schema (Phase 1f)
# ---------------------------------------------------------------------------


def _ctx(arcs=None, jokes=None):
    return {
        "meta": {"temporal_cutoff_utc": "2025-10-07T06:59:59Z"},
        "active_arcs_this_week": arcs or [],
        "league_memory": {"running_jokes": jokes or []},
    }


def _valid_arc(gid="trade_saga::A|B"):
    return {
        "arc_group_id": gid,
        "count": 3,
        "first_seen_at": "2025-09-10T10:00:00Z",
        "last_observed_at": "2025-09-20T10:00:00Z",
    }


def test_arc_joke_semantics_pass():
    errors = []
    joke = {
        "name": "taco",
        "count": 5,
        "first_seen_at": "2025-09-01T10:00:00Z",
        "last_observed_at": "2025-10-01T10:00:00Z",
    }
    check_arc_and_joke_semantics(_ctx(arcs=[_valid_arc()], jokes=[joke]), errors)
    assert errors == []


def test_arc_joke_semantics_count_bool_rejected():
    errors = []
    a = _valid_arc()
    a["count"] = True  # bool is a subclass of int -- must be rejected
    check_arc_and_joke_semantics(_ctx(arcs=[a]), errors)
    assert any("non-boolean int" in e for e in errors)


def test_arc_joke_semantics_count_zero_rejected():
    errors = []
    a = _valid_arc()
    a["count"] = 0
    check_arc_and_joke_semantics(_ctx(arcs=[a]), errors)
    assert any("positive" in e for e in errors)


def test_arc_joke_semantics_past_cutoff_last_observed_is_leak():
    errors = []
    a = _valid_arc()
    a["last_observed_at"] = "2025-12-01T10:00:00Z"  # after the cutoff
    check_arc_and_joke_semantics(_ctx(arcs=[a]), errors)
    assert any("last_observed_at" in e and "leak" in e for e in errors)


def test_arc_joke_semantics_coarse_bound_rejected():
    errors = []
    a = _valid_arc()
    a["first_seen_at"] = "2025-09"  # month-only -> not an exact instant
    check_arc_and_joke_semantics(_ctx(arcs=[a]), errors)
    assert any("first_seen_at" in e for e in errors)


def test_arc_joke_semantics_bounds_out_of_order():
    errors = []
    a = _valid_arc()
    a["first_seen_at"] = "2025-09-20T10:00:00Z"
    a["last_observed_at"] = "2025-09-10T10:00:00Z"
    check_arc_and_joke_semantics(_ctx(arcs=[a]), errors)
    assert any("after last_observed_at" in e for e in errors)


def test_arc_joke_semantics_arc_group_id_not_unique():
    errors = []
    check_arc_and_joke_semantics(
        _ctx(arcs=[_valid_arc("dup"), _valid_arc("dup")]), errors
    )
    assert any("not unique" in e for e in errors)


def test_arc_joke_semantics_missing_cutoff_fails_closed():
    errors = []
    ctx = {
        "active_arcs_this_week": [_valid_arc()],
        "league_memory": {"running_jokes": []},
    }  # no meta.temporal_cutoff_utc
    check_arc_and_joke_semantics(ctx, errors)
    assert any("temporal_cutoff_utc" in e for e in errors)


def test_arc_joke_semantics_malformed_cutoff_catches_future_bound():
    # A broken cutoff must NOT let a 2099 bound pass -- previously
    # admissible(bound, None) admitted everything.
    errors = []
    a = _valid_arc()
    a["last_observed_at"] = "2099-01-01T00:00:00Z"
    ctx = {
        "meta": {"temporal_cutoff_utc": "garbage"},
        "active_arcs_this_week": [a],
        "league_memory": {"running_jokes": []},
    }
    check_arc_and_joke_semantics(ctx, errors)
    assert any("temporal_cutoff_utc" in e for e in errors)


def test_arc_joke_semantics_coarse_cutoff_rejected():
    for bad in ("2025-10", "2025-10-07", "2025-10-07T06:59:59"):  # month/date/naive
        errors = []
        ctx = {
            "meta": {"temporal_cutoff_utc": bad},
            "active_arcs_this_week": [_valid_arc()],
            "league_memory": {"running_jokes": []},
        }
        check_arc_and_joke_semantics(ctx, errors)
        assert any("temporal_cutoff_utc" in e for e in errors), bad


def test_arc_joke_semantics_empty_or_null_gid_rejected():
    for bad_gid in ("", None):
        errors = []
        a = _valid_arc()
        a["arc_group_id"] = bad_gid
        check_arc_and_joke_semantics(_ctx(arcs=[a]), errors)
        assert any("nonempty string" in e for e in errors), repr(bad_gid)
