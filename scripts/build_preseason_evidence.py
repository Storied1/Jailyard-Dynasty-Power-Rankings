"""Project the compiled preseason state into one writer-facing evidence file.

The preseason writer reads exactly one league-data file: the PRIVATE bundle
private_bundles/preseason-2025/preseason_evidence.json (gitignored, local
custody only). It is a PROJECTION of the compiled, cutoff-bound preseason
edition state: team identities, draft information, the transaction log,
historical results, cutoff rosters, and exact chat quotes, every item
carrying its source reference and an instant at or before the edition
cutoff. It contains facts only -- no framing, no suggestions, no treatment
of any kind.

The tracked public surface is the manifest
content/preseason-2025/preseason_evidence.manifest.json: edition, cutoff,
the bundle's canonical sha256, aggregate counts, lineage, and the
regeneration command -- never the bundle bytes. `--verify` is the local
writer preflight: it rejects an absent or hash-mismatched private bundle.

The projection re-checks admissibility itself: a fact whose known_at is
missing, malformed, or after the cutoff is dropped even if it somehow reached
the input. `project()` is pure and is proven by a planted post-cutoff fact in
the test module.

Cutoff rosters are reconstructed by rewinding the week-1 roster snapshot
(data/2025/fantasy_rosters/week1.json, a later-state capture) through the
post-cutoff slice of the week-1 transaction log. `project_cutoff_rosters()`
is pure and fails closed: every post-cutoff transaction must be either fully
reflected in the snapshot (and is rewound) or fully absent (and must be
newer than every rewound one); any partial reflection or non-monotone
pattern raises. A planted post-cutoff add/drop/trade provably leaves the
projected cutoff roster unchanged (noninterference test in the test module).
"""

import argparse
import hashlib
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.compile_state import load_compiled_state  # noqa: E402
    from scripts.eval_arms import rehydrate_state  # noqa: E402
    from scripts.fact_schema import canonical_instant  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from compile_state import load_compiled_state  # noqa: E402
    from eval_arms import rehydrate_state  # noqa: E402
    from fact_schema import canonical_instant  # noqa: E402
from shared import load_json, save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "private_bundles" / "preseason-2025" / "preseason_evidence.json"
MANIFEST_PATH = ROOT / "content" / "preseason-2025" / "preseason_evidence.manifest.json"
ROSTER_SNAPSHOT = ROOT / "data" / "2025" / "fantasy_rosters" / "week1.json"
TRANSACTION_LOG = ROOT / "data" / "2025" / "transactions.json"
CHAT_WINDOW_START = "2025-02-10T00:00:00Z"  # offseason window for quotes
REGENERATE_CMD = "python scripts/build_preseason_evidence.py"


class RosterRewindError(ValueError):
    """The week-1 snapshot and the post-cutoff transaction log disagree in a
    way the rewind cannot resolve deterministically. Never a warning."""


def _admissible(fact, cutoff):
    """Exact-instant re-check at the projection boundary: known_at must parse
    canonically and be <= cutoff. Fail closed on anything else."""
    known = canonical_instant(getattr(fact, "known_at", None))
    bound = canonical_instant(cutoff)
    return known is not None and bound is not None and known <= bound


def _player_names():
    """player_id -> (name, position) from committed factual sources only:
    draft metadata and the player-arc index (name/position fields alone)."""
    names = {}
    arc_index = load_json(ROOT / "data" / "2025" / "player_arcs" / "_index.json")
    for pid, meta in (arc_index or {}).items():
        if isinstance(meta, dict) and meta.get("name"):
            names[str(pid)] = (meta["name"], meta.get("position"))
    picks = load_json(ROOT / "data" / "2025" / "draft_picks.json")
    for p in (picks or {}).get("picks", []):
        md = p.get("metadata") or {}
        nm = " ".join(x for x in (md.get("first_name"), md.get("last_name")) if x)
        if nm:
            names[str(p["player_id"])] = (nm, md.get("position"))
    return names


def _cutoff_epoch_ms(cutoff):
    """Exact cutoff instant as epoch milliseconds; None on malformed input."""
    canon = canonical_instant(cutoff)
    if canon is None:
        return None
    dt = datetime.strptime(canon[:-1], "%Y-%m-%dT%H:%M:%S.%f").replace(
        tzinfo=timezone.utc
    )
    return dt.timestamp() * 1000.0


