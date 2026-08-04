"""A5 acceptance tests — S13 strict load/canonicalization, qualified-artifact
identity (I54/I55 unit), R5 baseline input (I46/I51), bundle compiler with
two-kind source manifest (I19, I20, I22, I43, I56).
"""

import inspect
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.bundle_2026 import (
    build_baseline_standings,
    canonical_json_v1,
    compile_bundle,
    compute_bundle_sha256,
    content_sha256_of,
    freeze_qualified_artifact,
    load_json_strict,
    verify_qualified_artifact,
    write_bundle,
)
from scripts.capture_2026 import CaptureError, capture, freeze_policy

FIXED_NOW = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def git(repo: Path, *args):
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@test",
            *args,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


STANDINGS_DOC = {
    "season": 2025,
    "league_id": "1180228858937966592",
    "playoff_week_start": 3,
    "weeks": [
        {
            "week": 1,
            "is_playoff": False,
            "standings": [
                {"roster_id": 1, "wins": 1, "pf": 100.0},
                {"roster_id": 2, "wins": 0, "pf": 90.0},
                {"roster_id": 3, "wins": 1, "pf": 95.0},
                {"roster_id": 4, "wins": 0, "pf": 80.0},
            ],
        },
        {
            "week": 2,
            "is_playoff": False,
            "standings": [
                {"roster_id": 1, "wins": 2, "pf": 200.5},
                {"roster_id": 2, "wins": 1, "pf": 180.25},
                {"roster_id": 3, "wins": 1, "pf": 180.25},
                {"roster_id": 4, "wins": 0, "pf": 160.0},
            ],
        },
    ],
    # PRODUCTION SHAPE: the real season_combined.json stores roster_map as an
    # object keyed by roster-id strings, not a list (verifier finding 1 —
    # the list-shaped fixture hid a TypeError on the real artifact)
    "roster_map": {
        "1": {
            "roster_id": 1,
            "owner_id": "owner_a",
            "final_record": {"wins": 2, "fpts": 200.5},
        },
        "2": {
            "roster_id": 2,
            "owner_id": "owner_b",
            "final_record": {"wins": 1, "fpts": 180.25},
        },
        "3": {
            "roster_id": 3,
            "owner_id": "owner_c",
            # float-accumulation drift as in the real artifact (5/12 rosters):
            # weekly pf is 180.25 while the stored aggregate reads 180.2500000001
            "final_record": {"wins": 1, "fpts": 180.2500000001},
        },
        "4": {
            "roster_id": 4,
            "owner_id": "owner_d",
            "final_record": {"wins": 0, "fpts": 160.0},
        },
    },
}

# 2026 franchises: owner_c got LOW roster_id 1, owner_b got 2 (tie broken by
# 2026 roster_id ascending); owner_a kept 3; owner_d left, replaced by owner_new
ROSTERS_2026 = [
    {"roster_id": 1, "owner_id": "owner_c", "league_id": "1312884727480352768"},
    {"roster_id": 2, "owner_id": "owner_b", "league_id": "1312884727480352768"},
    {"roster_id": 3, "owner_id": "owner_a", "league_id": "1312884727480352768"},
    {"roster_id": 4, "owner_id": "owner_new", "league_id": "1312884727480352768"},
]


def make_repo(tmp_path: Path, standings=None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "core.autocrlf", "false")
    doc = standings if standings is not None else STANDINGS_DOC
    (repo / "standings.json").write_bytes(json.dumps(doc, indent=2).encode("utf-8"))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixture standings")
    return repo


def store_envelope(tmp_path, source_id, payload, captured_at, now=None):
    if now is None:
        # the store accumulates over time: clock rides just past captured_at
        now = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    return capture(
        source_id,
        payload,
        request={"endpoint_or_dataset": f"fixture:{source_id}", "params": {}},
        season=2026,
        league_id="1312884727480352768",
        captured_at=captured_at,
        known_at_basis="fixture",
        access_scope="public",
        privacy="public",
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        now=now,
    )


