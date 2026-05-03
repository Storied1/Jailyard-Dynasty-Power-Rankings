"""Fetch and cache nflreadpy data tables to data/external/.

Single source of truth for: schedules, team_stats, injuries, ff_playerids.
Replaces v1-spec's ESPN scoreboard + ESPN injury feed + OpenWeatherMap
(spike confirmed all three failed for one reason or another).

Cache cadence (architect F1): --max-age-hours N (default 168 = 7 days).
Refresh weekly during NFL season via GitHub Actions (Phase 2).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import nflreadpy as nfl

# Ensure scripts/ is on sys.path so this module is runnable both as a script
# (`python scripts/fetch_nflreadpy.py`) and as part of the test package
# (`from scripts.fetch_nflreadpy import ...`).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import REPO_ROOT  # noqa: E402

CACHE_DIR = REPO_ROOT / "data" / "external"

# Mapping: cache_key → (nflreadpy loader, kwargs builder)
LOADERS = {
    "schedules": lambda season: nfl.load_schedules(seasons=season),
    "team_stats": lambda season: nfl.load_team_stats(seasons=season),
    "injuries": lambda season: nfl.load_injuries(seasons=season),
    "ff_playerids": lambda season: nfl.load_ff_playerids(),  # season-agnostic
}


def is_stale(cache_path: Path, max_age_hours: int) -> bool:
    """True if cache file is missing or older than max_age_hours."""
    if not cache_path.exists():
        return True
    age_seconds = time.time() - cache_path.stat().st_mtime
    return age_seconds > (max_age_hours * 3600)


def fetch_one(name: str, season: int, max_age_hours: int = 168) -> Path:
    """Fetch one nflreadpy table; cache to disk; return path.

    Skips fetch if cache is fresh (per --max-age-hours).
    """
    if name not in LOADERS:
        raise ValueError(f"Unknown nflreadpy table: {name}")

    suffix = f"_{season}" if name != "ff_playerids" else ""
    cache_path = CACHE_DIR / f"{name}{suffix}.parquet"

    if not is_stale(cache_path, max_age_hours):
        return cache_path

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = LOADERS[name](season)
    df.write_parquet(cache_path)
    return cache_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and cache nflreadpy data.")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=168,
        help="Re-fetch if cache older than N hours (default 168 = 7 days).",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=list(LOADERS.keys()),
        help="Which tables to fetch (default: all).",
    )
    args = parser.parse_args()

    for name in args.tables:
        path = fetch_one(name, season=args.season, max_age_hours=args.max_age_hours)
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
