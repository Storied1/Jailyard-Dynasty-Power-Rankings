"""The preseason evidence projection: facts only, nothing past the cutoff.

The load-bearing tests are the planted-fact proofs: a post-cutoff fact placed
directly into the projection's input must not reach the output, and a planted
post-cutoff roster transaction must leave the projected cutoff roster
unchanged. The evidence bundle itself lives in gitignored private custody
(private_bundles/); the tracked public surface is the manifest, verified here
without reading private bytes. Private-side tests run only where the local
bundle and data files exist.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.build_preseason_evidence import (
    LEAGUE_EXEMPLARS,
    MANIFEST_PATH,
    OUT_PATH,
    RosterRewindError,
    check_manifest_public,
    project,
    project_cutoff_rosters,
    verify_bundle,
)

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = OUT_PATH  # private_bundles/preseason-2025/preseason_evidence.json
PRIVATE_STATE = REPO / "private_editions" / "2025-preseason" / "state.json"
ROSTER_SNAPSHOT = REPO / "data" / "2025" / "fantasy_rosters" / "week1.json"
TRANSACTION_LOG = REPO / "data" / "2025" / "transactions.json"
CUTOFF = "2025-09-03T23:59:59.000000Z"

_needs_private = pytest.mark.skipif(
    not (PRIVATE_STATE.exists() and EVIDENCE.exists()),
    reason="gitignored private edition state/bundle absent (present only locally)",
)
_needs_bundle = pytest.mark.skipif(
    not EVIDENCE.exists(),
    reason="gitignored private bundle absent (present only locally)",
)
_needs_rosters = pytest.mark.skipif(
    not (EVIDENCE.exists() and ROSTER_SNAPSHOT.exists()),
    reason="gitignored roster snapshot/bundle absent (present only locally)",
)


@dataclass(frozen=True)
class FakeFact:
    fact_id: str
    fact_type: str
    known_at: str
    payload: dict


def _chat(ts, sender="Zach", known_at=None, fid=None):
    return FakeFact(
        fact_id=fid or f"fact:{ts}",
        fact_type="chat_message",
        known_at=known_at or ts,
        payload={"sender": sender, "text": "quote", "timestamp_utc": ts},
    )


def test_planted_post_cutoff_fact_cannot_enter_the_evidence():
    """A late-2025 fact in the INPUT must be absent from the OUTPUT."""
    good = _chat("2025-08-20T00:17:46Z")
    plant = _chat("2025-11-20T02:00:00Z", fid="fact:planted-late")
    facts = [good, plant]
    assert plant in facts, "the plant must land in the input"
    out = project(facts, CUTOFF)
    ids = {q["fact_id"] for q in out["chat_quotes"]["messages"]}
    assert good.fact_id in ids
    assert plant.fact_id not in ids
    assert "fact:planted-late" not in json.dumps(out)


def test_planted_fact_with_backdated_payload_still_rejected():
    """A post-cutoff fact wearing an in-window timestamp_utc is still dropped:
    admissibility is judged on known_at, re-checked at the projection."""
    plant = FakeFact(
        fact_id="fact:backdated-payload",
        fact_type="chat_message",
        known_at="2025-11-20T02:00:00Z",
        payload={
            "sender": "Zach",
            "text": "quote",
            "timestamp_utc": "2025-08-01T00:00:00Z",
        },
    )
    out = project([plant], CUTOFF)
    assert out["chat_quotes"]["messages"] == []


def test_malformed_known_at_is_dropped_not_admitted():
    for bad in (None, "", "2025-08", "2025-08-20", "not-a-date"):
        plant = FakeFact(
            fact_id=f"fact:bad-{bad}",
            fact_type="draft_pick",
            known_at=bad,
            payload={"round": 1, "pick_no": 1, "roster_id": "1", "player_id": "9"},
        )
        out = project([plant], CUTOFF)
        assert out["draft"]["picks"] == [], f"admitted with known_at={bad!r}"


def test_projection_emits_facts_without_treatment_keys():
    out = project([_chat("2025-08-20T00:17:46Z")], CUTOFF)
    text = json.dumps(out).lower()
    for term in ("suggested_", "framing", "overheard", "callback"):
        assert term not in text


# ------------------------------------------- cutoff rosters (pure rewind) --


def _tx(tid, ms, adds=None, drops=None, type_="free_agent", status="complete"):
    return {
        "transaction_id": tid,
        "type": type_,
        "status": status,
        "status_updated": ms,
        "adds": adds,
        "drops": drops,
    }


CUT_MS = 1756943999000  # 2025-09-03T23:59:59Z


def _snapshot():
    return [
        {"roster_id": 1, "players": ["A", "B", "C"]},
        {"roster_id": 2, "players": ["D", "E"]},
    ]


def test_planted_post_cutoff_add_drop_trade_leave_cutoff_roster_unchanged():
    """Noninterference, detector-active: a consistent post-cutoff add, drop,
    and trade are APPLIED to the snapshot (the plant provably lands: the
    mutated snapshot differs from the clean one), and the projected cutoff
    roster is byte-identical to projecting the clean snapshot with no
    post-cutoff transactions at all."""
    clean = _snapshot()
    baseline, rewound = project_cutoff_rosters(clean, [], CUTOFF)
    assert rewound == []

    # Post-cutoff activity: roster 1 adds X and drops C; then trades A for D.
    plants = [
        _tx("t-add", CUT_MS + 1000, adds={"X": 1}, drops={"C": 1}),
        _tx(
            "t-trade",
            CUT_MS + 2000,
            adds={"A": 2, "D": 1},
            drops={"A": 1, "D": 2},
            type_="trade",
        ),
    ]
    mutated = [
        {"roster_id": 1, "players": ["B", "X", "D"]},
        {"roster_id": 2, "players": ["E", "A"]},
    ]
    assert {r["roster_id"]: set(r["players"]) for r in mutated} != {
        r["roster_id"]: set(r["players"]) for r in clean
    }, "the plant must land: the mutated snapshot differs"

    projected, rewound = project_cutoff_rosters(mutated, plants, CUTOFF)
    assert rewound == ["t-add", "t-trade"]
    assert projected == baseline, "post-cutoff activity leaked into the cutoff roster"


def test_partial_reflection_fails_closed():
    """A post-cutoff transaction half-applied to the snapshot is a data
    integrity failure, never a guess."""
    snap = [{"roster_id": 1, "players": ["A", "X"]}]  # add landed, drop didn't
    plant = _tx("t-partial", CUT_MS + 1000, adds={"X": 1}, drops={"A": 1})
    with pytest.raises(RosterRewindError):
        project_cutoff_rosters(snap, [plant], CUTOFF)


def test_non_monotone_boundary_fails_closed():
    """An older not-reflected transaction behind a newer reflected one means
    the snapshot is not a single moment; refuse."""
    snap = [{"roster_id": 1, "players": ["A", "Y"]}]
    older_unreflected = _tx("t-old", CUT_MS + 1000, adds={"X": 1})
    newer_reflected = _tx("t-new", CUT_MS + 2000, adds={"Y": 1})
    with pytest.raises(RosterRewindError):
        project_cutoff_rosters(snap, [older_unreflected, newer_reflected], CUTOFF)


def test_incomplete_and_pre_cutoff_transactions_are_ignored():
    snap = _snapshot()
    ignored = [
        _tx("t-failed", CUT_MS + 1000, adds={"Z": 1}, status="failed"),
        _tx("t-pre", CUT_MS - 1000, adds={"A": 1}),  # pre-cutoff: not rewound
    ]
    projected, rewound = project_cutoff_rosters(snap, ignored, CUTOFF)
    assert rewound == []
    assert projected == {r["roster_id"]: set(r["players"]) for r in snap}


# ------------------------------------------------- public manifest (tracked) --


def test_tracked_manifest_is_publicly_valid_without_private_bytes():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert check_manifest_public(manifest) == []
    assert manifest["cutoff_utc"] == CUTOFF
    assert manifest["counts"]["teams"] == 12
    assert manifest["counts"]["draft_picks"] == 72
    assert manifest["counts"]["roster_teams"] == 12
    assert manifest["counts"]["roster_players"] > 0


def test_tracked_manifest_carries_no_bundle_content():
    s = MANIFEST_PATH.read_text(encoding="utf-8")
    assert len(s) < 4096, "manifest must stay an aggregate record, not a bundle"
    for key in ('"messages"', '"players"', '"picks"', '"text"'):
        assert key not in s, f"bundle content key {key} leaked into the manifest"


def test_preflight_rejects_absent_bundle(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    ok, msg = verify_bundle(manifest_path=mpath, root=tmp_path)
    assert not ok
    assert "ABSENT" in msg


def test_preflight_rejects_hash_mismatched_bundle(tmp_path):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    bundle = tmp_path / Path(manifest["bundle"]["path"])
    bundle.parent.mkdir(parents=True)
    bundle.write_text('{"kind": "tampered"}', encoding="utf-8")
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    ok, msg = verify_bundle(manifest_path=mpath, root=tmp_path)
    assert not ok
    assert "MISMATCH" in msg


# ------------------------------------------------ private bundle (local only) --


@_needs_bundle
def test_private_bundle_has_no_post_cutoff_instant():
    s = EVIDENCE.read_text(encoding="utf-8")
    pat = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
    late = sorted(
        {m.group(0) for m in pat.finditer(s) if m.group(0) > "2025-09-03T23:59:59"}
    )
    assert late == [], late[:5]


@_needs_bundle
def test_private_bundle_shape():
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert doc["kind"] == "preseason-evidence/1"
    assert len(doc["teams"]) == 12
    assert len(doc["draft"]["picks"]) == 72
    assert doc["chat_quotes"]["messages"], "quotes must be present"
    for q in doc["chat_quotes"]["messages"][:50]:
        assert q["fact_id"].startswith("fact:")
        assert q["timestamp_utc"] <= "2025-09-03T23:59:59.999999Z"
    rosters = doc["rosters"]
    assert rosters["as_of_utc"] == CUTOFF
    assert rosters["derivation"]["method"] == "week1_snapshot_rewind"
    assert len(rosters["teams"]) == 12
    assert all(t["count"] == len(t["players"]) for t in rosters["teams"])


def test_league_exemplars_survive_a_narrowed_chat_window():
    """The curated form surface is NOT a window projection. Narrowing
    chat_window_start must drop the message from chat_quotes and keep it in
    league_exemplars. This is craft law 27 as a regression guard: the window was
    built to block the future and silently amputated the past instead, and the
    census only ever checks one direction, so nothing else would catch it."""
    fid = LEAGUE_EXEMPLARS[0][0]
    old = _chat("2023-10-04T12:57:13Z", sender="Karim", fid=fid)
    out = project([old], CUTOFF, chat_window_start="2025-02-10T00:00:00Z")
    assert out["chat_quotes"]["messages"] == [], "window filter should drop it"
    editions = out["league_exemplars"]["editions"]
    assert [e["fact_id"] for e in editions] == [fid]
    assert editions[0]["form"] == LEAGUE_EXEMPLARS[0][1]


def test_absent_exemplar_leaves_the_population_short():
    """The precondition main() fails closed on: an allowlisted id that resolves
    to nothing simply does not appear, so the count is the thing to assert."""
    out = project([_chat("2024-01-01T00:00:00Z", fid="fact:not-an-exemplar")], CUTOFF)
    assert out["league_exemplars"]["editions"] == []


@_needs_bundle
def test_every_league_exemplar_resolves_in_the_bundle():
    """All eight of the league's own power-ranking editions reached the writer.
    Two independent sweeps (length > 1200 chars, and >= 5 numbered list lines)
    agreed this is the whole population; Zach's epistolary has no numbered lines
    and only the first sweep finds it, which is why the allowlist is explicit."""
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    editions = doc["league_exemplars"]["editions"]
    assert {e["fact_id"] for e in editions} == {fid for fid, _ in LEAGUE_EXEMPLARS}
    assert len(editions) == 8
    for e in editions:
        assert e["text"] and len(e["text"]) > 1000, e["fact_id"]
        assert e["form"], e["fact_id"]
        assert e["author_team"], e["fact_id"]
        assert e["timestamp_utc"] <= "2025-09-03T23:59:59.999999Z"
    # Seven distinct authors: the column inherits a rotating-author tradition,
    # not one man's gimmick. Oscar wrote two of the eight.
    assert len({e["author"] for e in editions}) == 7


@_needs_bundle
def test_exemplars_are_also_quotable_through_the_ordinary_path():
    """Duplication with chat_quotes is intentional: the verbatim-quote audit
    resolves spans against chat_quotes.messages, so an exemplar quoted in prose
    must still be findable there."""
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    quoted = {q["fact_id"] for q in doc["chat_quotes"]["messages"]}
    assert {fid for fid, _ in LEAGUE_EXEMPLARS} <= quoted


@_needs_bundle
def test_private_bundle_matches_tracked_manifest():
    ok, msg = verify_bundle()
    assert ok, msg


@_needs_rosters
def test_bundle_rosters_match_a_fresh_rewind():
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    snap = json.loads(ROSTER_SNAPSHOT.read_text(encoding="utf-8"))
    tx = json.loads(TRANSACTION_LOG.read_text(encoding="utf-8"))
    state, rewound = project_cutoff_rosters(snap["rosters"], tx.get("1", []), CUTOFF)
    fresh = {str(rid): sorted(state[rid]) for rid in state}
    committed = {
        t["roster_id"]: sorted(p["player_id"] for p in t["players"])
        for t in doc["rosters"]["teams"]
    }
    assert fresh == committed
    assert doc["rosters"]["derivation"]["rewound_transactions"] == rewound


@_needs_rosters
def test_transaction_completeness_against_cutoff_rosters():
    """Completeness proof over the real data: replaying the bundle's own
    pre-cutoff record (draft picks, then the 182 offseason transactions in
    order) predicts membership for every touched player; the projected cutoff
    roster must agree exactly. Untouched carryover players are attested by
    the rewind's fail-closed classification instead."""
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    membership = {
        p["player_id"]: t["roster_id"]
        for t in doc["rosters"]["teams"]
        for p in t["players"]
    }
    expected = {}
    for p in doc["draft"]["picks"]:
        expected[p["player_id"]] = p["roster_id"]
    for tx in doc["transactions"]:  # already sorted by known_at
        # Drops before adds within one transaction: a trade lists the same
        # player as a drop from the old roster AND an add to the new one.
        for d in tx["drops"]:
            expected[d["player_id"]] = None
        for a in tx["adds"]:
            expected[a["player_id"]] = a["roster_id"]
    mismatches = [
        (pid, want, membership.get(pid))
        for pid, want in expected.items()
        if membership.get(pid) != want
    ]
    assert mismatches == [], mismatches[:10]


@_needs_private
def test_private_bundle_matches_a_fresh_projection():
    from scripts.build_preseason_evidence import _player_names
    from scripts.compile_state import load_compiled_state
    from scripts.eval_arms import rehydrate_state

    state = rehydrate_state(load_compiled_state("2025-preseason"))
    fresh = project(state.admitted, state.cutoff, names=_player_names())
    committed = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    committed.pop("edition_id", None)
    committed.pop("season", None)
    committed.pop("rosters", None)  # roster section is data-file derived
    committed.pop(
        "league_settings", None
    )  # likewise: read from data/2025/league_settings.json
    assert fresh == committed
