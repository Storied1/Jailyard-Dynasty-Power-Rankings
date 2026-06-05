"""Per-week fantasy roster snapshots for played weeks (T9, redesigned 2026-06-04).

Two modes, schema: scripts/schemas/fantasy_roster.schema.json →
data/{season}/fantasy_rosters/week{N}.json (gitignored).

PRIMARY — Sleeper matchup backfill. Matchup data is immutable history and
still serves 2025 weeks with full players[] + starters[] arrays
(probe-verified 2026-06-04: 12 entries/week, weeks 1-17). Authoritative:
no offseason-gap problem, starters recoverable. captured=true.

FALLBACK — transaction reversal from the current-roster snapshot
(data/{season}/rosters.json + transactions.json). Real Sleeper shapes:
transactions.json is a week-keyed dict; txns carry `leg` (NOT `week`) and
include status:"failed" entries that never executed. Reversal cannot see
the 2025→2026 offseason (transactions stop at leg 17, anchor is the
April-2026 snapshot), so derived snapshots are stamped
derived_confidence="approximate" and are ADVISORY for editorial checks,
never gate-authoritative. starters/reserve unrecoverable → null
(architect B2).

Usage:
    python scripts/derive_historical_rosters.py --season 2025
    python scripts/derive_historical_rosters.py --weeks 1 2 3 --mode derive
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# sys.path bootstrap so this runs BOTH as `python scripts/X.py` and under
# pytest as scripts.X (canonical pattern: scripts/fetch_nflreadpy.py).
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from shared import REPO_ROOT, load_json, save_json_canonical  # noqa: E402

SLEEPER_BASE = "https://api.sleeper.app/v1"
SCHEMA_PATH = REPO_ROOT / "scripts" / "schemas" / "fantasy_roster.schema.json"


# ---------- PRIMARY: matchup-sourced snapshots ----------


def fetch_week_matchups(league_id: str, week: int, timeout: int = 15) -> list[dict]:
    """GET /league/{id}/matchups/{week} — one entry per roster.

    int() coercion + host pin: both interpolants are forced numeric and the
    final URL must sit under the Sleeper API base, so no dynamic value can
    smuggle a scheme/host (semgrep urllib audit, 2026-06-04).
    """
    url = f"{SLEEPER_BASE}/league/{int(str(league_id))}/matchups/{int(week)}"
    if not url.startswith("https://api.sleeper.app/"):
        raise ValueError(f"refusing non-Sleeper URL: {url}")
    # nosemgrep — audited per the rule's instruction: interpolants are forced
    # ints and the host is pinned above; scheme injection is structurally
    # impossible. Project pipeline is stdlib-urllib by convention (zero deps).
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosemgrep
        return json.load(resp)


def build_snapshot_from_matchups(
    week: int, entries: list[dict], owner_by_roster: dict[int, str]
) -> dict:
    """Authoritative snapshot from immutable matchup history.

    Raises KeyError if an entry's roster_id has no owner mapping — a
    silent blank owner would pass downstream and corrupt editorial joins.
    """
    rosters = []
    for e in sorted(entries, key=lambda e: e["roster_id"]):
        rid = e["roster_id"]
        rosters.append(
            {
                "roster_id": rid,
                "owner_id": owner_by_roster[rid],  # KeyError on purpose
                "players": list(e.get("players") or []),
                "starters": list(e.get("starters") or []) or None,
                "reserve": None,  # matchup endpoint does not expose IR/taxi
            }
        )
    return {
        "week": week,
        "captured": True,
        "derived": False,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": "sleeper_matchups_backfill",
        "rosters": rosters,
    }


# ---------- FALLBACK: transaction-reversal derivation ----------


def flatten_transactions(week_keyed: dict) -> list[dict]:
    """Flatten transactions.json (dict keyed by week-string) to a list of
    COMPLETE transactions only — 97/717 in 2025 are status:"failed" and
    carry adds/drops that never happened."""
    flat: list[dict] = []
    for txns in week_keyed.values():
        for t in txns or []:
            if t.get("status") == "complete":
                flat.append(t)
    return flat


def derive_week(
    week: int, current_rosters: list[dict], transactions: list[dict]
) -> dict:
    """Derive week-N rosters by reversing transactions with leg > week.

    Keys on `leg` — the real Sleeper field. (The 2026-05-03 plan's draft
    read t["week"], which does not exist: every reversal silently no-opped
    and its synthetic-fixture tests passed anyway.)
    """
    rosters_by_id: dict[int, dict] = {
        r["roster_id"]: {
            "roster_id": r["roster_id"],
            "owner_id": r["owner_id"],
            "players": list(r.get("players") or []),
            "starters": None,  # unrecoverable via reversal (architect B2)
            "reserve": None,
        }
        for r in current_rosters
    }

    txns_after = [t for t in transactions if t.get("leg", 0) > week]
    txns_after.sort(key=lambda t: -(t.get("leg", 0)))

    for txn in txns_after:
        adds = txn.get("adds") or {}  # {player_id: roster_id}
        drops = txn.get("drops") or {}
        # Reverse an ADD: player joined after `week` → absent at `week`.
        for player_id, rid in adds.items():
            if rid in rosters_by_id and player_id in rosters_by_id[rid]["players"]:
                rosters_by_id[rid]["players"].remove(player_id)
        # Reverse a DROP: player left after `week` → present at `week`.
        for player_id, rid in drops.items():
            if rid in rosters_by_id and player_id not in rosters_by_id[rid]["players"]:
                rosters_by_id[rid]["players"].append(player_id)

    return {
        "week": week,
        "captured": False,
        "derived": True,
        "captured_at": None,
        "source": "transaction_reversal",
        "derived_confidence": "approximate",
        "rosters": [rosters_by_id[rid] for rid in sorted(rosters_by_id)],
    }


# ---------- orchestration ----------


def load_owner_map(season: int) -> dict[int, str]:
    rosters = load_json(REPO_ROOT / "data" / str(season) / "rosters.json")
    return {r["roster_id"]: r["owner_id"] for r in rosters}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument(
        "--weeks",
        nargs="+",
        type=int,
        default=list(range(1, 18)),
        help="Weeks to snapshot (default: 1-17; week 18 had no games in 2025)",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "fetch", "derive"],
        default="auto",
        help="auto: Sleeper matchup backfill, per-week derive fallback",
    )
    args = parser.parse_args()

    import jsonschema  # deferred: only main() validates

    schema = load_json(SCHEMA_PATH)
    season_dir = REPO_ROOT / "data" / str(args.season)
    out_dir = season_dir / "fantasy_rosters"

    owner_map = load_owner_map(args.season)
    league_id = load_json(season_dir / "season_combined.json")["league_id"]

    current_rosters = transactions = None
    if args.mode in ("auto", "derive"):
        current_rosters = load_json(season_dir / "rosters.json")
        transactions = flatten_transactions(load_json(season_dir / "transactions.json"))

    written = 0
    for week in args.weeks:
        snapshot = None
        if args.mode in ("auto", "fetch"):
            try:
                entries = fetch_week_matchups(league_id, week)
                if entries:
                    snapshot = build_snapshot_from_matchups(week, entries, owner_map)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                print(f"  week {week}: matchup fetch failed ({exc})", file=sys.stderr)
                if args.mode == "fetch":
                    return 1
        if snapshot is None:
            if args.mode == "fetch":
                print(f"  week {week}: no matchup data", file=sys.stderr)
                return 1
            snapshot = derive_week(week, current_rosters, transactions)

        jsonschema.validate(snapshot, schema)  # loud failure beats bad data
        out_path = out_dir / f"week{week}.json"
        save_json_canonical(out_path, snapshot)
        written += 1
        print(
            f"  week {week}: {snapshot['source']} -> {out_path.relative_to(REPO_ROOT)}"
        )

    print(
        f"Wrote {written}/{len(args.weeks)} snapshots to {out_dir.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
