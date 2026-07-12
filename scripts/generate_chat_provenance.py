#!/usr/bin/env python
"""Provenance manifest for the chat pipeline (two-layer, checkout-portable).

Binds the private raw source (_chat.txt), the committed SOURCE (name-map), the
DERIVED INTERMEDIATES the pipeline reparses (parsed_messages + identity_chain),
the committed DATA the pipeline reads (week{N}_data), the pipeline CODE, and the
committed DERIVED OUTPUTS (analytics, personas, the 19 contexts) via hashes.

Two layers (kept mechanically separate so a machine-specific checkout path can
authorize a write but never persists into the portable manifest):

  * PORTABLE PAYLOAD -- what gets persisted to content/chat/provenance.json and
    compared by --verify / --verify-public. Logical (repo-relative POSIX) keys
    only; NO absolute checkout path. Roles: inputs_private, inputs_source,
    derived_intermediates, inputs_data, code, outputs_derived, plus the
    private-derived `counts`.
  * RECEIPT ENVELOPE -- emitted by --rebuild-check (see the rebuild-check module
    added in the follow-up step). = {authorization: {normalized_source_root},
    payload: <portable payload>}. `normalized_source_root` is receipt-only
    AUTHORIZATION metadata: it gates --write but is never persisted and never
    compared by --verify/--verify-public.

Hashing (checkout-portable):
  - CODE / TEXT (.py/.md/.txt): LF-normalized content hash == the git blob, so a
    fresh LF checkout on any OS verifies.
  - JSON: CANONICAL (sort_keys, compact) hash -- prettier-invariant.

Roles are EXPLICIT (no broad glob). Fail-closed: any missing declared file, any
null hash, or any unclassified extra file in a hashed dir is a hard error / NONZERO.

Root-aware: derived nodes resolve under OUTPUT_ROOT, sources under SOURCE_ROOT;
both map to the SAME logical repo-relative key (via shared.rel_to_root), so a
rebuild into an external OUTPUT_ROOT still yields portable keys.

Usage:
  python scripts/generate_chat_provenance.py                 # --verify (default)
  python scripts/generate_chat_provenance.py --verify-public # private chat/* absent
  python scripts/generate_chat_provenance.py --write --receipt <path>
"""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import CONTENT_CHAT_OUT_DIR  # noqa: E402
from shared import (
    CHAT_TXT_PATH,
    IDENTITY_CHAIN_PATH,
    NAME_MAP_PATH,
    OUTPUT_ROOT,
    PARSED_MESSAGES_PATH,
    PRESEASON_OUT_DIR,
    SOURCE_ROOT,
    WEEKS_DIR,
    WEEKS_OUT_DIR,
    load_json,
    month_key_strict,
    rel_to_root,
    roster_persona_slugs,
)

SCRIPTS = Path(__file__).resolve().parent
PERSONAS_DIR = CONTENT_CHAT_OUT_DIR / "personas"

SCHEMA = (
    "chat-provenance/3"  # /3: parsed_messages+identity_chain -> derived_intermediates
)
RECEIPT_KIND = "chat-provenance-receipt/1"

# shared.py + the chat-pipeline scripts + the recompute producer + this script.
CODE_FILES = [
    SCRIPTS / "shared.py",
    SCRIPTS / "parse_whatsapp.py",
    SCRIPTS / "fingerprint_members.py",
    SCRIPTS / "split_chat_months.py",
    SCRIPTS / "map_chat_deterministic.py",
    SCRIPTS / "reduce_chat_deterministic.py",
    SCRIPTS / "recompute_projection.py",
    SCRIPTS / "build_chat_context.py",
    SCRIPTS / "generate_chat_provenance.py",
]

# Derived analytics JSON in content/chat/ (reduce_chat_deterministic outputs).
DERIVED_ANALYTICS = [
    "arcs.json",
    "consensus.json",
    "fingerprints.json",
    "league-memory.json",
    "predictions.json",
    "relationships.json",
]

# content/chat/*.json legitimately present but NOT chat-pipeline outputs.
KNOWN_NON_PIPELINE_CHAT_JSON = {
    "media-catalog.json",
    ".media_progress.json",
    "provenance.json",
    "name-map.json",  # source, hashed under inputs_source, not an output
}

WEEKS = range(1, 19)  # 1..18

