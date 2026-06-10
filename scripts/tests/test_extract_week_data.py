"""Regression tests for extract_week_data.py helpers.

Covers the F15-F24 fixes: _is_upset, _parse_home_away, _stat_line branches,
build_game_context lookup + home/away, _compute_matchup_momentum corner
cases, and _annotate_matchup_momentum integration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extract_week_data import _annotate_matchup_momentum  # noqa: E402
from extract_week_data import (
    _compute_matchup_momentum,
    _is_upset,
    _stat_line,
    build_game_context,
    compute_as_of_history,
)

# ---------------------------------------------------------------------------
# _is_upset (F23)
# ---------------------------------------------------------------------------


def test_is_upset_week1_returns_false():
    # Week 1 has empty prev_rankings — no baseline to judge
    assert _is_upset(winner_rid=5, t1_rid=5, t2_rid=3, prev_rankings={}) is False


def test_is_upset_legit_upset_true():
    # Winner was rank 10 (worse), loser was rank 2 (better) — real upset
    prev = {5: 10, 3: 2}
    assert _is_upset(winner_rid=5, t1_rid=5, t2_rid=3, prev_rankings=prev) is True


def test_is_upset_favorite_won_false():
    # Winner was rank 2 (better), loser was rank 10 — not an upset
    prev = {5: 2, 3: 10}
    assert _is_upset(winner_rid=5, t1_rid=5, t2_rid=3, prev_rankings=prev) is False


def test_is_upset_missing_roster_returns_false():
    # Loser not in prev_rankings — can't judge
    prev = {5: 2}
    assert _is_upset(winner_rid=5, t1_rid=5, t2_rid=3, prev_rankings=prev) is False


def test_is_upset_no_winner_returns_false():
    assert (
        _is_upset(winner_rid=None, t1_rid=5, t2_rid=3, prev_rankings={5: 2, 3: 10})
        is False
    )


# ---------------------------------------------------------------------------
# _stat_line (F19)
# ---------------------------------------------------------------------------


def test_stat_line_qb():
    stats = {"pass_yd": 394, "pass_td": 2, "rush_yd": 30, "rush_td": 2}
    assert _stat_line("QB", stats) == "394 pass yd, 2 pass TD, 30 rush yd, 2 rush TD"


def test_stat_line_rb():
    stats = {"rush_att": 22, "rush_yd": 135, "rush_td": 2, "rec": 3, "rec_yd": 32}
    assert _stat_line("RB", stats) == "22 carries, 135 yd, 2 rush TD, 3 rec, 32 rec yd"


def test_stat_line_wr():
    stats = {"rec": 7, "rec_yd": 95, "rec_td": 1}
    assert _stat_line("WR", stats) == "7 rec, 95 yd, 1 TD"


def test_stat_line_kicker_missed_all_fgs():
    # F19: K with fga but zero fgm should still render "0/3 FG"
    stats = {"fgm": 0, "fga": 3, "xpm": 2}
    assert _stat_line("K", stats) == "0/3 FG, 2 XP"


def test_stat_line_kicker_only_xp():
    stats = {"xpm": 3}
    assert _stat_line("K", stats) == "3 XP"


def test_stat_line_team_defense_uses_correct_keys():
    # F19: team DEF uses sack/int/fum_rec/def_td/safe/blk_kick/pts_allow,
    # NOT idp_* keys. Previously this silently returned "".
    stats = {"sack": 4, "int": 2, "def_td": 1, "fum_rec": 1, "pts_allow": 10}
    result = _stat_line("DEF", stats)
    assert "4 sack" in result
    assert "2 INT" in result
    assert "1 def TD" in result
    assert "1 FR" in result
    assert "10 pts allowed" in result


def test_stat_line_idp_de():
    # IDP positions use idp_* keys
    stats = {"idp_tkl_solo": 5, "idp_sack": 2.0, "idp_qb_hit": 3}
    assert _stat_line("DE", stats) == "5 solo tkl, 2.0 sack, 3 QB hit"


def test_stat_line_idp_lb():
    stats = {"idp_tkl_solo": 7, "idp_int": 1}
    assert _stat_line("LB", stats) == "7 solo tkl, 1 INT"


def test_stat_line_unknown_position_fallback():
    # F19: positions like P, FB, OL previously returned ""; now fallback
    # to fantasy pts so "data present but no formatter" is distinguishable
    # from "no data".
    stats = {"pts_ppr": 4.5}
    assert _stat_line("P", stats) == "4.5 fantasy pts"


def test_stat_line_empty_stats():
    assert _stat_line("QB", {}) == ""
    assert _stat_line("QB", None) == ""


# ---------------------------------------------------------------------------
# build_game_context (F18 dict lookup + F20 home/away)
# ---------------------------------------------------------------------------


def test_build_game_context_dict_lookup():
    # F18: stats_cache is now a dict keyed by str(player_id)
    stats_cache = {
        "4984": {
            "player_id": 4984,
            "opponent": "BAL",
            "game_id": "202510104",  # opaque Sleeper format
            "stats": {"pass_yd": 394, "pass_td": 2},
        }
    }
    gc = build_game_context("4984", "BUF", "QB", stats_cache)
    assert gc is not None
    assert gc["opponent"] == "BAL"
    assert "394 pass yd" in gc["stat_line"]
    assert gc["one_liner"].startswith("394 pass yd, 2 pass TD vs. the Ravens")


def test_build_game_context_not_found():
    stats_cache = {"1234": {"player_id": 1234, "opponent": "KC", "stats": {}}}
    assert build_game_context("9999", "BUF", "QB", stats_cache) is None


def test_build_game_context_empty_cache():
    assert build_game_context("4984", "BUF", "QB", None) is None
    assert build_game_context("4984", "BUF", "QB", {}) is None


def test_build_game_context_no_player_id():
    assert build_game_context(None, "BUF", "QB", {"4984": {}}) is None


def test_build_game_context_no_opponent():
    stats_cache = {
        "1": {
            "player_id": 1,
            "opponent": None,
            "stats": {"pass_yd": 100},
        }
    }
    gc = build_game_context("1", "LAC", "QB", stats_cache)
    assert gc["opponent"] is None
    assert gc["stat_line"] == "100 pass yd"


# ---------------------------------------------------------------------------
# _compute_matchup_momentum (F16)
# ---------------------------------------------------------------------------


def _make_std(name, rank, score, label):
    return {
        "team_name": name,
        "rank": rank,
        "momentum": {"score": score, "label": label},
    }


def _make_matchup(t1, t2):
    return {"team1": {"team_name": t1}, "team2": {"team_name": t2}}


def test_matchup_momentum_all_early_returns_too_early_sentinel():
    # F16: week 1 all teams "opening" → skip entirely, emit "too early"
    mu = _make_matchup("Alpha", "Beta")
    mbyt = {
        "Alpha": {"score": 0, "label": "opening"},
        "Beta": {"score": 0, "label": "opening"},
    }
    rbyt = {"Alpha": 1, "Beta": 2}
    result = _compute_matchup_momentum(mu, mbyt, rbyt, all_early=True)
    assert result["label"] == "too early"
    assert result["favorite_team_name"] is None
    assert result["edge"] == 0


def test_matchup_momentum_zero_edge_returns_none_favorite():
    # F16: both teams same momentum → coin flip with no fabricated favorite
    mu = _make_matchup("Alpha", "Beta")
    mbyt = {
        "Alpha": {"score": 1.0, "label": "hot"},
        "Beta": {"score": 1.0, "label": "hot"},
    }
    rbyt = {"Alpha": 3, "Beta": 4}
    result = _compute_matchup_momentum(mu, mbyt, rbyt, all_early=False)
    assert result["label"] == "coin flip"
    assert result["favorite_team_name"] is None


def test_matchup_momentum_slight_edge_has_correct_favorite():
    mu = _make_matchup("Alpha", "Beta")
    mbyt = {
        "Alpha": {"score": 1.5, "label": "surging"},
        "Beta": {"score": 0.6, "label": "hot"},
    }
    rbyt = {"Alpha": 3, "Beta": 4}
    result = _compute_matchup_momentum(mu, mbyt, rbyt, all_early=False)
    assert result["label"] == "slight edge"
    assert result["favorite_team_name"] == "Alpha"


def test_matchup_momentum_heavy_lean_favorite_is_higher_momentum():
    mu = _make_matchup("Alpha", "Beta")
    mbyt = {
        "Alpha": {"score": -1.0, "label": "cooling"},
        "Beta": {"score": 2.0, "label": "surging"},
    }
    rbyt = {"Alpha": 1, "Beta": 8}
    result = _compute_matchup_momentum(mu, mbyt, rbyt, all_early=False)
    assert result["label"] == "heavy lean"
    assert result["favorite_team_name"] == "Beta"


def test_matchup_momentum_upset_brewing_favorite_is_hot_underdog():
    # F16: underdog (rank 5, higher momentum) plays favorite (rank 2, lower
    # momentum). Rank gap 3 ≤ 4. Should label "upset brewing" AND set
    # favorite = underdog (not the higher seed).
    mu = _make_matchup("TopSeed", "Underdog")
    mbyt = {
        "TopSeed": {"score": -0.5, "label": "cooling"},
        "Underdog": {"score": 2.0, "label": "surging"},
    }
    rbyt = {"TopSeed": 2, "Underdog": 5}
    result = _compute_matchup_momentum(mu, mbyt, rbyt, all_early=False)
    assert result["label"] == "upset brewing"
    assert result["favorite_team_name"] == "Underdog"


def test_matchup_momentum_upset_brewing_requires_close_rank_gap():
    # Rank gap of 8 → should NOT fire upset-brewing even if underdog has
    # higher momentum. Should just be "heavy lean" for the underdog.
    mu = _make_matchup("TopSeed", "Underdog")
    mbyt = {
        "TopSeed": {"score": -0.5, "label": "cooling"},
        "Underdog": {"score": 2.0, "label": "surging"},
    }
    rbyt = {"TopSeed": 2, "Underdog": 10}
    result = _compute_matchup_momentum(mu, mbyt, rbyt, all_early=False)
    assert result["label"] == "heavy lean"
    # Underdog is still the favorite on pure edge math (higher momentum)
    assert result["favorite_team_name"] == "Underdog"


# ---------------------------------------------------------------------------
# _annotate_matchup_momentum integration (F16)
# ---------------------------------------------------------------------------


def test_annotate_all_early_sets_too_early_on_every_matchup():
    standings = [
        _make_std("Alpha", 1, 0, "opening"),
        _make_std("Beta", 2, 0, "opening"),
        _make_std("Gamma", 3, 0, "opening"),
        _make_std("Delta", 4, 0, "opening"),
    ]
    matchups = [_make_matchup("Alpha", "Beta"), _make_matchup("Gamma", "Delta")]
    _annotate_matchup_momentum(matchups, standings)
    for mu in matchups:
        assert mu["momentum"]["label"] == "too early"
        assert mu["momentum"]["favorite_team_name"] is None


def test_annotate_mixed_standings_produces_real_labels():
    standings = [
        _make_std("Alpha", 1, 2.5, "surging"),
        _make_std("Beta", 2, 1.0, "hot"),
        _make_std("Gamma", 3, -0.2, "steady"),
        _make_std("Delta", 4, -2.5, "collapsing"),
    ]
    matchups = [_make_matchup("Alpha", "Delta"), _make_matchup("Beta", "Gamma")]
    _annotate_matchup_momentum(matchups, standings)
    # Alpha (2.5) vs Delta (-2.5) → edge 5.0, heavy lean, Alpha favored
    assert matchups[0]["momentum"]["label"] == "heavy lean"
    assert matchups[0]["momentum"]["favorite_team_name"] == "Alpha"
    # Beta (1.0) vs Gamma (-0.2) → edge 1.2, slight edge, Beta favored
    assert matchups[1]["momentum"]["label"] == "slight edge"
    assert matchups[1]["momentum"]["favorite_team_name"] == "Beta"


# ---------------------------------------------------------------------------
# compute_as_of_history (Phase 4 / 1c-F7 standings leak fix)
# ---------------------------------------------------------------------------


def _history_fixture():
    oid = "OWNER1"
    return {
        "elo_current": {oid: 1561.1},  # season-END (the leak)
        "elo_history": {
            oid: [
                {"season": 2025, "week": 1, "elo": 1500.0},
                {"season": 2025, "week": 2, "elo": 1520.0},
                {"season": 2025, "week": 3, "elo": 1540.0},
                {"season": 2025, "week": 4, "elo": 1672.1},  # PEAK, future of wk3
                {"season": 2025, "week": 5, "elo": 1561.1},
            ]
        },
        "franchise_stats": {
            oid: {
                "all_time": {"wins": 39, "losses": 17},  # incl. full 2025
                "championships": 2,
                "best_win_streak": 11,
                "peak_elo": 1672.1,
                "season_results": [
                    {"season": 2022, "wins": 7, "losses": 7},
                    {"season": 2023, "wins": 11, "losses": 3},
                    {"season": 2024, "wins": 7, "losses": 7},
                    {"season": 2025, "wins": 14, "losses": 0},
                ],
            }
        },
    }


def test_as_of_current_elo_is_week_n_not_season_end():
    out = compute_as_of_history("OWNER1", 2025, 3, _history_fixture(), 3, 0)
    assert out["current_elo"] == 1540.0  # NOT 1561.1


def test_as_of_peak_elo_through_week_n_only():
    out = compute_as_of_history("OWNER1", 2025, 3, _history_fixture(), 3, 0)
    assert out["peak_elo"] == 1540.0  # wk4's 1672.1 is the future


def test_as_of_all_time_record_excludes_future_2025():
    # prior seasons 2022-24 = 25-17; 2025 through wk3 = 3-0  ->  28-17 (not 39-17)
    out = compute_as_of_history("OWNER1", 2025, 3, _history_fixture(), 3, 0)
    assert out["all_time_record"] == "28-17"


def test_as_of_omits_unrecoverable_counters():
    out = compute_as_of_history("OWNER1", 2025, 3, _history_fixture(), 3, 0)
    assert "championships" not in out and "best_win_streak" not in out


def test_as_of_empty_when_owner_missing():
    assert compute_as_of_history("NOPE", 2025, 3, _history_fixture(), 3, 0) == {}
