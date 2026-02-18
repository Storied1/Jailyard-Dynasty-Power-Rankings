#!/usr/bin/env python
"""Verify draft board pick ordering in draft.html.

Parses the inline draftPicks array from draft.html and asserts that
pick numbers are monotonically increasing within each round.
Exits non-zero on failure (CI-ready).
"""

import re
import sys
from pathlib import Path


def extract_draft_picks(html_path: Path) -> list[dict]:
    """Extract draftPicks array from draft.html inline JS.

    Uses per-object regex extraction instead of full JSON parsing to
    handle JS syntax (unquoted keys, single quotes, Unicode escapes).
    """
    text = html_path.read_text(encoding="utf-8")

    # Find the draftPicks array bounds
    start = text.find("const draftPicks = [")
    if start == -1:
        print("ERROR: Could not find draftPicks array in", html_path)
        sys.exit(2)

    # Find the closing ];
    end = text.find("];", start)
    if end == -1:
        print("ERROR: Could not find end of draftPicks array")
        sys.exit(2)

    array_text = text[start:end]

    # Extract each pick object using regex for the known fields
    # Use (?:[^'\\]|\\.)* to handle escaped quotes like Ja\'Tavion
    picks = []
    val = r"'((?:[^'\\]|\\.)*)'"  # matches single-quoted JS string with escapes
    pattern = re.compile(
        r"\{\s*"
        r"round\s*:\s*(\d+)\s*,\s*"
        r"pick\s*:\s*(\d+)\s*,\s*"
        rf"team\s*:\s*{val}\s*,\s*"
        rf"player\s*:\s*{val}\s*,\s*"
        rf"pos\s*:\s*{val}\s*,\s*"
        rf"college\s*:\s*{val}\s*,\s*"
        rf"note\s*:\s*{val}\s*"
        r"\}"
    )

    for m in pattern.finditer(array_text):
        picks.append({
            "round": int(m.group(1)),
            "pick": int(m.group(2)),
            "team": m.group(3),
            "player": m.group(4),
            "pos": m.group(5),
            "college": m.group(6),
            "note": m.group(7),
        })

    if not picks:
        print("ERROR: No picks extracted from draftPicks array")
        sys.exit(2)

    return picks


def verify_ordering(picks: list[dict]) -> bool:
    """Verify picks are ordered correctly within each round."""
    errors = []
    rounds: dict[int, list[dict]] = {}

    for p in picks:
        rounds.setdefault(p["round"], []).append(p)

    for r in sorted(rounds.keys()):
        round_picks = rounds[r]
        pick_count = len(round_picks)

        # Check we have the expected number of picks per round
        if pick_count != 12:
            errors.append(
                f"  Round {r}: found {pick_count} picks (expected 12)"
            )

        # Verify picks are sequential 1..N
        for i, p in enumerate(round_picks):
            expected_pick = i + 1
            if p["pick"] != expected_pick:
                errors.append(
                    f"  Round {r}: position {i} has pick {p['pick']} "
                    f"(expected {expected_pick}) - {p['player']}"
                )

        # Verify monotonically increasing
        pick_nums = [p["pick"] for p in round_picks]
        for i in range(1, len(pick_nums)):
            if pick_nums[i] <= pick_nums[i - 1]:
                errors.append(
                    f"  Round {r}: pick {pick_nums[i]} follows pick "
                    f"{pick_nums[i - 1]} (not monotonically increasing)"
                )

    if errors:
        print("FAIL: Draft order verification failed:")
        for e in errors:
            print(e)
        return False

    return True


def main():
    repo_root = Path(__file__).resolve().parent.parent
    draft_html = repo_root / "draft.html"

    if not draft_html.exists():
        print(f"ERROR: {draft_html} not found")
        sys.exit(2)

    picks = extract_draft_picks(draft_html)
    print(f"Parsed {len(picks)} draft picks from {draft_html.name}")

    rounds = sorted(set(p["round"] for p in picks))
    print(f"Rounds found: {rounds}")
    print(f"Picks per round: {[len([p for p in picks if p['round'] == r]) for r in rounds]}")

    if verify_ordering(picks):
        print("PASS: All picks correctly ordered within each round")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
