"""Tests for verify_week_content.py — Tier 1 game_context validation.

Architect I3: schema is single source of truth for game_context shape.
These tests lock the I3 contract — a future refactor that drops the
schema call (e.g. "this seems redundant") will fail these tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from verify_week_content import _check_thread_shape  # noqa: E402
from verify_week_content import check_game_context_presence  # noqa: E402
from verify_week_content import _diff_thread_continuity, run_tier1


def test_check_game_context_rejects_bogus_src_enum():
    """Architect I3: bogus src enum value caught by schema, not hand-rolled set."""
    errors: list[str] = []
    data = {
        "matchups": [
            {
                "matchup_id": 1,
                "team1": {
                    "top_scorers": [
                        {
                            "name": "TestPlayer",
                            "position": "QB",
                            "game_context": {
                                "game_id": "2025_06_BUF_NYJ",
                                "src": {"game_id": "BOGUS_SOURCE"},
                            },
                        }
                    ]
                },
                "team2": {"top_scorers": []},
            }
        ],
        "awards": {},
    }
    check_game_context_presence({}, data, errors)
    assert any(
        "BOGUS_SOURCE" in e or "is not one of" in e for e in errors
    ), f"Expected schema error for bogus src enum, got: {errors}"


def test_check_game_context_null_game_id_requires_status():
    """Semantic rule: null game_id allowed only with explanatory status."""
    # Case A: null game_id WITHOUT explanatory status -> error
    errors_a: list[str] = []
    data_a = {
        "matchups": [
            {
                "matchup_id": 1,
                "team1": {
                    "top_scorers": [
                        {
                            "name": "TestPlayer",
                            "position": "QB",
                            "game_context": {
                                "game_id": None,
                                "src": {"game_id": None},
                            },
                            # status field not present -> should error
                        }
                    ]
                },
                "team2": {"top_scorers": []},
            }
        ],
        "awards": {},
    }
    check_game_context_presence({}, data_a, errors_a)
    assert any(
        "game_id is null" in e or "without explanatory status" in e for e in errors_a
    ), f"Expected null-without-status error, got: {errors_a}"

    # Case B: null game_id WITH bye_week status -> no error from this rule
    errors_b: list[str] = []
    data_b = {
        "matchups": [
            {
                "matchup_id": 1,
                "team1": {
                    "top_scorers": [
                        {
                            "name": "TestPlayer",
                            "position": "QB",
                            "status": "bye_week",
                            "game_context": {
                                "game_id": None,
                                "src": {"game_id": None},
                            },
                        }
                    ]
                },
                "team2": {"top_scorers": []},
            }
        ],
        "awards": {},
    }
    check_game_context_presence({}, data_b, errors_b)
    # Should NOT have the null-without-status error (other errors OK)
    assert not any(
        "game_id is null" in e and "without explanatory status" in e for e in errors_b
    ), f"bye_week status should suppress null-game_id error, got: {errors_b}"


def test_check_game_context_awards_top_performer_validated():
    """awards.top_performer.game_context goes through the same schema check."""
    errors: list[str] = []
    data = {
        "matchups": [],
        "awards": {
            "top_performer": {
                "name": "TopGuy",
                "position": "RB",
                "game_context": {
                    "game_id": "2025_06_BUF_NYJ",
                    "src": {"game_id": "BOGUS_AWARDS_SOURCE"},
                },
            }
        },
    }
    check_game_context_presence({}, data, errors)
    assert any(
        "BOGUS_AWARDS_SOURCE" in e or "is not one of" in e for e in errors
    ), f"awards.top_performer should be schema-validated, got errors: {errors}"


# ---------------------------------------------------------------------------
# Threads ledger (meta.threads) -- M1 t4
# ---------------------------------------------------------------------------


def test_check_thread_shape_valid_no_errors():
    threads = [
        {"id": "a", "status": "opened"},
        {"id": "b", "status": "continued"},
    ]
    errors: list[str] = []
    _check_thread_shape(threads, errors)
    assert errors == []


def test_check_thread_shape_invalid_status():
    threads = [{"id": "a", "status": "bogus"}]
    errors: list[str] = []
    _check_thread_shape(threads, errors)
    assert len(errors) == 1
    assert "bogus" in errors[0]


def test_check_thread_shape_duplicate_id():
    threads = [
        {"id": "a", "status": "opened"},
        {"id": "a", "status": "continued"},
    ]
    errors: list[str] = []
    _check_thread_shape(threads, errors)
    assert any("Duplicate" in e and "'a'" in e for e in errors)


def test_diff_thread_continuity_carried_forward_no_warning():
    prev = [{"id": "a", "status": "opened"}]
    current = [{"id": "a", "status": "continued"}]
    warnings: list[str] = []
    _diff_thread_continuity(current, prev, "week 1", warnings)
    assert warnings == []


def test_diff_thread_continuity_silently_dropped_warns():
    prev = [{"id": "a", "status": "opened"}]
    current: list[dict] = []
    warnings: list[str] = []
    _diff_thread_continuity(current, prev, "week 1", warnings)
    assert len(warnings) == 1
    assert "'a'" in warnings[0] and "week 1" in warnings[0]


def test_diff_thread_continuity_terminal_status_not_flagged():
    # A thread already paid_off/dropped in the predecessor is closed --
    # its absence from the current week is expected, not a silent drop.
    prev = [
        {"id": "a", "status": "paid_off"},
        {"id": "b", "status": "dropped"},
    ]
    current: list[dict] = []
    warnings: list[str] = []
    _diff_thread_continuity(current, prev, "week 1", warnings)
    assert warnings == []


def test_run_tier1_returns_warnings_key():
    # Minimal content/data -- most of the other 10 checks legitimately fail
    # against empty input; that's expected and irrelevant here. This test
    # only locks the new warnings-channel shape and the updated tally.
    result = run_tier1({}, {})
    assert "warnings" in result and isinstance(result["warnings"], list)
    assert "errors" in result and isinstance(result["errors"], list)
    assert (
        result["passed"] + result["failed"] == 12
    )  # 10 existing + threads_continuity + rankings_order


# ---------------------------------------------------------------------------
# check_rankings_order — published order owned by exactly one authority
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from verify_week_content import check_rankings_order  # noqa: E402

_REPO = _Path(__file__).resolve().parents[2]
_ARITHMETIC_SRC = "content/editions/2025-wk01-recap/ranking_record.json"


def _order_fixture(order, src=None):
    content = {
        "meta": ({"ranking_source": src} if src else {}),
        "rankings": [{"rank": i + 1, "team_name": t} for i, t in enumerate(order)],
    }
    data = {
        "standings": [
            {"rank": i + 1, "team_name": t}
            for i, t in enumerate(["Alpha", "Beta", "Gamma"])
        ]
    }
    return content, data


def test_no_ranking_source_enforces_standings_order():
    content, data = _order_fixture(["Beta", "Alpha", "Gamma"])
    errors = []
    check_rankings_order(content, data, errors)
    assert errors and "standings order" in errors[0]


def test_no_ranking_source_passes_when_order_matches_standings():
    content, data = _order_fixture(["Alpha", "Beta", "Gamma"])
    errors = []
    check_rankings_order(content, data, errors)
    assert errors == []


def test_missing_ranking_source_file_fails_closed():
    content, data = _order_fixture(["Alpha"], src="content/nope/missing.json")
    errors = []
    check_rankings_order(content, data, errors)
    assert errors and "does not exist" in errors[0]


def test_escaping_ranking_source_fails_closed():
    content, data = _order_fixture(["Alpha"], src="../outside.json")
    errors = []
    check_rankings_order(content, data, errors)
    assert errors and "escapes the repository root" in errors[0]


def test_malformed_ranking_source_fails_closed(tmp_path):
    bad = _REPO / "content" / "weeks" / "_malformed_test_record.json"
    bad.write_text("{not json", encoding="utf-8")
    try:
        content, data = _order_fixture(
            ["Alpha"], src="content/weeks/_malformed_test_record.json"
        )
        errors = []
        check_rankings_order(content, data, errors)
        assert errors and "unreadable/malformed" in errors[0]
    finally:
        bad.unlink()


def test_red_ranking_source_fails_closed():
    """Pointing the column at the arithmetic record must fail: that record is
    RED at the judgment gate by design."""
    content, data = _order_fixture(["Alpha"], src=_ARITHMETIC_SRC)
    errors = []
    check_rankings_order(content, data, errors)
    assert errors and "RED" in errors[0]


def _with_green_gate(monkeypatch, record):
    """Point a ranking_source at a real temp file and force the gate GREEN, so
    the order-comparison stage is exercised in isolation."""
    import verify_ranking_judgment as vrj

    monkeypatch.setattr(vrj, "run_gate", lambda rec: (True, []))
    tmp = _REPO / "content" / "weeks" / "_order_test_record.json"
    tmp.write_text(_json.dumps(record), encoding="utf-8")
    return "content/weeks/_order_test_record.json", tmp


def _mini_record():
    names = ["Alpha", "Beta", "Gamma"]
    return {
        "positions": [
            {"rank": i + 1, "roster_id": str(i + 1), "team_name": t}
            for i, t in enumerate(names)
        ]
    }


def test_reversed_published_order_fails_against_green_record(monkeypatch):
    src, tmp = _with_green_gate(monkeypatch, _mini_record())
    try:
        content = {
            "meta": {"ranking_source": src},
            "rankings": [
                {"rank": i + 1, "team_name": t}
                for i, t in enumerate(["Gamma", "Beta", "Alpha"])
            ],
        }
        errors = []
        check_rankings_order(content, {"standings": []}, errors)
        assert errors and "gate-passed judgment record" in errors[0]
    finally:
        tmp.unlink()


def test_matching_published_order_passes_against_green_record(monkeypatch):
    src, tmp = _with_green_gate(monkeypatch, _mini_record())
    try:
        content = {
            "meta": {"ranking_source": src},
            "rankings": [
                {"rank": i + 1, "team_name": t}
                for i, t in enumerate(["Alpha", "Beta", "Gamma"])
            ],
        }
        errors = []
        check_rankings_order(content, {"standings": []}, errors)
        assert errors == []
    finally:
        tmp.unlink()
