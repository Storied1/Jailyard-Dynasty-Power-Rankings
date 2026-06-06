"""Tests for generate_player_arcs. Synthetic fixtures, no file/network I/O."""

from scripts.generate_player_arcs import (
    build_aggregates,
    build_draft_events,
    build_ownership,
    build_rostered_spans,
    build_txn_events,
    build_weekly,
)


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


# --- ownership_history (T3) ---


def _trade_txn(
    adds,
    drops,
    roster_ids,
    created=1726000000000,
    picks=None,
    status="complete",
    ttype="trade",
):
    return {
        "type": ttype,
        "status": status,
        "leg": 3,
        "created": created,
        "adds": adds,
        "drops": drops,
        "roster_ids": roster_ids,
        "draft_picks": picks or [],
        "settings": None,
    }


def test_trade_event_links_both_sides_with_in_return():
    txns = {"3": [_trade_txn({"pA": 6, "pB": 1}, {"pA": 1, "pB": 6}, [1, 6])]}
    events = build_txn_events({2024: txns}, names={"pA": "Player A", "pB": "Player B"})
    ev = [e for e in events["pA"] if e["event"] == "trade"][0]
    assert ev["from_roster_id"] == 1 and ev["to_roster_id"] == 6
    assert ev["in_return"]["players"] == [{"player_id": "pB", "name": "Player B"}]
    assert ev["season"] == 2024
    assert ev["date"] == "2024-09-10"


def test_trade_in_return_includes_picks_with_three_roster_semantics():
    pick = {
        "round": 2,
        "season": "2025",
        "roster_id": 9,
        "owner_id": 1,
        "previous_owner_id": 6,
    }
    txns = {"3": [_trade_txn({"pA": 6}, {"pA": 1}, [1, 6], picks=[pick])]}
    ev = build_txn_events({2024: txns}, names={})["pA"][0]
    assert ev["in_return"]["picks"] == [
        {
            "round": 2,
            "season": "2025",
            "original_roster_id": 9,
            "from_roster_id": 6,
            "to_roster_id": 1,
        }
    ]


def test_failed_and_pick_only_txns_produce_no_events():
    txns = {
        "3": [
            _trade_txn({"pA": 6}, {"pA": 1}, [1, 6], status="failed"),
            _trade_txn(None, None, [1, 6]),  # pick-only trade
        ]
    }
    assert build_txn_events({2024: txns}, names={}) == {}


def test_waiver_add_and_commissioner_drop():
    txns = {
        "5": [
            {
                "type": "waiver",
                "status": "complete",
                "leg": 5,
                "created": 1727000000000,
                "adds": {"pC": 4},
                "drops": None,
                "roster_ids": [4],
                "draft_picks": [],
                "settings": {"waiver_bid": 17},
            },
            {
                "type": "commissioner",
                "status": "complete",
                "leg": 5,
                "created": 1727000001000,
                "adds": None,
                "drops": {"pD": 9},
                "roster_ids": [9],
                "draft_picks": [],
                "settings": None,
            },
        ]
    }
    events = build_txn_events({2025: txns}, names={})
    assert events["pC"] == [
        {
            "event": "add",
            "season": 2025,
            "date": "2024-09-22",
            "roster_id": 4,
            "via": "waiver",
            "bid": 17,
        }
    ]
    assert events["pD"] == [
        {
            "event": "drop",
            "season": 2025,
            "date": "2024-09-22",
            "roster_id": 9,
            "via": "commissioner",
            "bid": None,
        }
    ]


def test_draft_events():
    picks_doc = {
        "season": 2022,
        "draft_id": "d",
        "draft_type": "snake",
        "start_date": "2022-08-08",
        "picks": [
            {
                "round": 1,
                "pick_no": 5,
                "draft_slot": 5,
                "roster_id": 3,
                "picked_by": "u3",
                "player_id": "pE",
                "is_keeper": None,
                "metadata": {},
            }
        ],
    }
    events = build_draft_events({2022: picks_doc})
    assert events["pE"] == [
        {
            "event": "draft",
            "season": 2022,
            "round": 1,
            "pick": 5,
            "draft_slot": 5,
            "roster_id": 3,
            "date": "2022-08-08",
        }
    ]


def test_rostered_spans_contiguity_and_owner_change():
    rows = (
        [_wk(2024, w, 3, 1.0) for w in (1, 2, 3)]
        + [_wk(2024, w, 7, 1.0) for w in (4, 5)]
        + [_wk(2024, 9, 7, 1.0)]  # gap weeks 6-8 (dropped)
        + [_wk(2025, 1, 7, 1.0)]
    )  # new season: never bridged
    spans = build_rostered_spans(rows)
    assert spans == [
        {
            "event": "rostered",
            "season": 2024,
            "roster_id": 3,
            "from_week": 1,
            "to_week": 3,
        },
        {
            "event": "rostered",
            "season": 2024,
            "roster_id": 7,
            "from_week": 4,
            "to_week": 5,
        },
        {
            "event": "rostered",
            "season": 2024,
            "roster_id": 7,
            "from_week": 9,
            "to_week": 9,
        },
        {
            "event": "rostered",
            "season": 2025,
            "roster_id": 7,
            "from_week": 1,
            "to_week": 1,
        },
    ]


def test_build_ownership_order_draft_then_dated_then_spans():
    draft = {
        "event": "draft",
        "season": 2024,
        "round": 1,
        "pick": 5,
        "draft_slot": 5,
        "roster_id": 3,
        "date": "2024-08-15",
    }
    trade = {
        "event": "trade",
        "season": 2024,
        "date": "2024-10-01",
        "from_roster_id": 3,
        "to_roster_id": 7,
        "in_return": {"players": [], "picks": []},
    }
    span = {
        "event": "rostered",
        "season": 2024,
        "roster_id": 3,
        "from_week": 1,
        "to_week": 4,
    }
    history = build_ownership([trade], [draft], [span])
    assert [e["event"] for e in history] == ["draft", "trade", "rostered"]
