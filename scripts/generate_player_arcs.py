"""Generate cross-season Player Arcs (Phase 1b Item 2).

data/2025/player_arcs/{pid}.json + _index.json (split path, >3MB rule)
or data/2025/player_arcs.json (monolith, if under threshold).

Ground truth: committed matchups.json (weekly ownership/points/started).
Narrative: draft_picks.json + transactions.json events.
Status/game_id enrichment: gitignored Sleeper stats caches + committed
nfl_games files (2025 game_ids only). See plan design decisions 1-12
(~/.claude/plans/immutable-questing-origami.md).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# fmt: off
from shared import (DATA_DIR, load_json, load_nfl_stats_cache,  # noqa: E402
                    normalize_team, save_json, save_json_canonical)

# fmt: on

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


def build_draft_events(picks_by_season):
    """pid -> draft events from data/{season}/draft_picks.json docs."""
    events = {}
    for season in sorted(picks_by_season):
        doc = picks_by_season[season]
        for p in doc.get("picks", []):
            events.setdefault(p["player_id"], []).append(
                {
                    "event": "draft",
                    "season": season,
                    "round": p["round"],
                    "pick": p["pick_no"],
                    "draft_slot": p["draft_slot"],
                    "roster_id": p["roster_id"],
                    "date": doc.get("start_date"),
                }
            )
    return events


def build_txn_events(txns_by_season, names):
    """pid -> dated narrative events from transactions.

    Filters status != "complete" (97/717 are failed -- Phase 1a finding).
    Handles trade / waiver / free_agent / commissioner (decision #6).
    Pick-only trades produce no player events (decision #8).
    """
    events = {}
    for season in sorted(txns_by_season):
        flat = []
        for week_txns in txns_by_season[season].values():
            flat.extend(t for t in week_txns if t.get("status") == "complete")
        flat.sort(key=lambda t: t.get("created") or 0)
        for txn in flat:
            adds = txn.get("adds") or {}
            drops = txn.get("drops") or {}
            date = _ms_to_iso(txn["created"]) if txn.get("created") else None
            if txn.get("type") == "trade":
                if len(txn.get("roster_ids") or []) > 2:
                    print(
                        f"WARNING: >2-team trade in {season} "
                        f"(txn {txn.get('transaction_id')}); per-player "
                        f"from/to still derived from adds/drops"
                    )
                picks = [
                    {
                        "round": dp.get("round"),
                        "season": dp.get("season"),
                        "original_roster_id": dp.get("roster_id"),
                        "from_roster_id": dp.get("previous_owner_id"),
                        "to_roster_id": dp.get("owner_id"),
                    }
                    for dp in (txn.get("draft_picks") or [])
                ]
                for pid in sorted(set(adds) | set(drops)):
                    to_rid, from_rid = adds.get(pid), drops.get(pid)
                    if to_rid is None or from_rid is None:
                        continue  # one-sided rows shouldn't exist (verified symmetric)
                    counter_players = [
                        {"player_id": o, "name": names.get(o)}
                        for o in sorted(set(adds) | set(drops))
                        if o != pid and adds.get(o) == from_rid
                    ]
                    counter_picks = [p for p in picks if p["to_roster_id"] == from_rid]
                    events.setdefault(pid, []).append(
                        {
                            "event": "trade",
                            "season": season,
                            "date": date,
                            "from_roster_id": from_rid,
                            "to_roster_id": to_rid,
                            "in_return": {
                                "players": counter_players,
                                "picks": counter_picks,
                            },
                        }
                    )
            else:
                via = txn.get("type")  # waiver | free_agent | commissioner
                settings = txn.get("settings") or {}
                bid = settings.get("waiver_bid") if via == "waiver" else None
                for pid, rid in sorted(adds.items()):
                    events.setdefault(pid, []).append(
                        {
                            "event": "add",
                            "season": season,
                            "date": date,
                            "roster_id": rid,
                            "via": via,
                            "bid": bid,
                        }
                    )
                for pid, rid in sorted(drops.items()):
                    events.setdefault(pid, []).append(
                        {
                            "event": "drop",
                            "season": season,
                            "date": date,
                            "roster_id": rid,
                            "via": via,
                            "bid": None,
                        }
                    )
    return events


def build_rostered_spans(weekly_rows):
    """Contiguous same-roster week runs, per season (decision #10)."""
    spans = []
    cur = None
    for r in weekly_rows:  # already sorted (season, week)
        if (
            cur
            and cur["season"] == r["season"]
            and cur["roster_id"] == r["owner_roster_id"]
            and cur["to_week"] == r["week"] - 1
        ):
            cur["to_week"] = r["week"]
            continue
        cur = {
            "event": "rostered",
            "season": r["season"],
            "roster_id": r["owner_roster_id"],
            "from_week": r["week"],
            "to_week": r["week"],
        }
        spans.append(cur)
    return spans


def build_ownership(txn_events, draft_events, spans):
    """Within season: drafts (by pick), dated events (by date), spans (by week)."""

    def keyed(items, kind_rank, sub):
        return [((e["season"], kind_rank, sub(e)), e) for e in items]

    decorated = (
        keyed(draft_events, 0, lambda e: e["pick"])
        + keyed(txn_events, 1, lambda e: e["date"] or "")
        + keyed(spans, 2, lambda e: e["from_week"])
    )
    return [e for _, e in sorted(decorated, key=lambda pair: pair[0])]


def load_stats_index(season):
    """{week: {"teams": set, "players": {pid: team}}} from gitignored caches.
    Weeks with no cache are absent from the dict."""
    index = {}
    for week in WEEKS:
        cache = load_nfl_stats_cache(season, week)
        if not cache:
            continue
        entries = cache.get("stats") or []
        players, teams = {}, set()
        for e in entries:
            team = normalize_team(e.get("team")) if e.get("team") else None
            if not team:
                continue
            teams.add(team)
            pid = e.get("player_id")
            if pid:
                players[pid] = team
        index[week] = {"teams": teams, "players": players}
    return index


def resolve_team(pid, week, stats_index):
    """Player's NFL team that week: direct, else nearest backward then forward."""
    wk = stats_index.get(week)
    if wk and pid in wk["players"]:
        return wk["players"][pid]
    for w in range(week - 1, 0, -1):
        wkb = stats_index.get(w)
        if wkb and pid in wkb["players"]:
            return wkb["players"][pid]
    for w in range(week + 1, 19):
        wkf = stats_index.get(w)
        if wkf and pid in wkf["players"]:
            return wkf["players"][pid]
    return None


def build_game_index_from_records(records):
    """(week, normalized_team) -> nflreadpy game_id, from committed
    data/2025/nfl_games/*.json. Skips the week:null orphan (decision #4)."""
    idx = {}
    for rec in records:
        week, gid = rec.get("week"), rec.get("game_id")
        if week is None or gid is None:
            continue
        for side in ("home_team", "away_team"):
            team = rec.get(side)
            if team:
                idx[(week, normalize_team(team))] = gid
    return idx


def load_game_index():
    games_dir = DATA_DIR / "2025" / "nfl_games"
    records = [
        load_json(p)
        for p in sorted(games_dir.glob("*.json"))
        if not p.name.startswith("_")
    ]
    return build_game_index_from_records([r for r in records if r])


def enrich_status(weekly_by_pid, stats_indexes, game_index):
    """In-place status + game_id enrichment (decisions #3, #4).

    played        stats entry exists for (pid, week)
    did_not_play  no entry, but player's team appears in that week's stats
    bye_week      no entry, team known, team absent from that week's stats
    no_game_data  no cache for that week OR team unresolvable
    game_id       2025 rows only, via (week, team) lookup
    """
    for pid, rows in weekly_by_pid.items():
        for r in rows:
            sidx = stats_indexes.get(r["season"])
            wk = (sidx or {}).get(r["week"])
            if not wk:
                continue  # stays no_game_data
            team = resolve_team(pid, r["week"], sidx)
            if pid in wk["players"]:
                r["status"] = "played"
            elif team is None:
                r["status"] = "no_game_data"
            elif team in wk["teams"]:
                r["status"] = "did_not_play"
            else:
                r["status"] = "bye_week"
            if r["season"] == 2025 and team and r["status"] != "bye_week":
                r["game_id"] = game_index.get((r["week"], team))


def backfill_stats(seasons, force=False):
    """Fetch + cache Sleeper stats for historical seasons (~51 GETs, one-time).
    Writes the same {"stats": [...]} wrapper fetch_sleeper.py uses."""
    from shared import fetch_nfl_stats, nfl_stats_path

    for season in seasons:
        for week in WEEKS:
            path = nfl_stats_path(season, week)
            if path.exists() and not force:
                continue
            stats = fetch_nfl_stats(season, week)
            save_json(path, {"stats": stats})
            print(f"[{season}] cached stats week {week} ({len(stats)} entries)")


def choose_split(arcs, threshold=SPLIT_THRESHOLD_BYTES):
    """Spec architect F2: serialized size > 3MB -> per-player files."""
    size = len(json.dumps(arcs, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return "split" if size > threshold else "single"


def build_arc_index_entry(arc):
    return {
        "name": arc["name"],
        "position": arc["position"],
        "current_owner_roster_id": (arc["current_owner"] or {}).get("roster_id"),
        "seasons": sorted(arc["season_aggregates"].keys()),
        "file": f"player_arcs/{arc['player_id']}.json",
    }


def write_outputs(arcs, mode):
    if mode == "split":
        out_dir = ARC_SEASON_DIR / "player_arcs"
        for pid, arc in sorted(arcs.items()):
            save_json_canonical(out_dir / f"{pid}.json", arc)
        index = {pid: build_arc_index_entry(a) for pid, a in sorted(arcs.items())}
        save_json_canonical(out_dir / "_index.json", index)
        return len(arcs) + 1
    save_json_canonical(ARC_SEASON_DIR / "player_arcs.json", arcs)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--fetch-stats",
        action="store_true",
        help="backfill 2022-2024 Sleeper stats caches first (network)",
    )
    ap.add_argument("--split-threshold", type=int, default=SPLIT_THRESHOLD_BYTES)
    args = ap.parse_args()

    players_path = DATA_DIR / "players.json"
    if not players_path.exists():
        sys.exit(
            "data/players.json missing (gitignored input). "
            "Run: python fetch_sleeper.py --season 2025"
        )
    players = load_json(players_path, required=True)

    if args.fetch_stats:
        backfill_stats([s for s in SEASONS if s != 2025])

    matchups = {
        s: load_json(DATA_DIR / str(s) / "matchups.json", required=True)
        for s in SEASONS
    }
    txns = {
        s: load_json(DATA_DIR / str(s) / "transactions.json", required=True)
        for s in SEASONS
    }
    picks = {}
    for s in SEASONS:
        doc = load_json(DATA_DIR / str(s) / "draft_picks.json")
        if doc:
            picks[s] = doc
    rosters_now = load_json(
        DATA_DIR / str(CURRENT_SEASON) / "rosters.json", required=True
    )
    users_now = load_json(DATA_DIR / str(CURRENT_SEASON) / "users.json", required=True)
    team_name_by_owner = {
        u["user_id"]: (u.get("metadata") or {}).get("team_name") for u in users_now
    }
    owner_now = {}
    for r in rosters_now:
        for pid in r.get("players") or []:
            owner_now[pid] = {
                "roster_id": r["roster_id"],
                "team_name": team_name_by_owner.get(r["owner_id"]),
            }

    def display_name(pid):
        p = players.get(pid) or {}
        return (
            p.get("full_name")
            or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
            or pid
        )

    weekly = build_weekly(matchups)
    stats_indexes = {s: load_stats_index(s) for s in SEASONS}
    enrich_status(weekly, stats_indexes, load_game_index())

    names = {pid: display_name(pid) for pid in weekly}
    txn_events = build_txn_events(txns, names)
    draft_events = build_draft_events(picks)

    arcs = {}
    for pid, rows in sorted(weekly.items()):
        p = players.get(pid) or {}
        arcs[pid] = {
            "player_id": pid,
            "gsis_id": p.get("gsis_id"),
            "name": display_name(pid),
            "position": p.get("position"),
            "current_owner": owner_now.get(pid),
            "ownership_history": build_ownership(
                txn_events.get(pid, []),
                draft_events.get(pid, []),
                build_rostered_spans(rows),
            ),
            "weekly": rows,
            "season_aggregates": build_aggregates(rows),
        }

    import jsonschema  # deferred: only main() validates (repo pattern)

    schema = load_json(
        Path(__file__).resolve().parent / "schemas" / "player_arc.schema.json",
        required=True,
    )
    for arc in arcs.values():
        jsonschema.validate(arc, schema)  # loud failure

    mode = choose_split(arcs, args.split_threshold)
    written = write_outputs(arcs, mode)
    statuses = {}
    for rows in weekly.values():
        for r in rows:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    print(f"arcs: {len(arcs)} players, mode={mode}, files written={written}")
    print(f"status coverage: {sorted(statuses.items())}")
    with_game = sum(1 for rows in weekly.values() for r in rows if r["game_id"])
    print(f"game_id populated: {with_game} rows (2025 only by design)")


if __name__ == "__main__":
    main()
