"""Tests for generate_franchise_wings. Synthetic fixtures only."""

from scripts.generate_franchise_wings import (
    build_lineage_entry,
    build_trophy_case,
    championship_from_bracket,
    playoff_participants,
    rekey_h2h,
)
from scripts.shared import normalize_username


def test_championship_min_matchup_id_at_max_round():
    winners = [
        {"r": 2, "m": 5, "w": 3, "l": 1, "t1": 3, "t2": 1},
        {"r": 3, "m": 7, "w": 11, "l": 9, "t1": 11, "t2": 9},  # 3rd place game
        {"r": 3, "m": 6, "w": 5, "l": 2, "t1": 5, "t2": 2},  # title game (min m)
    ]
    assert championship_from_bracket(winners) == (5, 2)


def test_playoff_participants_membership():
    winners = [
        {"r": 1, "m": 1, "w": 3, "l": 1, "t1": 3, "t2": 1},
        {"r": 2, "m": 6, "w": 5, "l": 3, "t1": 5, "t2": 3},
    ]
    assert playoff_participants(winners) == {1, 3, 5}


def test_rekey_h2h_substitutes_owner_ids():
    lh_h2h = {"oA|oB": {"wins": 5, "losses": 2, "pf": 1021.22, "pa": 888.78}}
    out = rekey_h2h(lh_h2h, {"oA": 1, "oB": 2}, "oA")
    assert out == {
        "2": {
            "opponent_roster_id": 2,
            "wins": 5,
            "losses": 2,
            "pf": 1021.22,
            "pa": 888.78,
        }
    }


def test_build_trophy_case():
    champs_by_season = {2022: (5, 2), 2023: (5, 9), 2024: (1, 5)}
    playoffs_by_season = {2022: {1, 2, 5, 9}, 2023: {5, 9}, 2024: {1, 5}}
    tc = build_trophy_case(5, champs_by_season, playoffs_by_season)
    assert tc == {
        "championships": [
            {"season": 2022, "runner_up_roster_id": 2},
            {"season": 2023, "runner_up_roster_id": 9},
        ],
        "runner_ups": [2024],
        "playoff_appearances": [2022, 2023, 2024],
    }


def test_normalize_username_collapses_whitespace_and_case():
    assert normalize_username("kharlo w") == normalize_username("Kharlow")


def test_build_lineage_entry_precedence_draft_then_trade_then_add():
    arc = {
        "player_id": "p1",
        "name": "P One",
        "position": "RB",
        "ownership_history": [
            {
                "event": "draft",
                "season": 2022,
                "round": 1,
                "pick": 5,
                "draft_slot": 5,
                "roster_id": 3,
                "date": None,
            },
            {
                "event": "trade",
                "season": 2024,
                "date": "2024-10-01",
                "from_roster_id": 3,
                "to_roster_id": 7,
                "in_return": {"players": [], "picks": []},
            },
        ],
    }
    e7 = build_lineage_entry(arc, roster_id=7)
    assert e7["acquired"] == {
        "event": "trade",
        "season": 2024,
        "detail": "from roster 3",
    }
    e3 = build_lineage_entry(arc, roster_id=3)
    assert e3["acquired"] == {
        "event": "draft",
        "season": 2022,
        "detail": "Round 1 Pick 5",
    }
    e9 = build_lineage_entry(arc, roster_id=9)
    assert e9["acquired"]["event"] == "unknown"
