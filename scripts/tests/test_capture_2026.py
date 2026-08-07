"""Tranche-A acceptance tests for scripts/capture_2026.py (envelope core).

Contract: docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md
A1 scope: S1 envelope write/verify — invariants I1, I2, I3, I4, I5.
Every test here is a named test from the contract's section 7 table.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.capture_2026 import (
    A7_REQUIRED_SOURCES,
    CaptureError,
    build_candidate_policy_v1,
    capture,
    compute_policy_sha256,
    freeze_policy,
    load_capture_table,
    load_policy,
    verify_envelope,
)
from scripts.shared import REPO_ROOT

FIXED_NOW = datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)
CONTRACT_PATH = (
    REPO_ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-03-jailyard-p-only-fallback.md"
)


def valid_kwargs(tmp_path: Path, **overrides):
    """A fully valid public-capture argument set; tests break one field at a time."""
    kwargs = dict(
        request={"endpoint_or_dataset": "/league/1312884727480352768", "params": {}},
        season=2026,
        league_id="1312884727480352768",
        captured_at="2026-08-04T10:00:00Z",
        known_at_basis="sleeper API read at captured_at",
        access_scope="public",
        privacy="public",
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        now=FIXED_NOW,
    )
    kwargs.update(overrides)
    return kwargs


def written_files(root: Path):
    return [p for p in root.rglob("*.json")] if root.exists() else []


# ---------------------------------------------------------------------------
# I1 — a failed fetch is never an envelope
# ---------------------------------------------------------------------------


def test_failed_fetch_is_never_written(tmp_path):
    kwargs = valid_kwargs(tmp_path)
    # fetch_sleeper.fetch_json returns None on exhausted retries -> refused
    with pytest.raises(CaptureError):
        capture("sleeper_league", None, **kwargs)
    # non-object payloads are refused (producers wrap lists into objects)
    for bad in ("a string", 42, ["bare", "list"], True):
        with pytest.raises(CaptureError):
            capture("sleeper_league", bad, **kwargs)
    assert written_files(tmp_path / "public") == []
    assert written_files(tmp_path / "private") == []


def test_empty_payload_respects_empty_valid(tmp_path):
    kwargs = valid_kwargs(tmp_path)
    with pytest.raises(CaptureError):
        capture("sleeper_transactions", {}, empty_valid=False, **kwargs)
    assert written_files(tmp_path / "public") == []

    path = capture("sleeper_transactions", {}, empty_valid=True, **kwargs)
    assert path.exists()
    ok, errors = verify_envelope(path)
    assert ok, errors


# ---------------------------------------------------------------------------
# I2 — capture() validates its own arguments (manual ingestion skips main())
# ---------------------------------------------------------------------------


def test_capture_validates_its_own_arguments(tmp_path):
    payload = {"league_id": "1312884727480352768"}

    # captured_at must be an exact tz-aware instant
    for bad_ts in (
        None,
        "",
        "2026-08",  # month-only
        "2026-08-04",  # date-only
        "2026-08-04T10:00:00",  # naive
        "2026-13-04T10:00:00Z",  # malformed
        20260804,
    ):
        with pytest.raises(CaptureError):
            capture(
                "sleeper_league",
                payload,
                **valid_kwargs(tmp_path, captured_at=bad_ts),
            )

    # enum fields are closed sets
    with pytest.raises(CaptureError):
        capture("sleeper_league", payload, **valid_kwargs(tmp_path, privacy="secret"))
    with pytest.raises(CaptureError):
        capture(
            "sleeper_league",
            payload,
            **valid_kwargs(tmp_path, access_scope="internal"),
        )

    # scope/privacy bijection: league_private data may never be written public
    with pytest.raises(CaptureError):
        capture(
            "chat_export",
            payload,
            **valid_kwargs(tmp_path, access_scope="league_private", privacy="public"),
        )
    with pytest.raises(CaptureError):
        capture(
            "sleeper_league",
            payload,
            **valid_kwargs(tmp_path, access_scope="public", privacy="private"),
        )

    # basis and request identity are mandatory
    with pytest.raises(CaptureError):
        capture("sleeper_league", payload, **valid_kwargs(tmp_path, known_at_basis=""))
    with pytest.raises(CaptureError):
        capture("sleeper_league", payload, **valid_kwargs(tmp_path, request=None))
    with pytest.raises(CaptureError):
        capture(
            "sleeper_league",
            payload,
            **valid_kwargs(tmp_path, request={"params": {}}),
        )

    # source_id is a filesystem-safe slug
    for bad_sid in ("", "UPPER", "a b", "a/b", "a\\b", "../escape", "a.b"):
        with pytest.raises(CaptureError):
            capture(bad_sid, payload, **valid_kwargs(tmp_path))

    assert written_files(tmp_path / "public") == []
    assert written_files(tmp_path / "private") == []


# ---------------------------------------------------------------------------
# I3 — append-only store
# ---------------------------------------------------------------------------


def test_append_only_refuses_overwrite(tmp_path):
    kwargs = valid_kwargs(tmp_path)
    payload = {"league_id": "1312884727480352768"}
    path = capture("sleeper_league", payload, **kwargs)
    original = path.read_bytes()

    with pytest.raises(CaptureError):
        capture("sleeper_league", {"different": "payload"}, **kwargs)
    assert path.read_bytes() == original


# ---------------------------------------------------------------------------
# I4 — future-dated captures are refused
# ---------------------------------------------------------------------------


def test_future_dated_capture_refused(tmp_path):
    with pytest.raises(CaptureError):
        capture(
            "sleeper_league",
            {"league_id": "x"},
            **valid_kwargs(tmp_path, captured_at="2026-08-04T13:00:00Z"),
        )
    assert written_files(tmp_path / "public") == []


# ---------------------------------------------------------------------------
# I5 — verification checks payload AND metadata; a tampered envelope is
# not coverage
# ---------------------------------------------------------------------------


def test_tampered_payload_is_not_coverage(tmp_path):
    path = capture(
        "sleeper_league",
        {"league_id": "1312884727480352768", "season": "2026"},
        **valid_kwargs(tmp_path),
    )
    ok, errors = verify_envelope(path)
    assert ok, errors

    env = json.loads(path.read_text(encoding="utf-8"))
    env["payload"]["season"] = "2027"
    path.write_text(json.dumps(env, indent=2), encoding="utf-8")

    ok, errors = verify_envelope(path)
    assert not ok
    assert any("payload_sha256" in e for e in errors)


def test_tampered_metadata_is_not_coverage(tmp_path):
    path = capture(
        "sleeper_league",
        {"league_id": "1312884727480352768"},
        **valid_kwargs(tmp_path),
    )
    env = json.loads(path.read_text(encoding="utf-8"))
    env["captured_at"] = "2026-08-01T00:00:00Z"  # backdate the metadata
    path.write_text(json.dumps(env, indent=2), encoding="utf-8")

    ok, errors = verify_envelope(path)
    assert not ok
    assert any("envelope_sha256" in e for e in errors)


# ---------------------------------------------------------------------------
# A1b — policy freeze (I47, I57) and gate-reachability census (I58)
# ---------------------------------------------------------------------------


def write_candidate(tmp_path: Path, doc=None, name="candidate.json") -> Path:
    doc = doc if doc is not None else build_candidate_policy_v1()
    path = tmp_path / name
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def candidate_sha(doc) -> str:
    """The approval identity: sha256 of the canonical unstamped candidate."""
    from scripts.capture_2026 import canonical_bytes, sha256_hex

    return sha256_hex(canonical_bytes(doc))


def freeze_v1(tmp_path: Path, **overrides):
    gov = overrides.pop("governance_dir", tmp_path / "governance")
    doc = build_candidate_policy_v1()
    return freeze_policy(
        write_candidate(tmp_path, doc),
        "v1",
        expected_candidate_sha256=candidate_sha(doc),
        governance_dir=gov,
        now=FIXED_NOW,
        **overrides,
    )


def test_policy_version_immutable_and_freeze_refuses_overwrite(tmp_path):
    gov = tmp_path / "governance"
    frozen = freeze_v1(tmp_path, governance_dir=gov)
    assert frozen.name == "source_policy_2026.v1.json"
    original = frozen.read_bytes()

    doc = load_policy(frozen)
    assert doc["policy_version"] == "v1"
    assert doc["scope"] == "baseline"
    assert doc["policy_sha256"] == compute_policy_sha256(doc)

    # freezing the same version again is refused and the bytes are untouched
    doc2 = build_candidate_policy_v1()
    with pytest.raises(CaptureError):
        freeze_policy(
            write_candidate(tmp_path, doc2, name="candidate2.json"),
            "v1",
            expected_candidate_sha256=candidate_sha(doc2),
            governance_dir=gov,
            now=FIXED_NOW,
        )
    assert frozen.read_bytes() == original


def test_freeze_never_writes_another_version_file(tmp_path):
    gov = tmp_path / "governance"
    frozen_v1 = freeze_v1(tmp_path, governance_dir=gov)
    v1_bytes = frozen_v1.read_bytes()
    before = {p.name for p in gov.iterdir()}

    v2_doc = build_candidate_policy_v1()
    v2_doc["policy_version"] = "v2"
    v2_doc["scope"] = "model_arms"
    for row in v2_doc["rows"]:
        row["policy_version"] = "v2"
        row["scope"] = "model_arms"
        row["arms"] = []
        row["required_for"] = []
    frozen_v2 = freeze_policy(
        write_candidate(tmp_path, v2_doc, name="candidate_v2.json"),
        "v2",
        expected_candidate_sha256=candidate_sha(v2_doc),
        governance_dir=gov,
        now=FIXED_NOW,
    )
    after = {p.name for p in gov.iterdir()}
    assert after - before == {"source_policy_2026.v2.json"}
    assert frozen_v1.read_bytes() == v1_bytes  # I49's A-side: v1 bytes untouched
    assert frozen_v2.name == "source_policy_2026.v2.json"


def test_v1_matches_schema_and_contains_exactly_the_declared_rows(tmp_path):
    frozen = freeze_v1(tmp_path)
    doc = load_policy(frozen)

    components = {
        c for group in load_capture_table()["groups"] for c in group["components"]
    }
    expected = components | {
        "standings_2025",
        "league_history_2022",
        "league_history_2023",
        "league_history_2024",
        "player_crosswalk",
    }
    assert len(expected) == 17
    assert {row["source_id"] for row in doc["rows"]} == expected

    required = {
        row["source_id"] for row in doc["rows"] if row["required_for"] or row["arms"]
    }
    assert required == set(A7_REQUIRED_SOURCES)
    for row in doc["rows"]:
        if row["source_id"] in A7_REQUIRED_SOURCES:
            assert row["required_for"] == ["record_points"]
        else:
            assert row["arms"] == [] and row["required_for"] == []
        assert row["policy_version"] == "v1" and row["scope"] == "baseline"
        assert row["kind"] in ("capture", "qualified_artifact")
        assert row["editions"] == ["2026-preseason", "2026-wk01-preview"]
        window = row["availability_window"]
        assert window["opens_at_rule"] and window["closes_at_rule"]
        if row["source_id"] == "chat_export":
            assert row["chat_refresh"]["initial"] and row["chat_refresh"]["subsequent"]

    # a candidate whose raw bytes carry duplicate keys is refused (fail-closed)
    dup = tmp_path / "dup.json"
    dup.write_text(
        '{"policy_version": "v3", "policy_version": "v3",'
        ' "scope": "baseline", "rows": []}',
        encoding="utf-8",
    )
    with pytest.raises(CaptureError):
        freeze_policy(
            dup,
            "v3",
            expected_candidate_sha256="0" * 64,  # strict load refuses first
            governance_dir=tmp_path / "gov3",
            now=FIXED_NOW,
        )


def test_freeze_requires_and_verifies_approved_candidate_hash(tmp_path):
    """The freeze boundary IS the approval boundary: absence or mismatch of
    the approved candidate's canonical sha256 fails closed before any file
    is created — a merely schema-valid candidate is not an approved one."""
    doc = build_candidate_policy_v1()
    path = write_candidate(tmp_path, doc)
    gov = tmp_path / "gov"

    with pytest.raises(CaptureError, match="fail closed"):
        freeze_policy(path, "v1", governance_dir=gov, now=FIXED_NOW)
    assert not gov.exists() or not list(gov.iterdir())

    different = build_candidate_policy_v1()
    for row in different["rows"]:
        if row["source_id"] == "sleeper_rosters":
            row["freshness"] = 999999
    with pytest.raises(CaptureError, match="not the approved one"):
        freeze_policy(
            write_candidate(tmp_path, different, name="different.json"),
            "v1",
            expected_candidate_sha256=candidate_sha(doc),  # approved != supplied
            governance_dir=gov,
            now=FIXED_NOW,
        )
    assert not gov.exists() or not list(gov.iterdir())

    frozen = freeze_policy(
        path,
        "v1",
        expected_candidate_sha256=candidate_sha(doc),
        governance_dir=gov,
        now=FIXED_NOW,
    )
    assert frozen.exists()


def test_capture_timestamp_sampled_after_acquisition(tmp_path):
    """Production timestamping happens only AFTER successful acquisition: a
    fetch that starts before a cutoff and completes after it can never be
    recorded as pre-cutoff (capture-time backdating)."""
    import time
    from datetime import datetime as real_datetime

    (tmp_path / "league.json").write_text(
        '{"league_id": "1312884727480352768"}', encoding="utf-8"
    )
    marks = {}

    def slow_fetch(endpoint, **_):
        marks["cutoff"] = real_datetime.now(timezone.utc)  # cutoff mid-fetch
        time.sleep(0.002)
        marks["completed"] = real_datetime.now(timezone.utc)
        return {"league_id": "1312884727480352768"}

    from scripts.capture_2026 import produce_sleeper_league

    path = produce_sleeper_league(
        fetch=slow_fetch,
        league_json_path=tmp_path / "league.json",
        public_root=tmp_path / "public",
        now=None,  # PRODUCTION mode: no injected clock
    )
    env = json.loads(path.read_text(encoding="utf-8"))
    stamped = datetime.fromisoformat(env["captured_at"].replace("Z", "+00:00"))
    assert stamped >= marks["completed"] > marks["cutoff"]

    # the cutoff-crossing consequence: selection at the mid-fetch cutoff
    # must NOT admit this envelope
    from scripts.bundle_2026 import _latest_envelope_at_or_before

    cutoff_iso = marks["cutoff"].isoformat().replace("+00:00", "Z")
    assert (
        _latest_envelope_at_or_before(
            "sleeper_league", [tmp_path / "public"], cutoff_iso
        )
        is None
    )


def test_run_tranche_passes_unresolved_clock_to_producers(tmp_path, monkeypatch):
    """run_tranche must not inject a pre-resolved clock into producers:
    production (now=None) reaches producers as None so they stamp
    post-acquisition; an explicit fixture clock still reaches them intact."""
    import scripts.capture_2026 as cap

    seen = []

    def spy_producer(source_id, **kwargs):
        seen.append(kwargs.get("now"))
        raise cap.CaptureError("spy: no envelope")

    monkeypatch.setattr(cap, "_run_producer", spy_producer)
    policy = freeze_v1(tmp_path)

    run_tranche_kwargs = dict(
        policy_path=policy,
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        league_json_path=tmp_path / "league.json",
        run_producers=True,
    )
    from scripts.capture_2026 import run_tranche

    run_tranche("A", receipts_root=tmp_path / "r1", now=None, **run_tranche_kwargs)
    assert seen == [None, None, None]  # production: producers self-clock

    seen.clear()
    run_tranche("A", receipts_root=tmp_path / "r2", now=FIXED_NOW, **run_tranche_kwargs)
    assert seen == [FIXED_NOW, FIXED_NOW, FIXED_NOW]  # fixtures deterministic


# ---------------------------------------------------------------------------
# A2 — required producers (I9, I50a) and the optional lane (I7, I8)
# ---------------------------------------------------------------------------


def fake_fetch(mapping):
    """Endpoint -> payload map; a missing endpoint returns None (failed fetch)."""

    def fetch(endpoint, **_):
        return mapping.get(endpoint)

    return fetch


def league_json(tmp_path: Path, league_id="1312884727480352768") -> Path:
    path = tmp_path / "league.json"
    path.write_text(json.dumps({"league_id": league_id}), encoding="utf-8")
    return path


LEAGUE_PAYLOAD = {
    "league_id": "1312884727480352768",
    "season": "2026",
    "status": "in_season",
}


def test_league_id_verified_against_fetched_payload(tmp_path):
    from scripts.capture_2026 import produce_sleeper_league

    good = fake_fetch({"/league/1312884727480352768": LEAGUE_PAYLOAD})
    path = produce_sleeper_league(
        fetch=good,
        league_json_path=league_json(tmp_path),
        public_root=tmp_path / "public",
        now=FIXED_NOW,
    )
    ok, errors = verify_envelope(path)
    assert ok, errors

    # fetched payload disagreeing with the on-disk league id is refused
    mismatched = fake_fetch(
        {"/league/1312884727480352768": {**LEAGUE_PAYLOAD, "league_id": "999"}}
    )
    with pytest.raises(CaptureError):
        produce_sleeper_league(
            fetch=mismatched,
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public2",
            now=FIXED_NOW,
        )
    assert written_files(tmp_path / "public2") == []

    # a failed fetch (None) is never an envelope
    with pytest.raises(CaptureError):
        produce_sleeper_league(
            fetch=fake_fetch({}),
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public3",
            now=FIXED_NOW,
        )
    assert written_files(tmp_path / "public3") == []


def test_a7_required_set_is_exactly_the_four_named_sources(tmp_path):
    doc = load_policy(freeze_v1(tmp_path))
    required = {
        row["source_id"]
        for row in doc["rows"]
        if "record_points" in row["required_for"]
    }
    assert required == {
        "standings_2025",
        "sleeper_rosters",
        "sleeper_league",
        "nfl_schedules",
    }
    assert required == set(A7_REQUIRED_SOURCES)


def test_rosters_producer_wraps_and_verifies(tmp_path):
    from scripts.capture_2026 import produce_sleeper_rosters

    rosters = [
        {"roster_id": i, "owner_id": f"owner{i}", "league_id": "1312884727480352768"}
        for i in range(1, 13)
    ]
    path = produce_sleeper_rosters(
        fetch=fake_fetch({"/league/1312884727480352768/rosters": rosters}),
        league_json_path=league_json(tmp_path),
        public_root=tmp_path / "public",
        now=FIXED_NOW,
    )
    ok, errors = verify_envelope(path)
    assert ok, errors
    env = json.loads(path.read_text(encoding="utf-8"))
    assert env["payload"]["count"] == 12
    assert env["payload"]["rosters"][0]["owner_id"] == "owner1"

    # a roster row bound to a different league is refused
    foreign = [dict(rosters[0], league_id="999")] + rosters[1:]
    with pytest.raises(CaptureError):
        produce_sleeper_rosters(
            fetch=fake_fetch({"/league/1312884727480352768/rosters": foreign}),
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public2",
            now=FIXED_NOW,
        )


SCHED_ROW = {
    "game_id": "2026_01_DAL_PHI",
    "season": 2026,
    "game_type": "REG",
    "week": 1,
    "gameday": "2026-09-09",
    "weekday": "Wednesday",
    "gametime": "20:20",
    "away_team": "DAL",
    "home_team": "PHI",
}


def test_schedules_producer_validates_season_and_shape(tmp_path):
    from scripts.capture_2026 import produce_nfl_schedules

    path = produce_nfl_schedules(
        load_rows=lambda season: [SCHED_ROW],
        public_root=tmp_path / "public",
        now=FIXED_NOW,
    )
    ok, errors = verify_envelope(path)
    assert ok, errors
    env = json.loads(path.read_text(encoding="utf-8"))
    assert env["payload"]["season"] == 2026
    assert env["payload"]["games"][0]["game_id"] == "2026_01_DAL_PHI"

    with pytest.raises(CaptureError):
        produce_nfl_schedules(
            load_rows=lambda season: [],
            public_root=tmp_path / "public2",
            now=FIXED_NOW,
        )
    with pytest.raises(CaptureError):
        produce_nfl_schedules(
            load_rows=lambda season: [dict(SCHED_ROW, season=2025)],
            public_root=tmp_path / "public3",
            now=FIXED_NOW,
        )


# --- optional lane (I7, I8) — written with the lane, gate at B1 -------------


def test_partial_leg_failure_is_not_an_empty_week(tmp_path):
    from scripts.capture_optional_2026 import produce_sleeper_transactions

    legs = {f"/league/1312884727480352768/transactions/{w}": [] for w in range(1, 19)}
    legs["/league/1312884727480352768/transactions/7"] = None  # outage, not quiet
    with pytest.raises(CaptureError):
        produce_sleeper_transactions(
            fetch=fake_fetch(legs),
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public",
            now=FIXED_NOW,
        )
    assert written_files(tmp_path / "public") == []


def test_all_legs_read_and_empty_is_valid(tmp_path):
    from scripts.capture_optional_2026 import produce_sleeper_transactions

    legs = {f"/league/1312884727480352768/transactions/{w}": [] for w in range(1, 19)}
    path = produce_sleeper_transactions(
        fetch=fake_fetch(legs),
        league_json_path=league_json(tmp_path),
        public_root=tmp_path / "public",
        now=FIXED_NOW,
    )
    ok, errors = verify_envelope(path)
    assert ok, errors
    env = json.loads(path.read_text(encoding="utf-8"))
    assert env["payload"]["weeks_requested"] == list(range(1, 19))
    assert all(env["payload"]["transactions"][str(w)] == [] for w in range(1, 19))


def test_draft_reaches_picks_and_fails_on_metadata_only(tmp_path):
    from scripts.capture_optional_2026 import produce_draft_picks

    drafts = [{"draft_id": "1312884727488737280", "status": "complete"}]
    picks = [
        {"pick_no": n, "round": (n - 1) // 12 + 1, "player_id": str(n)}
        for n in range(1, 73)
    ]
    mapping = {
        "/league/1312884727480352768/drafts": drafts,
        "/draft/1312884727488737280/picks": picks,
    }
    path = produce_draft_picks(
        fetch=fake_fetch(mapping),
        league_json_path=league_json(tmp_path),
        public_root=tmp_path / "public",
        now=FIXED_NOW,
    )
    env = json.loads(path.read_text(encoding="utf-8"))
    assert env["payload"]["pick_count"] == 72
    assert [p["pick_no"] for p in env["payload"]["picks"]] == list(range(1, 73))

    # metadata resolves but picks are empty -> the component FAILS
    with pytest.raises(CaptureError):
        produce_draft_picks(
            fetch=fake_fetch({**mapping, "/draft/1312884727488737280/picks": []}),
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public2",
            now=FIXED_NOW,
        )
    # out-of-order picks -> order not preserved -> refused
    shuffled = [picks[1], picks[0]] + picks[2:]
    with pytest.raises(CaptureError):
        produce_draft_picks(
            fetch=fake_fetch({**mapping, "/draft/1312884727488737280/picks": shuffled}),
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public3",
            now=FIXED_NOW,
        )


# ---------------------------------------------------------------------------
# A3 — tranche-scoped accounting (I10-I13, I15, I16a, I16b, I50b)
# ---------------------------------------------------------------------------


def _capture_component(tmp_path, source_id, payload=None, captured_at=None, **kw):
    return capture(
        source_id,
        payload if payload is not None else {"data": source_id},
        **valid_kwargs(
            tmp_path,
            captured_at=captured_at or "2026-08-04T10:00:00Z",
            request={"endpoint_or_dataset": f"fixture:{source_id}", "params": {}},
            **kw,
        ),
    )


def _capture_required_three(tmp_path):
    for sid in ("sleeper_league", "sleeper_rosters", "nfl_schedules"):
        _capture_component(tmp_path, sid)


def accounting(tmp_path, policy_doc_path=None, now=FIXED_NOW, tranche="A", errors=None):
    from scripts.capture_2026 import build_accounting_receipt

    if policy_doc_path is None:
        frozen = tmp_path / "governance" / "source_policy_2026.v1.json"
        policy_doc_path = frozen if frozen.exists() else freeze_v1(tmp_path)
    return build_accounting_receipt(
        load_policy(policy_doc_path),
        tranche=tranche,
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        now=now,
        producer_errors=errors or {},
    )


def test_eight_groups_twelve_components_independent(tmp_path):
    receipt = accounting(tmp_path)
    groups = {g["group"]: g for g in receipt["groups"]}
    assert set(groups) == {
        "league_identity",
        "rosters",
        "draft",
        "transactions",
        "league_matchups",
        "projections",
        "nfl_context",
        "chat",
    }
    components = [c for g in receipt["groups"] for c in g["components"]]
    assert len(components) == 12
    assert groups["league_identity"]["components"][0]["source_id"] == "sleeper_league"
    for component in components:
        assert component["status"] in ("captured", "due", "not_due", "error")
        for field in (
            "source_id",
            "required_for",
            "mechanism",
            "cadence",
            "availability_window",
            "empty_valid",
            "captured_at",
            "payload_sha256",
            "envelope_sha256",
            "error",
            "acquisition_trigger",
        ):
            assert field in component, f"{component['source_id']} missing {field}"


def test_group_passes_only_when_required_components_pass(tmp_path):
    # required component captured, optional sibling absent -> group incomplete
    # but the tranche-A gate passes (I11 evaluates the tranche in scope)
    _capture_required_three(tmp_path)
    receipt = accounting(tmp_path)
    groups = {g["group"]: g for g in receipt["groups"]}
    assert groups["league_identity"]["status"] == "incomplete"  # users absent
    assert receipt["ok"] is True and receipt["unmet_required"] == []

    # required component missing -> its group blocks the tranche
    receipt2 = accounting(tmp_path, now=FIXED_NOW, tranche="A")
    (tmp_path / "public" / "sleeper_league").rename(tmp_path / "hidden")
    receipt2 = accounting(tmp_path)
    assert receipt2["ok"] is False
    assert "sleeper_league" in receipt2["unmet_required"]


def test_not_due_before_window_due_after(tmp_path):
    candidate = build_candidate_policy_v1()
    for row in candidate["rows"]:
        if row["source_id"] == "sleeper_users":
            row["availability_window"]["opens_at_rule"] = "utc:2026-09-01T00:00:00Z"
        if row["source_id"] == "draft_meta":
            row["availability_window"]["opens_at_rule"] = "utc:2026-08-01T00:00:00Z"
    policy = freeze_policy(
        write_candidate(tmp_path, candidate),
        "v1",
        expected_candidate_sha256=candidate_sha(candidate),
        governance_dir=tmp_path / "governance",
        now=FIXED_NOW,
    )
    receipt = accounting(tmp_path, policy_doc_path=policy)
    status = {
        c["source_id"]: c["status"] for g in receipt["groups"] for c in g["components"]
    }
    assert status["sleeper_users"] == "not_due"  # window opens 2026-09-01
    assert status["draft_meta"] == "due"  # open since 2026-08-01, absent


def test_stale_component_returns_to_due(tmp_path):
    # sleeper_rosters freshness is 48h; captured 2026-08-01 vs now 2026-08-04
    _capture_component(tmp_path, "sleeper_rosters", captured_at="2026-08-01T00:00:00Z")
    receipt = accounting(tmp_path)
    status = {
        c["source_id"]: c["status"] for g in receipt["groups"] for c in g["components"]
    }
    assert status["sleeper_rosters"] == "due"
    assert "sleeper_rosters" in receipt["unmet_required"]

    # a fresh capture flips it to captured
    _capture_component(tmp_path, "sleeper_rosters", captured_at="2026-08-04T09:00:00Z")
    receipt2 = accounting(tmp_path)
    status2 = {
        c["source_id"]: c["status"] for g in receipt2["groups"] for c in g["components"]
    }
    assert status2["sleeper_rosters"] == "captured"


def test_component_clears_after_ingestion(tmp_path):
    receipt = accounting(tmp_path)
    status = {
        c["source_id"]: c["status"] for g in receipt["groups"] for c in g["components"]
    }
    assert status["sleeper_league"] == "due"

    _capture_component(tmp_path, "sleeper_league")
    receipt2 = accounting(tmp_path)
    status2 = {
        c["source_id"]: c["status"] for g in receipt2["groups"] for c in g["components"]
    }
    assert status2["sleeper_league"] == "captured"  # no permanent unavailable


def test_tranche_a_gate_ignores_unfinished_rich_components(tmp_path):
    _capture_required_three(tmp_path)
    receipt = accounting(tmp_path, errors={"sleeper_projections": "endpoint 500"})
    assert receipt["ok"] is True
    assert receipt["unmet_required"] == []

    # the SAME store fails the tranche-B gate (rich components unmet)
    receipt_b = accounting(
        tmp_path, tranche="B", errors={"sleeper_projections": "endpoint 500"}
    )
    assert receipt_b["ok"] is False
    assert "sleeper_projections" in receipt_b["unmet_required"]
    assert "chat_export" in receipt_b["unmet_required"]


def test_nonbaseline_component_due_or_error_cannot_block_a7(tmp_path):
    _capture_required_three(tmp_path)
    receipt = accounting(
        tmp_path,
        errors={"nfl_injuries": "nflreadpy timeout", "draft_picks": "api 502"},
    )
    status = {
        c["source_id"]: c["status"] for g in receipt["groups"] for c in g["components"]
    }
    assert status["nfl_injuries"] == "error"
    assert status["draft_picks"] == "error"
    assert status["chat_export"] in ("due", "not_due")
    assert receipt["ok"] is True  # none of them can block A7
    assert receipt["unmet_required"] == []


def test_receipt_carries_no_payload_or_chat(tmp_path):
    secret = "TRADE VETO rant from the group chat 2026-08-01"
    capture(
        "chat_export",
        {"messages_requested": ["2026-08"], "messages": [{"text": secret}]},
        **valid_kwargs(
            tmp_path,
            access_scope="league_private",
            privacy="private",
            request={"endpoint_or_dataset": "manual:whatsapp_export", "params": {}},
        ),
    )
    _capture_required_three(tmp_path)
    receipt = accounting(tmp_path)
    serialized = json.dumps(receipt)
    assert secret not in serialized
    assert "TRADE VETO" not in serialized
    assert '"payload"' not in serialized
    status = {c["source_id"]: c for g in receipt["groups"] for c in g["components"]}
    assert status["chat_export"]["status"] == "captured"
    assert status["chat_export"]["payload_sha256"]  # hashes yes, content no


def test_cli_exits_nonzero_on_unmet_required_component(tmp_path, monkeypatch):
    import scripts.capture_2026 as cap
    from scripts.capture_2026 import main, run_tranche

    # the real gate logic, against a fixture store missing everything
    policy = freeze_v1(tmp_path)
    receipt_path, code = run_tranche(
        "A",
        policy_path=policy,
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        receipts_root=tmp_path / "receipts",
        now=FIXED_NOW,
        run_producers=False,
    )
    assert code == 1
    assert receipt_path.exists()  # the receipt is still written (I16b)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["ok"] is False and receipt["unmet_required"]

    # and once the required three exist, the same gate passes
    _capture_required_three(tmp_path)
    receipt_path2, code2 = run_tranche(
        "A",
        policy_path=policy,
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        receipts_root=tmp_path / "receipts",
        now=FIXED_NOW.replace(hour=13),
        run_producers=False,
    )
    assert code2 == 0

    # main() wires run_tranche's exit code through unchanged
    monkeypatch.setattr(cap, "run_tranche", lambda *a, **k: (tmp_path / "r.json", 1))
    assert main(["--season", "2026", "--tranche", "A"]) == 1


def test_producer_runtime_error_still_writes_receipt(tmp_path, monkeypatch):
    """I16b — a non-ValueError producer failure (nflreadpy/polars/OS error)
    becomes an honest per-component error and the receipt is STILL written,
    never a bare traceback with no receipt."""
    import scripts.capture_2026 as cap
    from scripts.capture_2026 import run_tranche

    def exploding_producer(source_id, **kwargs):
        raise RuntimeError("unknown feature flag: 'sse3'")

    monkeypatch.setattr(cap, "_run_producer", exploding_producer)
    receipt_path, code = run_tranche(
        "A",
        policy_path=freeze_v1(tmp_path),
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        receipts_root=tmp_path / "receipts",
        now=FIXED_NOW,
        run_producers=True,
    )
    assert code == 1
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    statuses = {c["source_id"]: c for g in receipt["groups"] for c in g["components"]}
    assert statuses["sleeper_league"]["status"] == "error"
    assert "RuntimeError" in statuses["sleeper_league"]["error"]


def test_receipt_chronology_generated_at_after_admitted_captures(tmp_path, monkeypatch):
    """F1 control — a green receipt's generated_at is at or after EVERY
    admitted captured_at: the accounting clock resolves only after all
    producer attempts complete."""
    import scripts.capture_2026 as cap
    from scripts.capture_2026 import run_tranche

    def post_acquisition_producer(source_id, *, league_json_path, public_root, now):
        assert now is None  # production passthrough preserved
        stamp = datetime.now(timezone.utc)
        return capture(
            source_id,
            {"data": source_id},
            request={"endpoint_or_dataset": f"fixture:{source_id}", "params": {}},
            season=2026,
            league_id="1312884727480352768",
            captured_at=stamp.isoformat().replace("+00:00", "Z"),
            known_at_basis="post-acquisition stamp",
            access_scope="public",
            privacy="public",
            public_root=public_root,
            private_root=tmp_path / "private",
            now=stamp,
        )

    monkeypatch.setattr(cap, "_run_producer", post_acquisition_producer)
    receipt_path, code = run_tranche(
        "A",
        policy_path=freeze_v1(tmp_path),
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        receipts_root=tmp_path / "receipts",
        now=None,  # PRODUCTION mode
        run_producers=True,
    )
    assert code == 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["ok"] is True
    generated = datetime.fromisoformat(receipt["generated_at"].replace("Z", "+00:00"))
    admitted = [
        c["captured_at"]
        for g in receipt["groups"]
        for c in g["components"]
        if c["status"] == "captured"
    ]
    assert len(admitted) == 3
    for value in admitted:
        assert datetime.fromisoformat(value.replace("Z", "+00:00")) <= generated


def test_future_relative_envelope_cannot_satisfy_tranche_gate(tmp_path):
    """F1 control — an envelope captured after the accounting clock is a
    chronology violation: never 'captured', fails the gate closed."""
    capture(
        "sleeper_league",
        {"league_id": "1312884727480352768"},
        **valid_kwargs(
            tmp_path,
            captured_at="2026-08-04T13:00:00Z",
            now=datetime(2026, 8, 4, 13, 0, 0, tzinfo=timezone.utc),
        ),
    )
    _capture_component(tmp_path, "sleeper_rosters")
    _capture_component(tmp_path, "nfl_schedules")
    receipt = accounting(tmp_path)  # accounting clock is FIXED_NOW (12:00)
    status = {c["source_id"]: c for g in receipt["groups"] for c in g["components"]}
    assert status["sleeper_league"]["status"] == "error"
    assert "chronology" in status["sleeper_league"]["error"]
    assert receipt["ok"] is False
    assert "sleeper_league" in receipt["unmet_required"]


def test_gate_reachability_census_reports_zero_violations():
    """I58 — parse section 8's gate cells and section 10.B's census from the
    contract file; assert full coverage, ordering, and zero unreachable rows."""
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    order = {
        "A1": 0,
        "A1b": 1,
        "A2": 2,
        "A3": 3,
        "A4": 4,
        "A5": 5,
        "A6": 6,
        "A7": 7,
        "lane": 7.5,
        "B1": 8,
        "B2": 9,
        "B3": 10,
        "B4": 11,
        "B5": 12,
    }

    def expand(cell):
        tokens = set()
        for m in re.finditer(r"I(\d+)[ab]?–I(\d+)", cell):
            for n in range(int(m.group(1)), int(m.group(2)) + 1):
                tokens.add(f"I{n}")
        rest = re.sub(r"I\d+[ab]?–I\d+", "", cell)
        for m in re.finditer(r"\bI(\d+[ab]?)\b", rest):
            tokens.add(f"I{m.group(1)}")
        if re.search(r"\bR1\b", cell):
            tokens.add("R1")
        return tokens

    gate_tokens = {}
    for m in re.finditer(r"^\| \*\*(A\d+b?|B\d+)\*\*\s+\|(.+)\|(.+)\|\s*$", text, re.M):
        for token in expand(m.group(3)):
            gate_tokens.setdefault(token, set()).add(m.group(1))
    # Floor tripwire: the contract's gate surface is 62 tokens today. A parse
    # that shrinks (format drift, regex rot) must FAIL here, not silently pass
    # a smaller surface — planted-deviation probe 5 caught exactly that.
    assert (
        len(gate_tokens) >= 60
    ), f"only {len(gate_tokens)} gate tokens parsed — section 8 format drifted?"

    census = {}
    section = text.split("### B. Gate-reachability census")[1].split("### C.")[0]
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith(("| Invariant", "| ---")):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 5:
            continue
        for token in expand(cols[0]):
            assert token not in census, f"census maps {token} twice"
            census[token] = cols
    assert census, "no census rows parsed"

    violations = []
    for token, tasks in sorted(gate_tokens.items()):
        if token not in census:
            violations.append(f"gate token {token} ({sorted(tasks)}) unmapped")
            continue
        _, gate_col, _, delivered_col, reachable = census[token][:5]
        gates = re.findall(r"\b(A\d+b?|B\d+|lane)\b", gate_col)
        delivered = re.findall(r"\b(A\d+b?|B\d+|lane)\b", delivered_col)
        if "✅" not in reachable:
            violations.append(f"{token} not marked reachable")
        if gates and delivered:
            if max(order[t] for t in delivered) > max(order[t] for t in gates):
                violations.append(f"{token}: delivered {delivered} after gate {gates}")
        for task in tasks:
            if task not in gates:
                violations.append(
                    f"{token}: section 8 gates it at {task}, census says {gates}"
                )
    assert violations == [], "census violations: " + "; ".join(violations)


# --- B1: sleeper_projections producer ---------------------------------------
# The frozen policy row sets empty_valid=false and flags the endpoint shape as
# unverified. These tests pin the fail-closed rules; the shape was qualified
# against a live 2026 response before the producer was written.


def _proj_rec(week=1, season="2026", season_type="regular", pid="10881"):
    return {
        "player_id": pid,
        "season": season,
        "week": week,
        "season_type": season_type,
        "company": "rotowire",
        "stats": {"pts_ppr": 12.3},
    }


def fake_projection_fetch(mapping):
    """mapping: (season, week, season_type) -> payload (or None for unreadable)."""

    def _fetch(season, week, season_type):
        return mapping.get((season, week, season_type), None)

    return _fetch


def test_projections_capture_records_weeks_and_counts(tmp_path):
    from scripts.capture_optional_2026 import produce_sleeper_projections

    records = [_proj_rec(pid=str(n)) for n in range(1, 26)]
    path = produce_sleeper_projections(
        fetch=fake_projection_fetch({(2026, 1, "regular"): records}),
        league_json_path=league_json(tmp_path),
        public_root=tmp_path / "public",
        now=FIXED_NOW,
    )
    ok, errors = verify_envelope(path)
    assert ok, errors
    env = json.loads(path.read_text(encoding="utf-8"))
    assert env["payload"]["weeks_requested"] == [1]
    assert env["payload"]["counts"] == {"1": 25}
    assert len(env["payload"]["projections"]["1"]) == 25
    assert env["request"]["params"]["season_type"] == "regular"
    assert env["access_scope"] == "public" and env["privacy"] == "public"


def test_projections_unreadable_week_is_not_an_empty_week(tmp_path):
    from scripts.capture_optional_2026 import produce_sleeper_projections

    with pytest.raises(CaptureError):
        produce_sleeper_projections(
            fetch=fake_projection_fetch({}),  # None -> unreadable
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public",
            now=FIXED_NOW,
        )
    assert written_files(tmp_path / "public") == []


def test_projections_empty_payload_is_refused(tmp_path):
    """The frozen policy sets empty_valid=false for this source."""
    from scripts.capture_optional_2026 import produce_sleeper_projections

    with pytest.raises(CaptureError):
        produce_sleeper_projections(
            fetch=fake_projection_fetch({(2026, 1, "regular"): []}),
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public",
            now=FIXED_NOW,
        )
    assert written_files(tmp_path / "public") == []


def test_projections_non_list_response_is_refused(tmp_path):
    from scripts.capture_optional_2026 import produce_sleeper_projections

    with pytest.raises(CaptureError):
        produce_sleeper_projections(
            fetch=fake_projection_fetch({(2026, 1, "regular"): {"error": "nope"}}),
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public",
            now=FIXED_NOW,
        )
    assert written_files(tmp_path / "public") == []


def test_projections_response_must_match_the_request(tmp_path):
    """The discriminating check: the payload self-reports season/week/
    season_type, so a shifted or wrong-season response is caught at capture
    instead of being trusted into a bundle. Each field is planted alone."""
    from scripts.capture_optional_2026 import produce_sleeper_projections

    plants = [
        [_proj_rec(season="2025")],
        [_proj_rec(week=2)],
        [_proj_rec(season_type="post")],
        [_proj_rec(), _proj_rec(season="2025")],  # one bad record among good
    ]
    for i, records in enumerate(plants):
        with pytest.raises(CaptureError, match="does not match the request"):
            produce_sleeper_projections(
                fetch=fake_projection_fetch({(2026, 1, "regular"): records}),
                league_json_path=league_json(tmp_path),
                public_root=tmp_path / f"public{i}",
                now=FIXED_NOW,
            )
        assert written_files(tmp_path / f"public{i}") == []


def test_projections_is_registered_as_a_producer():
    """capture_2026 --component sleeper_projections must dispatch; before B1 it
    exited 1 with 'no producer for component'."""
    from scripts.capture_optional_2026 import OPTIONAL_PRODUCERS

    assert "sleeper_projections" in OPTIONAL_PRODUCERS


def test_projections_rejects_an_unknown_season_type(tmp_path):
    from scripts.capture_optional_2026 import produce_sleeper_projections

    with pytest.raises(CaptureError):
        produce_sleeper_projections(
            league_json_path=league_json(tmp_path),
            public_root=tmp_path / "public",
            now=FIXED_NOW,
            season_type="preseason",
        )
    assert written_files(tmp_path / "public") == []
