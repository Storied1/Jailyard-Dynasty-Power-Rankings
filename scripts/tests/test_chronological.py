"""K3.5 — chronological per-arm chains: closed lineage, guard-before-write,
masking on the execution path, crash-safe seal-as-commit-marker, replacement
trials, dry run, blind packet."""

import json

import pytest

from scripts.decision_history import CrossArmContamination
from scripts.eval_arms import _InjectedCrash, run_arm_chain
from scripts.tests.conftest_eval import synthetic_chain_states

EDITIONS = ["2025-preseason", "2025-wk01-preview", "2025-wk01-recap"]

# One synthetic state set per module: every family sourced, so the driver's
# mechanics are under test rather than the real store's known degradation.
STATES = synthetic_chain_states()


def _stub_claim():
    """One valid RESOLVABLE claim content dict: resolve_on == the recap cutoff,
    target a roster_id present in the synthetic standings -- so recap grading
    has something due and resolvable."""
    return {
        "target": "1",
        "claim_type": "ordinal_rank",
        "horizon": "next_week",
        "assertion": 1,
        "confidence": 0.6,
        "decisive_evidence": ["standings"],
        "contrary_evidence": "",
        "resolution_rule": {
            "rule": "final_regular_season_rank",
            "source": "standings",
            "resolve_on": "2025-09-09T06:59:59Z",
        },
    }


def _generic_stub(bundle, predecessor):
    teams = sorted(
        {
            f["payload"]["roster_id"]
            for f in bundle["facts"].get("franchise_identity", [])
        }
    ) or [r["team"] for r in bundle["standings"]]
    ranking = {"entries": [{"team": t, "rank": i + 1} for i, t in enumerate(teams)]}
    claims = [
        dict(_stub_claim(), target=t, assertion=i + 1) for i, t in enumerate(teams)
    ]
    return ranking, claims


STUB_RUNNERS = {
    a: _generic_stub
    for a in ("record_points", "minimal_legal", "full_rich", "no_chat", "no_history")
}


def load_runs_for_test(root):
    from scripts.decision_run import load_runs

    return load_runs(root)


def test_chain_seals_in_order(tmp_path):
    seals = run_arm_chain(
        "full_rich", 1, EDITIONS, root=tmp_path, _runners=STUB_RUNNERS, _states=STATES
    )
    assert [s.edition_id for s in seals] == EDITIONS
    assert seals[0].cutoff_utc < seals[1].cutoff_utc < seals[2].cutoff_utc


def test_preview_consumes_its_own_preseason_seal(tmp_path):
    seals = run_arm_chain(
        "full_rich", 1, EDITIONS, root=tmp_path, _runners=STUB_RUNNERS, _states=STATES
    )
    assert all(s.arm_id == "full_rich" and s.trial_id == 1 for s in seals)
    assert seals[1].predecessor_decision_hash == seals[0].decision_hash
    assert seals[2].predecessor_decision_hash == seals[1].decision_hash


def test_arm_cannot_consume_another_arms_seal(tmp_path):
    run_arm_chain(
        "no_chat", 1, EDITIONS[:1], root=tmp_path, _runners=STUB_RUNNERS, _states=STATES
    )
    run_arm_chain(
        "full_rich",
        1,
        EDITIONS[:1],
        root=tmp_path,
        _runners=STUB_RUNNERS,
        _states=STATES,
    )
    with pytest.raises(CrossArmContamination):
        run_arm_chain(
            "full_rich",
            1,
            EDITIONS[1:],
            root=tmp_path,
            _runners=STUB_RUNNERS,
            _states=STATES,
            _force_predecessor_arm="no_chat",
        )


def test_recap_grades_this_arms_prior_claims(tmp_path):
    run_arm_chain(
        "full_rich", 1, EDITIONS, root=tmp_path, _runners=STUB_RUNNERS, _states=STATES
    )
    from scripts.claims_ledger import load_claims

    graded = [c for c in load_claims(root=tmp_path) if c.outcome is not None]
    assert graded and all(c.arm_id == "full_rich" for c in graded)


