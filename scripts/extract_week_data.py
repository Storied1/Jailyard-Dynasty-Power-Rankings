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

from shared import (
    REPO_ROOT,
    DATA_DIR,
    WEEKS_DIR as OUTPUT_DIR,
    TEAM_PROFILES_PATH,
    load_json,
    load_nfl_stats_cache,
    compute_momentum,
)

PROJECT_DIR = REPO_ROOT


def load_season_data(season=2025):
    """Load the combined season data file."""
    path = DATA_DIR / str(season) / "season_combined.json"
    return load_json(path, label=f"season_combined.json for {season}", required=True)


def load_team_profiles():
    """Load team profiles for preseason context."""
    return load_json(TEAM_PROFILES_PATH)


def load_history_data():
    """Load league history for H2H, Elo, and franchise stats."""
    return load_json(DATA_DIR / "league_history.json")


NFL_TEAM_FULL = {
    "ARI": "Cardinals",
    "ATL": "Falcons",
    "BAL": "Ravens",
    "BUF": "Bills",
    "CAR": "Panthers",
    "CHI": "Bears",
    "CIN": "Bengals",
    "CLE": "Browns",
    "DAL": "Cowboys",
    "DEN": "Broncos",
    "DET": "Lions",
    "GB": "Packers",
    "HOU": "Texans",
    "IND": "Colts",
    "JAX": "Jaguars",
    "KC": "Chiefs",
    "LAC": "Chargers",
    "LAR": "Rams",
    "LV": "Raiders",
    "MIA": "Dolphins",
    "MIN": "Vikings",
    "NE": "Patriots",
    "NO": "Saints",
    "NYG": "Giants",
    "NYJ": "Jets",
    "PHI": "Eagles",
    "PIT": "Steelers",
    "SEA": "Seahawks",
    "SF": "49ers",
    "TB": "Buccaneers",
    "TEN": "Titans",
    "WAS": "Commanders",
}


def _stat_line(position, stats):
    """Render a position-appropriate stat line from a Sleeper player stats dict."""
    if not stats:
        return ""
    p = position or ""
    parts = []
    if p == "QB":
        if stats.get("pass_yd"):
            parts.append(f"{int(stats['pass_yd'])} pass yd")
        if stats.get("pass_td"):
            parts.append(f"{int(stats['pass_td'])} pass TD")
        if stats.get("pass_int"):
            parts.append(f"{int(stats['pass_int'])} INT")
        if stats.get("rush_yd"):
            parts.append(f"{int(stats['rush_yd'])} rush yd")
        if stats.get("rush_td"):
            parts.append(f"{int(stats['rush_td'])} rush TD")
    elif p == "RB":
        if stats.get("rush_att"):
            parts.append(f"{int(stats['rush_att'])} carries")
        if stats.get("rush_yd"):
            parts.append(f"{int(stats['rush_yd'])} yd")
        if stats.get("rush_td"):
            parts.append(f"{int(stats['rush_td'])} rush TD")
        if stats.get("rec"):
            parts.append(f"{int(stats['rec'])} rec")
        if stats.get("rec_yd"):
            parts.append(f"{int(stats['rec_yd'])} rec yd")
        if stats.get("rec_td"):
            parts.append(f"{int(stats['rec_td'])} rec TD")
    elif p in ("WR", "TE"):
        if stats.get("rec"):
            parts.append(f"{int(stats['rec'])} rec")
        if stats.get("rec_yd"):
            parts.append(f"{int(stats['rec_yd'])} yd")
        if stats.get("rec_td"):
            parts.append(f"{int(stats['rec_td'])} TD")
    elif p == "K":
        if stats.get("fgm"):
            parts.append(
                f"{int(stats['fgm'])}/{int(stats.get('fga', stats['fgm']))} FG"
            )
        if stats.get("xpm"):
            parts.append(f"{int(stats['xpm'])} XP")
    elif p in (
        "DEF",
        "DL",
        "DE",
        "DT",
        "NT",
        "LB",
        "ILB",
        "OLB",
        "MLB",
        "DB",
        "CB",
        "S",
        "SS",
        "FS",
    ):
        if stats.get("idp_tkl_solo"):
            parts.append(f"{int(stats['idp_tkl_solo'])} solo tkl")
        if stats.get("idp_sack"):
            parts.append(f"{stats['idp_sack']} sack")
        if stats.get("idp_qb_hit"):
            parts.append(f"{int(stats['idp_qb_hit'])} QB hit")
        if stats.get("idp_int"):
            parts.append(f"{int(stats['idp_int'])} INT")
        if stats.get("def_td"):
            parts.append(f"{int(stats['def_td'])} def TD")
        if stats.get("idp_fum_rec"):
            parts.append(f"{int(stats['idp_fum_rec'])} FR")
    return ", ".join(parts)


