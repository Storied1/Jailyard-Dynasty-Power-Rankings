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


# ---------------------------------------------------------------------------
# K3.5 -- chronological execution driver
# ---------------------------------------------------------------------------
import hashlib  # noqa: E402
import json  # noqa: E402
from dataclasses import asdict  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

try:  # package form first (Global Constraints)
    from scripts.claims_ledger import EDITION_IDS  # noqa: E402
    from scripts.claims_ledger import (
        CLAIMS_ROOT,
        Claim,
        load_claims,
        make_claim,
        resolve_claims,
        save_claims,
        validate_claim,
    )
    from scripts.decision_history import SEALS_ROOT  # noqa: E402
    from scripts.decision_history import (
        decision_history_at,
        load_decision,
        seal,
        verify_predecessor,
        write_json_once,
    )
    from scripts.decision_run import load_runs  # noqa: E402
    from scripts.decision_run import close_run, open_run, persist_run, runner_config
except ImportError:  # pragma: no cover - direct-run fallback
    from claims_ledger import Claim  # noqa: E402
    from claims_ledger import (
        CLAIMS_ROOT,
        EDITION_IDS,
        load_claims,
        make_claim,
        resolve_claims,
        save_claims,
        validate_claim,
    )
    from decision_history import SEALS_ROOT  # noqa: E402
    from decision_history import (
        decision_history_at,
        load_decision,
        seal,
        verify_predecessor,
        write_json_once,
    )
    from decision_run import open_run  # noqa: E402
    from decision_run import close_run, load_runs, persist_run, runner_config

# One per-experiment salt, recorded on every run receipt (§6): opaque tokens
# are re-derivable from committed evidence alone.
MASK_SALT = "k3-2025-backtest-v1"
BLIND_LABEL_MAP_PATH = (
    ROOT / "content" / "editions" / "_evaluation" / "blind_label_map.json"
)


class _InjectedCrash(RuntimeError):
    """Test-only crash injection (write-boundary tests). Never raised in
    production: _crash_at defaults to None."""


def _now():
    # Wall clock is legal on RECEIPTS (transport provenance); it is banned only
    # inside fact bodies, where it would break deterministic replay.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def refuse_if_sealed(root, season, arm_id, trial_id, edition_id):
    """The guard fires FIRST: a re-run is refused while the store is untouched
    and unpaid-for, never after ledger/receipt writes."""
    p = (
        Path(root)
        / f"{season}"
        / arm_id
        / f"trial{trial_id}"
        / f"{edition_id}.seal.json"
    )
    if p.exists():
        raise FileExistsError(
            f"{p}: cell already sealed (.seal.json is the commit marker); "
            "a failed cell is re-run under a NEW trial id, never re-sealed"
        )


def _mask_token(salt, roster_id):
    return "team_" + hashlib.sha256(f"{salt}:{roster_id}".encode()).hexdigest()[:8]


def _identity_map(bundle, salt):
    """roster_id -> (token, [identity strings]) from the bundle's
    franchise_identity facts. NFL entities stay real -- they are the public
    context being tested."""
    out = {}
    for f in bundle.get("facts", {}).get("franchise_identity", []):
        p = f.get("payload") or {}
        rid = str(p.get("roster_id", ""))
        if not rid:
            continue
        strings = [
            v
            for k, v in p.items()
            if k not in ("roster_id", "season") and isinstance(v, str) and v
        ]
        out[rid] = (_mask_token(salt, rid), strings)
    return out


def mask_bundle(bundle, salt):
    """Deterministic §6 masking BEFORE any model input: franchise/owner/display
    names become opaque tokens keyed by roster_id + the per-experiment salt.
    Longest-first replacement over the serialized bundle catches both the
    structured fields and in-text mentions (chat)."""
    identities = _identity_map(bundle, salt)
    text = json.dumps(bundle, ensure_ascii=False)
    replacements = sorted(
        ((s, token) for token, strings in identities.values() for s in strings),
        key=lambda pair: -len(pair[0]),
    )
    for real, token in replacements:
        text = text.replace(real, token)
    return json.loads(text)


