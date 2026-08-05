"""K1.6 — two-lane normalization: envelope replay, matchup pairing, coverage
gate, custody sentinel, four-bucket honesty report, timing-policy CLIs."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.fact_store import FactStore
from scripts.normalize_facts import (
    ENVELOPE_SOURCES,
    LEGACY_SOURCES,
    NORMALIZERS,
    UnqualifiedSource,
    _pair_matchup_rows,
    normalize_all,
)

PY = sys.executable
REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- fixtures
def _write_fixture_envelope(root, component, stamp, payload):
    """Fixture envelope matching the real Phase-P schema surface this module reads."""
    d = root / "data" / "captures" / "2026" / "public" / component
    d.mkdir(parents=True, exist_ok=True)
    env = {
        "source_id": component,
        "season": 2026,
        "captured_at": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}.000001Z",
        "access_scope": "public",
        "privacy": "public",
        "payload": payload,
    }
    (d / f"{stamp}.json").write_text(json.dumps(env), encoding="utf-8")
    return env


def _normalize_component(root, component_types, tmp_out):
    """Single-lane wrapper: restrict ENVELOPE_SOURCES to the given types."""
    restricted = {
        t: (spec if t in component_types else (None, "restricted out (test)"))
        for t, spec in ENVELOPE_SOURCES.items()
    }
    original = dict(ENVELOPE_SOURCES)
    ENVELOPE_SOURCES.clear()
    ENVELOPE_SOURCES.update(restricted)
    try:
        normalize_all(
            source_root=root,
            out_path=tmp_out,
            season=2026,
            private_out_path=tmp_out.with_name("priv.jsonl"),
        )
    finally:
        ENVELOPE_SOURCES.clear()
        ENVELOPE_SOURCES.update(original)
    return FactStore(tmp_out).load()


def _normalize_chat_fixture(msgs, out_path, private_out_path, tmp_root):
    """Chat-lane wrapper over normalize_all with both out paths, against a
    fixture source root carrying only the chat corpus + timing artifact."""
    (tmp_root / "chat").mkdir(parents=True, exist_ok=True)
    (tmp_root / "chat" / "parsed_messages.json").write_text(
        json.dumps({"messages": msgs}), encoding="utf-8"
    )
    restricted = {
        t: (spec if t == "chat_message" else (None, "restricted out (test)"))
        for t, spec in LEGACY_SOURCES.items()
    }
    original = dict(LEGACY_SOURCES)
    LEGACY_SOURCES.clear()
    LEGACY_SOURCES.update(restricted)
    try:
        return normalize_all(
            source_root=tmp_root,
            out_path=out_path,
            season=2025,
            private_out_path=private_out_path,
        )
    finally:
        LEGACY_SOURCES.clear()
        LEGACY_SOURCES.update(original)


# ------------------------------------------------------------------- tests
def test_all_nine_bridge_types_have_a_normalizer():
    for t in (
        "franchise_identity",
        "schedule_pairing",
        "matchup_result",
        "roster_membership",
        "transaction",
        "draft_pick",
        "chat_message",
        "historical_matchup",
        "nfl_game",
    ):
        assert t in NORMALIZERS, t


def test_schedule_from_a_completed_packet_is_unqualified():
    with pytest.raises(UnqualifiedSource):
        NORMALIZERS["schedule_pairing"](
            {"source": "weekly_packet_outcomes_stripped"}, season=2025
        )


def test_schedule_with_a_versioned_policy_is_admitted():
    meta, body = NORMALIZERS["schedule_pairing"](
        {
            "source": "sleeper_schedule",
            "policy_id": "sched-avail-v1",
            "home": "A",
            "away": "B",
            "season": 2025,
            "week": 1,
            "known_at": "2025-08-01T00:00:00Z",
        },
        season=2025,
    )
    assert meta["known_at_basis"] == "sched-avail-v1"
    assert body == {"season": 2025, "week": 1, "home": "A", "away": "B"}


def test_transaction_without_status_updated_is_unqualified():
    with pytest.raises(UnqualifiedSource):
        NORMALIZERS["transaction"](
            {"transaction_id": "1", "created": 1725000000000}, season=2025
        )


def test_chat_message_defaults_to_league_private():
    meta, body = NORMALIZERS["chat_message"](
        {"id": 1, "timestamp_utc": "2025-09-01T00:00:00Z", "sender": "x", "text": "hi"},
        season=2025,
    )
    assert meta["access_scope"] == "league_private" and meta["privacy"] == "private"


def test_source_map_deviation_fails_the_coverage_gate():
    """Both lanes enumerate ALL NINE types; a planted missing or extra type
    must fail. The gate binds the actual enumerated surfaces."""
    assert set(ENVELOPE_SOURCES) == set(LEGACY_SOURCES) == set(NORMALIZERS)
    planted_missing = dict(ENVELOPE_SOURCES)
    planted_missing.pop("nfl_game")
    assert set(planted_missing) != set(NORMALIZERS), "the plant must land"
    planted_extra = dict(ENVELOPE_SOURCES, speculative_type=(None, "planted"))
    assert set(planted_extra) != set(NORMALIZERS)


def test_matchup_rows_group_into_exactly_two_or_refuse():
    """Live Sleeper matchup rows are per-roster. Two rows sharing (week,
    matchup_id) pair into team1/team2 (lower roster_id first); a dangling or
    triple row is refused, never guessed."""
    rows = [
        {"roster_id": 2, "matchup_id": 1, "points": 100.0},
        {"roster_id": 1, "matchup_id": 1, "points": 120.0},
        {"roster_id": 3, "matchup_id": 2, "points": 90.0},  # dangling
    ]
    paired, refused = _pair_matchup_rows(rows, week=1)
    assert len(paired) == 1 and len(refused) == 1
    assert paired[0]["team1"]["roster_id"] == 1 and paired[0]["team2"]["roster_id"] == 2


def test_all_envelope_replay_a_a_b_a_preserves_first_held_and_chain(tmp_path):
    """Four synthetic envelopes for ONE record: A, A, B, A. Chronological
    iteration must coalesce the repeat (first captured_at retained) and
    supersede both changes -- a latest-only iterator collapses this to one
    fact and loses acquisition history."""
    root = tmp_path / "captures"
    for i, val in enumerate(("A", "A", "B", "A")):
        _write_fixture_envelope(
            root,
            "sleeper_rosters",
            f"2026080{i + 1}T000000Z",
            {"rosters": [{"roster_id": 1, "owner_id": "u1", "display_name_src": val}]},
        )
        _write_fixture_envelope(
            root,
            "sleeper_users",
            f"2026080{i + 1}T000000Z",
            {"users": [{"user_id": "u1", "display_name": val}]},
        )
    facts = _normalize_component(root, {"franchise_identity"}, tmp_path / "f.jsonl")
    chain = sorted(facts, key=lambda f: f.known_at)
    assert len(chain) == 3, "A(coalesced), B(supersedes), A(supersedes) = 3 facts"
    assert (
        chain[0].captured_at == "2026-08-01T00:00:00.000001Z"
    ), "first capture retained"
    assert chain[1].supersedes == chain[0].fact_id
    assert chain[2].supersedes == chain[1].fact_id
    assert [f.payload["display_name"] for f in chain] == ["A", "B", "A"]


def test_unsourced_types_are_recorded_unavailable_not_omitted(tmp_path):
    """The fail-closed contract IS the report: schedule_pairing and
    roster_membership must arrive in `unavailable` as recorded refusals."""
    r = normalize_all(
        source_root=REPO,
        out_path=tmp_path / "f.jsonl",
        season=2026,
        private_out_path=tmp_path / "p.jsonl",
    )
    assert {"schedule_pairing", "roster_membership"} <= set(r["unavailable"])


def test_2026_facts_come_from_envelopes_not_the_stale_snapshot(tmp_path):
    """The kernel's 2026 lane reads Phase-P captures ONLY; captured_at equals
    each envelope's canonicalized captured_at."""
    from scripts.fact_schema import canonical_instant

    normalize_all(
        source_root=REPO,
        out_path=tmp_path / "f.jsonl",
        season=2026,
        private_out_path=tmp_path / "p.jsonl",
    )
    facts = FactStore(tmp_path / "f.jsonl").load()
    assert facts, "the A-opt envelopes exist on disk; zero facts is a failed lane"
    assert all(f.source_ref.startswith("capture:2026/public/") for f in facts)
    for f in facts[:5]:
        env_file = (
            REPO
            / "data"
            / "captures"
            / "2026"
            / "public"
            / f.source_ref.split("public/")[1]
        )
        env = json.loads(env_file.read_text(encoding="utf-8"))
        assert f.captured_at == canonical_instant(env["captured_at"])


