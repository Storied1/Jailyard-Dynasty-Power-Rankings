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
    try:
        handle = open(target, "xb")
    except FileExistsError as exc:
        raise CaptureError(f"append-only artifact already exists: {target}") from exc
    with handle as f:
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


# ---------------------------------------------------------------------------
# A2 — the three A7-required producers (sole producer predecessor of A3-A7).
# Optional-lane producers live in capture_optional_2026.py, which this module
# NEVER imports at module level (I59): the baseline path must run with that
# module absent.
# ---------------------------------------------------------------------------

LEAGUE_JSON_PATH = REPO_ROOT / "data" / "2026" / "league.json"


def _default_fetch():
    """The audited constant-host Sleeper fetcher (I1 cites its None contract)."""
    from fetch_sleeper import fetch_json

    return fetch_json


def read_expected_league_id(league_json_path=None) -> str:
    path = Path(league_json_path) if league_json_path is not None else LEAGUE_JSON_PATH
    if not path.exists():
        raise CaptureError(f"league id source missing: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    league_id = doc.get("league_id")
    if not isinstance(league_id, str) or not league_id.isdigit():
        raise CaptureError(
            f"league_id in {path} must be a digit string, got {league_id!r}"
        )
    return league_id


def produce_sleeper_league(
    *, fetch=None, league_json_path=None, public_root=None, now=None
) -> Path:
    """Capture /league/{id}; I9: fetched league_id must equal the on-disk id."""
    fetch = fetch if fetch is not None else _default_fetch()
    expected = read_expected_league_id(league_json_path)
    endpoint = f"/league/{expected}"
    payload = fetch(endpoint)
    if payload is None:
        raise CaptureError(
            f"fetch failed for {endpoint}; refusing to write an envelope"
        )
    if not isinstance(payload, dict):
        raise CaptureError(
            f"league payload must be an object, got {type(payload).__name__}"
        )
    if payload.get("league_id") != expected:
        raise CaptureError(
            f"league id verification failed (I9): disk {expected!r} != "
            f"fetched {payload.get('league_id')!r}"
        )
    captured_dt = now if now is not None else datetime.now(timezone.utc)
    return capture(
        "sleeper_league",
        payload,
        request={"endpoint_or_dataset": endpoint, "params": {}},
        season=2026,
        league_id=expected,
        captured_at=captured_dt.isoformat().replace("+00:00", "Z"),
        known_at_basis="Sleeper league object read live at captured_at",
        access_scope="public",
        privacy="public",
        public_root=public_root,
        now=captured_dt,
    )


def produce_sleeper_rosters(
    *, fetch=None, league_json_path=None, public_root=None, now=None
) -> Path:
    """Capture /league/{id}/rosters wrapped as an object payload."""
    fetch = fetch if fetch is not None else _default_fetch()
    expected = read_expected_league_id(league_json_path)
    endpoint = f"/league/{expected}/rosters"
    rosters = fetch(endpoint)
    if rosters is None:
        raise CaptureError(
            f"fetch failed for {endpoint}; refusing to write an envelope"
        )
    if not isinstance(rosters, list) or not rosters:
        raise CaptureError(f"rosters payload must be a nonempty list, got {rosters!r}")
    for entry in rosters:
        if (
            not isinstance(entry, dict)
            or "roster_id" not in entry
            or "owner_id" not in entry
        ):
            raise CaptureError(f"roster entry missing roster_id/owner_id: {entry!r}")
        if entry.get("league_id") != expected:
            raise CaptureError(
                f"roster {entry.get('roster_id')} bound to league "
                f"{entry.get('league_id')!r}, expected {expected!r}"
            )
    payload = {"rosters": rosters, "count": len(rosters)}
    captured_dt = now if now is not None else datetime.now(timezone.utc)
    return capture(
        "sleeper_rosters",
        payload,
        request={"endpoint_or_dataset": endpoint, "params": {}},
        season=2026,
        league_id=expected,
        captured_at=captured_dt.isoformat().replace("+00:00", "Z"),
        known_at_basis="Sleeper rosters read live at captured_at",
        access_scope="public",
        privacy="public",
        public_root=public_root,
        now=captured_dt,
    )


SCHEDULE_ROW_FIELDS = (
    "game_id",
    "season",
    "game_type",
    "week",
    "gameday",
    "gametime",
    "away_team",
    "home_team",
)


def _load_schedule_rows(season: int):
    """Production loader: nflreadpy schedules (lazy import; heavy dep)."""
    import nflreadpy as nfl

    frame = nfl.load_schedules(seasons=[season])
    return frame.to_dicts()


def produce_nfl_schedules(
    *, load_rows=None, league_json_path=None, public_root=None, now=None
) -> Path:
    """Capture the nflverse schedules dataset for 2026 (cutoff source, I17)."""
    load_rows = load_rows if load_rows is not None else _load_schedule_rows
    rows = load_rows(2026)
    if rows is None:
        raise CaptureError("schedules load failed; refusing to write an envelope")
    if not isinstance(rows, list) or not rows:
        raise CaptureError("schedules payload must be a nonempty list of games")
    for row in rows:
        missing = [f for f in SCHEDULE_ROW_FIELDS if f not in row]
        if missing:
            raise CaptureError(
                f"schedule row missing {missing}: {row.get('game_id')!r}"
            )
        if row["season"] != 2026:
            raise CaptureError(
                f"schedule row {row['game_id']!r} has season {row['season']!r}, "
                "expected 2026"
            )
    payload = {"dataset": "schedules", "season": 2026, "games": rows}
    expected = read_expected_league_id(league_json_path)
    captured_dt = now if now is not None else datetime.now(timezone.utc)
    return capture(
        "nfl_schedules",
        payload,
        request={
            "endpoint_or_dataset": "nflreadpy:schedules",
            "params": {"season": 2026},
        },
        season=2026,
        league_id=expected,
        captured_at=captured_dt.isoformat().replace("+00:00", "Z"),
        known_at_basis="nflverse schedules dataset read at captured_at",
        access_scope="public",
        privacy="public",
        public_root=public_root,
        now=captured_dt,
    )


# ---------------------------------------------------------------------------
# S3 policy family — versioned, immutable once frozen (A1b: I47, I57)
# ---------------------------------------------------------------------------

GOVERNANCE_DIR = REPO_ROOT / "content" / "governance"

A7_REQUIRED_SOURCES = (
    "nfl_schedules",
    "sleeper_league",
    "sleeper_rosters",
    "standings_2025",
)
QUALIFIED_POLICY_SOURCES = (
    "standings_2025",
    "league_history_2022",
    "league_history_2023",
    "league_history_2024",
    "player_crosswalk",
)
POLICY_SCOPES = ("baseline", "model_arms")
SCOPE_ARMS = {
    "baseline": {"record_points"},
    "model_arms": {"minimal_legal", "full_rich"},
}
EDITIONS = ("2026-preseason", "2026-wk01-preview")
_POLICY_VERSION_RE = re.compile(r"^v\d+$")

POLICY_ROW_FIELDS = (
    "source_id",
    "kind",
    "locator_or_endpoint",
    "arms",
    "editions",
    "required_for",
    "availability_window",
    "freshness",
    "empty_valid",
    "known_at_basis",
    "policy_version",
    "scope",
)


def load_json_bytes_strict(raw: bytes):
    """Duplicate-key- and non-finite-rejecting JSON load over RAW BYTES.

    S13 semantics, hosted here because the freeze (A1b) must already refuse a
    candidate whose duplicate keys the stdlib would silently last-wins. A5's
    ``load_json_strict`` in bundle_2026.py is the versioned public wrapper.
    """

    def no_dupes(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise CaptureError(f"duplicate JSON key {key!r}")
            obj[key] = value
        return obj

    def refuse_constant(name):
        raise CaptureError(f"non-finite JSON constant {name!r} refused")

    if not isinstance(raw, bytes):
        raise CaptureError(f"strict load takes raw bytes, got {type(raw).__name__}")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=no_dupes,
            parse_constant=refuse_constant,
        )
    except CaptureError:
        raise
    except (UnicodeDecodeError, ValueError) as exc:
        raise CaptureError(f"strict JSON load failed: {exc}") from exc


def policy_path(version: str, governance_dir=None) -> Path:
    root = Path(governance_dir) if governance_dir is not None else GOVERNANCE_DIR
    return root / f"source_policy_2026.{version}.json"


def compute_policy_sha256(doc: dict) -> str:
    """Hash over the canonical document with the header hash field excluded."""
    body = {k: v for k, v in doc.items() if k != "policy_sha256"}
    return sha256_hex(canonical_bytes(body))


def _validate_policy_row(row, scope, version, components):
    if not isinstance(row, dict):
        raise CaptureError(f"policy row must be an object, got {type(row).__name__}")
    missing = [f for f in POLICY_ROW_FIELDS if f not in row]
    if missing:
        raise CaptureError(f"policy row {row.get('source_id')!r} missing {missing}")
    source_id = row["source_id"]
    if source_id in components:
        expected_kind = "capture"
    elif source_id in QUALIFIED_POLICY_SOURCES:
        expected_kind = "qualified_artifact"
    else:
        raise CaptureError(f"undeclared policy source {source_id!r}")
    if row["kind"] != expected_kind:
        raise CaptureError(
            f"{source_id}: kind must be {expected_kind!r}, got {row['kind']!r}"
        )
    if (
        not isinstance(row["locator_or_endpoint"], str)
        or not row["locator_or_endpoint"]
    ):
        raise CaptureError(f"{source_id}: locator_or_endpoint must be nonempty")
    allowed_arms = SCOPE_ARMS[scope]
    for field in ("arms", "required_for"):
        values = row[field]
        if not isinstance(values, list) or not set(values) <= allowed_arms:
            raise CaptureError(
                f"{source_id}: {field} must be a subset of {sorted(allowed_arms)} "
                f"for scope {scope!r}, got {values!r}"
            )
    if (
        not isinstance(row["editions"], list)
        or not row["editions"]
        or not set(row["editions"]) <= set(EDITIONS)
    ):
        raise CaptureError(
            f"{source_id}: editions must be a nonempty subset of {EDITIONS}"
        )
    window = row["availability_window"]
    if (
        not isinstance(window, dict)
        or set(window) != {"opens_at_rule", "closes_at_rule"}
        or not all(isinstance(window[k], str) and window[k] for k in window)
    ):
        raise CaptureError(f"{source_id}: availability_window needs opens/closes rules")
    if row["freshness"] is not None and (
        not isinstance(row["freshness"], int) or row["freshness"] <= 0
    ):
        raise CaptureError(f"{source_id}: freshness must be null or positive seconds")
    if not isinstance(row["empty_valid"], bool):
        raise CaptureError(f"{source_id}: empty_valid must be a bool")
    if not isinstance(row["known_at_basis"], str) or not row["known_at_basis"].strip():
        raise CaptureError(f"{source_id}: known_at_basis must be nonempty")
    if source_id == "chat_export":
        refresh = row.get("chat_refresh")
        if (
            not isinstance(refresh, dict)
            or set(refresh) != {"initial", "subsequent"}
            or not all(isinstance(refresh[k], str) and refresh[k] for k in refresh)
        ):
            raise CaptureError("chat_export row needs chat_refresh initial+subsequent")
    elif "chat_refresh" in row:
        raise CaptureError(f"{source_id}: chat_refresh belongs to the chat row only")
    if row["policy_version"] != version or row["scope"] != scope:
        raise CaptureError(f"{source_id}: freeze identity mismatch with header")


def validate_policy_document(doc, *, capture_table_path=None) -> None:
    """S3 schema + row-set validation; fail-closed (I57 for baseline scope)."""
    if not isinstance(doc, dict):
        raise CaptureError("policy document must be an object")
    for field in ("policy_version", "scope", "frozen_at", "policy_sha256", "rows"):
        if field not in doc:
            raise CaptureError(f"policy document missing {field}")
    version = doc["policy_version"]
    scope = doc["scope"]
    if not isinstance(version, str) or not _POLICY_VERSION_RE.fullmatch(version):
        raise CaptureError(f"policy_version must match v<N>, got {version!r}")
    if scope not in POLICY_SCOPES:
        raise CaptureError(f"scope must be one of {POLICY_SCOPES}, got {scope!r}")
    if not admissible(doc["frozen_at"], None):
        raise CaptureError(
            f"frozen_at must be an exact instant, got {doc['frozen_at']!r}"
        )

    table_path = (
        capture_table_path if capture_table_path is not None else CAPTURE_TABLE_PATH
    )
    components = {
        c
        for group in load_capture_table(table_path)["groups"]
        for c in group["components"]
    }
    expected_sources = components | set(QUALIFIED_POLICY_SOURCES)

    rows = doc["rows"]
    if not isinstance(rows, list):
        raise CaptureError("policy rows must be a list")
    seen = [row.get("source_id") if isinstance(row, dict) else None for row in rows]
    if len(seen) != len(set(seen)):
        raise CaptureError("duplicate source_id rows in policy")
    if set(seen) != expected_sources:
        raise CaptureError(
            f"policy must contain exactly the declared rows; missing "
            f"{sorted(expected_sources - set(seen))}, extra "
            f"{sorted(set(seen) - expected_sources)}"
        )
    for row in rows:
        _validate_policy_row(row, scope, version, components)

    if scope == "baseline":
        nonempty = {
            row["source_id"] for row in rows if row["arms"] or row["required_for"]
        }
        if nonempty != set(A7_REQUIRED_SOURCES):
            raise CaptureError(
                "baseline scope: arms/required_for must be nonempty exactly on "
                f"{sorted(A7_REQUIRED_SOURCES)}, got {sorted(nonempty)}"
            )
        for row in rows:
            if row["source_id"] in A7_REQUIRED_SOURCES:
                if row["required_for"] != ["record_points"]:
                    raise CaptureError(
                        f"{row['source_id']}: required_for must be ['record_points']"
                    )


def freeze_policy(
    candidate_path,
    version,
    *,
    expected_candidate_sha256=None,
    governance_dir=None,
    capture_table_path=None,
    now=None,
) -> Path:
    """Freeze one policy version: write exactly one new file, exactly once (I47).

    The candidate carries policy_version, scope and rows; freeze stamps
    frozen_at + policy_sha256 and writes the canonical bytes. An already-
    frozen version refuses; no other version's file is ever touched.

    The freeze boundary is also the APPROVAL boundary: the caller must pass
    the sha256 of the canonical unstamped candidate that was approved, and a
    missing or mismatched value fails closed BEFORE any file is created — a
    merely schema-valid candidate is not an approved candidate.
    """
    if not isinstance(version, str) or not _POLICY_VERSION_RE.fullmatch(version):
        raise CaptureError(f"version must match v<N>, got {version!r}")
    candidate_path = Path(candidate_path)
    if not candidate_path.exists():
        raise CaptureError(f"candidate policy missing: {candidate_path}")
    candidate = load_json_bytes_strict(candidate_path.read_bytes())
    if not isinstance(candidate, dict):
        raise CaptureError("candidate policy must be an object")
    for stamped in ("frozen_at", "policy_sha256"):
        if stamped in candidate:
            raise CaptureError(
                f"candidate already carries {stamped}; a candidate is not frozen"
            )
    if candidate.get("policy_version") != version:
        raise CaptureError(
            f"candidate policy_version {candidate.get('policy_version')!r} "
            f"!= freeze version {version!r}"
        )

    if not expected_candidate_sha256:
        raise CaptureError(
            "freeze requires expected_candidate_sha256 — the hash of the "
            "approved canonical candidate; refusing to freeze unbound (fail closed)"
        )
    actual_candidate_sha256 = sha256_hex(canonical_bytes(candidate))
    if actual_candidate_sha256 != expected_candidate_sha256:
        raise CaptureError(
            f"candidate is not the approved one: approved "
            f"{expected_candidate_sha256}, actual {actual_candidate_sha256}"
        )

    target = policy_path(version, governance_dir)
    if target.exists():
        raise CaptureError(f"policy {version} already frozen at {target}; immutable")

    frozen_dt = now if now is not None else datetime.now(timezone.utc)
    doc = {
        "policy_version": version,
        "scope": candidate.get("scope"),
        "frozen_at": frozen_dt.isoformat().replace("+00:00", "Z"),
        "rows": candidate.get("rows"),
    }
    doc["policy_sha256"] = compute_policy_sha256(doc)
    validate_policy_document(doc, capture_table_path=capture_table_path)

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise CaptureError(f"policy {version} already frozen at {target}; immutable")
    try:
        handle = open(target, "xb")
    except FileExistsError as exc:
        raise CaptureError(f"append-only artifact already exists: {target}") from exc
    with handle as f:
        f.write(canonical_bytes(doc))
    return target


def load_policy(path, *, capture_table_path=None) -> dict:
    """Strict-load a frozen policy, re-verify its hash and schema (I48 reload)."""
    path = Path(path)
    if not path.exists():
        raise CaptureError(f"policy missing: {path}")
    doc = load_json_bytes_strict(path.read_bytes())
    validate_policy_document(doc, capture_table_path=capture_table_path)
    expected = compute_policy_sha256(doc)
    if doc["policy_sha256"] != expected:
        raise CaptureError(
            f"policy hash mismatch at {path}: recorded {doc['policy_sha256']}, "
            f"recomputed {expected}"
        )
    return doc


def build_candidate_policy_v1() -> dict:
    """The exact proposed production v1 content (task-12 deliverable).

    Emitting the candidate is not freezing it: v1's contents require Blake's
    approval (contract section 9, item 1b) before any production freeze.
    """
    league_endpoint = "/league/1312884727480352768"
    both = list(EDITIONS)

    def row(source_id, kind, locator, **overrides):
        base = {
            "source_id": source_id,
            "kind": kind,
            "locator_or_endpoint": locator,
            "arms": [],
            "editions": both,
            "required_for": [],
            "availability_window": {
                "opens_at_rule": "immediate",
                "closes_at_rule": "never",
            },
            "freshness": 86400,
            "empty_valid": False,
            "known_at_basis": "Sleeper API object read live at captured_at",
            "policy_version": "v1",
            "scope": "baseline",
        }
        base.update(overrides)
        return base

    rows = [
        row(
            "sleeper_league",
            "capture",
            league_endpoint,
            arms=[],
            required_for=["record_points"],
            freshness=604800,
        ),
        row(
            "sleeper_rosters",
            "capture",
            f"{league_endpoint}/rosters",
            arms=["record_points"],
            required_for=["record_points"],
            freshness=172800,
        ),
        row(
            "nfl_schedules",
            "capture",
            "nflreadpy:schedules?season=2026",
            arms=[],
            required_for=["record_points"],
            freshness=604800,
            known_at_basis="nflverse schedules dataset read at captured_at",
        ),
        row("sleeper_users", "capture", f"{league_endpoint}/users"),
        row(
            "draft_meta",
            "capture",
            f"{league_endpoint}/drafts",
            known_at_basis=(
                "Sleeper draft metadata read live at captured_at "
                "(2026 rookie draft completed 2026-07-10)"
            ),
        ),
        row(
            "draft_picks",
            "capture",
            "/draft/{draft_id}/picks",
            known_at_basis=(
                "Sleeper draft picks read live at captured_at; draft_id resolved "
                "from /league/{league_id}/drafts (2026 draft complete, 72 picks)"
            ),
        ),
        row(
            "sleeper_transactions",
            "capture",
            f"{league_endpoint}/transactions/{{week}}",
        ),
        row(
            "sleeper_matchups",
            "capture",
            f"{league_endpoint}/matchups/{{week}}",
        ),
        row(
            "sleeper_projections",
            "capture",
            "/projections/nfl/2026/{week}?season_type=regular",
            known_at_basis=(
                "Sleeper projections endpoint read at captured_at "
                "(shape unverified until B1 — contract section 9 item 2)"
            ),
        ),
        row(
            "nfl_team_context",
            "capture",
            "nflreadpy:team_stats?season=2026",
            freshness=604800,
            known_at_basis="nflverse team stats dataset read at captured_at",
        ),
        row(
            "nfl_injuries",
            "capture",
            "nflreadpy:injuries?season=2026",
            known_at_basis="nflverse injuries dataset read at captured_at",
        ),
        row(
            "chat_export",
            "capture",
            "manual:whatsapp_export",
            freshness=None,
            known_at_basis=(
                "league-private WhatsApp export ingested manually; message "
                "timestamps carry their own known_at"
            ),
            chat_refresh={
                "initial": "full export ingested before the first B bundle",
                "subsequent": (
                    "re-export before the preview bundle when new messages exist"
                ),
            },
        ),
        row(
            "standings_2025",
            "qualified_artifact",
            "data/2025/season_combined.json",
            arms=["record_points"],
            required_for=["record_points"],
            freshness=None,
            known_at_basis=(
                "2025 season complete; committed artifact pinned to its git "
                "blob at bundle time (I54/I55)"
            ),
        ),
        row(
            "league_history_2022",
            "qualified_artifact",
            "data/2022/season_combined.json",
            freshness=None,
            known_at_basis="2022 season complete; committed artifact, blob-pinned",
        ),
        row(
            "league_history_2023",
            "qualified_artifact",
            "data/2023/season_combined.json",
            freshness=None,
            known_at_basis="2023 season complete; committed artifact, blob-pinned",
        ),
        row(
            "league_history_2024",
            "qualified_artifact",
            "data/2024/season_combined.json",
            freshness=None,
            known_at_basis="2024 season complete; committed artifact, blob-pinned",
        ),
        row(
            "player_crosswalk",
            "qualified_artifact",
            "data/2025/player_arcs/_index.json",
            freshness=None,
            known_at_basis=(
                "cross-season player-id index (committed, blob-pinned); shared "
                "identically by both model arms per S3 — binding happens at B"
            ),
        ),
    ]
    return {"policy_version": "v1", "scope": "baseline", "rows": rows}


# ---------------------------------------------------------------------------
# A3 — tranche-scoped accounting (S2; I10-I13, I15, I16a, I16b, I50b)
# ---------------------------------------------------------------------------

PRODUCTION_V1_POLICY_PATH = GOVERNANCE_DIR / "source_policy_2026.v1.json"

# chat is the one league-private component; its envelopes live under the
# private root, so accounting searches there for it (hashes only — I15).
PRIVATE_SOURCE_IDS = {"chat_export"}

_MECHANISM_BY_PREFIX = (
    ("nflreadpy:", "nflreadpy"),
    ("manual:", "manual"),
    ("/", "sleeper_api"),
)


def _mechanism_for(locator: str) -> str:
    for prefix, mechanism in _MECHANISM_BY_PREFIX:
        if locator.startswith(prefix):
            return mechanism
    return "unknown"


def _cadence_for(freshness) -> str:
    if freshness is None:
        return "on_demand"
    if freshness <= 86400:
        return "daily"
    if freshness <= 604800:
        return "weekly"
    return "periodic"


def _window_open(rule: str, now: datetime) -> bool:
    """Evaluate an opens_at_rule. Unknown rules fail closed (raise)."""
    if rule == "immediate":
        return True
    if rule == "never":
        return False
    if rule.startswith("utc:"):
        instant = rule[len("utc:") :]
        if not admissible(instant, None):
            raise CaptureError(f"window rule carries an inexact instant: {rule!r}")
        return now >= datetime.fromisoformat(instant.replace("Z", "+00:00"))
    if rule in ("preseason_cutoff", "preview_cutoff"):
        # resolvable only once a cutoff receipt exists (A4); before that the
        # conservative reading is "not yet open"
        return False
    raise CaptureError(f"unknown availability-window rule {rule!r}")


def latest_verified_envelope(source_id: str, roots) -> dict | None:
    """Newest verified envelope for a source across the given roots, or None.

    Tampered envelopes are skipped (I5: a mismatch is not coverage) rather
    than trusted or fatal — an older verified envelope may still qualify.
    """
    candidates = []
    for root in roots:
        source_dir = Path(root) / source_id
        if source_dir.is_dir():
            candidates.extend(source_dir.glob("*.json"))
    for path in sorted(candidates, key=lambda p: p.name, reverse=True):
        ok, _ = verify_envelope(path)
        if ok:
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _component_report(row, roots, now, producer_errors) -> dict:
    source_id = row["source_id"]
    report = {
        "source_id": source_id,
        "required_for": list(row["required_for"]),
        "mechanism": _mechanism_for(row["locator_or_endpoint"]),
        "cadence": _cadence_for(row["freshness"]),
        "availability_window": dict(row["availability_window"]),
        "empty_valid": row["empty_valid"],
        "status": None,
        "captured_at": None,
        "payload_sha256": None,
        "envelope_sha256": None,
        "error": None,
        "acquisition_trigger": (
            f"python scripts/capture_2026.py --season 2026 --component {source_id}"
        ),
    }

    envelope = latest_verified_envelope(source_id, roots)
    if envelope is not None:
        captured_dt = datetime.fromisoformat(
            envelope["captured_at"].replace("Z", "+00:00")
        )
        if captured_dt > now:
            # a capture from the accounting clock's FUTURE can never be
            # coverage: its negative age must not read as fresh; fail closed
            report["status"] = "error"
            report["error"] = (
                f"captured_at {envelope['captured_at']} is later than the "
                f"accounting clock {now.isoformat().replace('+00:00', 'Z')} — "
                "chronology violation, not coverage"
            )
            return report
        fresh = (
            row["freshness"] is None
            or (now - captured_dt).total_seconds() <= row["freshness"]
        )
        if fresh:
            report["status"] = "captured"
            report["captured_at"] = envelope["captured_at"]
            report["payload_sha256"] = envelope["payload_sha256"]
            report["envelope_sha256"] = envelope["envelope_sha256"]
            # a producer error this run is still reported alongside coverage
            if source_id in producer_errors:
                report["error"] = str(producer_errors[source_id])
            return report

    if source_id in producer_errors:
        report["status"] = "error"
        report["error"] = str(producer_errors[source_id])
        return report

    report["status"] = (
        "due"
        if _window_open(row["availability_window"]["opens_at_rule"], now)
        else "not_due"
    )
    return report


def required_components_for_tranche(policy: dict, tranche: str) -> set:
    """Capture components whose absence blocks the tranche's gate.

    Tranche A: components with required_for containing record_points (the
    qualified standings_2025 has no producer and is verified at bundle time).
    Tranche B: all twelve components (I36's all-twelve surface).
    """
    capture_rows = [r for r in policy["rows"] if r["kind"] == "capture"]
    if tranche == "A":
        return {
            r["source_id"] for r in capture_rows if "record_points" in r["required_for"]
        }
    if tranche == "B":
        return {r["source_id"] for r in capture_rows}
    raise CaptureError(f"unknown tranche {tranche!r}")


def build_accounting_receipt(
    policy: dict,
    *,
    tranche: str,
    public_root,
    private_root,
    now: datetime,
    producer_errors=None,
    capture_table_path=None,
) -> dict:
    """S2 receipt: eight groups, twelve independent components (I10).

    Derives every status from the store and the frozen policy WITHOUT
    invoking any producer (I59's accounting half). Carries hashes and
    metadata only — no payload, never raw chat (I15).
    """
    producer_errors = producer_errors or {}
    required = required_components_for_tranche(policy, tranche)
    rows_by_id = {r["source_id"]: r for r in policy["rows"] if r["kind"] == "capture"}
    table_path = (
        capture_table_path if capture_table_path is not None else CAPTURE_TABLE_PATH
    )
    table = load_capture_table(table_path)

    groups = []
    unmet = []
    for group_def in table["groups"]:
        components = []
        for source_id in group_def["components"]:
            row = rows_by_id.get(source_id)
            if row is None:
                raise CaptureError(f"component {source_id!r} has no policy row")
            roots = [public_root]
            if source_id in PRIVATE_SOURCE_IDS:
                roots.append(private_root)
            report = _component_report(row, roots, now, producer_errors)
            components.append(report)
            if source_id in required and report["status"] != "captured":
                unmet.append(source_id)
        statuses = {c["status"] for c in components}
        if "error" in statuses:
            group_status = "error"
        elif statuses == {"captured"}:
            group_status = "captured"
        else:
            group_status = "incomplete"
        groups.append(
            {
                "group": group_def["group"],
                "required_for": sorted(
                    {arm for c in components for arm in c["required_for"]}
                ),
                "status": group_status,
                "components": components,
            }
        )

    return {
        "season": 2026,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "tranche": tranche,
        "groups": groups,
        "unmet_required": sorted(unmet),
        "ok": not unmet,
    }


def write_accounting_receipt(receipt: dict, receipts_root=None) -> Path:
    root = Path(receipts_root) if receipts_root is not None else RECEIPTS_ROOT
    compact = _utc_compact(
        datetime.fromisoformat(receipt["generated_at"].replace("Z", "+00:00"))
    )
    target = root / f"accounting_{receipt['tranche']}_{compact}.json"
    if target.exists():
        raise CaptureError(f"append-only receipts: {target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = open(target, "xb")
    except FileExistsError as exc:
        raise CaptureError(f"append-only artifact already exists: {target}") from exc
    with handle as f:
        f.write(canonical_bytes(receipt))
    return target


CORE_PRODUCERS = {
    "sleeper_league": produce_sleeper_league,
    "sleeper_rosters": produce_sleeper_rosters,
    "nfl_schedules": produce_nfl_schedules,
}


def _run_producer(source_id, *, league_json_path, public_root, now):
    """Run one component producer; optional components lazy-import their
    module (I59: the baseline path runs with capture_optional_2026 absent)."""
    if source_id in CORE_PRODUCERS:
        producer = CORE_PRODUCERS[source_id]
        if source_id == "nfl_schedules":
            return producer(
                league_json_path=league_json_path, public_root=public_root, now=now
            )
        return producer(
            league_json_path=league_json_path, public_root=public_root, now=now
        )
    try:
        import capture_optional_2026 as optional
    except ImportError as exc:
        raise CaptureError(
            f"optional producer module absent; cannot capture {source_id}: {exc}"
        ) from exc
    producer = optional.OPTIONAL_PRODUCERS.get(source_id)
    if producer is None:
        raise CaptureError(f"no producer for component {source_id!r}")
    return producer(league_json_path=league_json_path, public_root=public_root, now=now)


def run_tranche(
    tranche: str,
    *,
    policy_path=None,
    public_root=None,
    private_root=None,
    receipts_root=None,
    league_json_path=None,
    now=None,
    run_producers=True,
) -> tuple[Path, int]:
    """The --tranche gate: attempt required producers, account, write, exit.

    The receipt is written even when the gate fails; the CLI exit code is
    nonzero when any component required for the tranche is not captured
    (I16b). Production callers pass no overrides.
    """
    policy = load_policy(
        policy_path if policy_path is not None else PRODUCTION_V1_POLICY_PATH
    )
    # Producers receive the CALLER'S clock argument, not a pre-resolved one:
    # in production that is None, so each producer stamps captured_at AFTER
    # its acquisition completes — a fetch that starts before a cutoff and
    # finishes after it can never be recorded as pre-cutoff. An explicitly
    # injected fixture clock stays deterministic. The resolved instant below
    # is only the accounting/receipt clock.
    producer_clock = now
    public = Path(public_root) if public_root is not None else PUBLIC_CAPTURE_ROOT
    private = Path(private_root) if private_root is not None else PRIVATE_CAPTURE_ROOT

    producer_errors = {}
    if run_producers:
        for source_id in sorted(required_components_for_tranche(policy, tranche)):
            try:
                _run_producer(
                    source_id,
                    league_json_path=league_json_path,
                    public_root=public,
                    now=producer_clock,
                )
            except Exception as exc:  # noqa: BLE001 — receipt MUST still
                # be written (I16b); nflreadpy/polars/OS errors become honest
                # per-component error statuses instead of a crash w/o receipt
                producer_errors[source_id] = f"{type(exc).__name__}: {exc}"

    # The accounting clock resolves only AFTER every producer attempt has
    # completed, so generated_at is never earlier than an admitted
    # captured_at — a receipt must attest a chronologically coherent state.
    now = now if now is not None else datetime.now(timezone.utc)

    receipt = build_accounting_receipt(
        policy,
        tranche=tranche,
        public_root=public,
        private_root=private,
        now=now,
        producer_errors=producer_errors,
    )
    receipt_path = write_accounting_receipt(receipt, receipts_root)
    return receipt_path, (0 if receipt["ok"] else 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="capture_2026.py",
        description=(
            "P-only 2026 capture envelopes (S1). Append-only store under "
            "data/captures/2026/public/ and private_captures/2026/."
        ),
    )
    parser.add_argument(
        "--freeze-policy",
        metavar="CANDIDATE_JSON",
        help="freeze a Blake-approved candidate as an immutable policy version (A1b)",
    )
    parser.add_argument(
        "--version",
        metavar="vN",
        help="policy version to freeze, e.g. v1 (required with --freeze-policy)",
    )
    parser.add_argument(
        "--expected-candidate-sha256",
        metavar="SHA256",
        help=(
            "sha256 of the approved canonical candidate (required with "
            "--freeze-policy; the freeze boundary is the approval boundary)"
        ),
    )
    parser.add_argument("--season", type=int, help="season (2026 only)")
    parser.add_argument(
        "--tranche",
        choices=("A", "B"),
        help="run the tranche gate: required producers + accounting receipt",
    )
    parser.add_argument(
        "--component",
        metavar="SOURCE_ID",
        help="run one component producer (lane usage)",
    )
    args = parser.parse_args(argv)

    if args.season is not None and args.season != 2026:
        print(
            f"this module is 2026-scoped; got --season {args.season}", file=sys.stderr
        )
        return 2

    if args.tranche:
        if args.season != 2026:
            print("--tranche requires --season 2026", file=sys.stderr)
            return 2
        try:
            receipt_path, code = run_tranche(args.tranche)
        except CaptureError as exc:
            print(f"tranche gate failed closed: {exc}", file=sys.stderr)
            return 1
        print(f"accounting receipt: {rel_to_root(receipt_path)} (exit {code})")
        return code

    if args.component:
        if args.season != 2026:
            print("--component requires --season 2026", file=sys.stderr)
            return 2
        try:
            path = _run_producer(
                args.component, league_json_path=None, public_root=None, now=None
            )
        except ValueError as exc:  # CaptureError from either module instance
            print(f"component capture failed: {exc}", file=sys.stderr)
            return 1
        print(f"captured: {rel_to_root(path)}")
        return 0

    if args.freeze_policy:
        if not args.version:
            print("--freeze-policy requires --version vN", file=sys.stderr)
            return 2
        if not args.expected_candidate_sha256:
            print(
                "--freeze-policy requires --expected-candidate-sha256 "
                "(the approved candidate's canonical hash)",
                file=sys.stderr,
            )
            return 2
        try:
            target = freeze_policy(
                args.freeze_policy,
                args.version,
                expected_candidate_sha256=args.expected_candidate_sha256,
            )
        except CaptureError as exc:
            print(f"freeze refused: {exc}", file=sys.stderr)
            return 1
        print(f"frozen: {rel_to_root(target)}")
        return 0

    # Asking for nothing is an error, not a silent success (a main() that
    # does nothing must not exit 0).
    parser.print_usage(sys.stderr)
    print("capture_2026.py: no action requested", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
