"""Tests for derive_historical_rosters.py (T9, redesigned 2026-06-04).

Two modes:
- PRIMARY  build_snapshot_from_matchups(): Sleeper matchup data is immutable
  history and still serves 2025 weeks with full players[] + starters[]
  arrays (probe-verified 2026-06-04). captured=true, derived=false,
  source="sleeper_matchups_backfill".
- FALLBACK derive_week(): reverse-apply transactions from the current-roster
  snapshot. Real Sleeper field shapes: txns use `leg` (NOT `week`) and
  include status:"failed" entries that must be filtered. Derived snapshots
  have null starters/reserve (architect B2) and are stamped
  derived_confidence="approximate" (advisory — offseason gap is
  unrecoverable: transactions stop at leg 17, anchor is post-offseason).

The 2026-05-03 plan's original fixtures used synthetic `week` keys, which
masked all three data-source bugs — these tests use the real shapes.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from scripts.derive_historical_rosters import (
    build_snapshot_from_matchups,
    derive_week,
    flatten_transactions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (REPO_ROOT / "scripts" / "schemas" / "fantasy_roster.schema.json").read_text(
        encoding="utf-8"
    )
)


def _owner_map(n=12):
    return {rid: f"owner_{rid}" for rid in range(1, n + 1)}


def _matchup_entries(n=12):
    """Realistic Sleeper matchup entries — keys as probed 2026-06-04."""
    return [
        {
            "roster_id": rid,
            "matchup_id": (rid + 1) // 2,
            "points": 100.0 + rid,
            "custom_points": None,
            "players": [f"p{rid}_a", f"p{rid}_b", f"p{rid}_c"],
            "players_points": {},
            "starters": [f"p{rid}_a", f"p{rid}_b"],
            "starters_points": [10.0, 9.5],
        }
        for rid in range(1, n + 1)
    ]


# ---------- PRIMARY: matchup-sourced snapshots ----------


def test_matchup_snapshot_is_captured_not_derived():
    snap = build_snapshot_from_matchups(
        week=3, entries=_matchup_entries(), owner_by_roster=_owner_map()
    )
    assert snap["week"] == 3
    assert snap["captured"] is True
    assert snap["derived"] is False
    assert snap["source"] == "sleeper_matchups_backfill"
    assert snap["captured_at"]  # ISO timestamp present


def test_matchup_snapshot_joins_owner_and_keeps_starters():
    snap = build_snapshot_from_matchups(
        week=1, entries=_matchup_entries(), owner_by_roster=_owner_map()
    )
    r1 = snap["rosters"][0]
    assert r1["roster_id"] == 1
    assert r1["owner_id"] == "owner_1"
    assert r1["players"] == ["p1_a", "p1_b", "p1_c"]
    assert r1["starters"] == ["p1_a", "p1_b"]  # recoverable via matchups
    assert r1["reserve"] is None  # not exposed by matchup endpoint


def test_matchup_snapshot_sorted_and_schema_valid():
    snap = build_snapshot_from_matchups(
        week=7, entries=list(reversed(_matchup_entries())), owner_by_roster=_owner_map()
    )
    rids = [r["roster_id"] for r in snap["rosters"]]
    assert rids == sorted(rids)
    jsonschema.validate(snap, SCHEMA)


def test_matchup_snapshot_missing_owner_raises():
    owners = _owner_map()
    del owners[5]
    with pytest.raises(KeyError):
        build_snapshot_from_matchups(
            week=1, entries=_matchup_entries(), owner_by_roster=owners
        )


# ---------- FALLBACK: transaction-reversal derivation ----------


def _current_rosters(n=12):
    return [
        {
            "roster_id": rid,
            "owner_id": f"owner_{rid}",
            "players": [f"p{rid}_a", f"p{rid}_b"],
            "starters": [f"p{rid}_a"],
            "reserve": [],
        }
        for rid in range(1, n + 1)
    ]


def test_flatten_transactions_uses_leg_and_filters_failed():
    """Real shape: week-keyed dict; txns carry `leg` + `status`."""
    week_keyed = {
        "5": [
            {
                "type": "waiver",
                "leg": 5,
                "status": "complete",
                "adds": {"x": 1},
                "drops": None,
            },
            {
                "type": "waiver",
                "leg": 5,
                "status": "failed",
                "adds": {"GHOST": 1},
                "drops": None,
            },
        ],
        "9": [
            {
                "type": "trade",
                "leg": 9,
                "status": "complete",
                "adds": {"y": 2},
                "drops": {"z": 2},
            },
        ],
    }
    flat = flatten_transactions(week_keyed)
    assert len(flat) == 2  # failed txn filtered out
    assert all(t["status"] == "complete" for t in flat)
    assert sorted(t["leg"] for t in flat) == [5, 9]


def test_derive_week_keys_on_leg_not_week():
    """A txn with only `leg` (real shape) MUST be reversed. The original
    plan's deriver read t['week'] — every reversal silently no-opped."""
    rosters = [
        {
            "roster_id": 1,
            "owner_id": "U1",
            "players": ["p_old", "p_new"],
            "starters": ["p_new"],
        },
    ]
    txns = [
        {
            "type": "waiver",
            "leg": 5,
            "status": "complete",
            "adds": {"p_new": 1},
            "drops": {},
        }
    ]
    snap = derive_week(week=3, current_rosters=rosters, transactions=txns)
    r1 = snap["rosters"][0]
    assert "p_new" not in r1["players"]  # added wk5 → absent in wk3
    assert "p_old" in r1["players"]


def test_derive_week_restores_dropped_players():
    rosters = [
        {"roster_id": 1, "owner_id": "U1", "players": ["p_kept"], "starters": None}
    ]
    txns = [
        {
            "type": "free_agent",
            "leg": 8,
            "status": "complete",
            "adds": {},
            "drops": {"p_cut": 1},
        },
    ]
    snap = derive_week(week=4, current_rosters=rosters, transactions=txns)
    assert "p_cut" in snap["rosters"][0]["players"]  # dropped wk8 → present wk4


def test_derive_week_ignores_transactions_at_or_before_week():
    rosters = [
        {"roster_id": 1, "owner_id": "U1", "players": ["p_early"], "starters": None}
    ]
    txns = [
        {
            "type": "waiver",
            "leg": 3,
            "status": "complete",
            "adds": {"p_early": 1},
            "drops": {},
        },
    ]
    snap = derive_week(week=3, current_rosters=rosters, transactions=txns)
    assert "p_early" in snap["rosters"][0]["players"]  # leg 3 is NOT > 3


def test_derived_snapshot_flags_nulls_and_confidence():
    snap = derive_week(week=2, current_rosters=_current_rosters(), transactions=[])
    assert snap["captured"] is False
    assert snap["derived"] is True
    assert snap["captured_at"] is None
    assert snap["source"] == "transaction_reversal"
    assert snap["derived_confidence"] == "approximate"
    for r in snap["rosters"]:
        assert r["starters"] is None  # architect B2: unrecoverable via reversal
        assert r["reserve"] is None


def test_derived_snapshot_schema_valid():
    snap = derive_week(week=6, current_rosters=_current_rosters(), transactions=[])
    jsonschema.validate(snap, SCHEMA)
