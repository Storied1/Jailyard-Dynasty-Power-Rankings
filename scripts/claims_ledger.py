"""Scoreable claims with resolution rules fixed at claim time. K3.1 of plan 562e90d.

Append-only JSONL ledger at data/claims/{season}.jsonl -- deliberately OUTSIDE
content/decisions/, so the ledger can never become a fifth file species in the
seal directory. save_claims is the ONE writer for Claims AND ResolutionEvents;
load_claims collapses resolution events onto their claims by claim_id (latest
resolved_at wins), so a re-run appends a new event and changes the current view
exactly once, never double-counts.
"""

import json
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_schema import canonical_instant, fact_hash  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import canonical_instant, fact_hash  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CLAIMS_ROOT = ROOT / "data" / "claims"

CLAIM_TYPES = {"ordinal_rank", "binary_probability", "bounded_quantity"}
HORIZONS = {"next_week", "rest_of_season", "championship", "dynasty"}

# Declared HERE, beside the claim record, and imported by K3.5's driver and
# K3.6's report -- the K3.7 shell loop must not be the only place the edition
# list exists.
EDITION_IDS = ("2025-preseason", "2025-wk01-preview", "2025-wk01-recap")


@dataclass(frozen=True)
class Claim:
    claim_id: str
    target: str
    claim_type: str
    horizon: str
    assertion: object
    confidence: float
    decisive_evidence: list
    contrary_evidence: str
    cutoff_utc: str
    state_hash: str
    arm_id: str
    trial_id: int
    decision_run_id: str
    edition_id: str
    resolution_rule: dict
    bound: float | None = None
    outcome: object = None
    score: float | None = None
    resolution_failed: bool = False


@dataclass(frozen=True)
class ResolutionEvent:
    """Immutable resolution record. Appending a new event is the ONLY way a
    claim's current view changes; the claim record itself is never rewritten."""

    claim_id: str
    outcome: object
    score: float | None
    resolved_at: str
    resolution_run_id: str
    resolution_failed: bool = False


CLAIM_FIELDS = tuple(f.name for f in fields(Claim))
EVENT_FIELDS = tuple(f.name for f in fields(ResolutionEvent))


def make_claim(**kw):
    """Build a Claim; claim_id is deterministic over the identity fields so a
    byte-identical claim re-made is the SAME claim, never a duplicate."""
    identity = {
        k: kw.get(k)
        for k in (
            "target",
            "claim_type",
            "horizon",
            "assertion",
            "cutoff_utc",
            "arm_id",
            "trial_id",
            "edition_id",
            "decision_run_id",
        )
    }
    claim_id = "claim-" + fact_hash(identity)[len("sha256:") :][:16]
    return Claim(claim_id=claim_id, **kw)


def validate_claim(claim) -> list:
    """Empty list means valid. Every rule fails closed."""
    problems = []
    if claim.claim_type not in CLAIM_TYPES:
        problems.append(
            f"claim_type: {claim.claim_type!r} not in {sorted(CLAIM_TYPES)}"
        )
    if claim.horizon not in HORIZONS:
        problems.append(f"horizon: {claim.horizon!r} not in {sorted(HORIZONS)}")
    for name in (
        "target",
        "cutoff_utc",
        "state_hash",
        "arm_id",
        "decision_run_id",
        "edition_id",
    ):
        if not getattr(claim, name):
            problems.append(f"{name}: required")
    if not isinstance(claim.trial_id, int) or claim.trial_id < 1:
        problems.append("trial_id: must be an int >= 1")
    rule = claim.resolution_rule
    if not isinstance(rule, dict) or not {"rule", "source", "resolve_on"} <= set(rule):
        problems.append(
            "resolution_rule: requires {rule, source, resolve_on} fixed at claim time"
        )
    if claim.claim_type == "bounded_quantity" and claim.bound is None:
        problems.append(
            "bound: required for bounded_quantity (error normalized by stated bound)"
        )
    if claim.claim_type == "binary_probability" and not (
        isinstance(claim.assertion, (int, float)) and 0.0 <= claim.assertion <= 1.0
    ):
        problems.append("assertion: binary_probability must be within [0, 1]")
    return problems


