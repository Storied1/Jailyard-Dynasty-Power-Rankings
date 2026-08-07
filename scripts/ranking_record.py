"""The ranking record: an ordering grounded in evidence that resolves in a state.

Design section 4 -- "The ranking record grounds an ordering in evidence."

Two deliberate boundaries, stated here so the artifact cannot be misread:

1. THE ORDER IS ARITHMETIC, and it says so in the artifact. It is the ordering
   already precommitted in this repository as the record_points recap basis
   (`LeagueState.standings()`: wins desc, then points-for desc, then roster_id).
   No judgment model is invented here. Choosing a richer ordering after seeing
   the data would be exactly the post-hoc metric selection the design forbids,
   and the arm that was built to earn a richer ordering is dormant.

2. THE EVIDENCE IS NOT ARITHMETIC. Every position carries the facts a reader
   needs to decide whether they disagree with its rank -- the game, the roster,
   the draft, the prior season -- each cited by `fact_id` and each verified to
   resolve in the compiled state before the record is written.

`build_record` refuses to emit a record containing a reference the state cannot
resolve. An unresolvable citation is the failure this artifact exists to prevent.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.compile_state import load_compiled_state  # noqa: E402
    from scripts.eval_arms import rehydrate_state  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from compile_state import load_compiled_state  # noqa: E402
    from eval_arms import rehydrate_state  # noqa: E402
from shared import load_json, save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

ORDERING_RULE = (
    "LeagueState.standings(): wins desc, then points_for desc, then roster_id asc. "
    "This is the record_points arm's recap basis, precommitted before the data was "
    "seen. It is arithmetic over admitted results, not a judgment."
)


class UnresolvedReference(RuntimeError):
    """A cited fact_id is not in the compiled state. Never downgraded to a warning."""


def _identity(state):
    """roster_id -> {name, owner, fact_id, names_available}. Reads the ADMITTED
    identity, so a state compiled before the attestation yields unnamed rosters
    rather than borrowing a later reading."""
    out = {}
    for f in state.by_type("franchise_identity"):
        p = f.payload
        out[p["roster_id"]] = {
            "team_name": p.get("team_name"),
            "owner_id": p.get("owner_id"),
            "display_name": p.get("display_name"),
            "fact_id": f.fact_id,
            "known_at": f.known_at,
            "names_available": not p.get("team_name_unavailable"),
        }
    return out


def _week_results(state, week):
    """roster_id -> the week's game, from admitted matchup_result facts."""
    games = {}
    for f in state.by_type("matchup_result"):
        p = f.payload
        if p.get("week") != week or p.get("season") != state.season:
            continue
        for team, pts, opp, opp_pts in (
            (p["home"], p["home_pts"], p["away"], p["away_pts"]),
            (p["away"], p["away_pts"], p["home"], p["home_pts"]),
        ):
            games[team] = {
                "fact_id": f.fact_id,
                "points_for": pts,
                "points_against": opp_pts,
                "opponent_roster_id": opp,
                "margin": round(pts - opp_pts, 2),
                "outcome": "W" if pts > opp_pts else ("L" if pts < opp_pts else "T"),
                "known_at": f.known_at,
            }
    return games


def _rosters(state):
    out = {}
    for f in state.by_type("roster_membership"):
        p = f.payload
        if not p.get("on_roster"):
            continue
        entry = out.setdefault(p["roster_id"], {"players": 0, "fact_ids": []})
        entry["players"] += 1
        entry["fact_ids"].append(f.fact_id)
    for entry in out.values():
        entry["fact_ids"].sort()
    return out


def _draft(state, season):
    out = {}
    for f in state.by_type("draft_pick"):
        p = f.payload
        rid = str(p.get("roster_id"))
        entry = out.setdefault(rid, {"picks": [], "fact_ids": []})
        entry["picks"].append(
            {
                "round": p.get("round"),
                "pick_no": p.get("pick_no"),
                "player": (p.get("player_name") or p.get("player_id")),
            }
        )
        entry["fact_ids"].append(f.fact_id)
    for entry in out.values():
        entry["picks"].sort(key=lambda x: (x["pick_no"] or 0))
        entry["fact_ids"].sort()
    return out


def _prior_season(state, season):
    """Prior-season finish, RECOMPUTED from admitted historical_matchup facts --
    never a stored season-end aggregate. Cites the facts it was computed from."""
    table = {row["team"]: row for row in state.standings(season=season)}
    used = {}
    for f in state.by_type("historical_matchup"):
        p = f.payload
        if p.get("season") != season:
            continue
        for team in (p["home"], p["away"]):
            used.setdefault(team, []).append(f.fact_id)
    order = sorted(
        table.values(), key=lambda r: (-r["wins"], -r["points_for"], r["team"])
    )
    rank = {row["team"]: i + 1 for i, row in enumerate(order)}
    return {
        rid: {
            "season": season,
            # NOT the final standings. standings() folds every admitted game, so
            # playoff results are included and teams that went deep played more
            # games. Named for what it is, because an aggregate that merely looks
            # plausible is the defect class this whole kernel exists to remove.
            "all_games_rank": rank[rid],
            "basis": "all admitted games including playoffs, not regular season",
            "games": row["wins"] + row["losses"] + row["ties"],
            "wins": row["wins"],
            "losses": row["losses"],
            "points_for": row["points_for"],
            "fact_ids": sorted(used.get(rid, [])),
        }
        for rid, row in table.items()
    }


