#!/usr/bin/env python3
"""Fetch the league's own rules from Sleeper into data/{season}/league_settings.json.

The preseason evidence builder READS this file; it never fetches, so the bundle
projection stays offline and deterministic. This script is the only network step
and it reuses fetch_sleeper.fetch_json, which enforces the constant Sleeper host.

Why this file exists: without the starting lineup and scoring table the column
asserts roster and IDP math a reader cannot check. The lineup is
QB/RB/RB/WR/WR/WR/TE/FLEX/K/DEF/DL/LB/DB.

TEMPORAL NOTE: Sleeper returns settings as they stand NOW, so for a completed
season this is a present-day read of a past season's rules. It is admitted on the
strength of pre-cutoff corroboration in league chat (recorded in `temporal_note`
in the output), not on the fetch alone. If a value ever contradicts pre-cutoff
chat, the chat wins and the discrepancy is a finding, not a rounding error.

    python scripts/fetch_league_settings.py --season 2025
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fetch_sleeper import fetch_json  # noqa: E402

CORROBORATION = (
    "Fetched after the season completed, so this records the settings as Sleeper holds "
    "them. Corroborated as in force before the 2025-09-03 cutoff by league chat: Nate, "
    "'2 points per PBU in our league' (matches idp_pass_def 2.0); Patrick 2023-10-05, "
    "'One solo tackle for a LB playing 100% of snaps' (idp_tkl_solo 1.0) and 'I remember "
    "when we used to play three IDP slots of any position' (the DL/LB/DB split); taxi "
    "squad referenced by Patrick and Blake through 2023; FLEX referenced by Brent "
    "2023-09-13 and Patrick 2023-10-09."
)


def league_id_for(season):
    """Read the season -> league id map straight out of config.js, the single source."""
    cfg = (ROOT / "config.js").read_text(encoding="utf-8")
    m = re.search(r"\b%s\s*:\s*[\"'](\d+)[\"']" % season, cfg)
    if not m:
        raise SystemExit("no league id for season %s in config.js" % season)
    return m.group(1)


def main():
    ap = argparse.ArgumentParser(prog="fetch_league_settings.py")
    ap.add_argument("--season", default="2025")
    a = ap.parse_args()

    lid = league_id_for(a.season)
    lg = fetch_json("/league/%s" % lid)
    rp = lg.get("roster_positions") or []
    st = lg.get("settings") or {}
    starters = [p for p in rp if p != "BN"]

    doc = {
        "kind": "league-settings/1",
        "season": int(lg.get("season")),
        "league_id": lid,
        "league_name": lg.get("name"),
        "source": "Sleeper API GET /v1/league/{league_id}",
        "roster_positions": rp,
        "starting_lineup": starters,
        "starting_lineup_summary": ", ".join(starters),
        "bench_slots": rp.count("BN"),
        "taxi_slots": st.get("taxi_slots"),
        "reserve_slots": st.get("reserve_slots"),
        "scoring_settings": lg.get("scoring_settings") or {},
        "temporal_note": CORROBORATION,
    }
    out = ROOT / "data" / a.season / "league_settings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8").write(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    print(
        "%s  (%d starters: %s | bench %d, taxi %s, IR %s)"
        % (
            out,
            len(starters),
            doc["starting_lineup_summary"],
            doc["bench_slots"],
            doc["taxi_slots"],
            doc["reserve_slots"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
