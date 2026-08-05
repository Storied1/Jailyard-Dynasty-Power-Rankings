"""The single temporal authority. state_at is the world, never our judgments about it.

Contract: docs/superpowers/plans/2026-08-02-jailyard-temporal-kernel.md K1.3 + K1.4.
Admission is a known_at question evaluated against the scope lattice; folding is
an effective_at question; supersession retires only against ADMITTED facts.
Aggregates are recomputed from admitted facts -- standings() is SEASON-QUALIFIED,
h2h() and records() are deliberately all-time (League Bible framing).
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_schema import (
        canonical_instant,  # noqa: E402, F401
        load_fact_types,
    )
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import canonical_instant, load_fact_types  # noqa: E402, F401

SCOPE_LATTICE = {
    "public": {"public"},
    "league_private": {"public", "league_private"},
}

FACTS_ROOT = Path(__file__).resolve().parents[1] / "data" / "facts"
PRIVATE_FACTS_ROOT = Path(__file__).resolve().parents[1] / "private_facts"


@dataclass(frozen=True)
class LeagueState:
    season: int
    cutoff: str
    access_scope: str
    as_recorded_at: str | None
    admitted: list
    private_root_absent: bool = False

    def by_type(self, fact_type):
        """Admitted facts of a type, in EFFECTIVE order.

        Admission is a known_at question; folding is an effective_at question.
        The design separates them deliberately: a correction learned in December
        about a September game is admitted by its December known_at, but it folds
        into the timeline at its September effective_at.
        """
        return sorted(
            (f for f in self.admitted if f.fact_type == fact_type),
            key=lambda f: (f.effective_at, f.source_record_id, f.fact_id),
        )

    def value(self, fact_type, source_record_id):
        """Supersession resolution: the latest KNOWN reading of one record.

        Ordered by known_at, not effective_at -- a later correction supersedes an
        earlier one because we learned it later, whatever instant it describes.
        Keyed on (fact_type, source_record_id), mirroring FactStore._latest_for:
        two types sharing a record id must never resolve into each other.
        """
        live = [
            f
            for f in self.admitted
            if f.fact_type == fact_type and f.source_record_id == source_record_id
        ]
        return max(live, key=lambda f: (f.known_at, f.fact_id)) if live else None

    # ------------------------------------------------------------------ K1.4
    def h2h(self, a, b):
        """Head-to-head from admitted meetings only. Never a stored aggregate.

        All-time by design (the League Bible framing): pre-2025 historical
        meetings count. Ties are a first-class outcome -- a tied meeting is
        never silently credited to the away team.
        """
        games = [
            f
            for f in self.by_type("matchup_result") + self.by_type("historical_matchup")
            if {f.payload["home"], f.payload["away"]} == {a, b}
        ]
        # effective_at, not payload season/week: the fact's own clock is the
        # authority, and a reducer that re-derives ordering from payload fields
        # is a second temporal rule.
        games.sort(key=lambda f: (f.effective_at, f.fact_id))
        a_wins = sum(1 for g in games if _winner(g.payload) == a)
        ties = sum(1 for g in games if _winner(g.payload) is None)
        last = games[-1].payload if games else None
        return {
            "a_wins": a_wins,
            "b_wins": len(games) - a_wins - ties,
            "ties": ties,
            "total_games": len(games),
            "last_meeting": last,
        }

    def records(self):
        """All seven league records, recomputed. Dated and undated alike.
        All-time by design; no stored value exists to read."""
        games = self.by_type("matchup_result") + self.by_type("historical_matchup")
        rec = dict.fromkeys(
            (
                "highest_score",
                "lowest_winning_score",
                "biggest_blowout",
                "highest_combined",
                "lowest_combined",
            )
        )
        streaks = {}
        for g in sorted(games, key=lambda f: (f.effective_at, f.fact_id)):
            p = g.payload
            for team, pts, opp in (
                (p["home"], p["home_pts"], p["away_pts"]),
                (p["away"], p["away_pts"], p["home_pts"]),
            ):
                cand = {
                    "points": pts,
                    "team": team,
                    "season": p["season"],
                    "week": p["week"],
                }
                if rec["highest_score"] is None or pts > rec["highest_score"]["points"]:
                    rec["highest_score"] = cand
                if pts > opp and (
                    rec["lowest_winning_score"] is None
                    or pts < rec["lowest_winning_score"]["points"]
                ):
                    rec["lowest_winning_score"] = cand
                d = streaks.setdefault(team, {"cw": 0, "cl": 0, "bw": 0, "bl": 0})
                if pts > opp:
                    d["cw"] += 1
                    d["cl"] = 0
                    d["bw"] = max(d["bw"], d["cw"])
                elif pts < opp:
                    d["cl"] += 1
                    d["cw"] = 0
                    d["bl"] = max(d["bl"], d["cl"])
                else:  # a tie breaks both streaks and extends neither
                    d["cw"] = 0
                    d["cl"] = 0
            margin = abs(p["home_pts"] - p["away_pts"])
            if (
                rec["biggest_blowout"] is None
                or margin > rec["biggest_blowout"]["margin"]
            ):
                rec["biggest_blowout"] = {
                    "margin": round(margin, 2),
                    "season": p["season"],
                    "week": p["week"],
                }
            comb = {
                "points": round(p["home_pts"] + p["away_pts"], 2),
                "season": p["season"],
                "week": p["week"],
            }
            for key, better in (
                ("highest_combined", lambda x, y: x > y),
                ("lowest_combined", lambda x, y: x < y),
            ):
                if rec[key] is None or better(comb["points"], rec[key]["points"]):
                    rec[key] = comb
        for key, field in (
            ("longest_win_streak", "bw"),
            ("longest_losing_streak", "bl"),
        ):
            if streaks:
                best = max(v[field] for v in streaks.values())
                team = sorted(t for t, v in streaks.items() if v[field] == best)[0]
                rec[key] = {"count": best, "team": team}
            else:
                rec[key] = None
        return rec

    def standings(self, season=None):
        """Win/loss/points-for from admitted results only, SEASON-QUALIFIED.

        The pool is deliberately not season-filtered (pre-2025 facts belong in a
        2025 state so the no-history arm can ablate them), which makes this
        reducer the only correct place for the season predicate. Without it,
        2022-2024 historical_matchup facts inflate a 2025 week-3 table to ~120
        games played -- silently, since the output still looks plausible.
        `season=None` means this state's own season; K3's record_points arm
        passes the PRIOR season explicitly at preseason/preview.
        """
        season = self.season if season is None else season
        table = {}
        for g in self.by_type("matchup_result") + self.by_type("historical_matchup"):
            p = g.payload
            if p["season"] != season:
                continue
            for team, pts, opp in (
                (p["home"], p["home_pts"], p["away_pts"]),
                (p["away"], p["away_pts"], p["home_pts"]),
            ):
                t = table.setdefault(
                    team,
                    {
                        "team": team,
                        "wins": 0,
                        "losses": 0,
                        "ties": 0,
                        "points_for": 0.0,
                        "points_against": 0.0,
                    },
                )
                t["wins"] += pts > opp
                t["losses"] += pts < opp
                t["ties"] += pts == opp
                t["points_for"] = round(t["points_for"] + pts, 2)
                t["points_against"] = round(t["points_against"] + opp, 2)
        return sorted(
            table.values(), key=lambda r: (-r["wins"], -r["points_for"], r["team"])
        )


def _winner(p):
    """None on a tie -- fantasy ties are rare but real (Sleeper roster settings
    carry a `ties` field), and h2h must agree with standings' tie column."""
    if p["home_pts"] == p["away_pts"]:
        return None
    return p["home"] if p["home_pts"] > p["away_pts"] else p["away"]


