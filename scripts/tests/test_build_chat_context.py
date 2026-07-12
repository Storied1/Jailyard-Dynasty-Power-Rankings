"""Unit tests for build_chat_context.py after the recompute-as-producer rewrite.

Synthetic fixtures only -- no file or network I/O. Arcs + jokes are now
RECOMPUTED from raw messages at the exact cutoff (recompute_projection), so the
month-grained `_month_le` gate is gone; find_active_arcs / sanitize_league_memory
/ build_suggested_callbacks consume the enriched, already-gated projection
(arc_group_id / count / first_seen_at / last_observed_at, NO status).
"""

import builtins
import copy
import inspect
import pathlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_chat_context as bcc  # noqa: E402
from build_chat_context import PRESEASON_END_2025  # noqa: E402
from build_chat_context import (
    PRESEASON_START_2025,
    _member_messages,
    build_context_dict,
    build_sentiment_snapshot,
    build_suggested_callbacks,
    compute_preseason_window,
    extract_chat_highlights,
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


def _proj_arc(participants, count=3, group=None, title="Trade activity surge"):
    """A minimal recompute-shaped arc (the producer output find_active_arcs and
    build_suggested_callbacks now consume)."""
    return {
        "arc_group_id": group or ("trade_saga::" + "|".join(sorted(participants))),
        "title": title,
        "type": "trade_saga",
        "participants": list(participants),
        "count": count,
        "first_seen_at": "2025-09-10T10:00:00Z",
        "last_observed_at": "2025-09-20T10:00:00Z",
    }


# ---------------------------------------------------------------------------
# find_active_arcs -- recompute arcs, enriched schema, no status/_month_le
# ---------------------------------------------------------------------------


def test_find_active_arcs_surfaces_enriched_schema_no_status():
    arcs = [_proj_arc(["Brent Boone"], count=4)]
    arcs[0]["last_observed_at"] = "2025-10-01T12:00:00Z"
    out = find_active_arcs(arcs, 2025, WEEK_DATA, {}, {"brent boone": 1})
    assert len(out) == 1
    a = out[0]
    assert a["arc_group_id"] == "trade_saga::Brent Boone"
    assert a["count"] == 4
    assert a["first_seen_at"] == "2025-09-10T10:00:00Z"
    assert a["last_observed_at"] == "2025-10-01T12:00:00Z"
    assert a["this_week_development"] == "Alpha won by 10"
    assert "status" not in a  # status removed (bounds carry recency)
    assert "arc_id" not in a  # only the non-lossy arc_group_id is surfaced


def test_find_active_arcs_drops_count_zero():
    # Fail-closed: no admissible evidence through the cutoff -> not surfaced.
    arcs = [_proj_arc(["Brent Boone"], count=0)]
    assert find_active_arcs(arcs, 2025, WEEK_DATA, {}, {"brent boone": 1}) == []


def test_find_active_arcs_excludes_participant_not_playing():
    # Participant resolves, but their roster is not in this week's slate.
    arcs = [_proj_arc(["Brent Boone"], count=3)]
    week_data = {"matchups": [{"team1": {"roster_id": 5}, "team2": {"roster_id": 7}}]}
    assert find_active_arcs(arcs, 2025, week_data, {}, {"brent boone": 1}) == []


def test_find_active_arcs_resolves_string_participants():
    # participants are WhatsApp display names; they must resolve via
    # name_to_roster or the arc is silently dropped (the shipped bug).
    arcs = [_proj_arc(["Brent Boone"], count=3)]
    week_data = {"matchups": [{"team1": {"roster_id": 3}, "team2": {"roster_id": 7}}]}
    out = find_active_arcs(arcs, 2025, week_data, {}, {"brent boone": 3})
    assert len(out) == 1, "string participant should resolve to roster 3 (playing)"


def test_find_active_arcs_string_participants_without_map_still_drop():
    arcs = [_proj_arc(["Brent Boone"], count=3)]
    week_data = {"matchups": [{"team1": {"roster_id": 3}, "team2": {"roster_id": 7}}]}
    assert find_active_arcs(arcs, 2025, week_data, {}, {}) == []


def test_find_active_arcs_preseason_full_roster_in_scope():
    # roster_id 3 has no matchup anywhere -- only reachable via the full-roster
    # fallback that preseason mode (week_data=None) provides.
    arcs = [_proj_arc(["Charlie Guy"], count=2, title="Preseason arc")]
    out = find_active_arcs(arcs, 2025, None, ROSTER_TO_TEAM, {"charlie guy": 3})
    assert len(out) == 1
    assert out[0]["this_week_development"] == "Entering the 2025 season"


# ---------------------------------------------------------------------------
# resolve_predictions -- admitter-gated made_at (uniform boundary)
# ---------------------------------------------------------------------------


def test_resolve_predictions_skips_predictions_made_after_cutoff():
    # made_at (UTC) is Nov 1, after the ~Oct-7 week-5 cutoff -> must be skipped.
    preds = [{"id": "p1", "made_at": "2025-11-01T00:00:00Z", "subject": "Alpha rolls"}]
    assert resolve_predictions(preds, 5, 2025, WEEK_DATA, CUTOFF) == []


def test_resolve_predictions_skips_missing_or_coarse_made_at():
    # Uniform admitter is fail-closed: a prediction with no / date-only made_at
    # is unknowable as-of-cutoff and dropped (was previously processed).
    preds = [
        {"id": "p0", "subject": "Alpha rolls"},  # no made_at
        {"id": "pd", "made_at": "2025-09-15", "subject": "Alpha rolls"},  # date-only
    ]
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


def test_resolve_predictions_gates_nested_evidence_and_local():
    """Nested evidence is its OWN admission point (crosswalk contract): an
    ADMITTED prediction (made_at <= C) must NOT surface a post-cutoff quote_block
    message (empty subject -> quote_block fallback) nor an ungated future
    timestamp_local. Fail-closed even though the corpus is clean today."""
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
            }
        ]
    }
    preds = [
        {
            "id": "poison",
            "made_at": "2025-09-15T00:00:00Z",  # admitted (<= CUTOFF)
            "author_whatsapp": "Karim",
            "subject": "",  # empty -> falls back to the quote_block join
            "quote_block": [
                {"text": "mahomes is elite", "timestamp": "2025-09-15T00:00:00Z"},
                {
                    "text": "FUTURE LEAK about mahomes",
                    "timestamp": "2025-12-01T00:00:00Z",
                },
            ],
            "timestamp_local": "2099-01-01 05:00:00",  # ungated future local
        }
    ]
    out = resolve_predictions(preds, 5, 2025, wd, CUTOFF)
    assert len(out) == 1  # made_at admitted -> resolves (mahomes elite + 31 pts)
    assert "FUTURE LEAK" not in out[0]["original_quote"]  # post-cutoff quote_block cut
    assert "mahomes is elite" in out[0]["original_quote"]  # admissible evidence kept
    assert (
        out[0]["made_at_local"] == "2025-09-15T00:00:00Z"
    )  # gated -> made_at fallback


