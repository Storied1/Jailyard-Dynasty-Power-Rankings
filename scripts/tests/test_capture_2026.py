"""Tranche-A acceptance tests for scripts/capture_2026.py (envelope core).

Contract: docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md
A1 scope: S1 envelope write/verify — invariants I1, I2, I3, I4, I5.
Every test here is a named test from the contract's section 7 table.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.capture_2026 import (
    A7_REQUIRED_SOURCES,
    CaptureError,
    build_candidate_policy_v1,
    capture,
    compute_policy_sha256,
    freeze_policy,
    load_capture_table,
    load_policy,
    verify_envelope,
)
from scripts.shared import REPO_ROOT

FIXED_NOW = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
CONTRACT_PATH = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-03-jailyard-p-only-fallback.md"
)


def valid_kwargs(tmp_path: Path, **overrides):
    """A fully valid public-capture argument set; tests break one field at a time."""
    kwargs = dict(
        request={"endpoint_or_dataset": "/league/1312884727480352768", "params": {}},
        season=2026,
        league_id="1312884727480352768",
        captured_at="2026-08-04T10:00:00Z",
        known_at_basis="sleeper API read at captured_at",
        access_scope="public",
        privacy="public",
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        now=FIXED_NOW,
    )
    kwargs.update(overrides)
    return kwargs


def written_files(root: Path):
    return [p for p in root.rglob("*.json")] if root.exists() else []


# ---------------------------------------------------------------------------
# I1 — a failed fetch is never an envelope
# ---------------------------------------------------------------------------


def test_failed_fetch_is_never_written(tmp_path):
    kwargs = valid_kwargs(tmp_path)
    # fetch_sleeper.fetch_json returns None on exhausted retries -> refused
    with pytest.raises(CaptureError):
        capture("sleeper_league", None, **kwargs)
    # non-object payloads are refused (producers wrap lists into objects)
    for bad in ("a string", 42, ["bare", "list"], True):
        with pytest.raises(CaptureError):
            capture("sleeper_league", bad, **kwargs)
    assert written_files(tmp_path / "public") == []
    assert written_files(tmp_path / "private") == []


def test_empty_payload_respects_empty_valid(tmp_path):
    kwargs = valid_kwargs(tmp_path)
    with pytest.raises(CaptureError):
        capture("sleeper_transactions", {}, empty_valid=False, **kwargs)
    assert written_files(tmp_path / "public") == []

    path = capture("sleeper_transactions", {}, empty_valid=True, **kwargs)
    assert path.exists()
    ok, errors = verify_envelope(path)
    assert ok, errors


# ---------------------------------------------------------------------------
# I2 — capture() validates its own arguments (manual ingestion skips main())
# ---------------------------------------------------------------------------


def test_capture_validates_its_own_arguments(tmp_path):
    payload = {"league_id": "1312884727480352768"}

    # captured_at must be an exact tz-aware instant
    for bad_ts in (
        None,
        "",
        "2026-08",  # month-only
        "2026-08-04",  # date-only
        "2026-08-04T10:00:00",  # naive
        "2026-13-04T10:00:00Z",  # malformed
        20260804,
    ):
        with pytest.raises(CaptureError):
            capture(
                "sleeper_league",
                payload,
                **valid_kwargs(tmp_path, captured_at=bad_ts),
            )

    # enum fields are closed sets
    with pytest.raises(CaptureError):
        capture("sleeper_league", payload, **valid_kwargs(tmp_path, privacy="secret"))
    with pytest.raises(CaptureError):
        capture(
            "sleeper_league",
            payload,
            **valid_kwargs(tmp_path, access_scope="internal"),
        )

    # scope/privacy bijection: league_private data may never be written public
    with pytest.raises(CaptureError):
        capture(
            "chat_export",
            payload,
            **valid_kwargs(tmp_path, access_scope="league_private", privacy="public"),
        )
    with pytest.raises(CaptureError):
        capture(
            "sleeper_league",
            payload,
            **valid_kwargs(tmp_path, access_scope="public", privacy="private"),
        )

    # basis and request identity are mandatory
    with pytest.raises(CaptureError):
        capture("sleeper_league", payload, **valid_kwargs(tmp_path, known_at_basis=""))
    with pytest.raises(CaptureError):
        capture("sleeper_league", payload, **valid_kwargs(tmp_path, request=None))
    with pytest.raises(CaptureError):
        capture(
            "sleeper_league",
            payload,
            **valid_kwargs(tmp_path, request={"params": {}}),
        )

    # source_id is a filesystem-safe slug
    for bad_sid in ("", "UPPER", "a b", "a/b", "a\\b", "../escape", "a.b"):
        with pytest.raises(CaptureError):
            capture(bad_sid, payload, **valid_kwargs(tmp_path))

    assert written_files(tmp_path / "public") == []
    assert written_files(tmp_path / "private") == []


# ---------------------------------------------------------------------------
# I3 — append-only store
# ---------------------------------------------------------------------------


def test_append_only_refuses_overwrite(tmp_path):
    kwargs = valid_kwargs(tmp_path)
    payload = {"league_id": "1312884727480352768"}
    path = capture("sleeper_league", payload, **kwargs)
    original = path.read_bytes()

    with pytest.raises(CaptureError):
        capture("sleeper_league", {"different": "payload"}, **kwargs)
    assert path.read_bytes() == original


# ---------------------------------------------------------------------------
# I4 — future-dated captures are refused
# ---------------------------------------------------------------------------


def test_future_dated_capture_refused(tmp_path):
    with pytest.raises(CaptureError):
        capture(
            "sleeper_league",
            {"league_id": "x"},
            **valid_kwargs(tmp_path, captured_at="2026-08-04T13:00:00Z"),
        )
    assert written_files(tmp_path / "public") == []


# ---------------------------------------------------------------------------
# I5 — verification checks payload AND metadata; a tampered envelope is
# not coverage
# ---------------------------------------------------------------------------


def test_tampered_payload_is_not_coverage(tmp_path):
    path = capture(
        "sleeper_league",
        {"league_id": "1312884727480352768", "season": "2026"},
        **valid_kwargs(tmp_path),
    )
    ok, errors = verify_envelope(path)
    assert ok, errors

    env = json.loads(path.read_text(encoding="utf-8"))
    env["payload"]["season"] = "2027"
    path.write_text(json.dumps(env, indent=2), encoding="utf-8")

    ok, errors = verify_envelope(path)
    assert not ok
    assert any("payload_sha256" in e for e in errors)


def test_tampered_metadata_is_not_coverage(tmp_path):
    path = capture(
        "sleeper_league",
        {"league_id": "1312884727480352768"},
        **valid_kwargs(tmp_path),
    )
    env = json.loads(path.read_text(encoding="utf-8"))
    env["captured_at"] = "2026-08-01T00:00:00Z"  # backdate the metadata
    path.write_text(json.dumps(env, indent=2), encoding="utf-8")

    ok, errors = verify_envelope(path)
    assert not ok
    assert any("envelope_sha256" in e for e in errors)


# ---------------------------------------------------------------------------
# A1b — policy freeze (I47, I57) and gate-reachability census (I58)
# ---------------------------------------------------------------------------


def write_candidate(tmp_path: Path, doc=None, name="candidate.json") -> Path:
    doc = doc if doc is not None else build_candidate_policy_v1()
    path = tmp_path / name
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def freeze_v1(tmp_path: Path, **overrides):
    gov = overrides.pop("governance_dir", tmp_path / "governance")
    return freeze_policy(
        write_candidate(tmp_path),
        "v1",
        governance_dir=gov,
        now=FIXED_NOW,
        **overrides,
    )


def test_policy_version_immutable_and_freeze_refuses_overwrite(tmp_path):
    gov = tmp_path / "governance"
    frozen = freeze_v1(tmp_path, governance_dir=gov)
    assert frozen.name == "source_policy_2026.v1.json"
    original = frozen.read_bytes()

    doc = load_policy(frozen)
    assert doc["policy_version"] == "v1"
    assert doc["scope"] == "baseline"
    assert doc["policy_sha256"] == compute_policy_sha256(doc)

    # freezing the same version again is refused and the bytes are untouched
    with pytest.raises(CaptureError):
        freeze_policy(
            write_candidate(tmp_path, name="candidate2.json"),
            "v1",
            governance_dir=gov,
            now=FIXED_NOW,
        )
    assert frozen.read_bytes() == original


def test_freeze_never_writes_another_version_file(tmp_path):
    gov = tmp_path / "governance"
    frozen_v1 = freeze_v1(tmp_path, governance_dir=gov)
    v1_bytes = frozen_v1.read_bytes()
    before = {p.name for p in gov.iterdir()}

    v2_doc = build_candidate_policy_v1()
    v2_doc["policy_version"] = "v2"
    v2_doc["scope"] = "model_arms"
    for row in v2_doc["rows"]:
        row["policy_version"] = "v2"
        row["scope"] = "model_arms"
        row["arms"] = []
        row["required_for"] = []
    frozen_v2 = freeze_policy(
        write_candidate(tmp_path, v2_doc, name="candidate_v2.json"),
        "v2",
        governance_dir=gov,
        now=FIXED_NOW,
    )
    after = {p.name for p in gov.iterdir()}
    assert after - before == {"source_policy_2026.v2.json"}
    assert frozen_v1.read_bytes() == v1_bytes  # I49's A-side: v1 bytes untouched
    assert frozen_v2.name == "source_policy_2026.v2.json"


def test_v1_matches_schema_and_contains_exactly_the_declared_rows(tmp_path):
    frozen = freeze_v1(tmp_path)
    doc = load_policy(frozen)

    components = {
        c for group in load_capture_table()["groups"] for c in group["components"]
    }
    expected = components | {
        "standings_2025",
        "league_history_2022",
        "league_history_2023",
        "league_history_2024",
        "player_crosswalk",
    }
    assert len(expected) == 17
    assert {row["source_id"] for row in doc["rows"]} == expected

    required = {
        row["source_id"] for row in doc["rows"] if row["required_for"] or row["arms"]
    }
    assert required == set(A7_REQUIRED_SOURCES)
    for row in doc["rows"]:
        if row["source_id"] in A7_REQUIRED_SOURCES:
            assert row["required_for"] == ["record_points"]
        else:
            assert row["arms"] == [] and row["required_for"] == []
        assert row["policy_version"] == "v1" and row["scope"] == "baseline"
        assert row["kind"] in ("capture", "qualified_artifact")
        assert row["editions"] == ["2026-preseason", "2026-wk01-preview"]
        window = row["availability_window"]
        assert window["opens_at_rule"] and window["closes_at_rule"]
        if row["source_id"] == "chat_export":
            assert row["chat_refresh"]["initial"] and row["chat_refresh"]["subsequent"]

    # a candidate whose raw bytes carry duplicate keys is refused (fail-closed)
    dup = tmp_path / "dup.json"
    dup.write_text(
        '{"policy_version": "v3", "policy_version": "v3",'
        ' "scope": "baseline", "rows": []}',
        encoding="utf-8",
    )
    with pytest.raises(CaptureError):
        freeze_policy(dup, "v3", governance_dir=tmp_path / "gov3", now=FIXED_NOW)


def test_gate_reachability_census_reports_zero_violations():
    """I58 — parse section 8's gate cells and section 10.B's census from the
    contract file; assert full coverage, ordering, and zero unreachable rows."""
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    order = {
        "A1": 0,
        "A1b": 1,
        "A2": 2,
        "A3": 3,
        "A4": 4,
        "A5": 5,
        "A6": 6,
        "A7": 7,
        "lane": 7.5,
        "B1": 8,
        "B2": 9,
        "B3": 10,
        "B4": 11,
        "B5": 12,
    }

    def expand(cell):
        tokens = set()
        for m in re.finditer(r"I(\d+)[ab]?–I(\d+)", cell):
            for n in range(int(m.group(1)), int(m.group(2)) + 1):
                tokens.add(f"I{n}")
        rest = re.sub(r"I\d+[ab]?–I\d+", "", cell)
        for m in re.finditer(r"\bI(\d+[ab]?)\b", rest):
            tokens.add(f"I{m.group(1)}")
        if re.search(r"\bR1\b", cell):
            tokens.add("R1")
        return tokens

    gate_tokens = {}
    for m in re.finditer(r"^\| \*\*(A\d+b?|B\d+)\*\*\s+\|(.+)\|(.+)\|\s*$", text, re.M):
        for token in expand(m.group(3)):
            gate_tokens.setdefault(token, set()).add(m.group(1))
    # Floor tripwire: the contract's gate surface is 62 tokens today. A parse
    # that shrinks (format drift, regex rot) must FAIL here, not silently pass
    # a smaller surface — planted-deviation probe 5 caught exactly that.
    assert (
        len(gate_tokens) >= 60
    ), f"only {len(gate_tokens)} gate tokens parsed — section 8 format drifted?"

    census = {}
    section = text.split("### B. Gate-reachability census")[1].split("### C.")[0]
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith(("| Invariant", "| ---")):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 5:
            continue
        for token in expand(cols[0]):
            assert token not in census, f"census maps {token} twice"
            census[token] = cols
    assert census, "no census rows parsed"

    violations = []
    for token, tasks in sorted(gate_tokens.items()):
        if token not in census:
            violations.append(f"gate token {token} ({sorted(tasks)}) unmapped")
            continue
        _, gate_col, _, delivered_col, reachable = census[token][:5]
        gates = re.findall(r"\b(A\d+b?|B\d+|lane)\b", gate_col)
        delivered = re.findall(r"\b(A\d+b?|B\d+|lane)\b", delivered_col)
        if "✅" not in reachable:
            violations.append(f"{token} not marked reachable")
        if gates and delivered:
            if max(order[t] for t in delivered) > max(order[t] for t in gates):
                violations.append(f"{token}: delivered {delivered} after gate {gates}")
        for task in tasks:
            if task not in gates:
                violations.append(
                    f"{token}: section 8 gates it at {task}, census says {gates}"
                )
    assert violations == [], "census violations: " + "; ".join(violations)