def build_game_context(player_id, nfl_team, position, stats_cache):
    """Build a game_context dict for a single player-week.

    stats_cache is the raw list from the Sleeper stats endpoint (each entry has
    player_id, team, opponent, stats, game_id, etc.). Returns None if no
    matching entry.
    """
    if not player_id or not stats_cache:
        return None

    player_entry = None
    for item in stats_cache:
        if str(item.get("player_id")) == str(player_id):
            player_entry = item
            break

    if not player_entry:
        return None

    opponent = player_entry.get("opponent")
    stats_dict = player_entry.get("stats") or {}
    stat_line = _stat_line(position, stats_dict)
    opp_full = NFL_TEAM_FULL.get(opponent, opponent) if opponent else None

    if opp_full and stat_line:
        one_liner = f"{stat_line} vs. the {opp_full}"
    elif stat_line:
        one_liner = stat_line
    elif opp_full:
        one_liner = f"played vs. the {opp_full}"
    else:
        one_liner = ""

    return {
        "opponent": opponent,
        "stat_line": stat_line,
        "one_liner": one_liner,
    }


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


def build_matchup_entry(
    m, roster_lookup, prev_rankings, history_data, rid_to_owner, stats_cache=None
):
    """Build a single matchup dict from raw matchup data."""
    t1 = m["team1"]
    t2 = m["team2"]
    r1_info = roster_lookup.get(t1["roster_id"], {})
    r2_info = roster_lookup.get(t2["roster_id"], {})

    margin = abs(t1["points"] - t2["points"])
    winner_rid = m.get("winner")

    entry = {
        "matchup_id": m["matchup_id"],
        "team1": {
            "roster_id": t1["roster_id"],
            "team_name": r1_info.get("team_name", "?"),
            "owner": r1_info.get("owner", "?"),
            "points": t1["points"],
            "projected": t1.get("projected", 0),
            "top_scorers": [
                {
                    "player_id": p.get("pid"),
                    "name": p["name"],
                    "position": p["position"],
                    "team": p["team"],
                    "points": p["points"],
                    "game_context": build_game_context(
                        p.get("pid"), p.get("team"), p.get("position"), stats_cache
                    ),
                }
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
                {
                    "player_id": p.get("pid"),
                    "name": p["name"],
                    "position": p["position"],
                    "team": p["team"],
                    "points": p["points"],
                    "game_context": build_game_context(
                        p.get("pid"), p.get("team"), p.get("position"), stats_cache
                    ),
                }
                for p in t2.get("top_starters", [])[:5]
            ],
        },
        "winner": (
            roster_lookup.get(winner_rid, {}).get("team_name", None)
            if winner_rid
            else "Tie"
        ),
        "margin": round(margin, 2),
        "upset": (
            winner_rid is not None
            and prev_rankings.get(winner_rid, 99)
            > prev_rankings.get(
                t1["roster_id"] if winner_rid == t2["roster_id"] else t2["roster_id"], 0
            )
        ),
    }

    # Inject H2H history if available
    if history_data:
        oid1 = rid_to_owner.get(t1["roster_id"], "")
        oid2 = rid_to_owner.get(t2["roster_id"], "")
        h2h = history_data.get("h2h", {})
        h2h_key = f"{oid1}|{oid2}"
        h2h_entry = h2h.get(h2h_key)
        if h2h_entry:
            last_game = h2h_entry["games"][-1] if h2h_entry["games"] else None
            entry["h2h"] = {
                "team1_wins": h2h_entry["wins"],
                "team2_wins": h2h_entry["losses"],
                "total_games": h2h_entry["wins"] + h2h_entry["losses"],
                "last_meeting": (
                    {
                        "season": last_game["season"],
                        "week": last_game["week"],
                        "score": f"{last_game['pts']}-{last_game['opp_pts']}",
                    }
                    if last_game
                    else None
                ),
            }

    return entry


