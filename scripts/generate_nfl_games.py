"""Generate per-game NFLGame entity files from cached nflreadpy data.

Reads:  data/external/{schedules,team_stats,injuries}_2025.parquet
Writes: data/2025/nfl_games/{game_id}.json (one per game)

Architect M2: NFLGame promoted to first-class entity. Player entries in
weekN_data.json reference game_id instead of nesting weather/opponent.

Architect M6: canonical save (sort_keys=True, ensure_ascii=False) — idempotent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import polars as pl

# Ensure scripts/ is on sys.path so this module is runnable both as a script
# (`python scripts/generate_nfl_games.py`) and as part of the test package
# (`from scripts.generate_nfl_games import ...`).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_nflreadpy import fetch_one  # noqa: E402
from shared import REPO_ROOT, save_json_canonical  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "2025" / "nfl_games"


def build_game_record(
    schedule_row: dict[str, Any],
    team_stats: pl.DataFrame | None,
    injuries: pl.DataFrame | None,
) -> dict[str, Any]:
    """Build one NFLGame record from a schedule row + optional team_stats + injuries."""
    home = schedule_row["home_team"]
    away = schedule_row["away_team"]
    h_score = schedule_row.get("home_score")
    a_score = schedule_row.get("away_score")

    record: dict[str, Any] = {
        "game_id": schedule_row["game_id"],
        "season": schedule_row["season"],
        "week": schedule_row["week"],
        "home_team": home,
        "away_team": away,
        "home_score": h_score,
        "away_score": a_score,
        "result": (
            (h_score - a_score)
            if (h_score is not None and a_score is not None)
            else None
        ),
        "kickoff": schedule_row.get("gametime") or schedule_row.get("kickoff"),
        "stadium": schedule_row.get("stadium"),
        "stadium_id": schedule_row.get("stadium_id"),
        "roof": schedule_row.get("roof"),
        "surface": schedule_row.get("surface"),
        "temp": schedule_row.get("temp"),
        "wind": schedule_row.get("wind"),
        "spread_line": schedule_row.get("spread_line"),
        "total_line": schedule_row.get("total_line"),
        "starting_qbs": {
            "home": schedule_row.get("home_qb_id"),
            "away": schedule_row.get("away_qb_id"),
        },
        "rest_days": {
            "home": schedule_row.get("home_rest"),
            "away": schedule_row.get("away_rest"),
        },
        # nflreadpy stores div_game as Int32 (0/1); schema expects boolean.
        "div_game": (
            bool(schedule_row["div_game"])
            if schedule_row.get("div_game") is not None
            else None
        ),
        "team_stats": (
            _team_stats_for_game(schedule_row["game_id"], team_stats)
            if team_stats is not None
            else None
        ),
        "key_injuries": (
            _injuries_for_game(schedule_row["week"], home, away, injuries)
            if injuries is not None
            else []
        ),
    }
    return record


def _team_stats_for_game(
    game_id: str, team_stats: pl.DataFrame
) -> dict[str, Any] | None:
    """Extract per-team aggregated EPA from team_stats DataFrame."""
    rows = team_stats.filter(pl.col("game_id") == game_id)
    if len(rows) == 0:
        return None
    out: dict[str, Any] = {}
    for r in rows.iter_rows(named=True):
        out[r["team"]] = {
            "passing_epa": r.get("passing_epa"),
            "rushing_epa": r.get("rushing_epa"),
            "receiving_epa": r.get("receiving_epa"),
            "passing_yards": r.get("passing_yards"),
            "rushing_yards": r.get("rushing_yards"),
            "passing_tds": r.get("passing_tds"),
            "rushing_tds": r.get("rushing_tds"),
        }
    return out


def _injuries_for_game(
    week: int, home: str, away: str, injuries: pl.DataFrame
) -> list[dict[str, Any]]:
    """Filter injuries to teams playing this week, status of concern."""
    rows = injuries.filter(
        (pl.col("week") == week)
        & (pl.col("team").is_in([home, away]))
        & (pl.col("report_status").is_in(["Out", "Doubtful", "Questionable"]))
    )
    return [
        {
            "team": r["team"],
            "gsis_id": r["gsis_id"],
            "name": r.get("full_name"),
            "status": r["report_status"],
            "primary_injury": r.get("report_primary_injury"),
        }
        for r in rows.iter_rows(named=True)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--max-age-hours", type=int, default=168)
    args = parser.parse_args()

    sched_path = fetch_one("schedules", args.season, args.max_age_hours)
    ts_path = fetch_one("team_stats", args.season, args.max_age_hours)
    inj_path = fetch_one("injuries", args.season, args.max_age_hours)

    schedules = pl.read_parquet(sched_path).sort("game_id")
    team_stats = pl.read_parquet(ts_path).sort(["game_id", "team"])
    injuries = pl.read_parquet(inj_path).sort(["week", "team", "gsis_id"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for row in schedules.iter_rows(named=True):
        record = build_game_record(row, team_stats, injuries)
        out_path = OUT_DIR / f"{record['game_id']}.json"
        save_json_canonical(out_path, record)
        count += 1
    print(f"Wrote {count} NFLGame files to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
