"""The judgment gate's own acceptance test.

The load-bearing half is the RED proof: the gate must FAIL on the committed
arithmetic ranking_record.json (G1, G2, G4). An instrument that cannot fail on
a known-bad sample is measuring nothing. The synthetic tests then pin each
check's firing condition individually, and the private-state tests prove the
full gate end to end where the frozen state exists.
"""

import json
from pathlib import Path

import pytest

from scripts.verify_ranking_judgment import (
    baseline_order,
    check_g1_no_arithmetic,
    check_g2_deviation_with_cause,
    check_g3_contender_sanity,
    check_g4_evidence_breadth,
    main,
    run_gate,
)

REPO = Path(__file__).resolve().parents[2]
EDITION_DIR = REPO / "content" / "editions" / "2025-wk01-recap"
OLD_RECORD = EDITION_DIR / "ranking_record.json"
NEW_RECORD = EDITION_DIR / "ranking_judgment.json"
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
    # one swap = two deviating positions: still a spreadsheet
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
    # A is prior-season #1 and won; E and F are bottom-3 priors (n-2 = 4)
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


# ------------------------------------------------- committed artifacts (RED) --


def test_gate_goes_red_on_the_arithmetic_record():
    """THE acceptance test: G1, G2 and G4 must all fire on the known-bad
    committed artifact. If any passes, the instrument is broken."""
    record = _load(OLD_RECORD)
    assert not check_g1_no_arithmetic(record)[0]
    assert not check_g2_deviation_with_cause(record)[0]
    assert not check_g4_evidence_breadth(record)[0]
    # and the two that legitimately hold on the old artifact still hold
    assert check_g3_contender_sanity(record)[0]


def test_judgment_record_passes_static_checks():
    record = _load(NEW_RECORD)
    for check in (
        check_g1_no_arithmetic,
        check_g2_deviation_with_cause,
        check_g3_contender_sanity,
        check_g4_evidence_breadth,
    ):
        ok, detail = check(record)
        assert ok, f"{check.__name__}: {detail}"


def test_judgment_record_orders_twelve_teams():
    record = _load(NEW_RECORD)
    assert sorted(p["rank"] for p in record["positions"]) == list(range(1, 13))
    assert len({p["roster_id"] for p in record["positions"]}) == 12


# ------------------------------------------------------- full gate (private) --


@_needs_private
def test_full_gate_green_on_judgment_record():
    assert main(["--record", str(NEW_RECORD)]) == 0


@_needs_private
def test_full_gate_red_on_arithmetic_record():
    assert main(["--record", str(OLD_RECORD)]) == 1


@_needs_private
def test_g5_fires_on_a_fabricated_citation():
    record = _load(NEW_RECORD)
    record["positions"][0]["reasoning"]["evidence"][0]["fact_ids"].append(
        "fact:0000000000000000000000000000000000000000000000000000000000000000"
    )
    passed, results = run_gate(record)
    assert not passed
    g5 = dict((name, (ok, detail)) for name, ok, detail in results)["G5 resolution"]
    assert not g5[0] and "do not resolve" in g5[1]


# ------------------------------------------------------- G0 completeness --


from scripts.verify_ranking_judgment import check_g0_structure  # noqa: E402


def test_g0_fails_when_a_position_is_removed():
    """Blake's probe, made permanent: an 11-team ranking must never be GREEN."""
    record = _load(NEW_RECORD)
    del record["positions"][4]
    ok, detail = check_g0_structure(record)
    assert not ok and "11 positions" in detail


def test_g0_fails_on_duplicate_roster():
    record = _load(NEW_RECORD)
    record["positions"][3]["roster_id"] = record["positions"][2]["roster_id"]
    ok, detail = check_g0_structure(record)
    assert not ok and "duplicate roster" in detail


def test_g0_fails_on_duplicate_rank():
    record = _load(NEW_RECORD)
    record["positions"][5]["rank"] = record["positions"][6]["rank"]
    ok, detail = check_g0_structure(record)
    assert not ok and "not exactly 1-12" in detail


def test_g0_fails_on_missing_rank():
    record = _load(NEW_RECORD)
    del record["positions"][0]["rank"]
    ok, detail = check_g0_structure(record)
    assert not ok


def test_g0_fails_on_unknown_roster_outside_baseline():
    record = _load(NEW_RECORD)
    record["positions"][7]["roster_id"] = "99"
    ok, detail = check_g0_structure(record)
    assert not ok and "not in the record's baseline" in detail


def test_g0_passes_on_the_committed_judgment_record():
    ok, detail = check_g0_structure(_load(NEW_RECORD))
    assert ok, detail


@_needs_private
def test_full_gate_red_when_a_position_is_removed(tmp_path):
    record = _load(NEW_RECORD)
    del record["positions"][0]
    mutated = tmp_path / "incomplete.json"
    mutated.write_text(json.dumps(record), encoding="utf-8")
    assert main(["--record", str(mutated)]) == 1
