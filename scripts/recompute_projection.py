#!/usr/bin/env python
"""Raw-only reimplementation oracle for the joke/arc projection (D spike).

`recompute_projection(messages, name_map, cutoff)` rebuilds the {jokes, arcs}
projection PURELY from raw inputs -- raw messages, name_map, and an as-of
`cutoff` -- with NO filesystem reads and no input mutation. It wraps the live
MAP detectors (`detect_predictions` / `detect_relationship_interactions` /
`detect_running_jokes` / `find_candidate_arcs`) per calendar-UTC month, merges
arcs via the legacy `reduce_arcs`, replicates the legacy running-joke selection
(`reduce_chat_deterministic.py:48-77`), and adds exact `count` /
`first_seen_at` / `last_observed_at` fields whose evidence is assigned PER
SOURCE BUCKET and unioned by reducer identity `(type, sorted participants)`.

Purpose: prove the projection algorithm against the committed analytics
(`content/chat/arcs.json` + `league-memory.json`) via COMPLETE ordered
normalized-array parity at all-evidence, without trusting any pre-derived
artifact (reading the committed answer would make the gate circular -- the
test suite's raw-only guard enforces the callable stays disk-free).

`--report` runs the diagnostic named-cutoff counts + the conclusive parity gate.

Graduated from the D spike into production (was DRAFT/UNCOMMITTED). The
exact-instant fail-closed admissibility rule (`_admissible`) implements the
uniform Temporal Contract in
`docs/superpowers/specs/2026-07-12-jailyard-governance-crosswalk.md`
(section "The Temporal Contract (uniform, exact-cutoff)"): admit iff an exact
tz-aware instant <= cutoff; month-granular comparison banned; counts are
through-cutoff; missing/coarse timestamps fail closed. The callable stays
disk-free; the CLI shells (`--report` diagnostics, `--verify` machine gate) do
the I/O.
"""

import argparse
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Runnable both as `python scripts/recompute_projection.py` and imported as a
# test module -- bootstrap scripts/ onto sys.path, then import bare (canonical
# pattern: fetch_nflreadpy.py:20-25).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from map_chat_deterministic import JOKE_PATTERNS  # noqa: E402
from map_chat_deterministic import (
    TRADE_PATTERNS,
    detect_predictions,
    detect_relationship_interactions,
    detect_running_jokes,
    find_candidate_arcs,
)
from reduce_chat_deterministic import reduce_arcs  # noqa: E402
from shared import NAME_MAP_PATH  # noqa: E402
from shared import CHAT_DIR, CONTENT_CHAT_DIR, admissible, load_json, parse_ts

# The uniform exact-cutoff admitter now lives in shared (promoted from this
# spike). Keep the private name for internal + graduation-test use.
_admissible = admissible

# Diagnostic cutoffs, sourced from build_chat_context.py (WEEK1_CUTOFF_2025;
# compute_week_cutoff W18 = Week1 + 17 weeks; compute_preseason_window end).
# Literal here to keep the callable import-light; DIAGNOSTIC-ONLY -- the
# pass/fail gate is all-evidence parity (cutoff=None).
CUTOFF_PRESEASON = datetime(2025, 9, 3, 23, 59, 59, tzinfo=timezone.utc)
CUTOFF_WEEK1 = datetime(2025, 9, 9, 6, 59, 59, tzinfo=timezone.utc)
CUTOFF_WEEK18 = datetime(2026, 1, 6, 6, 59, 59, tzinfo=timezone.utc)

_ADDED_ARC_FIELDS = ("first_seen_at", "last_observed_at", "count", "arc_group_id")
_ADDED_JOKE_FIELDS = ("first_seen_at", "last_observed_at", "count")


