"""Bundle compiler for the 2026 safeguard (task A5).

Contract: docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md
  S13 strict load + canonicalization (versioned, byte-boundary);
  S5 frozen bundle; S6 two-kind source manifest; R5 baseline input.
  Invariants: I19 (selection <= cutoff), I20 (hashes computed, never
  caller-supplied), I22 (private bundles under private_bundles/), I43
  (bundle binds the canonical decision-input payload + versioned
  projection), I46/I51 (R5 recomputation, owner_id join), I53-I56
  (strict load, commit-pinned qualified artifacts, required manifest).

A qualified artifact is pinned to a COMMIT, not the working tree: freeze
demands the worktree canonically equal the bound blob; verification later
reads only the bound commit/path/blob, so a legitimate worktree edit can
never invalidate an old seal (worktree drift is diagnostic only).
"""

import argparse
import hashlib
import inspect
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from scripts.capture_2026 import PRIVATE_BUNDLE_ROOT  # noqa: E402
    from scripts.capture_2026 import (
        PRIVATE_CAPTURE_ROOT,
        PUBLIC_CAPTURE_ROOT,
        CaptureError,
        canonical_bytes,
        load_json_bytes_strict,
        load_policy,
        sha256_hex,
    )
    from scripts.cutoff_2026 import load_cutoff_receipt  # noqa: E402
except ImportError:  # pragma: no cover — direct-run fallback
    from capture_2026 import PRIVATE_BUNDLE_ROOT  # noqa: E402
    from capture_2026 import (
        PRIVATE_CAPTURE_ROOT,
        PUBLIC_CAPTURE_ROOT,
        CaptureError,
        canonical_bytes,
        load_json_bytes_strict,
        load_policy,
        sha256_hex,
    )
    from cutoff_2026 import load_cutoff_receipt  # noqa: E402

try:
    from scripts.shared import REPO_ROOT  # noqa: E402
except ImportError:  # pragma: no cover
    from shared import REPO_ROOT  # noqa: E402

SEALS_ROOT = REPO_ROOT / "content" / "seals" / "2026"

# ---------------------------------------------------------------------------
# S13 — the versioned strict loader + canonicalizer pair
# ---------------------------------------------------------------------------

CANONICALIZER_ID = "canonical_json"
CANONICALIZER_VERSION = "v1"


def load_json_strict(raw):
    """S13: strict JSON load over RAW BYTES.

    Rejects duplicate keys at every nesting level and NaN/Infinity/-Infinity
    BEFORE parsing discards them; anything that is not bytes is refused —
    an already-parsed object has lost the information the check needs.
    """
    return load_json_bytes_strict(raw)


def canonical_json_v1(obj) -> bytes:
    """S13: canonical in-memory serialization — sort_keys, ensure_ascii=False,
    indent=2, allow_nan=False, exactly one trailing LF, explicit UTF-8."""
    return canonical_bytes(obj)


def canonicalizer_code_sha256() -> str:
    """Stable identity of the canonicalization pair for S6 entries."""
    source = inspect.getsource(load_json_strict) + inspect.getsource(canonical_json_v1)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def content_sha256_of(raw: bytes) -> str:
    """Authoritative source identity: canonical form of strictly-loaded bytes."""
    return sha256_hex(canonical_json_v1(load_json_strict(raw)))


# ---------------------------------------------------------------------------
# Qualified-artifact identity (I54 freeze, I55 verify)
# ---------------------------------------------------------------------------


def _git(repo_root, *args) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise CaptureError(
            f"git {' '.join(args)} failed in {repo_root}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _git_blob_bytes(repo_root, oid) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "blob", oid], capture_output=True
    )
    if result.returncode != 0:
        raise CaptureError(
            f"git cat-file blob {oid} failed: {result.stderr.decode(errors='replace')}"
        )
    return result.stdout


def _eol_profile(raw: bytes) -> str:
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    if crlf and lf:
        return "mixed"
    if crlf:
        return "crlf"
    if lf:
        return "lf"
    return "none"


