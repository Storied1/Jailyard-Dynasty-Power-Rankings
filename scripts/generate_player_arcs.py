"""Generate cross-season Player Arcs (Phase 1b Item 2).

data/2025/player_arcs/{pid}.json + _index.json (split path, >3MB rule)
or data/2025/player_arcs.json (monolith, if under threshold).

Ground truth: committed matchups.json (weekly ownership/points/started).
Narrative: draft_picks.json + transactions.json events.
Status/game_id enrichment: gitignored Sleeper stats caches + committed
nfl_games files (2025 game_ids only). See plan design decisions 1-12
(~/.claude/plans/immutable-questing-origami.md).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from shared import DATA_DIR  # noqa: E402

SEASONS = (2022, 2023, 2024, 2025)
CURRENT_SEASON = 2026  # current_owner source (live offseason state)
ARC_SEASON_DIR = DATA_DIR / "2025"  # spec-mandated vintage path
SPLIT_THRESHOLD_BYTES = 3_000_000  # spec architect F2: deterministic 3MB rule
WEEKS = range(1, 19)


def _ms_to_iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def build_weekly(matchups_by_season):
    """pid -> sorted weekly rows. Matchups are ownership ground truth (#1)."""
    weekly = {}
    for season in sorted(matchups_by_season):
        season_weeks = matchups_by_season[season]
        for week_str in sorted(season_weeks, key=int):
            for entry in season_weeks[week_str]:
                rid = entry["roster_id"]
                points = entry.get("players_points") or {}
                starters = set(entry.get("starters") or [])
                for pid in entry.get("players") or []:
                    weekly.setdefault(pid, []).append(
                        {
                            "season": season,
                            "week": int(week_str),
                            "owner_roster_id": rid,
                            "fantasy_points": points.get(pid),
                            "started": pid in starters,
                            "game_id": None,
                            "status": "no_game_data",  # enriched later (T4)
                        }
                    )
    for rows in weekly.values():
        rows.sort(key=lambda r: (r["season"], r["week"]))
    return weekly


def build_aggregates(weekly_rows):
    """Per-season aggregates over ALL rostered weeks 1-18 (decision #10)."""
    by_season = {}
    for r in weekly_rows:
        by_season.setdefault(str(r["season"]), []).append(r)
    out = {}
    for season, rows in sorted(by_season.items()):
        played = [
            r
            for r in rows
            if r["status"] == "played" and r["fantasy_points"] is not None
        ]
        best = max(played, key=lambda r: r["fantasy_points"], default=None)
        worst = min(played, key=lambda r: r["fantasy_points"], default=None)
        out[season] = {
            "total_fantasy_pts": round(
                sum(
                    r["fantasy_points"] for r in rows if r["fantasy_points"] is not None
                ),
                2,
            ),
            "weeks_rostered": len(rows),
            "weeks_started": sum(1 for r in rows if r["started"]),
            "weeks_played": len(played),
            "best_week": (
                {
                    "week": best["week"],
                    "points": best["fantasy_points"],
                    "owner_roster_id": best["owner_roster_id"],
                }
                if best
                else None
            ),
            "worst_week": (
                {
                    "week": worst["week"],
                    "points": worst["fantasy_points"],
                    "owner_roster_id": worst["owner_roster_id"],
                }
                if worst
                else None
            ),
        }
    return out


def build_txn_events(*args, **kwargs):  # implemented in T3
    raise NotImplementedError


def build_rostered_spans(*args, **kwargs):  # implemented in T3
    raise NotImplementedError


def choose_split(*args, **kwargs):  # implemented in T4
    raise NotImplementedError