def _to_utc(ts_str):
    """Parse a validated full ISO-8601 timestamp to a tz-aware UTC datetime."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _iso_z(dt):
    """Canonical `...Z` UTC string; retains microseconds when present.

    Second precision when microsecond == 0 (keeps existing second-grained
    bounds stable), else `...SS.ffffffZ`. These bounds are parity-stripped
    (`_ADDED_*_FIELDS`), so sub-second precision is safe against the
    committed-analytics parity gate.
    """
    dt = dt.astimezone(timezone.utc)
    if dt.microsecond:
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _trade_events(msgs):
    """UTC datetimes of every trade-qualifying message: one event per message
    (any TRADE_PATTERNS match), regardless of sender -- mirrors map:511-515."""
    out = []
    for m in msgs:
        text = (m.get("text", "") or "").lower()
        if any(re.search(p, text) for p in TRADE_PATTERNS):
            out.append(_to_utc(m["timestamp_utc"]))
    return out


def _rivalry_events(msgs, pair, members):
    """UTC datetimes (of the later message i) for each <=2h adjacency
    transition for `pair` -- mirrors the counting phase map:207-220."""
    out = []
    for i in range(1, len(msgs)):
        sender = msgs[i].get("sender") or ""
        prev = msgs[i - 1].get("sender") or ""
        if not sender or not prev or sender == prev:
            continue
        if sender not in members or prev not in members:
            continue
        ts_prev = parse_ts(msgs[i - 1].get("timestamp_utc", ""))
        ts_curr = parse_ts(msgs[i].get("timestamp_utc", ""))
        if ts_prev and ts_curr and (ts_curr - ts_prev) > timedelta(hours=2):
            continue
        if tuple(sorted([sender, prev])) == pair:
            out.append(_to_utc(msgs[i]["timestamp_utc"]))
    return out


def _prediction_events(predictions, author):
    """UTC datetimes of each detect_predictions result by the selected author."""
    return [
        _to_utc(p["made_at"])
        for p in predictions
        if p.get("author") == author and p.get("made_at")
    ]


def _arc_group_id(arc_type, participants):
    """Collision-free, NON-LOSSY group key over (type, sorted participants).

    Unlike reduce_arcs' `arc_id` (participants[:3], first-word, [:60] -> lossy,
    non-injective: crews sharing a top-3 + first-month collide), this encodes
    the COMPLETE sorted crew, so distinct groups never collide and a membership
    change necessarily changes the id. NOT durable thread continuity: it
    intentionally changes when a crew grows.

    Fail-closed & provably injective: the readable `type::a|b` form is injective
    ONLY if (1) neither separator appears inside a token and (2) no token is
    empty. A per-"::" check alone leaks a cross-seam collision
    (`"a:" + "::" + "b"` == `"a" + "::" + ":b"` == "a:::b"); an empty token leaks
    another (`("a", [])` and `("a", [""])` both emit "a::"). So RAISE if the arc
    type or any participant token is empty or contains ":" or "|". (An empty
    participant LIST stays valid -> "type::"; only an empty participant TOKEN
    fails.) With those excluded, the sole "::" and every "|" are the real
    separators and (type, participants) is uniquely recoverable -- airtight, not
    just true-in-practice. It never fires in production: arc types are 3
    `:`/`|`-free code literals (trade_saga/rivalry/prediction_saga) and
    participants are name-map keys (all 12 nonempty and ":"/"|"-free); the
    committed corpus confirms it -- 2 types present (trade_saga, prediction_saga)
    and 11 distinct participants, all clean.
    """
    parts = sorted(participants)
    for token in (arc_type, *parts):
        if not token or "|" in token or ":" in token:
            raise ValueError(
                f"arc_group_id: token {token!r} is empty or contains a reserved "
                f"separator (':' or '|'); the (type::a|b) encoding would be ambiguous"
            )
    return arc_type + "::" + "|".join(parts)


def recompute_projection(messages, name_map, cutoff):
    """Rebuild {"jokes": [...], "arcs": [...]} purely from raw inputs.

    No filesystem reads, no input mutation. `cutoff` is a tz-aware UTC datetime
    or None (all-evidence).
    """
    members = set(name_map.keys())

    # 1. Admissible = not is_system AND an exact instant at-or-before cutoff.
    #    `.get` -> a missing timestamp_utc key fails closed, never KeyError.
    admissible = [
        m
        for m in deepcopy(messages)
        if not m.get("is_system") and _admissible(m.get("timestamp_utc"), cutoff)
    ]

    # 2. Bucket by calendar-UTC month (convert to UTC BEFORE grouping),
    #    chronological insertion order (feeds reduce_arcs' stable tie-order).
    buckets = defaultdict(list)
    for m in admissible:
        buckets[_to_utc(m["timestamp_utc"]).strftime("%Y-%m")].append(m)
    ordered_months = sorted(buckets)

    # 3. Per-month MAP outputs (detectors run on a deep copy of the bucket, so
    #    the pristine bucket messages remain available for evidence scanning).
    map_outputs = {}
    per_month = {}
    for month in ordered_months:
        msgs = buckets[month]
        work = deepcopy(msgs)
        predictions = detect_predictions(work)
        relationships = detect_relationship_interactions(work, name_map)
        running_jokes = detect_running_jokes(work)
        candidate_arcs = find_candidate_arcs(work, predictions, relationships, name_map)
        map_outputs[month] = {
            "candidate_arcs": candidate_arcs,
            "running_jokes": running_jokes,
        }
        per_month[month] = {"msgs": msgs, "predictions": predictions}

    # Which months emitted each reducer identity (type, sorted participants).
    emitting = defaultdict(list)
    for month in ordered_months:
        for arc in map_outputs[month]["candidate_arcs"]:
            key = (arc["type"], tuple(sorted(arc["participants"])))
            emitting[key].append(month)

    # 4. Arcs schema via legacy reduce_arcs (deep-copied -- it mutates in place
    #    at :171 and :189). Then ADD count/bounds (per-source-bucket evidence
    #    union), REMOVE status. Legacy stable -narrative_potential order kept.
    arcs = []
    for arc in reduce_arcs(deepcopy(map_outputs), name_map):
        key = (arc["type"], tuple(sorted(arc["participants"])))
        events = []
        for month in emitting.get(key, []):
            if arc["type"] == "trade_saga":
                events += _trade_events(per_month[month]["msgs"])
            elif arc["type"] == "rivalry":
                events += _rivalry_events(per_month[month]["msgs"], key[1], members)
            elif arc["type"] == "prediction_saga":
                author = arc["participants"][0] if arc["participants"] else None
                events += _prediction_events(per_month[month]["predictions"], author)
        new_arc = {k: v for k, v in arc.items() if k != "status"}
        new_arc["arc_group_id"] = _arc_group_id(arc["type"], arc["participants"])
        new_arc["first_seen_at"] = _iso_z(min(events)) if events else None
        new_arc["last_observed_at"] = _iso_z(max(events)) if events else None
        new_arc["count"] = len(events)
        arcs.append(new_arc)

    # 5. Jokes: legacy selection (reduce:48-77) over the prefix buckets.
    joke_counts = Counter()
    joke_instances = defaultdict(list)
    for month in ordered_months:
        for joke in map_outputs[month]["running_jokes"]:
            name = joke.get("name", "")
            freq = joke.get("frequency_this_month", 0)
            joke_counts[name] += freq
            joke_instances[name].append(
                {
                    "month": month,
                    "frequency": freq,
                    "sample": joke.get("instances", [{}])[0].get("block", []),
                }
            )

    # 6. Joke count/bounds: every JOKE_PATTERNS match for the name across ALL
    #    admissible messages through C (single-name identity, no crew overlap;
    #    replicates detect_running_jokes' match loop, no break, len(text)>=3).
    joke_events = defaultdict(list)
    for m in admissible:
        text = (m.get("text", "") or "").lower()
        if len(text) < 3:
            continue
        dt = _to_utc(m["timestamp_utc"])
        for pattern, name in JOKE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                joke_events[name].append(dt)

    jokes = []
    for name, total in joke_counts.most_common(20):
        active_months = [inst["month"] for inst in joke_instances[name]]
        events = joke_events.get(name, [])
        jokes.append(
            {
                "name": name,
                "total_frequency": total,
                "first_seen": min(active_months),
                "last_seen": max(active_months),
                # still_active REMOVED
                "sample_block": joke_instances[name][0].get("sample", []),
                "first_seen_at": _iso_z(min(events)) if events else None,
                "last_observed_at": _iso_z(max(events)) if events else None,
                "count": len(events),
            }
        )

    return {"jokes": jokes, "arcs": arcs}


# --------------------------------------------------------------------------- #
# --report CLI (reads private inputs + committed comparison artifacts; the
# callable above stays disk-free, this shell does the I/O).
# --------------------------------------------------------------------------- #


def _load_messages():
    pm = load_json(CHAT_DIR / "parsed_messages.json", required=True)
    return pm["messages"] if isinstance(pm, dict) else pm


def _strip(d, drop):
    return {k: v for k, v in d.items() if k not in drop}


def _first_divergence(proj, legacy, kind):
    """Return a human string of the first difference, or None if identical."""
    if len(proj) != len(legacy):
        return f"length: projection={len(proj)} vs legacy={len(legacy)}"
    for i, (p, lg) in enumerate(zip(proj, legacy)):
        if p == lg:
            continue
        if set(p) != set(lg):
            return (
                f"{kind}[{i}] key-set: proj_only={sorted(set(p) - set(lg))} "
                f"legacy_only={sorted(set(lg) - set(p))}"
            )
        for k in p:
            if p[k] != lg[k]:
                ident = p.get("arc_id") or p.get("name")
                return f"{kind}[{i}] ({ident!r}) field '{k}' differs"
        return f"{kind}[{i}] differs"
    return None


def _load_legacy():
    """Read the committed comparison artifacts (arcs + running_jokes)."""
    legacy_arcs = load_json(CONTENT_CHAT_DIR / "arcs.json", required=True)
    legacy_lm = load_json(CONTENT_CHAT_DIR / "league-memory.json", required=True)
    return legacy_arcs, legacy_lm.get("running_jokes", [])


def _compare_to_legacy(proj, legacy_arcs, legacy_jokes):
    """Pure parity comparison over the SHARED schema. No disk reads.

    Added evidence fields (`_ADDED_ARC_FIELDS`/`_ADDED_JOKE_FIELDS`, incl.
    `arc_group_id`) are stripped from the projection; legacy `status` /
    `still_active` are stripped from the committed answer. Returns
    (cleared: bool, arcs_div: str|None, jokes_div: str|None).
    """
    proj_arcs = [_strip(a, _ADDED_ARC_FIELDS) for a in proj["arcs"]]
    base_arcs = [_strip(a, ("status",)) for a in legacy_arcs]
    proj_jokes = [_strip(j, _ADDED_JOKE_FIELDS) for j in proj["jokes"]]
    base_jokes = [_strip(j, ("still_active",)) for j in legacy_jokes]
    arcs_div = _first_divergence(proj_arcs, base_arcs, "arc")
    jokes_div = _first_divergence(proj_jokes, base_jokes, "joke")
    return (arcs_div is None and jokes_div is None), arcs_div, jokes_div


def _report():
    messages = _load_messages()
    name_map = load_json(NAME_MAP_PATH, required=True)

    print("=== recompute_projection --report ===")
    print(f"messages={len(messages)}  members={len(name_map)}\n")

    print("Named-cutoff diagnostics (arcs / jokes):")
    for label, cutoff in [
        ("preseason   ", CUTOFF_PRESEASON),
        ("week1       ", CUTOFF_WEEK1),
        ("week18      ", CUTOFF_WEEK18),
        ("all-evidence", None),
    ]:
        proj = recompute_projection(messages, name_map, cutoff)
        print(f"  {label}  arcs={len(proj['arcs']):>3}  jokes={len(proj['jokes']):>3}")

    # Conclusive gate: complete ordered normalized-array parity at all-evidence.
    proj = recompute_projection(messages, name_map, None)
    legacy_arcs, legacy_jokes = _load_legacy()
    cleared, arcs_div, jokes_div = _compare_to_legacy(proj, legacy_arcs, legacy_jokes)

    print("\nAll-evidence COMPLETE-ARRAY parity (added stripped vs removed stripped):")
    print(
        f"  arcs  (proj={len(proj['arcs'])} legacy={len(legacy_arcs)}): "
        f"{'PASS' if arcs_div is None else 'FAIL -- ' + arcs_div}"
    )
    print(
        f"  jokes (proj={len(proj['jokes'])} legacy={len(legacy_jokes)}): "
        f"{'PASS' if jokes_div is None else 'FAIL -- ' + jokes_div}"
    )
    print(
        "\nSPIKE VERDICT: "
        + (
            "PASS -- projection reproduces the committed analytics."
            if cleared
            else "FAIL -- divergence to diagnose."
        )
    )


def _verify(messages=None, name_map=None, legacy_arcs=None, legacy_jokes=None):
    """Machine parity gate: return 0 on PASS, 1 on FAIL.

    Production path reads private inputs + committed analytics from disk (the
    callable itself stays disk-free). Tests inject all four in-memory to drive
    the PASS and FAIL branches without touching disk; supply both legacy_arcs
    and legacy_jokes together, or neither.
    """
    messages = _load_messages() if messages is None else messages
    name_map = load_json(NAME_MAP_PATH, required=True) if name_map is None else name_map
    if legacy_arcs is None and legacy_jokes is None:
        legacy_arcs, legacy_jokes = _load_legacy()
    elif legacy_arcs is None or legacy_jokes is None:
        raise ValueError("supply both legacy_arcs and legacy_jokes, or neither")

    proj = recompute_projection(messages, name_map, None)
    cleared, arcs_div, jokes_div = _compare_to_legacy(proj, legacy_arcs, legacy_jokes)
    if cleared:
        print("recompute_projection --verify: PASS -- parity holds.")
        return 0
    print("recompute_projection --verify: FAIL")
    if arcs_div:
        print(f"  arcs:  {arcs_div}")
    if jokes_div:
        print(f"  jokes: {jokes_div}")
    return 1


def main():
    ap = argparse.ArgumentParser(description="D recompute-projection (graduated)")
    ap.add_argument(
        "--report",
        action="store_true",
        help="Print named-cutoff diagnostics + all-evidence parity gate",
    )
    ap.add_argument(
        "--verify",
        action="store_true",
        help="Machine parity gate: exit 0 on PASS, 1 on FAIL",
    )
    args = ap.parse_args()
    if args.verify:
        sys.exit(_verify())
    if args.report:
        _report()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
