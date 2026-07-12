"""Tests for the D recompute-projection prototype spike.

23 functions -> `pytest -v` reports 23 passed. Fixtures are in-memory; the
session-autouse content-purity gate (scripts/tests/conftest.py) guards against
any write into content/. Fixtures use the LIVE detector patterns
(map_chat_deterministic.py) so they exercise real code paths, not invented ones.
"""

import builtins
import copy
import pathlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recompute_projection as rp  # noqa: E402
from map_chat_deterministic import detect_predictions  # noqa: E402
from map_chat_deterministic import detect_relationship_interactions, find_candidate_arcs
from recompute_projection import _admissible  # noqa: E402
from recompute_projection import _arc_group_id, recompute_projection

TACO = "Taco/Sacko references"  # JOKE_PATTERNS: (r"\btaco\b", ...)


def M(sender, ts, text, is_system=False):
    return {"sender": sender, "timestamp_utc": ts, "text": text, "is_system": is_system}


def _joke_names(proj):
    return [j["name"] for j in proj["jokes"]]


def _arc(proj, arc_type):
    return next(a for a in proj["arcs"] if a["type"] == arc_type)


# 1 -------------------------------------------------------------------------- #
def test_admissible_table():
    cutoff = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    cases = [
        ("2025-05-01T10:00:00Z", True),  # before
        ("2025-06-01T00:00:00Z", True),  # equal (inclusive)
        ("2025-07-01T10:00:00Z", False),  # after
        # offset-aware month-boundary: = 2025-01-31T22:30:00Z, before cutoff
        ("2025-02-01T00:30:00+02:00", True),
        ("2025-05-01T10:00:00", False),  # naive -> reject
        ("2025-05-01", False),  # bare date-only -> reject
        ("2025-05", False),  # month-only -> reject
        ("2025-13", False),  # invalid month (month-only shape) -> reject
        (None, False),  # missing -> reject
        ("garbage", False),  # malformed -> reject
    ]
    for ts, expected in cases:
        assert _admissible(ts, cutoff) is expected, f"{ts!r} -> expected {expected}"
    # A valid-timestamp is_system row: _admissible judges the timestamp only.
    assert _admissible("2025-05-01T10:00:00Z", cutoff) is True
    # all-evidence (cutoff None) admits any exact tz-aware instant.
    assert _admissible("2030-01-01T00:00:00Z", None) is True


# 2 -------------------------------------------------------------------------- #
def test_inadmissible_ts_dropped_e2e():
    """Missing-key / month-only / invalid-month rows are dropped THROUGH
    recompute_projection. Each prohibited row sits beside one legitimate
    same-pattern match, so a broken boundary would emit a joke (2 matches)."""
    nm = {"Alice": {}, "Bob": {}}
    legit = M("Alice", "2025-01-10T10:00:00Z", "taco tuesday")
    prohibited_rows = [
        {"sender": "Bob", "text": "taco time", "is_system": False},  # NO timestamp_utc
        M("Bob", "2025-01", "taco time"),  # month-only
        M("Bob", "2025-13", "taco time"),  # invalid month
    ]
    for prohibited in prohibited_rows:
        proj = recompute_projection([legit, prohibited], nm, None)  # must not raise
        assert TACO not in _joke_names(proj)  # dropped -> 1 match -> no joke

    # Positive control: two legitimate rows in one month -> joke DOES form.
    proj = recompute_projection(
        [legit, M("Alice", "2025-01-11T10:00:00Z", "taco time")], nm, None
    )
    assert TACO in _joke_names(proj)


# 3 -------------------------------------------------------------------------- #
def test_is_system_dropped_e2e():
    nm = {"Alice": {}, "Bob": {}}
    legit = M("Alice", "2025-01-10T10:00:00Z", "taco tuesday")
    sysrow = M("Bob", "2025-01-10T09:00:00Z", "taco time", is_system=True)
    proj = recompute_projection([legit, sysrow], nm, None)
    assert TACO not in _joke_names(proj)  # is_system dropped -> 1 match -> no joke

    proj = recompute_projection(
        [legit, M("Alice", "2025-01-11T10:00:00Z", "taco time")], nm, None
    )
    assert TACO in _joke_names(proj)  # positive control