# Payload keys stripped for the PUBLIC projection (private roles + private-derived
# counts). Everything under chat/ is private/gitignored (absent on a fresh CI
# checkout), so both inputs_private and derived_intermediates come out.
PRIVATE_PAYLOAD_KEYS = ("counts", "inputs_private", "derived_intermediates")


def _sha(b):
    return "sha256:" + hashlib.sha256(b).hexdigest()


def text_sha(path, errors):
    """LF-normalized content hash for code/text (== the git blob)."""
    p = Path(path)
    if not p.exists():
        errors.append(f"MISSING code/text file: {rel_to_root(p)}")
        return None
    return _sha(p.read_bytes().replace(b"\r\n", b"\n"))


def canonical_sha(path, errors):
    """Semantic (prettier-invariant) hash for a JSON artifact."""
    p = Path(path)
    obj = load_json(p, warn=False)
    if obj is None:
        errors.append(f"MISSING or unreadable JSON: {rel_to_root(p)}")
        return None
    canon = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return _sha(canon.encode("utf-8"))


def compute_counts(errors):
    """Aggregate corpus stats from parsed_messages.json. PRIVATE-DERIVED: reads a
    private/gitignored intermediate, so it is excluded from the public projection."""
    parsed = load_json(PARSED_MESSAGES_PATH, warn=False)
    if parsed is None:
        errors.append(
            f"MISSING derived intermediate: {rel_to_root(PARSED_MESSAGES_PATH)}"
        )
        return None
    msgs = parsed if isinstance(parsed, list) else parsed.get("messages", parsed)
    if not isinstance(msgs, list):
        errors.append("parsed_messages.json is not a list of messages")
        return None
    return {
        "messages": len(msgs),
        "is_system": sum(1 for m in msgs if m.get("is_system")),
        "is_poll": sum(1 for m in msgs if m.get("is_poll")),
        "u200e_residue": sum(
            1 for m in msgs if isinstance(m.get("text"), str) and "‎" in m["text"]
        ),
        "media": sum(1 for m in msgs if m.get("media")),
        "members": len({m.get("sender") for m in msgs if m.get("sender")}),
    }


def _guard_content_chat_dir(errors):
    """Fail closed if an unclassified *.json shows up in the OUTPUT content/chat/."""
    if not CONTENT_CHAT_OUT_DIR.exists():
        errors.append(f"MISSING directory: {rel_to_root(CONTENT_CHAT_OUT_DIR)}")
        return
    known = set(DERIVED_ANALYTICS) | KNOWN_NON_PIPELINE_CHAT_JSON
    actual = {p.name for p in CONTENT_CHAT_OUT_DIR.glob("*.json")}
    extra = sorted(actual - known)
    if extra:
        errors.append(
            "unclassified content/chat/*.json (classify before hashing): "
            + ", ".join(extra)
        )


def _outputs(errors):
    """Derived-output role: analytics + personas + the 19 contexts."""
    _guard_content_chat_dir(errors)
    outputs = {}
    for name in DERIVED_ANALYTICS:
        outputs[rel_to_root(CONTENT_CHAT_OUT_DIR / name)] = canonical_sha(
            CONTENT_CHAT_OUT_DIR / name, errors
        )
    persona_files = sorted(PERSONAS_DIR.glob("*.md"))
    if not persona_files:
        errors.append(f"no persona .md files found in {rel_to_root(PERSONAS_DIR)}")
    for p in persona_files:
        outputs[rel_to_root(p)] = text_sha(p, errors)
    for w in WEEKS:
        outputs[rel_to_root(WEEKS_OUT_DIR / f"week{w}_chat_context.json")] = (
            canonical_sha(WEEKS_OUT_DIR / f"week{w}_chat_context.json", errors)
        )
    outputs[rel_to_root(PRESEASON_OUT_DIR / "preseason_chat_context.json")] = (
        canonical_sha(PRESEASON_OUT_DIR / "preseason_chat_context.json", errors)
    )
    # Fail-closed extra-file guard: bind the output SET, not just the expected
    # iteration. Iterating `for w in WEEKS` alone never hashes an extra real
    # week99_chat_context.json, so --verify/--verify-public would pass with it
    # present. Reject any *_chat_context.json outside the expected set.
    exp_ctx = {f"week{w}_chat_context.json" for w in WEEKS}
    act_ctx = {p.name for p in WEEKS_OUT_DIR.glob("*_chat_context.json")}
    if act_ctx != exp_ctx:
        errors.append(
            "content/weeks chat_context set mismatch: "
            f"extra={sorted(act_ctx - exp_ctx)} missing={sorted(exp_ctx - act_ctx)}"
        )
    act_pre = {p.name for p in PRESEASON_OUT_DIR.glob("*_chat_context.json")}
    if act_pre != {"preseason_chat_context.json"}:
        errors.append(f"preseason chat_context set mismatch: {sorted(act_pre)}")
    return outputs


