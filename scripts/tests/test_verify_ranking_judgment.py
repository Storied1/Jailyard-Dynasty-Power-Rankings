"""The judgment gate's acceptance tests.

The load-bearing half is the RED proof: the gate must FAIL on the arithmetic
ranking_record.json (G1, G2, G4). An instrument that cannot fail on a
known-bad sample is measuring nothing. The synthetic fixtures pin each
check's firing condition; the private-state tests prove the full gate end to
end where the frozen state exists.
"""

import json
from pathlib import Path

import pytest

from scripts.verify_ranking_judgment import (
    baseline_order,
    check_g0_structure,
    check_g1_no_arithmetic,
    check_g2_deviation_with_cause,
    check_g3_contender_sanity,
    check_g4_evidence_breadth,
    main,
    run_gate,
)

REPO = Path(__file__).resolve().parents[2]
ARITHMETIC_RECORD = (
    REPO / "content" / "editions" / "2025-wk01-recap" / "ranking_record.json"
)
PRIVATE_STATE = REPO / "private_editions" / "2025-wk01-recap" / "state.json"

_needs_private = pytest.mark.skipif(
    not PRIVATE_STATE.exists(),
    reason="gitignored private edition state absent (present only locally)",
)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- synthetic --


def _team(rank, rid, wins, pf, prior_rank, outcome="W", families=None, reason=None):
    return {
        "rank": rank,
        "roster_id": rid,
        "team_name": f"Team {rid}",
        "record": f"{wins}-{1 - wins}",
        "points_for": pf,
        "points_against": 100.0,
        "deviation": {"reason": reason},
        "reasoning": {
            "argument": reason or "",
            "evidence": [
                {"family": fam, "fact_ids": [f"fact:{rid}-{fam}"]}
                for fam in (families or [])
            ],
        },
        "evidence": {
            "week_result": {"fact_id": f"fact:{rid}-wk", "outcome": outcome},
            "prior_season": {"all_games_rank": prior_rank, "fact_ids": []},
        },
    }


def _synthetic(order=None, families=("week_result", "chat_message"), reasons=True):
    """Six-team record. Arithmetic baseline (wins desc, pf desc): A,B,C,D,E,F."""
    spec = [  # rid, wins, pf, prior_rank, outcome
        ("A", 1, 150.0, 1, "W"),
        ("B", 1, 140.0, 3, "W"),
        ("C", 1, 130.0, 2, "W"),
        ("D", 0, 145.0, 4, "L"),
        ("E", 0, 120.0, 5, "L"),
        ("F", 0, 110.0, 6, "L"),
    ]
    by_rid = {s[0]: s for s in spec}
    order = order or ["A", "B", "C", "D", "E", "F"]
    base = {rid: i + 1 for i, rid in enumerate(["A", "B", "C", "D", "E", "F"])}
    positions = []
    for rank, rid in enumerate(order, start=1):
        _, wins, pf, prior, outcome = by_rid[rid]
        deviates = rank != base[rid]
        positions.append(
            _team(
                rank,
                rid,
                wins,
                pf,
                prior,
                outcome,
                families=families,
                reason=(f"{rid} earned it" if (reasons and deviates) else None),
            )
        )
    return {"edition_id": "synthetic", "positions": positions}


def green_record():
    """A full 12-team record that passes G0-G4: three reasoned, fact-bound
    deviations from the arithmetic baseline; the prior-season champion (a
    winner) ranked above every bottom-3 prior finisher."""
    rids = [str(i) for i in range(1, 13)]
    published = ["1", "2", "3", "4", "7", "5", "6", "8", "9", "10", "11", "12"]
    base = {rid: i + 1 for i, rid in enumerate(rids)}
    positions = []
    for rank, rid in enumerate(published, start=1):
        i = int(rid)
        wins = 1 if i <= 6 else 0
        deviates = rank != base[rid]
        positions.append(
            _team(
                rank,
                rid,
                wins,
                160.0 - i,
                i,  # rid 1 is the returning champion and won
                "W" if wins else "L",
                families=("week_result", "prior_season", "chat_message"),
                reason=("schedule-quality call" if deviates else None),
            )
        )
        positions[-1]["baseline_rank"] = base[rid]
    return {
        "edition_id": "synthetic",
        "positions": positions,
        "baseline": [{"rank": base[r], "roster_id": r} for r in rids],
    }


def test_green_record_passes_g0_through_g4():
    rec = green_record()
    for check in (
        check_g0_structure,
        check_g1_no_arithmetic,
        check_g2_deviation_with_cause,
        check_g3_contender_sanity,
        check_g4_evidence_breadth,
    ):
        ok, detail = check(rec)
        assert ok, f"{check.__name__}: {detail}"


def test_baseline_order_is_wins_then_points_then_roster_id():
    rec = _synthetic()
    assert baseline_order(rec["positions"]) == ["A", "B", "C", "D", "E", "F"]


def test_g1_fails_on_pure_arithmetic_order():
    ok, detail = check_g1_no_arithmetic(_synthetic())
    assert not ok and "no judgment" in detail


def test_g1_passes_on_deviated_order():
    ok, _ = check_g1_no_arithmetic(_synthetic(order=["A", "D", "B", "C", "E", "F"]))
    assert ok


def test_g2_fails_below_three_deviations():
    ok, detail = check_g2_deviation_with_cause(
        _synthetic(order=["A", "C", "B", "D", "E", "F"])
    )
    assert not ok and "need >= 3" in detail


