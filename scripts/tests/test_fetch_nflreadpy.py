"""Tests for fetch_nflreadpy.py.

Cache discipline (architect F1): --max-age-hours N controls re-fetch.
Idempotency (architect M6): re-running with fresh cache produces no diff.
"""

import time
from pathlib import Path
from unittest.mock import patch

from scripts.fetch_nflreadpy import fetch_one, is_stale


def test_is_stale_when_file_missing(tmp_path: Path):
    """Missing cache file is always stale."""
    assert is_stale(tmp_path / "missing.parquet", max_age_hours=1) is True


def test_is_stale_when_file_recent(tmp_path: Path):
    """File modified moments ago is not stale."""
    f = tmp_path / "fresh.parquet"
    f.write_text("x")
    assert is_stale(f, max_age_hours=24) is False


def test_is_stale_when_file_old(tmp_path: Path, monkeypatch):
    """File older than max_age_hours is stale."""
    f = tmp_path / "old.parquet"
    f.write_text("x")
    # Set mtime to 25 hours ago
    old_time = time.time() - (25 * 3600)
    import os

    os.utime(f, (old_time, old_time))
    assert is_stale(f, max_age_hours=24) is True


def test_fetch_one_skips_when_fresh(tmp_path: Path, monkeypatch):
    """fetch_one does not call nflreadpy when cache is fresh."""
    monkeypatch.setattr("scripts.fetch_nflreadpy.CACHE_DIR", tmp_path)
    cache_file = tmp_path / "schedules_2025.parquet"
    cache_file.write_text("cached_data")
    # Patch nflreadpy to raise if called
    with patch("scripts.fetch_nflreadpy.nfl") as mock_nfl:
        mock_nfl.load_schedules.side_effect = AssertionError("should not be called")
        fetch_one("schedules", season=2025, max_age_hours=24)
    # If we reach here without AssertionError, fetch was correctly skipped
    assert cache_file.exists()
