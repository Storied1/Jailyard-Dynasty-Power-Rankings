"""Tests for generate_nfl_games.py.

Generator reads cached nflreadpy outputs and writes one JSON per game_id.
Idempotency (architect M6): re-running produces byte-identical files.
Schema validity (architect M4): each file validates against nfl_game.schema.json.
"""

from scripts.generate_nfl_games import build_game_record


def test_build_game_record_minimal():
    """Minimal schedule row produces valid game record."""
    schedule_row = {
        "game_id": "2025_06_BUF_NYJ",
        "season": 2025,
        "week": 6,
        "home_team": "BUF",
        "away_team": "NYJ",
        "home_score": 28,
        "away_score": 14,
        "kickoff": "2025-10-12T13:00-04:00",
        "stadium": "Highmark Stadium",
        "stadium_id": "BUF",
        "roof": "outdoors",
        "surface": "grass",
        "temp": 52,
        "wind": 12,
        "spread_line": -7.5,
        "total_line": 47,
        "away_qb_id": "00-0036442",
        "home_qb_id": "00-0034796",
        "away_rest": 7,
        "home_rest": 7,
        "div_game": True,
    }
    record = build_game_record(schedule_row, team_stats=None, injuries=None)
    assert record["game_id"] == "2025_06_BUF_NYJ"
    assert record["home_team"] == "BUF"
    assert record["away_team"] == "NYJ"
    assert record["temp"] == 52
    assert record["div_game"] is True
    assert record["starting_qbs"]["home"] == "00-0034796"
    assert record["starting_qbs"]["away"] == "00-0036442"
    assert record["rest_days"]["home"] == 7
    assert record["result"] == 14  # 28 - 14


def test_build_game_record_handles_missing_fields():
    """Optional fields default to null without crashing."""
    schedule_row = {
        "game_id": "2025_18_FOO_BAR",
        "season": 2025,
        "week": 18,
        "home_team": "FOO",
        "away_team": "BAR",
        "home_score": None,
        "away_score": None,
        "temp": None,
        "wind": None,
        "spread_line": None,
        "total_line": None,
    }
    record = build_game_record(schedule_row, team_stats=None, injuries=None)
    assert record["temp"] is None
    assert record["result"] is None
