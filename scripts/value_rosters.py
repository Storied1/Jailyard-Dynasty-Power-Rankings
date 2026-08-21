"""The valuation desk: derive roster value from evidence, on two axes, in tiers.

Productionised from three scratch prototypes (desk.py/desk2.py/desk3.py,
2026-08-19) after adversarial verification. The three confirmed defects those
prototypes carried are pinned by scripts/tests/test_value_rosters.py and must
not be reintroduced:

  BUG 1  season_aggregates.weeks_played counts ROSTER weeks, not appearances.
         Rates are computed from weekly[] rows where fantasy_points > 0.
  BUG 2  a minimum-games threshold DELETED contrary seasons. Every season the
         career covers is scored; missing time costs.
  BUG 3  rookie value anchored to its own position's replacement inflated
         rookie QBs. Rookie value is expressed directly in points over
         replacement, position-neutral.

THE TWO AXES (they correlate at rho ~= -0.16 in this league; they are
different questions and both are reported):

  PRESENT  2025 win-now strength: best legal lineup in points over
           replacement, blending per-appearance rate and per-week
           availability, plus half the best bench piece at RB/WR/TE.
  ASSET    dynasty asset value: every player's over-replacement production
           discounted by an age curve, so a 30-year-old bell cow and a
           23-year-old bell cow stop being the same asset.

Only QB/RB/WR/TE differentiate. K/DEF/DL/LB/DB are excluded because the
league streams them (zero trades in four years, fewer DBs rostered than
started) and they are structurally flat; they still produce 31% of scoring,
which is a fact about the format, not about any roster.

Output is TIERS with an uncertainty band per team, never a false 1-12: every
constant here is arguable, so the desk jointly perturbs all of them and
reports the p5-p95 rank band. Adjacent teams whose bands overlap share a
tier. What the desk cannot see is listed in `not_encoded` in the output;
future draft-pick capital is the big one (the transaction log carries no
traded picks), so pick debts like a traded 2026 first are editorial facts,
not model facts.

Post-cutoff safety: only seasons <= 2024 are read from the arcs (the edition
cutoff is 2025-09-03, before any 2025 game), and ages come from birth_date
computed AT the cutoff, never from the fetch-time `age` field.

Run:  python scripts/value_rosters.py [--runs 200] [--seed 11]
                                      [--out PATH]
Local-only inputs: the private preseason bundle and data/players.json.
"""

import argparse
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import load_json, save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "private_bundles" / "preseason-2025" / "preseason_evidence.json"
ARCS = ROOT / "data" / "2025" / "player_arcs"
PLAYERS = ROOT / "data" / "players.json"

CUTOFF = date(2025, 9, 3)
MAX_SEASON = 2024  # nothing from 2025 onward is admissible at this cutoff
SEASON_W = {2024: 0.70, 2023: 0.30}
SEASON_WEEKS = 17
MIN_RATE_GAMES = 3  # a 1-2 game sample is not a rate (it still counts in avail)

LINEUP = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX"]
FLEX_OK = {"RB", "WR", "TE"}
DIFFERENTIATING = {"QB"} | FLEX_OK
STARTED = {"QB": 12, "RB": 24, "WR": 36, "TE": 12}
FLEX_EXTRA = {"RB": 5, "WR": 5, "TE": 2}

ROOKIE_PEAK = 6.0  # points over replacement at pick 1
ROOKIE_ZERO_PICK = 30  # decays to zero here

# Age curve per position: full value through peak_end, linear to a 0.1 floor
# at cliff, a small premium below the peak (youth is optionality).
AGE_CURVE = {"QB": (30, 40), "RB": (24, 31), "WR": (26, 33), "TE": (27, 34)}
YOUTH_PREMIUM = 0.05  # per year under peak_end, capped at 1.15 total
ROOKIE_DEFAULT_AGE = 22.5

OWNER = {
    "GauchoTrain": "Brent",
    "bchodos": "Ben",
    "kharlow": "Harlow",
    "kevobucks": "Kevin",
    "KidBouzie": "Karim",
    "ToreroGaucho": "Patrick",
    "Chudders": "Matt",
    "rango_": "Nate",
    "Redrumsregrub": "David",
    "bLaker24": "Blake",
    "zbcowan": "Zach",
    "GrayskullXX": "Oscar",
}

