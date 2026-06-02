"""Tests for generate_expanded_week.py.

Architect M2: weekN_data_expanded.json carries a top-level games{} map; scorers
+ awards.top_performer reference games by game_context.game_id (one fetch, no
per-holder duplication).
Architect N2: content-addressable regen via line-ending- & version-aware hash.

Holders nest under matchups[].team{1,2}.top_scorers[] + awards.top_performer —
NOT a top-level array. Tests mirror reality.
"""

from pathlib import Path

import scripts.generate_expanded_week as mod
from scripts.generate_expanded_week import (
    _referenced_game_ids,
    build_expanded,
    compute_manifest_hash,
)


def _week_fixture():
    return {
        "meta": {"week": 6, "season": 2025},
        "matchups": [
            {
                "team1": {
                    "top_scorers": [
                        {
                            "player_id": "9509",
                            "game_context": {"game_id": "2025_06_BUF_ATL", "src": {}},
                        }
                    ]
                },
                "team2": {
                    "top_scorers": [
                        {
                            "player_id": "4017",
                            "game_context": {"game_id": "2025_06_CHI_WAS", "src": {}},
                        }
                    ]
                },
            }
        ],
        "awards": {
            "top_performer": {
                "player_id": "9509",
                "game_context": {"game_id": "2025_06_BUF_ATL", "src": {}},
            }
        },
    }


def test_compute_manifest_hash_stable_across_runs(tmp_path: Path):
    a = tmp_path / "a.json"
    a.write_text('{"x": 1}')
    assert compute_manifest_hash([a]) == compute_manifest_hash([a])


def test_compute_manifest_hash_changes_when_input_changes(tmp_path: Path):
    a = tmp_path / "a.json"
    a.write_text('{"x": 1}')
    h1 = compute_manifest_hash([a])
    a.write_text('{"x": 2}')
    assert h1 != compute_manifest_hash([a])


def test_compute_manifest_hash_line_ending_invariant(tmp_path: Path):
    """F4: CRLF (Windows on-disk) and LF (git/CI) inputs hash identically."""
    lf = tmp_path / "lf"
    lf.mkdir()
    crlf = tmp_path / "crlf"
    crlf.mkdir()
    (lf / "a.json").write_bytes(b'{\n  "x": 1\n}\n')
    (crlf / "a.json").write_bytes(b'{\r\n  "x": 1\r\n}\r\n')
    assert compute_manifest_hash([lf / "a.json"]) == compute_manifest_hash(
        [crlf / "a.json"]
    )


def test_compute_manifest_hash_changes_with_inliner_version(
    tmp_path: Path, monkeypatch
):
    """F1: bumping INLINER_VERSION invalidates the manifest."""
    a = tmp_path / "a.json"
    a.write_text('{"x": 1}')
    monkeypatch.setattr(mod, "INLINER_VERSION", "1")
    h1 = mod.compute_manifest_hash([a])
    monkeypatch.setattr(mod, "INLINER_VERSION", "2")
    assert h1 != mod.compute_manifest_hash([a])


def test_build_expanded_builds_games_map_from_nested_and_awards():
    nfl_games = {
        "2025_06_BUF_ATL": {
            "game_id": "2025_06_BUF_ATL",
            "home_team": "ATL",
            "away_team": "BUF",
            "temp": 52,
        },
        "2025_06_CHI_WAS": {
            "game_id": "2025_06_CHI_WAS",
            "home_team": "WAS",
            "away_team": "CHI",
            "temp": 61,
        },
    }
    expanded = build_expanded(_week_fixture(), nfl_games)
    assert set(expanded["games"]) == {"2025_06_BUF_ATL", "2025_06_CHI_WAS"}
    assert expanded["games"]["2025_06_BUF_ATL"]["temp"] == 52


def test_build_expanded_no_per_holder_duplication():
    nfl_games = {
        "2025_06_BUF_ATL": {"game_id": "2025_06_BUF_ATL", "temp": 52},
        "2025_06_CHI_WAS": {"game_id": "2025_06_CHI_WAS", "temp": 61},
    }
    expanded = build_expanded(_week_fixture(), nfl_games)
    scorer = expanded["matchups"][0]["team1"]["top_scorers"][0]
    assert "game" not in scorer  # referenced via game_context.game_id, not inlined
    assert scorer["game_context"]["game_id"] == "2025_06_BUF_ATL"


def test_build_expanded_games_map_excludes_unreferenced():
    nfl_games = {
        "2025_06_BUF_ATL": {"game_id": "2025_06_BUF_ATL", "temp": 52},
        "2025_06_CHI_WAS": {"game_id": "2025_06_CHI_WAS", "temp": 61},
        "2025_06_UNUSED_XX": {"game_id": "2025_06_UNUSED_XX", "temp": 99},
    }
    expanded = build_expanded(_week_fixture(), nfl_games)
    assert "2025_06_UNUSED_XX" not in expanded["games"]


def test_build_expanded_awards_game_resolvable_in_map():
    expanded = build_expanded(
        _week_fixture(), {"2025_06_BUF_ATL": {"game_id": "2025_06_BUF_ATL", "temp": 52}}
    )
    tp_gid = expanded["awards"]["top_performer"]["game_context"]["game_id"]
    assert tp_gid in expanded["games"]


def test_referenced_game_ids_collects_nested_and_awards():
    assert _referenced_game_ids(_week_fixture()) == {
        "2025_06_BUF_ATL",
        "2025_06_CHI_WAS",
    }