def compute_payload(errors, include_private=True):
    """The PORTABLE manifest payload (logical keys, no absolute path).

    include_private=False is the PUBLIC projection: omits the private roles
    (inputs_private + derived_intermediates, both under gitignored chat/) and the
    private-derived counts, so a fresh CI checkout without chat/* can verify it.
    """
    payload = {
        "schema": SCHEMA,
        "note": (
            "Provenance for the chat pipeline. Hashes only -- no message bodies. "
            "Code/text hashes are LF-normalized (== the git blob); JSON hashes are "
            "canonical (prettier-invariant). Portable: logical repo-relative keys, "
            "no absolute checkout path. normalized_source_root lives only in the "
            "rebuild receipt (authorization), never here."
        ),
        "generation": {
            "season": 2025,
            "weeks": "1-18 + preseason",
            "declared_parameters": {"no_ai": True},
            "declared_parameters_note": (
                "Operator-declared build flags, NOT independently verified: no_ai "
                "records the committed artifacts were built with --no-ai."
            ),
        },
        "inputs_source": {
            rel_to_root(NAME_MAP_PATH): canonical_sha(NAME_MAP_PATH, errors),
        },
        "inputs_data": {
            rel_to_root(WEEKS_DIR / f"week{w}_data.json"): canonical_sha(
                WEEKS_DIR / f"week{w}_data.json", errors
            )
            for w in WEEKS
        },
        "code": {rel_to_root(p): text_sha(p, errors) for p in CODE_FILES},
        "outputs_derived": _outputs(errors),
    }
    if include_private:
        payload["counts"] = compute_counts(errors)
        payload["inputs_private"] = {
            rel_to_root(CHAT_TXT_PATH): text_sha(CHAT_TXT_PATH, errors),
        }
        payload["derived_intermediates"] = {
            rel_to_root(PARSED_MESSAGES_PATH): canonical_sha(
                PARSED_MESSAGES_PATH, errors
            ),
            rel_to_root(IDENTITY_CHAIN_PATH): canonical_sha(
                IDENTITY_CHAIN_PATH, errors
            ),
        }
    return payload


def _public_view(payload):
    """Project a (persisted or recomputed) payload to its public subset."""
    return {k: v for k, v in payload.items() if k not in PRIVATE_PAYLOAD_KEYS}


def normalized_source_root():
    """The SOLE receipt authorization identity: realpath-resolved, normalized
    SOURCE_ROOT string. Amend-stable (no Git HEAD). Never persisted."""
    return os.path.normcase(str(Path(SOURCE_ROOT).resolve(strict=True))).replace(
        "\\", "/"
    )


def make_receipt(errors):
    """Build a receipt envelope from the CURRENT on-disk bytes (SOURCE_ROOT +
    OUTPUT_ROOT). Used by --rebuild-check (follow-up step) and by tests."""
    payload = compute_payload(errors, include_private=True)
    return {
        "kind": RECEIPT_KIND,
        "authorization": {"normalized_source_root": normalized_source_root()},
        "payload": payload,
    }


def _diff(expected, found, path=""):
    if isinstance(expected, dict) and isinstance(found, dict):
        for k in sorted(set(expected) | set(found)):
            sub = f"{path}.{k}" if path else k
            if k not in expected:
                yield f"  {sub}: unexpected key in committed = {found[k]!r}"
            elif k not in found:
                yield f"  {sub}: missing from committed (recomputed = {expected[k]!r})"
            else:
                yield from _diff(expected[k], found[k], sub)
    elif expected != found:
        yield f"  {path}: recomputed={expected!r}  committed={found!r}"


