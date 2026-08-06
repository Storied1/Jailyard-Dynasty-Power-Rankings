"""The five K3 data-layer arms. Inertia is a comparator inside each, never an arm.

K3.4 of plan 562e90d (K3.5 adds the chronological driver to this module).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_schema import Fact, canonical_bytes, fact_hash  # noqa: E402, F401
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import Fact, canonical_bytes, fact_hash  # noqa: E402, F401

ROOT = Path(__file__).resolve().parents[1]


class ArmUnavailable(RuntimeError):
    """The arm cannot measure what it exists to measure at this edition.
    Raised ONLY in the arm-execution lane; the contrast lane's family_counts
    catches it per (arm, edition) and records the arm unavailable (K3.3)."""


# Families that CANNOT exist at a given edition kind. Their absence is correct,
# not missing evidence -- a preseason state contains no 2025 results by construction,
# and treating that as an unavailable arm aborts the run before contrast can be judged.
STRUCTURALLY_ABSENT = {
    "preseason": {"matchup_result"},
    "preview": {"matchup_result"},
    "recap": set(),
}

# Pre-2025 fact types. The no-history arm ablates ALL of them ("Full minus
# pre-2025 facts"). In the current nine-type bridge, historical_matchup is the
# only such type -- the set form exists so a future pre-2025 type joins the
# ablation by membership, not by a second edit site.
PRE_2025_TYPES = {"historical_matchup"}

ARMS = {
    "record_points": {
        "runner_kind": "deterministic",
        "families": ["matchup_result"],
        # Executable, not inert metadata: at preseason and preview there are no 2025
        # results, so this arm ranks by prior-season final standings computed from
        # admitted historical_matchup facts via LeagueState.standings().
        "preseason_basis": "prior_season_final_standings",
        "families_by_kind": {
            "preseason": ["historical_matchup"],
            "preview": ["historical_matchup"],
            "recap": ["matchup_result", "historical_matchup"],
        },
    },
    "minimal_legal": {
        "runner_kind": "model",
        "families": ["franchise_identity", "draft_pick", "roster_membership"],
    },
    "full_rich": {
        "runner_kind": "model",
        "families": [
            "franchise_identity",
            "draft_pick",
            "roster_membership",
            "historical_matchup",
            "chat_message",
            "nfl_game",
            "matchup_result",
            "schedule_pairing",
        ],
    },
    "no_chat": {"runner_kind": "model", "ablates": ["chat_message"]},
    "no_history": {"runner_kind": "model", "ablates": sorted(PRE_2025_TYPES)},
}


def required_families(arm_id, edition_kind):
    """What THIS arm must have at THIS edition. Structurally absent families and
    families with no qualified source are excluded before the requirement is judged."""
    spec = ARMS[arm_id]
    base = spec.get("families_by_kind", {}).get(edition_kind) or spec.get("families")
    if base is None:  # ablation arm: full minus ablated
        base = [f for f in ARMS["full_rich"]["families"] if f not in spec["ablates"]]
    return [f for f in base if f not in STRUCTURALLY_ABSENT[edition_kind]]


def rehydrate_state(doc):
    """Rebuild a LeagueState from a compiled state document (K2.1's serialized
    form). state_at re-admits the already-admitted facts -- idempotent, and the
    ONE temporal authority stays the only admission rule."""
    from scripts.fact_schema import FACT_FIELDS
    from scripts.temporal_state import state_at

    facts = []
    for f in doc["admitted"]:
        kw = {k: f[k] for k in FACT_FIELDS}
        payload = f.get("payload")
        if payload is not None:
            kw["payload_bytes"] = canonical_bytes(payload)
        facts.append(Fact(**kw))
    return state_at(
        doc["season"],
        doc["cutoff"],
        doc["access_scope"],
        as_recorded_at=doc.get("as_recorded_at"),
        facts=facts,
    )


def bundle_for(arm_id, state, edition_kind):
    """One arity, one return shape, everywhere:
    {"families": [...], "facts": {...}, "ranking_basis": str | None, "standings": list}.

    ArmUnavailable fires in exactly two cases, both meaning the arm cannot
    measure what it exists to measure: a required family the state admits ZERO
    facts for, and an ablated family with zero facts (removing nothing is not
    an ablation). Never for a STRUCTURALLY_ABSENT family at this edition kind.
    """
    spec = ARMS[arm_id]
    fams = required_families(arm_id, edition_kind)
    for f in spec.get("ablates", ()):
        if f not in STRUCTURALLY_ABSENT[edition_kind] and not state.by_type(f):
            raise ArmUnavailable(
                f"{arm_id}: nothing to ablate -- zero {f} facts admitted; "
                "removing nothing is not an ablation"
            )
    facts = {}
    for f in fams:
        admitted = state.by_type(f)
        if not admitted:
            raise ArmUnavailable(
                f"{arm_id}: required family {f} has zero admitted facts at this "
                f"{edition_kind} edition (no qualified source)"
            )
        facts[f] = [
            {"effective_at": a.effective_at, "payload": a.payload} for a in admitted
        ]
    ranking_basis, standings = None, []
    if arm_id == "record_points":
        if edition_kind in ("preseason", "preview"):
            ranking_basis = spec["preseason_basis"]
            standings = state.standings(season=state.season - 1)
        else:
            ranking_basis = "current_season_standings"
            standings = state.standings()
        if not standings:
            raise ArmUnavailable(
                f"record_points: {ranking_basis} produced no ordering at {edition_kind}"
            )
    return {
        "families": sorted(facts),
        "facts": facts,
        "ranking_basis": ranking_basis,
        "standings": standings,
    }


def inertia_comparator(arm_id, trial_id, edition, root):
    """The unchanged prior seal of THIS arm, or None where no qualified predecessor exists.

    `edition` is the EditionDescriptor. Season and cutoff come from it — this consumer
    derives no temporal rule of its own.
    """
    # scripts.-form import (Global Constraints): a bare `from decision_history
    # import` under pytest creates a second module whose CrossArmContamination
    # is a different class -- the poison test would error instead of pass.
    from scripts.decision_history import decision_history_at

    if edition.kind == "preseason":
        return None  # nothing to carry forward; invent nothing
    prior = decision_history_at(
        edition.season, edition.cutoff_utc, arm_id, trial_id, root=root
    )
    return prior[-1] if prior else None