def make_fixture_policy(tmp_path, repo: Path) -> Path:
    """Freeze a baseline policy whose standings locator points into the
    fixture repo (repo-relative, as production points into the real repo)."""
    from scripts.capture_2026 import build_candidate_policy_v1

    candidate = build_candidate_policy_v1()
    for row in candidate["rows"]:
        if row["source_id"] == "standings_2025":
            row["locator_or_endpoint"] = "standings.json"
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate), encoding="utf-8")
    return freeze_policy(
        path, "v1", governance_dir=tmp_path / "governance", now=FIXED_NOW
    )


CUTOFF_GAMES = [
    {
        "game_id": "2026_01_AAA_BBB",
        "season": 2026,
        "game_type": "REG",
        "week": 1,
        "gameday": "2026-09-09",
        "weekday": "n/a",
        "gametime": "20:20",
        "away_team": "AAA",
        "home_team": "BBB",
    }
]

# capture instant for the fixture store: fresh against the seal-layer clock
# (2026-08-25T12:00Z) under the candidate policy's freshness windows
STORE_CAPTURED_AT = "2026-08-25T09:00:00Z"


def make_cutoff_receipt(tmp_path) -> Path:
    from scripts.cutoff_2026 import build_cutoff_receipt, write_cutoff_receipt

    envelope = store_envelope(
        tmp_path,
        "nfl_schedules",
        {"dataset": "schedules", "season": 2026, "games": CUTOFF_GAMES},
        "2026-08-04T10:00:00Z",
    )
    receipt = build_cutoff_receipt(envelope, now=FIXED_NOW)
    return write_cutoff_receipt(receipt, receipts_root=tmp_path / "receipts")


def full_store(tmp_path):
    """All three required capture envelopes, fresh against the seal clock."""
    store_envelope(
        tmp_path,
        "sleeper_league",
        {"league_id": "1312884727480352768"},
        STORE_CAPTURED_AT,
    )
    store_envelope(
        tmp_path,
        "sleeper_rosters",
        {"rosters": ROSTERS_2026, "count": 4},
        STORE_CAPTURED_AT,
    )
    store_envelope(
        tmp_path,
        "nfl_schedules",
        {"dataset": "schedules", "season": 2026, "games": CUTOFF_GAMES},
        STORE_CAPTURED_AT,
    )


def compile_fixture_bundle(tmp_path, edition="2026-preseason", **overrides):
    repo = overrides.pop("repo", None) or make_repo(tmp_path)
    policy_path = overrides.pop("policy_path", None) or make_fixture_policy(
        tmp_path, repo
    )
    receipt_path = overrides.pop("receipt_path", None) or make_cutoff_receipt(tmp_path)
    return compile_bundle(
        edition,
        "record_points",
        policy_path=policy_path,
        cutoff_receipt_path=receipt_path,
        public_root=tmp_path / "public",
        private_root=tmp_path / "private",
        repo_root=repo,
        **overrides,
    )


# ---------------------------------------------------------------------------
# I53 — strict load + canonicalization at the byte boundary
# ---------------------------------------------------------------------------


def test_strict_loader_rejects_nested_duplicate_keys():
    with pytest.raises(CaptureError):
        load_json_strict(b'{"a": 1, "a": 2}')
    with pytest.raises(CaptureError):
        load_json_strict(b'{"outer": {"x": {"k": 1, "k": 2}}}')
    with pytest.raises(CaptureError):
        load_json_strict(b'{"arr": [{"k": 1, "k": 2}]}')


def test_strict_loader_rejects_nan_inf_neginf():
    for bad in (b'{"x": NaN}', b'{"x": Infinity}', b'{"x": -Infinity}'):
        with pytest.raises(CaptureError):
            load_json_strict(bad)


def test_strict_loader_operates_on_raw_bytes_not_parsed_objects():
    with pytest.raises(CaptureError):
        load_json_strict({"already": "parsed"})
    with pytest.raises(CaptureError):
        load_json_strict('{"a": 1}')  # str is not bytes
    assert load_json_strict(b'{"a": 1}') == {"a": 1}


def test_canonical_json_v1_params_and_single_trailing_lf():
    out = canonical_json_v1({"b": 2, "a": {"z": 1, "y": [1, 2]}, "s": "café"})
    text = out.decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert text.index('"a"') < text.index('"b"') < text.index('"s"')  # sorted
    assert "café" in text  # ensure_ascii=False
    assert "  " in text  # indent=2
    with pytest.raises(ValueError):
        canonical_json_v1({"x": float("nan")})  # allow_nan=False
    # byte-stable across runs / insertion orders
    assert canonical_json_v1({"a": 1, "b": 2}) == canonical_json_v1({"b": 2, "a": 1})