NOT_ENCODED = [
    "future draft-pick capital: the transaction log carries no traded picks, "
    "so pick debts and credits (e.g. a traded 2026 first) are editorial "
    "facts, not model facts",
    "coaching/scheme/camp context: the desk reads production history only",
    "K/DEF/DL/LB/DB rosters: streamed weekly by league practice, so a "
    "September snapshot of them carries no signal (they still score 31% of "
    "league points; that is a format fact, not a roster fact)",
    "any 2025 result: the season had not started at the cutoff",
]


# ---- player values ---------------------------------------------------------------


def player_seasons(weekly):
    """{season: (total_points, appearances)} for seasons <= MAX_SEASON.

    An appearance is a weekly row with fantasy_points > 0. Roster weeks where
    the player scored 0.0 (injured, inactive, bye) are not appearances; using
    season_aggregates.weeks_played here was BUG 1.
    """
    out = {}
    for season in sorted({r.get("season") for r in weekly if r.get("season")}):
        if season > MAX_SEASON:
            continue
        pts = [
            r["fantasy_points"]
            for r in weekly
            if r.get("season") == season and (r.get("fantasy_points") or 0) > 0
        ]
        if pts:
            out[season] = (sum(pts), len(pts))
    return out


def player_value(weekly, season_w=None, min_rate_games=MIN_RATE_GAMES):
    """Two value definitions, both scoring EVERY covered season (BUG 2 fix).

    rate  = weighted points per appearance (how good when he plays)
    avail = weighted points per season week, total/17 (what he delivered)
    The gap between them is the injury question and is reported, not resolved.
    """
    season_w = season_w or SEASON_W
    seasons = player_seasons(weekly)
    out = {}
    for mode in ("rate", "avail"):
        num = den = 0.0
        for season, w in season_w.items():
            if season not in seasons:
                continue
            total, games = seasons[season]
            if mode == "rate":
                if games < min_rate_games:
                    continue
                v = total / games
            else:
                v = total / SEASON_WEEKS
            num += w * v
            den += w
        out[mode] = (num / den) if den else None
    return out


def rookie_over_replacement(
    pick_no, rookie_peak=ROOKIE_PEAK, rookie_zero_pick=ROOKIE_ZERO_PICK
):
    """Rookie value directly in points over replacement, position-neutral
    (BUG 3 fix): the estimate depends only on draft slot, so a rookie QB and
    a rookie WR at the same pick are the same asset until one of them plays."""
    if pick_no is None:
        return 0.0
    return max(0.0, rookie_peak * (1 - (pick_no - 1) / float(rookie_zero_pick)))


# ---- replacement and lineups ------------------------------------------------------


def replacement_levels(pool_by_pos, started=None, flex_extra=None):
    """Per position, the Nth-best rostered value, N = league starters plus a
    flex allowance. This is what a team could field without owning anyone."""
    started = started if started is not None else STARTED
    flex_extra = flex_extra if flex_extra is not None else FLEX_EXTRA
    repl = {}
    for pos, vals in pool_by_pos.items():
        vals = sorted(vals, reverse=True)
        n = started.get(pos, 12) + flex_extra.get(pos, 0)
        repl[pos] = vals[min(n, len(vals)) - 1] if vals else 0.0
    return repl


