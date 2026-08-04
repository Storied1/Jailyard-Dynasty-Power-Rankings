"""End-to-end test A + controls (contract section 7, E2E block).

A: envelopes (A's components only) -> tranche-A accounting -> cutoff
qualification -> baseline bundle -> deterministic run -> claims -> seal ->
reload verify -> rederive from the source manifest.

Controls in this module: missing component, post-cutoff envelope, private
leak, cross-arm predecessor, backdating, tamper (envelope, bundle,
decision-input payload, claims, receipt, cutoff receipt, seal), and retry
(a crash between run-close and seal leaves no valid seal; re-running is
safe and does not double-seal).

E2E-B (model arms, 7 runs) is Tranche B and is deliberately absent.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.capture_2026 import CaptureError, capture, run_tranche
from scripts.seal_2026 import rederive_trial, run_trial, seal_trial, verify_seal_dir
from scripts.tests.test_bundle_2026 import (
    ROSTERS_2026,
    full_store,
    make_cutoff_receipt,
    make_fixture_policy,
    make_repo,
    store_envelope,
)

FIXTURE_CLOCK = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def build_world(tmp_path):
    full_store(tmp_path)
    repo = make_repo(tmp_path)
    return {
        "policy_path": make_fixture_policy(tmp_path, repo),
        "cutoff_receipt_path": make_cutoff_receipt(tmp_path),
        "seals_root": tmp_path / "seals",
        "public_root": tmp_path / "public",
        "private_root": tmp_path / "private",
        "repo_root": repo,
    }


def test_e2e_a_complete_fixture_clock_path(tmp_path):
    """The full A path under an isolated fixture clock, through rederivation."""
    world = build_world(tmp_path)

    # 1. tranche-A accounting: the three required components are captured
    receipt_path, code = run_tranche(
        "A",
        policy_path=world["policy_path"],
        public_root=world["public_root"],
        private_root=world["private_root"],
        receipts_root=tmp_path / "acct",
        now=FIXTURE_CLOCK,
        run_producers=False,
    )
    assert code == 0
    accounting = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert accounting["ok"] is True

    # 2-7. bundle -> deterministic run -> claims -> seal, both editions
    preseason = run_trial(
        "2026-preseason", "record_points", 1, now=FIXTURE_CLOCK, **world
    )
    preview = run_trial(
        "2026-wk01-preview", "record_points", 1, now=FIXTURE_CLOCK, **world
    )

    for trial_dir in (preseason, preview):
        seal = json.loads((trial_dir / "seal.sealed.json").read_text(encoding="utf-8"))
        assert seal["label"] == "prospective"
        assert seal["runner_kind"] == "deterministic"

        # 8. reload verify
        ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
        assert ok, errors

        # 9. source-based rederivation
        result = rederive_trial(trial_dir, repo_root=world["repo_root"])
        assert result["ok"], result["errors"]

    # the preview run chains to the preseason decision (I29/I44)
    preview_seal = json.loads(
        (preview / "seal.sealed.json").read_text(encoding="utf-8")
    )
    preseason_seal = json.loads(
        (preseason / "seal.sealed.json").read_text(encoding="utf-8")
    )
    assert preview_seal["predecessor_decision_hash"] == preseason_seal["decision_hash"]

    # deterministic ranking content sanity: owner_a first (2-0 in 2025)
    decision = json.loads((preseason / "decision.json").read_text(encoding="utf-8"))
    assert decision["ranking"][0]["owner_id"] == "owner_a"
    assert [r["rank"] for r in decision["ranking"]] == [1, 2, 3, 4]


def test_e2e_control_missing_component_fails_gate_and_bundle(tmp_path):
    repo = make_repo(tmp_path)
    world = {
        "policy_path": make_fixture_policy(tmp_path, repo),
        "cutoff_receipt_path": make_cutoff_receipt(tmp_path),
        "seals_root": tmp_path / "seals",
        "public_root": tmp_path / "public",
        "private_root": tmp_path / "private",
        "repo_root": repo,
    }
    # only schedules exists (written by make_cutoff_receipt); league+rosters missing
    receipt_path, code = run_tranche(
        "A",
        policy_path=world["policy_path"],
        public_root=world["public_root"],
        private_root=world["private_root"],
        receipts_root=tmp_path / "acct",
        now=FIXTURE_CLOCK,
        run_producers=False,
    )
    assert code == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert {"sleeper_league", "sleeper_rosters"} <= set(receipt["unmet_required"])

    with pytest.raises(CaptureError):
        run_trial("2026-preseason", "record_points", 1, now=FIXTURE_CLOCK, **world)


def test_e2e_control_post_cutoff_envelope_never_selected(tmp_path):
    world = build_world(tmp_path)
    # rosters envelope after the preseason cutoff (2026-09-03T00:20:00Z)
    store_envelope(
        tmp_path,
        "sleeper_rosters",
        {"rosters": [dict(ROSTERS_2026[0], owner_id="late")], "count": 1},
        "2026-09-03T01:00:00Z",
    )
    trial_dir = run_trial(
        "2026-preseason", "record_points", 1, now=FIXTURE_CLOCK, **world
    )
    bundle = json.loads((trial_dir.parent / "bundle.json").read_text(encoding="utf-8"))
    entry = next(
        e for e in bundle["source_manifest"] if e["source_id"] == "sleeper_rosters"
    )
    from scripts.tests.test_bundle_2026 import STORE_CAPTURED_AT

    assert entry["captured_at"] == STORE_CAPTURED_AT
    decision = json.loads((trial_dir / "decision.json").read_text(encoding="utf-8"))
    assert all(r["owner_id"] != "late" for r in decision["ranking"])


def test_e2e_control_private_leak(tmp_path):
    world = build_world(tmp_path)
    secret = "VETO THE TRADE — private league chat 2026"
    capture(
        "chat_export",
        {"messages_requested": ["2026-08"], "messages": [{"text": secret}]},
        request={"endpoint_or_dataset": "manual:whatsapp_export", "params": {}},
        season=2026,
        league_id="1312884727480352768",
        captured_at="2026-08-20T11:00:00Z",
        known_at_basis="fixture private export",
        access_scope="league_private",
        privacy="private",
        public_root=world["public_root"],
        private_root=world["private_root"],
        now=FIXTURE_CLOCK,
    )
    receipt_path, _ = run_tranche(
        "A",
        policy_path=world["policy_path"],
        public_root=world["public_root"],
        private_root=world["private_root"],
        receipts_root=tmp_path / "acct",
        now=FIXTURE_CLOCK,
        run_producers=False,
    )
    trial_dir = run_trial(
        "2026-preseason", "record_points", 1, now=FIXTURE_CLOCK, **world
    )
    # no public artifact anywhere carries the private text
    public_artifacts = [
        receipt_path,
        trial_dir.parent / "bundle.json",
        trial_dir / "decision.json",
        trial_dir / "claims.json",
        trial_dir / "receipt.json",
        trial_dir / "seal.sealed.json",
    ]
    for path in public_artifacts:
        assert secret not in path.read_text(encoding="utf-8"), path
    # and nothing under the public capture root either
    for path in world["public_root"].rglob("*.json"):
        assert secret not in path.read_text(encoding="utf-8"), path


def test_e2e_control_cross_arm_predecessor_rejected(tmp_path):
    from scripts.seal_2026 import find_predecessor

    world = build_world(tmp_path)
    run_trial("2026-preseason", "record_points", 1, now=FIXTURE_CLOCK, **world)
    with pytest.raises(CaptureError):
        find_predecessor(
            world["seals_root"],
            arm_id="full_rich",
            trial_id=1,
            before_cutoff_utc="2026-09-10T00:19:59Z",
            expected_arm="record_points",
            expected_trial=1,
        )


def test_e2e_control_backdating_detected(tmp_path):
    world = build_world(tmp_path)
    trial_dir = run_trial(
        "2026-preseason",
        "record_points",
        1,
        now=datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc),  # post-cutoff
        **world,
    )
    seal_path = trial_dir / "seal.sealed.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    assert seal["label"] == "retrospective"
    seal["label"] = "prospective"
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok


def test_e2e_control_tamper_battery(tmp_path):
    """Envelope, bundle, decision-input payload, claims, receipt, cutoff
    receipt, seal — each mutation must fail reload or rederivation."""
    world = build_world(tmp_path)
    trial_dir = run_trial(
        "2026-preseason", "record_points", 1, now=FIXTURE_CLOCK, **world
    )

    def fresh(name):
        w = build_world(tmp_path / name)
        d = run_trial("2026-preseason", "record_points", 1, now=FIXTURE_CLOCK, **w)
        return w, d

    # 1. envelope
    w, d = fresh("t_envelope")
    env_path = next(iter((w["public_root"] / "sleeper_rosters").glob("*.json")))
    doc = json.loads(env_path.read_text(encoding="utf-8"))
    doc["payload"]["rosters"][0]["owner_id"] = "tampered"
    env_path.write_text(json.dumps(doc), encoding="utf-8")
    assert not rederive_trial(d, repo_root=w["repo_root"])["ok"]

    # 2. bundle + 3. decision-input payload (inside the bundle)
    w, d = fresh("t_bundle")
    bundle_path = d.parent / "bundle.json"
    doc = json.loads(bundle_path.read_text(encoding="utf-8"))
    doc["decision_input_payload"]["franchises"][0]["wins_2025"] = 99
    bundle_path.write_text(json.dumps(doc), encoding="utf-8")
    ok, _, _ = verify_seal_dir(d, repo_root=w["repo_root"])
    assert not ok

    # 4. claims
    w, d = fresh("t_claims")
    claims_path = d / "claims.json"
    doc = json.loads(claims_path.read_text(encoding="utf-8"))
    doc["claims"][0]["assertion"]["predicted_rank"] = 12
    claims_path.write_text(json.dumps(doc), encoding="utf-8")
    ok, _, _ = verify_seal_dir(d, repo_root=w["repo_root"])
    assert not ok

    # 5. receipt
    w, d = fresh("t_receipt")
    receipt_path = d / "receipt.json"
    doc = json.loads(receipt_path.read_text(encoding="utf-8"))
    doc["started_at"] = "2026-08-01T00:00:00Z"
    receipt_path.write_text(json.dumps(doc), encoding="utf-8")
    ok, _, _ = verify_seal_dir(d, repo_root=w["repo_root"])
    assert not ok

    # 6. cutoff receipt
    w, d = fresh("t_cutoff")
    cutoff_path = Path(w["cutoff_receipt_path"])
    doc = json.loads(cutoff_path.read_text(encoding="utf-8"))
    doc["preseason_cutoff_utc"] = "2026-09-09T00:00:00Z"
    cutoff_path.write_text(json.dumps(doc), encoding="utf-8")
    ok, _, _ = verify_seal_dir(d, repo_root=w["repo_root"])
    assert not ok

    # 7. seal
    w, d = fresh("t_seal")
    seal_path = d / "seal.sealed.json"
    doc = json.loads(seal_path.read_text(encoding="utf-8"))
    doc["bundle_sha256"] = "0" * 64
    seal_path.write_text(json.dumps(doc), encoding="utf-8")
    ok, _, _ = verify_seal_dir(d, repo_root=w["repo_root"])
    assert not ok

    # the untouched original still verifies (controls did not cross-poison)
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert ok, errors


def test_e2e_control_retry_crash_between_close_and_seal(tmp_path):
    world = build_world(tmp_path)
    # simulate the crash: run the trial WITHOUT sealing
    trial_dir = run_trial(
        "2026-preseason",
        "record_points",
        1,
        now=FIXTURE_CLOCK,
        stop_before_seal=True,
        **world,
    )
    assert (trial_dir / "receipt.json").exists()
    assert not (trial_dir / "seal.sealed.json").exists()
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert not ok  # no valid seal exists

    # re-running is safe: it completes the partial trial exactly once
    seal_trial(trial_dir, repo_root=world["repo_root"], now=FIXTURE_CLOCK)
    ok, errors, _ = verify_seal_dir(trial_dir, repo_root=world["repo_root"])
    assert ok, errors

    # and a further re-run does not double-seal
    with pytest.raises(CaptureError):
        seal_trial(trial_dir, repo_root=world["repo_root"], now=FIXTURE_CLOCK)
