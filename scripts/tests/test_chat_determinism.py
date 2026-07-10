"""Determinism pins for the chat MAP/REDUCE pipeline (PYTHONHASHSEED is unpinned)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from map_chat_deterministic import find_candidate_arcs  # noqa: E402
from reduce_chat_deterministic import reduce_arcs  # noqa: E402


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
