#!/usr/bin/env python3
"""
Fetch all Sleeper fantasy football data for The Jailyard dynasty league.

Usage:
    python3 fetch_sleeper.py                    # Fetch 2025 season (default)
    python3 fetch_sleeper.py --season 2024      # Fetch a specific season
    python3 fetch_sleeper.py --all              # Fetch all seasons (2022-2025)

Data is saved to ./data/ as JSON files that the season.html page can consume.
No dependencies beyond the Python 3 standard library.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "https://api.sleeper.app/v1"
DATA_DIR = Path(__file__).parent / "data"

# League IDs by season (dynasty league carries over each year)
LEAGUE_IDS = {
    2022: "792314138780090368",
    2023: "918335334096846848",
    2024: "1048889097223266304",
    2025: "1180228858937966592",
    2026: "1312884727480352768",  # offseason — season begins end of 2026
}

# Regular season weeks (NFL 2021+ has 18 weeks, but fantasy typically uses 14-17)
# We'll detect the actual number from league settings
DEFAULT_REG_WEEKS = 14
PLAYOFF_WEEKS = 4  # Weeks after regular season


def fetch_json(endpoint, retries=3, delay=1):
    """Fetch JSON from the Sleeper API with retry logic."""
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JailyardDynasty/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if attempt < retries - 1:
                wait = delay * (2 ** attempt)
                print(f"  Retry {attempt + 1} after {wait}s: {e}")
                time.sleep(wait)
            else:
                print(f"  FAILED: {url} — {e}")
                return None


def fetch_players():
    """Fetch the full NFL players database (~5MB). Cached for the session."""
    cache_path = DATA_DIR / "players.json"
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 24:
            print("  Using cached players.json (< 24h old)")
            with open(cache_path) as f:
                return json.load(f)

    print("  Fetching full player database (this may take a moment)...")
    players = fetch_json("/players/nfl")
    if players:
        with open(cache_path, "w") as f:
            json.dump(players, f)
        print(f"  Saved {len(players)} players to {cache_path}")
    return players


def fetch_season(season, league_id):
    """Fetch all data for a single season and save to data/."""
    print(f"\n{'='*60}")
    print(f"Fetching {season} season (league {league_id})")
    print(f"{'='*60}")

    season_dir = DATA_DIR / str(season)
    season_dir.mkdir(parents=True, exist_ok=True)

    # 1. League info
    print("\n[1/6] League info...")
    league = fetch_json(f"/league/{league_id}")
    if not league:
        print("ERROR: Could not fetch league info. Aborting.")
        return
    with open(season_dir / "league.json", "w") as f:
        json.dump(league, f, indent=2)

    # Detect total weeks
    settings = league.get("settings", {})
    playoff_week_start = settings.get("playoff_week_start", DEFAULT_REG_WEEKS + 1)
    reg_season_weeks = playoff_week_start - 1
    total_weeks = reg_season_weeks + PLAYOFF_WEEKS
    print(f"  Regular season: {reg_season_weeks} weeks, playoffs start week {playoff_week_start}")

    # 2. Users
    print("\n[2/6] Users...")
    users = fetch_json(f"/league/{league_id}/users")
    if users:
        with open(season_dir / "users.json", "w") as f:
            json.dump(users, f, indent=2)
        print(f"  Found {len(users)} users")

    # 3. Rosters (final standings)
    print("\n[3/6] Rosters & standings...")
    rosters = fetch_json(f"/league/{league_id}/rosters")
    if rosters:
        with open(season_dir / "rosters.json", "w") as f:
            json.dump(rosters, f, indent=2)
        print(f"  Found {len(rosters)} rosters")

    # 4. Weekly matchups
    print(f"\n[4/6] Matchups (weeks 1-{total_weeks})...")
    all_matchups = {}
    for week in range(1, total_weeks + 1):
        matchups = fetch_json(f"/league/{league_id}/matchups/{week}")
        if matchups:
            all_matchups[str(week)] = matchups
            # Check if this week has data (points > 0 for at least one team)
            has_data = any(m.get("points", 0) > 0 for m in matchups)
            if not has_data:
                print(f"  Week {week}: no scores (season may not have reached this week)")
                break
            total_pts = sum(m.get("points", 0) for m in matchups)
            print(f"  Week {week}: {len(matchups)} entries, {total_pts:.1f} total points")
        else:
            print(f"  Week {week}: no data")
            break
        time.sleep(0.1)  # Be nice to the API

    with open(season_dir / "matchups.json", "w") as f:
        json.dump(all_matchups, f, indent=2)
    print(f"  Saved {len(all_matchups)} weeks of matchups")

    # 5. Playoff brackets
    print("\n[5/6] Playoff brackets...")
    winners = fetch_json(f"/league/{league_id}/winners_bracket")
    losers = fetch_json(f"/league/{league_id}/losers_bracket")
    brackets = {"winners": winners, "losers": losers}
    with open(season_dir / "brackets.json", "w") as f:
        json.dump(brackets, f, indent=2)

    # 6. Transactions (trades, waivers)
    print(f"\n[6/6] Transactions...")
    all_transactions = {}
    for week in range(1, len(all_matchups) + 1):
        txns = fetch_json(f"/league/{league_id}/transactions/{week}")
        if txns:
            all_transactions[str(week)] = txns
        time.sleep(0.1)
    with open(season_dir / "transactions.json", "w") as f:
        json.dump(all_transactions, f, indent=2)
    trades = sum(
        1 for wk in all_transactions.values()
        for t in wk if t.get("type") == "trade"
    )
    waivers = sum(
        1 for wk in all_transactions.values()
        for t in wk if t.get("type") in ("waiver", "free_agent")
    )
    print(f"  {trades} trades, {waivers} waiver/FA moves")

    # Build the combined data file for season.html
    print("\nBuilding combined season data...")
    build_season_data(season, season_dir, league, users, rosters, all_matchups)

    print(f"\nDone! Data saved to {season_dir}/")


def build_season_data(season, season_dir, league, users, rosters, all_matchups):
    """
    Build a single combined JSON file with everything the season.html page needs,
    including computed power rankings for each week.
    """
    # Load players for name resolution
    players_db = fetch_players()

    # Build roster_id -> user info mapping
    user_map = {}
    if users:
        for u in users:
            user_map[u["user_id"]] = {
                "username": u.get("display_name", "Unknown"),
                "team_name": u.get("metadata", {}).get("team_name", ""),
                "avatar": u.get("avatar", ""),
            }

    roster_map = {}
    if rosters:
        for r in rosters:
            owner_id = r.get("owner_id", "")
            user_info = user_map.get(owner_id, {})
            roster_map[r["roster_id"]] = {
                "roster_id": r["roster_id"],
                "owner_id": owner_id,
                "username": user_info.get("username", "Unknown"),
                "team_name": user_info.get("team_name", ""),
                "final_record": {
                    "wins": r.get("settings", {}).get("wins", 0),
                    "losses": r.get("settings", {}).get("losses", 0),
                    "ties": r.get("settings", {}).get("ties", 0),
                    "fpts": r.get("settings", {}).get("fpts", 0)
                        + r.get("settings", {}).get("fpts_decimal", 0) / 100,
                    "fpts_against": r.get("settings", {}).get("fpts_against", 0)
                        + r.get("settings", {}).get("fpts_against_decimal", 0) / 100,
                },
            }

    def player_name(pid):
        if not players_db or pid not in players_db:
            return pid
        p = players_db[pid]
        return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()

    def player_info(pid):
        if not players_db or pid not in players_db:
            return {"name": pid, "position": "?", "team": "?"}
        p = players_db[pid]
        return {
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "position": p.get("position", "?"),
            "team": p.get("team", "?"),
        }

    # Process weekly data
    weekly_data = []
    cumulative_records = {rid: {"wins": 0, "losses": 0, "ties": 0, "pf": 0, "pa": 0}
                         for rid in roster_map}
    cumulative_points_history = {rid: [] for rid in roster_map}

    settings = league.get("settings", {})
    playoff_week_start = settings.get("playoff_week_start", DEFAULT_REG_WEEKS + 1)

    for week_num in sorted(all_matchups.keys(), key=int):
        week = int(week_num)
        matchups_raw = all_matchups[week_num]
        is_playoff = week >= playoff_week_start

        # Group by matchup_id
        matchup_groups = {}
        for m in matchups_raw:
            mid = m.get("matchup_id")
            if mid is None:
                continue
            matchup_groups.setdefault(mid, []).append(m)

        # Build matchup results
        matchup_results = []
        week_scores = {}
        week_top_players = []

        for mid, teams in matchup_groups.items():
            if len(teams) != 2:
                continue
            t1, t2 = teams
            r1, r2 = t1["roster_id"], t2["roster_id"]
            p1, p2 = t1.get("points", 0) or 0, t2.get("points", 0) or 0

            week_scores[r1] = p1
            week_scores[r2] = p2

            # Determine winner
            if p1 > p2:
                winner = r1
            elif p2 > p1:
                winner = r2
            else:
                winner = None  # tie

            # Top starters for each team
            def top_starters(team_entry):
                starters = team_entry.get("starters", [])
                starter_pts = team_entry.get("starters_points", [])
                result = []
                for i, pid in enumerate(starters):
                    pts = starter_pts[i] if i < len(starter_pts) else 0
                    info = player_info(pid)
                    result.append({"pid": pid, **info, "points": pts})
                result.sort(key=lambda x: x["points"], reverse=True)
                return result

            matchup_results.append({
                "matchup_id": mid,
                "team1": {
                    "roster_id": r1,
                    "points": p1,
                    "top_starters": top_starters(t1)[:5],
                },
                "team2": {
                    "roster_id": r2,
                    "points": p2,
                    "top_starters": top_starters(t2)[:5],
                },
                "winner": winner,
            })

            # Collect all starters for top performers
            for team_entry in [t1, t2]:
                starters = team_entry.get("starters", [])
                starter_pts = team_entry.get("starters_points", [])
                for i, pid in enumerate(starters):
                    pts = starter_pts[i] if i < len(starter_pts) else 0
                    if pts > 0:
                        info = player_info(pid)
                        week_top_players.append({
                            "pid": pid, **info, "points": pts,
                            "roster_id": team_entry["roster_id"]
                        })

        # Update cumulative records (regular season only)
        if not is_playoff:
            for mid, teams in matchup_groups.items():
                if len(teams) != 2:
                    continue
                t1, t2 = teams
                r1, r2 = t1["roster_id"], t2["roster_id"]
                p1, p2 = t1.get("points", 0) or 0, t2.get("points", 0) or 0
                if r1 in cumulative_records:
                    cumulative_records[r1]["pf"] += p1
                    cumulative_records[r1]["pa"] += p2
                if r2 in cumulative_records:
                    cumulative_records[r2]["pf"] += p2
                    cumulative_records[r2]["pa"] += p1
                if p1 > p2:
                    if r1 in cumulative_records:
                        cumulative_records[r1]["wins"] += 1
                    if r2 in cumulative_records:
                        cumulative_records[r2]["losses"] += 1
                elif p2 > p1:
                    if r2 in cumulative_records:
                        cumulative_records[r2]["wins"] += 1
                    if r1 in cumulative_records:
                        cumulative_records[r1]["losses"] += 1
                else:
                    if r1 in cumulative_records:
                        cumulative_records[r1]["ties"] += 1
                    if r2 in cumulative_records:
                        cumulative_records[r2]["ties"] += 1

        # Track point history
        for rid in roster_map:
            pts = week_scores.get(rid, 0)
            cumulative_points_history[rid].append(pts)

        # Sort top players
        week_top_players.sort(key=lambda x: x["points"], reverse=True)

        # Compute power rankings for this week
        # Formula: 40% win pct + 30% points for (normalized) + 20% recent form (last 3) + 10% strength of schedule
        standings = []
        for rid, rec in cumulative_records.items():
            total_games = rec["wins"] + rec["losses"] + rec["ties"]
            win_pct = (rec["wins"] + 0.5 * rec["ties"]) / max(total_games, 1)

            # Points for (normalized to league average)
            avg_pf = sum(r["pf"] for r in cumulative_records.values()) / max(len(cumulative_records), 1)
            pf_factor = rec["pf"] / max(avg_pf, 1)

            # Recent form (last 3 weeks' points)
            recent = cumulative_points_history.get(rid, [])[-3:]
            recent_avg = sum(recent) / max(len(recent), 1)
            league_recent_avg = sum(
                sum(cumulative_points_history.get(r, [])[-3:]) / max(len(cumulative_points_history.get(r, [])[-3:]), 1)
                for r in roster_map
            ) / max(len(roster_map), 1)
            recent_factor = recent_avg / max(league_recent_avg, 1)

            # Strength of schedule (points against normalized)
            avg_pa = sum(r["pa"] for r in cumulative_records.values()) / max(len(cumulative_records), 1)
            sos_factor = rec["pa"] / max(avg_pa, 1)

            power_score = (0.40 * win_pct + 0.30 * pf_factor + 0.20 * recent_factor + 0.10 * sos_factor)

            standings.append({
                "roster_id": rid,
                **rec,
                "power_score": round(power_score, 4),
                "week_points": week_scores.get(rid, 0),
            })

        # Sort by power score descending
        standings.sort(key=lambda x: x["power_score"], reverse=True)
        for i, s in enumerate(standings):
            s["power_rank"] = i + 1

        weekly_data.append({
            "week": week,
            "is_playoff": is_playoff,
            "matchups": matchup_results,
            "standings": standings,
            "top_performers": week_top_players[:10],
            "bottom_performers": week_top_players[-3:] if len(week_top_players) >= 3 else [],
            "highest_scorer": {
                "roster_id": max(week_scores, key=week_scores.get) if week_scores else None,
                "points": max(week_scores.values()) if week_scores else 0,
            },
            "lowest_scorer": {
                "roster_id": min(week_scores, key=week_scores.get) if week_scores else None,
                "points": min(week_scores.values()) if week_scores else 0,
            },
        })

    # Build the final combined output
    combined = {
        "season": season,
        "league_id": LEAGUE_IDS.get(season, ""),
        "league_name": league.get("name", "The Jailyard"),
        "total_rosters": league.get("total_rosters", 12),
        "playoff_week_start": playoff_week_start,
        "roster_map": {str(k): v for k, v in roster_map.items()},
        "weeks": weekly_data,
    }

    out_path = season_dir / "season_combined.json"
    with open(out_path, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"  Combined data saved to {out_path} ({os.path.getsize(out_path) / 1024:.0f} KB)")


def main():
    DATA_DIR.mkdir(exist_ok=True)

    args = sys.argv[1:]

    if "--all" in args:
        seasons = sorted(LEAGUE_IDS.keys())
    elif "--season" in args:
        idx = args.index("--season")
        if idx + 1 < len(args):
            s = int(args[idx + 1])
            if s not in LEAGUE_IDS:
                print(f"Unknown season {s}. Available: {list(LEAGUE_IDS.keys())}")
                sys.exit(1)
            seasons = [s]
        else:
            print("--season requires a year argument")
            sys.exit(1)
    else:
        seasons = [2025]

    # Fetch players database first (shared across seasons)
    print("Fetching player database...")
    fetch_players()

    for season in seasons:
        fetch_season(season, LEAGUE_IDS[season])

    print(f"\n{'='*60}")
    print("All done! Data is ready in ./data/")
    print("Open season.html in a browser to view the results.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