def freeze_qualified_artifact(
    source_id: str, locator: str, *, repo_root=None, commit="HEAD"
) -> dict:
    """I54 — bind commit/path/blob identity; freeze fails unless the current
    worktree canonically equals the bound blob. Worktree bytes, byte count
    and EOL profile are recorded as diagnostics only."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    commit_sha = _git(root, "rev-parse", commit)
    try:
        blob_oid = _git(root, "rev-parse", f"{commit_sha}:{locator}")
    except CaptureError as exc:
        raise CaptureError(
            f"qualified artifact {source_id}: no blob at {commit_sha[:12]}:{locator} "
            f"({exc})"
        ) from exc
    blob = _git_blob_bytes(root, blob_oid)
    blob_content = content_sha256_of(blob)

    worktree_path = root / locator
    if not worktree_path.exists():
        raise CaptureError(
            f"qualified artifact {source_id}: worktree copy missing at {worktree_path}"
        )
    worktree = worktree_path.read_bytes()
    if content_sha256_of(worktree) != blob_content:
        raise CaptureError(
            f"qualified artifact {source_id}: worktree does not canonically equal "
            f"the bound blob at {commit_sha[:12]}:{locator} — freeze refused (I54)"
        )

    return {
        "kind": "qualified_artifact",
        "source_id": source_id,
        "locator": locator,
        "content_sha256": blob_content,
        "canonicalizer_id": CANONICALIZER_ID,
        "canonicalizer_version": CANONICALIZER_VERSION,
        "canonicalizer_code_sha256": canonicalizer_code_sha256(),
        "commit_sha": commit_sha,
        "path": locator,
        "git_blob_oid": blob_oid,
        "blob_bytes_sha256": sha256_hex(blob),
        "observed_worktree_bytes_sha256": sha256_hex(worktree),
        "byte_count": len(worktree),
        "eol_profile": _eol_profile(worktree),
    }


def verify_qualified_artifact(entry: dict, *, repo_root=None):
    """I55 — read and verify the BOUND commit/path/blob, never the worktree.

    Returns (ok, diagnostics, errors). Missing or mismatched bound Git
    evidence fails closed; worktree differences are diagnostics only.
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    errors: list[str] = []
    diagnostics: list[str] = []

    try:
        resolved_oid = _git(root, "rev-parse", f"{entry['commit_sha']}:{entry['path']}")
    except CaptureError as exc:
        return False, diagnostics, [f"bound blob unresolvable: {exc}"]
    if resolved_oid != entry["git_blob_oid"]:
        errors.append(
            f"git_blob_oid mismatch: bound {entry['git_blob_oid']}, "
            f"resolved {resolved_oid}"
        )
        return False, diagnostics, errors

    try:
        blob = _git_blob_bytes(root, entry["git_blob_oid"])
    except CaptureError as exc:
        return False, diagnostics, [f"bound blob unreadable: {exc}"]
    if sha256_hex(blob) != entry["blob_bytes_sha256"]:
        errors.append("blob_bytes_sha256 mismatch against the bound blob")
    try:
        blob_content = content_sha256_of(blob)
    except CaptureError as exc:
        errors.append(f"bound blob fails strict canonicalization: {exc}")
        return False, diagnostics, errors
    if blob_content != entry["content_sha256"]:
        errors.append("content_sha256 mismatch against the bound blob")
    if errors:
        return False, diagnostics, errors

    worktree_path = root / entry["path"]
    if not worktree_path.exists():
        diagnostics.append("worktree copy absent (diagnostic only)")
    else:
        worktree = worktree_path.read_bytes()
        if worktree != blob:
            try:
                same_content = content_sha256_of(worktree) == blob_content
            except CaptureError:
                same_content = False
            if same_content:
                diagnostics.append(
                    "worktree differs: same_content_different_materialization"
                )
            else:
                diagnostics.append(
                    "worktree differs semantically from the bound blob "
                    "(diagnostic only — verification reads the blob)"
                )
    return True, diagnostics, errors


# ---------------------------------------------------------------------------
# R5 — the deterministic baseline input (I46, I51)
# ---------------------------------------------------------------------------