# ---------------------------------------------------------------------------
# sanitize_league_memory -- timeless culture + recompute jokes (new schema)
# ---------------------------------------------------------------------------


def test_sanitize_league_memory_culture_and_recompute_jokes():
    league_memory = {
        "meta": {"generated": "2026-02-26T00:00:00Z"},
        "culture": {
            "summary": "35 months, all-time retrospective -- leaks the ending",
            "activity_triggers": ["Trade announcements", "TNF"],
        },
        "lexicon": {"anything": "Used 5 times this month; also 2026-03"},
        "greatest_moments": [{"rank": 1, "title": "leak"}],
    }
    jokes = [
        {
            "name": "tank talk",
            "first_seen": "2025-09",
            "last_seen": "2025-10",
            "count": 12,
            "first_seen_at": "2025-09-05T10:00:00Z",
            "last_observed_at": "2025-10-01T10:00:00Z",
            "total_frequency": 99,  # all-time -> dropped
            "sample_block": [{"text": "unfiltered evidence"}],  # dropped
        },
        {
            "name": "zero joke",
            "first_seen": "2025-09",
            "last_seen": "2025-09",
            "count": 0,  # no admissible evidence -> dropped
            "first_seen_at": None,
            "last_observed_at": None,
        },
    ]
    out = sanitize_league_memory(league_memory, jokes)
    assert "greatest_moments" not in out and "meta" not in out
    # culture: only timeless activity_triggers survive; retrospective summary dropped
    assert out["culture"] == {"activity_triggers": ["Trade announcements", "TNF"]}
    # lexicon: fail-closed empty until a structured extractor lands
    assert out["lexicon"] == {}
    # running_jokes: count==0 dropped; kept joke reduced to the 6-field schema --
    # no all-time total_frequency, no unfiltered sample_block, no still_active.
    assert [j["name"] for j in out["running_jokes"]] == ["tank talk"]
    assert out["running_jokes"][0] == {
        "name": "tank talk",
        "first_seen": "2025-09",
        "last_seen": "2025-10",
        "count": 12,
        "first_seen_at": "2025-09-05T10:00:00Z",
        "last_observed_at": "2025-10-01T10:00:00Z",
    }


