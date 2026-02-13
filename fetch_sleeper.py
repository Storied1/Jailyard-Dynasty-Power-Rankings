#!/usr/bin/env python3
"""
Fetch all Sleeper fantasy football data for The Jailyard dynasty league.

Usage:
    python3 fetch_sleeper.py                    # Fetch current season only
    python3 fetch_sleeper.py --season 2024      # Fetch a specific season
    python3 fetch_sleeper.py --all              # Fetch all seasons (skips cached)
    python3 fetch_sleeper.py --all --force      # Re-fetch everything, ignore cache

Past seasons are immutable — once cached, they are skipped automatically.
Use --force to override this and re-fetch from the API.

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

    # 7. Player projections (for projected matchup scores)
    print(f"\n[7/8] Projections (weeks 1-{len(all_matchups)})...")
    all_projections = {}
    for week in range(1, len(all_matchups) + 1):
        season_type = "regular"
        if week >= playoff_week_start:
            season_type = "post"
        proj_url = f"https://api.sleeper.app/projections/nfl/{season}/{week}?season_type={season_type}"
        try:
            req = urllib.request.Request(proj_url, headers={"User-Agent": "JailyardDynasty/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                proj_data = json.loads(resp.read().decode())
                if proj_data:
                    all_projections[str(week)] = proj_data
                    print(f"  Week {week}: {len(proj_data)} player projections")
                else:
                    print(f"  Week {week}: no projections available")
        except Exception as e:
            print(f"  Week {week}: projections unavailable ({e})")
        time.sleep(0.1)
    if all_projections:
        with open(season_dir / "projections.json", "w") as f:
            json.dump(all_projections, f)
        print(f"  Saved projections for {len(all_projections)} weeks")
    else:
        print("  No projections data available (may be an older season)")

    # Build the combined data file for season.html
    print("\nBuilding combined season data...")
    build_season_data(season, season_dir, league, users, rosters, all_matchups,
                      brackets=brackets, projections=all_projections)

    print(f"\nDone! Data saved to {season_dir}/")


def build_season_data(season, season_dir, league, users, rosters, all_matchups,
                      brackets=None, projections=None):
    """
    Build a single combined JSON file with everything the season.html page needs,
    including computed power rankings for each week, projected scores, and bracket data.
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

        # Get projections for this week (if available)
        week_proj = {}
        if projections and str(week) in projections:
            for pid, pdata in projections[str(week)].items():
                if isinstance(pdata, dict):
                    # Sleeper projections use pts_ppr or pts_half_ppr or a generic pts field
                    proj_pts = pdata.get("pts_ppr", pdata.get("pts_half_ppr", pdata.get("pts_std", 0)))
                    if proj_pts:
                        week_proj[pid] = proj_pts

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
                    proj = week_proj.get(pid, 0)
                    result.append({"pid": pid, **info, "points": pts, "projected": round(proj, 2)})
                result.sort(key=lambda x: x["points"], reverse=True)
                return result

            # Compute projected totals from starters
            def proj_total(team_entry):
                starters = team_entry.get("starters", [])
                return round(sum(week_proj.get(pid, 0) for pid in starters), 2)

            matchup_results.append({
                "matchup_id": mid,
                "team1": {
                    "roster_id": r1,
                    "points": p1,
                    "projected": proj_total(t1),
                    "top_starters": top_starters(t1)[:5],
                },
                "team2": {
                    "roster_id": r2,
                    "points": p2,
                    "projected": proj_total(t2),
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
        "brackets": {
            "winners": brackets.get("winners") if brackets else None,
            "losers": brackets.get("losers") if brackets else None,
        },
        "has_projections": bool(projections),
    }

    out_path = season_dir / "season_combined.json"
    with open(out_path, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"  Combined data saved to {out_path} ({os.path.getsize(out_path) / 1024:.0f} KB)")


def is_season_cached(season):
    """Check if a season already has a complete cached dataset."""
    combined = DATA_DIR / str(season) / "season_combined.json"
    return combined.exists() and combined.stat().st_size > 100


def main():
    DATA_DIR.mkdir(exist_ok=True)

    args = sys.argv[1:]
    force = "--force" in args

    # Determine which season(s) are the current/active ones
    # (these always get re-fetched because data may have changed)
    current_year = max(LEAGUE_IDS.keys())

    if "--all" in args:
        requested = sorted(LEAGUE_IDS.keys())
    elif "--season" in args:
        idx = args.index("--season")
        if idx + 1 < len(args):
            s = int(args[idx + 1])
            if s not in LEAGUE_IDS:
                print(f"Unknown season {s}. Available: {list(LEAGUE_IDS.keys())}")
                sys.exit(1)
            requested = [s]
        else:
            print("--season requires a year argument")
            sys.exit(1)
    else:
        requested = [current_year]

    # Filter out already-cached past seasons (unless --force)
    seasons = []
    for s in requested:
        if not force and s < current_year and is_season_cached(s):
            print(f"  Skipping {s} — already cached (use --force to re-fetch)")
        else:
            seasons.append(s)

    if not seasons:
        print("All requested seasons are already cached. Nothing to fetch.")
        print("Use --force to re-fetch from the API.")
        # Still rebuild history if we have multiple seasons of cached data
        if len(requested) > 1:
            print("\nRebuilding cross-season league history from cache...")
            build_league_history(requested)
        return

    # Fetch players database first (shared across seasons)
    print("Fetching player database...")
    fetch_players()

    for season in seasons:
        fetch_season(season, LEAGUE_IDS[season])

    print(f"\n{'='*60}")
    print("All done! Data is ready in ./data/")
    print("Open season.html in a browser to view the results.")
    print(f"{'='*60}")

    # If fetching all seasons, also build the cross-season history
    # Use the full requested list so cached seasons are included
    if len(requested) > 1:
        print("\nBuilding cross-season league history...")
        build_league_history(requested)


def build_league_history(seasons):
    """
    Build a comprehensive cross-season dataset for history.html.
    Computes: Elo ratings, all-time records, H2H rivalry matrix,
    franchise career stats, and record book entries.
    """
    # Load each season's combined data
    all_seasons = {}
    for s in seasons:
        path = DATA_DIR / str(s) / "season_combined.json"
        if path.exists():
            with open(path) as f:
                all_seasons[s] = json.load(f)
            print(f"  Loaded {s} season data")
        else:
            print(f"  WARNING: No data for {s}, skipping")

    if not all_seasons:
        print("  No season data found. Run fetch for individual seasons first.")
        return

    # ---------------------------------------------------------------
    # 1. Identify franchises across seasons using owner_id
    # ---------------------------------------------------------------
    franchise_map = {}  # owner_id -> {username, team_name, seasons}
    for s, data in sorted(all_seasons.items()):
        for rid_str, info in data.get("roster_map", {}).items():
            oid = info.get("owner_id", "")
            if oid not in franchise_map:
                franchise_map[oid] = {
                    "owner_id": oid,
                    "username": info.get("username", "Unknown"),
                    "team_name": info.get("team_name", ""),
                    "seasons": {},
                }
            franchise_map[oid]["seasons"][s] = int(rid_str)
            # Update display name to latest
            if info.get("username"):
                franchise_map[oid]["username"] = info["username"]
            if info.get("team_name"):
                franchise_map[oid]["team_name"] = info["team_name"]

    print(f"  Identified {len(franchise_map)} franchises across {len(all_seasons)} seasons")

    # ---------------------------------------------------------------
    # 2. Gather all matchups across all seasons
    # ---------------------------------------------------------------
    all_games = []  # [{season, week, r1_owner, r2_owner, p1, p2, winner_owner, is_playoff}]
    for s, data in sorted(all_seasons.items()):
        rid_to_owner = {}
        for rid_str, info in data.get("roster_map", {}).items():
            rid_to_owner[int(rid_str)] = info.get("owner_id", "")

        for week_data in data.get("weeks", []):
            week = week_data["week"]
            is_playoff = week_data.get("is_playoff", False)
            for m in week_data.get("matchups", []):
                r1 = m["team1"]["roster_id"]
                r2 = m["team2"]["roster_id"]
                p1 = m["team1"]["points"]
                p2 = m["team2"]["points"]
                o1 = rid_to_owner.get(r1, "")
                o2 = rid_to_owner.get(r2, "")
                w = m.get("winner")
                winner_owner = rid_to_owner.get(w, "") if w else None

                all_games.append({
                    "season": s, "week": week,
                    "o1": o1, "o2": o2,
                    "p1": p1, "p2": p2,
                    "winner_owner": winner_owner,
                    "is_playoff": is_playoff,
                })

    print(f"  Processed {len(all_games)} total matchups")

    # ---------------------------------------------------------------
    # 3. Elo Rating System
    # ---------------------------------------------------------------
    K = 32
    MEAN_REGRESSION = 0.15  # Regress 15% toward 1500 between seasons

    elo = {oid: 1500.0 for oid in franchise_map}
    elo_history = {oid: [] for oid in franchise_map}
    prev_season = None

    for game in all_games:
        # Regress toward mean between seasons
        if prev_season is not None and game["season"] != prev_season:
            for oid in elo:
                elo[oid] = elo[oid] + MEAN_REGRESSION * (1500 - elo[oid])
        prev_season = game["season"]

        o1, o2 = game["o1"], game["o2"]
        if not o1 or not o2 or o1 not in elo or o2 not in elo:
            continue

        # Expected scores
        e1 = 1 / (1 + 10 ** ((elo[o2] - elo[o1]) / 400))
        e2 = 1 - e1

        # Actual scores (margin-weighted: bigger wins move Elo more)
        margin = abs(game["p1"] - game["p2"])
        margin_mult = max(1, (margin / 20) ** 0.5)  # sqrt scaling
        k_adj = K * margin_mult

        if game["winner_owner"] == o1:
            s1, s2 = 1, 0
        elif game["winner_owner"] == o2:
            s1, s2 = 0, 1
        else:
            s1, s2 = 0.5, 0.5

        elo[o1] += k_adj * (s1 - e1)
        elo[o2] += k_adj * (s2 - e2)

        elo_history[o1].append({
            "season": game["season"], "week": game["week"],
            "elo": round(elo[o1], 1),
        })
        elo_history[o2].append({
            "season": game["season"], "week": game["week"],
            "elo": round(elo[o2], 1),
        })

    print(f"  Elo ratings computed (top: {max(elo.values()):.0f}, bottom: {min(elo.values()):.0f})")

    # ---------------------------------------------------------------
    # 4. Head-to-Head Rivalry Matrix
    # ---------------------------------------------------------------
    h2h = {}  # (o1, o2) -> {wins, losses, pf, pa, games: [{season, week, p1, p2}]}
    for game in all_games:
        o1, o2 = game["o1"], game["o2"]
        if not o1 or not o2:
            continue
        # Store BOTH directions so every matrix cell is populated
        for a, b, pa_, pb_ in [(o1, o2, game["p1"], game["p2"]),
                                (o2, o1, game["p2"], game["p1"])]:
            key = (a, b)
            if key not in h2h:
                h2h[key] = {"wins": 0, "losses": 0, "pf": 0, "pa": 0, "games": []}
            h2h[key]["pf"] += pa_
            h2h[key]["pa"] += pb_
            h2h[key]["games"].append({
                "season": game["season"], "week": game["week"],
                "pts": pa_, "opp_pts": pb_,
            })
            if game["winner_owner"] == a:
                h2h[key]["wins"] += 1
            elif game["winner_owner"] == b:
                h2h[key]["losses"] += 1

    # Convert to serializable format
    h2h_serial = {}
    for (o1, o2), data in h2h.items():
        h2h_serial[f"{o1}|{o2}"] = data

    # ---------------------------------------------------------------
    # 5. All-Time Records Book
    # ---------------------------------------------------------------
    records = {
        "highest_score": {"points": 0},
        "lowest_winning_score": {"points": 99999},
        "biggest_blowout": {"margin": 0},
        "highest_combined": {"points": 0},
        "lowest_combined": {"points": 99999},
    }

    # Streak tracking
    streaks = {oid: {"current_w": 0, "current_l": 0, "best_w": 0, "best_l": 0}
               for oid in franchise_map}

    for game in all_games:
        o1, o2 = game["o1"], game["o2"]
        p1, p2 = game["p1"], game["p2"]
        if not o1 or not o2:
            continue

        combined = p1 + p2
        margin = abs(p1 - p2)
        f1 = franchise_map.get(o1, {})
        f2 = franchise_map.get(o2, {})
        name1 = f1.get("team_name") or f1.get("username", "?")
        name2 = f2.get("team_name") or f2.get("username", "?")

        # Highest single-week score
        for pts, name, opp_name, oid in [(p1, name1, name2, o1), (p2, name2, name1, o2)]:
            if pts > records["highest_score"]["points"]:
                records["highest_score"] = {
                    "points": pts, "team": name, "opponent": opp_name,
                    "season": game["season"], "week": game["week"], "owner_id": oid,
                }

        # Lowest winning score
        if p1 != p2:
            winner_pts = max(p1, p2)
            winner_name = name1 if p1 > p2 else name2
            loser_name = name2 if p1 > p2 else name1
            winner_oid = o1 if p1 > p2 else o2
            if winner_pts < records["lowest_winning_score"]["points"]:
                records["lowest_winning_score"] = {
                    "points": winner_pts, "team": winner_name, "opponent": loser_name,
                    "season": game["season"], "week": game["week"], "owner_id": winner_oid,
                }

        # Biggest blowout
        if margin > records["biggest_blowout"]["margin"]:
            records["biggest_blowout"] = {
                "margin": round(margin, 2), "winner": name1 if p1 > p2 else name2,
                "loser": name2 if p1 > p2 else name1,
                "score": f"{max(p1,p2):.1f}-{min(p1,p2):.1f}",
                "season": game["season"], "week": game["week"],
            }

        # Combined scores
        if combined > records["highest_combined"]["points"]:
            records["highest_combined"] = {
                "points": round(combined, 2), "teams": f"{name1} vs {name2}",
                "score": f"{p1:.1f}-{p2:.1f}",
                "season": game["season"], "week": game["week"],
            }
        if combined < records["lowest_combined"]["points"] and combined > 0:
            records["lowest_combined"] = {
                "points": round(combined, 2), "teams": f"{name1} vs {name2}",
                "score": f"{p1:.1f}-{p2:.1f}",
                "season": game["season"], "week": game["week"],
            }

        # Win/loss streaks
        if not game["is_playoff"]:
            for oid in [o1, o2]:
                if oid not in streaks:
                    continue
                won = game["winner_owner"] == oid
                if won:
                    streaks[oid]["current_w"] += 1
                    streaks[oid]["current_l"] = 0
                    streaks[oid]["best_w"] = max(streaks[oid]["best_w"], streaks[oid]["current_w"])
                else:
                    streaks[oid]["current_l"] += 1
                    streaks[oid]["current_w"] = 0
                    streaks[oid]["best_l"] = max(streaks[oid]["best_l"], streaks[oid]["current_l"])

    # Find longest streaks
    best_win_streak = max(streaks.values(), key=lambda x: x["best_w"])
    best_win_oid = [oid for oid, s in streaks.items() if s["best_w"] == best_win_streak["best_w"]][0]
    f = franchise_map.get(best_win_oid, {})
    records["longest_win_streak"] = {
        "count": best_win_streak["best_w"],
        "team": f.get("team_name") or f.get("username", "?"),
        "owner_id": best_win_oid,
    }

    best_loss_streak = max(streaks.values(), key=lambda x: x["best_l"])
    best_loss_oid = [oid for oid, s in streaks.items() if s["best_l"] == best_loss_streak["best_l"]][0]
    f = franchise_map.get(best_loss_oid, {})
    records["longest_losing_streak"] = {
        "count": best_loss_streak["best_l"],
        "team": f.get("team_name") or f.get("username", "?"),
        "owner_id": best_loss_oid,
    }

    # ---------------------------------------------------------------
    # 6. Franchise Career Stats
    # ---------------------------------------------------------------
    franchise_stats = {}
    for oid, info in franchise_map.items():
        stats = {
            "owner_id": oid,
            "username": info["username"],
            "team_name": info.get("team_name", ""),
            "seasons_played": len(info["seasons"]),
            "all_time": {"wins": 0, "losses": 0, "ties": 0, "pf": 0, "pa": 0},
            "playoff_appearances": 0,
            "championships": 0,
            "finals": 0,
            "season_results": [],
            "current_elo": round(elo.get(oid, 1500), 1),
            "peak_elo": 0,
            "best_win_streak": streaks.get(oid, {}).get("best_w", 0),
        }

        # Peak Elo
        if oid in elo_history:
            stats["peak_elo"] = max((e["elo"] for e in elo_history[oid]), default=1500)

        # Per-season results
        for s, data in sorted(all_seasons.items()):
            rid_str = str(info["seasons"].get(s, ""))
            if rid_str in data.get("roster_map", {}):
                r = data["roster_map"][rid_str]
                rec = r.get("final_record", {})
                w, l, t = rec.get("wins", 0), rec.get("losses", 0), rec.get("ties", 0)
                pf = rec.get("fpts", 0)
                pa = rec.get("fpts_against", 0)

                stats["all_time"]["wins"] += w
                stats["all_time"]["losses"] += l
                stats["all_time"]["ties"] += t
                stats["all_time"]["pf"] += pf
                stats["all_time"]["pa"] += pa

                stats["season_results"].append({
                    "season": s, "wins": w, "losses": l, "ties": t,
                    "pf": round(pf, 1), "pa": round(pa, 1),
                })

        stats["all_time"]["pf"] = round(stats["all_time"]["pf"], 1)
        stats["all_time"]["pa"] = round(stats["all_time"]["pa"], 1)
        franchise_stats[oid] = stats

    # Detect championships and finals from bracket data
    for s, data in sorted(all_seasons.items()):
        brackets_path = DATA_DIR / str(s) / "brackets.json"
        if brackets_path.exists():
            with open(brackets_path) as f:
                brackets = json.load(f)
            winners = brackets.get("winners", [])
            if winners:
                # Find the championship game (highest round)
                max_round = max((g.get("r", 0) for g in winners), default=0)
                for game in winners:
                    if game.get("r") == max_round:
                        rid_to_owner = {}
                        for rid_str, info in all_seasons[s].get("roster_map", {}).items():
                            rid_to_owner[int(rid_str)] = info.get("owner_id", "")
                        champ_rid = game.get("w")
                        r1 = game.get("t1")
                        r2 = game.get("t2")
                        for rid in [r1, r2]:
                            oid = rid_to_owner.get(rid, "")
                            if oid in franchise_stats:
                                franchise_stats[oid]["finals"] += 1
                        champ_oid = rid_to_owner.get(champ_rid, "")
                        if champ_oid in franchise_stats:
                            franchise_stats[champ_oid]["championships"] += 1

    # ---------------------------------------------------------------
    # 7. Build final output
    # ---------------------------------------------------------------
    history = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seasons": list(all_seasons.keys()),
        "total_games": len(all_games),
        "franchise_map": {oid: {"username": f["username"], "team_name": f.get("team_name", "")}
                          for oid, f in franchise_map.items()},
        "records": records,
        "elo_current": {oid: round(e, 1) for oid, e in elo.items()},
        "elo_history": elo_history,
        "h2h": h2h_serial,
        "franchise_stats": franchise_stats,
    }

    out_path = DATA_DIR / "league_history.json"
    with open(out_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"  League history saved to {out_path} ({os.path.getsize(out_path) / 1024:.0f} KB)")
    print(f"  Open history.html in a browser to explore.")


if __name__ == "__main__":
    main()