# 4 -------------------------------------------------------------------------- #
def test_utc_bucketing_e2e():
    """+02:00 timestamp and a Z timestamp both fall in UTC January and bucket
    together; bounds are canonical-Z (proves convert-before-group)."""
    nm = {"Alice": {}}
    msgs = [
        M("Alice", "2025-02-01T00:30:00+02:00", "taco one"),  # = 2025-01-31T22:30:00Z
        M("Alice", "2025-01-31T23:00:00Z", "taco two"),
    ]
    proj = recompute_projection(msgs, nm, None)
    jokes = {j["name"]: j for j in proj["jokes"]}
    assert TACO in jokes  # both in UTC Jan -> 2 matches in one month -> joke
    j = jokes[TACO]
    assert j["first_seen"] == "2025-01" and j["last_seen"] == "2025-01"
    assert j["first_seen_at"] == "2025-01-31T22:30:00Z"  # converted + canonical Z
    assert j["last_observed_at"] == "2025-01-31T23:00:00Z"
    assert j["count"] == 2


# 5 -------------------------------------------------------------------------- #
def test_joke_discriminator():
    nm = {"Alice": {}}
    split = [
        M("Alice", "2025-01-10T10:00:00Z", "taco a"),
        M("Alice", "2025-02-10T10:00:00Z", "taco b"),
    ]
    assert TACO not in _joke_names(recompute_projection(split, nm, None))  # 1/month
    same = [
        M("Alice", "2025-01-10T10:00:00Z", "taco a"),
        M("Alice", "2025-01-11T10:00:00Z", "taco b"),
    ]
    assert TACO in _joke_names(recompute_projection(same, nm, None))  # 2 in one month


# 6 -------------------------------------------------------------------------- #
def test_joke_count_semantics():
    """2-Jan / 1-Feb: count=3 & last_observed_at=Feb (all matches through C),
    while legacy total_frequency=2 & last_seen=Jan (only Jan emitted)."""
    nm = {"Alice": {}}
    msgs = [
        M("Alice", "2025-01-10T10:00:00Z", "taco a"),
        M("Alice", "2025-01-20T10:00:00Z", "taco b"),
        M("Alice", "2025-02-05T10:00:00Z", "taco c"),  # Feb: 1 match -> not emitted
    ]
    j = {x["name"]: x for x in recompute_projection(msgs, nm, None)["jokes"]}[TACO]
    assert j["count"] == 3
    assert j["last_observed_at"] == "2025-02-05T10:00:00Z"
    assert j["first_seen_at"] == "2025-01-10T10:00:00Z"
    assert j["total_frequency"] == 2  # only Jan (2) emitted; Feb (1) below threshold
    assert j["first_seen"] == "2025-01" and j["last_seen"] == "2025-01"


