#!/usr/bin/env python
"""Field-preserving merge for content/team-profiles.json (M1 t6).

team-profiles.json is a one-time hand-authored export -- nothing else in the
repo writes to it. This script safely refreshes its prose fields (rank, tier,
roast, blurb, preseasonEssay) from a hand-authored updates file while
preserving every structured field (initials, ranks{}, keyPlayers, draftPicks,
weeklyPoints, scheduleRank, needs, championshipHistory) verbatim, and
corrects the "kharlo w" / "kharlow" owner-spelling drift as a side effect of
joining on the already-canonical usernames in data/franchises/_index.json.
"""

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# fmt: off
from shared import (CONTENT_DIR, DATA_DIR, load_json,  # noqa: E402
                    merge_allowlisted_fields, normalize_username,
                    save_json_canonical)

# fmt: on

TEAM_PROFILES_PATH = CONTENT_DIR / "team-profiles.json"
FRANCHISES_INDEX_PATH = DATA_DIR / "franchises" / "_index.json"
SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "team_profiles.schema.json"

ALLOWED_UPDATE_KEYS = ("rank", "tier", "roast", "blurb", "preseasonEssay")


def load_canonical_usernames(index: dict) -> dict:
    """roster_id (int) -> canonical username, from the already-committed
    data/franchises/_index.json."""
    return {int(rid): info["username"] for rid, info in index.items()}


def merge_team_profiles(
    profiles: dict, updates: dict, canonical_usernames: dict
) -> dict:
    """Return a new profiles dict: owner spelling corrected to canonical
    (a side effect of the join), allow-listed prose fields updated from
    `updates` where a matching owner is found, everything else preserved.

    Raises ValueError if any update entry's owner doesn't match a team
    (by normalized username) -- catches spelling drift before it silently
    updates the wrong team or updates nothing at all.
    """
    canonical_by_norm = {normalize_username(u): u for u in canonical_usernames.values()}
    update_teams = updates.get("teams", [])

    merged_teams = []
    matched = 0
    for team in profiles["teams"]:
        owner_norm = normalize_username(team.get("owner"))
        canonical = canonical_by_norm.get(owner_norm)
        new_team = dict(team)
        if canonical and canonical != team.get("owner"):
            new_team["owner"] = canonical

        update_entry = next(
            (
                u
                for u in update_teams
                if normalize_username(u.get("owner")) == owner_norm
            ),
            None,
        )
        if update_entry:
            new_team = merge_allowlisted_fields(
                new_team, update_entry, ALLOWED_UPDATE_KEYS
            )
            matched += 1

        merged_teams.append(new_team)

    if matched != len(update_teams):
        raise ValueError(
            f"{matched}/{len(update_teams)} update entries matched a team by "
            f"owner -- check for owner spelling drift in the updates file"
        )

    return {**profiles, "teams": merged_teams}


def main():
    parser = argparse.ArgumentParser(
        description="Field-preserving merge for content/team-profiles.json"
    )
    parser.add_argument(
        "--updates",
        required=True,
        help="Path to a JSON file with {'teams': [{owner, rank, tier, roast, blurb, preseasonEssay}, ...]}",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and print, don't write"
    )
    args = parser.parse_args()

    import jsonschema  # deferred: only main() validates (repo pattern)

    profiles = load_json(TEAM_PROFILES_PATH, required=True)
    updates = load_json(Path(args.updates), required=True)
    index = load_json(FRANCHISES_INDEX_PATH, required=True)
    canonical_usernames = load_canonical_usernames(index)

    try:
        merged = merge_team_profiles(profiles, updates, canonical_usernames)
    except ValueError as e:
        sys.exit(f"GATE: {e}")

    schema = load_json(SCHEMA_PATH, required=True)
    jsonschema.validate(merged, schema)  # loud failure

    if args.dry_run:
        print(
            f"DRY RUN -- would write {TEAM_PROFILES_PATH} ({len(merged['teams'])} teams)"
        )
        return

    save_json_canonical(TEAM_PROFILES_PATH, merged, verbose=True)


if __name__ == "__main__":
    main()
