"""Run receipts, claims, seals, reload verification and rederivation (A6).

Contract: docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md
  S8 decision-run receipt, S9 claims, S11 seal, S12 experiment status.
  Invariants: I24 (trusted clock; injection test-only), I25 (started <=
  ended <= sealed), I26 (prospective iff BOTH ended and sealed at or
  before the cutoff; nothing reclassifies), I27 (only a closed run
  seals), I28 (artifacts keyed by edition/arm/trial), I29+I44
  (predecessor discipline), I30 (seals immutable, distinct suffix), I31
  (reload recomputes every hash), I32 (every position carries a bound
  claim), I21 (rederivation regenerates the decision input from the
  manifest, re-verifying every entry by kind), I42/I48 end-to-end.

Retry contract: a crash between run-close and seal leaves no valid seal;
re-running completes the partial trial exactly once and never
double-seals.
"""

import argparse
import hashlib
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from scripts.bundle_2026 import EDITION_CUTOFF_FIELD  # noqa: E402
    from scripts.bundle_2026 import (
        SEALS_ROOT,
        _build_decision_input,
        _git_blob_bytes,
        build_baseline_standings,
        canonical_json_v1,
        compile_bundle,
        compute_bundle_sha256,
        verify_qualified_artifact,
        write_bundle,
    )
    from scripts.capture_2026 import PRIVATE_CAPTURE_ROOT  # noqa: E402
    from scripts.capture_2026 import (
        PRODUCTION_V1_POLICY_PATH,
        PUBLIC_CAPTURE_ROOT,
        CaptureError,
        load_json_bytes_strict,
        sha256_hex,
        verify_envelope,
    )
    from scripts.cutoff_2026 import load_cutoff_receipt  # noqa: E402
except ImportError:  # pragma: no cover — direct-run fallback
    from bundle_2026 import SEALS_ROOT  # noqa: E402
    from bundle_2026 import (
        EDITION_CUTOFF_FIELD,
        _build_decision_input,
        _git_blob_bytes,
        build_baseline_standings,
        canonical_json_v1,
        compile_bundle,
        compute_bundle_sha256,
        verify_qualified_artifact,
        write_bundle,
    )
    from capture_2026 import PRIVATE_CAPTURE_ROOT  # noqa: E402
    from capture_2026 import (
        PRODUCTION_V1_POLICY_PATH,
        PUBLIC_CAPTURE_ROOT,
        CaptureError,
        load_json_bytes_strict,
        sha256_hex,
        verify_envelope,
    )
    from cutoff_2026 import load_cutoff_receipt  # noqa: E402

try:
    from scripts.shared import REPO_ROOT  # noqa: E402
except ImportError:  # pragma: no cover
    from shared import REPO_ROOT  # noqa: E402

DECISION_VERSION = "record_points_v1"
SEAL_SUFFIX = ".sealed.json"
EXPECTED_RUNS = {"record_points": 1, "minimal_legal": 3, "full_rich": 3}

