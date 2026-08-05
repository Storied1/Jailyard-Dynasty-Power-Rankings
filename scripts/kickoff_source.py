"""Timezone-correct kickoff qualification. K2.2 of plan 562e90d.

`kickoff`/`gametime` are LOCAL times of day, never ISO instants -- appending Z
turns a 20:20 ET kickoff into 20:20 UTC. Conversion goes through the venue
timezone map (stadium override first, then home team), failing closed on any
gap. The preview cutoff is DERIVED and RETAINED as a committed artifact with
source hashes; a human transcription is never the authority.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
VENUE_TZ_PATH = ROOT / "content" / "governance" / "venue_timezones.json"
SCHEDULES_TEMPLATE = "data/external/schedules_{season}.parquet"


class UnavailableEvidence(RuntimeError):
    """The instant cannot be established from qualified sources. Never guessed."""


def _load_tz_map():
    if not VENUE_TZ_PATH.exists():
        raise UnavailableEvidence(f"venue timezone map absent at {VENUE_TZ_PATH}")
    return json.loads(VENUE_TZ_PATH.read_text(encoding="utf-8"))


def resolve_zone(record, tz_map):
    """Stadium override first (neutral sites), then home team. Fail closed."""
    by_stadium = tz_map.get("by_stadium", {})
    by_team = tz_map.get("by_team", {})
    stadium_id = record.get("stadium_id")
    if stadium_id and stadium_id in by_stadium:
        return by_stadium[stadium_id]
    home = record.get("home_team")
    if home and home in by_team:
        return by_team[home]
    raise UnavailableEvidence(
        f"no timezone for stadium={stadium_id!r} home_team={home!r}; "
        "a kickoff without a venue zone is undatable"
    )


def to_utc(gameday, gametime, tzname):
    """Convert a local (date, time-of-day) at a named zone to an exact UTC instant."""
    if not tzname:
        raise UnavailableEvidence(
            "timezone required; local time-of-day is not an instant"
        )
    local = datetime.strptime(f"{gameday} {gametime}", "%Y-%m-%d %H:%M").replace(
        tzinfo=ZoneInfo(tzname)
    )
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def strictly_before(instant, seconds=1):
    dt = datetime.strptime(instant, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (dt - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def first_kickoff_instant(season):
    """The qualified first REG-season kickoff, with hashes of every source used."""
    import polars as pl

    parquet = ROOT / SCHEDULES_TEMPLATE.format(season=season)
    if not parquet.exists():
        raise UnavailableEvidence(
            f"schedules parquet absent at {parquet}; run scripts/fetch_nflreadpy.py first"
        )
    tz_map = _load_tz_map()
    df = pl.read_parquet(parquet).filter(
        (pl.col("game_type") == "REG") & (pl.col("week") == pl.col("week").min())
    )
    instants = []
    for rec in df.select(
        "game_id", "gameday", "gametime", "home_team", "stadium_id"
    ).iter_rows(named=True):
        if not rec["gameday"] or not rec["gametime"]:
            raise UnavailableEvidence(f"game {rec['game_id']} has no schedule instant")
        instants.append(
            (
                to_utc(rec["gameday"], rec["gametime"], resolve_zone(rec, tz_map)),
                rec["game_id"],
            )
        )
    if not instants:
        raise UnavailableEvidence(f"no REG games in {parquet}")
    instant, game_id = min(instants)
    return {
        "instant_utc": instant,
        "game_id": game_id,
        "source_hashes": {
            str(SCHEDULES_TEMPLATE.format(season=season)): _sha256_file(parquet),
            "content/governance/venue_timezones.json": _sha256_file(VENUE_TZ_PATH),
        },
    }


def main():
    ap = argparse.ArgumentParser(prog="kickoff_source.py")
    ap.add_argument("--derive-preview-cutoff", action="store_true", required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        r = first_kickoff_instant(a.season)
    except UnavailableEvidence as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    doc = {
        "kickoff_utc": r["instant_utc"],
        "kickoff_game_id": r["game_id"],
        "cutoff_utc": strictly_before(r["instant_utc"]),
        "source_hashes": r["source_hashes"],
        "provenance": (
            f"python scripts/kickoff_source.py --derive-preview-cutoff "
            f"--season {a.season} --out {a.out}"
        ),
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive-create: a re-derivation that would change a committed cutoff
    # must supersede as a new version, never overwrite -- and a failed repeat
    # cannot truncate the artifact.
    try:
        handle = open(out, "x", encoding="utf-8", newline="\n")
    except FileExistsError:
        print(
            f"refused: {out} already exists; supersede as a new version",
            file=sys.stderr,
        )
        return 1
    with handle:
        json.dump(doc, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    print(f"kickoff {doc['kickoff_utc']} -> cutoff {doc['cutoff_utc']} at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
