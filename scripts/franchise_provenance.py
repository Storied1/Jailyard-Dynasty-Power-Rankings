"""Honest dating for the 2025 franchise_identity family.

`fact_provenance_census.v1.json` records one dishonestly-dated family: all twelve
2025 `franchise_identity` facts carried `known_at = 2026-04-04T17:38:17Z`, the
instant the legacy file was DOWNLOADED, standing in for the instant the fact was
true. That postdates the whole 2025 season, so zero were admitted at any 2025
cutoff and every consumer of `state_at` saw a league with no franchises.

The census also records the constraint: the family asserts two different things
with two different provenances, and only one of them was ever datable.

  SPINE   -- roster_id <-> owner_id.  OBSERVED at the 2025 draft:
             data/2025/draft_picks.json carries roster_id AND picked_by on every
             pick, 12/12 rosters bound one-to-one, at start_date 2025-07-10.
             This is the same anchor draft-window-v1 already trusts for
             draft_pick, reused rather than re-argued.

  DISPLAY -- username + team_name.  NOT observable from any Sleeper capture at a
             2025 instant: data/2025/{season_combined,users}.json are April-2026
             downloads carrying CURRENT names, and Sleeper serves no league
             name-change history.  What IS on disk is this repository's own git
             history: a tracked artifact committed 2025-08-02, a month before
             week 1, whose inline league table binds each Sleeper username to a
             team name.  A commit instant is an OBSERVED upper bound on when the
             pair became knowable -- the same method legacy_capture_instants.v1
             already uses -- so it can never date a fact earlier than the truth.

The two are emitted as a supersession chain, not one merged fact: the spine at
the draft instant, superseded by the full identity at the attestation instant.
A cutoff between them therefore yields spine-only with names declared
unavailable, which is what was actually knowable then.

VALUES ARE NEVER TAKEN FROM THE ATTESTATION.  The 2025 artifact is hand-authored
and CLAUDE.md's standing rule is that AI-generated inline data arrays are never
trusted.  It supplies a DATE and nothing else: a display fact is emitted only
when the authoritative Sleeper value matches the attested value exactly after a
declared normalization.  A name that changed between 2025-08-02 and the 2026
download simply fails to match and stays unavailable -- the failure mode is
silence, never a wrong name with a confident date.
"""

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first -- one module identity under pytest and direct run
    from scripts.fact_schema import canonical_instant  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import canonical_instant  # noqa: E402
from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "content" / "governance" / "franchise_identity_2025.v1.json"

POLICY_ID = "franchise-identity-2025-v1"
SPINE_BASIS = "franchise-spine-draft-v1"
DISPLAY_BASIS = "franchise-display-attestation-v1"

# Archived legacy files. CLAUDE.md: never touched, and that includes never read
# as evidence -- an attestation must come from a file the repo still stands behind.
ARCHIVED_PREFIX = "dontuse"

# `name: '...'` immediately followed by `owner: '...'` inside the inline league
# table. Backslash escapes are consumed so an apostrophe in a team name cannot
# terminate the capture early.
_PAIR = re.compile(
    r"name:\s*'((?:[^'\\]|\\.)*)'\s*,\s*owner:\s*'((?:[^'\\]|\\.)*)'",
    re.S,
)

# Typographic folding, declared rather than incidental. Every substitution here
# is a RENDERING difference for the same string, never a semantic one.
_FOLD = {
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen  ("General Ken‑obi")
    "–": "-",  # en dash
    " ": " ",  # no-break space
    " ": " ",  # narrow no-break space
}


def fold(text):
    """Compare-form for a display string: NFKC, folded punctuation, collapsed
    whitespace, casefolded. Distinguishes real names; ignores typography."""
    s = unicodedata.normalize("NFKC", text or "")
    for src, dst in _FOLD.items():
        s = s.replace(src, dst)
    return " ".join(s.split()).casefold()


def username_key(text):
    """Join key for a Sleeper handle: fold(), then ALL whitespace removed.

    Whitespace-insensitive because of one documented corpus drift -- the 2025
    artifact carries `kharlo w` where Sleeper carries `kharlow`. The emitter proves
    the key is still injective on both sides before it is used, so the fold can
    never silently merge two owners.
    """
    return "".join(fold(text).split())


