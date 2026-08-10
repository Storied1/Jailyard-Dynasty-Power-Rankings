"""The judgment gate: proves a ranking contains judgment, not just arithmetic.

Every other gate in this repository measures provenance -- that a citation
resolves, that a cutoff held. None measures whether the ordering itself says
anything. This gate closes that hole, each check failing loudly by exit code:

  G0 STRUCTURE        Exactly 12 positions, ranks exactly 1-12, exactly 12
                      unique roster ids matching the record's baseline set.
                      A ranking that omits a franchise is not a ranking.

  G1 NO-ARITHMETIC    An ordering reproducible by sorting wins-then-points
                      contains no judgment. Fail.
  G2 DEVIATION+CAUSE  At least 3 positions must differ from the arithmetic
                      baseline, and every deviation must state a reason bound
                      to cited facts. Unreasoned reshuffling fails.
  G3 CONTENDER SANITY A prior-season champion that won this week cannot rank
                      below any team that finished bottom-3 last season.
                      (Champion = prior_season all_games_rank 1, recomputed
                      from admitted games; bottom-3 = all_games_rank >= n-2.)
  G4 EVIDENCE BREADTH Every position's reasoning must draw on >= 2 distinct
                      evidence families, >= 1 of which is not the week's box
                      score. A ranking justified only by what just happened
                      is autocomplete.
  G5 RESOLUTION       Every cited fact resolves in the edition's frozen state.
                      A state that cannot be loaded is a FAIL, never a skip --
                      a proof that cannot run must never report PASS.

Acceptance: run against the arithmetic ranking_record.json and this gate goes
RED on G1, G2 and G4 (see test_verify_ranking_judgment.py). An instrument that
cannot fail on a known-bad sample is measuring nothing.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# The week's box score. Everything else -- prior seasons, multi-year history,
# roster, draft, transactions, chat -- is evidence the box score cannot see.
BOX_SCORE_FAMILIES = {"week_result"}


def check_g0_structure(record):
    """Completeness is a GATE property, not a pytest property: a ranking that
    omits a franchise from a twelve-team league must go RED at the CLI, on
    every future run, not only under an artifact-specific test. Exactly 12
    positions, ranks exactly 1-12 with no duplicate or gap, exactly 12 unique
    roster ids, and — when the record carries its baseline block — exactly
    the baseline's franchise set (no unknown, no missing roster)."""
    positions = record.get("positions", [])
    problems = []
    if len(positions) != 12:
        problems.append(f"{len(positions)} positions (a 12-team league needs 12)")
    ranks = sorted(p.get("rank") for p in positions if p.get("rank") is not None)
    if ranks != list(range(1, 13)):
        problems.append(f"ranks are not exactly 1-12: {ranks}")
    rids = [str(p.get("roster_id")) for p in positions]
    dupes = sorted({r for r in rids if rids.count(r) > 1})
    if dupes:
        problems.append(f"duplicate roster id(s): {dupes}")
    if len(set(rids)) != 12:
        problems.append(f"{len(set(rids))} unique roster ids (need 12)")
    baseline = record.get("baseline")
    if baseline:
        want = {str(b.get("roster_id")) for b in baseline}
        unknown = sorted(set(rids) - want)
        missing = sorted(want - set(rids))
        if unknown:
            problems.append(f"roster id(s) not in the record's baseline: {unknown}")
        if missing:
            problems.append(f"baseline roster id(s) absent from positions: {missing}")
    if problems:
        return False, "; ".join(problems)
    return True, "12 positions, ranks 1-12, 12 unique rosters"


def _wins(position):
    return int(str(position.get("record", "0-0")).split("-")[0])


def baseline_order(positions):
    """The arithmetic ordering: wins desc, points_for desc, roster_id asc.

    Mirrors LeagueState.standings() exactly, including the string-ascending
    roster_id tiebreak -- the baseline must be THE precommitted rule, not a
    lookalike."""
    return [
        p["roster_id"]
        for p in sorted(
            positions,
            key=lambda p: (-_wins(p), -p.get("points_for", 0.0), str(p["roster_id"])),
        )
    ]


def ranked_order(positions):
    return [p["roster_id"] for p in sorted(positions, key=lambda p: p["rank"])]


def check_g1_no_arithmetic(record):
    positions = record["positions"]
    if ranked_order(positions) == baseline_order(positions):
        return False, (
            "ordering is exactly reproducible by sorting wins desc then "
            "points_for desc -- it contains no judgment"
        )
    return True, "ordering is not the arithmetic sort"


