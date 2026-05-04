"""Tests for verify_week_content.py — Tier 1 game_context validation.

Architect I3: schema is single source of truth for game_context shape.
These tests lock the I3 contract — a future refactor that drops the
schema call (e.g. "this seems redundant") will fail these tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from verify_week_content import check_game_context_presence  # noqa: E402


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