def build_standing_entry(
    s,
    data,
    week_num,
    roster_lookup,
    prev_rankings,
    history_data,
    rid_to_owner,
    prev_weeks=None,
    margin_this_week=0.0,
):
    """Build a single standings dict from raw standings data."""
    rid = s["roster_id"]
    info = roster_lookup.get(rid, {})
    prev_rank = prev_rankings.get(rid, None)
    current_rank = s["power_rank"]

    if prev_rank is not None:
        movement = prev_rank - current_rank  # positive = moved up
    else:
        movement = 0

    streak = compute_streak(data, week_num, rid, roster_lookup)
    momentum = compute_momentum(prev_weeks or [], rid, week_num)

    entry = {
        "roster_id": rid,
        "rank": current_rank,
        "prev_rank": prev_rank,
        "movement": movement,
        "team_name": info.get("team_name", "?"),
        "owner": info.get("owner", "?"),
        "record": f"{s['wins']}-{s['losses']}"
        + (f"-{s['ties']}" if s.get("ties", 0) > 0 else ""),
        "wins": s["wins"],
        "losses": s["losses"],
        "pf": round(s["pf"], 1),
        "pa": round(s.get("pa", 0), 1),
        "power_score": s["power_score"],
        "week_points": s["week_points"],
        "streak": streak,
        "margin_this_week": margin_this_week,
        "momentum": momentum,
    }

    # Inject Elo + franchise stats if history data available
    if history_data:
        oid = rid_to_owner.get(rid, "")
        elo_current = history_data.get("elo_current", {})
        franchise_stats = history_data.get("franchise_stats", {})
        elo_history = history_data.get("elo_history", {})

        if oid in elo_current:
            entry["current_elo"] = elo_current[oid]

        fstats = franchise_stats.get(oid)
        if fstats:
            entry["peak_elo"] = fstats.get("peak_elo")
            at = fstats.get("all_time", {})
            entry["all_time_record"] = f"{at.get('wins', 0)}-{at.get('losses', 0)}"
            entry["championships"] = fstats.get("championships", 0)
            entry["best_win_streak"] = fstats.get("best_win_streak", 0)

        # Compute elo_change for this week
        elo_change = None
        if oid in elo_history:
            entries = [e for e in elo_history[oid] if e["season"] == data["season"]]
            this_elo = next((e["elo"] for e in entries if e["week"] == week_num), None)
            prev_elo = next(
                (e["elo"] for e in entries if e["week"] == week_num - 1), None
            )
            if this_elo is not None and prev_elo is not None:
                elo_change = round(this_elo - prev_elo, 1)
        entry["elo_change"] = elo_change

    return entry


