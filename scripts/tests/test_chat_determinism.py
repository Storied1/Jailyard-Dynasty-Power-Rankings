"""Determinism pins for the chat MAP/REDUCE pipeline (PYTHONHASHSEED is unpinned)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import reduce_chat_deterministic as rc  # noqa: E402
from map_chat_deterministic import detect_consensus, find_candidate_arcs  # noqa: E402
from reduce_chat_deterministic import reduce_arcs  # noqa: E402
from reduce_chat_deterministic import (
    reduce_consensus,
    reduce_league_memory,
    reduce_predictions,
    reduce_relationships,
)


def _trade_msgs(senders):
    return [
        {"sender": s, "text": "I will trade you my RB1 for that pick"} for s in senders
    ]


def test_find_candidate_arcs_participants_sorted():
    name_map = {"Zeta": {}, "Alpha": {}, "Mike": {}}
    msgs = _trade_msgs(["Zeta", "Alpha", "Mike", "Zeta"])
    arcs = find_candidate_arcs(msgs, [], [], name_map)
    trade = [a for a in arcs if a.get("type") == "trade_saga"]
    assert trade, "expected a trade_saga arc from 3+ trade messages"
    parts = trade[0]["participants"]
    assert parts == sorted(parts), f"participants not sorted: {parts}"


def test_reduce_arcs_group_key_sorts_before_slice():
    # Same 4-participant SET in different list orders, split across two months.
    # Bug (slice-then-sort): month A keys on sorted(["d","c","b"]) = (b,c,d),
    # month B keys on sorted(["a","b","c"]) = (a,b,c) -> TWO merged arcs.
    # Fix (sort-then-slice): both key on (a,b,c) -> ONE merged arc.
    # reduce_arcs returns a bare list (merged_arcs[:30]) -- assert on length,
    # which is field-name independent and deterministic (no hash involved).
    base = {"title": "Trade activity surge", "type": "trade_saga", "key_moments": []}
    out = reduce_arcs(
        {
            "2025-09": {
                "candidate_arcs": [dict(base, participants=["d", "c", "b", "a"])]
            },
            "2025-10": {
                "candidate_arcs": [dict(base, participants=["a", "b", "c", "d"])]
            },
        },
        {},
    )
    assert len(out) == 1, f"same participant set must merge to ONE arc, got {len(out)}"


def test_detect_consensus_counts_members_only():
    name_map = {"Alpha": {}, "Bravo": {}, "Carol": {}, "Dave": {}}
    # Verified: CONSENSUS_MIN_SENDERS = 4, CONSENSUS_WINDOW_SIZE = 20
    # (scripts/shared.py). Each 20-message chunk of this fixture contains all
    # 6 rotating senders: only 3 are members (< 4 -> no fire with the fix);
    # with the precedence bug non-members count too (6 >= 4 -> fires).
    senders = ["Alpha", "Bravo", "Carol", "Nonmember1", "Nonmember2", "Nonmember3"]
    messages = [
        {"sender": senders[i % len(senders)], "text": "should I take this trade?"}
        for i in range(60)
    ]
    snapshots = detect_consensus(messages, name_map)
    # 3 unique members < CONSENSUS_MIN_SENDERS (4) -> no consensus should fire
    assert (
        snapshots == []
    ), "non-member senders inflated the consensus count (operator-precedence bug)"


def test_reduce_arcs_different_crews_stay_separate():
    # Full-crew grouping: a different 4th participant means a DIFFERENT saga.
    # (The pre-fix any-3-alphabetical key merged every month's trade cluster.)
    base = {"title": "Trade activity surge", "type": "trade_saga", "key_moments": []}
    out = reduce_arcs(
        {
            "2025-09": {
                "candidate_arcs": [dict(base, participants=["a", "b", "c", "d"])]
            },
            "2025-10": {
                "candidate_arcs": [dict(base, participants=["a", "b", "c", "e"])]
            },
        },
        {},
    )
    assert len(out) == 2, f"different crews must stay separate arcs, got {len(out)}"


# ---------------------------------------------------------------------------
# 2b — serialize-boundary order determinism. Each fixture is built so the
# UNsorted (insertion / dict / hash) order differs from the sorted order, so
# these fail before the sorted()/tie-break fix and pass after.
# ---------------------------------------------------------------------------


def test_reduce_league_memory_lexicon_sorted():
    map_outputs = {
        "2025-09": {"lexicon_candidates": {"zebra": "z", "apple": "a"}},
        "2025-10": {"lexicon_candidates": {"mango": "m"}},
    }
    result = reduce_league_memory(map_outputs, {}, 100)
    keys = list(result["lexicon"].keys())
    assert keys == sorted(keys), f"lexicon keys not sorted: {keys}"


def test_reduce_predictions_cred_index_sorted():
    map_outputs = {
        "2025-09": {
            "predictions_and_bets": [
                {"author": "Zed", "subject": "s1"},
                {"author": "Amy", "subject": "s2"},
                {"author": "Mo", "subject": "s3"},
            ]
        },
    }
    result = reduce_predictions(map_outputs, {})
    keys = list(result["credibility_index"].keys())
    assert keys == sorted(keys), f"cred_index keys not sorted: {keys}"


def test_reduce_relationships_pairs_tiebroken_by_members():
    # Equal interaction_count -> order must be deterministic by the sorted
    # member-pair tuple, not dict-insertion (which is [Yara..] first here).
    map_outputs = {
        "2025-09": {
            "relationship_interactions": [
                {"pair": ["Yara", "Zane"], "interaction_count": 5, "tone": "neutral"},
                {"pair": ["Amy", "Bob"], "interaction_count": 5, "tone": "neutral"},
            ]
        },
    }
    result = reduce_relationships(map_outputs, {})
    members = [p["members"] for p in result["pairs"]]
    assert members == sorted(
        members
    ), f"pairs not tie-broken deterministically: {members}"


def test_reduce_consensus_topics_sorted():
    map_outputs = {
        "2025-09": {
            "consensus_snapshots": [
                {"topic": "zebra", "group_lean": "x"},
                {"topic": "apple", "group_lean": "y"},
            ]
        },
    }
    result = reduce_consensus(map_outputs, {})
    topics = [s["topic"] for s in result["snapshots"]]
    assert topics == sorted(topics), f"consensus topics not sorted: {topics}"


def test_reduce_arcs_preserves_chronological_tie_order():
    # reduce_arcs ties are NOT alphabetical -- they preserve chronological
    # encounter order (Sep crew before Oct crew), which is already
    # PYTHONHASHSEED-independent. Guards against re-adding an alphabetical
    # tie-break (which would also break test_tie_order_preservation).
    base = {"title": "T", "type": "trade_saga", "key_moments": []}
    out = reduce_arcs(
        {
            "2025-09": {"candidate_arcs": [dict(base, participants=["yara", "zane"])]},
            "2025-10": {"candidate_arcs": [dict(base, participants=["amy", "bob"])]},
        },
        {},
    )
    assert [a["participants"] for a in out] == [["yara", "zane"], ["amy", "bob"]]


# ---------------------------------------------------------------------------
# 2i -- reduce_personas is roster-driven + fail-closed. PERSONAS_DIR is
# monkeypatched to tmp so nothing writes into content/ (conftest purity).
# ---------------------------------------------------------------------------


def _patch_personas(monkeypatch, tmp_path):
    monkeypatch.setattr(rc, "PERSONAS_DIR", tmp_path / "personas")
    monkeypatch.setattr(rc, "FINGERPRINTS_PATH", tmp_path / "absent-fingerprints.json")


def test_reduce_personas_rejects_wrong_member(tmp_path, monkeypatch):
    _patch_personas(monkeypatch, tmp_path)
    name_map = {"Neo": {"real_name": "Blake"}}
    map_outputs = {
        "2025-09": {
            "persona_observations": [{"member": "Stranger", "observations": []}]
        }
    }
    with pytest.raises(SystemExit):
        rc.reduce_personas(map_outputs, name_map)
    # detector-active: validation precedes any mkdir/write -> dir never created.
    assert not (tmp_path / "personas").exists()


def test_reduce_personas_rejects_slug_collision(tmp_path, monkeypatch):
    _patch_personas(monkeypatch, tmp_path)
    with pytest.raises(SystemExit):
        rc.reduce_personas({}, {"Ben Chodos": {}, "ben chodos": {}})
    assert not (tmp_path / "personas").exists()  # nothing written before rejection


def test_reduce_personas_rejects_stale_extra(tmp_path, monkeypatch):
    # A pre-existing (stale) persona file is an EXTRA -> post-write gate rejects.
    _patch_personas(monkeypatch, tmp_path)
    (tmp_path / "personas").mkdir()
    (tmp_path / "personas" / "ghost.md").write_text("stale", encoding="utf-8")
    with pytest.raises(SystemExit):
        rc.reduce_personas({}, {"Neo": {"real_name": "Blake"}})


def test_reduce_personas_roster_exact_and_embeds_identity(tmp_path, monkeypatch):
    _patch_personas(monkeypatch, tmp_path)
    name_map = {
        "Neo": {"real_name": "Blake", "sleeper_handle": "bLaker24"},
        "Sacko": {"real_name": "Sam"},
    }
    # Observations only for Neo -> Sacko still gets a persona (roster-driven).
    map_outputs = {
        "2025-09": {
            "persona_observations": [
                {
                    "member": "Neo",
                    "observations": ["x"],
                    "posting_stats": {"message_count": 3},
                }
            ]
        }
    }
    rc.reduce_personas(map_outputs, name_map)
    produced = sorted(p.stem for p in (tmp_path / "personas").glob("*.md"))
    assert produced == ["neo", "sacko"]  # EXACTLY the roster
    neo = (tmp_path / "personas" / "neo.md").read_text(encoding="utf-8")
    assert "Blake" in neo and "bLaker24" in neo  # identity embedded