def best_lineup(pool, lineup=None):
    """Best legal lineup from (pos, player_id, value) entries.

    Greedy per slot with FLEX last is provably optimal for this slot
    structure (verified adversarially on the prototypes). Non-differentiating
    positions are ignored. Returns (starters_total, depth, chosen) where
    chosen entries are (slot, pos, player_id, value) and depth is half the
    best remaining bench value at each of RB/WR/TE.
    """
    lineup = lineup or LINEUP
    cand = sorted([p for p in pool if p[0] in DIFFERENTIATING], key=lambda p: -p[2])
    used, total, chosen = set(), 0.0, []
    for slot in lineup:
        idxs = [
            i
            for i, c in enumerate(cand)
            if i not in used and (c[0] in FLEX_OK if slot == "FLEX" else c[0] == slot)
        ]
        if idxs:
            i = idxs[0]
            used.add(i)
            total += cand[i][2]
            chosen.append((slot, cand[i][0], cand[i][1], cand[i][2]))
    depth = 0.0
    for pos in sorted(FLEX_OK):
        rest = [
            cand[i][2] for i in range(len(cand)) if i not in used and cand[i][0] == pos
        ]
        if rest:
            depth += 0.5 * max(rest)
    return total, depth, chosen


# ---- the asset axis ---------------------------------------------------------------


def age_at_cutoff(birth_date, cutoff=CUTOFF):
    """Age in years at the edition cutoff, from birth_date only. The
    players.json `age` field is stamped at fetch time (possibly 2026) and is
    never used: birth_date is the only cutoff-safe field."""
    if not birth_date:
        return None
    try:
        y, m, d = (int(x) for x in str(birth_date).split("-"))
        born = date(y, m, d)
    except (ValueError, TypeError):
        return None
    return (cutoff - born).days / 365.2425


def age_multiplier(pos, age, curve=None):
    """Dynasty discount: full value through the position's peak, linear decay
    to a 0.1 floor at the cliff, a small premium below the peak."""
    peak_end, cliff = (curve or AGE_CURVE).get(pos, (26, 33))
    if age <= peak_end:
        return min(1.15, 1.0 + YOUTH_PREMIUM * (peak_end - age))
    return max(0.1, 1.0 - 0.9 * (age - peak_end) / float(cliff - peak_end))


# ---- tiers -------------------------------------------------------------------------


def assign_tiers(scores, bands):
    """Tier break between adjacent teams (by score) only where their p5-p95
    rank bands are DISJOINT: publishing a precise 1-12 across overlapping
    bands claims knowledge nobody has."""
    order = sorted(scores, key=lambda k: -scores[k])
    tiers, tier = {}, 1
    for i, team in enumerate(order):
        if i > 0 and bands[order[i - 1]][1] < bands[team][0]:
            tier += 1
        tiers[team] = tier
    return tiers


# ---- the desk ----------------------------------------------------------------------


def _load_inputs(bundle_path, arcs_dir, players_path):
    bundle = load_json(Path(bundle_path), required=True)
    index = load_json(Path(arcs_dir) / "_index.json", required=True)
    players_db = load_json(Path(players_path), required=True)
    return bundle, index, players_db


def _team_pools(bundle, arcs_dir, index, players_db):
    """Per roster: proven players with (pos, pid, name, rate, avail, age) and
    unproven players with (pos, pid, name, pick_no, age)."""
    picks = {str(p["player_id"]): p for p in bundle["draft"]["picks"]}
    arc_cache = {}

    def arc_value(pid):
        if pid not in arc_cache:
            f = Path(arcs_dir) / f"{pid}.json"
            arc = load_json(f) if f.exists() else None
            weekly = (arc or {}).get("weekly") or []
            arc_cache[pid] = player_value(weekly)
        return arc_cache[pid]

    proven, unproven = defaultdict(list), defaultdict(list)
    for team in bundle["rosters"]["teams"]:
        rid = str(team["roster_id"])
        for p in team["players"]:
            pid = p["player_id"]
            pos = (
                p.get("position") or index.get(pid, {}).get("position") or "?"
            ).upper()
            if pos not in DIFFERENTIATING:
                continue
            name = p.get("player_name") or index.get(pid, {}).get("name") or pid
            age = age_at_cutoff(players_db.get(pid, {}).get("birth_date"))
            v = arc_value(pid)
            if v["rate"] is None and v["avail"] is None:
                pick_no = picks.get(pid, {}).get("pick_no")
                unproven[rid].append((pos, pid, name, pick_no, age))
            else:
                proven[rid].append((pos, pid, name, v["rate"], v["avail"], age))
    return proven, unproven