def test_a_rerun_is_refused_before_any_write_or_spend(tmp_path):
    """The guard fires FIRST: the refused re-run leaves the ledger, receipts and
    seal directory byte-identical, and never invokes a runner. Round two placed
    the mutating writes ahead of the guard, so the normal response to a partial
    failure -- re-run -- double-appended claims and overwrote receipts before
    being refused (and for model arms, paid for a call it then threw away)."""
    from scripts.claims_ledger import load_claims

    calls = []

    def counting_stub(bundle, predecessor):
        calls.append(1)
        return {"entries": [{"team": "1", "rank": 1}]}, [_stub_claim()]

    run_arm_chain(
        "full_rich",
        1,
        EDITIONS[:1],
        root=tmp_path,
        _runners={"full_rich": counting_stub},
        _states=STATES,
    )
    n_calls, n_claims = len(calls), len(load_claims(root=tmp_path))
    files = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    with pytest.raises(FileExistsError, match=r"\.seal\.json"):
        run_arm_chain(
            "full_rich",
            1,
            EDITIONS[:1],
            root=tmp_path,
            _runners={"full_rich": counting_stub},
            _states=STATES,
        )
    assert len(calls) == n_calls, "the refused re-run must not invoke the runner"
    assert len(load_claims(root=tmp_path)) == n_claims, "no claim double-append"
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == files


def test_mutation_disabled_predecessor_check_accepts_poison(tmp_path, monkeypatch):
    """Rule 7's REAL mutation control (deferred from K1.7, where every consumer
    imports verify_predecessor by name and a module-attr patch is inert). The
    plant lands on the symbol run_arm_chain actually reads; with the check
    disabled, a cross-arm predecessor is accepted and the poisoned chain
    completes -- proving the check is the only thing standing."""
    import scripts.eval_arms as ea

    run_arm_chain(
        "no_chat", 1, EDITIONS[:1], root=tmp_path, _runners=STUB_RUNNERS, _states=STATES
    )
    passthrough = lambda sealed, arm_id, trial_id: sealed  # noqa: E731
    monkeypatch.setattr(ea, "verify_predecessor", passthrough)
    assert ea.verify_predecessor is passthrough, "the plant must land"
    seals = run_arm_chain(
        "full_rich",
        1,
        EDITIONS[:2],
        root=tmp_path,
        _runners=STUB_RUNNERS,
        _states=STATES,
        _force_predecessor_arm="no_chat",
    )
    assert seals, "control: without the check the poisoned chain completes"