def project_cutoff_rosters(snapshot_rosters, week1_transactions, cutoff):
    """Pure rewind: week-1 roster snapshot -> roster membership at the cutoff.

    Every COMPLETE transaction with status_updated strictly after the cutoff
    is classified against the evolving state, newest first: fully reflected
    (all adds present, all drops absent) -> rewound; fully absent (all adds
    absent, all drops present) -> skipped, but only while no older reflected
    transaction has been seen yet (the snapshot moment is a single boundary).
    Any partial reflection, unknown roster, or non-monotone pattern raises
    RosterRewindError. Returns ({roster_id(int): set(player_id)}, [rewound
    transaction ids oldest-first]).
    """
    cut_ms = _cutoff_epoch_ms(cutoff)
    if cut_ms is None:
        raise RosterRewindError(f"malformed cutoff instant: {cutoff!r}")
    state = {}
    for r in snapshot_rosters:
        rid = int(r["roster_id"])
        if rid in state:
            raise RosterRewindError(f"duplicate roster_id in snapshot: {rid}")
        state[rid] = set(str(p) for p in (r["players"] or []))

    post = [
        t
        for t in week1_transactions
        if t.get("status") == "complete"
        and isinstance(t.get("status_updated"), (int, float))
        and t["status_updated"] > cut_ms
    ]
    post.sort(key=lambda t: (t["status_updated"], str(t.get("transaction_id"))))

    rewound = []
    seen_reflected = False  # walking newest -> oldest
    for t in reversed(post):
        tid = str(t.get("transaction_id"))
        adds = {str(p): int(r) for p, r in (t.get("adds") or {}).items()}
        drops = {str(p): int(r) for p, r in (t.get("drops") or {}).items()}
        if not adds and not drops:
            continue  # no membership effect (e.g. pick-only trade)
        for rid in set(adds.values()) | set(drops.values()):
            if rid not in state:
                raise RosterRewindError(
                    f"transaction {tid} names unknown roster_id {rid}"
                )
        reflected = all(p in state[r] for p, r in adds.items()) and all(
            p not in state[r] for p, r in drops.items()
        )
        absent = all(p not in state[r] for p, r in adds.items()) and all(
            p in state[r] for p, r in drops.items()
        )
        if reflected:
            for p, r in adds.items():
                state[r].remove(p)
            for p, r in drops.items():
                state[r].add(p)
            rewound.append(tid)
            seen_reflected = True
        elif absent and not seen_reflected:
            continue  # newer than the snapshot moment; never entered it
        else:
            raise RosterRewindError(
                f"transaction {tid} is neither fully reflected nor cleanly "
                f"newer than the snapshot (partial reflection or non-monotone "
                f"boundary); refusing to guess the cutoff roster"
            )
    rewound.reverse()
    return state, rewound


