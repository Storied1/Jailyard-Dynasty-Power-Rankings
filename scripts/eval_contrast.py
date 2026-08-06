"""Frozen evidence-family manifest and contrast integrity. K3.3 of plan 562e90d.

One rule for a required family with no qualified source: the contrast lane
never propagates an exception as a verdict. family_counts records unavailable
arms/families; assess_contrast returns degraded (first cycle) or
stop_no_decision (second) through a PERSISTED cycle counter keyed by the frozen
manifest hash. ManifestDrift and every unexpected exception exit the CLI at 4
(failed gate), never 1 -- a gate that reads a crash as a verdict is not a gate.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_schema import fact_hash  # noqa: E402
    from scripts.normalize_facts import LEGACY_SOURCES  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import fact_hash  # noqa: E402
    from normalize_facts import LEGACY_SOURCES  # noqa: E402

from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "content" / "governance" / "evidence_families.json"
CONTRAST_STATE_PATH = (
    ROOT / "content" / "editions" / "_evaluation" / "contrast_state.json"
)
REPORT_PATH = ROOT / "data" / "facts" / "2025.report.json"

_STAMPS = ("frozen_at", "manifest_sha256")


class ManifestDrift(RuntimeError):
    """The live producer surface differs from the frozen manifest. A FAILED
    GATE (CLI exit 4), never a remediable verdict: the only repair is a NEW
    manifest version, which discards every completed arm."""


@dataclass(frozen=True)
class ContrastResult:
    status: str  # ok | degraded | stop_no_decision
    missing: list = field(default_factory=list)
    reason: str = ""
    per_edition: dict = field(default_factory=dict)
    cycles_used: int = 0


def _manifest_body_hash(doc):
    return fact_hash({k: v for k, v in doc.items() if k not in _STAMPS})


def load_manifest(path=MANIFEST_PATH):
    doc = load_json(path, required=True)
    if doc.get("frozen_at") is not None and doc.get(
        "manifest_sha256"
    ) != _manifest_body_hash(doc):
        raise ManifestDrift(
            f"manifest at {path} does not match its own frozen hash; refusing a tampered manifest"
        )
    return doc


def freeze_manifest(path=MANIFEST_PATH, frozen_at=None):
    """Stamp frozen_at + manifest_sha256 (hash over the whole document with
    both stamp fields excluded, so the hash is stable). Refuses a second
    freeze. frozen_at is passed in, never read from the clock."""
    if not frozen_at:
        raise ValueError("freeze_manifest requires an explicit frozen_at instant")
    doc = load_json(path, required=True)
    if doc.get("frozen_at") is not None:
        raise ValueError(
            f"manifest already frozen at {doc['frozen_at']}; a second freeze is refused"
        )
    doc["frozen_at"] = frozen_at
    doc["manifest_sha256"] = _manifest_body_hash(doc)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return doc


def _recomputed_producers():
    """Per-family live source_ids + normalizer_version, recomputed from the
    persisted normalization report and the K1.6 source maps -- what makes 'no
    source may be added after freezing' enforceable rather than declarative."""
    report = load_json(REPORT_PATH, required=True)
    live_version = report["normalizer_version"]
    producers = {}
    manifest = load_json(MANIFEST_PATH, required=True)
    for fam in manifest["families"]:
        name = fam["family"]
        if name in LEGACY_SOURCES:
            src = LEGACY_SOURCES[name][0]
            producers[name] = {
                "source_ids": [] if src is None else [f"legacy:{src}"],
                "normalizer_version": live_version,
            }
        else:  # media_item: not one of the nine bridge types, no producer
            producers[name] = {"source_ids": [], "normalizer_version": None}
    return producers


