"""Unit tests for the as-of-week chat-analytics sanitizer in build_chat_context.py.

Synthetic fixtures only -- no file or network I/O.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_chat_context import _month_le  # noqa: E402

# ~ Tuesday after Week 5 MNF, 2025 (early October).
CUTOFF = datetime(2025, 10, 7, 6, 59, 59, tzinfo=timezone.utc)


def test_month_le_before_and_at_cutoff_true():
    assert _month_le("2025-09", CUTOFF) is True
    assert _month_le("2025-10", CUTOFF) is True


def test_month_le_after_cutoff_false():
    assert _month_le("2025-11", CUTOFF) is False
    assert _month_le("2026-02", CUTOFF) is False


def test_month_le_none_is_true():
    # Missing date == not future; treat as visible (callers decide inclusion).
    assert _month_le(None, CUTOFF) is True


from build_chat_context import find_active_arcs  # noqa: E402

WEEK_DATA = {
    "matchups": [
        {
            "team1": {"roster_id": 1, "team_name": "Alpha", "points": 100},
            "team2": {"roster_id": 2, "team_name": "Bravo", "points": 90},
            "winner": "Alpha",
            "margin": 10,
        }
    ]
}


def test_find_active_arcs_includes_arc_that_resolves_later():
    # Started in Sep, "resolved" in Dec (future) -> live as of wk5, MUST appear.
    arcs = [
        {
            "arc_id": "a1",
            "title": "Saga",
            "status": "resolved",
            "span": {"start": "2025-09", "end": "2025-12"},
            "participants": [1],
        }
    ]
    out = find_active_arcs(arcs, 5, 2025, WEEK_DATA, {}, CUTOFF)
    assert len(out) == 1
    assert out[0]["status"] == "active"  # NOT the baked "resolved"


def test_find_active_arcs_excludes_future_start():
    arcs = [
        {
            "arc_id": "a2",
            "title": "Late",
            "status": "building",
            "span": {"start": "2025-11"},
            "participants": [1],
        }
    ]
    assert find_active_arcs(arcs, 5, 2025, WEEK_DATA, {}, CUTOFF) == []


def test_find_active_arcs_marks_resolved_when_ended_before_cutoff():
    arcs = [
        {
            "arc_id": "a3",
            "title": "Done",
            "status": "resolved",
            "span": {"start": "2025-09", "end": "2025-09"},
            "participants": [1],
        }
    ]
    out = find_active_arcs(arcs, 5, 2025, WEEK_DATA, {}, CUTOFF)
    assert out and out[0]["status"] == "resolved"