def _score_teams(
    proven, unproven, rookie_peak, rookie_zero_pick, mode_weights, age_curve
):
    """One full scoring pass. Returns {rid: {"present": x, "asset": y,
    "lineup": [...], "top_assets": [...]}}."""
    # replacement per mode from the proven pools
    repl = {}
    for mi, mode in enumerate(("rate", "avail")):
        pool_by_pos = defaultdict(list)
        for rid in proven:
            for pos, _, _, rate, avail, _ in proven[rid]:
                v = (rate, avail)[mi]
                if v is not None:
                    pool_by_pos[pos].append(v)
        repl[mode] = replacement_levels(pool_by_pos)

    out = {}
    for rid in sorted(set(proven) | set(unproven), key=int):
        rookies = [
            (
                pos,
                pid,
                name,
                rookie_over_replacement(pick_no, rookie_peak, rookie_zero_pick),
                age,
            )
            for pos, pid, name, pick_no, age in unproven.get(rid, [])
        ]
        present_scores, lineup_detail = [], None
        for mi, mode in enumerate(("rate", "avail")):
            pool = [
                (pos, pid, max(0.0, (rate, avail)[mi] - repl[mode][pos]))
                for pos, pid, name, rate, avail, _ in proven.get(rid, [])
                if (rate, avail)[mi] is not None
            ]
            pool += [(pos, pid, over) for pos, pid, _, over, _ in rookies]
            total, depth, chosen = best_lineup(pool)
            present_scores.append(mode_weights[mode] * (total + depth))
            if mode == "rate":
                lineup_detail = chosen
        present = sum(present_scores)

        assets = []
        for pos, pid, name, rate, avail, age in proven.get(rid, []):
            base = max(
                0.0,
                (rate if rate is not None else (avail or 0.0))
                - repl["rate"].get(pos, 0.0),
            )
            a = age if age is not None else 27.0
            assets.append((name, pos, base * age_multiplier(pos, a, age_curve)))
        for pos, pid, name, over, age in rookies:
            a = age if age is not None else ROOKIE_DEFAULT_AGE
            assets.append((name, pos, over * age_multiplier(pos, a, age_curve)))
        assets.sort(key=lambda x: (-x[2], x[0]))
        out[rid] = {
            "present": present,
            "asset": sum(v for _, _, v in assets),
            "lineup": lineup_detail,
            "top_assets": assets[:6],
        }
    return out


def _ranks(scores):
    order = sorted(scores, key=lambda k: (-scores[k], int(k)))
    return {rid: i + 1 for i, rid in enumerate(order)}