def family_counts(arm_id, editions_root=None):
    """The computed diff over admitted fact types, recorded per edition. For
    each compiled edition: hash-verified state resolution, then THIS arm's
    bundle; ArmUnavailable is caught per (arm, edition) and recorded at count 0
    with the arm marked unavailable. normalize_all's recorded refusals are
    folded in so a declared-unsourced family reads as DEGRADED, never as
    clean-but-empty."""
    # Deferred scripts.-form imports: eval_arms is K3.4; the contrast tests
    # inject counts and never require it.
    import scripts.compile_state as cs
    from scripts.claims_ledger import EDITION_IDS
    from scripts.eval_arms import ArmUnavailable, bundle_for, rehydrate_state

    editions_root = (
        Path(editions_root) if editions_root is not None else Path(cs.EDITIONS_ROOT)
    )
    per_edition, totals, unavailable = {}, {}, {}
    for edition_id in EDITION_IDS:
        descriptor = cs._descriptor_from_file(
            editions_root / edition_id / "descriptor.json"
        )
        doc = cs.load_compiled_state(edition_id, editions_root=editions_root)
        state = rehydrate_state(doc)
        try:
            bundle = bundle_for(arm_id, state, descriptor.kind)
            counts = {f: len(v) for f, v in bundle["facts"].items()}
        except ArmUnavailable as exc:
            counts = {}
            unavailable[f"{arm_id}@{edition_id}"] = str(exc)
        per_edition[edition_id] = counts
        for f, n in counts.items():
            totals[f] = totals.get(f, 0) + n
    report = load_json(REPORT_PATH, required=True)
    for fam, reason in report.get("unavailable", {}).items():
        unavailable.setdefault(fam, reason)
    return {"per_edition": per_edition, "totals": totals, "unavailable": unavailable}


def _read_cycles(state_path, manifest_sha256):
    p = Path(state_path)
    if not p.exists():
        return 0
    doc = json.loads(p.read_text(encoding="utf-8"))
    return doc["cycles_used"] if doc.get("manifest_sha256") == manifest_sha256 else 0


def _write_cycles(state_path, manifest_sha256, cycles_used):
    p = Path(state_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {"manifest_sha256": manifest_sha256, "cycles_used": cycles_used},
            handle,
            sort_keys=True,
            separators=(",", ":"),
        )
    return p


def _assess(manifest, full, minimal, state_path, _producers, increment):
    if manifest.get("frozen_at") is None:
        raise ValueError(
            "assess_contrast refuses an unfrozen manifest; freeze it first (K3.7 Step 1)"
        )
    live = _producers if _producers is not None else _recomputed_producers()
    for fam in manifest["families"]:
        name = fam["family"]
        frozen_view = {
            "source_ids": fam["source_ids"],
            "normalizer_version": fam["normalizer_version"],
        }
        if live.get(name) != frozen_view:
            raise ManifestDrift(
                f"{name}: live producers {live.get(name)} differ from frozen {frozen_view}; "
                "a producer change requires a NEW manifest version and discards every completed arm"
            )
    required = [f["family"] for f in manifest["families"] if f["required"]]
    unavailable = {**full.get("unavailable", {}), **minimal.get("unavailable", {})}
    missing = sorted(
        f for f in required if full["totals"].get(f, 0) == 0 or f in unavailable
    )
    per_edition = {"full": full["per_edition"], "minimal": minimal["per_edition"]}
    sha = manifest["manifest_sha256"]
    prior = _read_cycles(state_path, sha)
    if missing:
        if prior >= 1:
            return ContrastResult(
                status="stop_no_decision",
                missing=missing,
                reason=(
                    f"required families still without qualified evidence after the one "
                    f"approved remediation cycle: {missing}. STOP -- NO DECISION, NO "
                    f"EXPANSION; S1a does not begin."
                ),
                per_edition=per_edition,
                cycles_used=prior,
            )
        cycles = prior + 1 if increment else prior
        if increment:
            _write_cycles(state_path, sha, cycles)
        return ContrastResult(
            status="degraded",
            missing=missing,
            reason=f"required family without qualified evidence: {missing}",
            per_edition=per_edition,
            cycles_used=cycles,
        )
    if full["totals"] == minimal["totals"]:
        if prior >= 1:
            return ContrastResult(
                status="stop_no_decision",
                missing=[],
                reason=(
                    "no measurable difference between full and minimal bundles after the "
                    "one approved remediation cycle. S1a does not begin."
                ),
                per_edition=per_edition,
                cycles_used=prior,
            )
        cycles = prior + 1 if increment else prior
        if increment:
            _write_cycles(state_path, sha, cycles)
        return ContrastResult(
            status="degraded",
            missing=[],
            reason="no measurable difference between full and minimal bundles",
            per_edition=per_edition,
            cycles_used=cycles,
        )
    return ContrastResult(status="ok", per_edition=per_edition, cycles_used=prior)


