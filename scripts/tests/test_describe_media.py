"""Unit tests for describe_media.py response parsing (both backends share it)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("cv2")  # optional dep; describe_media hard-exits without it

from describe_media import parse_model_json_array  # noqa: E402


def test_parse_plain_json_array():
    raw = '[{"description": "a", "tags": ["meme"], "humor_type": "roast"}]'
    out = parse_model_json_array(raw, 1)
    assert out == [{"description": "a", "tags": ["meme"], "humor_type": "roast"}]


def test_parse_fenced_json_array():
    # Headless Claude Code wraps results in markdown fences (observed live).
    raw = '```json\n[{"description": "x", "tags": [], "humor_type": "none"}]\n```'
    out = parse_model_json_array(raw, 1)
    assert out[0]["description"] == "x"


def test_parse_array_embedded_in_prose():
    raw = 'Here you go:\n[{"description": "y", "tags": ["stats"], "humor_type": "none"}]\nDone.'
    out = parse_model_json_array(raw, 1)
    assert out[0]["tags"] == ["stats"]


def test_parse_garbage_returns_placeholders():
    out = parse_model_json_array("no json here at all", 3)
    assert len(out) == 3
    assert all(o["description"] == "Could not parse" for o in out)


def test_parse_non_array_json_returns_placeholders():
    # A bare object (not an array) must not be returned as-is.
    out = parse_model_json_array('{"description": "solo"}', 2)
    assert len(out) == 2
    assert all(o["tags"] == ["other"] for o in out)