def cmd_verify(manifest_path, public):
    """--verify (full) / --verify-public. Compares only the PORTABLE payload;
    never a machine-specific absolute source path."""
    errors = []
    recomputed = compute_payload(errors, include_private=not public)
    label = "public" if public else "full"
    if errors:
        print(f"FAIL (fail-closed): cannot {label}-verify -- artifacts incomplete:")
        for e in errors:
            print(f"  - {e}")
        return 1
    committed = load_json(manifest_path, warn=False)
    if committed is None:
        print(f"FAIL: no readable manifest at {manifest_path}")
        return 1
    committed_cmp = _public_view(committed) if public else committed
    if recomputed == committed_cmp:
        print(f"OK: {rel_to_root(manifest_path)} matches recomputed ({label}).")
        return 0
    print(f"MISMATCH ({label}): {rel_to_root(manifest_path)} != recomputed:")
    for line in _diff(recomputed, committed_cmp):
        print(line)
    return 1


def cmd_write(manifest_path, receipt_path):
    """Receipt-bound write. Two-layer: (1) authorize on normalized_source_root,
    (2) recompute + exactly compare the portable payload, (3) persist ONLY the
    portable payload. Every rejection leaves the target manifest byte-identical."""
    if receipt_path is None:
        print("FAIL: --write requires --receipt <path>.")
        return 1
    receipt = load_json(Path(receipt_path), warn=False)
    if receipt is None:
        print(f"FAIL: missing/unreadable receipt at {receipt_path}.")
        return 1
    if not isinstance(receipt, dict) or receipt.get("kind") != RECEIPT_KIND:
        print("FAIL: malformed receipt (kind).")
        return 1
    auth = receipt.get("authorization")
    rcpt_root = auth.get("normalized_source_root") if isinstance(auth, dict) else None
    rcpt_payload = receipt.get("payload")
    if not isinstance(rcpt_root, str) or not isinstance(rcpt_payload, dict):
        print("FAIL: malformed receipt (authorization/payload).")
        return 1
    # (1) authorization -- wrong-root / identity mismatch.
    if rcpt_root != normalized_source_root():
        print(
            "FAIL: receipt normalized_source_root does not match this checkout (wrong root)."
        )
        return 1
    # (2) recompute + exact-compare the portable payload from current bytes.
    errors = []
    recomputed = compute_payload(errors, include_private=True)
    if errors:
        print("FAIL (fail-closed): refusing to write -- artifacts incomplete:")
        for e in errors:
            print(f"  - {e}")
        return 1
    if recomputed != rcpt_payload:
        print("FAIL: on-disk payload does not match the receipt:")
        for line in _diff(recomputed, rcpt_payload):
            print(line)
        return 1
    # (3) persist ONLY the portable payload.
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(recomputed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {manifest_path} (receipt-bound, portable payload).")
    return 0


# --- Rebuild driver (2e): external full-DAG + receipt ------------------------- #


def _resolve_disjoint(output_root):
    """Resolve SOURCE_ROOT and OUTPUT_ROOT; reject equality / overlap / symlink
    re-entry in BOTH directions (a rebuild must never write inside the repo).
    ``.resolve()`` follows symlinks, so a junction pointing back into the repo is
    caught as an ancestor/descendant."""
    src = Path(SOURCE_ROOT).resolve(strict=True)
    out = Path(output_root).resolve()
    if out == src:
        raise ValueError(
            f"OUTPUT_ROOT == SOURCE_ROOT ({out}); set JAILYARD_OUTPUT_ROOT to a "
            "fresh external dir"
        )
    if src in out.parents:
        raise ValueError(f"OUTPUT_ROOT {out} is INSIDE SOURCE_ROOT {src}")
    if out in src.parents:
        raise ValueError(f"OUTPUT_ROOT {out} is an ANCESTOR of SOURCE_ROOT {src}")
    return src, out


def _run_stage(name, argv, env, result):
    proc = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / f"{name}.py"), *argv],
        env=env,
        capture_output=True,
        text=True,
    )
    result["stages"].append({"name": name, "argv": list(argv), "rc": proc.returncode})
    if proc.returncode != 0:
        result["failed_stage"] = name
        result["stderr_tail"] = proc.stderr[-1500:]
    return proc.returncode == 0