def rebind_names(artifact, salt, identities):
    """Presentation-only inverse of mask_bundle: token -> the real name.
    `identities` maps roster_id -> display string. NEVER applied to sealed
    bytes -- callers rebind copies AFTER seal() returns."""
    text = json.dumps(artifact, ensure_ascii=False)
    for rid, name in identities.items():
        text = text.replace(_mask_token(salt, rid), name)
    return json.loads(text)


def runner_kwargs(arm_id, bundle):
    """Model arms: runner_config's model block + computed prompt/rule hashes.
    record_points: computed code/config/input hashes, no provider fields."""
    if ARMS[arm_id]["runner_kind"] == "deterministic":
        return {
            "code_hash": fact_hash(Path(__file__).read_bytes()),
            "config_hash": fact_hash(ARMS["record_points"]),
            "input_hashes": {"bundle": fact_hash(bundle)},
        }
    cfg = runner_config(arm_id)
    return {
        "provider": cfg["provider"],
        "model": cfg["model"],
        "model_version": cfg["model_version"],
        "reasoning": cfg["reasoning"],
        "tools_policy": cfg["tools_policy"],
        "browsing": cfg["browsing"],
        "budget": cfg["budget"],
        "retries": cfg["retries"],
        "sampling_policy": cfg["sampling_policy"],
        "prompt_hash": fact_hash((ROOT / cfg["prompt_path"]).read_bytes()),
        "rule_hashes": {
            k: fact_hash((ROOT / rel).read_bytes())
            for k, rel in cfg["rule_paths"].items()
        },
    }


def _record_points_runner(bundle, predecessor):
    """The deterministic arm: order by the bundle's standings basis and emit
    one ordinal_rank claim per position. No provider, no spend."""
    entries = [
        {"team": row["team"], "rank": i + 1}
        for i, row in enumerate(bundle["standings"])
    ]
    claims = [
        {
            "target": e["team"],
            "claim_type": "ordinal_rank",
            "horizon": "rest_of_season",
            "assertion": e["rank"],
            "confidence": 0.5,
            "decisive_evidence": [f"standings:{bundle['ranking_basis']}"],
            "contrary_evidence": "",
            "resolution_rule": {
                "rule": "final_regular_season_rank",
                "source": "standings",
                "resolve_on": "2026-01-06T00:00:00Z",
            },
        }
        for e in entries
    ]
    return {"entries": entries}, claims


def _dry_run_stub(bundle, predecessor):
    """Zero-spend stand-in for the model arms: deterministic ranking over the
    masked bundle's roster_ids, one resolvable claim per position."""
    teams = sorted(
        {
            f["payload"]["roster_id"]
            for f in bundle["facts"].get("franchise_identity", [])
        }
    ) or [r["team"] for r in bundle["standings"]]
    entries = [{"team": t, "rank": i + 1} for i, t in enumerate(teams)]
    claims = [
        {
            "target": e["team"],
            "claim_type": "ordinal_rank",
            "horizon": "next_week",
            "assertion": e["rank"],
            "confidence": 0.5,
            "decisive_evidence": ["dry-run stub"],
            "contrary_evidence": "",
            "resolution_rule": {
                "rule": "final_regular_season_rank",
                "source": "standings",
                # The recap cutoff: due inside the chain, so the dry run also
                # rehearses resolution and the event-log collapse.
                "resolve_on": "2025-09-09T06:59:59Z",
            },
        }
        for e in entries
    ]
    return {"entries": entries}, claims


def _bind_claims(raw_claims, descriptor, state_hash, arm_id, trial_id, run_id):
    """The DRIVER owns cell identity: runner-returned claims are content only;
    arm/trial/edition/run/state bindings are overwritten here so the census can
    never drift from the cell that produced them."""
    bound = []
    for rc in raw_claims:
        content = asdict(rc) if isinstance(rc, Claim) else dict(rc)
        for k in (
            "claim_id",
            "cutoff_utc",
            "state_hash",
            "arm_id",
            "trial_id",
            "decision_run_id",
            "edition_id",
            "outcome",
            "score",
            "resolution_failed",
        ):
            content.pop(k, None)
        c = make_claim(
            cutoff_utc=descriptor.cutoff_utc,
            state_hash=state_hash,
            arm_id=arm_id,
            trial_id=trial_id,
            decision_run_id=run_id,
            edition_id=descriptor.edition_id,
            **content,
        )
        problems = validate_claim(c)
        if problems:
            raise ValueError(f"runner returned an invalid claim: {problems}")
        bound.append(c)
    return bound


