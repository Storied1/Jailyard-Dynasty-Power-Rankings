"""Tests for fetch_nfl_stats retry logic + response shape validation."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from shared import (  # noqa: E402
    NflStatsResponseError,
    fetch_nfl_stats,
    validate_nfl_stats_response,
)

# ---------------------------------------------------------------------------
# validate_nfl_stats_response — pure validation
# ---------------------------------------------------------------------------


def test_validate_accepts_valid_payload():
    payload = [
        {"player_id": "4984", "team": "BUF", "opponent": "BAL", "stats": {}},
        {"player_id": "5849", "team": "KC", "opponent": "LAC", "stats": {}},
    ]
    assert validate_nfl_stats_response(payload) is True


def test_validate_accepts_empty_list_by_default():
    # Preseason / off-week may return an empty list — not an error
    assert validate_nfl_stats_response([]) is True


def test_validate_rejects_dict_response():
    with pytest.raises(NflStatsResponseError, match="expected list"):
        validate_nfl_stats_response({"stats": []})


def test_validate_rejects_none():
    with pytest.raises(NflStatsResponseError):
        validate_nfl_stats_response(None)


def test_validate_rejects_entry_missing_player_id():
    payload = [{"team": "BUF", "stats": {}}]  # no player_id
    with pytest.raises(NflStatsResponseError, match="missing player_id"):
        validate_nfl_stats_response(payload)


def test_validate_rejects_entry_that_isnt_dict():
    payload = [{"player_id": "1"}, "not a dict"]
    with pytest.raises(NflStatsResponseError, match="expected dict"):
        validate_nfl_stats_response(payload)


def test_validate_respects_min_entries_threshold():
    with pytest.raises(NflStatsResponseError, match="at least 5"):
        validate_nfl_stats_response([{"player_id": "1"}], min_entries=5)


# ---------------------------------------------------------------------------
# fetch_nfl_stats — retry behavior via urlopen mocks
# ---------------------------------------------------------------------------


def _make_mock_response(payload_bytes):
    """Build a context-manager mock that urlopen's `with` block expects."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read = MagicMock(return_value=payload_bytes)
    return mock_resp


def test_fetch_nfl_stats_success_first_attempt():
    import json

    valid_payload = [{"player_id": "1", "team": "BUF", "stats": {}}]
    payload_bytes = json.dumps(valid_payload).encode("utf-8")
    mock_resp = _make_mock_response(payload_bytes)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = fetch_nfl_stats(2025, 1, retries=3, delay=0)
    assert result == valid_payload


def test_fetch_nfl_stats_retries_on_url_error_then_succeeds():
    import json
    import urllib.error

    valid_payload = [{"player_id": "1", "team": "BUF", "stats": {}}]
    payload_bytes = json.dumps(valid_payload).encode("utf-8")
    mock_resp = _make_mock_response(payload_bytes)

    # First 2 attempts raise, third succeeds
    calls = [
        urllib.error.URLError("transient"),
        urllib.error.URLError("transient"),
        mock_resp,
    ]

    def side_effect(*args, **kwargs):
        result = calls.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("urllib.request.urlopen", side_effect=side_effect):
        with patch("time.sleep"):  # skip backoff delays
            result = fetch_nfl_stats(2025, 1, retries=3, delay=0)
    assert result == valid_payload


def test_fetch_nfl_stats_raises_after_exhausting_retries():
    import urllib.error

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("persistent"),
    ):
        with patch("time.sleep"):
            with pytest.raises(urllib.error.URLError):
                fetch_nfl_stats(2025, 1, retries=2, delay=0)


def test_fetch_nfl_stats_raises_on_invalid_shape():
    import json

    # Sleeper returns something unexpected (dict instead of list)
    bad_payload = {"unexpected": "shape"}
    payload_bytes = json.dumps(bad_payload).encode("utf-8")
    mock_resp = _make_mock_response(payload_bytes)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with patch("time.sleep"):
            with pytest.raises(NflStatsResponseError):
                fetch_nfl_stats(2025, 1, retries=1, delay=0)
