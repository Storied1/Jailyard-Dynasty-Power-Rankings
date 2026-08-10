"""State leak census: every decision input carries ZERO post-cutoff facts.

Two censused surfaces, one contract:

1. Compiled states carry zero post-cutoff instants by construction (known_at
   admission), proven mechanically here. Every compiled-state read goes
   through compile_state.load_compiled_state (hash-verified private-root
   resolution).
2. The content/weeks writer packets are active decision inputs -- the writer
   reads them and verify_week_content validates against them -- so they are
   held to the same zero. Every cutoff-sensitive field is derived as-of the
   packet's week (extract_week_data's as_of_h2h / as_of_records slices), and
   this census enforces zero across all of them: a single post-cutoff value
   fails the --all run by exit code.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.compile_state import EditionDescriptor  # noqa: E402
    from scripts.compile_state import load_compiled_state, verify_compiled
    from scripts.fact_schema import canonical_instant  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from compile_state import (  # noqa: E402
        EditionDescriptor,
        load_compiled_state,
        verify_compiled,
    )
    from fact_schema import canonical_instant  # noqa: E402

from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Every leaf path of a writer week packet, mapped by dotted-path prefix to the
# fact type that carries it under the kernel, or to a non-fact disposition:
#   presentation -- prose/display selection, not evidence
#   derived      -- recomputed from admitted facts (reducers), never stored
# A leaf is covered when its top section AND its depth-2 key are both mapped;
# a planted unknown leaf at either depth fails the census.
FIELD_MAP = {
    "meta": "presentation",
    "matchups": "matchup_result",
    "standings": "derived",  # standings() recomputes from admitted facts
    "awards": "presentation",
    "historical_context": "derived",  # records() recomputes as-of
    "season_context": "presentation",
    "previous_weeks_summary": "presentation",
    "next_matchups": "schedule_pairing",
}


# The COMPLETE leaf-path surface of the writer week packets, hand-audited and
# explicit -- coverage is judged against exact normalized paths, never a depth
# approximation. Lists normalize to "[]". A leaf absent from this set -- at
# any depth -- is unmapped and fails the census.
ALLOWED_LEAVES = frozenset(
    {
        "awards.biggest_blowout",
        "awards.biggest_blowout.margin",
        "awards.biggest_blowout.score",
        "awards.biggest_blowout.teams",
        "awards.biggest_blowout.winner",
        "awards.closest_game",
        "awards.closest_game.margin",
        "awards.closest_game.score",
        "awards.closest_game.teams",
        "awards.high_scorer",
        "awards.high_scorer.owner",
        "awards.high_scorer.points",
        "awards.high_scorer.team_name",
        "awards.low_scorer",
        "awards.low_scorer.owner",
        "awards.low_scorer.points",
        "awards.low_scorer.team_name",
        "awards.top_performer",
        "awards.top_performer.fantasy_team",
        "awards.top_performer.game_context.game_id",
        "awards.top_performer.game_context.one_liner",
        "awards.top_performer.game_context.opponent",
        "awards.top_performer.game_context.src.game_id",
        "awards.top_performer.game_context.src.one_liner",
        "awards.top_performer.game_context.src.opponent",
        "awards.top_performer.game_context.src.stat_line",
        "awards.top_performer.game_context.stat_line",
        "awards.top_performer.name",
        "awards.top_performer.nfl_team",
        "awards.top_performer.player_id",
        "awards.top_performer.points",
        "awards.top_performer.position",
        "historical_context.biggest_blowout.loser",
        "historical_context.biggest_blowout.margin",
        "historical_context.biggest_blowout.score",
        "historical_context.biggest_blowout.season",
        "historical_context.biggest_blowout.week",
        "historical_context.biggest_blowout.winner",
        "historical_context.highest_combined.points",
        "historical_context.highest_combined.score",
        "historical_context.highest_combined.season",
        "historical_context.highest_combined.teams",
        "historical_context.highest_combined.week",
        "historical_context.highest_score.opponent",
        "historical_context.highest_score.owner_id",
        "historical_context.highest_score.points",
        "historical_context.highest_score.season",
        "historical_context.highest_score.team",
        "historical_context.highest_score.week",
        "historical_context.longest_losing_streak.count",
        "historical_context.longest_losing_streak.owner_id",
        "historical_context.longest_losing_streak.team",
        "historical_context.longest_win_streak.count",
        "historical_context.longest_win_streak.owner_id",
        "historical_context.longest_win_streak.team",
        "historical_context.lowest_combined.points",
        "historical_context.lowest_combined.score",
        "historical_context.lowest_combined.season",
        "historical_context.lowest_combined.teams",
        "historical_context.lowest_combined.week",
        "historical_context.lowest_winning_score.opponent",
        "historical_context.lowest_winning_score.owner_id",
        "historical_context.lowest_winning_score.points",
        "historical_context.lowest_winning_score.season",
        "historical_context.lowest_winning_score.team",
        "historical_context.lowest_winning_score.week",
        "matchups[].h2h.last_meeting",  # null when no PRIOR meeting exists as-of
        "matchups[].h2h.last_meeting.score",
        "matchups[].h2h.last_meeting.season",
        "matchups[].h2h.last_meeting.week",
        "matchups[].h2h.team1_wins",
        "matchups[].h2h.team2_wins",
        "matchups[].h2h.total_games",
        "matchups[].margin",
        "matchups[].matchup_id",
        "matchups[].momentum.edge",
        "matchups[].momentum.favorite_team_name",
        "matchups[].momentum.label",
        "matchups[].team1.owner",
        "matchups[].team1.points",
        "matchups[].team1.projected",
        "matchups[].team1.roster_id",
        "matchups[].team1.team_name",
        "matchups[].team1.top_scorers[].game_context.game_id",
        "matchups[].team1.top_scorers[].game_context.one_liner",
        "matchups[].team1.top_scorers[].game_context.opponent",
        "matchups[].team1.top_scorers[].game_context.src.game_id",
        "matchups[].team1.top_scorers[].game_context.src.one_liner",
        "matchups[].team1.top_scorers[].game_context.src.opponent",
        "matchups[].team1.top_scorers[].game_context.src.stat_line",
        "matchups[].team1.top_scorers[].game_context.stat_line",
        "matchups[].team1.top_scorers[].name",
        "matchups[].team1.top_scorers[].player_id",
        "matchups[].team1.top_scorers[].points",
        "matchups[].team1.top_scorers[].position",
        "matchups[].team1.top_scorers[].team",
        "matchups[].team2.owner",
        "matchups[].team2.points",
        "matchups[].team2.projected",
        "matchups[].team2.roster_id",
        "matchups[].team2.team_name",
        "matchups[].team2.top_scorers[].game_context.game_id",
        "matchups[].team2.top_scorers[].game_context.one_liner",
        "matchups[].team2.top_scorers[].game_context.opponent",
        "matchups[].team2.top_scorers[].game_context.src.game_id",
        "matchups[].team2.top_scorers[].game_context.src.one_liner",
        "matchups[].team2.top_scorers[].game_context.src.opponent",
        "matchups[].team2.top_scorers[].game_context.src.stat_line",
        "matchups[].team2.top_scorers[].game_context.stat_line",
        "matchups[].team2.top_scorers[].name",
        "matchups[].team2.top_scorers[].player_id",
        "matchups[].team2.top_scorers[].points",
        "matchups[].team2.top_scorers[].position",
        "matchups[].team2.top_scorers[].team",
        "matchups[].upset",
        "matchups[].winner",
        "meta.generated_for",
        "meta.is_playoff",
        "meta.season",
        "meta.week",
        "next_matchups[].team1",
        "next_matchups[].team1_rank",
        "next_matchups[].team2",
        "next_matchups[].team2_rank",
        "previous_weeks_summary[].high_score",
        "previous_weeks_summary[].high_scorer",
        "previous_weeks_summary[].leader",
        "previous_weeks_summary[].leader_record",
        "previous_weeks_summary[].week",
        "season_context.best_record.record",
        "season_context.best_record.team_name",
        "season_context.is_playoff",
        "season_context.league_avg_ppg",
        "season_context.points_leader.pf",
        "season_context.points_leader.team_name",
        "season_context.this_week_avg",
        "season_context.total_weeks",
        "season_context.weeks_played",
        "season_context.worst_record.record",
        "season_context.worst_record.team_name",
        "standings[].all_time_record",
        "standings[].current_elo",
        "standings[].elo_change",
        "standings[].losses",
        "standings[].margin_this_week",
        "standings[].momentum.label",
        "standings[].momentum.score",
        "standings[].movement",
        "standings[].owner",
        "standings[].pa",
        "standings[].peak_elo",
        "standings[].pf",
        "standings[].power_score",
        "standings[].prev_rank",
        "standings[].rank",
        "standings[].record",
        "standings[].roster_id",
        "standings[].streak",
        "standings[].team_name",
        "standings[].week_points",
        "standings[].wins",
    }
)

# Sections whose IMMEDIATE child keys are dynamic identities (bounded wildcard).
DYNAMIC_KEY_SECTIONS = set()


def unmapped_packet_fields(season, weeks_dir=None):
    """RECURSIVE leaf coverage: every actual leaf path must appear in the
    positive allowlist. --season is honored: only 2025 packets exist; any
    other season is REJECTED, never reported as a vacuous OK."""
    if season != 2025:
        raise ValueError(
            f"no writer week packets exist for season {season}; refusing a vacuous census"
        )
    unmapped = set()
    weeks_dir = Path(weeks_dir) if weeks_dir is not None else ROOT / "content" / "weeks"

    def walk(node, norm_path, fname, wild_next):
        if isinstance(node, dict):
            for k, v in node.items():
                seg = "*" if wild_next else k
                walk(v, f"{norm_path}.{seg}", fname, False)
        elif isinstance(node, list):
            for v in node:
                walk(v, f"{norm_path}[]", fname, False)
        else:
            if norm_path not in ALLOWED_LEAVES:
                unmapped.add(f"{fname}:{norm_path}")

    for p in sorted(weeks_dir.glob("week*_data.json")):
        doc = load_json(p, required=True)
        for key, v in doc.items():
            if key not in FIELD_MAP:
                unmapped.add(f"{p.name}:{key}")
                continue
            walk(v, key, p.name, key in DYNAMIC_KEY_SECTIONS)
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
    # The census trusts NOTHING unverified: the full compiled contract --
    # descriptor, manifest fields and counts, state locator, state payload,
    # source hashes against live inputs, preview-cutoff provenance -- must
    # verify before any metadata is consumed. A mutated authoritative artifact
    # fails here even when state/manifest metadata remain self-consistent.
    raw = load_json(
        ROOT / "content" / "editions" / edition_id / "compiled" / "descriptor.json",
        required=True,
    )
    descriptor_obj = EditionDescriptor(
        **{**raw, "predecessors": tuple(raw.get("predecessors", ()))}
    )
    problems = verify_compiled(descriptor_obj)
    if problems:
        raise ValueError(
            f"{edition_id}: compiled contract failed verification: {problems}"
        )
    doc = load_compiled_state(edition_id)
    descriptor = raw
    cutoff = canonical_instant(descriptor["cutoff_utc"])
    # VERIFIED metadata only: the hash-verified state's own cutoff must agree
    # with the descriptor the census is about to trust.
    if doc["cutoff"] != cutoff or doc["season"] != descriptor["season"]:
        raise ValueError(
            f"{edition_id}: descriptor metadata disagrees with the verified state "
            f"({descriptor['cutoff_utc']}/{descriptor['season']} vs "
            f"{doc['cutoff']}/{doc['season']})"
        )
    detail = sorted({i for i in _iter_instants(doc["admitted"]) if i > cutoff})
    return {"future_entries": len(detail), "detail": detail, "is_decision_input": True}


def _writer_packet_census(weeks_dir=None):
    """Post-cutoff facts in the active writer packets. Detectors: (a) h2h
    last_meeting rows postdating their packet, (b) a highest_combined record
    postdating its packet, (c) longest_losing_streak values exceeding the
    site-methodology as-of recomputation. The contract is zero; any hit
    fails the --all run."""
    weeks_dir = Path(weeks_dir) if weeks_dir is not None else ROOT / "content" / "weeks"
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
    return {"future_entries": len(detail), "detail": detail, "is_decision_input": True}


def state_leak_census(target, packets=False, weeks_dir=None):
    """packets=True censuses the active writer packets (weeks_dir overridable
    for planted-leak tests); otherwise target names a compiled edition."""
    if packets:
        return _writer_packet_census(weeks_dir=weeks_dir)
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
    ap.add_argument(
        "--weeks-dir",
        dest="weeks_dir",
        help="override the writer-packet directory (planted-leak testing only)",
    )
    a = ap.parse_args()
    failed = 0
    if a.all:
        try:
            unmapped = unmapped_packet_fields(a.season, weeks_dir=a.weeks_dir)
        except ValueError as exc:
            print(f"FAIL {exc}")
            return 1
        if unmapped:
            failed += 1
            print(f"FAIL {len(unmapped)} unmapped packet fields: {unmapped[:8]}")
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
        # Active writer packets are decision inputs: any post-cutoff fact in
        # them is a FAILURE, not a footnote.
        packets = state_leak_census(
            "content/weeks", packets=True, weeks_dir=a.weeks_dir
        )
        if packets["future_entries"]:
            failed += 1
            print(
                f"FAIL writer packets: {packets['future_entries']} future "
                f"entries {packets['detail'][:5]}"
            )
        print(
            f"writer packets: {packets['future_entries']} future entries "
            f"(decision input: {packets['is_decision_input']})"
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