# ---------------------------------------------------------------------------
# build_suggested_callbacks -- from_when carries the exact first_seen_at
# ---------------------------------------------------------------------------


def test_callbacks_jokes_use_exact_first_seen_at():
    jokes = [
        {
            "name": "Alpha tank jokes",
            "first_seen": "2025-09",
            "first_seen_at": "2025-09-05T10:00:00Z",
            "count": 5,
        }
    ]
    out = build_suggested_callbacks(jokes, None, None, WEEK_DATA, {}, CUTOFF)
    lm = [c for c in out if c["source"] == "league-memory"]
    assert lm and lm[0]["content"] == "Alpha tank jokes"
    assert lm[0]["from_when"] == "2025-09-05T10:00:00Z"  # exact instant, not month


def test_callbacks_arcs_use_exact_first_seen_at():
    arcs = [
        {
            "arc_group_id": "trade_saga::x",
            "title": "Alpha saga",
            "first_seen_at": "2025-03-01T10:00:00Z",
            "count": 3,
        }
    ]
    out = build_suggested_callbacks(None, arcs, None, WEEK_DATA, {}, CUTOFF)
    arc_cbs = [c for c in out if c["source"] == "arc"]
    assert arc_cbs and arc_cbs[0]["content"] == "Alpha saga"
    assert arc_cbs[0]["from_when"] == "2025-03-01T10:00:00Z"


def test_callbacks_prediction_branch_reads_subject_and_admitter_gates():
    preds = [
        {
            "id": "pred-007",
            "author_whatsapp": "Oscar",
            "subject": "Alpha will miss the playoffs, book it",
            "quote_block": [],
            "made_at": "2025-09-10T00:00:00Z",
            "resolution": "pending",
        },
        {
            "id": "pred-future",
            "subject": "Alpha wins it all",
            "made_at": "2025-12-01T00:00:00Z",  # after cutoff -> admitter drops
        },
    ]
    out = build_suggested_callbacks(None, None, preds, WEEK_DATA, {}, CUTOFF)
    pred_cbs = [c for c in out if c["source"] == "prediction"]
    assert len(pred_cbs) == 1 and "Alpha" in pred_cbs[0]["content"]


