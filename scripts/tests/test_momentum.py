"""Unit tests for compute_momentum in shared.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import compute_momentum


def make_prev_week(week, standings):
    """Helper: build a minimal prev_weeks entry. `standings` is a list of
    dicts with roster_id, rank, margin_this_week, streak."""
    return {
        "meta": {"week": week},
        "standings": standings,
    }


def test_week1_returns_opening_sentinel():
    result = compute_momentum(prev_weeks=[], rid=1, current_week=1)
    assert result["label"] == "opening"
    assert result["score"] == 0


def test_surging_team_3wins_climbing_high_margin():
    # Team 1: won 3 straight, avg margin +20, climbed from rank 8 to rank 3
    prev_weeks = [
        make_prev_week(
            1, [{"roster_id": 1, "rank": 8, "margin_this_week": 10, "streak": "W1"}]
        ),
        make_prev_week(
            2, [{"roster_id": 1, "rank": 5, "margin_this_week": 25, "streak": "W2"}]
        ),
        make_prev_week(
            3, [{"roster_id": 1, "rank": 3, "margin_this_week": 25, "streak": "W3"}]
        ),
    ]
    result = compute_momentum(prev_weeks, rid=1, current_week=4)
    assert result["label"] in ("surging", "hot"), f"expected surging/hot, got {result}"
    assert result["score"] > 1.5


def test_collapsing_team_3losses_dropping():
    prev_weeks = [
        make_prev_week(
            1, [{"roster_id": 2, "rank": 3, "margin_this_week": -5, "streak": "L1"}]
        ),
        make_prev_week(
            2, [{"roster_id": 2, "rank": 5, "margin_this_week": -25, "streak": "L2"}]
        ),
        make_prev_week(
            3, [{"roster_id": 2, "rank": 9, "margin_this_week": -30, "streak": "L3"}]
        ),
    ]
    result = compute_momentum(prev_weeks, rid=2, current_week=4)
    assert result["label"] in (
        "cooling",
        "collapsing",
    ), f"expected cooling/collapsing, got {result}"
    assert result["score"] < -1.5


def test_steady_team_mixed_results():
    prev_weeks = [
        make_prev_week(
            1, [{"roster_id": 3, "rank": 6, "margin_this_week": 5, "streak": "W1"}]
        ),
        make_prev_week(
            2, [{"roster_id": 3, "rank": 7, "margin_this_week": -10, "streak": "L1"}]
        ),
        make_prev_week(
            3, [{"roster_id": 3, "rank": 6, "margin_this_week": 8, "streak": "W1"}]
        ),
    ]
    result = compute_momentum(prev_weeks, rid=3, current_week=4)
    assert result["label"] == "steady"
    assert -0.5 <= result["score"] <= 0.5


def test_score_clamped_to_bounds():
    # Extreme inputs should clamp to [-3, +3]
    prev_weeks = [
        make_prev_week(
            w,
            [{"roster_id": 4, "rank": 12, "margin_this_week": 100, "streak": f"W{w}"}],
        )
        for w in range(1, 5)
    ]
    result = compute_momentum(prev_weeks, rid=4, current_week=5)
    assert -3 <= result["score"] <= 3


def test_missing_team_returns_opening():
    # roster_id not found in any prev_week
    prev_weeks = [
        make_prev_week(
            1, [{"roster_id": 99, "rank": 1, "margin_this_week": 0, "streak": "W1"}]
        ),
    ]
    result = compute_momentum(prev_weeks, rid=1, current_week=2)
    assert result["label"] == "opening"
