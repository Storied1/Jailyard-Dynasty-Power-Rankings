"""K3.2 — decision-run receipts: kind-specific field sets, closed-before-persisted,
retrospective labeling, runner configuration."""

import pytest

from scripts.decision_run import RUNNER_KINDS, close_run, open_run

# labeling is REQUIRED for every 2025 edition (design §6): open_run refuses its
# absence or any other value, so the label is on the receipt as well as the seal.
COMMON = dict(
    edition_id="2025-wk01-recap",
    arm_id="full_rich",
    trial_id=1,
    state_hash="sha256:" + "a" * 64,
    bundle_hash="sha256:" + "b" * 64,
    predecessor_decision_hash="sha256:" + "c" * 64,
    started_at="2026-08-02T00:00:00Z",
    labeling="retrospective_backtest",
)


def test_both_runner_kinds_exist():
    assert RUNNER_KINDS == {"deterministic", "model"}


def test_deterministic_run_needs_code_and_config_hashes():
    with pytest.raises(ValueError):
        open_run(runner_kind="deterministic", **COMMON)
    r = open_run(
        runner_kind="deterministic",
        code_hash="sha256:" + "d" * 64,
        config_hash="sha256:" + "e" * 64,
        input_hashes={"x": "sha256:" + "f" * 64},
        **COMMON,
    )
    assert r.runner_kind == "deterministic"


def test_deterministic_run_must_not_carry_a_provider():
    with pytest.raises(ValueError):
        open_run(
            runner_kind="deterministic",
            code_hash="sha256:" + "d" * 64,
            config_hash="sha256:" + "e" * 64,
            input_hashes={},
            provider="anthropic",
            **COMMON,
        )


def test_model_run_needs_provider_model_and_policy():
    with pytest.raises(ValueError):
        open_run(runner_kind="model", provider="anthropic", **COMMON)
    r = open_run(
        runner_kind="model",
        provider="anthropic",
        model="claude-opus-5",
        model_version="2026-05",
        reasoning="high",
        tools_policy="none",
        browsing="disabled",
        budget=100000,
        retries=0,
        sampling_policy="temp=0",
        prompt_hash="sha256:" + "1" * 64,
        rule_hashes={"voice": "sha256:" + "2" * 64},
        **COMMON,
    )
    assert r.browsing == "disabled"


def test_close_binds_the_output_hash():
    r = open_run(
        runner_kind="deterministic",
        code_hash="sha256:" + "d" * 64,
        config_hash="sha256:" + "e" * 64,
        input_hashes={},
        **COMMON,
    )
    done = close_run(
        r, output_decision_hash="sha256:" + "9" * 64, ended_at="2026-08-02T00:05:00Z"
    )
    assert done.output_decision_hash.startswith("sha256:") and done.ended_at


def test_predecessor_hash_is_mandatory_outside_preseason():
    with pytest.raises(ValueError):
        open_run(
            runner_kind="deterministic",
            code_hash="sha256:" + "d" * 64,
            config_hash="sha256:" + "e" * 64,
            input_hashes={},
            **dict(COMMON, predecessor_decision_hash=None),
        )


def test_labeling_is_required_for_a_2025_edition():
    """Design §6: the retrospective label is on the receipt, not just the seal.
    Absence AND any other value are both refused."""
    for bad in (dict(COMMON, labeling=None), dict(COMMON, labeling="prospective")):
        with pytest.raises(ValueError, match="retrospective_backtest"):
            open_run(
                runner_kind="deterministic",
                code_hash="sha256:" + "d" * 64,
                config_hash="sha256:" + "e" * 64,
                input_hashes={},
                **bad,
            )


def test_persist_refuses_an_open_run_and_round_trips_a_closed_one(tmp_path):
    """The receipt on disk must attest a COMPLETED run. Persisting the open
    record was the round-two ordering defect: load_runs could never confirm any
    run finished, and a crash left a receipt for a run that produced nothing.
    In a seal-less root the receipt is an ORPHAN -- enumerated, never evidence."""
    from scripts.decision_run import load_runs, persist_run

    r = open_run(
        runner_kind="deterministic",
        code_hash="sha256:" + "d" * 64,
        config_hash="sha256:" + "e" * 64,
        input_hashes={},
        **COMMON,
    )
    with pytest.raises(ValueError):
        persist_run(r, tmp_path)  # open: refused
    done = close_run(
        r, output_decision_hash="sha256:" + "9" * 64, ended_at="2026-08-02T00:05:00Z"
    )
    persist_run(done, tmp_path)
    runs, orphans = load_runs(tmp_path)
    assert (
        runs == [] and len(orphans) == 1
    ), "no seal in this root: the receipt is an orphan"
    assert orphans[0].ended_at and orphans[0].output_decision_hash


def test_runner_config_loads_and_every_path_resolves():
    """An earlier revision DISPLAYED the runner-config JSON and never created
    it; every model run would have died hashing a nonexistent prompt."""
    from pathlib import Path

    from scripts.decision_run import runner_config

    cfg = runner_config("full_rich")
    assert cfg["provider"] == "anthropic" and cfg["browsing"] == "disabled"
    assert cfg["tools_policy"] == "none" and cfg["retries"] == 0
    repo = Path(__file__).resolve().parents[2]
    paths = [cfg["prompt_path"], *cfg["rule_paths"].values()]
    for rel in paths:
        assert (repo / rel).is_file(), f"runner_config names an unreadable path: {rel}"