# 7 -------------------------------------------------------------------------- #
def test_arc_discriminator_and_per_type_oracles():
    nm = {"Alice": {}, "Bob": {}, "Cara": {}, "Dave": {}}

    # -- Discriminator: two distinct monthly crews -> per-month path = 2 arcs;
    #    the global one-shot extractor MERGES them into 1 (the verified error).
    two_crew = [
        # Jan crew {Alice, Bob}; "who says no to this trade" hits 2 patterns = 1 event
        M("Alice", "2025-01-05T10:00:00Z", "who says no to this trade"),
        M("Bob", "2025-01-06T10:00:00Z", "i want to trade my rb"),
        M("Alice", "2025-01-07T10:00:00Z", "that was a robbery"),
        # Feb crew {Cara, Dave}
        M("Cara", "2025-02-05T10:00:00Z", "trade offer incoming"),
        M("Dave", "2025-02-06T10:00:00Z", "what a steal"),
        M("Cara", "2025-02-07T10:00:00Z", "package deal trade"),
    ]
    proj = recompute_projection(two_crew, nm, None)
    assert [
        (a["type"], tuple(a["participants"]), a["count"]) for a in proj["arcs"]
    ] == [
        ("trade_saga", ("Alice", "Bob"), 3),  # trade oracle: regardless-of-sender,
        (
            "trade_saga",
            ("Cara", "Dave"),
            3,
        ),  # multi-pattern message counts ONCE (3 not 4)
    ]
    # the rejected global one-shot: one merged arc over all senders
    g_pred = detect_predictions(two_crew)
    g_rel = detect_relationship_interactions(two_crew, nm)
    global_arcs = find_candidate_arcs(two_crew, g_pred, g_rel, nm)
    assert len(global_arcs) == 1
    assert sorted(global_arcs[0]["participants"]) == ["Alice", "Bob", "Cara", "Dave"]

    # -- Rivalry oracle: <=2h competitive adjacency, timestamped by later msg i.
    rivalry = [
        M("Alice", "2025-03-01T10:00:00Z", "you are trash"),
        M("Bob", "2025-03-01T10:30:00Z", "no you are garbage"),
        M("Alice", "2025-03-01T11:00:00Z", "worst team ever"),
        M("Bob", "2025-03-01T11:30:00Z", "such a fraud"),
    ]
    r = _arc(recompute_projection(rivalry, {"Alice": {}, "Bob": {}}, None), "rivalry")
    assert r["participants"] == ["Alice", "Bob"]
    assert r["count"] == 3  # transitions at i=1,2,3
    assert r["first_seen_at"] == "2025-03-01T10:30:00Z"  # later message
    assert r["last_observed_at"] == "2025-03-01T11:30:00Z"

    # -- Prediction oracle: one result per message for the selected top-author.
    preds = [
        M("Alice", "2025-04-01T10:00:00Z", "i guarantee we win"),
        M("Alice", "2025-04-01T10:05:00Z", "mark my words on this"),
        M("Alice", "2025-04-01T10:10:00Z", "calling it now for real"),
        M("Bob", "2025-04-01T10:15:00Z", "i guarantee nothing much"),
    ]
    p = _arc(
        recompute_projection(preds, {"Alice": {}, "Bob": {}}, None), "prediction_saga"
    )
    assert p["participants"] == ["Alice"]
    assert p["count"] == 3  # Alice's three predictions (Bob's not counted)
    assert p["first_seen_at"] == "2025-04-01T10:00:00Z"
    assert p["last_observed_at"] == "2025-04-01T10:10:00Z"


# 8 -------------------------------------------------------------------------- #
def test_key_moments_cap():
    """Same crew across two months -> 6 candidate key_moments capped to the
    first 5 (Jan-then-Feb). (e) count == 6 with exact Jan-first / Feb-last
    bounds; (f) exact ordered moment identities -- each moment keyed by
    (date, target_message_index) AND its complete ordered block payload -- so a
    reordered or wrong-block selection fails (the repeating (date, significance)
    pair, or mere trigger-text membership over OVERLAPPING blocks, would not)."""
    nm = {"Alice": {}, "Bob": {}}
    msgs = [
        M("Alice", "2025-01-05T10:00:00Z", "trade one here"),
        M("Bob", "2025-01-05T10:05:00Z", "trade two here"),
        M("Alice", "2025-01-05T10:10:00Z", "trade three here"),
        M("Bob", "2025-02-05T10:00:00Z", "trade four here"),
        M("Alice", "2025-02-05T10:05:00Z", "trade five here"),
        M("Bob", "2025-02-05T10:10:00Z", "trade six here"),
    ]
    trade = _arc(recompute_projection(msgs, nm, None), "trade_saga")
    # (e) same-crew two-month arc: count == 6, exact Jan-first / Feb-last bounds.
    assert trade["count"] == 6
    assert trade["first_seen_at"] == "2025-01-05T10:00:00Z"
    assert trade["last_observed_at"] == "2025-02-05T10:10:00Z"
    # (f) exact ordered moment identities (capped at 5, Jan-then-Feb).
    km = trade["key_moments"]
    assert len(km) == 5
    assert [(k["date"], k["target_message_index"]) for k in km] == [
        ("2025-01", 0),
        ("2025-01", 1),
        ("2025-01", 2),
        ("2025-02", 0),
        ("2025-02", 1),
    ]
    assert [k["significance"] for k in km] == ["Trade discussion"] * 5
    # Complete ordered block payloads (sender, text, timestamp) per moment. The
    # windows OVERLAP (km[0] and km[1] both contain "trade one here"), so mere
    # text membership survives a block swap -- assert the exact windows so a
    # wrong-block-with-right-index fails.
    blocks = [
        [(b["sender"], b["text"], b["timestamp"]) for b in k["block"]] for k in km
    ]
    assert blocks == [
        [
            ("Alice", "trade one here", "2025-01-05T10:00:00Z"),
            ("Bob", "trade two here", "2025-01-05T10:05:00Z"),
        ],
        [
            ("Alice", "trade one here", "2025-01-05T10:00:00Z"),
            ("Bob", "trade two here", "2025-01-05T10:05:00Z"),
            ("Alice", "trade three here", "2025-01-05T10:10:00Z"),
        ],
        [
            ("Alice", "trade one here", "2025-01-05T10:00:00Z"),
            ("Bob", "trade two here", "2025-01-05T10:05:00Z"),
            ("Alice", "trade three here", "2025-01-05T10:10:00Z"),
        ],
        [
            ("Bob", "trade four here", "2025-02-05T10:00:00Z"),
            ("Alice", "trade five here", "2025-02-05T10:05:00Z"),
        ],
        [
            ("Bob", "trade four here", "2025-02-05T10:00:00Z"),
            ("Alice", "trade five here", "2025-02-05T10:05:00Z"),
            ("Bob", "trade six here", "2025-02-05T10:10:00Z"),
        ],
    ]


