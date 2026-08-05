"""Compile the three D1 states from the temporal kernel. K2.1 of plan 562e90d.

Custody split: all three D1 descriptors request access_scope=league_private, so
the compiled state.json embeds private chat text and lives ONLY under the
gitignored private_editions/ root. The TRACKED <edition>/compiled/ tree holds
descriptor.json, state_manifest.json (binding the private state by
state_payload_sha256) and source_hashes.json -- hashes and counts, no text.
Every consumer resolves states through load_compiled_state (hash-verifying),
never a direct file read. state_at is the SOLE authority: the persisted state
is its serialization, fact for fact.
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_schema import FACT_FIELDS, fact_hash  # noqa: E402
    from scripts.temporal_state import state_at  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import FACT_FIELDS, fact_hash  # noqa: E402
    from temporal_state import state_at  # noqa: E402
from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EDITIONS_ROOT = ROOT / "content" / "editions"
PRIVATE_EDITIONS_ROOT = ROOT / "private_editions"
PREVIEW_CUTOFF_PATH = ROOT / "content" / "governance" / "preview_cutoff_2025.v1.json"

# Test hook: every private state path the resolver opens is recorded here, so a
# suite-level control can assert the repository's real private root was never
# touched by relocated tests.
OPENED_PRIVATE_PATHS = []


@dataclass(frozen=True)
class EditionDescriptor:
    edition_id: str
    season: int
    kind: str
    cutoff_utc: str
    access_scope: str
    as_recorded_at: str | None
    predecessors: tuple


def _serialize_state(state):
    return {
        "season": state.season,
        "cutoff": state.cutoff,
        "access_scope": state.access_scope,
        "as_recorded_at": state.as_recorded_at,
        "admitted": [
            {**{k: getattr(f, k) for k in FACT_FIELDS}, "payload": f.payload}
            for f in state.admitted
        ],
    }


def _sha256_file(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_hashes(descriptor):
    """Every consumed input, as structured repo-relative paths and hashes."""
    import scripts.temporal_state as ts

    hashes = {}
    fact_file = ts.FACTS_ROOT / f"{descriptor.season}.jsonl"
    hashes["fact_store"] = {
        "path": f"data/facts/{descriptor.season}.jsonl",
        "sha256": _sha256_file(fact_file),
    }
    private_file = ts.PRIVATE_FACTS_ROOT / f"{descriptor.season}.jsonl"
    if private_file.exists():
        hashes["private_fact_store"] = {
            "path": f"private_facts/{descriptor.season}.jsonl",
            "sha256": _sha256_file(private_file),
        }
    hashes["normalizer_code"] = {
        "path": "scripts/normalize_facts.py",
        "sha256": _sha256_file(ROOT / "scripts" / "normalize_facts.py"),
    }
    hashes["fact_type_registry"] = {
        "path": "content/governance/fact_types.json",
        "sha256": _sha256_file(ROOT / "content" / "governance" / "fact_types.json"),
    }
    return hashes


def _check_preview_cutoff(descriptor):
    """A preview edition's cutoff must equal the RETAINED derivation -- never a
    human transcription. Refuse to compile otherwise."""
    if descriptor.kind != "preview":
        return
    if not PREVIEW_CUTOFF_PATH.exists():
        raise FileNotFoundError(
            f"preview cutoff artifact absent at {PREVIEW_CUTOFF_PATH}; "
            "derive it via scripts/kickoff_source.py --derive-preview-cutoff"
        )
    derived = load_json(PREVIEW_CUTOFF_PATH, required=True)["cutoff_utc"]
    if descriptor.cutoff_utc != derived:
        raise ValueError(
            f"preview descriptor cutoff {descriptor.cutoff_utc} != derived {derived}; "
            "the retained derivation is the authority"
        )


def compile_state(descriptor):
    """Compile one edition. Tracked artifacts under EDITIONS_ROOT/<ed>/compiled/;
    the state itself under PRIVATE_EDITIONS_ROOT/<ed>/state.json. Exclusive:
    an already-compiled edition is refused (use --verify for a re-check)."""
    _check_preview_cutoff(descriptor)
    editions_root = Path(EDITIONS_ROOT)
    private_root = Path(PRIVATE_EDITIONS_ROOT)
    out = editions_root / descriptor.edition_id / "compiled"
    priv = private_root / descriptor.edition_id
    if out.exists() or (priv / "state.json").exists():
        raise FileExistsError(
            f"{descriptor.edition_id} is already compiled; use --verify, or delete "
            "both the compiled/ tree and the private state to rebuild"
        )
    state = state_at(
        descriptor.season,
        descriptor.cutoff_utc,
        descriptor.access_scope,
        as_recorded_at=descriptor.as_recorded_at,
    )
    doc = _serialize_state(state)
    payload_hash = fact_hash(doc)

    # Private state first (the manifest must bind bytes that exist), then the
    # tracked tree via staging + atomic rename.
    priv.mkdir(parents=True, exist_ok=True)
    with open(priv / "state.json", "x", encoding="utf-8", newline="\n") as handle:
        json.dump(
            doc, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    staging = out.with_name("compiled.tmp")
    if staging.exists():
        raise FileExistsError(f"stale staging tree {staging}; remove it first")
    staging.mkdir(parents=True)
    _dump(
        staging / "descriptor.json",
        {**descriptor.__dict__, "predecessors": list(descriptor.predecessors)},
    )
    _dump(
        staging / "state_manifest.json",
        {
            "edition_id": descriptor.edition_id,
            "state_payload_sha256": payload_hash,
            "state_path": f"private_editions/{descriptor.edition_id}/state.json",
            "admitted_count": len(state.admitted),
            "admitted_by_type": _counts_by_type(state.admitted),
        },
    )
    _dump(staging / "source_hashes.json", _source_hashes(descriptor))
    staging.rename(out)
    return out


def _counts_by_type(admitted):
    by = {}
    for f in admitted:
        by[f.fact_type] = by.get(f.fact_type, 0) + 1
    return by


def _dump(path, doc):
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def load_compiled_state(edition_id, editions_root=None, private_root=None):
    """THE single state resolver every consumer uses: tracked manifest ->
    private state -> hash verification. Fails closed on an absent private root
    or any mismatch; no consumer ever trusts an unverified file."""
    editions_root = (
        Path(editions_root) if editions_root is not None else Path(EDITIONS_ROOT)
    )
    private_root = (
        Path(private_root) if private_root is not None else Path(PRIVATE_EDITIONS_ROOT)
    )
    manifest_path = editions_root / edition_id / "compiled" / "state_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"no compiled manifest for {edition_id} at {manifest_path}"
        )
    manifest = load_json(manifest_path, required=True)
    state_path = private_root / edition_id / "state.json"
    OPENED_PRIVATE_PATHS.append(str(state_path))
    if not state_path.exists():
        raise FileNotFoundError(
            f"private state absent at {state_path}; a league_private edition requires "
            "local private rehydration (the tracked tree deliberately has no state.json)"
        )
    doc = json.loads(state_path.read_text(encoding="utf-8"))
    if fact_hash(doc) != manifest["state_payload_sha256"]:
        raise ValueError(
            f"{edition_id}: private state does not match the tracked manifest hash; "
            "refusing a tampered or relocated state"
        )
    return doc


def verify_compiled(descriptor):
    """No-write verification: recompute the state and compare against the
    persisted manifest + private bytes. Returns [] or a list of problems."""
    problems = []
    try:
        doc = load_compiled_state(descriptor.edition_id)
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]
    state = state_at(
        descriptor.season,
        descriptor.cutoff_utc,
        descriptor.access_scope,
        as_recorded_at=descriptor.as_recorded_at,
    )
    recomputed = _serialize_state(state)
    if fact_hash(recomputed) != fact_hash(doc):
        problems.append(
            f"{descriptor.edition_id}: recomputed state differs from persisted state"
        )
    manifest = load_json(
        Path(EDITIONS_ROOT)
        / descriptor.edition_id
        / "compiled"
        / "state_manifest.json",
        required=True,
    )
    if manifest["state_payload_sha256"] != fact_hash(recomputed):
        problems.append(
            f"{descriptor.edition_id}: manifest hash differs from recomputation"
        )
    return problems


def _descriptor_from_file(path):
    raw = load_json(path, required=True)
    raw["predecessors"] = tuple(raw.get("predecessors", ()))
    return EditionDescriptor(**raw)


def main():
    ap = argparse.ArgumentParser(prog="compile_state.py")
    ap.add_argument("--descriptor", required=True)
    ap.add_argument(
        "--verify",
        action="store_true",
        help="no-write mode: recompute and compare against the persisted artifacts",
    )
    a = ap.parse_args()
    descriptor = _descriptor_from_file(a.descriptor)
    if a.verify:
        problems = verify_compiled(descriptor)
        if problems:
            for p in problems:
                print(f"FAIL {p}")
            return 1
        print(f"{descriptor.edition_id}: verified (no write)")
        return 0
    out = compile_state(descriptor)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
