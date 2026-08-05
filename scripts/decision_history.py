"""Sealed prior judgments. Separate from state_at: the world vs. our judgments about it.

Contract: docs/superpowers/plans/2026-08-02-jailyard-temporal-kernel.md K1.5.
Directory file-naming contract (the ONLY four species; every reader globs its
own suffix, never `*.json`):
  {edition_id}.seal.json     -- the SealedDecision (seal())
  {edition_id}.ranking.json  -- sealed ranking body (seal())
  {edition_id}.claims.json   -- sealed claims body (seal())
  {edition_id}.run.json      -- CLOSED decision-run receipt (K3 persist_run)
All four are exclusive-create; the seal is the transaction commit marker: a
cell without its .seal.json does not exist.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_schema import fact_hash  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import fact_hash  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEALS_ROOT = ROOT / "content" / "decisions"


class CrossArmContamination(RuntimeError):
    """An arm tried to consume another arm's or trial's judgment."""


@dataclass(frozen=True)
class SealedDecision:
    edition_id: str
    season: int
    cutoff_utc: str
    arm_id: str
    trial_id: int
    state_hash: str
    run_id: str
    ranking_hash: str
    claims_hash: str
    decision_hash: str
    # Lineage is RECORDED, not just enforced at runtime: verify_predecessor
    # checks it, and this field makes the chain auditable from committed files
    # alone. None only at preseason, where no qualified predecessor exists.
    predecessor_decision_hash: str | None
    # Design §6: every 2025 backtest artifact carries an EXPLICIT retrospective
    # label; seal() hard-codes it for season 2025 and verify_tree enforces it.
    label: str
    # Content LOCATORS, not just hashes -- root-relative POSIX (the Phase-P
    # portable-locator law): a machine-absolute path is a host/user leak into a
    # tracked file and makes decision_hash differ per machine.
    ranking_path: str
    claims_path: str
    run_receipt_path: str
    # The receipt's CONTENT is bound, not just its name.
    run_receipt_hash: str


def write_json_once(path, doc):
    """Exclusive-create canonical writer -- same semantics as Phase-P's
    `_write_json_once` (scripts/seal_2026.py:148): open(path, "xb") so
    append-only holds even under concurrent writers, and a crashed prior
    attempt's file is refused rather than truncated."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as handle:  # FileExistsError IS the immutability guard
        handle.write(
            json.dumps(
                doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        )
    return path


def seal(
    root,
    edition_id,
    season,
    cutoff_utc,
    arm_id,
    trial_id,
    state_hash,
    ranking,
    claims,
    run_id,
    run_receipt_path,
    run_receipt_hash,
    predecessor_decision_hash=None,
):
    from scripts.bundle_2026 import (
        portable_locator,
    )  # Phase-P's law, reused not reimplemented

    # The receipt is OPENED and verified, not trusted: its bytes must match
    # run_receipt_hash, and it must be CLOSED (ended_at + output_decision_hash
    # non-null) -- a seal must never bind a receipt it has not read.
    receipt_doc = json.loads(Path(run_receipt_path).read_text(encoding="utf-8"))
    if fact_hash(receipt_doc) != run_receipt_hash:
        raise ValueError(
            f"receipt at {run_receipt_path} does not match run_receipt_hash"
        )
    if not receipt_doc.get("ended_at") or not receipt_doc.get("output_decision_hash"):
        raise ValueError("seal refuses an OPEN run receipt")

    rh, ch = fact_hash(ranking), fact_hash(claims)
    d = Path(root) / f"{season}" / arm_id / f"trial{trial_id}"
    p = d / f"{edition_id}.seal.json"
    d.mkdir(parents=True, exist_ok=True)
    # Persist the bodies FIRST (exclusive-create), then seal over their
    # locations. A seal naming a nonexistent file is worse than no locator.
    rp, cp = d / f"{edition_id}.ranking.json", d / f"{edition_id}.claims.json"
    write_json_once(rp, ranking)
    write_json_once(cp, claims)
    body = {
        "edition_id": edition_id,
        "season": season,
        "cutoff_utc": cutoff_utc,
        "arm_id": arm_id,
        "trial_id": trial_id,
        "state_hash": state_hash,
        "run_id": run_id,
        "ranking_hash": rh,
        "claims_hash": ch,
        "predecessor_decision_hash": predecessor_decision_hash,
        "label": "retrospective_backtest",  # design §6; hard-coded for the 2025 lane
        "ranking_path": portable_locator(rp, Path(root)),
        "claims_path": portable_locator(cp, Path(root)),
        "run_receipt_path": portable_locator(Path(run_receipt_path), Path(root)),
        "run_receipt_hash": run_receipt_hash,
    }
    s = SealedDecision(**body, decision_hash=fact_hash(body))
    write_json_once(p, asdict(s))  # exclusive-create IS the immutability guard
    return s


def load_decision(sealed, root):
    """Return the sealed ranking and claims, verifying both against their hashes.

    Locators are root-relative POSIX, so the caller supplies the root they were
    sealed under. This is what the inertia comparator consumes: `unchanged
    prior decision` means THIS body, re-scored -- not a hash compared to itself.
    """
    ranking = json.loads((Path(root) / sealed.ranking_path).read_text(encoding="utf-8"))
    claims = json.loads((Path(root) / sealed.claims_path).read_text(encoding="utf-8"))
    if fact_hash(ranking) != sealed.ranking_hash:
        raise ValueError(
            f"{sealed.edition_id}: sealed ranking body does not match its hash"
        )
    if fact_hash(claims) != sealed.claims_hash:
        raise ValueError(
            f"{sealed.edition_id}: sealed claims body does not match its hash"
        )
    return ranking, claims


def decision_history_at(season, cutoff, arm_id, trial_id, root=SEALS_ROOT):
    d = Path(root) / f"{season}" / arm_id / f"trial{trial_id}"
    if not d.exists():
        return []
    out = []
    # Suffix-exact: the directory holds four file species and a bare *.json
    # glob would parse ranking/claims bodies as SealedDecision records --
    # TypeError on the first populated directory. Every reader globs its OWN
    # suffix.
    for p in sorted(d.glob("*.seal.json")):
        s = SealedDecision(**json.loads(p.read_text(encoding="utf-8")))
        if s.cutoff_utc < cutoff:  # strictly earlier
            out.append(s)
    return sorted(out, key=lambda s: s.cutoff_utc)


def verify_predecessor(sealed, arm_id, trial_id):
    if sealed.arm_id != arm_id or sealed.trial_id != trial_id:
        raise CrossArmContamination(
            f"predecessor belongs to arm={sealed.arm_id} trial={sealed.trial_id}, "
            f"consumer is arm={arm_id} trial={trial_id}"
        )
    return sealed


def verify_tree(root):
    """The kernel verifier: audit every sealed cell from committed files alone.

    Returns (checked, failures) where failures is a list of (path, problems).
    Checks: decision_hash recompute, locator resolution + body hashes, receipt
    hash + closedness, the retrospective label for season 2025, and predecessor
    lineage resolving to an existing same-arm same-trial seal.
    """
    root = Path(root)
    seals = []
    hashes = {}
    for p in sorted(root.glob("*/*/*/*.seal.json")):
        s = SealedDecision(**json.loads(p.read_text(encoding="utf-8")))
        seals.append((p, s))
        hashes[(s.arm_id, s.trial_id, s.edition_id)] = s.decision_hash
    checked, failures = 0, []
    for p, s in seals:
        checked += 1
        problems = []
        body = {k: v for k, v in asdict(s).items() if k != "decision_hash"}
        if fact_hash(body) != s.decision_hash:
            problems.append("decision_hash mismatch")
        try:
            load_decision(s, root)  # locators + body hashes
        except Exception as exc:  # noqa: BLE001 - every failure is a finding
            problems.append(f"body: {exc}")
        try:
            receipt = json.loads(
                (root / s.run_receipt_path).read_text(encoding="utf-8")
            )
            if fact_hash(receipt) != s.run_receipt_hash:
                problems.append("receipt hash mismatch")
            if not receipt.get("ended_at") or not receipt.get("output_decision_hash"):
                problems.append("receipt not closed")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"receipt: {exc}")
        if s.season == 2025 and s.label != "retrospective_backtest":
            problems.append(f"label {s.label!r}")
        if s.predecessor_decision_hash is not None:
            preds = [
                h
                for (a, tr, _), h in hashes.items()
                if a == s.arm_id
                and tr == s.trial_id
                and h == s.predecessor_decision_hash
            ]
            if not preds:
                problems.append("predecessor lineage unresolvable in same arm/trial")
        if problems:
            failures.append((str(p), problems))
    return checked, failures


def main():
    ap = argparse.ArgumentParser(prog="decision_history.py")
    ap.add_argument(
        "--verify-tree",
        metavar="ROOT",
        required=True,
        help="audit every sealed cell under ROOT from committed files alone",
    )
    a = ap.parse_args()
    checked, failures = verify_tree(a.verify_tree)
    for path, problems in failures:
        print(f"FAIL {path}: {problems}")
    print(f"checked {checked}, failures {len(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
