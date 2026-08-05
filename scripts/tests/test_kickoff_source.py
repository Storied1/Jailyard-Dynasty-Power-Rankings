"""K2.2 — timezone-correct kickoff qualification; neutral sites fail closed."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.kickoff_source import (
    UnavailableEvidence,
    first_kickoff_instant,
    resolve_zone,
    strictly_before,
    to_utc,
)

PY = sys.executable
REPO = Path(__file__).resolve().parents[2]


def test_local_time_is_converted_not_suffixed():
    assert to_utc("2025-09-04", "20:20", "America/New_York") == "2025-09-05T00:20:00Z"
    assert to_utc("2025-09-04", "20:20", "America/New_York") != "2025-09-04T20:20:00Z"


def test_missing_timezone_fails_closed():
    with pytest.raises(UnavailableEvidence):
        to_utc("2025-09-04", "20:20", None)


def test_neutral_site_without_an_override_fails_closed():
    with pytest.raises(UnavailableEvidence):
        resolve_zone(
            {"home_team": "ZZZ", "stadium_id": "NEUTRAL_X"},
            {"by_team": {}, "by_stadium": {}},
        )


def test_stadium_override_beats_home_team():
    tz = {
        "by_team": {"JAX": "America/New_York"},
        "by_stadium": {"LON00": "Europe/London"},
    }
    assert (
        resolve_zone({"home_team": "JAX", "stadium_id": "LON00"}, tz) == "Europe/London"
    )


def test_result_carries_every_source_hash():
    try:
        out = first_kickoff_instant(2025)
    except UnavailableEvidence:
        pytest.skip("schedules parquet absent; run scripts/fetch_nflreadpy.py first")
    assert out["instant_utc"].endswith("Z") and len(out["source_hashes"]) >= 2
    assert all(v.startswith("sha256:") for v in out["source_hashes"].values())


def test_strictly_before_is_strictly_before():
    assert strictly_before("2025-09-05T00:20:00Z") == "2025-09-05T00:19:59Z"


def test_derive_preview_cutoff_cli_is_exclusive_create_and_source_bound(tmp_path):
    """The exact CLI path: writes the artifact with source hashes matching
    independently computed input hashes; a repeat invocation cannot truncate or
    replace it; a bad season leaves NO artifact behind."""
    if not (REPO / "data" / "external" / "schedules_2025.parquet").exists():
        pytest.skip("schedules parquet absent")
    out = tmp_path / "preview_cutoff_test.v1.json"
    cmd = [
        PY,
        "scripts/kickoff_source.py",
        "--derive-preview-cutoff",
        "--season",
        "2025",
        "--out",
        str(out),
    ]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["cutoff_utc"] == strictly_before(doc["kickoff_utc"])
    import hashlib

    for rel, recorded in doc["source_hashes"].items():
        actual = "sha256:" + hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        assert recorded == actual, rel
    assert doc["provenance"].startswith("python scripts/kickoff_source.py")
    before = out.read_bytes()
    r2 = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    assert r2.returncode != 0, "a repeat invocation must refuse, never overwrite"
    assert out.read_bytes() == before, "the committed artifact is byte-untouched"
    missing = tmp_path / "none.v1.json"
    r3 = subprocess.run(
        [
            PY,
            "scripts/kickoff_source.py",
            "--derive-preview-cutoff",
            "--season",
            "1901",
            "--out",
            str(missing),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert (
        r3.returncode != 0 and not missing.exists()
    ), "missing inputs leave no false artifact"
