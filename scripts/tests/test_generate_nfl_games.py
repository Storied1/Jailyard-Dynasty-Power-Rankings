"""Tests for generate_nfl_games.py.

Generator reads cached nflreadpy outputs and writes one JSON per game_id.
Idempotency (architect M6): re-running produces byte-identical files.
Schema validity (architect M4): each file validates against nfl_game.schema.json.
"""

import polars as pl

from scripts.generate_nfl_games import build_game_record


def test_build_game_record_minimal():
    """Minimal schedule row produces valid game record."""
    # Synthetic schedule row — game_id is illustrative, not from real 2025 schedule.
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
    # Synthetic schedule row — game_id is illustrative, not from real 2025 schedule.
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


def test_team_stats_for_game_returns_both_teams():
    """Given a 2-row team_stats DataFrame for one game, returns both team entries."""
    from scripts.generate_nfl_games import _team_stats_for_game

    df = pl.DataFrame(
        {
            "game_id": ["2025_06_BUF_NYJ", "2025_06_BUF_NYJ"],
            "team": ["BUF", "NYJ"],
            "passing_epa": [12.5, -3.2],
            "rushing_epa": [4.1, 2.0],
            "receiving_epa": [12.5, -3.2],
            "passing_yards": [320, 180],
            "rushing_yards": [120, 95],
            "passing_tds": [3, 1],
            "rushing_tds": [1, 0],
        }
    )
    result = _team_stats_for_game("2025_06_BUF_NYJ", df)
    assert "BUF" in result
    assert "NYJ" in result
    assert result["BUF"]["passing_epa"] == 12.5
    assert result["NYJ"]["rushing_yards"] == 95


def test_team_stats_for_game_no_match_returns_none():
    """Wrong game_id returns None (no rows match)."""
    from scripts.generate_nfl_games import _team_stats_for_game

    df = pl.DataFrame(
        {
            "game_id": ["2025_06_BUF_NYJ"],
            "team": ["BUF"],
            "passing_epa": [12.5],
            "rushing_epa": [4.1],
            "receiving_epa": [12.5],
            "passing_yards": [320],
            "rushing_yards": [120],
            "passing_tds": [3],
            "rushing_tds": [1],
        }
    )
    result = _team_stats_for_game("2025_06_DEN_KC", df)
    assert result is None


def test_injuries_for_game_filters_status():
    """Only Out/Doubtful/Questionable statuses pass the filter."""
    from scripts.generate_nfl_games import _injuries_for_game

    df = pl.DataFrame(
        {
            "week": [6, 6, 6, 6, 6, 7],
            "team": ["BUF", "BUF", "NYJ", "BUF", "DEN", "BUF"],
            "gsis_id": ["00-001", "00-002", "00-003", "00-004", "00-005", "00-006"],
            "full_name": ["A", "B", "C", "D", "E", "F"],
            "report_status": [
                "Out",
                "Probable",
                "Questionable",
                "IR",
                "Doubtful",
                "Out",
            ],
            "report_primary_injury": [
                "ankle",
                "knee",
                "shoulder",
                "hamstring",
                "back",
                "wrist",
            ],
            "practice_status": ["DNP", "FP", "LP", "DNP", "DNP", "DNP"],
            "practice_primary_injury": [
                "ankle",
                None,
                "shoulder",
                "hamstring",
                "back",
                "wrist",
            ],
        }
    )
    result = _injuries_for_game(week=6, home="BUF", away="NYJ", injuries=df)
    statuses = [r["status"] for r in result]
    assert "Out" in statuses
    assert "Questionable" in statuses
    assert "Probable" not in statuses  # Filtered out
    assert "IR" not in statuses  # Filtered out
    assert all(r["team"] in ("BUF", "NYJ") for r in result)  # Wrong team filtered
    assert all(r["gsis_id"] != "00-006" for r in result)  # Wrong week filtered