def build_baseline_standings(standings_doc: dict, rosters_2026: list) -> list:
    """Final 2025 regular-season ordering joined to 2026 franchises by owner.

    Regular season = weeks 1 .. playoff_week_start - 1. Wins/points-for are
    recomputed from weeks[playoff_week_start - 2].standings (the cumulative
    snapshot through the final regular week) and cross-checked against
    roster_map[*].final_record, failing closed on disagreement — the stored
    aggregate is corroboration, never the input. Ordering: wins desc,
    points-for desc, 2026 roster_id asc. An unmatched 2026 owner takes
    (0, 0.0) and therefore sorts last under the same ordering (I51).
    """
    pws = standings_doc.get("playoff_week_start")
    if not isinstance(pws, int) or pws < 2:
        raise CaptureError(f"playoff_week_start must be an int >= 2, got {pws!r}")
    weeks = standings_doc.get("weeks")
    if not isinstance(weeks, list) or len(weeks) < pws - 1:
        raise CaptureError("standings source lacks the final regular-season week")
    final_week = weeks[pws - 2]
    if final_week.get("week") != pws - 1 or final_week.get("is_playoff"):
        raise CaptureError(
            f"weeks[{pws - 2}] is not the final regular-season week "
            f"(week={final_week.get('week')}, is_playoff={final_week.get('is_playoff')})"
        )

    recomputed = {}
    for row in final_week.get("standings", []):
        recomputed[row["roster_id"]] = {
            "wins": row["wins"],
            "pf": float(row["pf"]),
        }

    owner_records = {}
    for entry in standings_doc.get("roster_map", []):
        rid = entry["roster_id"]
        if rid not in recomputed:
            raise CaptureError(f"2025 roster {rid} missing from final-week standings")
        final_record = entry.get("final_record") or {}
        if (
            final_record.get("wins") != recomputed[rid]["wins"]
            or float(final_record.get("fpts", -1)) != recomputed[rid]["pf"]
        ):
            raise CaptureError(
                f"final_record cross-check failed for roster {rid}: recomputed "
                f"{recomputed[rid]}, stored {final_record} (I46 fails closed)"
            )
        owner_records[entry["owner_id"]] = recomputed[rid]

    franchises = []
    for roster in rosters_2026:
        owner_id = roster.get("owner_id")
        record = owner_records.get(owner_id)
        franchises.append(
            {
                "roster_id": roster["roster_id"],
                "owner_id": owner_id,
                "wins_2025": record["wins"] if record else 0,
                "points_for_2025": record["pf"] if record else 0.0,
                "matched": record is not None,
            }
        )

    franchises.sort(
        key=lambda f: (-f["wins_2025"], -f["points_for_2025"], f["roster_id"])
    )
    for rank, franchise in enumerate(franchises, start=1):
        franchise["rank"] = rank
    return franchises


# ---------------------------------------------------------------------------
# S5/S6 — the bundle compiler
# ---------------------------------------------------------------------------

ORDERING_VERSION = "baseline_ordering_v1"
REDACTION_VERSION = "baseline_redaction_v1"
PROJECTION_VERSION = "baseline_projection_v1"

EDITION_CUTOFF_FIELD = {
    "2026-preseason": "preseason_cutoff_utc",
    "2026-wk01-preview": "preview_cutoff_utc",
}


