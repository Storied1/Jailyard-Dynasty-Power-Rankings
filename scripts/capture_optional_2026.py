"""Optional-lane producers for the 2026 preservation lane (A-opt + B1).

Contract: docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md
Lane components: sleeper_users, draft_meta, draft_picks,
sleeper_transactions, sleeper_matchups. Their evidence is perishable, so
the lane runs alongside Tranche A — but it never gates A3-A7, and the
baseline path must run with THIS MODULE ABSENT (I59): capture_2026 only
ever imports it lazily, inside a CLI dispatch.

Invariants owned here: I7 (per-leg sources record *_requested and raise on
any unreadable leg — an outage is never byte-identical to a quiet week)
and I8 (draft_picks resolves draft_id then reaches actual picks; metadata
alone is failure). Gate: B1, re-verifying the lane's own green.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Package-form import FIRST: under pytest the core module is loaded as
# scripts.capture_2026, and exception identity (CaptureError) must match —
# a bare `from capture_2026 import` would create a second module instance
# whose CaptureError is a different class. Bare form only as a fallback for
# direct script execution; CLI dispatch catches ValueError (the shared
# builtin base) so either instance is caught.
try:
    from scripts.capture_2026 import capture  # noqa: E402
    from scripts.capture_2026 import CaptureError, read_expected_league_id
except ImportError:  # pragma: no cover — direct-run fallback
    from capture_2026 import capture  # noqa: E402
    from capture_2026 import CaptureError, read_expected_league_id

NFL_WEEKS = list(range(1, 19))


def _default_fetch():
    from fetch_sleeper import fetch_json

    return fetch_json


def _capture_public(source_id, payload, *, endpoint, league_id, public_root, now):
    captured_dt = now if now is not None else datetime.now(timezone.utc)
    return capture(
        source_id,
        payload,
        request={"endpoint_or_dataset": endpoint, "params": {}},
        season=2026,
        league_id=league_id,
        captured_at=captured_dt.isoformat().replace("+00:00", "Z"),
        known_at_basis=f"live read of {endpoint} at captured_at",
        access_scope="public",
        privacy="public",
        public_root=public_root,
        now=captured_dt,
    )


def _fetch_weekly_legs(fetch, endpoint_template, weeks):
    """I7 — read every leg; None (unreadable) raises, [] (quiet week) records."""
    legs = {}
    for week in weeks:
        endpoint = endpoint_template.format(week=week)
        leg = fetch(endpoint)
        if leg is None:
            raise CaptureError(
                f"leg {endpoint} unreadable; a partial read is not an empty week"
            )
        if not isinstance(leg, list):
            raise CaptureError(
                f"leg {endpoint} must be a list, got {type(leg).__name__}"
            )
        legs[str(week)] = leg
    return legs


def produce_sleeper_users(
    *, fetch=None, league_json_path=None, public_root=None, now=None
) -> Path:
    fetch = fetch if fetch is not None else _default_fetch()
    league_id = read_expected_league_id(league_json_path)
    endpoint = f"/league/{league_id}/users"
    users = fetch(endpoint)
    if users is None:
        raise CaptureError(f"fetch failed for {endpoint}")
    if not isinstance(users, list) or not users:
        raise CaptureError(f"users payload must be a nonempty list, got {users!r}")
    return _capture_public(
        "sleeper_users",
        {"users": users, "count": len(users)},
        endpoint=endpoint,
        league_id=league_id,
        public_root=public_root,
        now=now,
    )


def produce_draft_meta(
    *, fetch=None, league_json_path=None, public_root=None, now=None
) -> Path:
    fetch = fetch if fetch is not None else _default_fetch()
    league_id = read_expected_league_id(league_json_path)
    endpoint = f"/league/{league_id}/drafts"
    drafts = fetch(endpoint)
    if drafts is None:
        raise CaptureError(f"fetch failed for {endpoint}")
    if not isinstance(drafts, list) or not drafts:
        raise CaptureError("draft metadata absent — window may not be open yet")
    return _capture_public(
        "draft_meta",
        {"drafts": drafts, "count": len(drafts)},
        endpoint=endpoint,
        league_id=league_id,
        public_root=public_root,
        now=now,
    )


def produce_draft_picks(
    *, fetch=None, league_json_path=None, public_root=None, now=None
) -> Path:
    """I8 — resolve draft_id, then fetch actual picks; metadata alone fails."""
    fetch = fetch if fetch is not None else _default_fetch()
    league_id = read_expected_league_id(league_json_path)
    drafts_endpoint = f"/league/{league_id}/drafts"
    drafts = fetch(drafts_endpoint)
    if not isinstance(drafts, list) or not drafts:
        raise CaptureError("cannot resolve draft_id: no draft metadata")
    draft_id = drafts[0].get("draft_id")
    if not isinstance(draft_id, str) or not draft_id.isdigit():
        raise CaptureError(f"draft_id must be a digit string, got {draft_id!r}")

    picks_endpoint = f"/draft/{draft_id}/picks"
    picks = fetch(picks_endpoint)
    if picks is None:
        raise CaptureError(f"fetch failed for {picks_endpoint}")
    if not isinstance(picks, list) or len(picks) == 0:
        raise CaptureError(
            "draft component fails unless pick_count > 0 — metadata alone is not "
            "a draft capture (I8)"
        )
    pick_numbers = [p.get("pick_no") for p in picks]
    if pick_numbers != sorted(pick_numbers) or len(set(pick_numbers)) != len(picks):
        raise CaptureError("pick order not preserved or duplicated pick_no (I8)")

    return _capture_public(
        "draft_picks",
        {"draft_id": draft_id, "picks": picks, "pick_count": len(picks)},
        endpoint=picks_endpoint,
        league_id=league_id,
        public_root=public_root,
        now=now,
    )


def produce_sleeper_transactions(
    *, fetch=None, league_json_path=None, public_root=None, now=None, weeks=None
) -> Path:
    fetch = fetch if fetch is not None else _default_fetch()
    league_id = read_expected_league_id(league_json_path)
    weeks = list(weeks) if weeks is not None else NFL_WEEKS
    template = f"/league/{league_id}/transactions/{{week}}"
    legs = _fetch_weekly_legs(fetch, template, weeks)
    payload = {"weeks_requested": weeks, "transactions": legs}
    return _capture_public(
        "sleeper_transactions",
        payload,
        endpoint=template,
        league_id=league_id,
        public_root=public_root,
        now=now,
    )


def produce_sleeper_matchups(
    *, fetch=None, league_json_path=None, public_root=None, now=None, weeks=None
) -> Path:
    fetch = fetch if fetch is not None else _default_fetch()
    league_id = read_expected_league_id(league_json_path)
    weeks = list(weeks) if weeks is not None else NFL_WEEKS
    template = f"/league/{league_id}/matchups/{{week}}"
    legs = _fetch_weekly_legs(fetch, template, weeks)
    payload = {"weeks_requested": weeks, "matchups": legs}
    return _capture_public(
        "sleeper_matchups",
        payload,
        endpoint=template,
        league_id=league_id,
        public_root=public_root,
        now=now,
    )


# --- B1: sleeper_projections ------------------------------------------------
# The projections endpoint is NOT under /v1, so `fetch_json` (which prefixes
# the v1 base) cannot reach it. This producer therefore carries its own audited
# reader, following fetch_sleeper.py:197-208 verbatim in shape: literal https
# Sleeper host, integer-coerced season/week, fixed season_type enum, and the
# host asserted BEFORE the request so the audit is honest.
PROJECTIONS_HOST = "https://api.sleeper.app"
SEASON_TYPES = ("regular", "post")
# Both editions the frozen policy names for this source (2026-preseason,
# 2026-wk01-preview) are decisions ABOUT week 1, and one week is ~5.5 MB of
# tracked JSON. Capturing all 18 weeks would preserve ~100 MB of projections
# for weeks no sealed edition ranks. The weeks actually requested are recorded
# in the payload, so the capture's scope is auditable rather than implied.
PROJECTION_WEEKS = (1,)


def _fetch_projections(season, week, season_type):
    """One live read. Returns the decoded list, or None when unreadable."""
    import json as _json
    import urllib.request

    season, week = int(season), int(week)
    if season_type not in SEASON_TYPES:
        raise CaptureError(
            f"season_type must be one of {SEASON_TYPES}, got {season_type!r}"
        )
    url = (
        f"{PROJECTIONS_HOST}/projections/nfl/{season}/{week}?season_type={season_type}"
    )
    # Enforce the host before the request to keep the audit honest.
    if not url.startswith("https://api.sleeper.app/"):
        raise CaptureError(f"refusing non-Sleeper URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "JailyardDynasty/1.0"})
    try:
        # nosemgrep: audited -- literal https Sleeper host enforced above
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosemgrep
            return _json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001 - unreadable is a value here, never a crash
        return None


def produce_sleeper_projections(
    *,
    fetch=None,
    league_json_path=None,
    public_root=None,
    now=None,
    weeks=None,
    season=2026,
    season_type="regular",
) -> Path:
    """B1 — per-week Sleeper projections.

    Fails closed on: an unreadable week (an outage is never a quiet week, I7),
    a non-list response, an EMPTY week (the frozen policy sets
    ``empty_valid: false`` for this source), and any record that does not
    self-report the season/week/season_type actually requested — the response
    carries those fields, so a silently shifted or cached-wrong-season payload
    is caught at capture rather than trusted into a bundle.
    """
    fetch = fetch if fetch is not None else _fetch_projections
    league_id = read_expected_league_id(league_json_path)
    weeks = list(weeks) if weeks is not None else list(PROJECTION_WEEKS)
    if not weeks:
        raise CaptureError("weeks must be a nonempty list of NFL week numbers")

    legs, counts = {}, {}
    for week in weeks:
        records = fetch(season, week, season_type)
        if records is None:
            raise CaptureError(
                f"projections week {week} unreadable; a partial read is not an empty week"
            )
        if not isinstance(records, list):
            raise CaptureError(
                f"projections week {week} must be a list, got {type(records).__name__}"
            )
        if not records:
            # policy row: empty_valid is false for sleeper_projections
            raise CaptureError(
                f"projections week {week} is empty; the frozen policy refuses an "
                "empty payload for this source"
            )
        for rec in records:
            if not isinstance(rec, dict):
                raise CaptureError(
                    f"projections week {week} record must be an object, got "
                    f"{type(rec).__name__}"
                )
            actual = (rec.get("season"), rec.get("week"), rec.get("season_type"))
            expected = (str(season), week, season_type)
            if (str(actual[0]), actual[1], actual[2]) != expected:
                raise CaptureError(
                    f"projections record does not match the request: got "
                    f"season={actual[0]!r} week={actual[1]!r} season_type={actual[2]!r}, "
                    f"requested season={season} week={week} season_type={season_type!r}"
                )
        legs[str(week)] = records
        counts[str(week)] = len(records)

    endpoint = f"/projections/nfl/{season}/{{week}}?season_type={season_type}"
    captured_dt = now if now is not None else datetime.now(timezone.utc)
    return capture(
        "sleeper_projections",
        {
            "weeks_requested": weeks,
            "season": season,
            "season_type": season_type,
            "projections": legs,
            "counts": counts,
        },
        request={
            "endpoint_or_dataset": endpoint,
            "params": {
                "season": season,
                "season_type": season_type,
                "weeks": weeks,
            },
        },
        season=2026,
        league_id=league_id,
        captured_at=captured_dt.isoformat().replace("+00:00", "Z"),
        known_at_basis=f"live read of {endpoint} at captured_at",
        access_scope="public",
        privacy="public",
        public_root=public_root,
        now=captured_dt,
    )


OPTIONAL_PRODUCERS = {
    "sleeper_users": produce_sleeper_users,
    "draft_meta": produce_draft_meta,
    "draft_picks": produce_draft_picks,
    "sleeper_transactions": produce_sleeper_transactions,
    "sleeper_matchups": produce_sleeper_matchups,
    "sleeper_projections": produce_sleeper_projections,
}