def _season_of(records, season):
    if season is not None:
        return int(season)
    for r in records:
        if isinstance(r, Claim):
            return int(r.edition_id.split("-", 1)[0])
    raise ValueError(
        "save_claims cannot derive a season from a pure ResolutionEvent batch; pass season="
    )


def save_claims(records, root=None, season=None):
    """Append-only JSONL; records are Claims or ResolutionEvents -- the ONE
    writer for both. Batch sorted by (arm_id, edition_id, trial_id, claim_id)
    for claims, (claim_id, resolved_at) for events."""
    if not records:
        return None
    root = Path(root) if root is not None else CLAIMS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_season_of(records, season)}.jsonl"
    claims = sorted(
        (r for r in records if isinstance(r, Claim)),
        key=lambda c: (c.arm_id, c.edition_id, c.trial_id, c.claim_id),
    )
    events = sorted(
        (r for r in records if isinstance(r, ResolutionEvent)),
        key=lambda e: (e.claim_id, e.resolved_at),
    )
    if len(claims) + len(events) != len(records):
        raise TypeError("save_claims accepts only Claim and ResolutionEvent records")
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        for record in [*claims, *events]:
            kind = "claim" if isinstance(record, Claim) else "resolution_event"
            handle.write(
                json.dumps(
                    {"kind": kind, **asdict(record)},
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            )
    return path


def load_claims(root=None, arm_id=None, trial_id=None, current=True):
    """Read the ledger back. current=True collapses resolution events onto their
    claims (latest resolved_at wins); current=False returns the raw event log."""
    root = Path(root) if root is not None else CLAIMS_ROOT
    claims, events = [], []
    if root.exists():
        for path in sorted(root.glob("*.jsonl")):
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    doc = json.loads(line)
                    kind = doc.pop("kind")
                    if kind == "claim":
                        claims.append(Claim(**doc))
                    else:
                        events.append(ResolutionEvent(**doc))
    if not current:
        return events
    latest = {}
    for e in events:
        prior = latest.get(e.claim_id)
        if prior is None or e.resolved_at > prior.resolved_at:
            latest[e.claim_id] = e
    out = []
    for c in claims:
        e = latest.get(c.claim_id)
        if e is not None:
            c = Claim(
                **{
                    **asdict(c),
                    "outcome": e.outcome,
                    "score": e.score,
                    "resolution_failed": e.resolution_failed,
                }
            )
        if arm_id is not None and c.arm_id != arm_id:
            continue
        if trial_id is not None and c.trial_id != trial_id:
            continue
        out.append(c)
    return out


def _standings_rank(target, grading_state):
    """Rank of `target` (a roster_id -- matchup payloads key teams by roster_id)
    in the grading state's season standings; None when the source yields nothing."""
    for i, row in enumerate(grading_state.standings(), start=1):
        if row["team"] == str(target):
            return i
    return None


_RULE_SOURCES = {"standings": _standings_rank}


def resolve_claims(claims, grading_state, resolution_run_id=None):
    """Pure -- the caller persists. Emits one ResolutionEvent per claim whose
    resolution_rule.resolve_on has passed at the grading state's cutoff, reading
    the outcome from the named source in the supplied state; resolution_failed
    is set when that source yields nothing (the design's `unresolvable` class,
    reported and never silently dropped)."""
    run_id = resolution_run_id or f"resolve@{grading_state.cutoff}"
    events = []
    for c in claims:
        if c.outcome is not None:
            continue  # already resolved; a re-grade is a NEW event by the caller
        due = canonical_instant(c.resolution_rule.get("resolve_on"))
        if due is None or due > grading_state.cutoff:
            continue
        source = _RULE_SOURCES.get(c.resolution_rule.get("source"))
        outcome = source(c.target, grading_state) if source else None
        score = None
        if outcome is not None:
            try:  # scoring rules are K3.6's; mid-build absence leaves score for
                # eval_scoring's scoring-time pass, which recomputes live anyway.
                from scripts.eval_scoring import score_claim

                score = score_claim(Claim(**{**asdict(c), "outcome": outcome}))
            except ImportError:  # pragma: no cover - only before K3.6 lands
                score = None
        events.append(
            ResolutionEvent(
                claim_id=c.claim_id,
                outcome=outcome,
                score=score,
                resolved_at=grading_state.cutoff,
                resolution_run_id=run_id,
                resolution_failed=outcome is None,
            )
        )
    return events