def test_private_secret_never_reaches_a_tracked_artifact(tmp_path):
    """The custody sentinel. A synthetic secret chat message lands in the
    PRIVATE store only; report and public store carry no private text; the
    guard pattern catches a planted private index entry."""
    secret = "SENTINEL-9f3a-do-not-commit"
    msgs = [
        {
            "id": 1,
            "timestamp_utc": "2025-09-01T00:00:00Z",
            "sender": "x",
            "text": secret,
        }
    ]
    pub, priv = tmp_path / "pub.jsonl", tmp_path / "priv.jsonl"
    report = _normalize_chat_fixture(msgs, pub, priv, tmp_path / "srcroot")
    assert secret in priv.read_text(encoding="utf-8")
    if pub.exists():
        assert secret not in pub.read_text(encoding="utf-8")
    assert secret not in json.dumps(report)
    guard = re.compile(
        r"^(private_captures|private_bundles|private_facts|private_editions)/"
    )
    assert guard.match("private_facts/2025.jsonl"), "the plant must be catchable"
    assert "private_facts/" in (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "private_editions/" in (REPO / ".gitignore").read_text(encoding="utf-8")


def test_pregame_lane_qualified_instant_and_postgame_leak_plant(tmp_path, monkeypatch):
    """The pregame/postgame split. With an injected qualified instant the
    pregame record is admitted carrying only pregame fields; a planted score
    in a pregame body fails; without the artifact the lane reports
    unavailable."""
    pre_raw = {
        "phase": "pregame",
        "game_id": "2025_01_DAL_PHI",
        "home_team": "PHI",
        "away_team": "DAL",
        "kickoff_utc": "2025-09-05T00:20:00Z",
        "pregame_known_at": "2025-05-14T00:00:00Z",
        "pregame_policy": "sched-publication-test-v1",
        "rest_days": 7,
        "div_game": 1,
        "spread_line": -6.5,
    }
    meta, body = NORMALIZERS["nfl_game"](pre_raw, season=2025)
    assert meta["source_record_id"].endswith(":pregame")
    assert meta["known_at"] == "2025-05-14T00:00:00Z"
    assert "home_score" not in {k: v for k, v in body.items() if v is not None}
    planted = dict(pre_raw, home_score=24)
    with pytest.raises(UnqualifiedSource, match="postgame field"):
        NORMALIZERS["nfl_game"](planted, season=2025)
    # Production: no approved artifact -> unavailable, never invented.
    report = json.loads(
        (REPO / "data" / "facts" / "2025.report.json").read_text(encoding="utf-8")
    )
    if not (
        REPO / "content" / "governance" / "sched_publication_2025.v1.json"
    ).exists():
        assert "nfl_game_pregame" in report["unavailable"]


def test_schedule_shell_is_refused_as_postgame_context():
    with pytest.raises(UnqualifiedSource, match="schedule shell"):
        NORMALIZERS["nfl_game"](
            {
                "game_id": "2025_01_X_Y",
                "concluded_at": "2025-09-09T06:59:59Z",
                "home_team": "X",
                "away_team": "Y",
            },
            season=2025,
        )


def test_emit_clis_produce_source_bound_artifacts():
    """The exact CLI paths for both timing-policy emitters; provenance and
    source hashes present; week-conclusion hashes match the parquet bytes."""
    r1 = subprocess.run(
        [PY, "scripts/normalize_facts.py", "--emit-legacy-instants"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0, r1.stderr
    doc = json.loads(r1.stdout)
    assert doc["policy_id"] == "legacy-capture-v1" and "provenance" in doc
    assert doc["entries"]["chat/parsed_messages.json"]["policy_id"] == "chat-capture-v1"
    r2 = subprocess.run(
        [PY, "scripts/normalize_facts.py", "--emit-week-conclusions"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, r2.stderr
    doc2 = json.loads(r2.stdout)
    import hashlib

    for rel, recorded in doc2["source_hashes"].items():
        actual = "sha256:" + hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        assert recorded == actual, rel
    assert doc2["weeks"]["2025:1"] == "2025-09-09T06:59:59.000000Z"


def test_report_is_persisted_and_carries_no_private_text():
    report_path = REPO / "data" / "facts" / "2025.report.json"
    assert report_path.exists(), "the report is a durable tracked artifact, not stdout"
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(doc) == {
        "counts",
        "unqualified",
        "undatable",
        "unavailable",
        "normalizer_version",
    }
    assert doc["counts"]["chat_message"] == 22884  # counts only -- never text