# 9 -------------------------------------------------------------------------- #
def test_bounds_vs_samples():
    """>=4 qualifying events -> full-set count/bounds, samples stay at legacy
    cap (trade key_moments = trade_msgs[:3])."""
    nm = {"Alice": {}, "Bob": {}}
    msgs = [
        M("Alice", "2025-01-01T10:00:00Z", "trade one"),
        M("Bob", "2025-01-01T11:00:00Z", "trade two"),
        M("Alice", "2025-01-01T12:00:00Z", "trade three"),
        M("Bob", "2025-01-01T13:00:00Z", "trade four"),
    ]
    trade = _arc(recompute_projection(msgs, nm, None), "trade_saga")
    assert trade["count"] == 4
    assert len(trade["key_moments"]) == 3  # legacy sample cap, not 4
    assert trade["first_seen_at"] == "2025-01-01T10:00:00Z"
    assert trade["last_observed_at"] == "2025-01-01T13:00:00Z"


# 10 ------------------------------------------------------------------------- #
def test_tie_order_preservation():
    """Two trade arcs tied on narrative_potential, encounter order reversed vs
    alphabetical -> legacy (encounter / insertion) order preserved."""
    nm = {"Zeb": {}, "Yan": {}, "Al": {}, "Bo": {}}
    msgs = [
        M("Zeb", "2025-01-05T10:00:00Z", "trade talk here"),  # Jan crew {Yan, Zeb}
        M("Yan", "2025-01-06T10:00:00Z", "trade talk here"),
        M("Zeb", "2025-01-07T10:00:00Z", "trade talk here"),
        M("Al", "2025-02-05T10:00:00Z", "trade talk here"),  # Feb crew {Al, Bo}
        M("Bo", "2025-02-06T10:00:00Z", "trade talk here"),
        M("Al", "2025-02-07T10:00:00Z", "trade talk here"),
    ]
    proj = recompute_projection(msgs, nm, None)
    assert [tuple(a["participants"]) for a in proj["arcs"]] == [
        ("Yan", "Zeb"),  # Jan crew first despite alphabetical ordering to the contrary
        ("Al", "Bo"),
    ]
    assert (
        proj["arcs"][0]["narrative_potential"] == proj["arcs"][1]["narrative_potential"]
    )