def extract_week(
    data,
    week_num,
    roster_lookup,
    team_profiles=None,
    prev_weeks=None,
    history_data=None,
):
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

    # Load NFL stats cache for this week (may be None if cache absent)
    nfl_cache = load_nfl_stats_cache(data.get("season", 2025), week_num)
    stats_cache = (nfl_cache or {}).get("stats") if nfl_cache else None

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

    # Build owner_id lookup for history cross-referencing
    owner_id_map = {}  # owner_id -> roster_id
    rid_to_owner = {}  # roster_id -> owner_id
    for rid, info in roster_lookup.items():
        oid = info.get("owner_id", "")
        if oid:
            owner_id_map[oid] = rid
            rid_to_owner[rid] = oid

    # --- Matchups ---
    matchups = []
    all_scores = {}
    for m in week_data["matchups"]:
        all_scores[m["team1"]["roster_id"]] = m["team1"]["points"]
        all_scores[m["team2"]["roster_id"]] = m["team2"]["points"]
        matchups.append(
            build_matchup_entry(
                m,
                roster_lookup,
                prev_rankings,
                history_data,
                rid_to_owner,
                stats_cache,
            )
        )

    # Sort matchups by closest margin first (for narrative interest)
    matchups.sort(key=lambda x: x["margin"])

    # Compute per-roster margin this week (for momentum)
    margins_this_week = {}
    for mu in week_data["matchups"]:
        t1 = mu["team1"]
        t2 = mu["team2"]
        margins_this_week[t1["roster_id"]] = round(t1["points"] - t2["points"], 2)
        margins_this_week[t2["roster_id"]] = round(t2["points"] - t1["points"], 2)

    # --- Standings ---
    standings = []
    for s in week_data["standings"]:
        rid = s["roster_id"]
        standings.append(
            build_standing_entry(
                s,
                data,
                week_num,
                roster_lookup,
                prev_rankings,
                history_data,
                rid_to_owner,
                prev_weeks=prev_weeks,
                margin_this_week=margins_this_week.get(rid, 0.0),
            )
        )

    standings.sort(key=lambda x: x["rank"])

    # --- Matchup momentum (derived from team momentum) ---
    momentum_by_team = {s["team_name"]: s["momentum"] for s in standings}
    rank_by_team = {s["team_name"]: s["rank"] for s in standings}
    for mu in matchups:
        t1_name = mu["team1"]["team_name"]
        t2_name = mu["team2"]["team_name"]
        t1_m = momentum_by_team.get(t1_name, {"score": 0, "label": "opening"})
        t2_m = momentum_by_team.get(t2_name, {"score": 0, "label": "opening"})
        edge = round(t1_m["score"] - t2_m["score"], 2)
        t1_rank = rank_by_team.get(t1_name, 99)
        t2_rank = rank_by_team.get(t2_name, 99)

        abs_edge = abs(edge)
        if abs_edge < 0.5:
            label = "coin flip"
        elif abs_edge < 1.5:
            label = "slight edge"
        else:
            label = "heavy lean"

        # Upset brewing: lower-ranked (numerically higher) team has higher
        # momentum AND the rank gap is small (<= 4).
        if t1_rank < t2_rank:
            higher_momentum = t1_m
            lower_momentum = t2_m
        else:
            higher_momentum = t2_m
            lower_momentum = t1_m
        rank_gap = abs(t1_rank - t2_rank)
        if lower_momentum["score"] > higher_momentum["score"] and rank_gap <= 4:
            label = "upset brewing"

        favorite = t1_name if edge >= 0 else t2_name
        mu["momentum"] = {
            "edge": edge,
            "label": label,
            "favorite_team_name": favorite,
        }

    # --- Weekly Awards ---
    high_scorer_rid = week_data["highest_scorer"]["roster_id"]
    low_scorer_rid = week_data["lowest_scorer"]["roster_id"]

    # Find closest and biggest blowout matchups
    closest_matchup = min(matchups, key=lambda m: m["margin"]) if matchups else None
    biggest_blowout = max(matchups, key=lambda m: m["margin"]) if matchups else None

    # Top individual performer
    top_performer = (
        week_data["top_performers"][0] if week_data.get("top_performers") else None
    )

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
        "closest_game": (
            {
                "teams": f"{closest_matchup['team1']['team_name']} vs {closest_matchup['team2']['team_name']}",
                "score": f"{max(closest_matchup['team1']['points'], closest_matchup['team2']['points']):.1f}-{min(closest_matchup['team1']['points'], closest_matchup['team2']['points']):.1f}",
                "margin": closest_matchup["margin"],
            }
            if closest_matchup
            else None
        ),
        "biggest_blowout": (
            {
                "winner": biggest_blowout["winner"],
                "teams": f"{biggest_blowout['team1']['team_name']} vs {biggest_blowout['team2']['team_name']}",
                "score": f"{max(biggest_blowout['team1']['points'], biggest_blowout['team2']['points']):.1f}-{min(biggest_blowout['team1']['points'], biggest_blowout['team2']['points']):.1f}",
                "margin": biggest_blowout["margin"],
            }
            if biggest_blowout
            else None
        ),
        "top_performer": (
            {
                "player_id": top_performer.get("pid"),
                "name": top_performer["name"],
                "position": top_performer["position"],
                "nfl_team": top_performer["team"],
                "points": top_performer["points"],
                "fantasy_team": roster_lookup.get(
                    top_performer.get("roster_id"), {}
                ).get("team_name", "?"),
                "game_context": build_game_context(
                    top_performer.get("pid"),
                    top_performer.get("team"),
                    top_performer.get("position"),
                    stats_cache,
                ),
            }
            if top_performer
            else None
        ),
    }

    # --- Season Context ---
    total_weeks_played = week_num
    all_weekly_totals = []
    for w in weeks[: week_idx + 1]:
        week_total = sum(s["week_points"] for s in w["standings"])
        all_weekly_totals.append(week_total / data["total_rosters"])

    season_avg_ppg = (
        sum(all_weekly_totals) / len(all_weekly_totals) if all_weekly_totals else 0
    )

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
            r1_rank = next(
                (
                    s["rank"]
                    for s in standings
                    if s["team_name"] == r1_info.get("team_name")
                ),
                "?",
            )
            r2_rank = next(
                (
                    s["rank"]
                    for s in standings
                    if s["team_name"] == r2_info.get("team_name")
                ),
                "?",
            )
            next_matchups.append(
                {
                    "team1": r1_info.get("team_name", "?"),
                    "team1_rank": r1_rank,
                    "team2": r2_info.get("team_name", "?"),
                    "team2_rank": r2_rank,
                }
            )

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
                "essay_snippet": team["preseasonEssay"][:500] + "...",
                "ranks": team.get("ranks", {}),
            }

    # --- Previous Weeks Summary (for callbacks) ---
    prev_summaries = []
    if prev_weeks:
        for pw in prev_weeks:
            prev_summaries.append(
                {
                    "week": pw["meta"]["week"],
                    "high_scorer": pw["awards"]["high_scorer"]["team_name"],
                    "high_score": pw["awards"]["high_scorer"]["points"],
                    "leader": pw["standings"][0]["team_name"],
                    "leader_record": pw["standings"][0]["record"],
                }
            )

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

    # Inject historical context (all-time records) if available
    if history_data:
        result["historical_context"] = history_data.get("records")

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
                return "T1" if streak_count == 0 else f"{streak_type}{streak_count}"
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
    history_data = load_history_data()

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
        print(
            "Usage: python extract_week_data.py --week N [--season YYYY] [--all] [--pretty]"
        )
        sys.exit(1)

    # Extract sequentially so each week can reference previous weeks
    prev_weeks = []
    for week_num in sorted(weeks_to_extract):
        print(f"Extracting Week {week_num}...")
        result = extract_week(
            data, week_num, roster_lookup, team_profiles, prev_weeks, history_data
        )
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