def build_record(edition_id, week=1):
    doc = load_compiled_state(edition_id)
    state = rehydrate_state(doc)
    descriptor = load_json(
        ROOT / "content" / "editions" / edition_id / "descriptor.json", required=True
    )
    manifest = load_json(
        ROOT / "content" / "editions" / edition_id / "compiled" / "state_manifest.json",
        required=True,
    )

    identity = _identity(state)
    results = _week_results(state, week)
    rosters = _rosters(state)
    draft = _draft(state, state.season)
    prior = _prior_season(state, state.season - 1)
    standings = state.standings()

    positions = []
    for rank, row in enumerate(standings, start=1):
        rid = row["team"]
        ident = identity.get(rid, {})
        game = results.get(rid, {})
        positions.append(
            {
                "rank": rank,
                "roster_id": rid,
                "team_name": ident.get("team_name"),
                "owner_id": ident.get("owner_id"),
                "record": f"{row['wins']}-{row['losses']}"
                + (f"-{row['ties']}" if row["ties"] else ""),
                "points_for": row["points_for"],
                "points_against": row["points_against"],
                "evidence": {
                    "identity": {
                        "fact_id": ident.get("fact_id"),
                        "known_at": ident.get("known_at"),
                    },
                    "week_result": game,
                    "roster": rosters.get(rid, {"players": 0, "fact_ids": []}),
                    "draft": draft.get(rid, {"picks": [], "fact_ids": []}),
                    "prior_season": prior.get(rid),
                },
            }
        )

    record = {
        "record_id": f"{edition_id}-ranking.v1",
        "edition_id": edition_id,
        "season": state.season,
        "week": week,
        "cutoff_utc": descriptor["cutoff_utc"],
        "access_scope": state.access_scope,
        "state_payload_sha256": manifest["state_payload_sha256"],
        "ordering_rule": ORDERING_RULE,
        "what_this_ordering_does_not_encode": [
            "roster strength, injuries, schedule difficulty, or dynasty value",
            "anything the league chat said (admitted to the state, not to this rule)",
            "any judgment: one game of results is a thin basis and the artifact "
            "does not pretend otherwise",
        ],
        "evidence_available_but_unused_by_the_ordering": {
            t: len(state.by_type(t))
            for t in sorted({f.fact_type for f in state.admitted})
        },
        "positions": positions,
    }
    _assert_resolvable(record, state)
    return record


def _collect_ids(node, out):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "fact_id" and isinstance(value, str):
                out.add(value)
            elif key == "fact_ids" and isinstance(value, list):
                out.update(value)
            else:
                _collect_ids(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_ids(item, out)


def _assert_resolvable(record, state):
    """Every citation must resolve in the state the record was built from.

    Checked against `state.admitted` -- the facts this cutoff actually admits --
    not against the whole store, so a citation of a real-but-inadmissible fact is
    a failure rather than a silent pass.
    """
    cited = set()
    _collect_ids(record, cited)
    available = {f.fact_id for f in state.admitted}
    missing = sorted(cited - available)
    if missing:
        raise UnresolvedReference(
            f"{len(missing)} cited fact_ids do not resolve in {record['edition_id']}: "
            f"{missing[:3]}"
        )
    record["citation_count"] = len(cited)
    return len(cited)


def main():
    ap = argparse.ArgumentParser(prog="ranking_record.py")
    ap.add_argument("--edition", default="2025-wk01-recap")
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument(
        "--out", help="default: content/editions/<edition>/ranking_record.json"
    )
    ap.add_argument("--print", action="store_true", help="human-readable to stdout")
    a = ap.parse_args()
    record = build_record(a.edition, a.week)
    out = (
        Path(a.out)
        if a.out
        else ROOT / "content" / "editions" / a.edition / "ranking_record.json"
    )
    save_json_canonical(out, record)
    if a.print:
        print(render(record))
    else:
        print(f"{out}  ({record['citation_count']} resolved citations)")
    return 0


def render(record):
    """Plain readable form. No prose, no narrative -- the evidence, in order."""
    lines = [
        f"{record['edition_id']}  cutoff {record['cutoff_utc']}  "
        f"({record['citation_count']} citations, all resolving)",
        "",
    ]
    for p in record["positions"]:
        g = p["evidence"]["week_result"]
        prior = p["evidence"]["prior_season"] or {}
        lines.append(
            f"{p['rank']:>2}. {p['team_name'] or '(name unavailable)':<26} "
            f"{p['record']:<5} {p['points_for']:>7.2f} PF"
        )
        if g:
            lines.append(
                f"     wk{record['week']}: {g['outcome']} {g['points_for']:.2f}-"
                f"{g['points_against']:.2f} vs roster {g['opponent_roster_id']} "
                f"(margin {g['margin']:+.2f})"
            )
        if prior:
            lines.append(
                f"     {prior['season']}: {prior['wins']}-{prior['losses']} over "
                f"{prior['games']} games (all games incl. playoffs), "
                f"{prior['points_for']:.2f} PF, #{prior['all_games_rank']} by that measure"
            )
        lines.append(
            f"     roster {p['evidence']['roster']['players']} players | "
            f"{len(p['evidence']['draft']['picks'])} draft picks"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
