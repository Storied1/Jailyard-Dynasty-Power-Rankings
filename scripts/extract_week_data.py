#!/usr/bin/env python3
"""
Extract clean, AI-ready JSON for a specific week from season_combined.json.

Usage:
    python scripts/extract_week_data.py --week 1
    python scripts/extract_week_data.py --week 1 --season 2025
    python scripts/extract_week_data.py --all                   # Extract all weeks
    python scripts/extract_week_data.py --week 1 --pretty       # Pretty-print output

Output is saved to content/weeks/week{N}_data.json
"""

import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "content" / "weeks"
TEAM_PROFILES = PROJECT_DIR / "content" / "team-profiles.json"


def load_season_data(season=2025):
    """Load the combined season data file."""
    path = DATA_DIR / str(season) / "season_combined.json"
    if not path.exists():
        print(f"ERROR: {path} not found. Run fetch_sleeper.py --season {season} first.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_team_profiles():
    """Load team profiles for preseason context."""
    if TEAM_PROFILES.exists():
        with open(TEAM_PROFILES) as f:
            return json.load(f)
    return None


def build_roster_lookup(data):
    """Build roster_id -> team info lookup from roster_map."""
    lookup = {}
    for rid_str, info in data["roster_map"].items():
        rid = int(rid_str)
        lookup[rid] = {
            "roster_id": rid,
            "owner": info.get("username", "Unknown"),
            "team_name": info.get("team_name", ""),
            "owner_id": info.get("owner_id", ""),
            "final_record": info.get("final_record", {}),
        }
    return lookup


def extract_week(data, week_num, roster_lookup, team_profiles=None, prev_weeks=None):
    """
    Extract all AI-ready data for a single week.

    Returns a dict with:
    - meta: week number, season context
    - matchups: detailed matchup results with team names, scores, top scorers
    - standings: full standings with movement tracking
    - awards: weekly superlatives
    - previous_rankings: last week's power rankings (for movement arrows)
    - next_matchups: next week's scheduled matchups (if available)
    - season_context: running stats, streaks, trends
    - team_profiles_summary: condensed preseason context per team
    """
    weeks = data["weeks"]
    week_idx = None
    for i, w in enumerate(weeks):
        if w["week"] == week_num:
            week_idx = i
            break

    if week_idx is None:
        print(f"ERROR: Week {week_num} not found in data.")
        return None

    week_data = weeks[week_idx]

    # Previous week data (for movement tracking)
    prev_week_data = weeks[week_idx - 1] if week_idx > 0 else None
    prev_rankings = {}
    if prev_week_data:
        for s in prev_week_data["standings"]:
            prev_rankings[s["roster_id"]] = s["power_rank"]

    # Next week data (for upcoming matchup preview)
    next_week_data = weeks[week_idx + 1] if week_idx + 1 < len(weeks) else None

    # --- Matchups ---
    matchups = []
    all_scores = {}
    for m in week_data["matchups"]:
        t1 = m["team1"]
        t2 = m["team2"]
        r1_info = roster_lookup.get(t1["roster_id"], {})
        r2_info = roster_lookup.get(t2["roster_id"], {})

        all_scores[t1["roster_id"]] = t1["points"]
        all_scores[t2["roster_id"]] = t2["points"]

        margin = abs(t1["points"] - t2["points"])
        winner_rid = m.get("winner")

        matchup_entry = {
            "matchup_id": m["matchup_id"],
            "team1": {
                "roster_id": t1["roster_id"],
                "team_name": r1_info.get("team_name", "?"),
                "owner": r1_info.get("owner", "?"),
                "points": t1["points"],
                "projected": t1.get("projected", 0),
                "top_scorers": [
                    {"name": p["name"], "position": p["position"], "team": p["team"], "points": p["points"]}
                    for p in t1.get("top_starters", [])[:5]
                ],
            },
            "team2": {
                "roster_id": t2["roster_id"],
                "team_name": r2_info.get("team_name", "?"),
                "owner": r2_info.get("owner", "?"),
                "points": t2["points"],
                "projected": t2.get("projected", 0),
                "top_scorers": [
                    {"name": p["name"], "position": p["position"], "team": p["team"], "points": p["points"]}
                    for p in t2.get("top_starters", [])[:5]
                ],
            },
            "winner": roster_lookup.get(winner_rid, {}).get("team_name", None) if winner_rid else "Tie",
            "margin": round(margin, 2),
            "upset": (
                winner_rid is not None
                and prev_rankings.get(winner_rid, 99) > prev_rankings.get(
                    t1["roster_id"] if winner_rid == t2["roster_id"] else t2["roster_id"], 0
                )
            ),
        }
        matchups.append(matchup_entry)

    # Sort matchups by closest margin first (for narrative interest)
    matchups.sort(key=lambda x: x["margin"])

    # --- Standings ---
    standings = []
    for s in week_data["standings"]:
        rid = s["roster_id"]
        info = roster_lookup.get(rid, {})
        prev_rank = prev_rankings.get(rid, None)
        current_rank = s["power_rank"]

        if prev_rank is not None:
            movement = prev_rank - current_rank  # positive = moved up
        else:
            movement = 0

        # Compute streak from previous weeks
        streak = compute_streak(data, week_num, rid, roster_lookup)

        standings.append({
            "rank": current_rank,
            "prev_rank": prev_rank,
            "movement": movement,
            "team_name": info.get("team_name", "?"),
            "owner": info.get("owner", "?"),
            "record": f"{s['wins']}-{s['losses']}" + (f"-{s['ties']}" if s.get("ties", 0) > 0 else ""),
            "wins": s["wins"],
            "losses": s["losses"],
            "pf": round(s["pf"], 1),
            "pa": round(s.get("pa", 0), 1),
            "power_score": s["power_score"],
            "week_points": s["week_points"],
            "streak": streak,
        })

    standings.sort(key=lambda x: x["rank"])

    # --- Weekly Awards ---
    scores_by_team = {
        roster_lookup.get(rid, {}).get("team_name", "?"): pts
        for rid, pts in all_scores.items()
    }

    high_scorer_rid = week_data["highest_scorer"]["roster_id"]
    low_scorer_rid = week_data["lowest_scorer"]["roster_id"]

    # Find closest and biggest blowout matchups
    closest_matchup = min(matchups, key=lambda m: m["margin"]) if matchups else None
    biggest_blowout = max(matchups, key=lambda m: m["margin"]) if matchups else None

    # Top individual performer
    top_performer = week_data["top_performers"][0] if week_data.get("top_performers") else None

    awards = {
        "high_scorer": {
            "team_name": roster_lookup.get(high_scorer_rid, {}).get("team_name", "?"),
            "owner": roster_lookup.get(high_scorer_rid, {}).get("owner", "?"),
            "points": week_data["highest_scorer"]["points"],
        },
        "low_scorer": {
            "team_name": roster_lookup.get(low_scorer_rid, {}).get("team_name", "?"),
            "owner": roster_lookup.get(low_scorer_rid, {}).get("owner", "?"),
            "points": week_data["lowest_scorer"]["points"],
        },
        "closest_game": {
            "teams": f"{closest_matchup['team1']['team_name']} vs {closest_matchup['team2']['team_name']}",
            "score": f"{max(closest_matchup['team1']['points'], closest_matchup['team2']['points']):.1f}-{min(closest_matchup['team1']['points'], closest_matchup['team2']['points']):.1f}",
            "margin": closest_matchup["margin"],
        } if closest_matchup else None,
        "biggest_blowout": {
            "winner": biggest_blowout["winner"],
            "teams": f"{biggest_blowout['team1']['team_name']} vs {biggest_blowout['team2']['team_name']}",
            "score": f"{max(biggest_blowout['team1']['points'], biggest_blowout['team2']['points']):.1f}-{min(biggest_blowout['team1']['points'], biggest_blowout['team2']['points']):.1f}",
            "margin": biggest_blowout["margin"],
        } if biggest_blowout else None,
        "top_performer": {
            "name": top_performer["name"],
            "position": top_performer["position"],
            "nfl_team": top_performer["team"],
            "points": top_performer["points"],
            "fantasy_team": roster_lookup.get(top_performer.get("roster_id"), {}).get("team_name", "?"),
        } if top_performer else None,
    }

    # --- Season Context ---
    total_weeks_played = week_num
    all_weekly_totals = []
    for w in weeks[:week_idx + 1]:
        week_total = sum(s["week_points"] for s in w["standings"])
        all_weekly_totals.append(week_total / data["total_rosters"])

    season_avg_ppg = sum(all_weekly_totals) / len(all_weekly_totals) if all_weekly_totals else 0

    # Standings leaders/trailers
    best_record = standings[0]
    worst_record = standings[-1]

    # Points leader
    pf_leader = max(standings, key=lambda x: x["pf"])

    season_context = {
        "weeks_played": total_weeks_played,
        "total_weeks": data.get("playoff_week_start", 15) - 1,
        "is_playoff": week_data.get("is_playoff", False),
        "league_avg_ppg": round(season_avg_ppg, 1),
        "this_week_avg": round(sum(all_scores.values()) / max(len(all_scores), 1), 1),
        "best_record": {
            "team_name": best_record["team_name"],
            "record": best_record["record"],
        },
        "worst_record": {
            "team_name": worst_record["team_name"],
            "record": worst_record["record"],
        },
        "points_leader": {
            "team_name": pf_leader["team_name"],
            "pf": pf_leader["pf"],
        },
    }

    # --- Next Week Matchups ---
    next_matchups = []
    if next_week_data:
        for m in next_week_data["matchups"]:
            r1_info = roster_lookup.get(m["team1"]["roster_id"], {})
            r2_info = roster_lookup.get(m["team2"]["roster_id"], {})
            # Find current ranks for each team
            r1_rank = next((s["rank"] for s in standings if s["team_name"] == r1_info.get("team_name")), "?")
            r2_rank = next((s["rank"] for s in standings if s["team_name"] == r2_info.get("team_name")), "?")
            next_matchups.append({
                "team1": r1_info.get("team_name", "?"),
                "team1_rank": r1_rank,
                "team2": r2_info.get("team_name", "?"),
                "team2_rank": r2_rank,
            })

    # --- Team Profiles Summary (for callbacks) ---
    profiles_summary = {}
    if team_profiles:
        for team in team_profiles.get("teams", []):
            profiles_summary[team["name"]] = {
                "preseason_rank": team["rank"],
                "tier": team["tier"],
                "roast": team["roast"],
                "needs": team["needs"],
                "weeklyPoints_projected": team["weeklyPoints"],
                "essay_snippet": team["preseasonEssay"][:200] + "...",
            }

    # --- Previous Weeks Summary (for callbacks) ---
    prev_summaries = []
    if prev_weeks:
        for pw in prev_weeks:
            prev_summaries.append({
                "week": pw["meta"]["week"],
                "high_scorer": pw["awards"]["high_scorer"]["team_name"],
                "high_score": pw["awards"]["high_scorer"]["points"],
                "leader": pw["standings"][0]["team_name"],
                "leader_record": pw["standings"][0]["record"],
            })

    # --- Build final output ---
    result = {
        "meta": {
            "week": week_num,
            "season": data["season"],
            "is_playoff": week_data.get("is_playoff", False),
            "generated_for": "AI content generation",
        },
        "matchups": matchups,
        "standings": standings,
        "awards": awards,
        "season_context": season_context,
        "next_matchups": next_matchups,
        "previous_weeks_summary": prev_summaries,
        "team_profiles_summary": profiles_summary,
    }

    return result


def compute_streak(data, up_to_week, roster_id, roster_lookup):
    """Compute current win/loss streak for a team up to a given week."""
    streak_type = None  # 'W' or 'L'
    streak_count = 0

    for w in reversed(data["weeks"]):
        if w["week"] > up_to_week:
            continue
        if w.get("is_playoff", False):
            continue

        for m in w["matchups"]:
            t1_rid = m["team1"]["roster_id"]
            t2_rid = m["team2"]["roster_id"]
            winner_rid = m.get("winner")

            if roster_id not in (t1_rid, t2_rid):
                continue

            if winner_rid == roster_id:
                result = "W"
            elif winner_rid is None:
                return f"T1" if streak_count == 0 else f"{streak_type}{streak_count}"
            else:
                result = "L"

            if streak_type is None:
                streak_type = result
                streak_count = 1
            elif result == streak_type:
                streak_count += 1
            else:
                return f"{streak_type}{streak_count}"

    return f"{streak_type}{streak_count}" if streak_type else "—"


def main():
    args = sys.argv[1:]
    season = 2025
    pretty = "--pretty" in args
    extract_all = "--all" in args

    if "--season" in args:
        idx = args.index("--season")
        if idx + 1 < len(args):
            season = int(args[idx + 1])

    data = load_season_data(season)
    roster_lookup = build_roster_lookup(data)
    team_profiles = load_team_profiles()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if extract_all:
        weeks_to_extract = [w["week"] for w in data["weeks"]]
    elif "--week" in args:
        idx = args.index("--week")
        if idx + 1 < len(args):
            weeks_to_extract = [int(args[idx + 1])]
        else:
            print("--week requires a number")
            sys.exit(1)
    else:
        print("Usage: python extract_week_data.py --week N [--season YYYY] [--all] [--pretty]")
        sys.exit(1)

    # Extract sequentially so each week can reference previous weeks
    prev_weeks = []
    for week_num in sorted(weeks_to_extract):
        print(f"Extracting Week {week_num}...")
        result = extract_week(data, week_num, roster_lookup, team_profiles, prev_weeks)
        if result is None:
            continue

        out_path = OUTPUT_DIR / f"week{week_num}_data.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2 if pretty else None, ensure_ascii=False)

        size_kb = os.path.getsize(out_path) / 1024
        print(f"  -> {out_path} ({size_kb:.1f} KB)")

        # Keep a running summary for subsequent weeks
        prev_weeks.append(result)

    print(f"\nDone! Extracted {len(weeks_to_extract)} week(s).")


if __name__ == "__main__":
    main()
