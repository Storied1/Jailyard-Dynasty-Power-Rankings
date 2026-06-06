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


def choose_split(*args, **kwargs):  # implemented in T4
    raise NotImplementedError