# ---------------------------------------------------------------------------
# Git archaeology
# ---------------------------------------------------------------------------
def _git(root, *args):
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",  # never cp1252: git speaks UTF-8 and mojibake reads as corruption
        check=True,
        cwd=root,
    ).stdout


def _commit_instant(root, commit):
    iso = _git(root, "show", "-s", "--format=%aI", commit).strip()
    utc = datetime.fromisoformat(iso).astimezone(timezone.utc)
    return canonical_instant(utc.strftime("%Y-%m-%dT%H:%M:%SZ"))


def parse_attestation(text):
    """(username_key -> {username, team_name}) from an inline league table.

    Returns {} when the file carries no such table. A duplicate key is a refusal,
    not a last-write-wins merge.
    """
    pairs = {}
    for name, owner in _PAIR.findall(text):
        key = username_key(owner)
        if not key:
            continue
        if key in pairs and pairs[key]["team_name"] != name:
            raise ValueError(f"attestation binds {owner!r} to two team names")
        pairs[key] = {"username": owner, "team_name": name}
    return pairs


def earliest_attestation(root, expected_usernames):
    """The EARLIEST tracked commit whose blob attests every expected username.

    Earliest, not latest: a commit instant is an upper bound on when the pair
    became knowable, so the earliest proof is the tightest honest bound. It can
    only ever be later than the truth, never earlier -- the fail-closed
    direction. Returns (commit, path, instant, pairs) or None.
    """
    want = {username_key(u) for u in expected_usernames}
    # Only commits that ADDED or MODIFIED an .html file can be the first commit
    # whose tree holds an attesting blob -- a blob enters the tree exactly when
    # it is added. Walking every commit's full tree instead is correct but
    # quadratic, and the answer is identical.
    log = _git(
        root,
        "log",
        "--reverse",
        "--diff-filter=AM",
        "--format=%x00%H",
        "--name-only",
        "--",
        "*.html",
    )
    seen_blobs = set()
    for chunk in log.split("\x00"):
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue
        commit, changed = lines[0], lines[1:]
        for rel in changed:
            if not rel.endswith(".html") or Path(rel).name.startswith(ARCHIVED_PREFIX):
                continue
            try:
                blob_id = _git(root, "rev-parse", f"{commit}:{rel}").strip()
            except subprocess.CalledProcessError:  # pragma: no cover - deleted path
                continue
            if blob_id in seen_blobs:
                continue  # identical content already rejected under another path
            seen_blobs.add(blob_id)
            pairs = parse_attestation(_git(root, "cat-file", "-p", blob_id))
            if want <= set(pairs):
                return commit, rel, _commit_instant(root, commit), pairs
    return None


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------
def build_artifact(root=ROOT, season=2025):
    """The versioned known_at inference policy the design's Open Items require.

    Nothing here is asserted: the spine bindings are read out of the draft file,
    the attestation instant out of git, and every display row must survive an
    exact match against the authoritative Sleeper capture.
    """
    root = Path(root)
    draft = load_json(root / f"data/{season}/draft_picks.json", required=True)
    combined = load_json(root / f"data/{season}/season_combined.json", required=True)
    roster_map = combined["roster_map"]

    # --- spine: roster_id <-> owner_id, observed at the draft ---------------
    bound = {}
    for pick in draft["picks"]:
        rid, owner = str(pick["roster_id"]), pick["picked_by"]
        if rid in bound and bound[rid] != owner:
            raise ValueError(f"roster {rid} bound to two owners in the draft record")
        bound[rid] = owner
    missing = sorted(set(roster_map) - set(bound), key=int)
    if missing:
        raise ValueError(
            f"draft record binds no owner for rosters {missing}; the spine anchor "
            "covers the league or it is not an anchor"
        )
    for rid, owner in bound.items():
        if roster_map[rid]["owner_id"] != owner:
            raise ValueError(
                f"roster {rid}: draft owner {owner} != captured owner "
                f"{roster_map[rid]['owner_id']}; refusing to date a contested binding"
            )
    spine_instant = canonical_instant(f"{draft['start_date']}T23:59:59Z")
    if spine_instant is None:
        raise ValueError(f"unusable draft start_date {draft.get('start_date')!r}")

    # --- display: names dated by the earliest repo attestation --------------
    usernames = {rid: roster_map[rid]["username"] for rid in roster_map}
    keys = [username_key(u) for u in usernames.values()]
    if len(set(keys)) != len(keys):
        raise ValueError("username_key is not injective over the captured league")
    found = earliest_attestation(root, usernames.values())

    display, unattested = {}, []
    attestation = None
    if found:
        commit, rel, instant, pairs = found
        attestation = {
            "commit": commit,
            "path": rel,
            "instant": instant,
            "locator": f"git:{commit}:{rel}",
        }
        for rid in sorted(roster_map, key=int):
            entry = roster_map[rid]
            attested = pairs.get(username_key(entry["username"]))
            if attested and fold(attested["team_name"]) == fold(entry["team_name"]):
                display[rid] = {
                    # AUTHORITATIVE values (Sleeper), attested date. Never the
                    # attestation's own strings.
                    "username": entry["username"],
                    "team_name": entry["team_name"],
                    "attested_username": attested["username"],
                    "attested_team_name": attested["team_name"],
                }
            else:
                unattested.append(rid)
    else:
        unattested = sorted(roster_map, key=int)

    return {
        "policy_id": POLICY_ID,
        "season": season,
        "kind": (
            "Versioned known_at inference policy (design Open Items: 'known_at "
            "inference policies for legacy 2025 sources carrying no publication "
            "instant'). Dates facts; never supplies their values."
        ),
        "spine": {
            "known_at_basis": SPINE_BASIS,
            "instant": spine_instant,
            "source": f"data/{season}/draft_picks.json",
            "derivation": (
                "every pick carries roster_id AND picked_by; the binding is "
                "one-to-one over all 12 rosters and is cross-checked against the "
                "captured roster_map before being dated. Instant = end of the "
                "draft start_date UTC, the draft-window-v1 convention."
            ),
            "bindings": dict(sorted(bound.items(), key=lambda kv: int(kv[0]))),
        },
        "display": {
            "known_at_basis": DISPLAY_BASIS,
            "attestation": attestation,
            "provenance": (
                "earliest tracked commit whose inline league table binds every "
                "captured Sleeper username to a team name; instant = git author "
                "date in UTC, the legacy-capture-v1 method. A commit instant is "
                "an OBSERVED UPPER BOUND on knowability, so it cannot date a "
                "fact earlier than it was true."
            ),
            "match_rule": (
                "a display fact is emitted only where the AUTHORITATIVE Sleeper "
                "team_name equals the attested team_name after NFKC + folded "
                "hyphens/no-break spaces + collapsed whitespace + casefold, "
                "joined on a whitespace-insensitive username key (the documented "
                "'kharlo w'/'kharlow' drift). No match = names stay unavailable."
            ),
            "attested": display,
            "unattested": unattested,
        },
    }


def load_policy(path=None):
    return load_json(Path(path) if path else ARTIFACT_PATH, required=True)


def main():
    ap = argparse.ArgumentParser(prog="franchise_provenance.py")
    ap.add_argument("--season", type=int, default=2025)
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument(
        "--emit", action="store_true", help="print the policy artifact to stdout"
    )
    ap.add_argument(
        "--verify",
        action="store_true",
        help="re-derive from git + sources and compare against the committed artifact",
    )
    a = ap.parse_args()
    if not (a.emit or a.verify):
        ap.error("one of --emit or --verify is required")
    built = build_artifact(a.root, a.season)
    if a.emit:
        print(json.dumps(built, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    committed = load_policy()
    if committed != built:
        print("FAIL committed franchise-identity policy differs from re-derivation")
        return 1
    att = built["display"]["attestation"]
    print(
        f"{POLICY_ID}: verified — spine {built['spine']['instant']} "
        f"({len(built['spine']['bindings'])} rosters), display "
        f"{att['instant'] if att else 'UNAVAILABLE'} "
        f"({len(built['display']['attested'])} attested, "
        f"{len(built['display']['unattested'])} unavailable)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
