"""Migration checks and the state leak census. K2.3 of plan 562e90d.

The design demotes the source census to a migration check -- "did every legacy
field find a fact type" -- and adds a mechanical leak census: compiled states
must carry ZERO post-cutoff instants (by construction, proven here), while the
legacy week packets still carry their 46 confirmed future entries and are no
longer decision inputs. Every compiled-state read goes through
compile_state.load_compiled_state (hash-verified private-root resolution).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.compile_state import load_compiled_state  # noqa: E402
    from scripts.fact_schema import canonical_instant  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from compile_state import load_compiled_state  # noqa: E402
    from fact_schema import canonical_instant  # noqa: E402
from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Every top-level section of a legacy week packet, mapped to the fact type that
# carries it under the kernel, or to a non-fact disposition:
#   presentation -- prose/display selection, not evidence
#   derived      -- recomputed from admitted facts (reducers), never stored
FIELD_MAP = {
    "meta": "presentation",
    "matchups": "matchup_result",
    "standings": "derived",  # standings() recomputes from admitted facts
    "awards": "presentation",
    "historical_context": "derived",  # records() recomputes; the 46 lived here
    "season_context": "presentation",
    "team_profiles_summary": "presentation",
    "previous_weeks_summary": "presentation",
    "next_matchups": "schedule_pairing",
}


def unmapped_legacy_fields(season):
    """Top-level packet sections with no fact-type or disposition mapping."""
    unmapped = set()
    weeks_dir = ROOT / "content" / "weeks"
    for p in sorted(weeks_dir.glob("week*_data.json")):
        doc = load_json(p, required=True)
        for key in doc:
            if key not in FIELD_MAP:
                unmapped.add(f"{p.name}:{key}")
    return sorted(unmapped)


def _iter_instants(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "captured_at":
                # The custody clock legitimately postdates a backtest cutoff
                # (design: latest reconstruction "including facts captured
                # afterward"). The leak census is about KNOWLEDGE clocks.
                continue
            yield from _iter_instants(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_instants(v)
    elif isinstance(obj, str):
        c = canonical_instant(obj)
        if c is not None:
            yield c


def _compiled_leak_census(edition_id):
    """Zero post-cutoff instants, mechanically: every temporal string anywhere
    in the compiled state must be <= the descriptor cutoff."""
    doc = load_compiled_state(edition_id)
    descriptor = load_json(
        ROOT / "content" / "editions" / edition_id / "compiled" / "descriptor.json",
        required=True,
    )
    cutoff = canonical_instant(descriptor["cutoff_utc"])
    detail = sorted({i for i in _iter_instants(doc["admitted"]) if i > cutoff})
    return {"future_entries": len(detail), "detail": detail, "is_decision_input": True}


def _legacy_packet_census():
    """The 46, re-derived: (a) h2h last_meeting rows postdating their packet,
    (b) the week-14 highest_combined present in packets 1-13, (c) undated
    longest_losing_streak values exceeding the kernel's as-of recomputation."""
    weeks_dir = ROOT / "content" / "weeks"
    conclusions = load_json(
        ROOT / "content" / "governance" / "week_conclusions_2022_2025.v1.json",
        required=True,
    )["weeks"]
    detail = []

    site_games = None
    # The census recomputes the PACKET'S OWN aggregate methodology as-of --
    # regular-season weeks (<= 14) only, per the committed values -- not the
    # kernel's all-games records() definition. The leak to detect is the site's
    # committed value versus the site's correct value; the kernel deliberately
    # defines streaks over every played game, which is a different (documented)
    # aggregate and would mask this packet's leak by coincidence of values.

    def site_streak_through(week):
        nonlocal site_games
        if site_games is None:
            site_games = []
            for season in (2022, 2023, 2024, 2025):
                sc = load_json(
                    ROOT / f"data/{season}/season_combined.json", required=True
                )
                for wk in sc["weeks"]:
                    if wk["week"] > 14:
                        continue  # site streaks: regular season only
                    for m in wk["matchups"]:
                        site_games.append((season, wk["week"], m))
        best = 0
        streaks = {}
        for season, wk, m in sorted(site_games, key=lambda g: (g[0], g[1])):
            if season == 2025 and wk > week:
                continue
            for mine, opp in ((m["team1"], m["team2"]), (m["team2"], m["team1"])):
                rid = mine["roster_id"]
                if mine["points"] < opp["points"]:
                    streaks[rid] = streaks.get(rid, 0) + 1
                    best = max(best, streaks[rid])
                else:
                    streaks[rid] = 0
        return best

    for p in sorted(
        weeks_dir.glob("week*_data.json"), key=lambda q: int(q.stem.split("_")[0][4:])
    ):
        week = int(p.stem.split("_")[0][4:])
        doc = load_json(p, required=True)
        for m in doc.get("matchups", []):
            lm = (m.get("h2h") or {}).get("last_meeting") or {}
            if lm.get("season") == 2025 and (lm.get("week") or 0) > week:
                detail.append(f"{p.name}: h2h last_meeting wk{lm['week']}")
        hc = doc.get("historical_context") or {}
        comb = hc.get("highest_combined") or {}
        if comb.get("season") == 2025 and (comb.get("week") or 0) > week:
            detail.append(f"{p.name}: highest_combined wk{comb['week']}")
        streak = hc.get("longest_losing_streak") or {}
        committed = streak.get("count")
        if committed is not None and f"2025:{week}" in conclusions:
            correct = site_streak_through(week)
            if committed > correct:
                detail.append(
                    f"{p.name}: longest_losing_streak {committed} > as-of {correct}"
                )
    return {"future_entries": len(detail), "detail": detail, "is_decision_input": False}


def state_leak_census(target, legacy=False):
    if legacy:
        return _legacy_packet_census()
    edition_id = str(target).rstrip("/").split("/")[-1]
    return _compiled_leak_census(edition_id)


def main():
    ap = argparse.ArgumentParser(prog="migration_census.py")
    # Required mutually-exclusive group: a bare invocation errors at exit 2,
    # never calls state_leak_census(None).
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--edition")
    ap.add_argument("--season", type=int, default=2025)
    a = ap.parse_args()
    failed = 0
    if a.all:
        unmapped = unmapped_legacy_fields(a.season)
        if unmapped:
            failed += 1
            print(f"FAIL {len(unmapped)} unmapped legacy fields: {unmapped[:8]}")
        # Discover MANIFESTS -- the tracked state.json path is abolished.
        editions = sorted(
            p.parent.parent.name
            for p in (ROOT / "content" / "editions").glob(
                "*/compiled/state_manifest.json"
            )
        )
        if not editions:
            print("FAIL discovered 0 compiled states; --all must not pass vacuously")
            return 1
        for e in editions:
            r = state_leak_census(e)
            if r["future_entries"]:
                failed += 1
                print(
                    f"FAIL {e}: {r['future_entries']} future entries {r['detail'][:3]}"
                )
        legacy = state_leak_census("content/weeks", legacy=True)
        print(
            f"legacy packets: {legacy['future_entries']} future entries "
            f"(decision input: {legacy['is_decision_input']})"
        )
    else:
        r = state_leak_census(a.edition)
        if r["future_entries"]:
            failed += 1
            print(f"FAIL {a.edition}: {r['detail'][:5]}")
    print("OK" if not failed else f"{failed} failure(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