def _expected_months(output_root, errors):
    parsed = load_json(Path(output_root) / "chat" / "parsed_messages.json", warn=False)
    if parsed is None:
        errors.append("candidate parsed_messages.json missing")
        return set()
    msgs = parsed if isinstance(parsed, list) else parsed.get("messages", parsed)
    try:
        return {month_key_strict(m.get("timestamp_utc", "")) for m in msgs}
    except ValueError as exc:
        errors.append(f"candidate corpus has a rejectable timestamp: {exc}")
        return set()


def _produced_months(output_root):
    d = Path(output_root) / "content" / "chat" / ".map_cache"
    if not d.exists():
        return set()
    return {p.stem for p in d.glob("*.json") if not p.stem.endswith("_raw")}


def run_rebuild(output_root, test_hooks=None):
    """Run the full chat DAG into an external OUTPUT_ROOT via subprocesses (env set
    BEFORE each child imports shared; ``-B`` / PYTHONDONTWRITEBYTECODE=1). Returns
    an in-memory structured result -- the TEST-ONLY detector surface (NOT persisted,
    NOT under OUTPUT_ROOT, NOT in the receipt / inventory / nonmutation snapshot).

    ``test_hooks``: {stage_name: callable(output_root)} run AFTER that stage -- a
    test-only seam; the production CLI (cmd_rebuild_check) never passes hooks.
    """
    output_root = Path(output_root)
    test_hooks = test_hooks or {}
    env = dict(os.environ)
    env["JAILYARD_OUTPUT_ROOT"] = str(output_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = {
        "stages": [],
        "failed_stage": None,
        "reduce_invoked": False,
        "month_gate": None,
        "persona_gate": None,
        "completed": False,
        "produced_paths": [],
        "exit_code": 1,
    }

    def finalize():
        # produced_paths = the WHOLE candidate root ({rel: kind}, non-following;
        # link kinds are never expected), so an extra file/dir/link/type ANYWHERE
        # (root-level included) fails the inventory.
        # exit_code mirrors what cmd_rebuild_check would return for this outcome.
        result["produced_paths"] = _root_entries(output_root)
        result["exit_code"] = 0 if result["completed"] else 1
        return result

    def stage(name, argv=()):
        ok = _run_stage(name, argv, env, result)
        if ok and name in test_hooks:
            test_hooks[name](output_root)
        return ok

    for name in ("parse_whatsapp", "fingerprint_members", "split_chat_months"):
        if not stage(name):
            return finalize()
    if not stage("map_chat_deterministic"):
        return finalize()
    # [exact month-set gate] -- reject missing AND extra; NO REDUCE until it passes.
    merrs = []
    expected = _expected_months(output_root, merrs)
    produced = _produced_months(output_root)
    result["month_gate"] = {
        "ok": (not merrs) and expected == produced,
        "missing": sorted(expected - produced),
        "extra": sorted(produced - expected),
        "errors": merrs,
    }
    if not result["month_gate"]["ok"]:
        result["failed_stage"] = "month-set-gate"
        return finalize()
    # reduce_invoked reflects INVOCATION, not success -- set BEFORE the call so an
    # invoked-but-failed REDUCE can never read as "never ran".
    result["reduce_invoked"] = True
    if not stage("reduce_chat_deterministic"):
        return finalize()
    # [exact persona-set gate] -- produced personas == the roster slugs.
    name_map = load_json(NAME_MAP_PATH, warn=False) or {}
    try:
        expected_p = set(roster_persona_slugs(name_map).values())
    except ValueError as exc:
        result["persona_gate"] = {"ok": False, "error": str(exc)}
        result["failed_stage"] = "persona-set-gate"
        return finalize()
    pdir = output_root / "content" / "chat" / "personas"
    produced_p = {p.stem for p in pdir.glob("*.md")} if pdir.exists() else set()
    result["persona_gate"] = {
        "ok": expected_p == produced_p,
        "missing": sorted(expected_p - produced_p),
        "extra": sorted(produced_p - expected_p),
    }
    if not result["persona_gate"]["ok"]:
        result["failed_stage"] = "persona-set-gate"
        return finalize()
    for w in range(1, 19):
        if not stage(
            "build_chat_context", ["--week", str(w), "--season", "2025", "--no-ai"]
        ):
            return finalize()
    if not stage("build_chat_context", ["--preseason", "--season", "2025", "--no-ai"]):
        return finalize()
    result["completed"] = True
    return finalize()


# DAG surfaces (private + derived) PLUS the code surface (scripts/): a byte-change
# to an already-dirty tracked .py is invisible to `git status --porcelain` (the
# label stays " M"), so content-hash it too. __pycache__/.pyc are excluded.
_SNAPSHOT_SUBS = (
    "chat",
    "content/chat",
    "content/weeks",
    "content/preseason-2025",
    "scripts",
)


def _excluded(p):
    return "__pycache__" in p.parts or p.suffix == ".pyc"


_REPARSE_ATTR = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _entry_kind(p):
    """NON-FOLLOWING object kind: 'file'|'dir'|'symlink'|'junction'|'other'.
    'junction' = any non-symlink reparse object (Windows junction etc.)."""
    st = os.lstat(p)
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    if getattr(st, "st_file_attributes", 0) & _REPARSE_ATTR:
        return "junction"
    if stat.S_ISDIR(st.st_mode):
        return "dir"
    if stat.S_ISREG(st.st_mode):
        return "file"
    return "other"


def _link_target(p):
    try:
        return os.readlink(p)
    except OSError:
        return "<unreadable>"


def _iter_nofollow(d):
    """Depth-first sorted (path, kind) under d; ONLY regular dirs are entered --
    symlinks/junctions/reparse objects are yielded but never descended (their
    children belong to the linked tree, not this root)."""
    for p in sorted(Path(d).iterdir()):
        k = _entry_kind(p)
        yield p, k
        if k == "dir":
            yield from _iter_nofollow(p)


def _fs_snapshot(root):
    """NONMUTATION binding over the DAG + code surfaces, NON-FOLLOWING: regular
    dirs 'dir', regular files by content hash, symlinks/junctions by kind+raw
    target (never followed, never descended). Catches a file<->dir swap, a
    byte-change (even to an already-dirty tracked .py), and a same-content
    file->link or dir->junction substitution. Excludes __pycache__/.pyc.
    Schema is DISTINCT from _root_entries (kind-only) -- keep them separate."""
    root = Path(root)
    snap = {}
    for sub in _SNAPSHOT_SUBS:
        d = root / sub
        if not os.path.lexists(d):
            continue
        k = _entry_kind(d)
        if k != "dir":
            # A subtree root that is itself a link/non-dir is a deviation worth
            # binding verbatim -- never descend it.
            rel = d.relative_to(root).as_posix()
            snap[rel] = f"{k}->{_link_target(d)}" if k in ("symlink", "junction") else k
            continue
        for p, kind in _iter_nofollow(d):
            if _excluded(p):
                continue
            rel = p.relative_to(root).as_posix()
            if kind == "dir":
                snap[rel] = "dir"
            elif kind == "file":
                snap[rel] = _sha(p.read_bytes())
            else:
                snap[rel] = f"{kind}->{_link_target(p)}"
    return snap


def _root_entries(root):
    """{rel POSIX: kind} for the WHOLE root, NON-FOLLOWING -- kind ONLY, in
    exactly the expected_generated_paths vocabulary ('file'|'dir') for regular
    entries. Symlink/junction/other are DISTINCT kinds, so a link-shaped entry
    can never satisfy an expected inventory slot (expected sets contain only
    'file'/'dir') and is never descended. Excl. __pycache__/.pyc. Catches a
    root-level or unexpected-subtree/dir extra AND a link substitution."""
    entries = {}
    for p, kind in _iter_nofollow(Path(root)):
        if _excluded(p):
            continue
        entries[p.relative_to(Path(root)).as_posix()] = kind
    return entries


def _with_dirs(file_paths):
    """Expand file paths to {path: 'file'} plus every implied ancestor {dir: 'dir'},
    so an inventory compare over the WHOLE root catches an empty extra dir too."""
    entries = {}
    for fp in file_paths:
        entries[fp] = "file"
        parts = fp.split("/")
        for i in range(1, len(parts)):
            entries["/".join(parts[:i])] = "dir"
    return entries


def expected_generated_paths(candidate_root):
    """The COMPLETE set of generated logical (repo-relative POSIX) paths a full
    rebuild must produce -- catches a MISSING or an EXTRA artifact. Months come
    from the CANDIDATE's freshly re-parsed corpus (so the check works even when
    SOURCE carries no/wrong canonical parsed_messages, e.g. the isolation mirror);
    the roster comes from the SOURCE name-map (NAME_MAP_PATH)."""
    cand = Path(candidate_root)
    parsed = load_json(cand / "chat" / "parsed_messages.json", warn=False)
    msgs = (
        parsed if isinstance(parsed, list) else (parsed or {}).get("messages", parsed)
    )
    months = sorted(
        {month_key_strict(m.get("timestamp_utc", "")) for m in (msgs or [])}
    )
    name_map = load_json(NAME_MAP_PATH, warn=False) or {}
    slugs = set(roster_persona_slugs(name_map).values())
    paths = {"chat/parsed_messages.json", "chat/identity_chain.json"}
    for name in DERIVED_ANALYTICS:
        paths.add(f"content/chat/{name}")
    for mo in months:
        paths.add(f"content/chat/.map_cache/{mo}_raw.json")
        paths.add(f"content/chat/.map_cache/{mo}.json")
    for s in slugs:
        paths.add(f"content/chat/personas/{s}.md")
    for w in WEEKS:
        paths.add(f"content/weeks/week{w}_chat_context.json")
    paths.add("content/preseason-2025/preseason_chat_context.json")
    # Expand to files + implied dirs so the WHOLE-root inventory compare catches
    # an unexpected file/dir/type anywhere (not just a missing expected file).
    return _with_dirs(paths)


def _worktree_value(p):
    """Content-sensitive NON-FOLLOWING value for one worktree entry: regular
    files by hash, links by kind+raw target, anything else by kind."""
    if not os.path.lexists(p):
        return "missing"
    k = _entry_kind(p)
    if k == "file":
        return _sha(Path(p).read_bytes())
    if k in ("symlink", "junction"):
        return f"{k}->{_link_target(p)}"
    return k


def _git_state(root):
    def g(*a):
        return subprocess.run(
            ["git", *a], cwd=root, capture_output=True, text=True
        ).stdout

    # Content-sensitive on FOUR axes: HEAD commit; the exact staged index (blob
    # shas via ls-files --stage -- a staged A->B keeps the SAME porcelain label
    # but changes the blob sha); exact WORKTREE types+bytes over ALL tracked
    # paths (an already-" M" file changing AGAIN keeps label AND index stable --
    # only worktree bytes catch it); and exact types+bytes under every
    # porcelain-untracked path (a "??" file's bytes can change while its status
    # path stays identical). Porcelain itself is kept only as a cheap set-level
    # widener, never as the content check.
    root_p = Path(root)
    tracked = {}
    for rel in g("ls-files", "-z").split("\0"):
        if rel:
            tracked[rel] = _worktree_value(root_p / rel)
    untracked = {}
    for entry in g("status", "--porcelain", "-z").split("\0"):
        if not entry.startswith("?? "):
            continue
        rel = entry[3:].rstrip("/")
        p = root_p / rel
        if os.path.lexists(p) and _entry_kind(p) == "dir":
            for sub, kind in _iter_nofollow(p):
                if _excluded(sub):
                    continue
                sub_rel = f"{rel}/{sub.relative_to(p).as_posix()}"
                untracked[sub_rel] = "dir" if kind == "dir" else _worktree_value(sub)
        else:
            untracked[rel] = _worktree_value(p)
    return {
        "head": g("rev-parse", "HEAD").strip(),
        "index": g("ls-files", "--stage"),
        "status": g("status", "--porcelain"),
        "worktree_tracked": tracked,
        "worktree_untracked": untracked,
    }


def cmd_rebuild_check(receipt_path, test_hooks=None):
    """External full-DAG rebuild into a FRESH, disjoint OUTPUT_ROOT candidate; prove
    the repo is byte-untouched across the DAG + code surfaces AND git state; enforce
    the COMPLETE independently-declared generated inventory; emit a receipt envelope
    to a path OUTSIDE the repo. Requires JAILYARD_OUTPUT_ROOT set to a fresh external
    dir and --receipt. ``test_hooks`` is a test-only seam: main() never passes it."""
    if receipt_path is None:
        print("FAIL: --rebuild-check requires --receipt <path>.")
        return 1
    try:
        src, out = _resolve_disjoint(OUTPUT_ROOT)
    except ValueError as exc:
        print(f"FAIL: unsafe OUTPUT_ROOT for --rebuild-check -- {exc}")
        return 1
    # The receipt must resolve OUTSIDE SOURCE_ROOT, else --receipt <inside-repo>
    # would mutate the repo AFTER the "untouched" proof and still return 0.
    rcpt = Path(receipt_path).resolve()
    if rcpt == src or src in rcpt.parents:
        print(
            f"FAIL: --receipt {rcpt} resolves inside SOURCE_ROOT {src}; use an external path."
        )
        return 1
    # Freshness: OUTPUT_ROOT must be nonexistent or TRULY entry-empty (iterdir --
    # any file/dir/type at the root, not just the five snapshot subtrees).
    if out.exists() and any(out.iterdir()):
        print(f"FAIL: OUTPUT_ROOT {out} is not fresh (contains entries).")
        return 1
    before_fs, before_git = _fs_snapshot(src), _git_state(src)
    result = run_rebuild(out, test_hooks=test_hooks)
    if not result["completed"]:
        print(
            f"FAIL: rebuild did not complete (failed_stage={result['failed_stage']})."
        )
        if result.get("stderr_tail"):
            print(result["stderr_tail"])
        return 1
    # Complete inventory over the WHOLE candidate root ({rel: type}) -- no missing,
    # no extra, no wrong type -- enforced INSIDE the driver, not only in a test.
    produced, expected = result["produced_paths"], expected_generated_paths(out)
    if produced != expected:
        missing = sorted(set(expected) - set(produced))
        extra = sorted(set(produced) - set(expected))
        print(
            f"FAIL: candidate inventory mismatch missing={missing[:8]} extra={extra[:8]}."
        )
        return 1
    errors = []
    receipt = make_receipt(errors)  # read-only compute; OUTPUT_ROOT == out (frozen)
    if errors:
        print("FAIL: cannot emit receipt -- candidate incomplete:")
        for e in errors:
            print(f"  - {e}")
        return 1
    # NONMUTATION proof BEFORE publishing the receipt: on any failure NO new
    # receipt is published and any preexisting one stays byte-identical.
    after_fs, after_git = _fs_snapshot(src), _git_state(src)
    if before_fs != after_fs or before_git != after_git:
        changed = sorted(
            k
            for k in set(before_fs) | set(after_fs)
            if before_fs.get(k) != after_fs.get(k)
        )
        print(
            f"FAIL: rebuild MUTATED the repo (surfaces={changed[:10]} "
            f"git_changed={before_git != after_git}); no receipt published."
        )
        return 1
    # Publish atomically ONLY after the proof passes (unique temp -> os.replace),
    # so a crash/failure never leaves a usable partial OR complete temp receipt:
    # a publication failure returns nonzero, keeps any preexisting target
    # byte-identical, and the finally-unlink removes the temp.
    rcpt.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=rcpt.name + ".", suffix=".tmp", dir=rcpt.parent
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, rcpt)
    except OSError as e:
        print(f"FAIL: receipt publication failed ({e}); no receipt published.")
        return 1
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    print(f"OK: rebuild complete, repo byte-untouched (DAG+code); receipt -> {rcpt}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Chat pipeline provenance (portable).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="(default) full verify")
    mode.add_argument(
        "--verify-public",
        action="store_true",
        help="verify the PUBLIC projection (private chat/* may be absent)",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="receipt-bound write (requires --receipt)",
    )
    mode.add_argument(
        "--rebuild-check",
        action="store_true",
        help="external full-DAG rebuild + emit receipt (requires "
        "JAILYARD_OUTPUT_ROOT set to a fresh external dir, and --receipt)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=CONTENT_CHAT_OUT_DIR / "provenance.json",
        help="Manifest path (default: content/chat/provenance.json).",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Receipt path (required for --write/--rebuild-check).",
    )
    args = parser.parse_args(argv)
    if args.write:
        return cmd_write(args.manifest, args.receipt)
    if args.rebuild_check:
        return cmd_rebuild_check(args.receipt)
    if args.verify_public:
        return cmd_verify(args.manifest, public=True)
    return cmd_verify(args.manifest, public=False)  # default


if __name__ == "__main__":
    raise SystemExit(main())
