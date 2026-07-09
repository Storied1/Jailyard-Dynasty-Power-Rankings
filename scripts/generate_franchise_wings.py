"""Generate Franchise Wing files (Phase 1b Item 3).

data/franchises/{roster_id}.json x12 + _index.json. Rekeys owner_id-keyed
league_history.json aggregates to roster_id (stable across all seasons --
verified), adds bracket-derived trophy years, arc-derived roster lineage,
and team-profiles voice callbacks. Inputs are committed files plus the
generated player arcs; regenerable anywhere the repo is checked out.
"""

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# fmt: off
from shared import (CONTENT_DIR, DATA_DIR, load_json,  # noqa: E402
                    normalize_username, save_json_canonical)

# fmt: on

SEASONS = (2022, 2023, 2024, 2025)
CURRENT_SEASON = 2026
OUT_DIR = DATA_DIR / "franchises"
ARCS_DIR = DATA_DIR / "2025" / "player_arcs"
SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "franchise.schema.json"
PROFILE_SOURCE = "team-profiles.json (2025 preseason)"


def championship_from_bracket(winners):
    """(champion_rid, runner_up_rid) -- max round, min matchup_id (CLAUDE.md
    law: 2 games at max round; championship is min(m))."""
    if not winners:
        return (None, None)
    max_r = max(g.get("r", 0) for g in winners)
    finals = sorted(
        (g for g in winners if g.get("r") == max_r), key=lambda g: g.get("m", 0)
    )
    title = finals[0]
    return (title.get("w"), title.get("l"))


def playoff_participants(winners):
    return {g[k] for g in winners for k in ("t1", "t2") if isinstance(g.get(k), int)}


def rekey_h2h(lh_h2h, owner_to_roster, my_owner_id):
    """Directed pairs are pre-oriented in league_history (verified) --
    pure key substitution, no pf/pa swapping."""
    out = {}
    for key, rec in lh_h2h.items():
        a, b = key.split("|")
        if a != my_owner_id:
            continue
        rid = owner_to_roster.get(b)
        if rid is None:
            continue
        out[str(rid)] = {
            "opponent_roster_id": rid,
            "wins": rec["wins"],
            "losses": rec["losses"],
            "pf": rec["pf"],
            "pa": rec["pa"],
        }
    return out


def build_trophy_case(rid, champs_by_season, playoffs_by_season):
    championships, runner_ups, appearances = [], [], []
    for season in sorted(champs_by_season):
        champ, runner = champs_by_season[season]
        if champ == rid:
            championships.append({"season": season, "runner_up_roster_id": runner})
        elif runner == rid:
            runner_ups.append(season)
        if rid in playoffs_by_season.get(season, set()):
            appearances.append(season)
    return {
        "championships": championships,
        "runner_ups": runner_ups,
        "playoff_appearances": appearances,
    }


def match_profile(teams, username):
    target = normalize_username(username)
    for t in teams:
        if normalize_username(t.get("owner")) == target:
            return t
    return None


def build_lineage_entry(arc, roster_id):
    """How the franchise acquired this player: the LAST event in the arc's
    ownership_history that delivered the player to this roster wins; no
    such event -> unknown (e.g. 2026 offseason pickup, outside arc scope)."""
    acquired = {"event": "unknown", "season": None, "detail": None}
    for ev in arc.get("ownership_history", []):
        kind = ev.get("event")
        if kind == "draft" and ev.get("roster_id") == roster_id:
            acquired = {
                "event": "draft",
                "season": ev["season"],
                "detail": f"Round {ev['round']} Pick {ev['pick']}",
            }
        elif kind == "trade" and ev.get("to_roster_id") == roster_id:
            acquired = {
                "event": "trade",
                "season": ev["season"],
                "detail": f"from roster {ev['from_roster_id']}",
            }
        elif kind == "add" and ev.get("roster_id") == roster_id:
            acquired = {"event": "add", "season": ev["season"], "detail": ev.get("via")}
    return {
        "player_id": arc["player_id"],
        "name": arc.get("name"),
        "position": arc.get("position"),
        "acquired": acquired,
    }


