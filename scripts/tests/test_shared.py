"""Tests for shared.py's canonical load_json/save_json/parse_ts helpers.

CLAUDE.md calls these three "canonical" (import, never redefine locally) but
none had a dedicated unit test — only indirect coverage via other modules'
tests. This covers them directly.
"""

from datetime import timezone
from pathlib import Path

import pytest

from scripts.shared import (
    load_json,
    month_key_strict,
    parse_ts,
    persona_slug,
    roster_persona_slugs,
    save_json,
)


def test_load_json_reads_valid_file(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text('{"a": 1, "b": [2, 3]}', encoding="utf-8")
    assert load_json(path) == {"a": 1, "b": [2, 3]}


def test_load_json_missing_file_returns_none_by_default(tmp_path: Path):
    missing = tmp_path / "nope.json"
    assert load_json(missing) is None


def test_load_json_missing_file_required_exits(tmp_path: Path):
    missing = tmp_path / "nope.json"
    with pytest.raises(SystemExit) as exc_info:
        load_json(missing, required=True)
    assert exc_info.value.code == 1


def test_load_json_missing_file_warns(tmp_path: Path, capsys):
    missing = tmp_path / "nope.json"
    load_json(missing, label="thing")
    assert "thing" in capsys.readouterr().out


def test_save_json_round_trips(tmp_path: Path):
    out = tmp_path / "out.json"
    data = {"team": "Légion of Bouz", "scores": [1.5, 2.0]}
    save_json(out, data)
    assert load_json(out) == data


def test_save_json_preserves_unicode(tmp_path: Path):
    out = tmp_path / "out.json"
    save_json(out, {"name": "Légion"})
    text = out.read_text(encoding="utf-8")
    assert "Légion" in text
    assert "\\u" not in text


def test_save_json_creates_parent_dirs(tmp_path: Path):
    out = tmp_path / "nested" / "dir" / "out.json"
    save_json(out, {"ok": True})
    assert out.exists()


def test_parse_ts_none_input():
    assert parse_ts(None) is None


def test_parse_ts_unparseable_returns_none():
    assert parse_ts("not a timestamp") is None


def test_parse_ts_z_suffix_is_utc():
    dt = parse_ts("2026-06-09T12:30:00Z")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 12 and dt.minute == 30


def test_parse_ts_naive_string_assumed_utc():
    dt = parse_ts("2026-06-09T12:30:00")
    assert dt.tzinfo == timezone.utc


def test_parse_ts_explicit_offset_converted_to_utc():
    dt = parse_ts("2026-06-09T08:30:00-04:00")
    assert dt.tzinfo == timezone.utc
    assert dt.hour == 12


# --- month_key_strict: fail-closed %Y-%m bucketing (no bare ts[:7]) ---


def test_month_key_strict_valid_instant():
    assert month_key_strict("2025-09-14T22:05:00Z") == "2025-09"


def test_month_key_strict_offset_converted_to_utc():
    # 00:30+05:00 is 19:30Z the PREVIOUS day -> UTC month is 2024-12, NOT the
    # "2025-01" a bare ts[:7] slice of the local string would wrongly produce.
    assert month_key_strict("2025-01-01T00:30:00+05:00") == "2024-12"


def test_month_key_strict_preserves_subsecond_month():
    assert month_key_strict("2025-09-14T22:05:00.123456Z") == "2025-09"


@pytest.mark.parametrize(
    "bad",
    [
        "",  # missing/empty
        None,  # missing
        20250914,  # non-str
        "2025-09",  # month-only
        "2025-09-14",  # date-only
        "not-a-timestamp",  # malformed
        "2025-13-05T00:00:00Z",  # malformed (bad month)
        "2025-09-14T22:05:00",  # naive (no tz)
    ],
)
def test_month_key_strict_rejects_non_instant(bad):
    with pytest.raises(ValueError):
        month_key_strict(bad)


# --- persona_slug / roster_persona_slugs: fail-closed filesystem safety ---


def test_persona_slug_real_members():
    assert persona_slug("Ben Chodos") == "ben-chodos"
    assert persona_slug("~ Harlow") == "harlow"
    assert persona_slug("~ Patrick Raue") == "patrick-raue"
    assert persona_slug("Neo") == "neo"


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "~", "..", "../etc", "a/b", "a\\b", "!!!", ".", None, 5],
)
def test_persona_slug_rejects_unsafe(bad):
    with pytest.raises(ValueError):
        persona_slug(bad)


def test_roster_persona_slugs_rejects_collision():
    # "Ben Chodos" and "ben chodos" both slug to "ben-chodos".
    with pytest.raises(ValueError):
        roster_persona_slugs({"Ben Chodos": {}, "ben chodos": {}})


def test_roster_persona_slugs_maps_members():
    assert roster_persona_slugs({"Neo": {}, "~ Harlow": {}}) == {
        "Neo": "neo",
        "~ Harlow": "harlow",
    }