def run_arm_chain(
    arm_id,
    trial_id,
    editions,
    root=None,
    _force_predecessor_arm=None,
    _runners=None,
    _crash_at=None,
    _states=None,
):
    """The complete path, per edition, in chronological order. Close, persist,
    then seal -- the SEAL is the transaction commit marker: a cell without its
    .seal.json does not exist. `root=None` means the real roots (seals to
    content/decisions/, claims to data/claims/); tests pass tmp roots.
    `_runners`/`_states`/`_crash_at`/`_force_predecessor_arm` are test/dry-run
    injection points -- the suite never calls a live provider."""
    import scripts.compile_state as cs

    seals_root = Path(root) if root is not None else SEALS_ROOT
    claims_root = Path(root) if root is not None else CLAIMS_ROOT
    out_seals = []
    for eid in editions:
        descriptor = cs._descriptor_from_file(
            Path(cs.EDITIONS_ROOT) / eid / "descriptor.json"
        )
        if _states is not None:
            state = _states[eid]
            doc = cs._serialize_state(state)
        else:
            doc = cs.load_compiled_state(eid)
            state = rehydrate_state(doc)
        state_hash = fact_hash(doc)
        # Guard BEFORE any write or model call.
        refuse_if_sealed(seals_root, descriptor.season, arm_id, trial_id, eid)
        bundle = bundle_for(
            arm_id, state, descriptor.kind
        )  # ArmUnavailable fails closed
        pred = None
        if descriptor.kind != "preseason":
            hist_arm = _force_predecessor_arm or arm_id
            hist = decision_history_at(
                descriptor.season,
                descriptor.cutoff_utc,
                hist_arm,
                trial_id,
                root=seals_root,
            )
            if hist:
                pred = verify_predecessor(hist[-1], arm_id, trial_id)
        run = open_run(
            runner_kind=ARMS[arm_id]["runner_kind"],
            edition_id=eid,
            arm_id=arm_id,
            trial_id=trial_id,
            state_hash=state_hash,
            bundle_hash=fact_hash(bundle),
            predecessor_decision_hash=pred.decision_hash if pred else None,
            started_at=_now(),
            labeling="retrospective_backtest",
            mask_salt=MASK_SALT,
            **runner_kwargs(arm_id, bundle),
        )
        # §6 masking is ON the execution path, before any model call.
        masked = mask_bundle(bundle, MASK_SALT)
        runner = (_runners or {}).get(arm_id)
        if runner is None:
            if ARMS[arm_id]["runner_kind"] == "deterministic":
                runner = _record_points_runner
            else:
                raise RuntimeError(
                    f"{arm_id}: no model transport wired; K3.7 supplies the qualified "
                    "subscription transport, tests supply _runners -- never an implicit "
                    "provider call"
                )
        ranking, raw_claims = runner(masked, pred)
        entries = ranking["entries"]
        teams = [e["team"] for e in entries]
        if len(set(teams)) != len(teams):
            raise ValueError("ranking must carry exactly one entry per franchise")
        if len(raw_claims) < len(entries):
            raise ValueError(
                "every ranking position must yield at least one scoreable claim; "
                f"got {len(raw_claims)} claims for {len(entries)} positions"
            )
        claims = _bind_claims(
            raw_claims, descriptor, state_hash, arm_id, trial_id, run.run_id
        )
        claims_body = [asdict(c) for c in claims]
        cell_dir = seals_root / f"{descriptor.season}" / arm_id / f"trial{trial_id}"
        if _crash_at == "after_ranking_body":
            write_json_once(cell_dir / f"{eid}.ranking.json", ranking)
            raise _InjectedCrash(_crash_at)
        if _crash_at == "after_claims_body":
            write_json_once(cell_dir / f"{eid}.ranking.json", ranking)
            write_json_once(cell_dir / f"{eid}.claims.json", claims_body)
            raise _InjectedCrash(_crash_at)
        save_claims(claims, root=claims_root)  # EXPLICIT: nothing else persists them
        if _crash_at == "after_claims_write":
            raise _InjectedCrash(_crash_at)
        # Recap grades what is due: immutable resolution events, latest wins.
        events = resolve_claims(
            load_claims(root=claims_root, arm_id=arm_id, trial_id=trial_id),
            state,
            resolution_run_id=run.run_id,
        )
        if events:
            save_claims(events, root=claims_root, season=descriptor.season)
        # The unchanged prior judgment, re-scored at K3.6 -- derivable from the
        # seal tree; invoked here so the flow exercises the comparator lane.
        inertia_comparator(arm_id, trial_id, descriptor, root=seals_root)
        run = close_run(
            run,
            output_decision_hash=fact_hash({"ranking": ranking, "claims": claims_body}),
            ended_at=_now(),
        )
        receipt_path = persist_run(
            run, seals_root
        )  # the CLOSED receipt, exclusive-create
        if _crash_at == "after_receipt":
            raise _InjectedCrash(_crash_at)
        s = seal(
            root=seals_root,
            edition_id=eid,
            season=descriptor.season,
            cutoff_utc=descriptor.cutoff_utc,
            arm_id=arm_id,
            trial_id=trial_id,
            state_hash=state_hash,
            ranking=ranking,
            claims=claims_body,
            run_id=run.run_id,
            run_receipt_path=receipt_path,
            run_receipt_hash=fact_hash(asdict(run)),
            predecessor_decision_hash=pred.decision_hash if pred else None,
        )
        out_seals.append(s)
    return out_seals


