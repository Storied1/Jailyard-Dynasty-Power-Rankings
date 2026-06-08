"""Unit tests for the as-of-week chat-analytics sanitizer in build_chat_context.py.

Synthetic fixtures only -- no file or network I/O.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_chat_context import _month_le  # noqa: E402

# ~ Tuesday after Week 5 MNF, 2025 (early October).
CUTOFF = datetime(2025, 10, 7, 6, 59, 59, tzinfo=timezone.utc)


def test_month_le_before_and_at_cutoff_true():
    assert _month_le("2025-09", CUTOFF) is True
    assert _month_le("2025-10", CUTOFF) is True


def test_month_le_after_cutoff_false():
    assert _month_le("2025-11", CUTOFF) is False
    assert _month_le("2026-02", CUTOFF) is False


def test_month_le_none_is_true():
    # Missing date == not future; treat as visible (callers decide inclusion).
    assert _month_le(None, CUTOFF) is True
