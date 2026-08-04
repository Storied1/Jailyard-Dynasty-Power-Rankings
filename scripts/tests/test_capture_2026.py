"""Tranche-A acceptance tests for scripts/capture_2026.py (envelope core).

Contract: docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md
A1 scope: S1 envelope write/verify — invariants I1, I2, I3, I4, I5.
Every test here is a named test from the contract's section 7 table.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.capture_2026 import CaptureError, capture, verify_envelope

FIXED_NOW = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)


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