def clean_incomplete_cell(root, season, arm_id, trial_id, edition_id):
    """Remove a seal-less cell's orphan bodies/receipt -- the ONLY sanctioned
    deletion in the decisions tree, and mechanically impossible for a sealed
    cell."""
    d = Path(root) / f"{season}" / arm_id / f"trial{trial_id}"
    if (d / f"{edition_id}.seal.json").exists():
        raise ValueError(
            f"{edition_id}: cell is SEALED; a sealed cell is immutable and never cleaned"
        )
    for suffix in (".ranking.json", ".claims.json", ".run.json"):
        p = d / f"{edition_id}{suffix}"
        if p.exists():
            p.unlink()


def resume_chain(arm_id, root=None, _runners=None, _states=None):
    """The replacement-trial controller: clean sealless orphans, allocate a NEW
    trial id (max existing + 1), run the full edition chain under it. Seals are
    immutable -- a failed cell is never re-sealed. Prior trials are enumerated
    from the seal tree AND the claims ledger: a crash before any cell file
    lands still leaves ledger claims under the old trial id, and re-using that
    id would double-append the same claim identities."""
    seals_root = Path(root) if root is not None else SEALS_ROOT
    claims_root = Path(root) if root is not None else CLAIMS_ROOT
    arm_dir = seals_root / "2025" / arm_id
    trial_ids = sorted(
        {
            int(p.name[len("trial") :])
            for p in arm_dir.glob("trial*")
            if p.is_dir() and p.name[len("trial") :].isdigit()
        }
        | {c.trial_id for c in load_claims(root=claims_root, arm_id=arm_id)}
    )
    for t in trial_ids:  # noqa: B007
        for eid in EDITION_IDS:
            d = arm_dir / f"trial{t}"
            if not (d / f"{eid}.seal.json").exists() and any(
                (d / f"{eid}{sfx}").exists()
                for sfx in (".ranking.json", ".claims.json", ".run.json")
            ):
                clean_incomplete_cell(root, 2025, arm_id, t, eid)
    new_trial = (trial_ids[-1] if trial_ids else 0) + 1
    return run_arm_chain(
        arm_id,
        new_trial,
        list(EDITION_IDS),
        root=root,
        _runners=_runners,
        _states=_states,
    )


def complete_chains(arm_id, root):
    """Trial ids whose ALL-edition chains sealed, read from the run receipts
    (seal-backed only). Replacement trials mean the valid ids need not be 1..N."""
    runs, _orphans = load_runs(root)
    by_trial = {}
    for r in runs:
        if r.arm_id == arm_id:
            by_trial.setdefault(r.trial_id, set()).add(r.edition_id)
    return sorted(t for t, eds in by_trial.items() if set(EDITION_IDS) <= eds)


