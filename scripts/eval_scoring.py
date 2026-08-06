"""Precommitted scoring rules and fixed aggregation. K3.6 of plan 562e90d.

All three scoring rules are DISTANCES -- lower is always better -- and
combine_trials reports median-with-range per arm. The K3.8 comparison form is
fixed before any arm runs: full_rich vs minimal_legal, and each ablation vs
full_rich, on median claim score with inter-trial ranges shown. The lift
THRESHOLD is deliberately not precommitted -- that judgment is Blake's.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.claims_ledger import (  # noqa: E402
        EDITION_IDS,
        load_claims,
        resolve_claims,
        save_claims,
    )
    from scripts.decision_history import (
        SEALS_ROOT,  # noqa: E402
        SealedDecision,
        verify_tree,
    )
    from scripts.eval_arms import ARMS  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from claims_ledger import (  # noqa: E402
        EDITION_IDS,
        load_claims,
        resolve_claims,
        save_claims,
    )
    from decision_history import SEALS_ROOT, SealedDecision, verify_tree  # noqa: E402
    from eval_arms import ARMS  # noqa: E402

AGGREGATION_ORDER = ("claim", "team", "edition", "trial", "arm")
MIN_TRIALS_NONDETERMINISTIC = 3

# Module globals main() reads AT CALL TIME so tests can redirect the ledger and
# the receipts tree. None means the respective real root.
CLAIMS_DEFAULT_ROOT = None
DECISIONS_DEFAULT_ROOT = None


def score_claim(claim):
    """The three precommitted rules, all distances (lower is better):
    ordinal_rank -> Spearman footrule per position; binary_probability ->
    Brier; bounded_quantity -> absolute error normalized by the stated bound.
    None when the claim is unresolved."""
    if claim.outcome is None:
        return None
    if claim.claim_type == "ordinal_rank":
        return abs(claim.assertion - claim.outcome)
    if claim.claim_type == "binary_probability":
        return (claim.assertion - claim.outcome) ** 2
    if claim.claim_type == "bounded_quantity":
        if not claim.bound:
            raise ValueError("bounded_quantity scoring requires the stated bound")
        return abs(claim.assertion - claim.outcome) / claim.bound
    raise ValueError(f"unknown claim_type {claim.claim_type!r}")


def aggregate(claims):
    """Fixed order claim -> team -> edition -> trial -> arm. Unresolved claims
    are EXCLUDED from the mean and COUNTED -- more unresolved claims never
    improve an arm; unresolvable (resolution_failed) claims are reported
    separately, never silently dropped."""
    scores = []
    unresolved = unresolvable = 0
    for c in claims:
        s = score_claim(c)
        if s is not None:
            scores.append(s)
        elif c.resolution_failed:
            unresolvable += 1
        else:
            unresolved += 1
    return {
        "scored": len(scores),
        "unresolved": unresolved,
        "unresolvable": unresolvable,
        "mean_score": (sum(scores) / len(scores)) if scores else None,
    }


def combine_trials(trials, runner_kind):
    """Median-with-range across trial mean scores. A model arm with fewer than
    three trials cannot be reported as a measurement."""
    if runner_kind == "model" and len(trials) < MIN_TRIALS_NONDETERMINISTIC:
        raise ValueError(
            f"a nondeterministic arm requires >= {MIN_TRIALS_NONDETERMINISTIC} trials; "
            f"got {len(trials)}"
        )
    means = [t["mean_score"] for t in trials if t["mean_score"] is not None]
    if not means:
        return {
            "median": None,
            "range": None,
            "trials": len(trials),
            "unresolved": sum(t["unresolved"] for t in trials),
            "unresolvable": sum(t["unresolvable"] for t in trials),
        }
    return {
        "median": statistics.median(means),
        "range": (min(means), max(means)),
        "trials": len(trials),
        "unresolved": sum(t["unresolved"] for t in trials),
        "unresolvable": sum(t["unresolvable"] for t in trials),
    }


def _all_seals(arm_id, root):
    """Every seal of an arm across trials -- no cutoff filter."""
    out = []
    for p in sorted(Path(root).glob(f"*/{arm_id}/trial*/*.seal.json")):
        out.append(SealedDecision(**json.loads(p.read_text(encoding="utf-8"))))
    return out


def _grading_state(resolve_on):
    """The grading state: state_at(2025, resolve_on, league_private) from the
    FULL fact store, computed at scoring time. Structurally unavailable to
    every decision runner -- never compiled into content/editions/, never in a
    bundle. Tests monkeypatch this symbol; production reads the real store."""
    from scripts.temporal_state import state_at

    return state_at(2025, resolve_on, "league_private")


def main():
    import argparse

    ap = argparse.ArgumentParser(prog="eval_scoring.py")
    ap.add_argument("--report", action="store_true", required=True)
    ap.add_argument("--arm")
    a = ap.parse_args()
    claims_root = CLAIMS_DEFAULT_ROOT
    dec_root = (
        DECISIONS_DEFAULT_ROOT if DECISIONS_DEFAULT_ROOT is not None else SEALS_ROOT
    )
    claims = load_claims(root=claims_root)
    if not claims:
        # stderr: K3.7 Step 5 redirects stdout into scores.json, and a diagnostic
        # written there would become the artifact.
        print(
            "FAIL no claims found; --report must not emit an empty measurement",
            file=sys.stderr,
        )
        return 1
    # A report that silently omits an arm, edition, or trial reads as a complete
    # measurement of a smaller experiment. Refuse instead. The census is over
    # COMPLETE CHAINS from the run receipts (replacement trials mean the valid
    # ids need not be 1..N -- chains {1,3,4} with 2 abandoned is a valid grid).
    from scripts.eval_arms import complete_chains

    expected = set()
    for arm in ARMS:
        need = (
            1
            if ARMS[arm]["runner_kind"] == "deterministic"
            else MIN_TRIALS_NONDETERMINISTIC
        )
        chains = complete_chains(arm, dec_root)
        if len(chains) < need:
            print(
                f"FAIL {arm}: {len(chains)} complete chains, {need} required",
                file=sys.stderr,
            )
            return 1
        expected |= {(arm, ed, t) for ed in EDITION_IDS for t in chains[:need]}
    # Only claims belonging to VERIFIED sealed cells count: a claim whose
    # (arm, edition, trial) has no seal -- or whose seal fails verify_tree --
    # is orphan/corrupt evidence and is excluded before the census.
    checked, failures = verify_tree(dec_root)
    if failures:
        print(
            f"FAIL kernel verifier: {len(failures)} bad seal(s); scoring refuses",
            file=sys.stderr,
        )
        return 1
    sealed = {
        (s.arm_id, s.edition_id, s.trial_id)
        for arm in ARMS
        for s in _all_seals(arm, dec_root)
    }
    claims = [c for c in claims if (c.arm_id, c.edition_id, c.trial_id) in sealed]
    present = {(c.arm_id, c.edition_id, c.trial_id) for c in claims}
    if not a.arm and (missing := sorted(expected - present)):
        print(
            f"FAIL incomplete experiment, {len(missing)} cells missing: {missing[:5]}",
            file=sys.stderr,
        )
        return 1
    if a.arm:
        claims = [c for c in claims if c.arm_id == a.arm]
    # Scoring-time grading: claims resolving past the recap cutoff are graded
    # against the grading state HERE -- immutable events appended to the ledger,
    # then the current view reloaded.
    due = [c for c in claims if c.outcome is None and not c.resolution_failed]
    if due:
        events = []
        for resolve_on in sorted({c.resolution_rule["resolve_on"] for c in due}):
            batch = [c for c in due if c.resolution_rule["resolve_on"] == resolve_on]
            gs = _grading_state(resolve_on)
            events += resolve_claims(batch, gs, resolution_run_id="scoring-pass")
        if events:
            save_claims(events, root=claims_root, season=2025)
            claims = [
                c
                for c in load_claims(root=claims_root)
                if (c.arm_id, c.edition_id, c.trial_id) in sealed
                and (not a.arm or c.arm_id == a.arm)
            ]
    # Comparable-scores gate: every compared arm needs >=1 resolved-and-scored
    # claim, or the report is a null measurement dressed as one. Refuse BEFORE
    # any by_arm output reaches stdout.
    for arm in sorted({c.arm_id for c in claims}):
        if not any(score_claim(c) is not None for c in claims if c.arm_id == arm):
            print(
                f"FAIL {arm}: zero resolved-and-scored claims; no lift verdict "
                "is derivable from an unresolved grid",
                file=sys.stderr,
            )
            return 1
    by_arm = {}
    for arm in sorted({c.arm_id for c in claims}):
        trials = [
            aggregate([c for c in claims if c.arm_id == arm and c.trial_id == t])
            for t in sorted({c.trial_id for c in claims if c.arm_id == arm})
        ]
        by_arm[arm] = combine_trials(trials, runner_kind=ARMS[arm]["runner_kind"])
    print(json.dumps(by_arm, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
