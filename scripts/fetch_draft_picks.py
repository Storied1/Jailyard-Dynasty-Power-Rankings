"""Fetch Sleeper draft picks per season -> committed data/{season}/draft_picks.json.

One-time backfill (Phase 1b Task 1). draft_id comes from committed
data/{season}/league.json. Records roster_id AND picked_by verbatim --
traded-pick rows are where they can diverge (plan design decision #2); the
divergence report prints them for eyeball verification before commit.
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from shared import DATA_DIR, load_json, save_json_canonical  # noqa: E402

SLEEPER_BASE = "https://api.sleeper.app/v1"
SEASONS = (2022, 2023, 2024, 2025)

PICK_FIELDS = (
    "round",
    "pick_no",
    "draft_slot",
    "roster_id",
    "picked_by",
    "player_id",
    "is_keeper",
)
META_FIELDS = ("first_name", "last_name", "position", "team")


def fetch_json(url, timeout=15):
    """GET a Sleeper API URL. Refuses non-Sleeper hosts (same guard as
    derive_historical_rosters)."""
    if not url.startswith("https://api.sleeper.app/"):
        raise ValueError(f"refusing non-Sleeper URL: {url}")
    # nosemgrep: audited -- constant https host enforced above; the only
    # dynamic segment is a digits-only draft_id validated in main()
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosemgrep
        return json.load(resp)


def validate_picks_response(payload):
    """Shape-check the /draft/{id}/picks payload. Loud failure."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("picks payload is not a non-empty list")
    for i, p in enumerate(payload):
        if not isinstance(p, dict):
            raise ValueError(f"pick[{i}] is not a dict")
        for key in ("round", "pick_no", "roster_id", "player_id"):
            if p.get(key) is None:
                raise ValueError(f"pick[{i}] missing {key}")
    return payload


def transform_picks(picks_raw):
    """Keep canonical fields only; sort by pick_no for determinism."""
    out = []
    for p in picks_raw:
        meta = p.get("metadata") or {}
        out.append(
            {
                **{k: p.get(k) for k in PICK_FIELDS},
                "metadata": {k: meta.get(k) for k in META_FIELDS},
            }
        )
    return sorted(out, key=lambda p: p["pick_no"])


def build_season_file(season, draft_meta, picks):
    start_ms = draft_meta.get("start_time")
    start_date = (
        datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date().isoformat()
        if start_ms
        else None
    )
    return {
        "season": season,
        "draft_id": str(draft_meta.get("draft_id")),
        "draft_type": draft_meta.get("type"),
        "start_date": start_date,
        "picks": picks,
    }


def divergence_report(picks_raw, owner_by_roster):
    """Rows where picked_by isn't the roster's owner (traded-pick signal)."""
    flagged = []
    for p in picks_raw:
        expected = owner_by_roster.get(p.get("roster_id"))
        if expected is not None and p.get("picked_by") != expected:
            flagged.append(
                {
                    "pick_no": p.get("pick_no"),
                    "roster_id": p.get("roster_id"),
                    "picked_by": p.get("picked_by"),
                    "expected_owner": expected,
                }
            )
    return flagged


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seasons", nargs="+", type=int, default=list(SEASONS))
    ap.add_argument("--timeout", type=int, default=15)
    args = ap.parse_args()

    for season in args.seasons:
        league = load_json(DATA_DIR / str(season) / "league.json", required=True)
        draft_id = str(league.get("draft_id") or "")
        if not draft_id:
            print(f"[{season}] no draft_id in league.json -- skipping")
            continue
        if not draft_id.isdigit():
            raise ValueError(
                f"[{season}] non-numeric draft_id {draft_id!r} "
                "in league.json -- refusing to build URL"
            )
        meta = fetch_json(f"{SLEEPER_BASE}/draft/{draft_id}", args.timeout)
        raw = validate_picks_response(
            fetch_json(f"{SLEEPER_BASE}/draft/{draft_id}/picks", args.timeout)
        )

        rosters = load_json(DATA_DIR / str(season) / "rosters.json", required=True)
        owner_by_roster = {r["roster_id"]: r["owner_id"] for r in rosters}
        flagged = divergence_report(raw, owner_by_roster)
        for f in flagged:
            print(
                f"[{season}] DIVERGENCE pick {f['pick_no']}: roster {f['roster_id']} "
                f"owner {f['expected_owner']} but picked_by {f['picked_by']}"
            )

        doc = build_season_file(season, meta, transform_picks(raw))
        out = DATA_DIR / str(season) / "draft_picks.json"
        save_json_canonical(out, doc)
        print(
            f"[{season}] wrote {len(doc['picks'])} picks -> {out.name} "
            f"({len(flagged)} divergent)"
        )


if __name__ == "__main__":
    main()