def test_callbacks_gate_nested_prediction_evidence():
    """The callback quote_block gate mirrors resolve_predictions: an admissible
    nested team mention fires exactly one prediction callback; a post-cutoff (or
    malformed-timestamp) nested mention fires ZERO -- fail-closed. Without the
    gate the post-cutoff mention would join, match "alpha", and fire a callback."""

    def _preds(qb_ts):
        return {
            "predictions": [
                {
                    "id": "cb",
                    "made_at": "2025-09-15T00:00:00Z",  # admitted (<= C)
                    "subject": "",  # empty -> quote_block fallback
                    "quote_block": [{"text": "alpha is a fraud", "timestamp": qb_ts}],
                }
            ]
        }

    def _pred_cbs(qb_ts):
        out = build_suggested_callbacks(
            None, None, _preds(qb_ts), WEEK_DATA, {}, CUTOFF
        )
        return [c for c in out if c["source"] == "prediction"]

    assert len(_pred_cbs("2025-09-15T00:00:00Z")) == 1  # admissible nested mention
    assert _pred_cbs("2025-12-01T00:00:00Z") == []  # post-cutoff -> zero
    assert _pred_cbs("garbage") == []  # malformed timestamp -> zero (fail-closed)


def test_build_suggested_callbacks_none_week_data_uses_roster_fallback():
    arcs = [
        {
            "arc_group_id": "trade_saga::x",
            "title": "Alpha saga",
            "first_seen_at": "2025-03-01T10:00:00Z",
            "count": 3,
        }
    ]
    cbs = build_suggested_callbacks(
        None, arcs, None, None, ROSTER_TO_TEAM, PRESEASON_END_2025
    )
    assert any(c["source"] == "arc" for c in cbs)


# ---------------------------------------------------------------------------
# _member_messages / highlights invariants (unchanged)
# ---------------------------------------------------------------------------


def test_member_messages_enforces_sender_invariant():
    raw = [
        {"sender": "Zach", "is_system": False},
        {"sender": None, "is_system": True, "text": "This message was deleted."},
        {"sender": None, "is_system": False, "text": "malformed non-system"},
        {"sender": "", "is_system": False, "text": "empty sender"},
        {"sender": "Sacko", "is_system": False},
    ]
    out = _member_messages(raw)
    assert [m["sender"] for m in out] == ["Zach", "Sacko"]
    assert all(m.get("sender") for m in out)  # invariant: never a null/empty sender


def test_highlight_uses_only_real_members_no_phantom_participant():
    raw = [
        {
            "sender": "Zach",
            "timestamp_utc": "2025-10-01T10:00:00Z",
            "text": "yo",
            "is_system": False,
        },
        {
            "sender": None,
            "timestamp_utc": "2025-10-01T10:01:00Z",
            "text": "This message was deleted.",
            "is_system": True,
        },
        {
            "sender": "Sacko",
            "timestamp_utc": "2025-10-01T10:02:00Z",
            "text": "hey",
            "is_system": False,
        },
        {
            "sender": "Zach",
            "timestamp_utc": "2025-10-01T10:03:00Z",
            "text": "lol",
            "is_system": False,
        },
    ]
    good = extract_chat_highlights(_member_messages(raw), [])
    assert good, "two real members in a 5-min cluster should yield a highlight"
    for h in good:
        parts = [
            n.strip()
            for n in h["summary"].replace(" exchanging messages", "").split(",")
        ]
        assert "" not in parts and len(parts) >= 2  # no blank; genuine multi-person
        assert set(parts) <= {"Zach", "Sacko"}  # only real members, no phantom
        block_text = " ".join(b.get("text", "") for b in h["block"]).lower()
        assert "message was deleted" not in block_text


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
    assert get_all_team_names(WEEK_DATA, ROSTER_TO_TEAM) == {"alpha", "bravo"}


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


def test_resolve_sender_none_sender_returns_none_pair():
    assert resolve_sender(None, {"brent boone": 3}, {3: "Chudders"}) == (None, None)


def test_resolve_sender_empty_sender_returns_none_pair():
    assert resolve_sender("", {"brent boone": 3}, {3: "Chudders"}) == (None, None)


# ---------------------------------------------------------------------------
# IO-free pure core (1e) + no dead season_combined read (1i)
# ---------------------------------------------------------------------------


