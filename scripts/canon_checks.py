"""Validate sanitizer source artifacts (pre-write) for a given week.

Checks the *source artifacts* the as-of-week sanitizer produces
(week{N}_chat_context.json, week{N}_data.json) for structural completeness,
before /write-week ever runs. Distinct from verify_week_content.py, which
validates *written content* against source data after the fact.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure scripts/ is on sys.path so this module is runnable both as a script
# (`python scripts/canon_checks.py`) and as part of the test package
# (`from scripts.canon_checks import ...`).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import WEEKS_DIR, load_json  # noqa: E402


def check_league_memory_present(chat_context: dict, errors: list) -> None:
    if "league_memory" not in chat_context:
        errors.append(
            "league_memory key missing from chat_context — "
            "writer will get zero league-culture context"
        )
        return
    lm = chat_context["league_memory"]
    for key in ("culture", "lexicon", "running_jokes"):
        if key not in lm:
            errors.append(f"league_memory.{key} missing")


def check_as_of_week_fields(standings_entry: dict, errors: list) -> None:
    team = standings_entry.get("team_name", "<unknown>")
    for key in ("current_elo", "peak_elo", "all_time_record"):
        if key not in standings_entry:
            errors.append(
                f"{team}: as-of-week field '{key}' missing from standings entry"
            )
    for key in ("championships", "best_win_streak"):
        if key in standings_entry:
            errors.append(
                f"{team}: season-end field '{key}' present in-season — as-of-week leak"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Validate sanitizer source artifacts (pre-write) for a given week"
    )
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    errors = []
    chat_context = load_json(
        WEEKS_DIR / f"week{args.week}_chat_context.json", required=True
    )
    check_league_memory_present(chat_context, errors)

    data = load_json(WEEKS_DIR / f"week{args.week}_data.json", required=True)
    for entry in data["standings"]:
        check_as_of_week_fields(entry, errors)

    if errors:
        print(f"FAIL ({len(errors)} issue(s)):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"PASS — week {args.week} artifacts are as-of-week compliant")


if __name__ == "__main__":
    main()