def _projection_code_sha256() -> str:
    source = inspect.getsource(build_baseline_standings) + inspect.getsource(
        _build_decision_input
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _build_decision_input(edition_id, arm_id, cutoff_utc, franchises) -> dict:
    return {
        "edition_id": edition_id,
        "arm_id": arm_id,
        "cutoff_utc": cutoff_utc,
        "ranking_basis": "2025 final regular-season standings (R5)",
        "franchises": franchises,
    }


def _latest_envelope_at_or_before(source_id, roots, cutoff_utc: str):
    """I19 — latest VERIFIED envelope with captured_at <= cutoff; a
    post-cutoff envelope is never selected, a tampered one never counts."""
    try:
        from scripts.capture_2026 import verify_envelope
    except ImportError:  # pragma: no cover
        from capture_2026 import verify_envelope

    cutoff_dt = datetime.fromisoformat(cutoff_utc.replace("Z", "+00:00"))
    candidates = []
    for root in roots:
        source_dir = Path(root) / source_id
        if source_dir.is_dir():
            candidates.extend(source_dir.glob("*.json"))
    for path in sorted(candidates, key=lambda p: p.name, reverse=True):
        ok, _ = verify_envelope(path)
        if not ok:
            continue
        env = load_json_strict(path.read_bytes())
        captured_dt = datetime.fromisoformat(env["captured_at"].replace("Z", "+00:00"))
        if captured_dt <= cutoff_dt:
            return env
    return None


def _capture_manifest_entry(envelope: dict) -> dict:
    return {
        "kind": "capture",
        "source_id": envelope["source_id"],
        "locator": envelope["locator"],
        "content_sha256": sha256_hex(canonical_json_v1(envelope["payload"])),
        "canonicalizer_id": CANONICALIZER_ID,
        "canonicalizer_version": CANONICALIZER_VERSION,
        "canonicalizer_code_sha256": canonicalizer_code_sha256(),
        "envelope_sha256": envelope["envelope_sha256"],
        "payload_sha256": envelope["payload_sha256"],
        "captured_at": envelope["captured_at"],
    }


def compute_bundle_sha256(bundle: dict) -> str:
    body = {k: v for k, v in bundle.items() if k != "bundle_sha256"}
    return sha256_hex(canonical_json_v1(body))


def compile_bundle(
    edition_id: str,
    arm_id: str,
    *,
    policy_path,
    cutoff_receipt_path,
    public_root=None,
    private_root=None,
    repo_root=None,
    commit="HEAD",
) -> dict:
    """Compile the S5 frozen bundle for one (edition, arm).

    Selection is per source and per kind (I19); every hash is computed from
    content here — there is no caller-supplied factset or bundle hash (I20).
    """
    if edition_id not in EDITION_CUTOFF_FIELD:
        raise CaptureError(f"unknown edition {edition_id!r}")
    policy = load_policy(policy_path)
    if arm_id not in {
        a for arms in ("record_points",) for a in [arms]
    } and arm_id not in (
        "minimal_legal",
        "full_rich",
    ):
        raise CaptureError(f"unknown arm {arm_id!r}")

    receipt = load_cutoff_receipt(cutoff_receipt_path)
    cutoff_utc = receipt[EDITION_CUTOFF_FIELD[edition_id]]

    public = Path(public_root) if public_root is not None else PUBLIC_CAPTURE_ROOT
    private = Path(private_root) if private_root is not None else PRIVATE_CAPTURE_ROOT
    root = Path(repo_root) if repo_root is not None else REPO_ROOT

    selected_rows = [
        row
        for row in policy["rows"]
        if arm_id in row["arms"] or arm_id in row["required_for"]
    ]
    if not selected_rows:
        raise CaptureError(
            f"policy {policy['policy_version']} selects no sources for arm {arm_id!r}"
        )

    manifest = []
    envelopes_by_source = {}
    contains_private = False
    for row in sorted(selected_rows, key=lambda r: r["source_id"]):
        source_id = row["source_id"]
        if row["kind"] == "capture":
            roots = [public]
            if source_id == "chat_export":
                roots.append(private)
                contains_private = True
            envelope = _latest_envelope_at_or_before(source_id, roots, cutoff_utc)
            if envelope is None:
                raise CaptureError(
                    f"no verified envelope for required source {source_id!r} at or "
                    f"before {cutoff_utc} — bundle fails (I56)"
                )
            manifest.append(_capture_manifest_entry(envelope))
            envelopes_by_source[source_id] = envelope
        else:
            entry = freeze_qualified_artifact(
                source_id, row["locator_or_endpoint"], repo_root=root, commit=commit
            )
            manifest.append(entry)

    required_ids = {
        row["source_id"] for row in policy["rows"] if arm_id in row["required_for"]
    }
    present = {entry["source_id"] for entry in manifest}
    missing = required_ids - present
    if missing:
        raise CaptureError(f"manifest missing required sources {sorted(missing)} (I56)")

    if arm_id == "record_points":
        standings_entry = next(
            e for e in manifest if e["source_id"] == "standings_2025"
        )
        standings_doc = load_json_strict(
            _git_blob_bytes(root, standings_entry["git_blob_oid"])
        )
        rosters_env = envelopes_by_source["sleeper_rosters"]
        franchises = build_baseline_standings(
            standings_doc, rosters_env["payload"]["rosters"]
        )
    else:  # pragma: no cover — model arms are Tranche B
        raise CaptureError("model-arm bundles are Tranche B scope")

    decision_input = _build_decision_input(edition_id, arm_id, cutoff_utc, franchises)

    bundle = {
        "edition_id": edition_id,
        "arm_id": arm_id,
        "cutoff_utc": cutoff_utc,
        "cutoff_receipt_locator": str(cutoff_receipt_path),
        "cutoff_receipt_sha256": receipt["receipt_sha256"],
        "source_manifest": manifest,
        "source_manifest_sha256": sha256_hex(canonical_json_v1(manifest)),
        "decision_input_payload": decision_input,
        "decision_input_sha256": sha256_hex(canonical_json_v1(decision_input)),
        "projection": {
            "ordering_version": ORDERING_VERSION,
            "redaction_version": REDACTION_VERSION,
            "projection_version": PROJECTION_VERSION,
            "code_sha256": _projection_code_sha256(),
            "config_sha256": sha256_hex(
                canonical_json_v1(
                    {
                        "ordering": "wins desc, points_for desc, roster_id asc",
                        "redactions": [],
                    }
                )
            ),
            "parameters": {"season": 2026, "join_key": "owner_id"},
        },
        "policy_locator": str(policy_path),
        "matrix_sha256": policy["policy_sha256"],
        "contains_private": contains_private,
    }
    bundle["bundle_sha256"] = compute_bundle_sha256(bundle)
    return bundle


def bundle_path_for(bundle: dict, public_bundles_root=None, private_bundles_root=None):
    if bundle.get("contains_private"):
        root = (
            Path(private_bundles_root)
            if private_bundles_root is not None
            else PRIVATE_BUNDLE_ROOT
        )
    else:
        root = (
            Path(public_bundles_root) if public_bundles_root is not None else SEALS_ROOT
        )
    return root / bundle["edition_id"] / bundle["arm_id"] / "bundle.json"


def write_bundle(bundle: dict, *, public_bundles_root=None, private_bundles_root=None):
    """I22 — a bundle containing any private component lands under
    private_bundles/; append-only like every other artifact."""
    target = bundle_path_for(bundle, public_bundles_root, private_bundles_root)
    if target.exists():
        raise CaptureError(f"append-only bundles: {target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        f.write(canonical_json_v1(bundle))
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="bundle_2026.py",
        description="Compile the S5 frozen bundle for one (edition, arm).",
    )
    parser.add_argument(
        "--edition", required=False, choices=sorted(EDITION_CUTOFF_FIELD)
    )
    parser.add_argument("--arm", required=False, default="record_points")
    parser.add_argument(
        "--policy",
        required=False,
        help="exact policy version file, e.g. content/governance/source_policy_2026.v1.json",
    )
    args = parser.parse_args(argv)

    if not args.edition or not args.policy:
        parser.print_usage(sys.stderr)
        print("bundle_2026.py: --edition and --policy are required", file=sys.stderr)
        return 2

    try:
        from scripts.cutoff_2026 import latest_cutoff_receipt_path
    except ImportError:  # pragma: no cover
        from cutoff_2026 import latest_cutoff_receipt_path

    receipt_path = latest_cutoff_receipt_path()
    if receipt_path is None:
        print(
            "no cutoff receipt; run cutoff_2026.py --season 2026 --write-receipt",
            file=sys.stderr,
        )
        return 1
    try:
        bundle = compile_bundle(
            args.edition,
            args.arm,
            policy_path=args.policy,
            cutoff_receipt_path=receipt_path,
        )
        target = write_bundle(bundle)
    except CaptureError as exc:
        print(f"bundle failed closed: {exc}", file=sys.stderr)
        return 1
    print(f"bundle: {target}")
    print(f"  bundle_sha256 {bundle['bundle_sha256']}")
    print(f"  decision_input_sha256 {bundle['decision_input_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