def _synthetic_core_inputs():
    messages = [
        {
            "sender": "Brent Boone",
            "timestamp_utc": "2025-09-05T10:00:00Z",
            "text": "who says no to this trade",
            "is_system": False,
        },
        {
            "sender": "Matt Russell",
            "timestamp_utc": "2025-09-06T10:00:00Z",
            "text": "i want to trade my rb",
            "is_system": False,
        },
        {
            "sender": "Brent Boone",
            "timestamp_utc": "2025-09-07T10:00:00Z",
            "text": "that was a robbery",
            "is_system": False,
        },
    ]
    name_map = {"Brent Boone": {}, "Matt Russell": {}}
    identity_chain = {
        "by_roster_id": {
            "1": {"whatsapp_name": "Brent Boone", "team_name": "Alpha"},
            "2": {"whatsapp_name": "Matt Russell", "team_name": "Bravo"},
        }
    }
    league_memory = {"culture": {"activity_triggers": ["Trade announcements"]}}
    week_data = {
        "matchups": [
            {
                "team1": {"roster_id": 1, "team_name": "Alpha", "points": 100},
                "team2": {"roster_id": 2, "team_name": "Bravo", "points": 90},
                "winner": "Alpha",
                "margin": 10,
            }
        ]
    }
    predictions = {"predictions": []}
    return messages, name_map, identity_chain, league_memory, week_data, predictions


def test_build_context_dict_is_io_free_and_input_pure(monkeypatch):
    """The pure core reads NO disk / network and mutates none of its injected
    inputs -- in BOTH the --no-ai branch (scored computed internally) AND the
    PRODUCTION AI composition (scored=<precomputed list>, as the CLI supplies
    after ai_rescore). score_relevancy is itself pure. A leaked disk/network
    read (or a preloaded module global) would be a bug. cutoff = the Week-1
    instant."""
    messages, name_map, ic, lm, wd, preds = _synthetic_core_inputs()
    before = copy.deepcopy((messages, name_map, ic, lm, wd, preds))
    cutoff = datetime(2025, 9, 9, 6, 59, 59, tzinfo=timezone.utc)  # Week 1 cutoff

    # Precompute a scored list the way the AI outer stage would (before patching).
    window_messages, _ws, rtn, ntr, rtt = bcc._window_and_maps(
        messages, ic, 2025, 1, False, cutoff
    )
    scored = bcc.score_relevancy(window_messages, wd, ic, rtn, ntr, rtt)

    def _boom(*a, **k):
        raise AssertionError("pure core performed disk/network I/O")

    monkeypatch.setattr(bcc, "load_json", _boom)
    monkeypatch.setattr(builtins, "open", _boom)
    monkeypatch.setattr(pathlib.Path, "open", _boom)
    # (1) --no-ai branch: scored computed internally.
    out_noai = build_context_dict(
        messages, name_map, ic, lm, wd, preds, 2025, 1, False, cutoff
    )
    # (2) production AI composition: scored supplied (post ai_rescore).
    out_ai = build_context_dict(
        messages, name_map, ic, lm, wd, preds, 2025, 1, False, cutoff, scored=scored
    )
    # (3) score_relevancy is itself pure under the same guard.
    bcc.score_relevancy(window_messages, wd, ic, rtn, ntr, rtt)
    monkeypatch.undo()

    assert out_noai["meta"]["type"] == "week" and out_noai["meta"]["week"] == 1
    # A trade arc among Brent+Matt (both playing) surfaces with the new schema.
    arcs = out_noai["active_arcs_this_week"]
    assert arcs and "arc_group_id" in arcs[0] and "status" not in arcs[0]
    assert out_ai["active_arcs_this_week"]  # AI-composition path surfaces arcs too
    # Inputs unmutated across both paths.
    assert (messages, name_map, ic, lm, wd, preds) == before


def test_no_season_combined_read_anywhere():
    # 1i: the dead, undeclared season_combined.json read (result discarded) is
    # gone -- assert the string appears nowhere in the module source.
    assert "season_combined" not in inspect.getsource(
        bcc
    ), "the dead season_combined.json read must stay deleted"