def assess_contrast(
    manifest, full, minimal, state_path=CONTRAST_STATE_PATH, _producers=None
):
    """`full`/`minimal` are family_counts RESULTS ({totals, per_edition,
    unavailable}), never flat maps. A degraded verdict increments the persisted
    cycle counter; a second degraded run is stop_no_decision."""
    return _assess(manifest, full, minimal, state_path, _producers, increment=True)


def preflight(
    manifest,
    editions_root=None,
    state_path=CONTRAST_STATE_PATH,
    _full=None,
    _minimal=None,
    _producers=None,
):
    """assess_contrast with increment=False: same required-family and
    difference checks, but ADVISORY -- it never consumes the one remediation
    cycle. _full/_minimal are test injections; production computes real
    family_counts before any model arm burns a trial."""
    full = _full if _full is not None else family_counts("full_rich", editions_root)
    minimal = (
        _minimal
        if _minimal is not None
        else family_counts("minimal_legal", editions_root)
    )
    return _assess(manifest, full, minimal, state_path, _producers, increment=False)


def main():
    import argparse

    ap = argparse.ArgumentParser(prog="eval_contrast.py")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--assess", action="store_true")
    mode.add_argument(
        "--preflight",
        action="store_true",
        help="judge contrast BEFORE model arms burn trials",
    )
    mode.add_argument("--freeze", action="store_true")
    ap.add_argument("--frozen-at", help="exact UTC instant; required with --freeze")
    ap.add_argument("--full-arm", default="full_rich")
    ap.add_argument("--minimal-arm", default="minimal_legal")
    a = ap.parse_args()
    if a.freeze:
        if not a.frozen_at:
            ap.error("--freeze requires --frozen-at")
        print(json.dumps(freeze_manifest(frozen_at=a.frozen_at), indent=2))
        return 0
    # cycles_used is read from and written to the persisted contrast state, keyed by
    # manifest_sha256 -- never supplied by the caller, or every re-run is cycle one.
    try:
        r = (
            preflight(load_manifest())
            if a.preflight
            else assess_contrast(
                load_manifest(), family_counts(a.full_arm), family_counts(a.minimal_arm)
            )
        )
    except Exception as exc:  # noqa: BLE001 - ManifestDrift, IO, anything unforeseen
        # A crash is a FAILED GATE, never a verdict. Unhandled, CPython exits 1 --
        # which K3.7's case block would read as DEGRADED, conflating three
        # different events on one code.
        print(
            json.dumps(
                {"status": "failed_gate", "error": f"{type(exc).__name__}: {exc}"}
            ),
            file=sys.stderr,
        )
        return 4
    print(
        json.dumps(
            {
                "status": r.status,
                "missing": r.missing,
                "reason": r.reason,
                "cycles_used": r.cycles_used,
                "per_edition": r.per_edition,
            },
            indent=2,
            sort_keys=True,
        )
    )
    # 2 is deliberately skipped: argparse exits 2 on a usage error, and a gate that
    # branched on 2 would read a mistyped flag as a stop-no-decision verdict.
    return {"ok": 0, "degraded": 1, "stop_no_decision": 3}[r.status]


if __name__ == "__main__":
    raise SystemExit(main())