def project(facts, cutoff, names=None, chat_window_start=CHAT_WINDOW_START):
    """Pure projection: admitted facts -> writer-facing evidence sections.

    Every emitted item carries its fact_id. A fact that fails the exact-instant
    admissibility re-check against the cutoff is dropped, whatever its type.
    """
    names = names or {}
    admitted = [f for f in facts if _admissible(f, cutoff)]

    teams = []
    for f in (x for x in admitted if x.fact_type == "franchise_identity"):
        p = f.payload
        teams.append(
            {
                "roster_id": p["roster_id"],
                "team_name": p.get("team_name"),
                "owner": p.get("display_name"),
                "owner_id": p.get("owner_id"),
                "fact_id": f.fact_id,
            }
        )
    teams.sort(key=lambda t: int(t["roster_id"]))

    picks = []
    for f in (x for x in admitted if x.fact_type == "draft_pick"):
        p = f.payload
        nm, pos = names.get(str(p.get("player_id")), (None, None))
        picks.append(
            {
                "round": p.get("round"),
                "pick_no": p.get("pick_no"),
                "roster_id": str(p.get("roster_id")),
                "player_id": str(p.get("player_id")),
                "player_name": nm,
                "position": pos,
                "fact_id": f.fact_id,
            }
        )
    picks.sort(key=lambda x: (x["pick_no"] or 0))

    transactions = []
    for f in (x for x in admitted if x.fact_type == "transaction"):
        p = f.payload

        def _side(d):
            return [
                {
                    "player_id": str(pid),
                    "player_name": names.get(str(pid), (None, None))[0],
                    "roster_id": str(rid),
                }
                for pid, rid in sorted((d or {}).items())
            ]

        transactions.append(
            {
                "type": p.get("type"),
                "roster_ids": [str(r) for r in (p.get("roster_ids") or [])],
                "adds": _side(p.get("adds")),
                "drops": _side(p.get("drops")),
                "known_at": f.known_at,
                "fact_id": f.fact_id,
            }
        )
    transactions.sort(key=lambda t: (t["known_at"], t["fact_id"]))

    games = []
    records = defaultdict(
        lambda: defaultdict(lambda: {"wins": 0, "losses": 0, "points_for": 0.0})
    )
    for f in (x for x in admitted if x.fact_type == "historical_matchup"):
        p = f.payload
        games.append(
            {
                "season": p["season"],
                "week": p["week"],
                "home": p["home"],
                "home_pts": p["home_pts"],
                "away": p["away"],
                "away_pts": p["away_pts"],
                "fact_id": f.fact_id,
            }
        )
        for rid, pts, opp in (
            (p["home"], p["home_pts"], p["away_pts"]),
            (p["away"], p["away_pts"], p["home_pts"]),
        ):
            r = records[p["season"]][rid]
            r["points_for"] = round(r["points_for"] + pts, 2)
            if pts > opp:
                r["wins"] += 1
            elif pts < opp:
                r["losses"] += 1
    games.sort(key=lambda g: (g["season"], g["week"], g["fact_id"]))
    season_records = {
        str(season): {rid: rows[rid] for rid in sorted(rows, key=int)}
        for season, rows in sorted(records.items())
    }

    team_by_wa = {}
    name_map = load_json(ROOT / "content" / "chat" / "name-map.json") or {}
    for wa, info in name_map.items():
        team_by_wa[wa] = {
            "display_name": info.get("display_name"),
            "roster_id": info.get("roster_id"),
            "team_name": info.get("team_name"),
        }

    quotes = []
    for f in (x for x in admitted if x.fact_type == "chat_message"):
        p = f.payload
        ts = p.get("timestamp_utc")
        if not ts or ts < chat_window_start or not p.get("sender"):
            continue
        who = team_by_wa.get(p["sender"], {})
        quotes.append(
            {
                "timestamp_utc": ts,
                "author": p["sender"],
                "author_display": who.get("display_name"),
                "author_roster_id": who.get("roster_id"),
                "author_team": who.get("team_name"),
                "text": p.get("text"),
                "fact_id": f.fact_id,
            }
        )
    quotes.sort(key=lambda q: (q["timestamp_utc"], q["fact_id"]))

    return {
        "kind": "preseason-evidence/1",
        "cutoff_utc": cutoff,
        "teams": teams,
        "draft": {"season": 2025, "picks": picks},
        "transactions": transactions,
        "historical_results": {"season_records": season_records, "games": games},
        "chat_quotes": {
            "window_start_utc": chat_window_start,
            "messages": quotes,
        },
    }


def build_rosters_section(cutoff, names=None):
    """Cutoff roster membership for all 12 teams, derived by rewinding the
    week-1 snapshot through the post-cutoff transaction slice. Reads the two
    local data files; the projection itself is `project_cutoff_rosters`."""
    names = names or {}
    snap = load_json(ROSTER_SNAPSHOT, required=True)
    tx = load_json(TRANSACTION_LOG, required=True)
    state, rewound = project_cutoff_rosters(snap["rosters"], tx.get("1", []), cutoff)
    teams = []
    for rid in sorted(state):
        players = []
        for pid in sorted(state[rid]):
            nm, pos = names.get(pid, (None, None))
            players.append({"player_id": pid, "player_name": nm, "position": pos})
        teams.append({"roster_id": str(rid), "count": len(players), "players": players})
    return {
        "as_of_utc": cutoff,
        "derivation": {
            "method": "week1_snapshot_rewind",
            "snapshot": "data/2025/fantasy_rosters/week1.json",
            "transaction_log": "data/2025/transactions.json",
            "rewound_transactions": rewound,
        },
        "teams": teams,
    }


def _counts(evidence):
    rosters = evidence.get("rosters", {}).get("teams", [])
    return {
        "teams": len(evidence["teams"]),
        "draft_picks": len(evidence["draft"]["picks"]),
        "transactions": len(evidence["transactions"]),
        "historical_games": len(evidence["historical_results"]["games"]),
        "chat_quotes": len(evidence["chat_quotes"]["messages"]),
        "roster_teams": len(rosters),
        "roster_players": sum(t["count"] for t in rosters),
    }


