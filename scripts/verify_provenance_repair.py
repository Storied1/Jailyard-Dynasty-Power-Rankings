"""No-write proof that the 2025 provenance repair leaked nothing backward.

The admission rule (`known_at <= cutoff`) is not a proof of this. Re-asserting it
only shows the filter ran; it says nothing about whether the VALUES that filter
admitted were knowable then. A fact can pass admission and still carry a 2026
reading -- that is precisely how `franchise_identity` came to be dated by its
download instant while every mechanical check stayed green.

So each proof below re-derives from an INDEPENDENT source and compares:

  P1  admission        every admitted fact's known_at is at or before the cutoff
  P2  no capture dates no admitted fact is dated by a download instant
  P3  names            every admitted team_name is re-read out of the 2025-08-02
                       git blob -- NOT out of the policy artifact and NOT out of
                       the 2026 capture. If a name only ever existed in 2026,
                       this fails.
  P4  rosters          the recap's membership equals week 1's snapshot EXACTLY.
                       A week-2+ transaction leaking backward changes this set.
  P5  no collateral    untouched families still match the counts recorded in the
                       committed pre-repair census, family for family.
  P6  boundary         one second before each anchor, the facts are gone.
  P7  planted future   a fact dated mid-season is refused by the recap state.

Exit 0 = every proof passed. Exit 1 = at least one failed, itemized.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_store import FactStore  # noqa: E402
    from scripts.franchise_provenance import fold, parse_attestation  # noqa: E402
    from scripts.temporal_state import state_at  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_store import FactStore  # noqa: E402
    from franchise_provenance import fold, parse_attestation  # noqa: E402
    from temporal_state import state_at  # noqa: E402

from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CENSUS_PATH = ROOT / "content" / "governance" / "fact_provenance_census.v1.json"
POLICY_PATH = ROOT / "content" / "governance" / "franchise_identity_2025.v1.json"

EDITIONS = ("2025-preseason", "2025-wk01-preview", "2025-wk01-recap")
# The families this repair touches. Everything else must be provably unmoved.
REPAIRED = {"franchise_identity", "roster_membership"}


def _descriptor(edition_id):
    return load_json(
        ROOT / "content" / "editions" / edition_id / "descriptor.json", required=True
    )


def _public_facts(season=2025):
    return FactStore(ROOT / "data" / "facts" / f"{season}.jsonl").load()


def _git_blob(commit, path):
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",  # git speaks UTF-8; cp1252 would read as corruption
        check=True,
        cwd=ROOT,
    ).stdout


def run_proofs(facts=None):
    """Returns (results, failures). Each result is (proof_id, detail)."""
    facts = _public_facts() if facts is None else facts
    results, failures = [], []

    def check(pid, ok, detail):
        results.append((pid, "PASS" if ok else "FAIL", detail))
        if not ok:
            failures.append(f"{pid}: {detail}")

    def unavailable(pid, detail):
        """A proof whose INPUT is missing did not pass -- it did not run.

        Reporting PASS here is the self-passing-instrument defect: the same shape
        as eval_contrast.family_counts zeroing its census after the first
        ArmUnavailable and still answering confidently. UNAVAILABLE is counted as
        a failure so `no backward leak proven` can never print off a proof that
        inspected nothing.
        """
        results.append((pid, "UNAVAILABLE", detail))
        failures.append(f"{pid}: {detail}")

    states = {
        eid: state_at(2025, _descriptor(eid)["cutoff_utc"], "public", facts=facts)
        for eid in EDITIONS
    }

    # --- P1 admission ------------------------------------------------------
    bad = [
        (eid, f.fact_type, f.known_at)
        for eid, st in states.items()
        for f in st.admitted
        if f.known_at > st.cutoff
    ]
    check(
        "P1",
        not bad,
        f"{sum(len(s.admitted) for s in states.values())} admitted, "
        f"{len(bad)} past their cutoff",
    )

    # --- P2 no capture-instant dating --------------------------------------
    dated_by_capture = [
        (f.fact_type, f.known_at_basis)
        for f in facts
        if f.known_at_basis == "legacy-capture-v1"
    ]
    check(
        "P2",
        not dated_by_capture,
        f"{len(dated_by_capture)} facts still dated by a download instant",
    )

    # --- P3 names re-read from the 2025 blob --------------------------------
    att = load_json(POLICY_PATH, required=True)["display"]["attestation"]
    attested = parse_attestation(_git_blob(att["commit"], att["path"]))
    attested_names = {fold(v["team_name"]) for v in attested.values()}
    unbacked = []
    for eid, st in states.items():
        for f in st.by_type("franchise_identity"):
            name = f.payload.get("team_name")
            if name is None:
                continue  # spine reading: declares its own unavailability
            if fold(name) not in attested_names:
                unbacked.append((eid, name))
    named = sum(
        1
        for st in states.values()
        for f in st.by_type("franchise_identity")
        if f.payload.get("team_name")
    )
    check(
        "P3",
        not unbacked,
        f"{named} admitted team names, {len(unbacked)} not present in the "
        f"{att['instant'][:10]} blob",
    )

    # --- P4 recap rosters equal week 1 exactly ------------------------------
    snap = load_json(ROOT / "data/2025/fantasy_rosters/week1.json", required=False)
    if snap is None:
        unavailable(
            "P4",
            "week-1 snapshot absent (data/*/fantasy_rosters/ is gitignored) — the "
            "roster proof did NOT run; rehydrate the snapshot to prove it",
        )
    else:
        expected = {
            str(r["roster_id"]): {str(p) for p in (r.get("players") or [])}
            for r in snap["rosters"]
        }
        admitted = {}
        for f in states["2025-wk01-recap"].by_type("roster_membership"):
            if f.payload["on_roster"]:
                admitted.setdefault(f.payload["roster_id"], set()).add(
                    f.payload["player_id"]
                )
        drift = {r: (len(expected[r] ^ admitted.get(r, set()))) for r in expected}
        drift = {r: n for r, n in drift.items() if n}
        check(
            "P4",
            not drift,
            f"{sum(len(v) for v in expected.values())} week-1 players; "
            f"{len(drift)} rosters differ from the snapshot",
        )

    # --- P5 untouched families unmoved vs the committed pre-repair census ----
    census = load_json(CENSUS_PATH, required=True)
    recorded = census["store_census"]["public"]
    live = {}
    for f in facts:
        live[f.fact_type] = live.get(f.fact_type, 0) + 1
    moved = [
        (t, recorded[t]["facts"], live.get(t, 0))
        for t in recorded
        if t not in REPAIRED and live.get(t, 0) != recorded[t]["facts"]
    ]
    check(
        "P5",
        not moved,
        f"{len(recorded) - len(REPAIRED & set(recorded))} untouched public "
        f"families compared against census v1; {len(moved)} moved",
    )

    # --- P6 boundary: one second before each anchor -------------------------
    policy = load_json(POLICY_PATH, required=True)
    boundary = []
    for label, instant, expect in (
        ("spine", policy["spine"]["instant"], 0),
        ("display", policy["display"]["attestation"]["instant"], 0),
    ):
        just_before = instant[:17] + f"{int(instant[17:19]) - 1:02d}" + instant[19:]
        st = state_at(2025, just_before, "public", facts=facts)
        named_here = [
            f for f in st.by_type("franchise_identity") if f.payload.get("team_name")
        ]
        got = (
            len(st.by_type("franchise_identity"))
            if label == "spine"
            else len(named_here)
        )
        if got != expect:
            boundary.append(f"{label}: {got} facts one second before {instant}")
    check(
        "P6",
        not boundary,
        "; ".join(boundary)
        or "zero franchise facts before the draft anchor; zero names before the attestation",
    )

    # --- P7 a planted mid-season fact is refused ----------------------------
    from copy import copy

    victim = next(f for f in facts if f.fact_type == "franchise_identity")
    planted = copy(victim)
    object.__setattr__(planted, "known_at", "2025-12-01T00:00:00.000000Z")
    object.__setattr__(planted, "fact_id", "fact:planted-future-control")
    object.__setattr__(planted, "supersedes", None)
    poisoned = state_at(
        2025,
        _descriptor("2025-wk01-recap")["cutoff_utc"],
        "public",
        facts=facts + [planted],
    )
    leaked = any(f.fact_id == "fact:planted-future-control" for f in poisoned.admitted)
    check(
        "P7",
        not leaked,
        (
            "a franchise fact dated 2025-12-01 was refused by the week-1 recap state"
            if not leaked
            else "PLANTED FUTURE FACT WAS ADMITTED"
        ),
    )

    return results, failures


def main():
    ap = argparse.ArgumentParser(prog="verify_provenance_repair.py")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    a = ap.parse_args()
    results, failures = run_proofs()
    if a.json:
        print(
            json.dumps(
                {
                    "proofs": [
                        {"id": p, "verdict": v, "detail": d} for p, v, d in results
                    ],
                    "failures": failures,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for pid, verdict, detail in results:
            print(f"{verdict} {pid}  {detail}")
        print(
            "\nno backward leak proven" if not failures else "\n" + "\n".join(failures)
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
