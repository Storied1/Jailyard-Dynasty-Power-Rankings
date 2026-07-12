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

from shared import admissible  # noqa: E402
from shared import PRESEASON_DIR, WEEKS_DIR, load_json, parse_ts


def check_preseason_type_marker(chat_context: dict, errors: list) -> None:
    """Preseason artifacts must self-identify via meta.type == 'preseason' so
    downstream gates don't have to infer mode from stdout."""
    if chat_context.get("meta", {}).get("type") != "preseason":
        errors.append(
            "meta.type is not 'preseason' -- preseason_chat_context.json must "
            "self-identify (regenerate via build_chat_context.py --preseason)"
        )


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


def check_storyline_layers_populated(chat_context: dict, errors: list) -> None:
    """Both storyline layers empty = the dead-integration class (2026-07-10):
    every context file ever generated shipped empty arcs/callbacks until the
    field-map revival. Legitimately quiet artifacts still populate at least
    one layer, so both-empty means producer/consumer field drift."""
    if not chat_context.get("active_arcs_this_week") and not chat_context.get(
        "suggested_callbacks"
    ):
        errors.append(
            "active_arcs_this_week AND suggested_callbacks both empty -- "
            "storyline integration layer looks dead (field/key drift between "
            "the chat analytics and build_chat_context?)"
        )


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


def check_arc_and_joke_semantics(chat_context: dict, errors: list) -> None:
    """Semantic validation of the enriched recompute schema (Phase 1f).

    Every surfaced arc and running-joke must carry exact-instant bounds ordered
    within the exact cutoff, a positive NON-BOOLEAN int count, and (arcs) a
    snapshot-unique NONEMPTY arc_group_id. A post-cutoff last_observed_at is a
    leak; a coarse / naive / missing bound fails the uniform admitter. bool is a
    subclass of int, so it is rejected explicitly. The cutoff itself must be an
    exact aware instant -- else admissible(bound, None) would admit all evidence
    and a post-cutoff bound would pass clean."""
    cutoff_str = chat_context.get("meta", {}).get("temporal_cutoff_utc")
    if not admissible(cutoff_str, None):
        errors.append(
            f"meta.temporal_cutoff_utc {cutoff_str!r} is not an exact aware instant "
            f"(missing / malformed / naive / date-only / month-only)"
        )
        return  # cannot validate bounds without a valid cutoff -> fail-closed
    cutoff = parse_ts(cutoff_str)

    def _check(label, item):
        cnt = item.get("count")
        if isinstance(cnt, bool) or not isinstance(cnt, int) or cnt <= 0:
            errors.append(
                f"{label}: count must be a positive non-boolean int, got {cnt!r}"
            )
        fs = item.get("first_seen_at")
        ls = item.get("last_observed_at")
        if not admissible(fs, cutoff):
            errors.append(
                f"{label}: first_seen_at {fs!r} is not an exact instant on/before the cutoff"
            )
        if not admissible(ls, cutoff):
            errors.append(
                f"{label}: last_observed_at {ls!r} is not an exact instant "
                f"on/before the cutoff (post-cutoff = leak)"
            )
        fs_dt, ls_dt = parse_ts(fs), parse_ts(ls)
        if fs_dt and ls_dt and fs_dt > ls_dt:
            errors.append(f"{label}: first_seen_at {fs} is after last_observed_at {ls}")

    arcs = chat_context.get("active_arcs_this_week", []) or []
    for i, a in enumerate(arcs):
        gid = a.get("arc_group_id")
        if not isinstance(gid, str) or not gid:
            errors.append(
                f"active_arcs[{i}]: arc_group_id must be a nonempty string, got {gid!r}"
            )
    valid_gids = [
        a.get("arc_group_id")
        for a in arcs
        if isinstance(a.get("arc_group_id"), str) and a.get("arc_group_id")
    ]
    dupes = sorted({g for g in valid_gids if valid_gids.count(g) > 1})
    if dupes:
        errors.append(f"arc_group_id not unique in snapshot: {dupes}")
    for i, a in enumerate(arcs):
        _check(f"active_arcs[{i}] ({a.get('arc_group_id', '?')})", a)

    jokes = (chat_context.get("league_memory", {}) or {}).get("running_jokes", []) or []
    for i, j in enumerate(jokes):
        _check(f"running_jokes[{i}] ({j.get('name', '?')})", j)


def main():
    parser = argparse.ArgumentParser(
        description="Validate sanitizer source artifacts (pre-write) for a given week"
    )
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument(
        "--preseason", action="store_true", help="Validate the preseason artifact"
    )
    args = parser.parse_args()

    if args.preseason:
        if args.week is not None:
            print("ERROR: --week is not valid with --preseason")
            sys.exit(1)
    elif args.week is None:
        print("ERROR: --week is required unless --preseason is set")
        sys.exit(1)

    errors = []

    if args.preseason:
        chat_context = load_json(
            PRESEASON_DIR / "preseason_chat_context.json", required=True
        )
        check_league_memory_present(chat_context, errors)
        check_preseason_type_marker(chat_context, errors)
        check_storyline_layers_populated(chat_context, errors)
        check_arc_and_joke_semantics(chat_context, errors)
        # Deliberately no data/standings load -- preseason has no week data.
        label = "preseason"
    else:
        chat_context = load_json(
            WEEKS_DIR / f"week{args.week}_chat_context.json", required=True
        )
        check_league_memory_present(chat_context, errors)
        check_storyline_layers_populated(chat_context, errors)
        check_arc_and_joke_semantics(chat_context, errors)

        data = load_json(WEEKS_DIR / f"week{args.week}_data.json", required=True)
        for entry in data["standings"]:
            check_as_of_week_fields(entry, errors)
        label = f"week {args.week}"

    if errors:
        print(f"FAIL ({len(errors)} issue(s)):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"PASS — {label} artifacts are as-of-week compliant")


if __name__ == "__main__":
    main()