# ---------------------------------------------------------------------------
# I54 — freeze binds commit/path/blob and demands canonical equality
# ---------------------------------------------------------------------------


def test_freeze_binds_commit_path_blob_oid_and_blob_bytes_sha256(tmp_path):
    repo = make_repo(tmp_path)
    entry = freeze_qualified_artifact(
        "standings_2025", "standings.json", repo_root=repo
    )
    assert entry["kind"] == "qualified_artifact"
    assert entry["commit_sha"] == git(repo, "rev-parse", "HEAD")
    assert entry["git_blob_oid"] == git(repo, "rev-parse", "HEAD:standings.json")
    blob = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", entry["git_blob_oid"]],
        capture_output=True,
    ).stdout
    import hashlib

    assert entry["blob_bytes_sha256"] == hashlib.sha256(blob).hexdigest()
    assert entry["content_sha256"] == content_sha256_of(blob)
    assert entry["canonicalizer_id"] and entry["canonicalizer_version"]
    assert entry["canonicalizer_code_sha256"]
    # worktree observations are present but diagnostic
    assert entry["observed_worktree_bytes_sha256"]
    assert entry["byte_count"] > 0
    assert entry["eol_profile"] in ("lf", "crlf", "mixed", "none")


def test_freeze_requires_worktree_canonically_equal_to_bound_blob(tmp_path):
    repo = make_repo(tmp_path)
    # a semantic (non-materialization) worktree change must fail the freeze
    doc = json.loads((repo / "standings.json").read_text(encoding="utf-8"))
    doc["playoff_week_start"] = 4
    (repo / "standings.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(CaptureError):
        freeze_qualified_artifact("standings_2025", "standings.json", repo_root=repo)

    # a pure CRLF rematerialization of identical content must still freeze
    git(repo, "checkout", "--", "standings.json")
    lf_bytes = (repo / "standings.json").read_bytes().replace(b"\r\n", b"\n")
    (repo / "standings.json").write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
    entry = freeze_qualified_artifact(
        "standings_2025", "standings.json", repo_root=repo
    )
    assert entry["eol_profile"] == "crlf"


# ---------------------------------------------------------------------------
# I55 (unit) — verification reads the BOUND blob, never the worktree
# ---------------------------------------------------------------------------


def test_rederive_reads_bound_blob_not_current_worktree(tmp_path):
    repo = make_repo(tmp_path)
    entry = freeze_qualified_artifact(
        "standings_2025", "standings.json", repo_root=repo
    )
    # later legitimate edit: semantic worktree change AFTER the freeze
    doc = json.loads((repo / "standings.json").read_text(encoding="utf-8"))
    doc["playoff_week_start"] = 4
    (repo / "standings.json").write_text(json.dumps(doc), encoding="utf-8")

    ok, diagnostics, errors = verify_qualified_artifact(entry, repo_root=repo)
    assert ok, errors  # the bound blob still verifies
    assert any("worktree" in d for d in diagnostics)


def test_missing_or_mismatched_bound_git_evidence_fails_closed(tmp_path):
    repo = make_repo(tmp_path)
    entry = freeze_qualified_artifact(
        "standings_2025", "standings.json", repo_root=repo
    )

    doctored = dict(entry, blob_bytes_sha256="0" * 64)
    ok, _, errors = verify_qualified_artifact(doctored, repo_root=repo)
    assert not ok and any("blob_bytes_sha256" in e for e in errors)

    doctored = dict(entry, git_blob_oid="0" * 40)
    ok, _, errors = verify_qualified_artifact(doctored, repo_root=repo)
    assert not ok

    doctored = dict(entry, commit_sha="0" * 40)
    ok, _, errors = verify_qualified_artifact(doctored, repo_root=repo)
    assert not ok

    doctored = dict(entry, content_sha256="0" * 64)
    ok, _, errors = verify_qualified_artifact(doctored, repo_root=repo)
    assert not ok and any("content_sha256" in e for e in errors)


def test_worktree_difference_reported_as_same_content_different_materialization(
    tmp_path,
):
    repo = make_repo(tmp_path)
    entry = freeze_qualified_artifact(
        "standings_2025", "standings.json", repo_root=repo
    )
    # rematerialize the worktree copy as CRLF — identical content
    raw = (repo / "standings.json").read_bytes().replace(b"\r\n", b"\n")
    (repo / "standings.json").write_bytes(raw.replace(b"\n", b"\r\n"))

    ok, diagnostics, errors = verify_qualified_artifact(entry, repo_root=repo)
    assert ok, errors
    assert any("same_content_different_materialization" in d for d in diagnostics)


# ---------------------------------------------------------------------------
# I46 / I51 — R5 baseline input
# ---------------------------------------------------------------------------


def test_baseline_uses_playoff_week_start_and_tiebreaks():
    rows = build_baseline_standings(STANDINGS_DOC, ROSTERS_2026)
    # owner_a 2-0 first; owner_b vs owner_c tie on (1, 180.25) broken by
    # 2026 roster_id ascending: owner_c has roster 1, owner_b roster 2
    assert [r["owner_id"] for r in rows] == [
        "owner_a",
        "owner_c",
        "owner_b",
        "owner_new",
    ]
    assert [r["rank"] for r in rows] == [1, 2, 3, 4]


def test_baseline_recomputes_wins_and_pf_and_crosschecks_final_record():
    rows = build_baseline_standings(STANDINGS_DOC, ROSTERS_2026)
    by_owner = {r["owner_id"]: r for r in rows}
    assert by_owner["owner_a"]["wins_2025"] == 2
    assert by_owner["owner_a"]["points_for_2025"] == 200.5

    # a stored aggregate that disagrees with the recomputation fails closed
    doctored = json.loads(json.dumps(STANDINGS_DOC))
    doctored["roster_map"]["1"]["final_record"]["wins"] = 9
    with pytest.raises(CaptureError):
        build_baseline_standings(doctored, ROSTERS_2026)
    # ...and a points-for disagreement beyond scoring granularity also fails
    doctored2 = json.loads(json.dumps(STANDINGS_DOC))
    doctored2["roster_map"]["1"]["final_record"]["fpts"] = 199.9
    with pytest.raises(CaptureError):
        build_baseline_standings(doctored2, ROSTERS_2026)


def test_baseline_joins_2025_to_2026_by_owner_id():
    rows = build_baseline_standings(STANDINGS_DOC, ROSTERS_2026)
    by_owner = {r["owner_id"]: r for r in rows}
    # owner_c moved from 2025 roster 3 to 2026 roster 1 — record follows OWNER
    assert by_owner["owner_c"]["roster_id"] == 1
    assert by_owner["owner_c"]["wins_2025"] == 1
    assert by_owner["owner_c"]["points_for_2025"] == 180.25


def test_baseline_builds_from_real_2025_artifact():
    """Regression net for the two production-shape findings: the COMMITTED
    2025 artifact (dict roster_map, float drift on 5/12 rosters) and the
    committed 2026 rosters must build end to end — fixtures can no longer
    diverge from reality without this failing."""
    from scripts.shared import REPO_ROOT

    standings = json.loads(
        (REPO_ROOT / "data" / "2025" / "season_combined.json").read_text(
            encoding="utf-8"
        )
    )
    rosters = json.loads(
        (REPO_ROOT / "data" / "2026" / "rosters.json").read_text(encoding="utf-8")
    )
    rows = build_baseline_standings(standings, rosters)
    assert len(rows) == 12
    assert [r["rank"] for r in rows] == list(range(1, 13))
    assert all(r["matched"] for r in rows)  # owner overlap is 12/12
    wins = [r["wins_2025"] for r in rows]
    assert wins == sorted(wins, reverse=True)


def test_unmatched_2026_franchise_sorts_last_deterministically():
    rows = build_baseline_standings(STANDINGS_DOC, ROSTERS_2026)
    last = rows[-1]
    assert last["owner_id"] == "owner_new"
    assert last["matched"] is False
    assert last["wins_2025"] == 0 and last["points_for_2025"] == 0.0


# ---------------------------------------------------------------------------
# I19 / I20 / I43 / I56 / I22 — the bundle compiler
# ---------------------------------------------------------------------------


def test_compiler_excludes_post_cutoff_envelopes(tmp_path):
    full_store(tmp_path)
    # a POST-preseason-cutoff rosters envelope (cutoff 2026-09-03T00:20:00Z)
    store_envelope(
        tmp_path,
        "sleeper_rosters",
        {"rosters": [dict(ROSTERS_2026[0], owner_id="postcutoff")], "count": 1},
        "2026-09-03T09:00:00Z",
    )
    bundle = compile_fixture_bundle(tmp_path)
    rosters_entry = next(
        e for e in bundle["source_manifest"] if e["source_id"] == "sleeper_rosters"
    )
    assert rosters_entry["captured_at"] == STORE_CAPTURED_AT  # pre-cutoff one


def test_no_caller_supplied_bundle_or_factset_hash(tmp_path):
    params = inspect.signature(compile_bundle).parameters
    assert not any(
        "sha" in name or "hash" in name or "factset" in name for name in params
    )
    full_store(tmp_path)
    bundle = compile_fixture_bundle(tmp_path)
    assert bundle["bundle_sha256"] == compute_bundle_sha256(bundle)
    # tampering the compiled bundle is detectable by recomputation
    tampered = json.loads(json.dumps(bundle))
    tampered["decision_input_payload"]["franchises"][0]["wins_2025"] = 99
    assert compute_bundle_sha256(tampered) != bundle["bundle_sha256"]


def test_bundle_binds_canonical_decision_input_and_projection_versions(tmp_path):
    full_store(tmp_path)
    bundle = compile_fixture_bundle(tmp_path)
    from scripts.bundle_2026 import sha256_hex

    assert bundle["decision_input_sha256"] == sha256_hex(
        canonical_json_v1(bundle["decision_input_payload"])
    )
    projection = bundle["projection"]
    for field in (
        "ordering_version",
        "redaction_version",
        "projection_version",
        "code_sha256",
        "config_sha256",
        "parameters",
    ):
        assert projection[field] or projection[field] == {}
    assert bundle["cutoff_receipt_locator"] and bundle["cutoff_receipt_sha256"]
    assert bundle["policy_locator"] and bundle["matrix_sha256"]


def test_source_manifest_carries_capture_and_qualified_entries(tmp_path):
    full_store(tmp_path)
    bundle = compile_fixture_bundle(tmp_path)
    kinds = {e["source_id"]: e["kind"] for e in bundle["source_manifest"]}
    assert kinds["standings_2025"] == "qualified_artifact"
    assert kinds["sleeper_rosters"] == "capture"
    for entry in bundle["source_manifest"]:
        assert entry["content_sha256"] and entry["canonicalizer_id"]
        if entry["kind"] == "capture":
            assert entry["envelope_sha256"] and entry["payload_sha256"]
            assert entry["captured_at"]
        else:
            assert entry["commit_sha"] and entry["git_blob_oid"]
            assert entry["blob_bytes_sha256"]


def test_all_four_a7_sources_present_and_verified(tmp_path):
    full_store(tmp_path)
    bundle = compile_fixture_bundle(tmp_path)
    assert {e["source_id"] for e in bundle["source_manifest"]} == {
        "standings_2025",
        "sleeper_rosters",
        "sleeper_league",
        "nfl_schedules",
    }


def test_manifest_missing_a_required_source_fails_bundle(tmp_path):
    # no sleeper_league envelope in the store
    store_envelope(
        tmp_path,
        "sleeper_rosters",
        {"rosters": ROSTERS_2026, "count": 4},
        "2026-08-20T10:00:00Z",
    )
    with pytest.raises(CaptureError):
        compile_fixture_bundle(tmp_path)


def test_private_bundle_stays_untracked(tmp_path):
    full_store(tmp_path)
    bundle = compile_fixture_bundle(tmp_path)
    bundle["contains_private"] = True
    bundle["bundle_sha256"] = compute_bundle_sha256(bundle)
    path = write_bundle(
        bundle,
        public_bundles_root=tmp_path / "seals",
        private_bundles_root=tmp_path / "priv_bundles",
    )
    assert path.resolve().is_relative_to((tmp_path / "priv_bundles").resolve())

    # and the real private root is gitignored (I37 already proves the pattern)
    result = subprocess.run(
        ["git", "check-ignore", "-q", "private_bundles/2026/x/bundle.json"],
        capture_output=True,
    )
    assert result.returncode == 0
