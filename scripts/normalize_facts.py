"""Normalize captures and qualified legacy artifacts into typed temporal facts.

Contract: docs/superpowers/plans/2026-08-02-jailyard-temporal-kernel.md K1.6.
Two source lanes -- Phase-P envelopes for 2026 (ALL envelopes, chronologically),
verified legacy walks for the 2025 backtest -- both enumerating all nine bridge
types (sentinels carried as data). Every normalizer returns (meta, body); the
body is the shaped observation the reducers consume, never the raw record.
Custody splits at write time: privacy="private" facts go ONLY to the gitignored
private store. captured_at comes from the ENVELOPE or a versioned policy
artifact, never from a record and never from now().

PREREQUISITE: K2.2's kickoff_source.py exists (imported by normalize_all).
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:  # package form first (Global Constraints import law)
    from scripts.fact_schema import canonical_instant  # noqa: E402
    from scripts.fact_store import FactStore  # noqa: E402
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import canonical_instant  # noqa: E402
    from fact_store import FactStore  # noqa: E402

from shared import load_json, save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NORMALIZER_VERSION = "norm-v1"
PRIOR_SEASONS = (
    2022,
    2023,
    2024,
)  # historical_matchup scope; never the compiled season

LEGACY_INSTANTS_PATH = (
    ROOT / "content" / "governance" / "legacy_capture_instants.v1.json"
)
WEEK_CONCLUSIONS_PATH = (
    ROOT / "content" / "governance" / "week_conclusions_2022_2025.v1.json"
)
# Pregame nfl_game context needs a qualified schedule-publication instant no
# later than the preview cutoff. No such versioned artifact is approved today,
# so the pregame lane records `unavailable` in production (tests exercise it by
# injecting a synthetic qualified instant). Never invented, never backdated.
SCHED_PUBLICATION_PATH = (
    ROOT / "content" / "governance" / "sched_publication_2025.v1.json"
)


class UnqualifiedSource(RuntimeError):
    """The source cannot establish known_at. The fact is unavailable, not guessed."""


class MissingSource(RuntimeError):
    """A legacy source file is absent. Raised BEFORE the first yield, so the
    normalize loop records the type unavailable without discarding records."""


# ---------------------------------------------------------------------------
# Source lanes -- both enumerate ALL NINE types; a type absent from a map would
# silently vanish from the census (the coverage test binds the surfaces).
# ---------------------------------------------------------------------------
ENVELOPE_SOURCES = {
    "franchise_identity": (
        "sleeper_rosters",
        "payload.rosters[] x sleeper_users on owner_id",
    ),
    "matchup_result": (
        "sleeper_matchups",
        "payload.matchups.{week}[] paired by (week, matchup_id)",
    ),
    "transaction": ("sleeper_transactions", "payload.transactions.{week}[]"),
    "draft_pick": (
        "draft_picks",
        "payload.picks[] + top-level draft_id; envelope captured_at",
    ),
    "nfl_game": ("nfl_schedules", "payload games list"),
    "chat_message": (
        None,
        "manual export not ingested for 2026 (design: private-class, manual)",
    ),
    "historical_matchup": (None, "n/a for 2026 BY DESIGN (design section 3 row)"),
    "schedule_pairing": (None, "qualified 2026 mapping deliberately deferred to K3"),
    "roster_membership": (None, "no qualified 2026 anchor policy approved"),
}

LEGACY_SOURCES = {
    "franchise_identity": ("data/{season}/season_combined.json", "roster_map entries"),
    "matchup_result": ("data/{season}/season_combined.json", "weeks[] -> matchups[]"),
    "transaction": (
        "data/{season}/transactions.json",
        "dict keyed by week string -> list",
    ),
    "draft_pick": (
        "data/{season}/draft_picks.json",
        "top-level {draft_id, start_date, picks[]}",
    ),
    "chat_message": (
        "chat/parsed_messages.json",
        "messages[] (gitignored local corpus)",
    ),
    "historical_matchup": (
        "data/{prior}/season_combined.json",
        "fan-out over PRIOR_SEASONS",
    ),
    "nfl_game": ("data/{season}/nfl_games/*.json", "one game per file"),
    "schedule_pairing": (
        None,
        "no qualified pre-kickoff schedule source (design section 1)",
    ),
    "roster_membership": (
        None,
        "no qualified pre-kickoff roster anchor (open dependency 3)",
    ),
}


# ---------------------------------------------------------------------------
# Normalizers -- each returns (meta, body)
# ---------------------------------------------------------------------------
def _instant(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _franchise_identity(raw, season):
    """known_at = the capture instant that first held it. `capture_instant` is
    threaded onto the record by the ITERATOR (envelope captured_at for 2026, the
    legacy-capture-v1 map for 2025) -- no normalizer reads captured_at off a raw
    source record, because no source record carries one."""
    inst = raw["capture_instant"]
    meta = {
        "fact_type": "franchise_identity",
        "source_record_id": f"franchise:{season}:{raw['roster_id']}",
        "entity_ref": {"type": "franchise", "id": str(raw["roster_id"])},
        "effective_at": inst,
        "known_at": inst,
        "known_at_basis": raw.get("capture_instant_basis", "capture_instant"),
        "access_scope": "public",
        "privacy": "public",
    }
    body = {
        "season": season,
        "roster_id": str(raw["roster_id"]),
        "owner_id": raw.get("owner_id"),
        # 2026: sleeper_users display_name; 2025 legacy: roster_map carries
        # username/team_name, never display_name -- read both.
        "display_name": raw.get("display_name") or raw.get("username"),
        "team_name": raw.get("team_name"),
    }
    if raw.get("display_name_unavailable"):
        # Roster-only identity: no users capture existed no later than this
        # roster capture. Recorded as unavailable, never backfilled from later.
        body["display_name_unavailable"] = True
    return meta, body


def _schedule_pairing(raw, season):
    if raw.get("source") in {"weekly_packet_outcomes_stripped", "weekly_packet"}:
        raise UnqualifiedSource(
            "a completed weekly packet with outcomes stripped proves concealment, not "
            "pregame availability; supply a qualified schedule source or a versioned policy"
        )
    if not raw.get("policy_id") and not raw.get("known_at"):
        raise UnqualifiedSource(
            "schedule_pairing requires known_at or a versioned policy_id"
        )
    meta = {
        "fact_type": "schedule_pairing",
        "source_record_id": f"sched:{season}:{raw['week']}:{raw['home']}:{raw['away']}",
        "entity_ref": {"type": "matchup", "id": f"{raw['home']}|{raw['away']}"},
        "effective_at": raw["known_at"],
        "known_at": raw["known_at"],
        "known_at_basis": raw.get("policy_id", "qualified_schedule_source"),
        "access_scope": "public",
        "privacy": "public",
    }
    body = {
        "season": season,
        "week": raw["week"],
        "home": raw["home"],
        "away": raw["away"],
    }
    return meta, body


def _matchup_result(raw, season):
    """known_at = game conclusion (iterator-enriched via the versioned week-
    conclusion policy for legacy; a pairing with no conclusion instant -- e.g.
    an unplayed 2026 matchup -- is refused, never guessed). Teams are roster_id
    strings; team1/team2 carry {roster_id, points}."""
    if not raw.get("concluded_at"):
        raise UnqualifiedSource(
            f"matchup {raw.get('matchup_id')} has no conclusion instant; a pairing is "
            "a schedule_pairing fact, never a matchup_result"
        )
    inst = raw["concluded_at"]
    meta = {
        "fact_type": "matchup_result",
        "source_record_id": f"match:{season}:{raw['week']}:{raw['matchup_id']}",
        "entity_ref": {"type": "matchup", "id": str(raw["matchup_id"])},
        "effective_at": inst,
        "known_at": inst,
        "known_at_basis": raw.get("conclusion_policy", "game_conclusion"),
        "access_scope": "public",
        "privacy": "public",
    }
    body = {
        "season": season,
        "week": raw["week"],
        "home": str(raw["team1"]["roster_id"]),
        "away": str(raw["team2"]["roster_id"]),
        "home_pts": raw["team1"]["points"],
        "away_pts": raw["team2"]["points"],
    }
    return meta, body


def _roster_membership(raw, season):
    anchor = raw.get("anchor_known_at")
    if not anchor:
        raise UnqualifiedSource(
            "roster_membership requires a qualified pre-kickoff anchor instant; "
            "a season-end roster snapshot cannot date a preseason membership"
        )
    meta = {
        "fact_type": "roster_membership",
        "source_record_id": f"roster:{season}:{raw['roster_id']}:{raw['player_id']}",
        "entity_ref": {"type": "franchise", "id": str(raw["roster_id"])},
        "effective_at": anchor,
        "known_at": anchor,
        "known_at_basis": "anchor_or_transaction_completion",
        "access_scope": "public",
        "privacy": "public",
    }
    body = {
        "season": season,
        "roster_id": str(raw["roster_id"]),
        "player_id": str(raw["player_id"]),
        "on_roster": bool(raw.get("on_roster", True)),
    }
    return meta, body


def _transaction(raw, season):
    ms = raw.get("status_updated")
    if ms is None:
        raise UnqualifiedSource(
            f"transaction {raw.get('transaction_id')} has no status_updated; "
            "`created` is not an acceptable fallback for an effective instant"
        )
    inst = _instant(ms)
    meta = {
        "fact_type": "transaction",
        "source_record_id": f"txn:{raw['transaction_id']}",
        "entity_ref": {"type": "transaction", "id": str(raw["transaction_id"])},
        "effective_at": inst,
        "known_at": inst,
        "known_at_basis": "effective_completion_instant",
        "access_scope": "public",
        "privacy": "public",
    }
    body = {
        "season": season,
        "transaction_id": str(raw["transaction_id"]),
        "type": raw.get("type"),
        "adds": raw.get("adds"),
        "drops": raw.get("drops"),
        "roster_ids": raw.get("roster_ids"),
    }
    return meta, body


def _draft_pick(raw, season):
    """Neither legacy pick records nor envelope picks carry a per-pick
    timestamp; the datable instant is per-DRAFT, iterator-threaded."""
    inst = _instant(raw["pick_ts"]) if raw.get("pick_ts") else raw.get("draft_instant")
    if not inst:
        raise UnqualifiedSource(
            f"draft pick {raw.get('pick_no')} has no datable instant"
        )
    if not raw.get("player_id"):
        raise UnqualifiedSource(f"draft pick {raw.get('pick_no')} has no player_id")
    meta = {
        "fact_type": "draft_pick",
        "source_record_id": f"pick:{raw['draft_id']}:{raw['pick_no']}",
        "entity_ref": {"type": "player", "id": str(raw["player_id"])},
        "effective_at": inst,
        "known_at": inst,
        "known_at_basis": raw.get("draft_instant_basis", "pick_timestamp_else_capture"),
        "access_scope": "public",
        "privacy": "public",
    }
    body = {
        "season": season,
        "draft_id": raw["draft_id"],
        "pick_no": raw["pick_no"],
        "round": raw.get("round"),
        "roster_id": str(raw.get("roster_id")),
        "player_id": str(raw["player_id"]),
    }
    return meta, body


def _chat_message(raw, season):
    ts = raw["timestamp_utc"]
    meta = {
        "fact_type": "chat_message",
        "source_record_id": f"msg:{raw['id']}",
        "entity_ref": {"type": "message", "id": str(raw["id"])},
        "effective_at": ts,
        "known_at": ts,
        "known_at_basis": "message_timestamp",
        "access_scope": "league_private",
        "privacy": "private",
    }
    body = {
        "id": raw["id"],
        "timestamp_utc": ts,
        "sender": raw.get("sender"),
        "text": raw.get("text"),
    }
    return meta, body


def _historical_matchup(raw, season):
    """Prior seasons' season_combined. Body shape is IDENTICAL to
    _matchup_result's; `season` in the body is the PRIOR season the game
    belongs to, never the compiled season."""
    if not raw.get("concluded_at"):
        raise UnqualifiedSource(
            f"historical matchup {raw.get('matchup_id')} is undated"
        )
    inst = raw["concluded_at"]
    meta = {
        "fact_type": "historical_matchup",
        "source_record_id": f"hist:{raw['season']}:{raw['week']}:{raw['matchup_id']}",
        "entity_ref": {"type": "matchup", "id": str(raw["matchup_id"])},
        "effective_at": inst,
        "known_at": inst,
        "known_at_basis": raw.get("conclusion_policy", "game_conclusion"),
        "access_scope": "public",
        "privacy": "public",
    }
    body = {
        "season": raw["season"],
        "week": raw["week"],
        "home": str(raw["team1"]["roster_id"]),
        "away": str(raw["team2"]["roster_id"]),
        "home_pts": raw["team1"]["points"],
        "away_pts": raw["team2"]["points"],
    }
    return meta, body


# Postgame information-bearing fields. A record carrying NONE of them is a
# schedule shell, refused as unqualified context -- the design's rationale for
# this required family is "distinguishes rich from minimal".
_NFL_POSTGAME_FIELDS = (
    "home_score",
    "away_score",
    "result",
    "key_injuries",
    "team_stats",
)
_NFL_PREGAME_FIELDS = (
    "rest_days",
    "div_game",
    "spread_line",
    "total_line",
    "roof",
    "temp",
    "wind",
)


def _nfl_game(raw, season):
    """PREGAME/POSTGAME SPLIT (defensible clocks). The iterator fans each game
    into a postgame record (default) and -- ONLY when a qualified schedule-
    publication instant exists -- a pregame record (phase="pregame"). Scores,
    results, EPA and postgame injuries can never enter the pregame body; a
    pregame known_at is never invented."""
    if raw.get("phase") == "pregame":
        inst = raw.get("pregame_known_at")
        if not inst:
            raise UnqualifiedSource(
                f"game {raw.get('game_id')}: no qualified schedule-publication instant"
            )
        for k in _NFL_POSTGAME_FIELDS:
            if raw.get(k) is not None:
                raise UnqualifiedSource(
                    f"game {raw.get('game_id')}: postgame field {k!r} in a pregame record"
                )
        meta = {
            "fact_type": "nfl_game",
            "source_record_id": f"nflgame:{raw['game_id']}:pregame",
            "entity_ref": {"type": "game", "id": str(raw["game_id"])},
            "effective_at": inst,
            "known_at": inst,
            "known_at_basis": raw.get("pregame_policy", "sched-pregame-v1"),
            "access_scope": "public",
            "privacy": "public",
        }
        body = {
            "season": season,
            "game_id": raw["game_id"],
            "phase": "pregame",
            "home_team": raw.get("home_team"),
            "away_team": raw.get("away_team"),
            "kickoff_utc": raw.get("kickoff_utc"),
            **{k: raw.get(k) for k in _NFL_PREGAME_FIELDS},
        }
        return meta, body

    if not raw.get("concluded_at"):
        raise UnqualifiedSource(f"game {raw.get('game_id')} has no conclusion instant")
    context = {k: raw.get(k) for k in _NFL_POSTGAME_FIELDS + _NFL_PREGAME_FIELDS}
    if not any(v is not None for v in context.values()):
        raise UnqualifiedSource(
            f"game {raw.get('game_id')}: no information-bearing context fields; "
            "a schedule shell is not evidence"
        )
    inst = raw["concluded_at"]
    meta = {
        "fact_type": "nfl_game",
        "source_record_id": f"nflgame:{raw['game_id']}",
        "entity_ref": {"type": "game", "id": str(raw["game_id"])},
        "effective_at": inst,
        "known_at": inst,
        "known_at_basis": raw.get("conclusion_policy", "game_conclusion"),
        "access_scope": "public",
        "privacy": "public",
    }
    body = {
        "season": season,
        "game_id": raw["game_id"],
        "phase": "postgame",
        "home_team": raw.get("home_team"),
        "away_team": raw.get("away_team"),
        "kickoff_utc": raw.get("kickoff_utc"),
        **context,
    }
    return meta, body


NORMALIZERS = {
    "franchise_identity": _franchise_identity,
    "schedule_pairing": _schedule_pairing,
    "matchup_result": _matchup_result,
    "roster_membership": _roster_membership,
    "transaction": _transaction,
    "draft_pick": _draft_pick,
    "chat_message": _chat_message,
    "historical_matchup": _historical_matchup,
    "nfl_game": _nfl_game,
}


# ---------------------------------------------------------------------------
# Iteration
# ---------------------------------------------------------------------------
def _pair_matchup_rows(rows, week):
    """Group live per-roster Sleeper rows by (week, matchup_id) into exactly-two
    pairs (team1 = lower roster_id, deterministic). Dangling/triple groups are
    refused, never guessed. Returns (paired, refused)."""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("matchup_id"), []).append(r)
    paired, refused = [], []
    for mid in sorted(groups, key=lambda m: (m is None, m)):
        g = sorted(groups[mid], key=lambda r: r.get("roster_id") or 0)
        if mid is None or len(g) != 2:
            refused.append({"matchup_id": mid, "week": week, "rows": len(g)})
            continue
        paired.append(
            {
                "week": week,
                "matchup_id": mid,
                "team1": {"roster_id": g[0]["roster_id"], "points": g[0].get("points")},
                "team2": {"roster_id": g[1]["roster_id"], "points": g[1].get("points")},
            }
        )
    return paired, refused


def _require_json(path):
    if not Path(path).exists():
        raise MissingSource(f"source file absent: {path}")
    return load_json(path, required=True)


def _legacy_instants():
    doc = _require_json(LEGACY_INSTANTS_PATH)
    return doc["entries"], doc["policy_id"]


def _week_conclusions():
    doc = _require_json(WEEK_CONCLUSIONS_PATH)
    return doc["weeks"], doc["policy_id"]


def _capture_instant_for(rel_path):
    entries, policy = _legacy_instants()
    if rel_path in entries:
        return entries[rel_path]["instant"], entries[rel_path].get("policy_id", policy)
    # Directory-level entry (e.g. data/2025/nfl_games for 286 per-game files).
    parent = str(Path(rel_path).parent).replace("\\", "/")
    if parent in entries:
        return entries[parent]["instant"], entries[parent].get("policy_id", policy)
    raise MissingSource(
        f"no legacy capture instant for {rel_path}; refusing to invent one "
        "(regenerate content/governance/legacy_capture_instants.v1.json)"
    )


def _conclusion_for(season, week):
    """(instant, policy) or (None, policy): a missing entry yields None and the
    NORMALIZER refuses that record into `unqualified` -- an iterator-raised
    refusal would abort the whole lane over one undatable record."""
    weeks, policy = _week_conclusions()
    return weeks.get(f"{season}:{week}"), policy


def _iter_source(source_root, fact_type, spec, season):
    """Yield (source_ref, env_meta, record). Envelope lane iterates ALL
    envelopes chronologically; legacy lane performs the verified walks with
    versioned instant enrichment. MissingSource raises before the first yield."""
    root = Path(source_root)
    if season >= 2026:
        yield from _iter_envelopes(root, fact_type, spec)
    else:
        yield from _iter_legacy(root, fact_type, spec, season)


def _envelope_files(root, component):
    d = root / "data" / "captures" / "2026" / "public" / component
    if not d.exists():
        raise MissingSource(f"no envelopes for component {component} under {d}")
    return sorted(d.glob("*.json"))  # filename-ordered ISO timestamps = chronological


def _env_meta(env):
    return {
        "captured_at": env["captured_at"],
        "access_scope": env.get("access_scope", "public"),
        "privacy": env.get("privacy", "public"),
    }


def _iter_envelopes(root, fact_type, spec):
    component, _ = spec
    files = _envelope_files(root, component)
    users_docs, users_refs = [], {}
    if fact_type == "franchise_identity":
        try:
            users_files = _envelope_files(root, "sleeper_users")
        except MissingSource:
            users_files = []  # roster-only identity: user fields unavailable
        for up in users_files:
            doc = json.loads(up.read_text(encoding="utf-8"))
            users_docs.append(doc)
            users_refs[doc["captured_at"]] = (
                f"capture:2026/public/sleeper_users/{up.name}"
            )
    for p in files:
        env = json.loads(p.read_text(encoding="utf-8"))
        ref = f"capture:2026/public/{component}/{p.name}"
        meta = _env_meta(env)
        payload = env["payload"]
        if fact_type == "franchise_identity":
            # TEMPORAL RULE: a joined value may never be dated earlier than
            # EITHER input. Only users envelopes captured no later than this
            # rosters envelope are joinable; when none exists yet, the identity
            # is emitted ROSTER-ONLY with user fields explicitly unavailable --
            # never a later capture's names backdated onto an earlier clock.
            eligible = [u for u in users_docs if u["captured_at"] <= env["captured_at"]]
            users_doc = eligible[-1] if eligible else None
            names = (
                {
                    u["user_id"]: u.get("display_name")
                    for u in users_doc["payload"]["users"]
                }
                if users_doc
                else {}
            )
            # Provenance binds BOTH envelopes for a joined observation -- in
            # the source_ref METADATA field, never the hashed body: provenance
            # in the body would make every identical repeat a distinct fact and
            # defeat the design's unconditional coalescing.
            joined_ref = (
                f"{ref}+{users_refs[users_doc['captured_at']]}" if users_doc else ref
            )
            for r in payload["rosters"]:
                rec = {
                    "roster_id": r["roster_id"],
                    "owner_id": r.get("owner_id"),
                    "display_name": names.get(r.get("owner_id")) if users_doc else None,
                    "display_name_unavailable": users_doc is None,
                    "capture_instant": env["captured_at"],
                }
                yield joined_ref, meta, rec
        elif fact_type == "matchup_result":
            for week_str in sorted(payload["matchups"], key=int):
                paired, _refused = _pair_matchup_rows(
                    payload["matchups"][week_str], int(week_str)
                )
                for rec in paired:
                    yield ref, meta, rec  # no concluded_at: refused by the normalizer
        elif fact_type == "transaction":
            for week_str in sorted(payload["transactions"], key=int):
                for rec in payload["transactions"][week_str]:
                    yield ref, meta, rec
        elif fact_type == "draft_pick":
            for pick in payload["picks"]:
                rec = dict(
                    pick,
                    draft_id=payload["draft_id"],
                    draft_instant=env["captured_at"],
                    draft_instant_basis="capture_instant",
                )
                yield ref, meta, rec
        elif fact_type == "nfl_game":
            games = payload if isinstance(payload, list) else payload.get("games", [])
            for rec in games:
                yield ref, meta, rec
        else:  # pragma: no cover - sentinel components never reach here
            raise MissingSource(f"no envelope walk for {fact_type}")


def _iter_legacy(root, fact_type, spec, season):
    pattern, _ = spec
    rel = pattern.replace("{season}", str(season))

    if fact_type == "franchise_identity":
        rel_path = rel
        doc = _require_json(root / rel_path)
        instant, policy = _capture_instant_for(rel_path)
        meta = {"captured_at": instant, "access_scope": "public", "privacy": "public"}
        for rid in sorted(doc["roster_map"], key=int):
            rec = dict(doc["roster_map"][rid])
            rec["capture_instant"] = instant
            rec["capture_instant_basis"] = policy
            yield f"legacy:{rel_path}", meta, rec

    elif fact_type == "matchup_result":
        doc = _require_json(root / rel)
        instant, _cpolicy = _capture_instant_for(rel)
        meta = {"captured_at": instant, "access_scope": "public", "privacy": "public"}
        for wk in doc["weeks"]:
            week = wk["week"]
            concluded_at, policy = _conclusion_for(season, week)
            for m in wk["matchups"]:
                rec = dict(
                    m, week=week, concluded_at=concluded_at, conclusion_policy=policy
                )
                yield f"legacy:{rel}", meta, rec

    elif fact_type == "historical_matchup":
        for prior in PRIOR_SEASONS:
            rel_p = pattern.replace("{prior}", str(prior))
            doc = _require_json(root / rel_p)
            instant, _cpolicy = _capture_instant_for(rel_p)
            meta = {
                "captured_at": instant,
                "access_scope": "public",
                "privacy": "public",
            }
            for wk in doc["weeks"]:
                week = wk["week"]
                concluded_at, policy = _conclusion_for(prior, week)
                for m in wk["matchups"]:
                    rec = dict(
                        m,
                        season=prior,
                        week=week,
                        concluded_at=concluded_at,
                        conclusion_policy=policy,
                    )
                    yield f"legacy:{rel_p}", meta, rec

    elif fact_type == "transaction":
        doc = _require_json(root / rel)
        instant, _cpolicy = _capture_instant_for(rel)
        meta = {"captured_at": instant, "access_scope": "public", "privacy": "public"}
        for week_str in sorted(doc, key=int):
            for rec in doc[week_str]:
                yield f"legacy:{rel}", meta, rec

    elif fact_type == "draft_pick":
        doc = _require_json(root / rel)
        instant, _cpolicy = _capture_instant_for(rel)
        meta = {"captured_at": instant, "access_scope": "public", "privacy": "public"}
        start = doc.get("start_date")
        # draft-window-v1: picks knowable no later than end of the draft start
        # date UTC -- a NAMED policy, far from any cutoff boundary.
        draft_instant = f"{start}T23:59:59Z" if start else None
        for pick in doc["picks"]:
            rec = dict(
                pick,
                draft_id=doc["draft_id"],
                draft_instant=draft_instant,
                draft_instant_basis="draft-window-v1",
            )
            yield f"legacy:{rel}", meta, rec

    elif fact_type == "chat_message":
        doc = _require_json(root / rel)
        instant, policy = _capture_instant_for(rel)
        meta = {
            "captured_at": instant,
            "access_scope": "league_private",
            "privacy": "private",
        }
        msgs = doc["messages"] if isinstance(doc, dict) else doc
        for rec in msgs:
            yield f"legacy:{rel}", meta, rec

    elif fact_type == "nfl_game":
        d = root / rel.split("*")[0].rstrip("/")
        if not d.exists():
            raise MissingSource(f"source directory absent: {d}")
        dir_rel = rel.split("/*")[0]
        instant, _cpolicy = _capture_instant_for(dir_rel + "/x")  # dir-level entry
        meta = {"captured_at": instant, "access_scope": "public", "privacy": "public"}
        pregame = _sched_publication_instant()
        for p in sorted(d.glob("*.json")):
            if p.name.startswith("_"):
                continue  # _expanded_manifest.json: idempotency manifest, not a game
            game = load_json(p, required=True)
            week = game.get("week")
            concluded_at, policy = _conclusion_for(season, week)
            kickoff_utc = _kickoff_utc_for(game)
            rec = dict(
                game,
                concluded_at=concluded_at,
                conclusion_policy=policy,
                kickoff_utc=kickoff_utc,
            )
            yield f"legacy:{dir_rel}/{p.name}", meta, rec
            if pregame is not None:
                pre = {
                    "phase": "pregame",
                    "game_id": game["game_id"],
                    "home_team": game.get("home_team"),
                    "away_team": game.get("away_team"),
                    "kickoff_utc": kickoff_utc,
                    "pregame_known_at": pregame["instant"],
                    "pregame_policy": pregame["policy_id"],
                    **{k: game.get(k) for k in _NFL_PREGAME_FIELDS},
                }
                yield f"legacy:{dir_rel}/{p.name}", meta, pre

    else:  # pragma: no cover - sentinels never reach here
        raise MissingSource(f"no legacy walk for {fact_type}")


def _sched_publication_instant():
    """The qualified schedule-publication instant, or None (pregame lane
    unavailable). Only a committed versioned artifact can supply it."""
    if not SCHED_PUBLICATION_PATH.exists():
        return None
    doc = load_json(SCHED_PUBLICATION_PATH, required=True)
    return {"instant": doc["instant"], "policy_id": doc["policy_id"]}


def _kickoff_utc_for(game):
    """Best-effort kickoff instant from the game's local kickoff + venue map;
    None when unresolvable (kickoff_utc is context, not a clock)."""
    try:
        from scripts.kickoff_source import resolve_zone, to_utc

        tz_map = load_json(
            ROOT / "content" / "governance" / "venue_timezones.json", required=True
        )
        gameday = game.get("gameday")
        kickoff = game.get("kickoff")
        if not gameday or not kickoff:
            return None
        return to_utc(gameday, kickoff, resolve_zone(game, tz_map))
    except Exception:  # noqa: BLE001 - kickoff_utc is context, not a clock
        return None


# ---------------------------------------------------------------------------
# normalize_all
# ---------------------------------------------------------------------------
def normalize_all(source_root, out_path, season, private_out_path=None):
    """Every bridge type, TWO custody-split FactStores, deterministic order, no
    wall clock. Returns the four-bucket honesty report:
    {"counts", "unqualified", "undatable", "unavailable", "normalizer_version"}.
    """
    from scripts.kickoff_source import UnavailableEvidence

    assert set(ENVELOPE_SOURCES) == set(LEGACY_SOURCES) == set(NORMALIZERS)
    sources = ENVELOPE_SOURCES if season >= 2026 else LEGACY_SOURCES
    out_path = Path(out_path)
    store = FactStore(out_path)
    private_store = FactStore(
        Path(private_out_path)
        if private_out_path
        else Path("private_facts") / f"{season}.jsonl"
    )
    counts, unqualified, undatable, unavailable = {}, {}, {}, {}
    actions = {"created": {}, "coalesced": {}, "superseded": {}}
    for fact_type in sorted(sources):
        spec = sources[fact_type]
        if spec[0] is None:
            unavailable[fact_type] = spec[1]
            continue
        try:
            # MissingSource raises from _iter_source BEFORE its first yield (at
            # file open), so this wrap never discards already-observed records.
            for source_ref, env_meta, raw in _iter_source(
                source_root, fact_type, spec, season
            ):
                try:
                    meta, body = NORMALIZERS[fact_type](raw, season)
                except UnqualifiedSource:
                    unqualified[fact_type] = unqualified.get(fact_type, 0) + 1
                    continue
                except UnavailableEvidence:
                    undatable[fact_type] = undatable.get(fact_type, 0) + 1
                    continue
                target = private_store if meta["privacy"] == "private" else store
                _fact, action = target.observe(
                    payload=body,
                    source_ref=source_ref,
                    captured_at=env_meta["captured_at"],  # ENVELOPE/policy, never now()
                    normalizer_version=NORMALIZER_VERSION,
                    **meta,
                )
                actions[action][fact_type] = actions[action].get(fact_type, 0) + 1
                if action != "coalesced":
                    # counts = MATERIALIZED facts. A coalesced repeat writes
                    # nothing; counting it would report an inflated store.
                    counts[fact_type] = counts.get(fact_type, 0) + 1
        except MissingSource as exc:
            unavailable[fact_type] = str(exc)
            continue
    store.write()
    private_store.write()
    if any(f.privacy == "private" for f in store.load()):
        raise ValueError("custody violation: private fact in the public store")
    if season < 2026 and _sched_publication_instant() is None:
        unavailable["nfl_game_pregame"] = (
            "no qualified schedule-publication instant (sched_publication_2025.v1.json absent); "
            "pregame context is not invented or backdated"
        )
    for t in sorted(set(unqualified) - set(counts)):
        unavailable[t] = (
            f"all {unqualified[t]} records refused ({t} yielded zero facts)"
        )
    # Reconciliation is enforced, not asserted in prose: counts must equal the
    # materialized store contents per type, and created+coalesced+superseded
    # must equal the observations that reached a store.
    materialized = {}
    for f in store.load() + private_store.load():
        materialized[f.fact_type] = materialized.get(f.fact_type, 0) + 1
    for t_, n in counts.items():
        if materialized.get(t_, 0) < n:
            raise ValueError(
                f"accounting drift: counts[{t_}]={n} exceeds materialized {materialized.get(t_, 0)}"
            )
    return {
        "counts": counts,
        "actions": actions,
        "unqualified": unqualified,
        "undatable": undatable,
        "unavailable": unavailable,
        "normalizer_version": NORMALIZER_VERSION,
    }


# ---------------------------------------------------------------------------
# Timing-policy artifact emitters + CLI
# ---------------------------------------------------------------------------
def _expand_legacy_paths():
    """The tracked legacy paths needing capture instants: named files per
    season in scope, plus the nfl_games directory (one entry for 286 files),
    plus the chat special entry."""
    paths = [
        "data/2025/season_combined.json",
        "data/2025/transactions.json",
        "data/2025/draft_picks.json",
        "data/2025/nfl_games",
    ]
    paths += [f"data/{prior}/season_combined.json" for prior in PRIOR_SEASONS]
    return paths


def _git_iso_to_canonical_utc(iso):
    dt = datetime.fromisoformat(iso)
    return canonical_instant(dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def _emit_legacy_instants():
    entries = {}
    for path in _expand_legacy_paths():
        iso = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", path],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
        if not iso:
            raise SystemExit(
                f"no git history for {path}; refusing to invent an instant"
            )
        entries[path] = {
            "instant": _git_iso_to_canonical_utc(iso),
            "policy_id": "legacy-capture-v1",
        }
    # The gitignored chat corpus has no git date; its instant is the commit
    # instant of the receipt-bound provenance manifest that verified its bytes.
    iso = subprocess.run(
        ["git", "log", "-1", "--format=%aI", "--", "content/chat/provenance.json"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout.strip()
    entries["chat/parsed_messages.json"] = {
        "instant": _git_iso_to_canonical_utc(iso),
        "policy_id": "chat-capture-v1",
    }
    return {
        "policy_id": "legacy-capture-v1",
        "entries": entries,
        "provenance": (
            "git log -1 --format=%aI -- <path> per tracked legacy path; chat entry from "
            "content/chat/provenance.json's commit instant (chat-capture-v1)"
        ),
    }


def _week_conclusions_from_schedules(seasons):
    """Final gameday of each (season, week) REG slate, advanced to the repo's
    established Tuesday 06:59:59Z weekly boundary."""
    import hashlib

    import polars as pl

    table, hashes = {}, {}
    for season in seasons:
        parquet = ROOT / f"data/external/schedules_{season}.parquet"
        if not parquet.exists():
            raise SystemExit(f"schedules parquet absent: {parquet}; fetch it first")
        hashes[f"data/external/schedules_{season}.parquet"] = (
            "sha256:" + hashlib.sha256(parquet.read_bytes()).hexdigest()
        )
        df = pl.read_parquet(
            parquet
        )  # ALL game types: nfl_games includes playoffs (weeks 19+)
        for week, last_day in (
            df.group_by("week").agg(pl.col("gameday").max()).iter_rows()
        ):
            d = datetime.strptime(last_day, "%Y-%m-%d").date()
            delta = ((1 - d.weekday()) % 7) or 7  # next Tuesday STRICTLY after
            boundary = d + timedelta(days=delta)
            table[f"{season}:{week}"] = canonical_instant(
                boundary.strftime("%Y-%m-%dT06:59:59Z")
            )
    return dict(sorted(table.items())), hashes


def main():
    ap = argparse.ArgumentParser(prog="normalize_facts.py")
    ap.add_argument("--season", type=int)
    ap.add_argument("--source-root", default=".")
    ap.add_argument("--out", help="default: data/facts/{season}.jsonl")
    ap.add_argument(
        "--emit-legacy-instants",
        action="store_true",
        help="print the legacy-capture-v1 artifact JSON to stdout",
    )
    ap.add_argument(
        "--emit-week-conclusions",
        action="store_true",
        help="print the legacy-week-conclusion-v1 artifact JSON to stdout",
    )
    a = ap.parse_args()
    if a.emit_legacy_instants:
        print(json.dumps(_emit_legacy_instants(), indent=2, sort_keys=True))
        return 0
    if a.emit_week_conclusions:
        table, hashes = _week_conclusions_from_schedules(PRIOR_SEASONS + (2025,))
        print(
            json.dumps(
                {
                    "policy_id": "legacy-week-conclusion-v1",
                    "weeks": table,
                    "source_hashes": hashes,
                    "provenance": (
                        "schedules parquet final REG gameday per (season, week) -> "
                        "following Tuesday 06:59:59Z"
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if a.season is None:
        ap.error("--season is required unless emitting an artifact")
    out = Path(a.out) if a.out else Path("data") / "facts" / f"{a.season}.jsonl"
    report = normalize_all(source_root=a.source_root, out_path=out, season=a.season)
    # The report is a DURABLE, TRACKED artifact, not stdout: K3.3's contrast
    # reads availability from it. Counts and refusal reasons only -- no text.
    save_json_canonical(out.with_suffix(".report.json"), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    # Zero facts overall is a failed run, not a quiet success.
    return 0 if report["counts"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
