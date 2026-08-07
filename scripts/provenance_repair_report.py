"""Whole-surface answer to fact_provenance_census.v1, family by family.

The census named nine registered families. This report gives every one of them a
disposition -- repaired, left alone because it was already honest, or explicitly
NOT repairable from anything on disk. "Not repairable" is a result here, not a
gap: the mission's rule is that a fact whose true date cannot be sourced does not
get an invented one, so a family that cannot be honestly dated is recorded as
such and left refused.

This report does NOT supersede the census. `fact_provenance_census.v1.json` is a
read-only record of the pre-repair state and stays exactly as committed.

Live numbers (fact counts, known_at bases, per-edition admissions, leak-proof
verdicts) are computed at emit time. Only the dispositions are editorial, and
each states what it does not fix.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_store import FactStore  # noqa: E402
    from scripts.temporal_state import state_at  # noqa: E402
    from scripts.verify_provenance_repair import (
        CENSUS_PATH,  # noqa: E402
        EDITIONS,
        _descriptor,
        _public_facts,
        run_proofs,
    )
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_store import FactStore  # noqa: E402
    from temporal_state import state_at  # noqa: E402
    from verify_provenance_repair import (  # noqa: E402
        CENSUS_PATH,
        EDITIONS,
        _descriptor,
        _public_facts,
        run_proofs,
    )

from shared import load_json, save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "content" / "governance" / "fact_provenance_repair.v1.json"

DISPOSITIONS = {
    "franchise_identity": (
        "REPAIRED",
        "Split into the two assertions it always conflated. The roster/owner SPINE "
        "is dated 2025-07-10 from data/2025/draft_picks.json, where every pick "
        "carries roster_id AND picked_by; the binding is one-to-one over all 12 "
        "rosters and is cross-checked against the capture before being dated. The "
        "DISPLAY layer (username, team_name) is dated 2025-08-02T20:30:09Z, the "
        "author instant of commit d464f8c, the earliest tracked commit whose blob "
        "attests every captured username -- an OBSERVED upper bound on when the "
        "names were knowable, established by the same git method "
        "legacy_capture_instants.v1 already uses. The two are emitted as a "
        "supersession chain, so a cutoff between them yields spine-only with names "
        "declared unavailable. Values always come from the authoritative Sleeper "
        "capture; the attestation supplies a date and nothing else, and a name "
        "that does not match it exactly stays unavailable.",
        "It cannot recover a team name that CHANGED during 2025. If a franchise "
        "renamed after 2025-08-02, this dates the post-rename name at the "
        "pre-rename instant. Nothing on disk can detect that -- Sleeper serves no "
        "name-change history and the repo holds no later 2025 attestation -- so "
        "the bound is stated rather than hidden. It also leaves the 2026 lane "
        "untouched, where capture instant and knowledge instant genuinely "
        "coincide because the capture is prospective.",
    ),
    "roster_membership": (
        "REPAIRED, PARTIALLY -- post-kickoff only",
        "Was declared unsourced with zero facts. Now sourced from the captured "
        "weekly snapshots under data/2025/fantasy_rosters/, each dated at its "
        "week's conclusion under the same legacy-week-conclusion-v1 policy the "
        "result families use. Departures are emitted explicitly rather than "
        "implied, because the reducer is `latest` and an implied departure would "
        "leave rosters that only ever grow. A snapshot that is derived, "
        "uncaptured, or carries no usable instant is refused outright.",
        "It gives NO pre-kickoff anchor, so the preseason and preview states still "
        "admit zero roster facts. That refusal stands and is asserted by test. "
        "Separately: the census proposed draft_picks.json as an opening-roster "
        "anchor, and that does not hold. This is a DYNASTY league "
        "(data/2025/league.json settings.type=2, draft_rounds=6), so 72 picks over "
        "12 teams is a rookie draft, not a roster.",
    ),
    "draft_pick": (
        "NOT REPAIRABLE FROM DISK -- coarse, and honestly so",
        "Unchanged. All 72 picks share the draft-window-v1 instant.",
        "Per-pick instants are not in the captured file -- no pick carries a "
        "timestamp. Refining this needs a re-capture of Sleeper's draft endpoint "
        "with pick metadata, which is new evidence, not a re-derivation. Pick 72 "
        "is still treated as knowable at the moment pick 1 was.",
    ),
    "matchup_result": (
        "UNCHANGED -- already honest",
        "Conservative LATE bound: the Tuesday after the week's final game. Erring "
        "late is fail-closed -- it can withhold a fact from a state, never leak "
        "one in early.",
        "Finer per-game instants are derivable from the schedules parquet and were "
        "deliberately not adopted. Refining this can only admit facts EARLIER, "
        "which is the one direction that can leak, and nothing needs it.",
    ),
    "historical_matchup": (
        "UNCHANGED -- already honest",
        "The same conservative-late policy applied to 2022-2024.",
        "The same deliberate coarsening as matchup_result.",
    ),
    "nfl_game": (
        "UNCHANGED -- the refusal is correct",
        "Postgame context only, dated at each week's conclusion. This is why "
        "nfl_game is absent from the preseason and preview states and present only "
        "at the recap.",
        "Pregame context -- injuries, spreads, weather as knowable BEFORE kickoff "
        "-- stays unavailable. Dating it needs an approved schedule-publication "
        "policy that does not exist. Correct behaviour, not a gap in the data.",
    ),
    "chat_message": (
        "UNCHANGED -- already honest",
        "known_at is each message's own timestamp. The largest honestly-dated "
        "evidence body in the store, and untouched by this repair.",
        "Nothing. It was never mis-dated.",
    ),
    "transaction": (
        "UNCHANGED -- already honest",
        "known_at is each transaction's own completion instant, with 514 distinct "
        "times of day across 717 facts.",
        "Nothing. It was never mis-dated.",
    ),
    "schedule_pairing": (
        "NOT REPAIRED -- needs a decision, not data",
        "Still unavailable, still zero facts.",
        "Design section 1: stripping outcomes from a completed weekly packet "
        "proves concealment, not pregame availability. Admitting it needs either "
        "an independently qualified schedule source, which is not captured for "
        "2025, or an approved versioned availability policy. That is a governance "
        "call for Blake; inventing one is exactly the defect this repair removes.",
    ),
}


def build_report(season=2025):
    public = _public_facts(season)
    facts = list(public)
    private_path = ROOT / "private_facts" / f"{season}.jsonl"
    if private_path.exists():
        facts += FactStore(private_path).load()

    census = load_json(CENSUS_PATH, required=True)
    live = load_json(ROOT / "data" / "facts" / f"{season}.report.json", required=True)

    counts, bases = {}, {}
    for f in facts:
        counts[f.fact_type] = counts.get(f.fact_type, 0) + 1
        bucket = bases.setdefault(f.fact_type, {})
        bucket[f.known_at_basis] = bucket.get(f.known_at_basis, 0) + 1

    per_family = {}
    for family, (disposition, does, does_not) in DISPOSITIONS.items():
        v1 = census["per_family_provenance"].get(family, {})
        per_family[family] = {
            "census_v1_honest": v1.get("honest"),
            "census_v1_defect": v1.get("defect"),
            "disposition": disposition,
            "what_the_repair_does": does,
            "what_it_deliberately_does_not_fix": does_not,
            "facts_now": counts.get(family, 0),
            "known_at_bases_now": dict(sorted(bases.get(family, {}).items())),
        }

    admitted = {}
    for eid in EDITIONS:
        state = state_at(season, _descriptor(eid)["cutoff_utc"], "public", facts=public)
        by = {}
        for f in state.admitted:
            by[f.fact_type] = by.get(f.fact_type, 0) + 1
        admitted[eid] = dict(sorted(by.items()))

    results, failures = run_proofs(facts=public)
    dishonest_now = sum(1 for fam in bases if "legacy-capture-v1" in bases[fam])
    return {
        "report_id": "fact_provenance_repair.v1",
        "answers": census["census_id"],
        "kind": (
            "READ-ONLY REPORT. Answers fact_provenance_census.v1 family by family. "
            "Does NOT supersede it -- v1 stands as the pre-repair record."
        ),
        "season": season,
        "surface_summary": {
            "families_registered": census["surface_summary"]["families_registered"],
            "families_dishonestly_dated_before": census["surface_summary"][
                "families_dishonestly_dated"
            ],
            "families_dishonestly_dated_after": dishonest_now,
            "families_populated_before": census["surface_summary"][
                "families_populated"
            ],
            "families_populated_after": len([f for f, n in counts.items() if n]),
            "families_still_unavailable": sorted(live["unavailable"]),
        },
        "admitted_by_edition_after": admitted,
        "leak_proofs": [{"id": p, "verdict": v, "detail": d} for p, v, d in results],
        "leak_proof_failures": failures,
        "per_family": per_family,
    }


def main():
    ap = argparse.ArgumentParser(prog="provenance_repair_report.py")
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--write", action="store_true", help="write the tracked artifact")
    a = ap.parse_args()
    report = build_report(a.season)
    if a.write:
        save_json_canonical(REPORT_PATH, report)
        print(REPORT_PATH)
    print(json.dumps(report["surface_summary"], indent=2, sort_keys=True))
    for family, row in sorted(report["per_family"].items()):
        print(f"  {family:<20} {row['disposition']}  ({row['facts_now']} facts)")
    return 1 if report["leak_proof_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