def state_at(season, cutoff, access_scope, as_recorded_at=None, facts=None):
    if access_scope not in SCOPE_LATTICE:
        raise ValueError(
            f"access_scope must be one of {sorted(SCOPE_LATTICE)}; "
            "an omitted or unrecognized scope is an error, never a default"
        )
    # BOTH sides of every temporal comparison are canonical: fact instants are
    # canonicalized at construction, and the cutoff/vantage here -- otherwise a
    # fact .000001s past a whole-second cutoff would still string-compare below
    # the short form and be admitted.
    cutoff = canonical_instant(cutoff)
    as_recorded_at = canonical_instant(as_recorded_at) if as_recorded_at else None
    if cutoff is None:
        raise ValueError("cutoff must be an exact UTC instant")
    private_root_absent = False
    if facts is not None:
        pool = list(facts)
    else:
        pool, private_root_absent = _load_default_facts(season)
        if access_scope == "league_private" and private_root_absent:
            # Fail closed: a league_private compile on a clone without the
            # private root must not silently produce a chat-free state that
            # claims the full scope.
            raise FileNotFoundError(
                f"private fact store absent for season {season}; a league_private "
                "state cannot be compiled without local private rehydration"
            )

    admitted = [
        f
        for f in pool
        if f.access_scope in SCOPE_LATTICE[access_scope]
        and f.known_at <= cutoff
        and (as_recorded_at is None or f.captured_at <= as_recorded_at)
    ]
    # Drop anything superseded by another ADMITTED fact. A superseding fact that
    # is itself inadmissible at this cutoff must not retire its predecessor.
    retired = {f.supersedes for f in admitted if f.supersedes}
    admitted = sorted(
        (f for f in admitted if f.fact_id not in retired),
        key=lambda f: (f.fact_type, f.source_record_id, f.known_at, f.fact_id),
    )
    return LeagueState(
        season, cutoff, access_scope, as_recorded_at, admitted, private_root_absent
    )


def _load_default_facts(season):
    """Exactly one PUBLIC file plus one PRIVATE file, each named for the season.
    Never a glob over either root -- that is how a poisoned sibling store enters
    a state it does not belong to. FACTS_ROOT / PRIVATE_FACTS_ROOT are module
    globals read at call time so tests can relocate them. The private store is
    LOCAL REHYDRATION (gitignored); its absence is reported so a public clone
    fails closed on league_private editions."""
    try:
        from scripts.fact_store import FactStore
    except ImportError:  # pragma: no cover - direct-run fallback
        from fact_store import FactStore
    path = FACTS_ROOT / f"{season}.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"no fact store for season {season} at {path}; normalize before compiling"
        )
    facts = FactStore(path).load()
    private_path = PRIVATE_FACTS_ROOT / f"{season}.jsonl"
    private_root_absent = not private_path.exists()
    if not private_root_absent:
        facts += FactStore(private_path).load()
    return facts, private_root_absent