def build_manifest(evidence, bundle_path=OUT_PATH):
    """The tracked public record of the private bundle: edition, cutoff,
    canonical bundle hash, aggregate counts, lineage, regeneration command.
    Carries no bundle bytes and no quotes."""
    raw = Path(bundle_path).read_bytes()
    return {
        "kind": "preseason-evidence-manifest/1",
        "edition_id": evidence.get("edition_id", "2025-preseason"),
        "cutoff_utc": evidence["cutoff_utc"],
        "bundle": {
            "path": "private_bundles/preseason-2025/preseason_evidence.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "counts": _counts(evidence),
        "lineage": {
            "compiled_state": "content/editions/2025-preseason/compiled/",
            "projection": "scripts/build_preseason_evidence.py",
            "roster_snapshot": "data/2025/fantasy_rosters/week1.json",
            "transaction_log": "data/2025/transactions.json",
        },
        "regenerate": REGENERATE_CMD,
    }


def check_manifest_public(manifest):
    """Public-side manifest validation: shape and internal consistency only,
    no private bytes read. Returns a list of problems (empty == OK)."""
    problems = []
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]
    if manifest.get("kind") != "preseason-evidence-manifest/1":
        problems.append(f"unexpected kind: {manifest.get('kind')!r}")
    if canonical_instant(manifest.get("cutoff_utc")) is None:
        problems.append(f"malformed cutoff_utc: {manifest.get('cutoff_utc')!r}")
    b = manifest.get("bundle") or {}
    path = b.get("path", "")
    if not path.startswith("private_bundles/"):
        problems.append(f"bundle.path escapes private custody: {path!r}")
    sha = b.get("sha256", "")
    if not (
        isinstance(sha, str)
        and len(sha) == 64
        and all(c in "0123456789abcdef" for c in sha)
    ):
        problems.append("bundle.sha256 is not a lowercase hex sha256")
    if not (isinstance(b.get("bytes"), int) and b["bytes"] > 0):
        problems.append("bundle.bytes is not a positive integer")
    counts = manifest.get("counts") or {}
    for key in (
        "teams",
        "draft_picks",
        "transactions",
        "historical_games",
        "chat_quotes",
        "roster_teams",
        "roster_players",
    ):
        if not (isinstance(counts.get(key), int) and counts[key] >= 0):
            problems.append(f"counts.{key} missing or not a non-negative int")
    if not manifest.get("regenerate"):
        problems.append("regenerate command missing")
    return problems


def verify_bundle(manifest_path=MANIFEST_PATH, root=ROOT):
    """Local writer preflight. (ok, message): rejects a missing manifest, a
    structurally bad manifest, an ABSENT private bundle, or a bundle whose
    canonical hash does not match the tracked manifest."""
    manifest = load_json(manifest_path)
    if manifest is None:
        return False, f"manifest ABSENT: {manifest_path}"
    problems = check_manifest_public(manifest)
    if problems:
        return False, "manifest INVALID: " + "; ".join(problems)
    bundle = Path(root) / manifest["bundle"]["path"]
    if not bundle.exists():
        return False, (
            f"private bundle ABSENT: {bundle} -- regenerate locally with: "
            f"{manifest['regenerate']}"
        )
    got = hashlib.sha256(bundle.read_bytes()).hexdigest()
    want = manifest["bundle"]["sha256"]
    if got != want:
        return False, (
            f"private bundle HASH MISMATCH: {bundle}\n  manifest {want}\n  "
            f"on disk  {got}\n  regenerate with: {manifest['regenerate']} "
            f"(or restore the manifest)"
        )
    return (
        True,
        f"bundle verified against manifest ({want[:12]}..., {manifest['bundle']['bytes']} bytes)",
    )


def main():
    ap = argparse.ArgumentParser(prog="build_preseason_evidence.py")
    ap.add_argument("--edition", default="2025-preseason")
    ap.add_argument(
        "--verify",
        action="store_true",
        help="writer preflight: verify the private bundle against the tracked manifest",
    )
    a = ap.parse_args()

    if a.verify:
        ok, msg = verify_bundle()
        print(("OK: " if ok else "FAIL: ") + msg)
        return 0 if ok else 1

    doc = load_compiled_state(a.edition)
    state = rehydrate_state(doc)
    names = _player_names()
    evidence = project(state.admitted, state.cutoff, names=names)
    evidence["rosters"] = build_rosters_section(state.cutoff, names=names)
    evidence["edition_id"] = a.edition
    evidence["season"] = state.season
    save_json_canonical(OUT_PATH, evidence)
    save_json_canonical(MANIFEST_PATH, build_manifest(evidence))
    c = _counts(evidence)
    print(
        f"{OUT_PATH}  (teams={c['teams']}, picks={c['draft_picks']}, "
        f"transactions={c['transactions']}, games={c['historical_games']}, "
        f"quotes={c['chat_quotes']}, roster_players={c['roster_players']})"
    )
    print(f"{MANIFEST_PATH}  (tracked public manifest)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
