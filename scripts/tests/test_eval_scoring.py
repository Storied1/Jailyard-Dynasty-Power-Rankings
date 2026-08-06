"""K3.6 — precommitted scoring rules, fixed aggregation, completeness and
comparable-scores gates."""

import pytest

from scripts.eval_scoring import (
    AGGREGATION_ORDER,
    MIN_TRIALS_NONDETERMINISTIC,
    aggregate,
    score_claim,
)
from scripts.tests.conftest_eval import synthetic_chain_states


def _sealed_grid_root(tmp_path):
    """A scratch decisions tree whose 39 cells are sealed via K3.5's stubs, so
    the census passes and ONLY the gate under test fires."""
    from scripts.eval_arms import dry_run_all

    root = tmp_path / "decisions"
    dry_run_all(root, _states=synthetic_chain_states())
    return root


def test_aggregation_order_is_fixed():
    assert AGGREGATION_ORDER == ("claim", "team", "edition", "trial", "arm")


def test_three_trials_required_for_nondeterministic_runners():
    assert MIN_TRIALS_NONDETERMINISTIC == 3


def test_ordinal_rank_uses_spearman_footrule(claim_factory):
    c = claim_factory(claim_type="ordinal_rank", assertion=2, outcome=5)
    assert score_claim(c) == 3


def test_binary_probability_uses_brier(claim_factory):
    c = claim_factory(claim_type="binary_probability", assertion=0.8, outcome=1)
    assert abs(score_claim(c) - 0.04) < 1e-9


def test_bounded_quantity_normalizes_by_its_bound(claim_factory):
    c = claim_factory(
        claim_type="bounded_quantity", assertion=120.0, outcome=100.0, bound=200.0
    )
    assert abs(score_claim(c) - 0.1) < 1e-9


def test_unresolved_claims_are_excluded_and_counted(claim_factory):
    claims = [claim_factory(outcome=None), claim_factory(assertion=2, outcome=2)]
    r = aggregate(claims)
    assert r["unresolved"] == 1 and r["scored"] == 1


def test_more_unresolved_claims_do_not_improve_an_arm(claim_factory):
    few = aggregate([claim_factory(assertion=2, outcome=5)])
    many = aggregate(
        [claim_factory(assertion=2, outcome=5)]
        + [claim_factory(outcome=None) for _ in range(9)]
    )
    assert few["mean_score"] == many["mean_score"]


def test_missing_outcome_source_is_unresolvable_not_dropped(claim_factory):
    c = claim_factory(outcome=None, resolution_failed=True)
    r = aggregate([c])
    assert r["unresolvable"] == 1


def test_nondeterministic_arm_reports_median_and_range(claim_factory):
    trials = [aggregate([claim_factory(assertion=2, outcome=o)]) for o in (3, 5, 9)]
    from scripts.eval_scoring import combine_trials

    combined = combine_trials(trials, runner_kind="model")
    assert combined["median"] == 3 and combined["range"] == (1, 7)


def test_single_trial_model_arm_is_rejected(claim_factory):
    from scripts.eval_scoring import combine_trials

    with pytest.raises(ValueError):
        combine_trials(
            [aggregate([claim_factory(assertion=2, outcome=3)])], runner_kind="model"
        )


def test_report_refuses_a_missing_cell(claim_factory, tmp_path, monkeypatch, capsys):
    """The completeness gate is TESTED, not asserted: a claim set missing exactly
    one (arm, edition, trial) cell makes main() return 1. This is the guard
    against reporting a smaller experiment as a complete one, and it depends on
    edition_id being populated -- which is why both claim helpers carry it."""
    from scripts.claims_ledger import EDITION_IDS, save_claims
    from scripts.eval_arms import ARMS
    from scripts.eval_scoring import main as scoring_main

    full_grid = [
        claim_factory(arm_id=a, trial_id=t, edition_id=e, assertion=2, outcome=3)
        for a in ARMS
        for e in EDITION_IDS
        for t in range(1, (1 if ARMS[a]["runner_kind"] == "deterministic" else 3) + 1)
    ]
    save_claims(full_grid[:-1], root=tmp_path)  # exactly one cell missing
    # CLAIMS_DEFAULT_ROOT is a module global eval_scoring's main() READS AT CALL
    # TIME -- the patch below is live, not the inert-default-argument class this
    # plan documents for SEALS_ROOT and EDITIONS_ROOT.
    monkeypatch.setattr("scripts.eval_scoring.CLAIMS_DEFAULT_ROOT", tmp_path)
    monkeypatch.setattr(
        "scripts.eval_scoring.DECISIONS_DEFAULT_ROOT", _sealed_grid_root(tmp_path)
    )
    monkeypatch.setattr("sys.argv", ["eval_scoring.py", "--report"])
    assert scoring_main() == 1
    assert "incomplete experiment" in capsys.readouterr().err


def test_all_unresolved_grid_cannot_produce_a_lift_verdict(
    claim_factory, tmp_path, monkeypatch, capsys
):
    """A full 39-cell grid where NOTHING resolved is a null measurement: the
    comparable-scores gate must exit 1 BEFORE any by_arm output is written."""
    from scripts.claims_ledger import EDITION_IDS, save_claims
    from scripts.eval_arms import ARMS
    from scripts.eval_scoring import main as scoring_main

    grid = [
        claim_factory(arm_id=a, trial_id=t, edition_id=e, outcome=None)
        for a in ARMS
        for e in EDITION_IDS
        for t in range(1, (1 if ARMS[a]["runner_kind"] == "deterministic" else 3) + 1)
    ]
    save_claims(grid, root=tmp_path)
    monkeypatch.setattr("scripts.eval_scoring.CLAIMS_DEFAULT_ROOT", tmp_path)
    monkeypatch.setattr(
        "scripts.eval_scoring.DECISIONS_DEFAULT_ROOT", _sealed_grid_root(tmp_path)
    )  # seals exist; scores don't
    # The grading pass must not read the real private fact store from a unit
    # test: inject the synthetic recap state, where target "T" resolves to
    # nothing -- resolution_failed, still zero scored claims.
    recap = synthetic_chain_states()["2025-wk01-recap"]
    monkeypatch.setattr("scripts.eval_scoring._grading_state", lambda resolve_on: recap)
    monkeypatch.setattr("sys.argv", ["eval_scoring.py", "--report"])
    assert scoring_main() == 1
    err = capsys.readouterr()
    assert "zero resolved-and-scored claims" in err.err
    assert "by_arm" not in err.out and err.out.strip() == ""