def test_g2_fails_on_unreasoned_deviation():
    rec = _synthetic(order=["A", "D", "B", "C", "E", "F"], reasons=False)
    ok, detail = check_g2_deviation_with_cause(rec)
    assert not ok and "no stated reason" in detail


def test_g2_fails_when_reason_cites_no_facts():
    rec = _synthetic(order=["A", "D", "B", "C", "E", "F"], families=())
    ok, detail = check_g2_deviation_with_cause(rec)
    assert not ok and "cites no facts" in detail


def test_g2_fails_on_misstated_baseline_rank():
    rec = _synthetic(order=["A", "D", "B", "C", "E", "F"])
    rec["positions"][1]["baseline_rank"] = 2  # D's true baseline is 4
    ok, detail = check_g2_deviation_with_cause(rec)
    assert not ok and "baseline" in detail


def test_g2_passes_with_reasoned_fact_bound_deviations():
    ok, detail = check_g2_deviation_with_cause(
        _synthetic(order=["A", "D", "B", "C", "E", "F"])
    )
    assert ok, detail


def test_g3_fails_when_winning_champion_ranks_below_bottom3():
    rec = _synthetic(order=["B", "E", "A", "C", "D", "F"])
    ok, detail = check_g3_contender_sanity(rec)
    assert not ok and "prior-season #1" in detail


def test_g3_passes_when_champion_above_all_bottom3():
    ok, _ = check_g3_contender_sanity(_synthetic(order=["A", "D", "B", "C", "E", "F"]))
    assert ok


def test_g3_vacuous_when_champion_lost():
    rec = _synthetic(order=["B", "E", "A", "C", "D", "F"])
    for p in rec["positions"]:
        if p["roster_id"] == "A":
            p["evidence"]["week_result"]["outcome"] = "L"
    ok, _ = check_g3_contender_sanity(rec)
    assert ok


def test_g3_fails_closed_on_missing_prior_season():
    rec = _synthetic()
    rec["positions"][0]["evidence"]["prior_season"] = {}
    ok, detail = check_g3_contender_sanity(rec)
    assert not ok and "cannot be evaluated" in detail


def test_g4_fails_on_box_score_only_reasoning():
    ok, detail = check_g4_evidence_breadth(_synthetic(families=("week_result",)))
    assert not ok and "beyond the box score" in detail


def test_g4_ignores_families_with_empty_fact_ids():
    rec = _synthetic(families=("week_result", "chat_message"))
    for p in rec["positions"]:
        for e in p["reasoning"]["evidence"]:
            if e["family"] == "chat_message":
                e["fact_ids"] = []
    ok, _ = check_g4_evidence_breadth(rec)
    assert not ok


def test_g4_passes_on_two_families_one_beyond_box_score():
    ok, detail = check_g4_evidence_breadth(_synthetic())
    assert ok, detail


# ------------------------------------------------------- G0 completeness --


def test_g0_fails_when_a_position_is_removed():
    rec = green_record()
    del rec["positions"][4]
    ok, detail = check_g0_structure(rec)
    assert not ok and "11 positions" in detail


def test_g0_fails_on_duplicate_roster():
    rec = green_record()
    rec["positions"][3]["roster_id"] = rec["positions"][2]["roster_id"]
    ok, detail = check_g0_structure(rec)
    assert not ok and "duplicate roster" in detail


def test_g0_fails_on_duplicate_rank():
    rec = green_record()
    rec["positions"][5]["rank"] = rec["positions"][6]["rank"]
    ok, detail = check_g0_structure(rec)
    assert not ok and "not exactly 1-12" in detail


def test_g0_fails_on_missing_rank():
    rec = green_record()
    del rec["positions"][0]["rank"]
    ok, _ = check_g0_structure(rec)
    assert not ok


def test_g0_fails_on_unknown_roster_outside_baseline():
    rec = green_record()
    rec["positions"][7]["roster_id"] = "99"
    ok, detail = check_g0_structure(rec)
    assert not ok and "not in the record's baseline" in detail


# ------------------------------------------------- committed artifact (RED) --


def test_gate_goes_red_on_the_arithmetic_record():
    """G1, G2 and G4 must all fire on the arithmetic record. If any passes,
    the instrument is broken."""
    record = _load(ARITHMETIC_RECORD)
    assert not check_g1_no_arithmetic(record)[0]
    assert not check_g2_deviation_with_cause(record)[0]
    assert not check_g4_evidence_breadth(record)[0]
    # the two that legitimately hold on the arithmetic record still hold
    assert check_g0_structure(record)[0]
    assert check_g3_contender_sanity(record)[0]


# ------------------------------------------------------- full gate (private) --


@_needs_private
def test_full_gate_red_on_arithmetic_record():
    assert main(["--record", str(ARITHMETIC_RECORD)]) == 1


@_needs_private
def test_g5_fires_on_a_fabricated_citation():
    record = _load(ARITHMETIC_RECORD)
    record["positions"][0]["evidence"]["roster"]["fact_ids"].append(
        "fact:0000000000000000000000000000000000000000000000000000000000000000"
    )
    passed, results = run_gate(record)
    assert not passed
    g5 = {name: (ok, detail) for name, ok, detail in results}["G5 resolution"]
    assert not g5[0] and "do not resolve" in g5[1]