def build_desk(
    runs=200, seed=11, bundle_path=BUNDLE, arcs_dir=ARCS, players_path=PLAYERS
):
    """The full desk: base scoring pass, joint perturbation of every arguable
    constant, p5-p95 rank bands, tiers per axis. Deterministic under a seed."""
    bundle, index, players_db = _load_inputs(bundle_path, arcs_dir, players_path)
    teams_meta = {str(t["roster_id"]): t for t in bundle["teams"]}
    proven, unproven = _team_pools(bundle, arcs_dir, index, players_db)

    base = _score_teams(
        proven,
        unproven,
        ROOKIE_PEAK,
        ROOKIE_ZERO_PICK,
        {"rate": 0.5, "avail": 0.5},
        AGE_CURVE,
    )

    rng = random.Random(seed)
    rank_samples = {"present": defaultdict(list), "asset": defaultdict(list)}
    for _ in range(runs):
        w24 = rng.uniform(0.55, 0.85)
        global SEASON_W
        season_w_save = SEASON_W
        SEASON_W = {2024: w24, 2023: 1 - w24}
        wr = rng.uniform(0.25, 0.75)
        curve = {
            pos: (peak + rng.choice((-1, 0, 1)), cliff + rng.choice((-1, 0, 1)))
            for pos, (peak, cliff) in AGE_CURVE.items()
        }
        try:
            # re-derive player values under the perturbed season weights
            proven_p, unproven_p = _team_pools(bundle, arcs_dir, index, players_db)
            scored = _score_teams(
                proven_p,
                unproven_p,
                rng.uniform(3.0, 9.0),
                rng.choice((20, 30, 45, 60)),
                {"rate": wr, "avail": 1 - wr},
                curve,
            )
        finally:
            SEASON_W = season_w_save
        for axis in ("present", "asset"):
            for rid, rank in _ranks({r: scored[r][axis] for r in scored}).items():
                rank_samples[axis][rid].append(rank)

    def band(samples, lo, hi):
        v = sorted(samples)
        if len(v) < 20:
            return (min(v), max(v))
        return (v[int(lo * len(v))], v[int(hi * len(v)) - 1])

    axes = {}
    for axis in ("present", "asset"):
        scores = {rid: base[rid][axis] for rid in base}
        ranks = _ranks(scores)
        # reported band: p5-p95 (the honest spread). tiering band: IQR --
        # a tier break claims "more likely than not separable", and one
        # high-variance team must not chain-bridge the whole table.
        bands, tier_bands = {}, {}
        for rid in base:
            samples = rank_samples[axis][rid]
            if samples:
                bands[rid] = band(samples, 0.05, 0.95)
                tier_bands[rid] = band(samples, 0.25, 0.75)
            else:
                bands[rid] = tier_bands[rid] = (ranks[rid], ranks[rid])
        axes[axis] = {
            "scores": scores,
            "ranks": ranks,
            "bands": bands,
            "tiers": assign_tiers(scores, tier_bands),
        }

    teams = []
    for rid in sorted(base, key=int):
        meta = teams_meta[rid]
        row = {
            "roster_id": rid,
            "owner": OWNER.get(meta["owner"], meta["owner"]),
            "team_name": meta["team_name"],
            "top_assets": [
                {"player": n, "position": p, "value": round(v, 2)}
                for n, p, v in base[rid]["top_assets"]
            ],
            "lineup_rate_basis": [
                {
                    "slot": s,
                    "position": p,
                    "player_id": pid,
                    "over_replacement": round(v, 2),
                }
                for s, p, pid, v in (base[rid]["lineup"] or [])
            ],
        }
        for axis in ("present", "asset"):
            a = axes[axis]
            row[axis] = {
                "score": round(a["scores"][rid], 2),
                "rank": a["ranks"][rid],
                "rank_band": list(a["bands"][rid]),
                "tier": a["tiers"][rid],
            }
        teams.append(row)

    return {
        "kind": "roster-valuation/1",
        "edition_id": bundle.get("edition_id"),
        "cutoff_utc": bundle.get("cutoff_utc"),
        "parameters": {
            "season_weights": {str(k): v for k, v in SEASON_W.items()},
            "min_rate_games": MIN_RATE_GAMES,
            "rookie_peak": ROOKIE_PEAK,
            "rookie_zero_pick": ROOKIE_ZERO_PICK,
            "age_curve": {k: list(v) for k, v in AGE_CURVE.items()},
            "perturbation_runs": runs,
            "seed": seed,
        },
        "not_encoded": list(NOT_ENCODED),
        "teams": teams,
    }


# ---- CLI ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(prog="value_rosters.py")
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", help="write the full desk JSON here")
    a = ap.parse_args(argv)

    desk = build_desk(runs=a.runs, seed=a.seed)

    print(
        f"{'owner':9} {'PRESENT':>8} {'rk':>3} {'band':>7} {'tier':>4}"
        f"   {'ASSET':>8} {'rk':>3} {'band':>7} {'tier':>4}"
    )
    for t in sorted(desk["teams"], key=lambda t: t["present"]["rank"]):
        p, s = t["present"], t["asset"]
        print(
            f"{t['owner']:9} {p['score']:8.1f} {p['rank']:3}"
            f" {p['rank_band'][0]:3}-{p['rank_band'][1]:<3} {p['tier']:4}"
            f"   {s['score']:8.1f} {s['rank']:3}"
            f" {s['rank_band'][0]:3}-{s['rank_band'][1]:<3} {s['tier']:4}"
        )
    if a.out:
        save_json_canonical(Path(a.out), desk)
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