def check_g2_deviation_with_cause(record):
    positions = record["positions"]
    base_rank = {rid: i + 1 for i, rid in enumerate(baseline_order(positions))}
    problems = []
    deviations = 0
    for p in sorted(positions, key=lambda p: p["rank"]):
        rid, rank = p["roster_id"], p["rank"]
        stated = p.get("baseline_rank")
        if stated is not None and stated != base_rank[rid]:
            problems.append(
                f"roster {rid}: states baseline_rank {stated} but the "
                f"arithmetic baseline puts it at {base_rank[rid]}"
            )
        if rank == base_rank[rid]:
            continue
        deviations += 1
        reason = (p.get("deviation") or {}).get("reason")
        cited = [
            e
            for e in (p.get("reasoning") or {}).get("evidence", [])
            if e.get("fact_ids")
        ]
        if not (isinstance(reason, str) and reason.strip()):
            problems.append(
                f"roster {rid}: rank {rank} deviates from baseline "
                f"{base_rank[rid]} with no stated reason"
            )
        elif not cited:
            problems.append(f"roster {rid}: deviation reason cites no facts")
    if deviations < 3:
        problems.append(
            f"only {deviations} position(s) deviate from the arithmetic "
            "baseline (need >= 3): the ranking is a reshuffled spreadsheet, "
            "not an opinion"
        )
    if problems:
        return False, "; ".join(problems)
    return True, f"{deviations} deviations, every one reasoned and fact-bound"


def check_g3_contender_sanity(record):
    positions = record["positions"]
    n = len(positions)
    prior = {
        p["roster_id"]: (p.get("evidence", {}).get("prior_season") or {})
        for p in positions
    }
    missing = [rid for rid, pr in prior.items() if not pr.get("all_games_rank")]
    if missing:
        return False, (
            f"prior_season evidence missing for roster(s) {sorted(missing)}; "
            "contender sanity cannot be evaluated, which is a FAIL, not a skip"
        )
    rank_of = {p["roster_id"]: p["rank"] for p in positions}
    bottom3 = {rid for rid, pr in prior.items() if pr["all_games_rank"] >= n - 2}
    problems = []
    for p in positions:
        pr = prior[p["roster_id"]]
        won = (p.get("evidence", {}).get("week_result") or {}).get("outcome") == "W"
        if pr["all_games_rank"] == 1 and won:
            below = sorted(
                rid for rid in bottom3 if rank_of[rid] < rank_of[p["roster_id"]]
            )
            if below:
                problems.append(
                    f"roster {p['roster_id']} (prior-season #1) won this week "
                    f"yet ranks below bottom-3 finisher(s) {below}"
                )
    if problems:
        return False, "; ".join(problems)
    return True, "no winning champion ranks below a bottom-3 prior finisher"


def check_g4_evidence_breadth(record):
    problems = []
    for p in sorted(record["positions"], key=lambda p: p["rank"]):
        families = {
            e["family"]
            for e in (p.get("reasoning") or {}).get("evidence", [])
            if e.get("fact_ids")
        }
        beyond = families - BOX_SCORE_FAMILIES
        if len(families) < 2 or not beyond:
            problems.append(
                f"rank {p['rank']} (roster {p['roster_id']}): "
                f"{sorted(families) if families else 'no'} evidence "
                "families cited (need >= 2, >= 1 beyond the box score)"
            )
    if problems:
        return False, "; ".join(problems)
    return True, "every position cites >= 2 families, >= 1 beyond the box score"


def _collect_ids(node, out):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "fact_id" and isinstance(value, str):
                out.add(value)
            elif key == "fact_ids" and isinstance(value, list):
                out.update(value)
            else:
                _collect_ids(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_ids(item, out)


def check_g5_resolution(record):
    try:  # package form first -- one module identity under pytest and direct run
        from scripts.compile_state import load_compiled_state
        from scripts.eval_arms import rehydrate_state
    except ImportError:  # pragma: no cover - direct-run fallback
        from compile_state import load_compiled_state
        from eval_arms import rehydrate_state

    try:
        state = rehydrate_state(load_compiled_state(record["edition_id"]))
    except Exception as exc:
        return False, (
            f"frozen state for {record['edition_id']} cannot be loaded ({exc}); "
            "a proof that cannot run must never report PASS"
        )
    cited = set()
    _collect_ids(record, cited)
    available = {f.fact_id for f in state.admitted}
    missing = sorted(cited - available)
    if missing:
        return False, (
            f"{len(missing)} cited fact_id(s) do not resolve in the frozen "
            f"state: {missing[:3]}"
        )
    return True, f"all {len(cited)} citations resolve in the frozen state"


CHECKS = [
    ("G0 structure", check_g0_structure),
    ("G1 no-arithmetic", check_g1_no_arithmetic),
    ("G2 deviation-with-cause", check_g2_deviation_with_cause),
    ("G3 contender-sanity", check_g3_contender_sanity),
    ("G4 evidence-breadth", check_g4_evidence_breadth),
    ("G5 resolution", check_g5_resolution),
]


def run_gate(record):
    """Run every gate check. Returns (all_passed, [(name, ok, detail)])."""
    results = [(name, *check(record)) for name, check in CHECKS]
    return all(ok for _, ok, _ in results), results


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify_ranking_judgment.py")
    ap.add_argument(
        "--record",
        required=True,
        help="path to the ranking record to gate",
    )
    a = ap.parse_args(argv)
    record = load_json(Path(a.record), required=True)
    passed, results = run_gate(record)
    for name, ok, detail in results:
        print(f"{name}: {'PASS' if ok else 'FAIL'} -- {detail}")
    print(
        f"\n{'GREEN' if passed else 'RED'}: {a.record} "
        f"({sum(ok for _, ok, _ in results)}/{len(results)} checks passed)"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