def build_milestones(stats, records, elo_history, owner_id):
    ms = []
    for label, rec in sorted(records.items()):
        if rec.get("owner_id") == owner_id:
            ms.append(
                {
                    "type": "league_record",
                    "label": label,
                    "season": rec.get("season"),
                    "week": rec.get("week"),
                    "value": rec.get("points"),
                }
            )
    if stats.get("best_win_streak"):
        ms.append(
            {
                "type": "best_win_streak",
                "label": "best win streak",
                "season": None,
                "week": None,
                "value": stats["best_win_streak"],
            }
        )
    peak = max(elo_history or [], key=lambda e: e["elo"], default=None)
    if peak:
        ms.append(
            {
                "type": "peak_elo",
                "label": "peak Elo",
                "season": peak["season"],
                "week": peak["week"],
                "value": peak["elo"],
            }
        )
    first = min((sr["season"] for sr in stats.get("season_results", [])), default=None)
    if first is not None:
        ms.append(
            {
                "type": "first_season",
                "label": "first season",
                "season": first,
                "week": None,
                "value": None,
            }
        )
    return ms


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()

    import jsonschema  # deferred: only main() validates (repo pattern)

    schema = load_json(SCHEMA_PATH, required=True)
    lh = load_json(DATA_DIR / "league_history.json", required=True)
    profiles = load_json(CONTENT_DIR / "team-profiles.json", required=True)
    rosters_2025 = load_json(DATA_DIR / "2025" / "rosters.json", required=True)
    owner_to_roster = {r["owner_id"]: r["roster_id"] for r in rosters_2025}
    roster_to_owner = {v: k for k, v in owner_to_roster.items()}

    champs_by_season, playoffs_by_season = {}, {}
    for season in SEASONS:
        brackets = load_json(DATA_DIR / str(season) / "brackets.json", required=True)
        winners = brackets.get("winners") or []
        champs_by_season[season] = championship_from_bracket(winners)
        playoffs_by_season[season] = playoff_participants(winners)

    names_by_season = {}
    for season in (*SEASONS, CURRENT_SEASON):
        users = load_json(DATA_DIR / str(season) / "users.json", required=True)
        names_by_season[season] = {
            u["user_id"]: (u.get("metadata") or {}).get("team_name") for u in users
        }

    arc_index = load_json(ARCS_DIR / "_index.json", required=True)
    rosters_now = load_json(
        DATA_DIR / str(CURRENT_SEASON) / "rosters.json", required=True
    )
    players_now = {r["roster_id"]: (r.get("players") or []) for r in rosters_now}

    matched = 0
    for rid in sorted(roster_to_owner):
        oid = roster_to_owner[rid]
        stats = lh["franchise_stats"][oid]
        profile = match_profile(profiles["teams"], stats["username"])
        if profile:
            matched += 1

        lineage = []
        for pid in sorted(players_now.get(rid, [])):
            if pid in arc_index:
                arc = load_json(ARCS_DIR / f"{pid}.json", required=True)
                lineage.append(build_lineage_entry(arc, rid))
            else:  # 2026 offseason pickup with no 2022-2025 league history
                lineage.append(
                    {
                        "player_id": pid,
                        "name": None,
                        "position": None,
                        "acquired": {
                            "event": "unknown",
                            "season": None,
                            "detail": None,
                        },
                    }
                )

        at = stats["all_time"]
        games = at["wins"] + at["losses"] + at["ties"]
        season_results = []
        for sr in stats.get("season_results", []):
            season = sr["season"]
            champ, runner = champs_by_season.get(season, (None, None))
            season_results.append(
                {
                    **{
                        k: sr[k]
                        for k in ("season", "wins", "losses", "ties", "pf", "pa")
                    },
                    "team_name": names_by_season.get(season, {}).get(oid),
                    "champion": champ == rid,
                    "runner_up": runner == rid,
                    "made_playoffs": rid in playoffs_by_season.get(season, set()),
                }
            )

        trophy = build_trophy_case(rid, champs_by_season, playoffs_by_season)
        if len(trophy["championships"]) != stats.get("championships", 0):
            sys.exit(
                f"GATE: roster {rid} bracket championships "
                f"{len(trophy['championships'])} != franchise_stats "
                f"{stats.get('championships')}"
            )
        # finals = championships + runner-ups; franchise_stats.finals IS
        # populated (sums to 2 finalists x 4 seasons). NOTE: we deliberately
        # do NOT gate on franchise_stats.playoff_appearances -- that field is
        # 0 for all 12 owners (dead upstream in build_league_history); the
        # bracket-derived years are the observable truth, sanity-checked
        # globally below (6 participants x 4 seasons).
        finals = len(trophy["championships"]) + len(trophy["runner_ups"])
        if finals != stats.get("finals", 0):
            sys.exit(
                f"GATE: roster {rid} bracket finals {finals} "
                f"!= franchise_stats {stats.get('finals')}"
            )

        peak = max(lh["elo_history"].get(oid, []), key=lambda e: e["elo"], default=None)
        franchise = {
            "roster_id": rid,
            "owner_id": oid,
            "username": stats["username"],
            "current_team_name": names_by_season[CURRENT_SEASON].get(oid)
            or stats.get("team_name"),
            "trophy_case": trophy,
            "all_time_record": {
                **at,
                "win_pct": round(at["wins"] / games, 4) if games else 0.0,
            },
            "elo": {
                "current": lh["elo_current"].get(oid, 0.0),
                "peak": stats.get("peak_elo", 0.0),
                "peak_season": peak["season"] if peak else None,
                "peak_week": peak["week"] if peak else None,
            },
            "h2h": rekey_h2h(lh["h2h"], owner_to_roster, oid),
            "season_results": season_results,
            "milestones": build_milestones(
                stats, lh["records"], lh["elo_history"].get(oid), oid
            ),
            "roster_lineage": lineage,
            "voice_bible_callbacks": {
                "preseason_rank": (profile or {}).get("rank"),
                "tier": (profile or {}).get("tier"),
                "roast": (profile or {}).get("roast"),
                # position-keyed dict in team-profiles ({qb: [...], rb: ...})
                "key_players": (profile or {}).get("keyPlayers") or {},
                "source": PROFILE_SOURCE,
            },
        }

        jsonschema.validate(franchise, schema)  # loud failure
        save_json_canonical(OUT_DIR / f"{rid}.json", franchise)

    if matched != 12:
        sys.exit(f"GATE: only {matched}/12 team-profiles matched by username")

    total_appearances = sum(len(playoffs_by_season[s]) for s in SEASONS)
    if total_appearances != 6 * len(SEASONS):
        sys.exit(
            f"GATE: bracket playoff participants {total_appearances} "
            f"!= {6 * len(SEASONS)} (6 per season expected)"
        )

    index = {}
    for rid in sorted(roster_to_owner):
        oid = roster_to_owner[rid]
        index[str(rid)] = {
            "owner_id": oid,
            "username": lh["franchise_stats"][oid]["username"],
            "current_team_name": names_by_season[CURRENT_SEASON].get(oid),
            "historical_names": {str(s): names_by_season[s].get(oid) for s in SEASONS},
        }
    save_json_canonical(OUT_DIR / "_index.json", index)
    print(f"franchises: 12 files + _index.json -> {OUT_DIR}")


if __name__ == "__main__":
    main()