def test_root_isolation_leaves_the_repository_untouched(tmp_path):
    """Control: the tests above must not be writing into content/decisions/.
    Anchored to the REPO ROOT, not the CWD -- a CWD-dependent [] == [] pass is
    vacuous whenever pytest runs from anywhere else."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    decisions = repo / "content" / "decisions"
    before = (
        sorted(p.name for p in decisions.glob("**/*")) if decisions.exists() else []
    )
    run_arm_chain(
        "no_history",
        1,
        EDITIONS[:1],
        root=tmp_path,
        _runners=STUB_RUNNERS,
        _states=STATES,
    )
    after = sorted(p.name for p in decisions.glob("**/*")) if decisions.exists() else []
    assert before == after


def test_masking_bypass_plant_is_caught(tmp_path, monkeypatch):
    """A planted REAL identity in the runner's input must fail. The capturing
    stub sees exactly what a provider would; with mask_bundle disabled the real
    name leaks -- proving masking is the only thing standing, and the plant
    landed."""
    import scripts.eval_arms as ea

    seen = {}

    def capture_stub(bundle, predecessor):
        seen["bundle"] = json.dumps(bundle)
        return {"entries": [{"team": "1", "rank": 1}]}, [_stub_claim()]

    run_arm_chain(
        "full_rich",
        1,
        EDITIONS[:1],
        root=tmp_path,
        _runners={"full_rich": capture_stub},
        _states=STATES,
    )
    assert "General Ken-obi" not in seen["bundle"], "masked path leaks no real name"
    identity = lambda bundle, salt: bundle  # noqa: E731
    monkeypatch.setattr(ea, "mask_bundle", identity)
    assert ea.mask_bundle is identity, "the plant must land"
    run_arm_chain(
        "full_rich",
        2,
        EDITIONS[:1],
        root=tmp_path,
        _runners={"full_rich": capture_stub},
        _states=STATES,
    )
    assert (
        "General Ken-obi" in seen["bundle"]
    ), "control: with masking disabled the real identity reaches the runner"


def test_crash_boundaries_leave_no_visible_cell(tmp_path):
    """Inject a crash after each write (body1, body2, receipt, claims) and
    assert: no seal exists, the cell is invisible to decision_history_at and
    load_runs, orphans are enumerated, cleanup + resume under a new trial id
    succeeds, and a SEALED cell can never be cleaned."""
    from scripts.decision_history import decision_history_at
    from scripts.eval_arms import clean_incomplete_cell, resume_chain

    for boundary in (
        "after_ranking_body",
        "after_claims_body",
        "after_receipt",
        "after_claims_write",
    ):
        root = tmp_path / boundary
        with pytest.raises(_InjectedCrash):
            run_arm_chain(
                "full_rich",
                1,
                EDITIONS[:1],
                root=root,
                _runners=STUB_RUNNERS,
                _states=STATES,
                _crash_at=boundary,
            )
        assert (
            decision_history_at(2025, "2099-01-01T00:00:00Z", "full_rich", 1, root=root)
            == []
        )
        runs, orphans = load_runs_for_test(root)
        assert not runs, "a sealless cell is never evidence"
        if boundary == "after_receipt":
            assert orphans, "the crashed receipt is enumerated, not lost"
        clean_incomplete_cell(root, 2025, "full_rich", 1, EDITIONS[0])
        seals = resume_chain("full_rich", root, _runners=STUB_RUNNERS, _states=STATES)
        assert seals and seals[0].trial_id == 2, "resume allocates a NEW trial id"
        with pytest.raises(ValueError):
            clean_incomplete_cell(root, 2025, "full_rich", 2, EDITIONS[0])


def test_replacement_trials_census_1_3_4_complete_2_abandoned(tmp_path):
    """Complete chains {1,3,4} with 2 abandoned mid-chain is a VALID model-arm
    grid; a missing edition cell inside trial 4 is not."""
    from scripts.eval_arms import complete_chains

    for trial in (1, 3, 4):
        run_arm_chain(
            "full_rich",
            trial,
            EDITIONS,
            root=tmp_path,
            _runners=STUB_RUNNERS,
            _states=STATES,
        )
    run_arm_chain(
        "full_rich",
        2,
        EDITIONS[:1],
        root=tmp_path,
        _runners=STUB_RUNNERS,
        _states=STATES,
    )  # abandoned partial
    assert complete_chains("full_rich", tmp_path) == [1, 3, 4]
    partial = tmp_path / "partial"
    for trial in (1, 3):
        run_arm_chain(
            "full_rich",
            trial,
            EDITIONS,
            root=partial,
            _runners=STUB_RUNNERS,
            _states=STATES,
        )
    run_arm_chain(
        "full_rich",
        4,
        EDITIONS[:2],
        root=partial,
        _runners=STUB_RUNNERS,
        _states=STATES,
    )  # missing recap cell
    assert complete_chains("full_rich", partial) == [
        1,
        3,
    ], "an incomplete chain never counts as complete"


def test_dry_run_seals_all_39_cells(tmp_path):
    """The mandatory zero-spend rehearsal: 5 arms x (1|3 trials) x 3 editions =
    39 sealed cells on stub runners, proving the loop and the completeness gate
    agree before any paid call."""
    from scripts.eval_arms import dry_run_all

    n = dry_run_all(tmp_path, _states=STATES)
    assert n == 39
    from scripts.eval_arms import complete_chains

    assert complete_chains("record_points", tmp_path) == [1]
    assert complete_chains("full_rich", tmp_path) == [1, 2, 3]


def test_blind_packet_is_opaque_and_fully_mapped(tmp_path):
    """No packet file names or contains any of the five arm ids; the label map
    holds exactly one entry per packet file and lives OUTSIDE the packet dir."""
    from scripts.eval_arms import ARMS, dry_run_all, write_blind_packet

    root = tmp_path / "decisions"
    dry_run_all(root, _states=STATES)
    out = tmp_path / "packet"
    label_map = tmp_path / "label_map.json"
    n = write_blind_packet(out, label_map_path=label_map, root=root)
    files = sorted(out.iterdir())
    assert n == len(files) == 39
    for p in files:
        body = p.read_text(encoding="utf-8")
        for arm in ARMS:
            assert arm not in p.name and arm not in body
    mapping = json.loads(label_map.read_text(encoding="utf-8"))
    assert sorted(mapping) == sorted(p.name.rsplit(".", 1)[0] for p in files)
