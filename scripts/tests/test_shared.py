"""Tests for shared.py's canonical load_json/save_json/parse_ts helpers.

CLAUDE.md calls these three "canonical" (import, never redefine locally) but
none had a dedicated unit test — only indirect coverage via other modules'
tests. This covers them directly.
"""

from datetime import timezone
from pathlib import Path

import pytest

from scripts.shared import load_json, parse_ts, save_json


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
