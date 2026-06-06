"""Tests for fetch_draft_picks transform + validation (no network)."""

import pytest

from scripts.fetch_draft_picks import (
    build_season_file,
    divergence_report,
    transform_picks,
    validate_picks_response,
)


def _raw_pick(**over):
    p = {
        "round": 1,
        "pick_no": 1,
        "draft_slot": 1,
        "roster_id": 8,
        "picked_by": "u8",
        "player_id": "7564",
        "is_keeper": None,
        "draft_id": "792315382554824704",
        "reactions": None,
        "metadata": {
            "first_name": "Jonathan",
            "last_name": "Taylor",
            "position": "RB",
            "team": "IND",
            "injury_status": "",
        },
    }
    p.update(over)
    return p


def test_validate_rejects_non_list():
    with pytest.raises(ValueError):
        validate_picks_response({"not": "a list"})


def test_validate_rejects_missing_player_id():
    with pytest.raises(ValueError):
        validate_picks_response([_raw_pick(player_id=None)])


def test_transform_keeps_canonical_fields_only():
    out = transform_picks([_raw_pick()])
    assert out == [
        {
            "round": 1,
            "pick_no": 1,
            "draft_slot": 1,
            "roster_id": 8,
            "picked_by": "u8",
            "player_id": "7564",
            "is_keeper": None,
            "metadata": {
                "first_name": "Jonathan",
                "last_name": "Taylor",
                "position": "RB",
                "team": "IND",
            },
        }
    ]


def test_transform_sorts_by_pick_no():
    out = transform_picks(
        [_raw_pick(pick_no=2, player_id="2"), _raw_pick(pick_no=1, player_id="1")]
    )
    assert [p["pick_no"] for p in out] == [1, 2]


def test_build_season_file_shape():
    doc = build_season_file(
        2022,
        {
            "draft_id": "d1",
            "start_time": 1660000000000,
            "type": "snake",
            "season": "2022",
        },
        transform_picks([_raw_pick()]),
    )
    assert doc["season"] == 2022
    assert doc["draft_id"] == "d1"
    assert doc["draft_type"] == "snake"
    assert doc["start_date"] == "2022-08-08"  # UTC date of ms epoch
    assert len(doc["picks"]) == 1


def test_divergence_report_flags_mismatch():
    picks = [_raw_pick(roster_id=8, picked_by="uX")]
    owner_by_roster = {8: "u8"}
    flagged = divergence_report(picks, owner_by_roster)
    assert flagged == [
        {"pick_no": 1, "roster_id": 8, "picked_by": "uX", "expected_owner": "u8"}
    ]


def test_divergence_report_empty_when_consistent():
    assert divergence_report([_raw_pick()], {8: "u8"}) == []
