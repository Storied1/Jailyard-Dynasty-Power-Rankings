"""Capture-envelope core for the P-only 2026 prospective safeguard (Tranche A).

Contract: docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md
  S1  capture envelope   {root}/{source_id}/{captured_at_compact}.json
  S14 capture table      content/governance/capture_table_2026.json
  A1 invariants: I1-I6, I37-I41 (privacy boundary enforced before any
  private write). Later tasks extend this module: policy freeze (A1b),
  producers (A2), accounting (A3).

The store is append-only (I3): an existing envelope path is never
overwritten, and nothing here deletes. Production callers never pass
``now`` / ``*_root`` overrides — those parameters exist for test isolation
only (the CLI constructs none of them).
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import REPO_ROOT, admissible, rel_to_root  # noqa: E402

CAPTURE_TABLE_PATH = REPO_ROOT / "content" / "governance" / "capture_table_2026.json"
PUBLIC_CAPTURE_ROOT = REPO_ROOT / "data" / "captures" / "2026" / "public"
RECEIPTS_ROOT = REPO_ROOT / "data" / "captures" / "2026" / "_receipts"
PRIVATE_CAPTURE_ROOT = REPO_ROOT / "private_captures" / "2026"
PRIVATE_BUNDLE_ROOT = REPO_ROOT / "private_bundles" / "2026"

ACCESS_SCOPES = ("public", "league_private")
PRIVACY_VALUES = ("public", "private")

# scope <-> privacy is a bijection: league-private data may never be written
# to a public root, and public data has no business under private_captures/.
SCOPE_TO_PRIVACY = {"public": "public", "league_private": "private"}

_SOURCE_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")

ENVELOPE_FIELDS = (
    "source_id",
    "request",
    "season",
    "league_id",
    "locator",
    "captured_at",
    "known_at_basis",
    "access_scope",
    "privacy",
    "payload_sha256",
    "envelope_sha256",
    "payload",
)


class CaptureError(ValueError):
    """Fail-closed refusal anywhere in the capture layer."""


def canonical_bytes(obj) -> bytes:
    """Canonical in-memory JSON serialization used for every capture hash.

    Same parameter set S13 fixes for ``canonical_json_v1`` (A5 wraps this
    with strict loading + version identity): sort_keys, ensure_ascii=False,
    indent=2, allow_nan=False, exactly one trailing LF, explicit UTF-8.
    """
    text = json.dumps(
        obj, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False
    )
    return (text + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_exact_instant(ts) -> datetime:
    """Exact tz-aware instant -> aware UTC datetime; anything else refuses.

    Delegates admissibility to ``shared.admissible`` (the project's one
    fail-closed temporal admitter: rejects missing / malformed / naive /
    date-only / month-only) with no cutoff, then parses.
    """
    if not admissible(ts, None):
        raise CaptureError(f"captured_at must be an exact tz-aware instant, got {ts!r}")
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _utc_compact(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _validate_source_id(source_id) -> str:
    if not isinstance(source_id, str) or not _SOURCE_ID_RE.fullmatch(source_id):
        raise CaptureError(
            f"source_id must match {_SOURCE_ID_RE.pattern}, got {source_id!r}"
        )
    return source_id


def _contained_write_target(root: Path, source_id: str, filename: str) -> Path:
    """I39/I40: the resolved write path must stay inside the resolved root.

    ``resolve()`` follows symlinks, junctions and other reparse points in
    every existing component, so a link that escapes the root lands outside
    ``root.resolve()`` and is rejected rather than followed.
    """
    root_resolved = root.resolve()
    target_resolved = (root / source_id / filename).resolve()
    if not target_resolved.is_relative_to(root_resolved):
        raise CaptureError(
            f"write path {target_resolved} escapes capture root {root_resolved}"
        )
    return target_resolved


def capture(
    source_id,
    payload,
    *,
    request,
    season,
    league_id,
    captured_at,
    known_at_basis,
    access_scope,
    privacy,
    empty_valid=False,
    public_root=None,
    private_root=None,
    now=None,
) -> Path:
    """Validate, hash and append one S1 envelope; return its path.

    Validates its own arguments (I2) because manual ingestion never passes
    through ``main()``. Refuses: a failed/empty/non-object payload (I1),
    any inexact timestamp, a future-dated capture (I4), an existing target
    path (I3), and any write that would resolve outside its root (I39/I40).
    """
    source_id = _validate_source_id(source_id)

    if not isinstance(request, dict) or not str(request.get("endpoint_or_dataset", "")):
        raise CaptureError(
            "request must be a dict carrying the exact source request identity "
            f"(endpoint_or_dataset, params), got {request!r}"
        )
    if not isinstance(season, int):
        raise CaptureError(f"season must be an int, got {season!r}")
    if not isinstance(league_id, str) or not league_id:
        raise CaptureError(f"league_id must be a nonempty string, got {league_id!r}")
    if not isinstance(known_at_basis, str) or not known_at_basis.strip():
        raise CaptureError("known_at_basis must be a nonempty string")
    if access_scope not in ACCESS_SCOPES:
        raise CaptureError(
            f"access_scope must be one of {ACCESS_SCOPES}, got {access_scope!r}"
        )
    if privacy not in PRIVACY_VALUES:
        raise CaptureError(f"privacy must be one of {PRIVACY_VALUES}, got {privacy!r}")
    if SCOPE_TO_PRIVACY[access_scope] != privacy:
        raise CaptureError(
            f"access_scope {access_scope!r} requires privacy "
            f"{SCOPE_TO_PRIVACY[access_scope]!r}, got {privacy!r}"
        )

    captured_dt = parse_exact_instant(captured_at)
    trusted_now = now if now is not None else datetime.now(timezone.utc)
    if captured_dt > trusted_now:
        raise CaptureError(
            f"future-dated capture refused: captured_at {captured_dt.isoformat()} "
            f"> now {trusted_now.isoformat()}"
        )

    # I1 — a failed fetch is never an envelope. fetch_sleeper.fetch_json
    # returns None on exhausted retries; producers wrap list responses.
    if payload is None:
        raise CaptureError(
            "payload is None (failed fetch) — refusing to write an envelope"
        )
    if not isinstance(payload, dict):
        raise CaptureError(
            f"payload must be a JSON object, got {type(payload).__name__} "
            "(producers wrap list responses)"
        )
    if not payload and not empty_valid:
        raise CaptureError(
            "empty payload refused: empty_valid is false for this component"
        )

    if privacy == "private":
        root = Path(private_root) if private_root is not None else PRIVATE_CAPTURE_ROOT
    else:
        root = Path(public_root) if public_root is not None else PUBLIC_CAPTURE_ROOT

    filename = f"{_utc_compact(captured_dt)}.json"
    target = _contained_write_target(root, source_id, filename)

    if target.exists():
        raise CaptureError(f"append-only store: envelope already exists at {target}")

    envelope = {
        "source_id": source_id,
        "request": request,
        "season": season,
        "league_id": league_id,
        "locator": rel_to_root(target),
        "captured_at": captured_dt.isoformat().replace("+00:00", "Z"),
        "known_at_basis": known_at_basis,
        "access_scope": access_scope,
        "privacy": privacy,
        "payload_sha256": sha256_hex(canonical_bytes(payload)),
        "payload": payload,
    }
    envelope["envelope_sha256"] = sha256_hex(canonical_bytes(envelope))

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():  # re-check after mkdir: append-only, never overwrite
        raise CaptureError(f"append-only store: envelope already exists at {target}")
    with open(target, "wb") as f:
        f.write(canonical_bytes(envelope))
    return target


def verify_envelope(path) -> tuple[bool, list[str]]:
    """I5 — verification checks payload AND metadata; mismatch is not coverage."""
    errors: list[str] = []
    path = Path(path)
    try:
        env = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, [f"unreadable envelope {path}: {exc}"]
    if not isinstance(env, dict):
        return False, [f"envelope is not an object: {path}"]

    missing = [f for f in ENVELOPE_FIELDS if f not in env]
    if missing:
        errors.append(f"missing envelope fields: {missing}")
        return False, errors

    expected_payload = sha256_hex(canonical_bytes(env["payload"]))
    if env["payload_sha256"] != expected_payload:
        errors.append(
            f"payload_sha256 mismatch: recorded {env['payload_sha256']}, "
            f"recomputed {expected_payload}"
        )

    body = {k: v for k, v in env.items() if k != "envelope_sha256"}
    expected_envelope = sha256_hex(canonical_bytes(body))
    if env["envelope_sha256"] != expected_envelope:
        errors.append(
            f"envelope_sha256 mismatch: recorded {env['envelope_sha256']}, "
            f"recomputed {expected_envelope}"
        )
    return (not errors), errors


def staging_guard(repo_root=REPO_ROOT) -> tuple[bool, list[str]]:
    """I41 — fail on any STAGED private path.

    ``git status`` cannot do this job: an ignored path never appears there,
    but ``git add -f`` still stages it. The index is the authority.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, [f"git diff --cached failed: {result.stderr.strip()}"]
    offending = [
        line
        for line in result.stdout.splitlines()
        if line.startswith(("private_captures/", "private_bundles/"))
    ]
    return (not offending), offending


