"""Tests for v2 extract_week_data — game_context references game_id + src field.

Architect M3: src field per-attribution for graceful degradation.
Architect M2: game_id reference replaces nested weather/opponent.
"""

import pytest

from scripts.extract_week_data import build_game_context_v2


@pytest.fixture
def player_id_to_game_id():
    """Mock crosswalk: sleeper player_id -> nfl game_id for the week."""
    return {
        "4017": "2025_06_ATL_BUF",  # Bijan
        "421": "2025_06_KC_LV",  # Mahomes
    }


def test_game_context_v2_returns_game_id_reference(player_id_to_game_id):
    """game_context contains game_id reference, not nested weather/opponent."""
    ctx = build_game_context_v2(
        player_id="4017",
        sleeper_stats_for_player={"car": 22, "rush_yd": 169, "rush_td": 2},
        player_id_to_game_id=player_id_to_game_id,
        nfl_team_full={"BUF": "Bills", "ATL": "Falcons"},
        opponent_abbr="BUF",
    )
    assert ctx["game_id"] == "2025_06_ATL_BUF"
    assert "weather" not in ctx  # Moved to NFLGame entity
    assert "opponent_dvoa" not in ctx  # Moved to NFLGame entity


def test_game_context_v2_includes_src_attribution(player_id_to_game_id):
    """src field present with per-attribution sources."""
    ctx = build_game_context_v2(
        player_id="4017",
        sleeper_stats_for_player={"car": 22, "rush_yd": 169, "rush_td": 2},
        player_id_to_game_id=player_id_to_game_id,
        nfl_team_full={"BUF": "Bills", "ATL": "Falcons"},
        opponent_abbr="BUF",
    )
    assert "src" in ctx
    assert ctx["src"].get("game_id") in ("nflreadpy", "fallback")


def test_game_context_v2_handles_missing_game_id(player_id_to_game_id):
    """Player not in crosswalk -> game_id null, src.game_id null."""
    ctx = build_game_context_v2(
        player_id="9999",
        sleeper_stats_for_player={},
        player_id_to_game_id=player_id_to_game_id,
        nfl_team_full={},
        opponent_abbr=None,
    )
    assert ctx["game_id"] is None
    assert ctx["src"].get("game_id") is None
