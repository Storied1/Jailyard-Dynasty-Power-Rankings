"""Tests for save_json_canonical helper.

Canonicalization (architect M6) requires sort_keys=True so re-serializing the
same data produces byte-identical output regardless of dict insertion order.
"""

from pathlib import Path

from scripts.shared import save_json_canonical


def test_canonical_save_sorts_keys(tmp_path: Path):
    """Keys sorted alphabetically regardless of insertion order."""
    data = {"zebra": 1, "alpha": 2, "mongoose": 3}
    out = tmp_path / "out.json"
    save_json_canonical(out, data)
    text = out.read_text(encoding="utf-8")
    assert text.index('"alpha"') < text.index('"mongoose"') < text.index('"zebra"')


def test_canonical_save_idempotent(tmp_path: Path):
    """Saving same data twice produces byte-identical files."""
    data = {"b": [3, 1, 2], "a": {"y": 1, "x": 2}}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    save_json_canonical(a, data)
    save_json_canonical(b, data)
    assert a.read_bytes() == b.read_bytes()


def test_canonical_save_non_ascii_preserved(tmp_path: Path):
    """ensure_ascii=False so unicode renders as glyphs not escapes."""
    data = {"team": "Légion of Bouz", "emoji": "✅"}
    out = tmp_path / "u.json"
    save_json_canonical(out, data)
    text = out.read_text(encoding="utf-8")
    assert "Légion" in text
    assert "✅" in text
    assert "\\u" not in text
