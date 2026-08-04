"""A6 acceptance tests — run receipt, claims, seal, reload verify, rederive.

Contract invariants: I24-I32, I44 (seal discipline), I21 (rederivation),
I42 end-to-end, I48 (policy binding on reload), I52 (v1 alone completes),
I55 end-to-end (old seal survives a later worktree edit), I59 (optional
modules absent), S3 freeze/drift pair, I46 locator+hash binding.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.capture_2026 import CaptureError
from scripts.seal_2026 import (
    close_run,
    find_predecessor,
    open_run,
    rederive_trial,
    run_trial,
    seal_trial,
    verify_seal_dir,
)
from scripts.tests.test_bundle_2026 import (
    full_store,
    make_cutoff_receipt,
    make_fixture_policy,
    make_repo,
)

# preseason cutoff in the fixtures is 2026-09-03T00:20:00Z; this clock is
# comfortably before it, so completed+sealed runs label prospective
SEAL_NOW = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
POST_CUTOFF_NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def build_world(tmp_path):
    """Store + repo + frozen v1 + cutoff receipt, shared by most tests."""
    full_store(tmp_path)
    repo = make_repo(tmp_path)
    policy_path = make_fixture_policy(tmp_path, repo)
    receipt_path = make_cutoff_receipt(tmp_path)
    return {
        "policy_path": policy_path,
        "cutoff_receipt_path": receipt_path,
        "seals_root": tmp_path / "seals",
        "public_root": tmp_path / "public",
        "private_root": tmp_path / "private",
        "repo_root": repo,
    }


def sealed_trial(tmp_path, world=None, edition="2026-preseason", trial=1, now=SEAL_NOW):
    world = world or build_world(tmp_path)
    trial_dir = run_trial(edition, "record_points", trial, now=now, **world)
    return world, trial_dir


# ---------------------------------------------------------------------------
# I24 — production clock is not injectable
# ---------------------------------------------------------------------------


def test_production_clock_is_not_injectable():
    import scripts.bundle_2026 as bundle_mod
    import scripts.capture_2026 as capture_mod
    import scripts.cutoff_2026 as cutoff_mod
    import scripts.seal_2026 as seal_mod

    for mod in (capture_mod, cutoff_mod, bundle_mod, seal_mod):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        # no CLI clock flag and no environment clock override anywhere
        assert "--now" not in source, mod.__name__
        assert "--clock" not in source, mod.__name__
        assert "JAILYARD_NOW" not in source, mod.__name__
        for line in source.splitlines():
            if "environ" in line:
                raise AssertionError(f"{mod.__name__} reads the environment: {line}")


# ---------------------------------------------------------------------------
# I25 / I26 — timestamp ordering and the prospective label
# ---------------------------------------------------------------------------


def test_timestamp_ordering_enforced(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    receipt = json.loads((trial_dir / "receipt.json").read_text(encoding="utf-8"))
    seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
    started = datetime.fromisoformat(receipt["started_at"].replace("Z", "+00:00"))
    ended = datetime.fromisoformat(receipt["ended_at"].replace("Z", "+00:00"))
    sealed = datetime.fromisoformat(seal["sealed_at"].replace("Z", "+00:00"))
    assert started <= ended <= sealed

    # an out-of-order close is refused at the API
    opened = open_run(
        "2026-preseason",
        "record_points",
        7,
        bundle=json.loads(
            (
                world["seals_root"] / "2026-preseason" / "record_points" / "bundle.json"
            ).read_text(encoding="utf-8")
        ),
        cutoff_receipt_path=world["cutoff_receipt_path"],
        policy_path=world["policy_path"],
        seals_root=world["seals_root"],
        started_at=SEAL_NOW,
    )
    with pytest.raises(CaptureError):
        close_run(
            opened,
            {"any": "decision"},
            ended_at=datetime(2026, 8, 25, 11, 0, 0, tzinfo=timezone.utc),
        )


def test_prospective_requires_both_completion_and_sealing_before_cutoff(tmp_path):
    _, trial_dir = sealed_trial(tmp_path, now=SEAL_NOW)
    seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
    assert seal["label"] == "prospective"


def test_late_completion_early_seal_is_retrospective(tmp_path):
    _, trial_dir = sealed_trial(tmp_path, now=POST_CUTOFF_NOW)
    seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
    assert seal["label"] == "retrospective"


def test_backdating_is_impossible(tmp_path):
    # a seal whose recorded instants were doctored to look pre-cutoff no
    # longer hashes: reload detects the rewrite. No reclassification API
    # exists (grep guard), so retrospective cannot become prospective.
    world, trial_dir = sealed_trial(tmp_path, now=POST_CUTOFF_NOW)
    seal_path = trial_dir / "seal.sealed.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["label"] = "prospective"
    seal["sealed_at"] = "2026-08-25T12:00:00Z"
    seal["ended_at"] = "2026-08-25T12:00:00Z"
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok
    assert any("decision_hash" in e for e in errors)

    import scripts.seal_2026 as seal_mod

    source = Path(seal_mod.__file__).read_text(encoding="utf-8")
    assert "reclassify" not in source.lower()


# ---------------------------------------------------------------------------
# I27 / I28 / I30 — closed-run discipline, keying, seal immutability
# ---------------------------------------------------------------------------


def test_sealing_an_open_run_refused(tmp_path):
    world = build_world(tmp_path)
    trial_dir = world["seals_root"] / "2026-preseason" / "record_points" / "trial9"
    trial_dir.mkdir(parents=True)
    # write an OPEN receipt (no ended_at / output_decision_sha256)
    from scripts.bundle_2026 import compile_bundle, write_bundle

    bundle = compile_bundle(
        "2026-preseason",
        "record_points",
        policy_path=world["policy_path"],
        cutoff_receipt_path=world["cutoff_receipt_path"],
        public_root=world["public_root"],
        private_root=world["private_root"],
        repo_root=world["repo_root"],
    )
    write_bundle(bundle, public_bundles_root=world["seals_root"])
    opened = open_run(
        "2026-preseason",
        "record_points",
        9,
        bundle=bundle,
        cutoff_receipt_path=world["cutoff_receipt_path"],
        policy_path=world["policy_path"],
        seals_root=world["seals_root"],
        started_at=SEAL_NOW,
    )
    (trial_dir / "receipt.json").write_bytes(
        json.dumps(opened, indent=2).encode("utf-8")
    )
    # decision and claims BOTH exist and are valid, so the ONLY possible
    # refusal left is the open receipt itself (I27) — a missing-file error
    # must not be able to satisfy this test
    from scripts.seal_2026 import build_claims, run_record_points

    decision = run_record_points(bundle)
    (trial_dir / "decision.json").write_bytes(
        json.dumps(decision, indent=2).encode("utf-8")
    )
    claims = build_claims(decision, bundle, opened["decision_run_id"], 9)
    (trial_dir / "claims.json").write_bytes(
        json.dumps(claims, indent=2).encode("utf-8")
    )
    with pytest.raises(CaptureError, match="OPEN run"):
        seal_trial(trial_dir, repo_root=world["repo_root"], now=SEAL_NOW)
    assert not (trial_dir / "seal.sealed.json").exists()


def test_artifacts_keyed_by_edition_arm_trial(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    assert trial_dir == (
        world["seals_root"] / "2026-preseason" / "record_points" / "trial1"
    )
    for name in ("receipt.json", "decision.json", "claims.json", "seal.sealed.json"):
        assert (trial_dir / name).exists()
    # a second run of the same (edition, arm, trial) must not double-seal
    with pytest.raises(CaptureError):
        run_trial("2026-preseason", "record_points", 1, now=SEAL_NOW, **world)


def test_seal_immutable_and_bodies_not_seals(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    with pytest.raises(CaptureError):
        seal_trial(trial_dir, repo_root=world["repo_root"], now=SEAL_NOW)

    # a decision body must never deserialize as a seal
    from scripts.seal_2026 import load_seal

    with pytest.raises(CaptureError):
        load_seal(trial_dir / "decision.json")
    seal = load_seal(trial_dir / "seal.sealed.json")
    assert seal["decision_hash"]


# ---------------------------------------------------------------------------
# I29 / I44 — predecessor discipline
# ---------------------------------------------------------------------------


def test_latest_qualified_same_arm_trial_predecessor(tmp_path):
    world, preseason_dir = sealed_trial(tmp_path)
    preseason_seal = json.loads(
        (preseason_dir / "seal.sealed.json").read_text(encoding="utf-8")
    )
    assert preseason_seal["predecessor_decision_hash"] is None
    receipt = json.loads((preseason_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["predecessor_null_reason"]

    preview_dir = run_trial(
        "2026-wk01-preview", "record_points", 1, now=SEAL_NOW, **world
    )
    preview_seal = json.loads(
        (preview_dir / "seal.sealed.json").read_text(encoding="utf-8")
    )
    assert preview_seal["predecessor_decision_hash"] == preseason_seal["decision_hash"]


def test_cross_arm_predecessor_poison_rejected(tmp_path):
    world, _ = sealed_trial(tmp_path)
    with pytest.raises(CaptureError):
        find_predecessor(
            world["seals_root"],
            arm_id="minimal_legal",
            trial_id=1,
            before_cutoff_utc="2026-09-10T00:19:59Z",
            expected_arm="record_points",
            expected_trial=1,
        )


def test_cross_trial_predecessor_poison_rejected(tmp_path):
    world, _ = sealed_trial(tmp_path)
    with pytest.raises(CaptureError):
        find_predecessor(
            world["seals_root"],
            arm_id="record_points",
            trial_id=2,
            before_cutoff_utc="2026-09-10T00:19:59Z",
            expected_arm="record_points",
            expected_trial=1,
        )


def test_null_predecessor_requires_a_reason(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    receipt = json.loads((trial_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["predecessor_decision_hash"] is None
    assert "no earlier qualified seal" in receipt["predecessor_null_reason"]


# ---------------------------------------------------------------------------
# I31 / I42 e2e / I48 — reload cross-checks every hash
# ---------------------------------------------------------------------------


def test_reload_cross_checks_every_hash(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    ok, errors, diagnostics = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert ok, errors


def test_tampered_bundle_decision_claims_receipt_detected(tmp_path):
    for artifact in ("bundle", "decision", "claims", "receipt"):
        world, trial_dir = sealed_trial(tmp_path / artifact)
        if artifact == "bundle":
            target = trial_dir.parent / "bundle.json"
        else:
            target = trial_dir / f"{artifact}.json"
        doc = json.loads(target.read_text(encoding="utf-8"))
        if artifact == "bundle":
            doc["decision_input_payload"]["franchises"][0]["wins_2025"] = 99
        elif artifact == "decision":
            doc["ranking"][0]["rank"] = 12
        elif artifact == "claims":
            doc["claims"][0]["assertion"]["predicted_rank"] = 12
        else:
            doc["output_decision_sha256"] = "0" * 64
        target.write_text(json.dumps(doc), encoding="utf-8")
        ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
        assert not ok, f"tampered {artifact} not detected"


def test_cutoff_receipt_bound_and_cross_verified_everywhere(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
    receipt = json.loads((trial_dir / "receipt.json").read_text(encoding="utf-8"))
    bundle = json.loads((trial_dir.parent / "bundle.json").read_text(encoding="utf-8"))
    cutoff = json.loads(Path(world["cutoff_receipt_path"]).read_text(encoding="utf-8"))
    assert (
        seal["cutoff_receipt_sha256"]
        == receipt["cutoff_receipt_sha256"]
        == bundle["cutoff_receipt_sha256"]
        == cutoff["receipt_sha256"]
    )
    assert seal["cutoff_utc"] == bundle["cutoff_utc"] == cutoff["preseason_cutoff_utc"]

    # a tampered cutoff receipt fails the reload
    Path(world["cutoff_receipt_path"]).write_text(
        json.dumps(dict(cutoff, preseason_cutoff_utc="2026-09-09T00:00:00Z")),
        encoding="utf-8",
    )
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok
    assert any("cutoff" in e for e in errors)


def test_bundle_receipt_seal_bind_policy_locator_and_hash(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
    receipt = json.loads((trial_dir / "receipt.json").read_text(encoding="utf-8"))
    bundle = json.loads((trial_dir.parent / "bundle.json").read_text(encoding="utf-8"))
    policy = json.loads(Path(world["policy_path"]).read_text(encoding="utf-8"))
    assert (
        seal["matrix_sha256"]
        == receipt["matrix_sha256"]
        == bundle["matrix_sha256"]
        == policy["policy_sha256"]
    )
    assert seal["policy_locator"] == receipt["policy_locator"]

    # reload re-reads the policy locator and verifies it still hashes (I48)
    doctored = dict(policy)
    doctored["rows"] = list(policy["rows"])
    doctored["rows"][0] = dict(doctored["rows"][0], freshness=1)
    Path(world["policy_path"]).write_text(json.dumps(doctored), encoding="utf-8")
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok
    assert any("policy" in e or "matrix" in e for e in errors)


# ---------------------------------------------------------------------------
# I32 — every ranking position carries a bound claim
# ---------------------------------------------------------------------------


def test_every_position_carries_a_bound_claim(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    decision = json.loads((trial_dir / "decision.json").read_text(encoding="utf-8"))
    claims_doc = json.loads((trial_dir / "claims.json").read_text(encoding="utf-8"))
    claims = claims_doc["claims"]
    assert len(claims) == len(decision["ranking"]) == 4
    ranked_targets = {r["owner_id"] for r in decision["ranking"]}
    for claim in claims:
        assert claim["claim_type"] == "ordinal_rank"
        assert claim["target"] in ranked_targets
        assert claim["resolution_rule"]["rule"]
        assert claim["resolution_rule"]["resolve_on"]
        assert claim["bundle_sha256"] and claim["source_manifest_sha256"]
        assert claim["outcome"] is None and claim["score"] is None


# ---------------------------------------------------------------------------
# I21 — rederivation regenerates the decision-input payload from sources
# ---------------------------------------------------------------------------


def test_rederive_regenerates_decision_input_payload(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    result = rederive_trial(trial_dir, repo_root=world["repo_root"])
    assert result["ok"], result["errors"]
    assert (
        result["regenerated_decision_input_sha256"]
        == result["bound_decision_input_sha256"]
    )
    assert result["regenerated_bundle_sha256"] == result["bound_bundle_sha256"]


def test_rederive_fails_when_an_envelope_changed(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    rosters_dir = world["public_root"] / "sleeper_rosters"
    envelope_path = next(iter(sorted(rosters_dir.glob("*.json"))))
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    env["payload"]["rosters"][0]["owner_id"] = "poisoned"
    envelope_path.write_text(json.dumps(env), encoding="utf-8")
    result = rederive_trial(trial_dir, repo_root=world["repo_root"])
    assert not result["ok"]
    assert any("sleeper_rosters" in e for e in result["errors"])


def test_later_worktree_edit_does_not_invalidate_an_old_seal(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    # legitimate post-seal edit to the standings file in the fixture repo
    standings_path = world["repo_root"] / "standings.json"
    doc = json.loads(standings_path.read_text(encoding="utf-8"))
    doc["weeks"][1]["standings"][0]["pf"] = 999.9
    standings_path.write_text(json.dumps(doc), encoding="utf-8")

    ok, errors, diagnostics = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert ok, errors  # the seal reads the bound blob, not the worktree
    result = rederive_trial(trial_dir, repo_root=world["repo_root"])
    assert result["ok"], result["errors"]


def test_baseline_source_locator_and_hash_bound(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    bundle = json.loads((trial_dir.parent / "bundle.json").read_text(encoding="utf-8"))
    standings = next(
        e for e in bundle["source_manifest"] if e["source_id"] == "standings_2025"
    )
    assert standings["locator"] == "standings.json"
    assert standings["content_sha256"] and standings["blob_bytes_sha256"]
    seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
    assert seal["source_manifest_sha256"] == bundle["source_manifest_sha256"]


# ---------------------------------------------------------------------------
# I52 / I59 — v1 alone completes; optional modules absent
# ---------------------------------------------------------------------------


def test_v1_alone_completes_accounting_bundle_seal_and_rederive(tmp_path):
    from scripts.capture_2026 import run_tranche

    world = build_world(tmp_path)
    assert not list(Path(tmp_path / "governance").glob("*v2*"))  # NO v2 on disk

    receipt_path, code = run_tranche(
        "A",
        policy_path=world["policy_path"],
        public_root=world["public_root"],
        private_root=world["private_root"],
        receipts_root=tmp_path / "receipts_acct",
        now=SEAL_NOW,
        run_producers=False,
    )
    assert code == 0

    trial_dir = run_trial("2026-preseason", "record_points", 1, now=SEAL_NOW, **world)
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert ok, errors
    result = rederive_trial(trial_dir, repo_root=world["repo_root"])
    assert result["ok"], result["errors"]
    seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
    assert seal["label"] == "prospective"


def test_baseline_path_runs_with_optional_producer_modules_absent(
    tmp_path, monkeypatch
):
    import builtins
    import sys as _sys

    # simulate the optional module being ABSENT from the environment
    monkeypatch.delitem(_sys.modules, "capture_optional_2026", raising=False)
    monkeypatch.delitem(_sys.modules, "scripts.capture_optional_2026", raising=False)
    real_import = builtins.__import__

    def refuse_optional(name, *args, **kwargs):
        if "capture_optional_2026" in name:
            raise ImportError(f"fixture: {name} absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_optional)

    world = build_world(tmp_path)
    trial_dir = run_trial("2026-preseason", "record_points", 1, now=SEAL_NOW, **world)
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert ok, errors


def test_accounting_reports_optional_status_without_invoking_producers(
    tmp_path, monkeypatch
):
    import builtins

    calls = []
    real_import = builtins.__import__

    def spy_import(name, *args, **kwargs):
        if "capture_optional_2026" in name:
            calls.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", spy_import)

    from scripts.tests.test_capture_2026 import accounting

    full_store(tmp_path)
    receipt = accounting(tmp_path)
    statuses = {
        c["source_id"]: c["status"] for g in receipt["groups"] for c in g["components"]
    }
    assert statuses["draft_picks"] in ("due", "not_due")  # reported...
    assert calls == []  # ...without importing the optional module


# ---------------------------------------------------------------------------
# S3 pair — matrix frozen before any run; drift invalidates runs
# ---------------------------------------------------------------------------


def test_matrix_frozen_before_any_run(tmp_path):
    world = build_world(tmp_path)
    # an unfrozen (hash-stripped) policy cannot support a run
    policy = json.loads(Path(world["policy_path"]).read_text(encoding="utf-8"))
    unfrozen = {k: v for k, v in policy.items() if k != "policy_sha256"}
    bad_path = tmp_path / "unfrozen.json"
    bad_path.write_text(json.dumps(unfrozen), encoding="utf-8")
    with pytest.raises(CaptureError):
        run_trial(
            "2026-preseason",
            "record_points",
            1,
            now=SEAL_NOW,
            **{**world, "policy_path": bad_path},
        )


def test_matrix_drift_invalidates_runs(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    policy = json.loads(Path(world["policy_path"]).read_text(encoding="utf-8"))
    policy["rows"][0]["freshness"] = 1  # drift after the run
    Path(world["policy_path"]).write_text(json.dumps(policy), encoding="utf-8")
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok


# ---------------------------------------------------------------------------
# Consolidated-repair discriminating tests (verifier + Codex findings)
# ---------------------------------------------------------------------------


def _build_in_repo_world(tmp_path, monkeypatch):
    """A world whose store, governance, receipts and seals ALL live inside
    the fixture repo root, so every persisted locator is repo-relative."""
    import sys as _sys

    repo = make_repo(tmp_path)
    # shared loads twice (package form for tests, bare form via the scripts
    # bootstrap); rel_to_root reads OUTPUT_ROOT from ITS OWN module globals,
    # so both instances must be patched for envelope locators to relativize
    for mod_name in ("scripts.shared", "shared"):
        mod = _sys.modules.get(mod_name)
        if mod is not None:
            monkeypatch.setattr(mod, "OUTPUT_ROOT", repo)
    full_store(repo)
    policy_path = make_fixture_policy(repo, repo)
    receipt_path = make_cutoff_receipt(repo)
    return {
        "policy_path": policy_path,
        "cutoff_receipt_path": receipt_path,
        "seals_root": repo / "seals",
        "public_root": repo / "public",
        "private_root": repo / "private",
        "repo_root": repo,
    }


def test_seal_verifies_after_repo_relocation(tmp_path, monkeypatch):
    """No machine-absolute path in a repository-owned seal: the same seal
    must verify and rederive after the whole tree moves to another root."""
    import shutil

    world = _build_in_repo_world(tmp_path, monkeypatch)
    repo = world["repo_root"]
    trial_dir = run_trial("2026-preseason", "record_points", 1, now=SEAL_NOW, **world)

    seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
    for field in (
        "cutoff_receipt_locator",
        "policy_locator",
        "bundle_locator",
        "decision_locator",
        "claims_locator",
        "receipt_locator",
    ):
        value = seal[field]
        assert ":" not in value and not value.startswith("/"), (field, value)

    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=repo)
    assert ok, errors

    moved = tmp_path / "moved"
    shutil.copytree(repo, moved)
    moved_trial = moved / "seals" / "2026-preseason" / "record_points" / "trial1"
    ok, errors, _ = verify_seal_dir(moved_trial, repo_root=moved)
    assert ok, errors
    result = rederive_trial(moved_trial, repo_root=moved)
    assert result["ok"], result["errors"]


def test_repo_owned_seal_refuses_machine_absolute_locator(tmp_path):
    """The fail-closed guard: seals inside the repo root refuse to persist
    any machine-absolute locator (here: store/policy live OUTSIDE it)."""
    world = build_world(tmp_path)
    world["seals_root"] = world["repo_root"] / "seals"  # repo-owned seals
    with pytest.raises(CaptureError, match="machine-absolute"):
        run_trial("2026-preseason", "record_points", 1, now=SEAL_NOW, **world)


def test_doctored_claims_in_crash_window_refused_at_seal(tmp_path):
    world = build_world(tmp_path)
    trial_dir = run_trial(
        "2026-preseason",
        "record_points",
        1,
        now=SEAL_NOW,
        stop_before_seal=True,
        **world,
    )
    claims_path = trial_dir / "claims.json"
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    claims["claims"] = claims["claims"][:1]  # 4 positions, 1 claim
    claims_path.write_text(json.dumps(claims), encoding="utf-8")
    with pytest.raises(CaptureError, match="I32|inconsistent"):
        seal_trial(trial_dir, repo_root=world["repo_root"], now=SEAL_NOW)


def test_doctored_receipt_binding_in_crash_window_refused_at_seal(tmp_path):
    world = build_world(tmp_path)
    trial_dir = run_trial(
        "2026-preseason",
        "record_points",
        1,
        now=SEAL_NOW,
        stop_before_seal=True,
        **world,
    )
    receipt_path = trial_dir / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["bundle_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(CaptureError, match="inconsistent"):
        seal_trial(trial_dir, repo_root=world["repo_root"], now=SEAL_NOW)


def test_reload_fails_when_qualification_envelope_missing(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    cutoff = json.loads(Path(world["cutoff_receipt_path"]).read_text(encoding="utf-8"))
    Path(cutoff["kickoff_source_locator"]).unlink()
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok
    assert any("qualification source" in e for e in errors)


def test_corrupt_predecessor_refuses_to_chain(tmp_path):
    from scripts.seal_2026 import find_predecessor

    world, preseason_dir = sealed_trial(tmp_path)
    preview_dir = run_trial(
        "2026-wk01-preview", "record_points", 1, now=SEAL_NOW, **world
    )

    # corrupt the predecessor's decision_hash FIELD without re-hashing
    seal_path = preseason_dir / "seal.sealed.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["decision_hash"] = "0" * 64
    seal_path.write_text(json.dumps(seal), encoding="utf-8")

    with pytest.raises(CaptureError, match="self-verification"):
        find_predecessor(
            world["seals_root"],
            arm_id="record_points",
            trial_id=1,
            before_cutoff_utc="2026-09-10T00:19:59Z",
            expected_arm="record_points",
            expected_trial=1,
        )
    # and the successor's reload flags its now-unverifiable chain
    ok, errors, _ = verify_seal_dir(preview_dir, repo_root=world["repo_root"])
    assert not ok
    assert any("predecessor" in e for e in errors)


def test_copied_trial_dir_fails_identity_check(tmp_path):
    import shutil

    from scripts.seal_2026 import derive_experiment_status

    world, trial_dir = sealed_trial(tmp_path)
    arm_dir = trial_dir.parent

    # copy the valid trial into a different trial slot and a different arm
    shutil.copytree(trial_dir, arm_dir / "trial2")
    foreign_arm = arm_dir.parent / "minimal_legal"
    (foreign_arm).mkdir(parents=True)
    shutil.copytree(trial_dir, foreign_arm / "trial1")

    ok, errors, _ = verify_seal_dir(arm_dir / "trial2", repo_root=world["repo_root"])
    assert not ok and any("trial_id" in e for e in errors)
    ok, errors, _ = verify_seal_dir(
        foreign_arm / "trial1", repo_root=world["repo_root"]
    )
    assert not ok and any("arm_id" in e for e in errors)

    status = derive_experiment_status(
        "2026-preseason",
        seals_root=world["seals_root"],
        repo_root=world["repo_root"],
        now=SEAL_NOW,
    )
    assert status["experiment_status"] == "unavailable"
    assert status["verified_prospective_seals"] == ["record_points/trial1"]


def test_recorded_bundle_self_hash_tamper_detected(tmp_path):
    world, trial_dir = sealed_trial(tmp_path)
    bundle_path = trial_dir.parent / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["bundle_sha256"] = "0" * 64  # ONLY the recorded self-hash field
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok
    assert any("recorded bundle_sha256" in e for e in errors)


def test_worktree_diagnostics_are_non_gating(tmp_path):
    """S6's 'non-gating diagnostics only' made literal: mutating eol_profile
    or worktree observations changes NO gating hash, while mutating a gating
    manifest field still fails the reload."""
    from scripts.bundle_2026 import compute_bundle_sha256

    world, trial_dir = sealed_trial(tmp_path)
    bundle_path = trial_dir.parent / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    standings = next(
        e for e in bundle["source_manifest"] if e["source_id"] == "standings_2025"
    )
    original_hash = bundle["bundle_sha256"]

    standings["eol_profile"] = "crlf" if standings["eol_profile"] != "crlf" else "lf"
    standings["byte_count"] = standings["byte_count"] + 7
    standings["observed_worktree_bytes_sha256"] = "f" * 64
    assert compute_bundle_sha256(bundle) == original_hash  # diagnostics don't gate
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert ok, errors

    standings["content_sha256"] = "0" * 64  # a GATING field still gates
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok


def test_production_seal_requires_green_tranche_a_gate(tmp_path, monkeypatch):
    import scripts.seal_2026 as seal_mod

    calls = {"paths": 0}

    monkeypatch.setattr(
        seal_mod, "run_tranche", lambda tranche: (tmp_path / "r.json", 1)
    )

    def paths_sentinel():
        calls["paths"] += 1
        raise CaptureError("production paths reached")

    monkeypatch.setattr(seal_mod, "_production_paths", paths_sentinel)

    # RED gate -> refuse before any production path is touched
    assert seal_mod.main(["--edition", "2026-preseason"]) == 1
    assert calls["paths"] == 0

    # GREEN gate -> proceeds into the production path (sentinel proves it)
    monkeypatch.setattr(
        seal_mod, "run_tranche", lambda tranche: (tmp_path / "r.json", 0)
    )
    assert seal_mod.main(["--edition", "2026-preseason"]) == 1
    assert calls["paths"] == 1
