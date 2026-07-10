"""Unit tests for the as-of-week chat-analytics sanitizer in build_chat_context.py.

Synthetic fixtures only -- no file or network I/O.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_chat_context import _month_le  # noqa: E402
from build_chat_context import (
    PRESEASON_END_2025,
    PRESEASON_START_2025,
    build_sentiment_snapshot,
    build_suggested_callbacks,
    compute_preseason_window,
    find_active_arcs,
    get_all_player_names,
    get_all_team_names,
    get_matchup_roster_pairs,
    get_week_high_low_scorers,
    resolve_predictions,
    resolve_sender,
    sanitize_league_memory,
)

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

# Full 3-team league roster, used for preseason (week_data=None) fallback tests --
# roster_id 3 ("Charlie") deliberately has no matchup in WEEK_DATA above.
ROSTER_TO_TEAM = {1: "Alpha", 2: "Bravo", 3: "Charlie"}


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


def test_resolve_predictions_skips_predictions_made_after_cutoff():
    # made_at (UTC) is Nov 1, after the ~Oct-7 week-5 cutoff -> must be skipped.
    preds = [{"id": "p1", "made_at": "2025-11-01T00:00:00Z", "subject": "Alpha rolls"}]
    assert resolve_predictions(preds, 5, 2025, WEEK_DATA, CUTOFF) == []


def test_resolve_predictions_made_before_cutoff_resolves_without_baked_fields():
    wd = {
        "matchups": [
            {
                "team1": {
                    "team_name": "Alpha",
                    "points": 120,
                    "top_scorers": [{"name": "Mahomes", "points": 31.0}],
                },
                "team2": {"team_name": "Bravo", "points": 90, "top_scorers": []},
                "winner": "Alpha",
                "margin": 30,
            }
        ]
    }
    preds = [
        {
            "id": "p3",
            "made_at": "2025-09-15T00:00:00Z",
            "author_whatsapp": "Karim",
            "subject": "Mahomes is elite",
            "quote_block": [],
            "resolution": "wrong",
            "resolution_context": "leaked",
            "credibility_impact": -9,
        }
    ]
    out = resolve_predictions(preds, 5, 2025, wd, CUTOFF)
    assert len(out) == 1  # made before cutoff -> not filtered out
    assert out[0]["resolution"] == "right"  # recomputed locally (elite + 31 pts)
    assert "credibility_impact" not in out[0] and out[0].get("evidence")


def test_resolve_predictions_reads_subject_and_author_whatsapp():
    preds = [
        {
            "id": "pred-042",
            "author_whatsapp": "Karim",
            "subject": "Bijan Robinson is elite, top back this year",
            "quote_block": [{"sender": "Karim", "text": "book it", "timestamp": "x"}],
            "made_at": "2025-09-10T00:00:00Z",
            "resolution": "right",  # baked season-end value -- must be IGNORED
        }
    ]
    week_data = {
        "matchups": [
            {
                "team1": {
                    "team_name": "Chudders",
                    "points": 100,
                    "top_scorers": [{"name": "Bijan Robinson", "points": 28.4}],
                },
                "team2": {"team_name": "Kittler", "points": 90, "top_scorers": []},
                "winner": "Chudders",
            }
        ]
    }
    out = resolve_predictions(preds, 5, 2025, week_data, CUTOFF)
    assert len(out) == 1, "subject text names a 20+ pt scorer with a positive word"
    assert out[0]["author"] == "Karim"
    assert out[0]["prediction_id"] == "pred-042"
    assert "Bijan Robinson".lower() in out[0]["original_quote"].lower()


def test_sanitize_league_memory_drops_greatest_moments_and_meta():
    lm = {
        "meta": {"generated": "2026-02-26T00:00:00Z"},
        "culture": {"x": 1},
        "lexicon": {"y": 2},
        "greatest_moments": [{"rank": 1, "title": "leak"}],
        "running_jokes": [
            {
                "name": "old",
                "first_seen": "2025-09",
                "last_seen": "2026-02",
                "still_active": True,
            },
            {"name": "future", "first_seen": "2025-11", "last_seen": "2026-01"},
        ],
    }
    out = sanitize_league_memory(lm, CUTOFF)
    assert "greatest_moments" not in out and "meta" not in out
    assert out["culture"] == {"x": 1} and out["lexicon"] == {"y": 2}
    names = [j["name"] for j in out["running_jokes"]]
    assert "old" in names and "future" not in names
    old = next(j for j in out["running_jokes"] if j["name"] == "old")
    assert old["last_seen"] == "2025-10"  # clamped to cutoff month


def test_build_suggested_callbacks_excludes_future_arc():
    arcs = [{"arc_id": "f1", "title": "Alpha future", "span": {"start": "2025-11"}}]
    cbs = build_suggested_callbacks({}, arcs, {}, WEEK_DATA, {}, CUTOFF)
    assert all(c["source"] != "arc" for c in cbs)


def test_callbacks_league_memory_uses_running_jokes_with_cutoff():
    league_memory = {
        "running_jokes": [
            {
                "name": "Alpha tank jokes",
                "first_seen": "2025-09",
                "sample_block": "alpha lol",
            },
            {
                "name": "Future joke",
                "first_seen": "2025-12",
                "sample_block": "alpha again",
            },
        ]
    }
    out = build_suggested_callbacks(league_memory, None, None, WEEK_DATA, {}, CUTOFF)
    contents = [c["content"] for c in out if c["source"] == "league-memory"]
    assert "Alpha tank jokes" in contents, "in-window joke naming a playing team"
    assert "Future joke" not in contents, "first_seen after cutoff must be excluded"


def test_callbacks_prediction_branch_reads_subject():
    preds = [
        {
            "id": "pred-007",
            "author_whatsapp": "Oscar",
            "subject": "Alpha will miss the playoffs, book it",
            "quote_block": [],
            "made_at": "2025-09-10T00:00:00Z",
            "resolution": "pending",
        }
    ]
    out = build_suggested_callbacks(None, None, preds, WEEK_DATA, {}, CUTOFF)
    pred_cbs = [c for c in out if c["source"] == "prediction"]
    assert pred_cbs and "Alpha" in pred_cbs[0]["content"]


# ---------------------------------------------------------------------------
# Preseason mode (week_data=None) -- null-guards and graceful degrades
# ---------------------------------------------------------------------------


def test_compute_preseason_window_2025_matches_constants():
    assert compute_preseason_window(2025) == (PRESEASON_START_2025, PRESEASON_END_2025)


def test_get_matchup_roster_pairs_none_week_data_returns_empty():
    assert get_matchup_roster_pairs(None) == []


def test_get_week_high_low_scorers_none_week_data_returns_none_none():
    assert get_week_high_low_scorers(None) == (None, None)


def test_get_all_player_names_none_week_data_returns_empty_set():
    assert get_all_player_names(None) == set()


def test_get_all_team_names_none_week_data_falls_back_to_roster():
    assert get_all_team_names(None, ROSTER_TO_TEAM) == {"alpha", "bravo", "charlie"}


def test_get_all_team_names_none_week_data_no_roster_returns_empty():
    assert get_all_team_names(None) == set()


def test_get_all_team_names_with_week_data_ignores_roster_fallback():
    # Regression: real week_data takes precedence, new param doesn't change it.
    assert get_all_team_names(WEEK_DATA, ROSTER_TO_TEAM) == {"alpha", "bravo"}


def test_find_active_arcs_preseason_full_roster_in_scope():
    # roster_id 3 has no matchup anywhere -- only reachable via the full-roster
    # fallback that preseason mode (week_data=None) is supposed to provide.
    arcs = [
        {
            "arc_id": "p1",
            "title": "Preseason arc",
            "span": {"start": "2025-03"},
            "participants": [3],
        }
    ]
    out = find_active_arcs(arcs, 0, 2025, None, ROSTER_TO_TEAM, PRESEASON_END_2025)
    assert len(out) == 1
    assert out[0]["this_week_development"] == "Entering the 2025 season"


def test_find_active_arcs_preseason_excludes_future_start():
    arcs = [
        {
            "arc_id": "p2",
            "title": "Late",
            "span": {"start": "2025-10"},
            "participants": [1],
        }
    ]
    assert (
        find_active_arcs(arcs, 0, 2025, None, ROSTER_TO_TEAM, PRESEASON_END_2025) == []
    )


def test_resolve_predictions_none_week_data_returns_empty():
    preds = [
        {"id": "p1", "made_at": "2025-03-01T00:00:00Z", "quote": "Mahomes is elite"}
    ]
    assert resolve_predictions(preds, 0, 2025, None, PRESEASON_END_2025) == []


def test_build_sentiment_snapshot_none_week_data_still_computes_mood():
    messages = [
        {
            "sender": "Alice",
            "text": "lol let's go fire dub",
            "timestamp_utc": "2025-03-01T00:00:00Z",
        },
    ]
    name_to_roster = {"alice": 1}
    out = build_sentiment_snapshot(messages, name_to_roster, ROSTER_TO_TEAM, None)
    assert out["Alpha"]["mood"] == "hyped"
    assert out["Alpha"]["activity"] == "low"


def test_build_suggested_callbacks_none_week_data_uses_roster_fallback():
    arcs = [{"arc_id": "a1", "title": "Alpha saga", "span": {"start": "2025-03"}}]
    cbs = build_suggested_callbacks(
        {}, arcs, {}, None, ROSTER_TO_TEAM, PRESEASON_END_2025
    )
    assert any(c["source"] == "arc" for c in cbs)


def test_find_active_arcs_resolves_string_participants():
    # arcs.json participants are WhatsApp display names; they must resolve
    # via name_to_roster or every arc is silently dropped (the shipped bug).
    arcs = [
        {
            "title": "Trade activity surge",
            "span": {"start": "2025-09"},
            "participants": ["Brent Boone"],
        }
    ]
    week_data = {
        "matchups": [
            {"team1": {"roster_id": 3}, "team2": {"roster_id": 7}},
        ]
    }
    out = find_active_arcs(
        arcs, 5, 2025, week_data, {}, CUTOFF, name_to_roster={"brent boone": 3}
    )
    assert len(out) == 1, "string participant should resolve to roster 3 (playing)"


def test_find_active_arcs_string_participants_without_map_still_drop():
    arcs = [
        {"title": "x", "span": {"start": "2025-09"}, "participants": ["Brent Boone"]}
    ]
    week_data = {"matchups": [{"team1": {"roster_id": 3}, "team2": {"roster_id": 7}}]}
    assert find_active_arcs(arcs, 5, 2025, week_data, {}, CUTOFF) == []


def test_resolve_sender_none_sender_returns_none_pair():
    # system messages and parser mis-splits carry sender=None; the corpus has
    # two inside the preseason window (2025-04-18, 2025-07-11)
    assert resolve_sender(None, {"brent boone": 3}, {3: "Chudders"}) == (None, None)


def test_resolve_sender_empty_sender_returns_none_pair():
    assert resolve_sender("", {"brent boone": 3}, {3: "Chudders"}) == (None, None)
