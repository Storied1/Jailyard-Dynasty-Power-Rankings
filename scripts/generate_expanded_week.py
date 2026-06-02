"""Generate weekN_data_expanded.json from weekN_data.json + NFLGame entities.

Architect M2: denormalized COMPANION for chrome authors who want one fetch per
week instead of N+1. Game data lives in a top-level `games` map; scorers +
awards.top_performer reference it by game_context.game_id (normalize within the
single-fetch document -- no per-holder duplication, ~4.3x smaller than inlining).

Architect N2: content-addressable regeneration via a logical-content +
inliner-version hash -- line-ending- & format-invariant (CRLF Windows tree and
LF CI checkout agree) and sensitive to inliner-semantics changes.

Holders nest under matchups[].team{1,2}.top_scorers[] + awards.top_performer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# scripts/ on sys.path -> runnable as `python scripts/generate_expanded_week.py`
# AND importable as `from scripts.generate_expanded_week import ...` under pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import REPO_ROOT, load_json, save_json_canonical  # noqa: E402

WEEKS_DIR = REPO_ROOT / "content" / "weeks"
NFL_GAMES_DIR = REPO_ROOT / "data" / "2025" / "nfl_games"
MANIFEST_PATH = NFL_GAMES_DIR / "_expanded_manifest.json"

# Bump when build_expanded / _iter_game_context_holders SEMANTICS change, so the
# content-addressable manifest invalidates even when inputs are unchanged (F1).
INLINER_VERSION = "1"


def _iter_game_context_holders(week_data: dict):
    """Yield every dict carrying a game_context (verified nested shape)."""
    for matchup in week_data.get("matchups", []):
        for side_key in ("team1", "team2"):
            side = matchup.get(side_key) or {}
            for scorer in side.get("top_scorers", []):
                yield scorer
    top_performer = (week_data.get("awards") or {}).get("top_performer")
    if isinstance(top_performer, dict):
        yield top_performer


def _referenced_game_ids(week_data: dict) -> set:
    ids = {
        (h.get("game_context") or {}).get("game_id")
        for h in _iter_game_context_holders(week_data)
    }
    ids.discard(None)
    return ids


def compute_manifest_hash(paths: list) -> str:
    """SHA-256 over INLINER_VERSION + sorted (name, canonical-content) pairs.

    Hashes LOGICAL JSON content (load_json normalizes CRLF->LF on read), so a
    Windows working tree and an LF CI checkout produce the same digest (F4).
    INLINER_VERSION invalidates the manifest on a logic change (F1).
    """
    h = hashlib.sha256()
    h.update(f"inliner-v{INLINER_VERSION}\x00".encode("utf-8"))
    for p in sorted(paths, key=str):
        h.update(p.name.encode("utf-8"))
        h.update(b"\x00")
        h.update(
            json.dumps(load_json(p), sort_keys=True, ensure_ascii=False).encode("utf-8")
        )
        h.update(b"\x00")
    return h.hexdigest()


def build_expanded(week_data: dict, nfl_games: dict) -> dict:
    """Attach a top-level `games` map keyed by game_id.

    Scorers + awards.top_performer keep their game_context.game_id as the
    reference. Chrome authors resolve via week.games[ctx.game_id] -- one fetch,
    one local lookup, no per-holder duplication.
    """
    expanded = json.loads(json.dumps(week_data))  # deep copy
    referenced = _referenced_game_ids(expanded)
    expanded["games"] = {
        gid: nfl_games[gid] for gid in sorted(referenced) if gid in nfl_games
    }
    return expanded


def regenerate_for_week(week: int, season: int = 2025) -> bool:
    """Regenerate one week's expanded file. Returns True if written."""
    week_data_path = WEEKS_DIR / f"week{week}_data.json"
    week_data = load_json(week_data_path)
    if week_data is None:
        print(f"  week{week}: no week_data.json -- skipped")
        return False

    game_ids = _referenced_game_ids(week_data)
    referenced_game_paths = [NFL_GAMES_DIR / f"{gid}.json" for gid in game_ids]
    inputs = [week_data_path] + [p for p in referenced_game_paths if p.exists()]
    new_hash = compute_manifest_hash(inputs)

    manifest = (load_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}) or {}
    if manifest.get(str(week)) == new_hash:
        return False  # up-to-date

    nfl_games = {p.stem: load_json(p) for p in referenced_game_paths if p.exists()}
    expanded = build_expanded(week_data, nfl_games)
    save_json_canonical(WEEKS_DIR / f"week{week}_data_expanded.json", expanded)

    manifest[str(week)] = new_hash
    save_json_canonical(MANIFEST_PATH, manifest)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--week", type=int, default=None, help="Single week (default: all 1-18)"
    )
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()

    weeks = [args.week] if args.week else list(range(1, 19))
    written = 0
    for w in weeks:
        if regenerate_for_week(w, args.season):
            written += 1
            print(f"  Wrote week{w}_data_expanded.json")
        else:
            print(f"  week{w}: up-to-date (manifest hash unchanged)")
    print(f"  Total written: {written}/{len(weeks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