SEAL_FIELDS = (
    "edition_id",
    "kind",
    "season",
    "arm_id",
    "trial_id",
    "cutoff_utc",
    "cutoff_receipt_locator",
    "cutoff_receipt_sha256",
    "ended_at",
    "sealed_at",
    "label",
    "bundle_sha256",
    "bundle_locator",
    "decision_input_sha256",
    "source_manifest_sha256",
    "policy_locator",
    "matrix_sha256",
    "decision_sha256",
    "decision_locator",
    "claims_sha256",
    "claims_locator",
    "receipt_sha256",
    "receipt_locator",
    "predecessor_decision_hash",
    "runner_kind",
    "decision_hash",
)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _write_json_once(path: Path, doc) -> Path:
    if path.exists():
        raise CaptureError(f"append-only artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(canonical_json_v1(doc))
    return path


# ---------------------------------------------------------------------------
# Deterministic runner + claims
# ---------------------------------------------------------------------------


def run_record_points(bundle: dict) -> dict:
    """The deterministic arm: a pure function of the frozen decision input."""
    payload = bundle["decision_input_payload"]
    ranking = [
        {
            "rank": f["rank"],
            "roster_id": f["roster_id"],
            "owner_id": f["owner_id"],
            "wins_2025": f["wins_2025"],
            "points_for_2025": f["points_for_2025"],
        }
        for f in payload["franchises"]
    ]
    return {
        "decision_version": DECISION_VERSION,
        "edition_id": bundle["edition_id"],
        "arm_id": bundle["arm_id"],
        "cutoff_utc": bundle["cutoff_utc"],
        "ranking": ranking,
    }


def runner_code_sha256() -> str:
    return hashlib.sha256(
        inspect.getsource(run_record_points).encode("utf-8")
    ).hexdigest()


def build_claims(decision: dict, bundle: dict, decision_run_id: str, trial_id: int):
    """S9/I32 — one ordinal_rank claim per ranking position, resolution rule
    fixed before any outcome, bound to the bundle and manifest hashes."""
    claims = []
    for row in decision["ranking"]:
        claims.append(
            {
                "claim_id": f"{decision_run_id}_rank{row['rank']:02d}",
                "target": row["owner_id"],
                "claim_type": "ordinal_rank",
                "horizon": "2026 final regular-season standings",
                "assertion": {"predicted_rank": row["rank"]},
                "confidence": None,
                "bound": None,
                "decisive_evidence": "2025 final regular-season record and points-for",
                "contrary_evidence": None,
                "cutoff_utc": decision["cutoff_utc"],
                "edition_id": decision["edition_id"],
                "arm_id": decision["arm_id"],
                "trial_id": trial_id,
                "decision_run_id": decision_run_id,
                "bundle_sha256": bundle["bundle_sha256"],
                "source_manifest_sha256": bundle["source_manifest_sha256"],
                "resolution_rule": {
                    "rule": (
                        "final 2026 regular-season standings ordering: wins desc, "
                        "points-for desc, roster_id asc"
                    ),
                    "source": "verified sleeper_matchups captures through week 14",
                    "resolve_on": "after the 2026 regular season completes",
                },
                "outcome": None,
                "score": None,
                "resolution_failed": False,
            }
        )
    return {"claims": claims}


# ---------------------------------------------------------------------------
# Predecessor discipline (I29, I44)
# ---------------------------------------------------------------------------


def find_predecessor(
    seals_root,
    *,
    arm_id,
    trial_id,
    before_cutoff_utc,
    expected_arm,
    expected_trial,
):
    """Latest qualified seal of the SAME arm and trial at a strictly earlier
    cutoff. A foreign predecessor identity raises rather than chains."""
    if arm_id != expected_arm or trial_id != expected_trial:
        raise CaptureError(
            f"foreign predecessor refused: requested ({arm_id!r}, trial "
            f"{trial_id}) for a run of ({expected_arm!r}, trial {expected_trial})"
        )
    root = Path(seals_root)
    before = _parse_z(before_cutoff_utc)
    best = None
    if root.is_dir():
        for seal_path in root.glob(f"*/{arm_id}/trial{trial_id}/seal{SEAL_SUFFIX}"):
            seal = load_seal(seal_path)
            if seal["arm_id"] != arm_id or seal["trial_id"] != trial_id:
                raise CaptureError(
                    f"seal at {seal_path} carries foreign identity "
                    f"({seal['arm_id']!r}, trial {seal['trial_id']})"
                )
            cutoff = _parse_z(seal["cutoff_utc"])
            if cutoff < before and (best is None or cutoff > best[0]):
                best = (cutoff, seal["decision_hash"])
    if best is None:
        return None, (
            f"no earlier qualified seal for ({arm_id}, trial {trial_id}) "
            f"before {before_cutoff_utc}"
        )
    return best[1], None


# ---------------------------------------------------------------------------
# S8 run receipt: open -> close (I25, I27)
# ---------------------------------------------------------------------------


def open_run(
    edition_id,
    arm_id,
    trial_id,
    *,
    bundle,
    cutoff_receipt_path,
    policy_path,
    seals_root,
    started_at,
):
    if bundle["bundle_sha256"] != compute_bundle_sha256(bundle):
        raise CaptureError("bundle hash does not recompute; refusing to open a run")
    predecessor_hash, null_reason = find_predecessor(
        seals_root,
        arm_id=arm_id,
        trial_id=trial_id,
        before_cutoff_utc=bundle["cutoff_utc"],
        expected_arm=arm_id,
        expected_trial=trial_id,
    )
    started = started_at if started_at is not None else datetime.now(timezone.utc)
    decision_run_id = (
        f"{edition_id}_{arm_id}_t{trial_id}_{started.strftime('%Y%m%dT%H%M%SZ')}"
    )
    return {
        "decision_run_id": decision_run_id,
        "edition_id": edition_id,
        "arm_id": arm_id,
        "trial_id": trial_id,
        "runner_kind": "deterministic",
        "bundle_sha256": bundle["bundle_sha256"],
        "decision_input_sha256": bundle["decision_input_sha256"],
        "source_manifest_sha256": bundle["source_manifest_sha256"],
        "cutoff_receipt_locator": str(cutoff_receipt_path),
        "cutoff_receipt_sha256": bundle["cutoff_receipt_sha256"],
        "policy_locator": str(policy_path),
        "matrix_sha256": bundle["matrix_sha256"],
        "predecessor_decision_hash": predecessor_hash,
        "predecessor_null_reason": null_reason,
        "state_hash": None,
        "state_hash_null_reason": "no state_at exists pre-kernel",
        "started_at": _iso_z(started),
        "code_sha256": runner_code_sha256(),
        "config_sha256": sha256_hex(
            canonical_json_v1({"decision_version": DECISION_VERSION})
        ),
        "input_hashes": {
            "decision_input_sha256": bundle["decision_input_sha256"],
            "source_manifest_sha256": bundle["source_manifest_sha256"],
        },
    }


def close_run(receipt: dict, decision: dict, ended_at) -> dict:
    if "ended_at" in receipt or "output_decision_sha256" in receipt:
        raise CaptureError("run already closed")
    ended = ended_at if ended_at is not None else datetime.now(timezone.utc)
    if ended < _parse_z(receipt["started_at"]):
        raise CaptureError(
            f"ended_at {_iso_z(ended)} precedes started_at {receipt['started_at']} (I25)"
        )
    closed = dict(receipt)
    closed["ended_at"] = _iso_z(ended)
    closed["output_decision_sha256"] = sha256_hex(canonical_json_v1(decision))
    return closed


# ---------------------------------------------------------------------------
# S11 seal (I26, I27, I30) + trial orchestration (I28, retry contract)
# ---------------------------------------------------------------------------


def load_seal(path) -> dict:
    path = Path(path)
    if not path.name.endswith(SEAL_SUFFIX):
        raise CaptureError(
            f"{path.name} is not a seal (seals use the {SEAL_SUFFIX} suffix); "
            "decision, claims and receipt bodies are never deserialized as seals"
        )
    if not path.exists():
        raise CaptureError(f"seal missing: {path}")
    seal = load_json_bytes_strict(path.read_bytes())
    missing = [f for f in SEAL_FIELDS if f not in seal]
    if missing:
        raise CaptureError(f"seal missing fields {missing}: {path}")
    return seal


def seal_trial(trial_dir, *, repo_root=None, now=None) -> Path:
    """Seal one CLOSED run (I27). Never double-seals; completing a partial
    trial after a crash is safe because the closed receipt is the input."""
    trial_dir = Path(trial_dir)
    seal_path = trial_dir / f"seal{SEAL_SUFFIX}"
    if seal_path.exists():
        raise CaptureError(f"trial already sealed: {seal_path} (no double-seal)")

    receipt_path = trial_dir / "receipt.json"
    decision_path = trial_dir / "decision.json"
    claims_path = trial_dir / "claims.json"
    for path in (receipt_path, decision_path, claims_path):
        if not path.exists():
            raise CaptureError(f"cannot seal: {path.name} missing from {trial_dir}")
    receipt = load_json_bytes_strict(receipt_path.read_bytes())
    if "ended_at" not in receipt or "output_decision_sha256" not in receipt:
        raise CaptureError("sealing an OPEN run is refused (I27)")
    decision = load_json_bytes_strict(decision_path.read_bytes())
    claims = load_json_bytes_strict(claims_path.read_bytes())
    if sha256_hex(canonical_json_v1(decision)) != receipt["output_decision_sha256"]:
        raise CaptureError("decision does not match the closed receipt")

    bundle_path = trial_dir.parent / "bundle.json"
    bundle = load_json_bytes_strict(bundle_path.read_bytes())

    sealed = now if now is not None else datetime.now(timezone.utc)
    ended = _parse_z(receipt["ended_at"])
    if sealed < ended:
        raise CaptureError(
            f"sealed_at {_iso_z(sealed)} precedes ended_at {receipt['ended_at']} (I25)"
        )
    cutoff = _parse_z(bundle["cutoff_utc"])
    label = "prospective" if (ended <= cutoff and sealed <= cutoff) else "retrospective"

    seal = {
        "edition_id": receipt["edition_id"],
        "kind": "baseline_power_ranking",
        "season": 2026,
        "arm_id": receipt["arm_id"],
        "trial_id": receipt["trial_id"],
        "cutoff_utc": bundle["cutoff_utc"],
        "cutoff_receipt_locator": receipt["cutoff_receipt_locator"],
        "cutoff_receipt_sha256": receipt["cutoff_receipt_sha256"],
        "ended_at": receipt["ended_at"],
        "sealed_at": _iso_z(sealed),
        "label": label,
        "bundle_sha256": bundle["bundle_sha256"],
        "bundle_locator": str(bundle_path),
        "decision_input_sha256": bundle["decision_input_sha256"],
        "source_manifest_sha256": bundle["source_manifest_sha256"],
        "policy_locator": receipt["policy_locator"],
        "matrix_sha256": receipt["matrix_sha256"],
        "decision_sha256": receipt["output_decision_sha256"],
        "decision_locator": str(decision_path),
        "claims_sha256": sha256_hex(canonical_json_v1(claims)),
        "claims_locator": str(claims_path),
        "receipt_sha256": sha256_hex(canonical_json_v1(receipt)),
        "receipt_locator": str(receipt_path),
        "predecessor_decision_hash": receipt["predecessor_decision_hash"],
        "runner_kind": receipt["runner_kind"],
    }
    seal["decision_hash"] = sha256_hex(canonical_json_v1(seal))
    return _write_json_once(seal_path, seal)


def run_trial(
    edition_id,
    arm_id,
    trial_id,
    *,
    policy_path,
    cutoff_receipt_path,
    seals_root,
    public_root=None,
    private_root=None,
    repo_root=None,
    now=None,
    stop_before_seal=False,
) -> Path:
    """Compile-or-load the bundle, execute, close, write bodies, seal."""
    if arm_id != "record_points":
        raise CaptureError("model-arm trials are Tranche B scope")
    seals = Path(seals_root)
    trial_dir = seals / edition_id / arm_id / f"trial{trial_id}"
    if trial_dir.exists():
        raise CaptureError(
            f"trial dir already exists: {trial_dir} — a partial trial is completed "
            f"via seal_trial, a sealed one never re-runs (I28)"
        )

    bundle_path = seals / edition_id / arm_id / "bundle.json"
    if bundle_path.exists():
        bundle = load_json_bytes_strict(bundle_path.read_bytes())
        if bundle["bundle_sha256"] != compute_bundle_sha256(bundle):
            raise CaptureError(f"existing bundle fails recompute: {bundle_path}")
    else:
        bundle = compile_bundle(
            edition_id,
            arm_id,
            policy_path=policy_path,
            cutoff_receipt_path=cutoff_receipt_path,
            public_root=public_root,
            private_root=private_root,
            repo_root=repo_root,
        )
        write_bundle(bundle, public_bundles_root=seals)

    receipt = open_run(
        edition_id,
        arm_id,
        trial_id,
        bundle=bundle,
        cutoff_receipt_path=cutoff_receipt_path,
        policy_path=policy_path,
        seals_root=seals,
        started_at=now,
    )
    decision = run_record_points(bundle)
    closed = close_run(receipt, decision, ended_at=now)
    claims = build_claims(decision, bundle, closed["decision_run_id"], trial_id)

    _write_json_once(trial_dir / "decision.json", decision)
    _write_json_once(trial_dir / "claims.json", claims)
    _write_json_once(trial_dir / "receipt.json", closed)
    if not stop_before_seal:
        seal_trial(trial_dir, repo_root=repo_root, now=now)
    return trial_dir


# ---------------------------------------------------------------------------
# Reload verification (I31, I42/I48 end-to-end) and rederivation (I21, I55)
# ---------------------------------------------------------------------------


def _resolve_locator(locator: str, repo_root) -> Path:
    path = Path(locator)
    return path if path.is_absolute() else Path(repo_root) / locator


def _verify_manifest_entries(manifest, repo_root, errors):
    for entry in manifest:
        if entry["kind"] == "capture":
            envelope_path = _resolve_locator(entry["locator"], repo_root)
            ok, env_errors = verify_envelope(envelope_path)
            if not ok:
                errors.append(
                    f"{entry['source_id']}: envelope failed verification "
                    f"({'; '.join(env_errors)})"
                )
                continue
            envelope = load_json_bytes_strict(envelope_path.read_bytes())
            if envelope["envelope_sha256"] != entry["envelope_sha256"]:
                errors.append(f"{entry['source_id']}: envelope_sha256 drifted")
            if envelope["payload_sha256"] != entry["payload_sha256"]:
                errors.append(f"{entry['source_id']}: payload_sha256 drifted")
        else:
            ok, _, qa_errors = verify_qualified_artifact(entry, repo_root=repo_root)
            if not ok:
                errors.append(
                    f"{entry['source_id']}: qualified artifact failed "
                    f"({'; '.join(qa_errors)})"
                )


def verify_seal_dir(trial_dir, *, repo_root=None) -> tuple[bool, list, list]:
    """I31 — recompute and cross-check EVERY hash in the chain."""
    trial_dir = Path(trial_dir)
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    errors: list[str] = []
    diagnostics: list[str] = []

    try:
        seal = load_seal(trial_dir / f"seal{SEAL_SUFFIX}")
    except CaptureError as exc:
        return False, [str(exc)], diagnostics

    body = {k: v for k, v in seal.items() if k != "decision_hash"}
    if sha256_hex(canonical_json_v1(body)) != seal["decision_hash"]:
        return False, ["seal decision_hash does not recompute"], diagnostics

    try:
        decision = load_json_bytes_strict(
            _resolve_locator(seal["decision_locator"], root).read_bytes()
        )
        claims = load_json_bytes_strict(
            _resolve_locator(seal["claims_locator"], root).read_bytes()
        )
        receipt = load_json_bytes_strict(
            _resolve_locator(seal["receipt_locator"], root).read_bytes()
        )
        bundle = load_json_bytes_strict(
            _resolve_locator(seal["bundle_locator"], root).read_bytes()
        )
    except (OSError, CaptureError) as exc:
        return False, [f"seal body unreadable: {exc}"], diagnostics

    if sha256_hex(canonical_json_v1(decision)) != seal["decision_sha256"]:
        errors.append("decision_sha256 mismatch")
    if sha256_hex(canonical_json_v1(claims)) != seal["claims_sha256"]:
        errors.append("claims_sha256 mismatch")
    if sha256_hex(canonical_json_v1(receipt)) != seal["receipt_sha256"]:
        errors.append("receipt_sha256 mismatch")
    if compute_bundle_sha256(bundle) != seal["bundle_sha256"]:
        errors.append("bundle_sha256 mismatch")
    if (
        sha256_hex(canonical_json_v1(bundle.get("decision_input_payload")))
        != seal["decision_input_sha256"]
    ):
        errors.append("decision_input_sha256 mismatch")
    if (
        sha256_hex(canonical_json_v1(bundle.get("source_manifest")))
        != seal["source_manifest_sha256"]
    ):
        errors.append("source_manifest_sha256 mismatch")
    if receipt.get("output_decision_sha256") != seal["decision_sha256"]:
        errors.append("receipt/decision disagreement")

    started = _parse_z(receipt["started_at"])
    ended = _parse_z(seal["ended_at"])
    sealed = _parse_z(seal["sealed_at"])
    if not (started <= ended <= sealed):
        errors.append("timestamp ordering violated (I25)")
    cutoff = _parse_z(seal["cutoff_utc"])
    expected_label = (
        "prospective" if (ended <= cutoff and sealed <= cutoff) else "retrospective"
    )
    if seal["label"] != expected_label:
        errors.append(
            f"label {seal['label']!r} inconsistent with instants (I26 re-derivation)"
        )

    # cutoff receipt: re-read, re-hash, and cross-check agreement (I42 e2e)
    try:
        cutoff_receipt = load_cutoff_receipt(
            _resolve_locator(seal["cutoff_receipt_locator"], root)
        )
        if cutoff_receipt["receipt_sha256"] != seal["cutoff_receipt_sha256"]:
            errors.append("cutoff receipt hash differs from the bound value")
        edition_field = EDITION_CUTOFF_FIELD[seal["edition_id"]]
        if cutoff_receipt[edition_field] != seal["cutoff_utc"]:
            errors.append("cutoff value disagrees with the qualification receipt")
        if bundle.get("cutoff_utc") != seal["cutoff_utc"]:
            errors.append("bundle cutoff disagrees with the seal")
        if receipt.get("cutoff_receipt_sha256") != seal["cutoff_receipt_sha256"]:
            errors.append("run receipt cutoff binding disagrees with the seal")
    except CaptureError as exc:
        errors.append(f"cutoff receipt failed reload: {exc}")

    # policy: re-read the locator; it must still hash to the bound value (I48)
    try:
        policy_raw = _resolve_locator(seal["policy_locator"], root).read_bytes()
        policy = load_json_bytes_strict(policy_raw)
        policy_body = {k: v for k, v in policy.items() if k != "policy_sha256"}
        if sha256_hex(canonical_json_v1(policy_body)) != seal["matrix_sha256"]:
            errors.append(
                "policy/matrix drift: locator no longer hashes to bound value"
            )
    except (OSError, CaptureError) as exc:
        errors.append(f"policy unreadable at bound locator: {exc}")

    _verify_manifest_entries(bundle.get("source_manifest", []), root, errors)

    return (not errors), errors, diagnostics


def rederive_trial(trial_dir, *, repo_root=None) -> dict:
    """I21 — regenerate the decision-input payload FROM THE SOURCE MANIFEST,
    re-verifying every entry by kind, then reproduce both bound hashes.
    Re-hashing the frozen bundle is not a test; the payload is rebuilt from
    the bound blob (I55) and the bound envelopes, never the worktree."""
    trial_dir = Path(trial_dir)
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    errors: list[str] = []

    seal = load_seal(trial_dir / f"seal{SEAL_SUFFIX}")
    bundle = load_json_bytes_strict(
        _resolve_locator(seal["bundle_locator"], root).read_bytes()
    )
    manifest = bundle["source_manifest"]
    _verify_manifest_entries(manifest, root, errors)
    if errors:
        return {"ok": False, "errors": errors}

    entries = {e["source_id"]: e for e in manifest}
    standings_entry = entries.get("standings_2025")
    rosters_entry = entries.get("sleeper_rosters")
    if standings_entry is None or rosters_entry is None:
        return {
            "ok": False,
            "errors": ["manifest missing standings_2025 or sleeper_rosters"],
        }

    standings_doc = load_json_bytes_strict(
        _git_blob_bytes(root, standings_entry["git_blob_oid"])
    )
    rosters_env = load_json_bytes_strict(
        _resolve_locator(rosters_entry["locator"], root).read_bytes()
    )
    franchises = build_baseline_standings(
        standings_doc, rosters_env["payload"]["rosters"]
    )
    regenerated = _build_decision_input(
        bundle["edition_id"], bundle["arm_id"], bundle["cutoff_utc"], franchises
    )
    regenerated_sha = sha256_hex(canonical_json_v1(regenerated))

    rebuilt = dict(bundle)
    rebuilt["decision_input_payload"] = regenerated
    rebuilt["decision_input_sha256"] = regenerated_sha
    rebuilt_sha = compute_bundle_sha256(rebuilt)

    result = {
        "ok": True,
        "errors": [],
        "regenerated_decision_input_sha256": regenerated_sha,
        "bound_decision_input_sha256": seal["decision_input_sha256"],
        "regenerated_bundle_sha256": rebuilt_sha,
        "bound_bundle_sha256": seal["bundle_sha256"],
    }
    if regenerated_sha != seal["decision_input_sha256"]:
        result["ok"] = False
        result["errors"].append("regenerated decision input hash differs from bound")
    if rebuilt_sha != seal["bundle_sha256"]:
        result["ok"] = False
        result["errors"].append("regenerated bundle hash differs from bound")
    return result


# ---------------------------------------------------------------------------
# S12 — derived experiment status (never manually asserted)
# ---------------------------------------------------------------------------


def derive_experiment_status(edition_id, *, seals_root=None, repo_root=None, now=None):
    seals = Path(seals_root) if seals_root is not None else SEALS_ROOT
    verified = []
    for arm_id, trials in EXPECTED_RUNS.items():
        for trial in range(1, trials + 1):
            trial_dir = seals / edition_id / arm_id / f"trial{trial}"
            if not (trial_dir / f"seal{SEAL_SUFFIX}").exists():
                continue
            ok, _, _ = verify_seal_dir(trial_dir, repo_root=repo_root)
            if not ok:
                continue
            seal = load_seal(trial_dir / f"seal{SEAL_SUFFIX}")
            if seal["label"] == "prospective":
                verified.append(f"{arm_id}/trial{trial}")
    expected = sum(EXPECTED_RUNS.values())
    complete = len(verified) == expected
    computed = now if now is not None else datetime.now(timezone.utc)
    return {
        "edition_id": edition_id,
        "expected_runs": expected,
        "verified_prospective_seals": sorted(verified),
        "experiment_status": "complete" if complete else "unavailable",
        "reason": (
            None
            if complete
            else f"{len(verified)}/{expected} verified prospective seals"
        ),
        "computed_at": _iso_z(computed),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _production_paths():
    try:
        from scripts.cutoff_2026 import latest_cutoff_receipt_path
    except ImportError:  # pragma: no cover
        from cutoff_2026 import latest_cutoff_receipt_path

    receipt_path = latest_cutoff_receipt_path()
    if receipt_path is None:
        raise CaptureError(
            "no cutoff receipt; run cutoff_2026.py --season 2026 --write-receipt"
        )
    return {
        "policy_path": PRODUCTION_V1_POLICY_PATH,
        "cutoff_receipt_path": receipt_path,
        "seals_root": SEALS_ROOT,
        "public_root": PUBLIC_CAPTURE_ROOT,
        "private_root": PRIVATE_CAPTURE_ROOT,
        "repo_root": REPO_ROOT,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="seal_2026.py",
        description="Run receipts, claims, seals, reload verify and rederive (A6).",
    )
    parser.add_argument("--edition", choices=sorted(EDITION_CUTOFF_FIELD))
    parser.add_argument("--arm", default="record_points")
    parser.add_argument("--trial", type=int, default=1)
    parser.add_argument("--verify-all", action="store_true")
    parser.add_argument("--rederive-all", action="store_true")
    parser.add_argument("--experiment-status", action="store_true")
    args = parser.parse_args(argv)

    if args.verify_all or args.rederive_all:
        failures = 0
        checked = 0
        for seal_path in sorted(SEALS_ROOT.glob(f"*/*/trial*/seal{SEAL_SUFFIX}")):
            trial_dir = seal_path.parent
            checked += 1
            if args.verify_all:
                ok, errors, _ = verify_seal_dir(trial_dir)
                status = "OK" if ok else f"FAIL {errors}"
            else:
                result = rederive_trial(trial_dir)
                ok = result["ok"]
                status = "OK" if ok else f"FAIL {result['errors']}"
            print(f"{trial_dir}: {status}")
            failures += 0 if ok else 1
        print(f"checked {checked}, failures {failures}")
        return 0 if checked and not failures else 1

    if args.experiment_status:
        if not args.edition:
            print("--experiment-status requires --edition", file=sys.stderr)
            return 2
        status = derive_experiment_status(args.edition)
        print(json.dumps(status, indent=2))
        return 0 if status["experiment_status"] == "complete" else 1

    if args.edition:
        try:
            paths = _production_paths()
            trial_dir = run_trial(args.edition, args.arm, args.trial, **paths)
        except CaptureError as exc:
            print(f"trial failed closed: {exc}", file=sys.stderr)
            return 1
        print(f"sealed: {trial_dir}")
        return 0

    parser.print_usage(sys.stderr)
    print("seal_2026.py: no action requested", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
