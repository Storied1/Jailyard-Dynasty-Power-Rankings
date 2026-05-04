"""Tests for v2 extract_week_data — game_context references game_id + src field.

Architect M3: src field per-attribution for graceful degradation.
Architect M2: game_id reference replaces nested weather/opponent.
Task 5 fix-up: per-week team-pair crosswalk (NOT ff_playerids static team).
"""

import pytest

from scripts.extract_week_data import build_game_context_v2


@pytest.fixture
def team_pair_to_game_id():
    """Mock per-week crosswalk: frozenset(team_pair) -> game_id."""
    return {
        frozenset({"BUF", "ATL"}): "2025_06_BUF_ATL",
        frozenset({"KC", "LV"}): "2025_06_KC_LV",
    }


def test_game_context_v2_returns_game_id_reference(team_pair_to_game_id):
    """game_context contains game_id reference, not nested weather/opponent."""
    ctx = build_game_context_v2(
        player_id="4017",
        sleeper_stats_for_player={"car": 22, "rush_yd": 169, "rush_td": 2},
        team_pair_to_game_id=team_pair_to_game_id,
        nfl_team_full={"BUF": "Bills", "ATL": "Falcons"},
        player_team="ATL",
        opponent_abbr="BUF",
    )
    assert ctx["game_id"] == "2025_06_BUF_ATL"
    assert "weather" not in ctx  # Moved to NFLGame entity
    assert "opponent_dvoa" not in ctx  # Moved to NFLGame entity


def test_game_context_v2_includes_src_attribution(team_pair_to_game_id):
    """src field present with per-attribution sources."""
    ctx = build_game_context_v2(
        player_id="4017",
        sleeper_stats_for_player={"car": 22, "rush_yd": 169, "rush_td": 2},
        team_pair_to_game_id=team_pair_to_game_id,
        nfl_team_full={"BUF": "Bills", "ATL": "Falcons"},
        player_team="ATL",
        opponent_abbr="BUF",
    )
    assert "src" in ctx
    assert ctx["src"].get("game_id") in ("nflreadpy", "fallback")


def test_game_context_v2_handles_missing_team_pair(team_pair_to_game_id):
    """Player team not in any week's game -> game_id null, src.game_id null."""
    ctx = build_game_context_v2(
        player_id="9999",
        sleeper_stats_for_player={},
        team_pair_to_game_id=team_pair_to_game_id,
        nfl_team_full={},
        player_team=None,
        opponent_abbr=None,
    )
    assert ctx["game_id"] is None
    assert ctx["src"].get("game_id") is None


def test_game_context_v2_traded_player_resolves_to_correct_game(team_pair_to_game_id):
    """C1 fix: a player whose ff_playerids team is stale (e.g. TEN) but who
    actually played for ATL this week resolves via Sleeper's per-week truth,
    not ff_playerids' static team.

    Sleeper says: player_team=ATL, opponent=BUF.
    Crosswalk has BUF-ATL game.
    Result: game_id = 2025_06_BUF_ATL (correct), NOT a stale TEN game.
    """
    ctx = build_game_context_v2(
        player_id="traded_player_id",
        sleeper_stats_for_player={"car": 12, "rush_yd": 65},
        team_pair_to_game_id=team_pair_to_game_id,
        nfl_team_full={"BUF": "Bills", "ATL": "Falcons"},
        player_team="ATL",  # Sleeper's per-week truth — NOT ff_playerids' static team
        opponent_abbr="BUF",
    )
    assert ctx["game_id"] == "2025_06_BUF_ATL"
