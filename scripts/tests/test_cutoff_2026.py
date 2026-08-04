"""A4 acceptance tests — kickoff qualification + cutoff receipt.

Contract: I17 (verified envelope + venue-timezone derivation, never
hardcoded), I18 (receipt binds game, source, version), R1 (preseason =
kickoff - 7d; preview strictly before kickoff), I42 unit surface (cutoffs
are read only from the hash-verified receipt).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.capture_2026 import CaptureError, capture
from scripts.cutoff_2026 import (
    build_cutoff_receipt,
    load_cutoff_receipt,
    qualify_kickoff,
    write_cutoff_receipt,
)

FIXED_NOW = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)


def game(game_id, gameday, gametime, week=1, game_type="REG"):
    return {
        "game_id": game_id,
        "season": 2026,
        "game_type": game_type,
        "week": week,
        "gameday": gameday,
        "weekday": "n/a",
        "gametime": gametime,
        "away_team": game_id.split("_")[-2],
        "home_team": game_id.split("_")[-1],
    }


DEFAULT_GAMES = [
    # opener: Wed 2026-09-09 20:20 ET == 2026-09-10T00:20:00Z (EDT, UTC-4)
    game("2026_01_DAL_PHI", "2026-09-09", "20:20"),
    game("2026_01_KC_LAC", "2026-09-10", "20:00"),
    game("2026_01_TB_ATL", "2026-09-13", "13:00"),
    game("2026_02_PHI_NYG", "2026-09-17", "20:15", week=2),
]


def schedules_envelope(tmp_path: Path, games=None) -> Path:
    return capture(
        "nfl_schedules",
        {"dataset": "schedules", "season": 2026, "games": games or DEFAULT_GAMES},
        request={
            "endpoint_or_dataset": "nflreadpy:schedules",
            "params": {"season": 2026},
        },
        season=2026,
        league_id="1312884727480352768",
        captured_at="2026-08-04T10:00:00Z",
        known_at_basis="nflverse schedules dataset read at captured_at",
        access_scope="public",
        privacy="public",
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        now=FIXED_NOW,
    )


def test_kickoff_derived_with_venue_timezone(tmp_path):
    envelope_path = schedules_envelope(tmp_path)
    qualified = qualify_kickoff(envelope_path)
    # 20:20 Eastern on 2026-09-09 is 00:20 UTC on 2026-09-10 (EDT = UTC-4)
    assert qualified["kickoff_utc"] == "2026-09-10T00:20:00Z"
    assert qualified["kickoff_game_id"] == "2026_01_DAL_PHI"

    # the derivation responds to the data — a different opener time moves it
    moved = [game("2026_01_DAL_PHI", "2026-09-09", "19:00")] + DEFAULT_GAMES[1:]
    envelope2 = schedules_envelope(tmp_path / "b", games=moved)
    assert qualify_kickoff(envelope2)["kickoff_utc"] == "2026-09-09T23:00:00Z"

    # a tampered envelope is refused — derivation demands a VERIFIED source
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    env["payload"]["games"][0]["gametime"] = "18:00"
    envelope_path.write_text(json.dumps(env), encoding="utf-8")
    with pytest.raises(CaptureError):
        qualify_kickoff(envelope_path)


def test_kickoff_never_hardcoded_in_production_path():
    source = Path("scripts/cutoff_2026.py").read_text(encoding="utf-8")
    for literal in ("2026-09-10T00:20", "2026-09-09", "00:20:00Z", "20:20"):
        assert literal not in source, f"kickoff literal {literal!r} hardcoded"


def test_cutoff_receipt_binds_game_source_and_version(tmp_path):
    envelope_path = schedules_envelope(tmp_path)
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    receipt = build_cutoff_receipt(envelope_path, now=FIXED_NOW)

    assert receipt["season"] == 2026
    assert receipt["kickoff_game_id"] == "2026_01_DAL_PHI"
    assert receipt["kickoff_source_locator"] == envelope["locator"]
    assert receipt["kickoff_source_envelope_sha256"] == envelope["envelope_sha256"]
    assert receipt["derivation_version"]
    assert receipt["qualified_at"] == "2026-08-04T12:00:00Z"

    path = write_cutoff_receipt(receipt, receipts_root=tmp_path / "receipts")
    loaded = load_cutoff_receipt(path)
    assert loaded == receipt

    # I42 unit: a tampered receipt is refused at read time (hash re-verified)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["preview_cutoff_utc"] = "2026-09-11T00:00:00Z"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(CaptureError):
        load_cutoff_receipt(path)


def test_preseason_cutoff_is_seven_days_before_kickoff(tmp_path):
    receipt = build_cutoff_receipt(schedules_envelope(tmp_path), now=FIXED_NOW)
    kickoff = datetime.fromisoformat(receipt["kickoff_utc"].replace("Z", "+00:00"))
    preseason = datetime.fromisoformat(
        receipt["preseason_cutoff_utc"].replace("Z", "+00:00")
    )
    assert kickoff - preseason == timedelta(days=7)
    assert receipt["preseason_cutoff_utc"] == "2026-09-03T00:20:00Z"


def test_preview_cutoff_is_strictly_before_kickoff(tmp_path):
    receipt = build_cutoff_receipt(schedules_envelope(tmp_path), now=FIXED_NOW)
    kickoff = datetime.fromisoformat(receipt["kickoff_utc"].replace("Z", "+00:00"))
    preview = datetime.fromisoformat(
        receipt["preview_cutoff_utc"].replace("Z", "+00:00")
    )
    assert preview < kickoff
    assert kickoff - preview == timedelta(seconds=1)
