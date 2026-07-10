"""Unit tests for resolve_media's GIPHY junk-batch detection."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip(
    "requests"
)  # optional dep; resolve_media imports it at module level

from resolve_media import _is_junk_batch  # noqa: E402


def test_junk_batch_detected():
    assert _is_junk_batch([{"giphy_id": "cCZIBp9U0MiuQ"}, {"giphy_id": "real"}])


def test_real_batch_passes():
    assert not _is_junk_batch([{"giphy_id": "xc3OTAUFkT0TT5DtSv"}])


def test_empty_batch_is_not_junk():
    assert not _is_junk_batch([])
