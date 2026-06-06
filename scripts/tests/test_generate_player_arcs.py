"""Tests for generate_player_arcs. Synthetic fixtures, no file/network I/O."""

from scripts.generate_player_arcs import build_aggregates, build_weekly


def _matchups(season_weeks):
    """season_weeks: {week: [(roster_id, players, starters, points{pid: f})]}"""
    return {
        str(w): [
            {
                "roster_id": rid,
                "matchup_id": 1,
                "players": players,
                "starters": starters,
                "players_points": pts,
            }
            for rid, players, starters, pts in entries
        ]
        for w, entries in season_weeks.items()
    }


def test_build_weekly_owner_points_started():
    m = {2025: _matchups({1: [(3, ["p1", "p2"], ["p1"], {"p1": 21.5, "p2": 0.0})]})}
    weekly = build_weekly(m)
    assert weekly["p1"] == [
        {
            "season": 2025,
            "week": 1,
            "owner_roster_id": 3,
            "fantasy_points": 21.5,
            "started": True,
            "game_id": None,
            "status": "no_game_data",
        }
    ]
    assert weekly["p2"][0]["started"] is False
    assert weekly["p2"][0]["fantasy_points"] == 0.0


def test_build_weekly_missing_points_entry_is_null():
    m = {2025: _matchups({1: [(3, ["p1"], [], {})]})}
    assert build_weekly(m)["p1"][0]["fantasy_points"] is None


def test_build_weekly_sorted_by_season_week():
    m = {
        2023: _matchups(
            {2: [(1, ["p1"], [], {"p1": 1.0})], 1: [(1, ["p1"], [], {"p1": 2.0})]}
        ),
        2022: _matchups({5: [(2, ["p1"], [], {"p1": 3.0})]}),
    }
    rows = build_weekly(m)["p1"]
    assert [(r["season"], r["week"]) for r in rows] == [(2022, 5), (2023, 1), (2023, 2)]


def _wk(season, week, rid, pts, started=False, status="played"):
    return {
        "season": season,
        "week": week,
        "owner_roster_id": rid,
        "fantasy_points": pts,
        "started": started,
        "game_id": None,
        "status": status,
    }


def test_aggregates_totals_and_best_worst():
    weekly = [
        _wk(2025, 1, 3, 10.0, True),
        _wk(2025, 2, 3, 30.0),
        _wk(2025, 3, 3, 0.0, status="bye_week"),
        _wk(2025, 4, 7, None, status="no_game_data"),
    ]
    agg = build_aggregates(weekly)["2025"]
    assert agg["total_fantasy_pts"] == 40.0
    assert agg["weeks_rostered"] == 4
    assert agg["weeks_started"] == 1
    assert agg["weeks_played"] == 2
    assert agg["best_week"] == {"week": 2, "points": 30.0, "owner_roster_id": 3}
    assert agg["worst_week"] == {"week": 1, "points": 10.0, "owner_roster_id": 3}


def test_aggregates_no_played_weeks_gives_null_best_worst():
    agg = build_aggregates([_wk(2025, 1, 3, 0.0, status="no_game_data")])["2025"]
    assert agg["best_week"] is None and agg["worst_week"] is None
    assert agg["weeks_played"] == 0
