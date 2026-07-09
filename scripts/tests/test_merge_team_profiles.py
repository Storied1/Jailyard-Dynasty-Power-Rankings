"""Tests for merge_team_profiles.py -- field-preserving team-profiles.json merge.

Synthetic fixtures only -- no file or network I/O.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from merge_team_profiles import merge_team_profiles  # noqa: E402
from shared import merge_allowlisted_fields  # noqa: E402

PROFILES = {
    "generated_from": "preseason.html inline data (league.teams[] + extras{})",
    "season": "2025",
    "teams": [
        {
            "name": "General Ken‑obi",
            "owner": "bLaker24",
            "initials": "GK",
            "rank": 1,
            "tier": "Contender",
            "roast": "old roast",
            "keyPlayers": {"qb": ["Old Player"]},
            "draftPicks": ["2026 1st"],
            "weeklyPoints": 48.9,
            "scheduleRank": 7.0,
            "needs": ["QB"],
            "blurb": "old blurb",
            "preseasonEssay": "old essay",
            "championshipHistory": ["2023 Champion"],
        },
        {
            "name": "Burden of Etienne‑y Woody",
            "owner": "kharlo w",  # the known typo -- corrected via normalized join
            "initials": "BEW",
            "rank": 8,
            "tier": "Fraud",
            "roast": "old fraud roast",
            "keyPlayers": {"wr": ["Justin Jefferson"]},
            "draftPicks": [],
            "weeklyPoints": 30.0,
            "scheduleRank": 5.0,
            "needs": ["QB", "RB"],
            "blurb": "old fraud blurb",
            "preseasonEssay": "old fraud essay",
            "championshipHistory": [],
        },
    ],
}

# roster_id -> canonical username, mirroring data/franchises/_index.json's shape.
CANONICAL_USERNAMES = {10: "bLaker24", 1: "kharlow"}


def _prose_update(owner, **overrides):
    base = {
        "owner": owner,
        "rank": 2,
        "tier": "Frisky",
        "roast": "new roast",
        "blurb": "new blurb",
        "preseasonEssay": "new essay",
    }
    base.update(overrides)
    return base


def test_merge_preserves_structured_fields():
    updates = {"teams": [_prose_update("bLaker24")]}
    merged = merge_team_profiles(PROFILES, updates, CANONICAL_USERNAMES)
    team = next(t for t in merged["teams"] if t["initials"] == "GK")
    assert team["keyPlayers"] == {"qb": ["Old Player"]}
    assert team["draftPicks"] == ["2026 1st"]
    assert team["initials"] == "GK"
    assert team["weeklyPoints"] == 48.9
    assert team["scheduleRank"] == 7.0
    assert team["needs"] == ["QB"]
    assert team["championshipHistory"] == ["2023 Champion"]


def test_merge_updates_allowlisted_prose_fields():
    updates = {"teams": [_prose_update("bLaker24")]}
    merged = merge_team_profiles(PROFILES, updates, CANONICAL_USERNAMES)
    team = next(t for t in merged["teams"] if t["initials"] == "GK")
    assert team["rank"] == 2
    assert team["tier"] == "Frisky"
    assert team["roast"] == "new roast"
    assert team["blurb"] == "new blurb"
    assert team["preseasonEssay"] == "new essay"


def test_merge_corrects_owner_spelling_via_normalized_join():
    # Update keyed on the CORRECT spelling; source profile has the typo.
    updates = {"teams": [_prose_update("kharlow", rank=9, tier="Fraud")]}
    merged = merge_team_profiles(PROFILES, updates, CANONICAL_USERNAMES)
    team = next(t for t in merged["teams"] if t["initials"] == "BEW")
    assert team["owner"] == "kharlow"  # corrected from "kharlo w"
    assert team["rank"] == 9


def test_merge_unmatched_update_raises_value_error():
    updates = {"teams": [_prose_update("nobody-in-the-league")]}
    with pytest.raises(ValueError, match="matched"):
        merge_team_profiles(PROFILES, updates, CANONICAL_USERNAMES)


def test_merge_no_updates_still_corrects_owner_spelling():
    merged = merge_team_profiles(PROFILES, {"teams": []}, CANONICAL_USERNAMES)
    team = next(t for t in merged["teams"] if t["initials"] == "BEW")
    assert team["owner"] == "kharlow"  # corrected even with zero prose updates
    assert team["roast"] == "old fraud roast"  # untouched


def test_merge_allowlisted_fields_only_overwrites_listed_keys():
    target = {"a": 1, "b": 2, "c": 3}
    source = {"a": 99, "c": 100, "d": 999}
    result = merge_allowlisted_fields(target, source, ("a", "c"))
    assert result == {"a": 99, "b": 2, "c": 100}


def test_merge_allowlisted_fields_missing_source_key_preserves_target():
    target = {"a": 1, "b": 2}
    source = {"a": 99}  # "b" absent from source
    result = merge_allowlisted_fields(target, source, ("a", "b"))
    assert result == {"a": 99, "b": 2}