def dry_run_all(root, _states=None, _runners=None):
    """MANDATORY zero-spend rehearsal: the full five-arm loop on stub runners
    into a scratch root. Must seal all 39 cells (1 deterministic trial + 4
    model arms x 3 trials, x 3 editions), proving the loop and the completeness
    gate agree before any paid call."""
    stubs = dict(_runners or {})
    for arm in ARMS:
        stubs.setdefault(
            arm,
            (
                _record_points_runner
                if ARMS[arm]["runner_kind"] == "deterministic"
                else _dry_run_stub
            ),
        )
    sealed = 0
    for arm in sorted(ARMS):
        trials = 1 if ARMS[arm]["runner_kind"] == "deterministic" else 3
        for t in range(1, trials + 1):
            sealed += len(
                run_arm_chain(
                    arm,
                    t,
                    list(EDITION_IDS),
                    root=root,
                    _runners=stubs,
                    _states=_states,
                )
            )
    return sealed


def write_blind_packet(out, label_map_path, root=None):
    """One anonymized ranking body per sealed (arm, trial, edition), named by
    opaque token. The label map is written OUTSIDE the packet directory -- a
    NAMED, COMMITTED destination, or the recorded review is opaque tokens
    forever. Returns the number of anonymized decisions written."""
    from scripts.decision_history import SealedDecision

    root = Path(root) if root is not None else SEALS_ROOT
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    label_map, written = {}, 0
    for p in sorted(root.glob("*/*/*/*.seal.json")):
        s = SealedDecision(**json.loads(p.read_text(encoding="utf-8")))
        ranking, _claims = load_decision(s, root)
        token = (
            "blind_"
            + hashlib.sha256(
                f"{MASK_SALT}:{s.arm_id}:{s.trial_id}:{s.edition_id}".encode()
            ).hexdigest()[:12]
        )
        write_json_once(out / f"{token}.json", ranking)
        label_map[token] = {
            "arm_id": s.arm_id,
            "trial_id": s.trial_id,
            "edition_id": s.edition_id,
        }
        written += 1
    if written:
        write_json_once(label_map_path, label_map)
    return written


def main():
    import argparse

    ap = argparse.ArgumentParser(prog="eval_arms.py")
    ap.add_argument("--arm", choices=sorted(ARMS))
    ap.add_argument("--trial", type=int)
    ap.add_argument("--editions", help="comma-separated edition ids, chronological")
    ap.add_argument(
        "--blind-packet",
        action="store_true",
        help="write anonymized sealed rankings for blind review",
    )
    ap.add_argument("--out", help="output directory; required with --blind-packet")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="execute the FULL chain against stub runners into --out-root; "
        "no provider call, no real-store write",
    )
    ap.add_argument("--out-root", help="scratch root; required with --dry-run")
    ap.add_argument(
        "--resume",
        action="store_true",
        help="clean sealless orphans and re-run --arm under a NEW trial id",
    )
    a = ap.parse_args()
    if a.dry_run:
        if not a.out_root:
            ap.error("--dry-run requires --out-root")
        n = dry_run_all(Path(a.out_root))  # all five arms, stub runners
        print(f"dry run sealed {n} cells under {a.out_root}")
        return 0 if n == 39 else 1  # the loop and the completeness gate must agree
    if a.blind_packet:
        if not a.out:
            ap.error("--blind-packet requires --out")
        n = write_blind_packet(a.out, label_map_path=BLIND_LABEL_MAP_PATH)
        print(f"wrote {n} anonymized decisions; the label map is NOT in {a.out}")
        return 0 if n else 1
    if a.resume:
        if a.arm is None:
            ap.error("--resume requires --arm")
        seals = resume_chain(a.arm, SEALS_ROOT)
        for s in seals:
            print(f"{s.edition_id} {s.arm_id} trial{s.trial_id} {s.decision_hash[:19]}")
        return 0
    # `is None`, not truthiness: `--trial 0` must be rejected as out of range
    # (trials start at 1), never silently read as absent.
    if a.arm is None or a.trial is None or a.editions is None:
        ap.error("--arm, --trial and --editions are required unless --blind-packet")
    if a.trial < 1:
        ap.error("--trial must be >= 1")
    editions = [e.strip() for e in a.editions.split(",") if e.strip()]
    seals = run_arm_chain(a.arm, a.trial, editions)
    for s in seals:
        print(f"{s.edition_id} {s.arm_id} trial{s.trial_id} {s.decision_hash[:19]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