def load_capture_table(path=CAPTURE_TABLE_PATH) -> dict:
    """Load + shape-check the S14 capture table (deep R4 pin lives in tests)."""
    path = Path(path)
    if not path.exists():
        raise CaptureError(f"capture table missing: {path}")
    table = json.loads(path.read_text(encoding="utf-8"))
    if set(table) != {"season", "groups"}:
        raise CaptureError(
            f"capture table must have exactly season+groups, got {sorted(table)}"
        )
    if not isinstance(table["groups"], list) or not table["groups"]:
        raise CaptureError("capture table groups must be a nonempty list")
    for group in table["groups"]:
        if set(group) != {"group", "components"}:
            raise CaptureError(
                f"group must have exactly group+components, got {sorted(group)}"
            )
        if not isinstance(group["components"], list) or not group["components"]:
            raise CaptureError(f"group {group.get('group')!r} has no components")
    return table


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="capture_2026.py",
        description=(
            "P-only 2026 capture envelopes (S1). Append-only store under "
            "data/captures/2026/public/ and private_captures/2026/."
        ),
    )
    parser.parse_args(argv)
    # No action flags exist yet at A1; asking for nothing is an error, not a
    # silent success (a main() that does nothing must not exit 0).
    parser.print_usage(sys.stderr)
    print("capture_2026.py: no action requested", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