# 11 ------------------------------------------------------------------------- #
def test_noninterference_and_positive_oracle():
    """Byte-identical at cutoff C under dominating post-cutoff evidence -- for
    the RIGHT reason: first prove the evidence is detector-active."""
    nm = {"Alice": {}, "Bob": {}, "Cara": {}, "Dave": {}}
    C = datetime(2025, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    base = [
        M("Alice", "2025-01-05T10:00:00Z", "who says no to this trade"),
        M("Bob", "2025-01-06T10:00:00Z", "i want to trade my rb"),
        M("Alice", "2025-01-07T10:00:00Z", "that was a robbery"),
    ]
    # Dominating post-cutoff evidence: a bigger, DISTINCT crew after C.
    evidence = [
        M("Cara", "2025-03-01T10:00:00Z", "trade offer one"),
        M("Dave", "2025-03-02T10:00:00Z", "trade offer two"),
        M("Cara", "2025-03-03T10:00:00Z", "trade offer three"),
        M("Dave", "2025-03-04T10:00:00Z", "trade offer four"),
    ]
    # (b) detector-active: the evidence genuinely changes the all-evidence result
    assert recompute_projection(base + evidence, nm, None) != recompute_projection(
        base, nm, None
    )
    # (c) noninterference: excluded at cutoff C -> byte-identical
    assert recompute_projection(base + evidence, nm, C) == recompute_projection(
        base, nm, C
    )
    # (d) positive oracle: base @ C is a specific, non-empty structure
    arcs = recompute_projection(base, nm, C)["arcs"]
    assert [(a["type"], tuple(a["participants"]), a["count"]) for a in arcs] == [
        ("trade_saga", ("Alice", "Bob"), 3)
    ]


# 12 ------------------------------------------------------------------------- #
def test_purity_and_no_disk_reads(monkeypatch):
    """The parity gate is non-tautological: recompute_projection reads NO disk
    artifact (else it could read the committed answer). Plus input purity."""
    nm = {"Alice": {}, "Bob": {}}
    msgs = [
        M("Alice", "2025-01-05T10:00:00Z", "who says no to this trade"),
        M("Bob", "2025-01-06T10:00:00Z", "i want to trade my rb"),
        M("Alice", "2025-01-07T10:00:00Z", "that was a robbery"),
    ]
    msgs_before = copy.deepcopy(msgs)
    nm_before = copy.deepcopy(nm)

    def _boom(*a, **k):
        raise AssertionError("recompute_projection performed a disk read")

    monkeypatch.setattr(rp, "load_json", _boom)
    monkeypatch.setattr(builtins, "open", _boom)
    monkeypatch.setattr(pathlib.Path, "open", _boom)
    result = recompute_projection(msgs, nm, None)  # must not touch disk
    monkeypatch.undo()

    assert result["arcs"]  # produced a real projection
    assert msgs == msgs_before  # inputs unmutated
    assert nm == nm_before


# 13 ------------------------------------------------------------------------- #
def test_subsecond_bounds_roundtrip():
    """_iso_z retains microseconds when present; bounds round-trip sub-second,
    while microsecond==0 stays second-precision (no ``.000000``)."""
    nm = {"Alice": {}}
    subsec = [
        M("Alice", "2025-01-10T10:00:00.123456Z", "taco one"),
        M("Alice", "2025-01-10T10:00:00.654321Z", "taco two"),
    ]
    j = {x["name"]: x for x in recompute_projection(subsec, nm, None)["jokes"]}[TACO]
    assert j["first_seen_at"] == "2025-01-10T10:00:00.123456Z"
    assert j["last_observed_at"] == "2025-01-10T10:00:00.654321Z"

    whole = [
        M("Alice", "2025-01-10T10:00:00Z", "taco one"),
        M("Alice", "2025-01-11T10:00:00Z", "taco two"),
    ]
    j2 = {x["name"]: x for x in recompute_projection(whole, nm, None)["jokes"]}[TACO]
    assert j2["first_seen_at"] == "2025-01-10T10:00:00Z"  # no fractional suffix


# 14 ------------------------------------------------------------------------- #
def test_verify_pass_and_fail_paths():
    """Machine parity gate: 0 on PASS, 1 on FAIL, both driven in-memory (no
    disk). Partial legacy injection is a contract error."""
    nm = {"Alice": {}, "Bob": {}}
    msgs = [
        M("Alice", "2025-01-05T10:00:00Z", "who says no to this trade"),
        M("Bob", "2025-01-06T10:00:00Z", "i want to trade my rb"),
        M("Alice", "2025-01-07T10:00:00Z", "that was a robbery"),
    ]
    proj = recompute_projection(msgs, nm, None)
    # Legacy answer == the projection with added fields stripped + legacy-only
    # fields restored (status on arcs, still_active on jokes).
    legacy_arcs = [
        {**rp._strip(a, rp._ADDED_ARC_FIELDS), "status": "building"}
        for a in proj["arcs"]
    ]
    legacy_jokes = [
        {**rp._strip(j, rp._ADDED_JOKE_FIELDS), "still_active": True}
        for j in proj["jokes"]
    ]
    assert (
        rp._verify(
            messages=msgs,
            name_map=nm,
            legacy_arcs=legacy_arcs,
            legacy_jokes=legacy_jokes,
        )
        == 0
    )
    # FAIL path: a bogus legacy arcs list cannot match -> exit 1.
    assert (
        rp._verify(
            messages=msgs,
            name_map=nm,
            legacy_arcs=[{"type": "nope"}],
            legacy_jokes=legacy_jokes,
        )
        == 1
    )
    with pytest.raises(ValueError):
        rp._verify(
            messages=msgs, name_map=nm, legacy_arcs=legacy_arcs, legacy_jokes=None
        )


# 15 ------------------------------------------------------------------------- #
def test_senderless_trade_raises_count():
    """(a) A senderless trade message is a trade EVENT (raises count) but never
    a participant (participants derive from senders & members)."""
    nm = {"Alice": {}, "Bob": {}}
    base = [
        M("Alice", "2025-01-05T10:00:00Z", "trade talk here"),
        M("Bob", "2025-01-06T10:00:00Z", "trade talk here"),
        M("Alice", "2025-01-07T10:00:00Z", "trade talk here"),
    ]
    a0 = _arc(recompute_projection(base, nm, None), "trade_saga")
    assert a0["count"] == 3 and tuple(a0["participants"]) == ("Alice", "Bob")
    senderless = {
        "sender": None,
        "timestamp_utc": "2025-01-08T10:00:00Z",
        "text": "trade offer",
        "is_system": False,
    }
    a1 = _arc(recompute_projection(base + [senderless], nm, None), "trade_saga")
    assert a1["count"] == 4  # senderless message raised the event count
    assert tuple(a1["participants"]) == ("Alice", "Bob")  # participants unchanged
    assert a1["last_observed_at"] == "2025-01-08T10:00:00Z"


# 16 ------------------------------------------------------------------------- #
def test_rivalry_over_2h_excluded():
    """(b) A competitive message >2h after its predecessor is NOT a rivalry
    transition -- excluded from count and bounds (mirrors the <=2h gap)."""
    nm = {"Alice": {}, "Bob": {}}
    base = [
        M("Alice", "2025-03-01T10:00:00Z", "you are trash"),
        M("Bob", "2025-03-01T10:30:00Z", "no you are garbage"),
        M("Alice", "2025-03-01T11:00:00Z", "worst team ever"),
        M("Bob", "2025-03-01T11:30:00Z", "such a fraud"),
    ]
    r0 = _arc(recompute_projection(base, nm, None), "rivalry")
    assert r0["count"] == 3
    assert r0["last_observed_at"] == "2025-03-01T11:30:00Z"
    # 5th competitive message 2.5h after the 4th -> transition excluded.
    plus = base + [M("Alice", "2025-03-01T14:00:00Z", "still trash to me")]
    r1 = _arc(recompute_projection(plus, nm, None), "rivalry")
    assert r1["count"] == 3  # the >2h transition is excluded; count unchanged
    assert r1["last_observed_at"] == "2025-03-01T11:30:00Z"


# 17 ------------------------------------------------------------------------- #
def test_fourth_prediction_beyond_sample_cap():
    """(d) A 4th prediction by the top author pushes count past the 3 sampled
    key_moments (samples cap at 3; count does not)."""
    nm = {"Alice": {}, "Bob": {}}
    msgs = [
        M("Alice", "2025-04-01T10:00:00Z", "i guarantee we win"),
        M("Alice", "2025-04-01T10:05:00Z", "mark my words on this"),
        M("Alice", "2025-04-01T10:10:00Z", "calling it now for real"),
        M("Alice", "2025-04-01T10:15:00Z", "i bet we finish first"),  # 4th
        M("Bob", "2025-04-01T10:20:00Z", "i guarantee nothing here"),
    ]
    p = _arc(recompute_projection(msgs, nm, None), "prediction_saga")
    assert p["participants"] == ["Alice"]
    assert p["count"] == 4  # all four Alice predictions counted
    assert len(p["key_moments"]) == 3  # sample cap, strictly below count
    assert p["first_seen_at"] == "2025-04-01T10:00:00Z"
    assert p["last_observed_at"] == "2025-04-01T10:15:00Z"


# 18 ------------------------------------------------------------------------- #
def test_joke_noninterference():
    """(g) Jokes are recomputed from messages: post-cutoff joke evidence is
    detector-active at all-evidence yet byte-identical at cutoff C."""
    nm = {"Alice": {}}
    C = datetime(2025, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    base = [
        M("Alice", "2025-01-10T10:00:00Z", "taco time"),
        M("Alice", "2025-01-11T10:00:00Z", "taco tuesday"),
    ]
    evidence = [
        M("Alice", "2025-03-01T10:00:00Z", "taco again"),
        M("Alice", "2025-03-02T10:00:00Z", "taco more"),
    ]
    # detector-active FIRST: the post-cutoff taco messages change all-evidence.
    assert recompute_projection(base + evidence, nm, None) != recompute_projection(
        base, nm, None
    )
    # noninterference: excluded at cutoff C -> byte-identical.
    assert recompute_projection(base + evidence, nm, C) == recompute_projection(
        base, nm, C
    )
    # positive oracle: base @ C has the taco joke, count 2, Jan bounds.
    j = {x["name"]: x for x in recompute_projection(base, nm, C)["jokes"]}[TACO]
    assert j["count"] == 2
    assert j["last_observed_at"] == "2025-01-11T10:00:00Z"


# 19 ------------------------------------------------------------------------- #
def test_arc_group_id_unique_in_snapshot():
    """(1) Every arc in one snapshot carries a distinct arc_group_id."""
    nm = {"Alice": {}, "Bob": {}, "Cara": {}, "Dave": {}}
    msgs = [
        M("Alice", "2025-01-05T10:00:00Z", "who says no to this trade"),
        M("Bob", "2025-01-06T10:00:00Z", "i want to trade my rb"),
        M("Alice", "2025-01-07T10:00:00Z", "that was a robbery"),
        M("Cara", "2025-02-05T10:00:00Z", "trade offer incoming"),
        M("Dave", "2025-02-06T10:00:00Z", "what a steal"),
        M("Cara", "2025-02-07T10:00:00Z", "package deal trade"),
    ]
    gids = [a["arc_group_id"] for a in recompute_projection(msgs, nm, None)["arcs"]]
    assert len(gids) == 2
    assert len(set(gids)) == len(gids)  # all unique


# 20 ------------------------------------------------------------------------- #
def test_arc_group_id_stable_across_cutoffs():
    """(2) arc_group_id is cutoff-INVARIANT: the same crew across two months
    keeps one id even as the evidence window (count/bounds) changes with the
    cutoff -- not mere same-input determinism."""
    nm = {"Alice": {}, "Bob": {}}
    msgs = [
        # Jan crew {Alice, Bob}
        M("Alice", "2025-01-05T10:00:00Z", "trade one here"),
        M("Bob", "2025-01-06T10:00:00Z", "trade two here"),
        M("Alice", "2025-01-07T10:00:00Z", "trade three here"),
        # Feb: the SAME crew
        M("Bob", "2025-02-05T10:00:00Z", "trade four here"),
        M("Alice", "2025-02-06T10:00:00Z", "trade five here"),
        M("Bob", "2025-02-07T10:00:00Z", "trade six here"),
    ]
    C = datetime(2025, 2, 1, 0, 0, 0, tzinfo=timezone.utc)  # between the two months
    a_jan = _arc(recompute_projection(msgs, nm, C), "trade_saga")
    a_all = _arc(recompute_projection(msgs, nm, None), "trade_saga")
    # the evidence window genuinely differs across the cutoff...
    assert a_jan["count"] == 3 and a_all["count"] == 6
    assert a_jan["last_observed_at"] == "2025-01-07T10:00:00Z"
    assert a_all["last_observed_at"] == "2025-02-07T10:00:00Z"
    # ...yet the group id is identical (cutoff-invariant).
    assert a_jan["arc_group_id"] == a_all["arc_group_id"] == "trade_saga::Alice|Bob"


# 21 ------------------------------------------------------------------------- #
def test_arc_group_id_changes_on_growth():
    """(3) Participant growth changes arc_group_id even where the lossy arc_id
    collides ({B,M,O,Z} vs {B,M,O,S,Z} -- the non-injectivity the fix targets)."""
    nm = {"Brent": {}, "Matt": {}, "Oscar": {}, "Zach": {}, "Sacko": {}}

    def arc_for(members):
        msgs = [
            M(m, f"2025-01-0{i + 1}T10:00:00Z", "trade talk here")
            for i, m in enumerate(members)
        ]
        return _arc(recompute_projection(msgs, nm, None), "trade_saga")

    a4 = arc_for(["Brent", "Matt", "Oscar", "Zach"])
    a5 = arc_for(["Brent", "Matt", "Oscar", "Sacko", "Zach"])
    assert a4["arc_id"] == a5["arc_id"]  # lossy slug (participants[:3]+month) collides
    assert a4["arc_group_id"] != a5["arc_group_id"]  # non-lossy key separates them
    assert a5["arc_group_id"] == "trade_saga::Brent|Matt|Oscar|Sacko|Zach"


# 22 ------------------------------------------------------------------------- #
def test_arc_group_id_no_collision():
    """(4) Distinct crews never collide; the key is a pure function of
    (type, sorted participants), order-insensitive; and a token that is empty or
    bears a reserved separator (":"/"|") fails CLOSED rather than colliding."""
    assert _arc_group_id("trade_saga", ["Bob", "Alice"]) == "trade_saga::Alice|Bob"
    assert _arc_group_id("trade_saga", ["Alice", "Bob"]) == _arc_group_id(
        "trade_saga", ["Bob", "Alice"]
    )  # order-insensitive
    assert _arc_group_id("trade_saga", ["Alice", "Bob"]) != _arc_group_id(
        "rivalry", ["Alice", "Bob"]
    )  # type participates
    assert _arc_group_id("trade_saga", ["Alice", "Bob"]) != _arc_group_id(
        "trade_saga", ["Cara", "Dave"]
    )  # crew participates
    # Adversarial: any token bearing a reserved separator ("|" or ":") RAISES
    # rather than emitting a colliding id. ":" is banned FULLY (not just "::"):
    # single colons straddling the type/crew seam re-form "::" ambiguously --
    # ("a:", ["b"]) and ("a", [":b"]) both assemble "a:::b".
    assert _arc_group_id("trade_saga", ["A", "B"]) == "trade_saga::A|B"  # control
    with pytest.raises(ValueError):
        _arc_group_id("trade_saga", ["A|B"])  # pipe in a participant
    with pytest.raises(ValueError):
        _arc_group_id("trade_saga", ["A:B"])  # colon in a participant
    with pytest.raises(ValueError):
        _arc_group_id("trade:saga", ["Alice", "Bob"])  # colon in the type
    with pytest.raises(ValueError):
        _arc_group_id("a:", ["b"])  # cross-seam ":::" -> "a:::b"
    with pytest.raises(ValueError):
        _arc_group_id("a", [":b"])  # cross-seam ":::" -> "a:::b"
    # Degenerate empties also collided pre-guard: ("a", []) and ("a", [""]) both
    # emit "a::". An empty participant LIST stays valid (-> "type::"); an empty
    # participant TOKEN or an empty arc TYPE fails closed.
    assert _arc_group_id("a", []) == "a::"  # empty list: valid, no participants
    with pytest.raises(ValueError):
        _arc_group_id("a", [""])  # empty participant token (would collide with [])
    with pytest.raises(ValueError):
        _arc_group_id("", ["Alice"])  # empty arc type


# 23 ------------------------------------------------------------------------- #
def test_verify_cli_wiring(monkeypatch):
    """main() must sys.exit(_verify()) -- a regression to a bare _verify() call
    would swallow a real FAIL and exit 0. Drive main() with a stubbed _verify."""
    monkeypatch.setattr(sys, "argv", ["recompute_projection.py", "--verify"])
    monkeypatch.setattr(rp, "_verify", lambda *a, **k: 1)
    with pytest.raises(SystemExit) as exc:
        rp.main()
    assert exc.value.code == 1  # FAIL code propagated through sys.exit
    monkeypatch.setattr(rp, "_verify", lambda *a, **k: 0)
    with pytest.raises(SystemExit) as exc:
        rp.main()
    assert exc.value.code == 0  # PASS code propagated too
