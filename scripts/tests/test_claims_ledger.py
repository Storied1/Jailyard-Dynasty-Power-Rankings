"""K3.1 — scoreable claims with pre-fixed resolution rules; append-only ledger."""

from scripts.claims_ledger import CLAIM_TYPES, HORIZONS, make_claim, validate_claim


def base(**over):
    # edition_id is REQUIRED: K3.6's completeness gate keys cells on
    # (arm_id, edition_id, trial_id); a claim without it collapses the grid.
    b = dict(
        target="General Ken-obi",
        claim_type="ordinal_rank",
        horizon="rest_of_season",
        assertion=2,
        confidence=0.6,
        decisive_evidence=["/records/highest_score"],
        contrary_evidence="thin schedule so far",
        cutoff_utc="2025-09-09T06:59:59Z",
        state_hash="sha256:" + "a" * 64,
        arm_id="full_rich",
        trial_id=1,
        decision_run_id="run-1",
        edition_id="2025-wk01-recap",
        resolution_rule={
            "rule": "final_regular_season_rank",
            "source": "standings",
            "resolve_on": "2026-01-06T00:00:00Z",
        },
    )
    b.update(over)
    return b


def test_claim_types_and_horizons_are_the_declared_sets():
    assert CLAIM_TYPES == {"ordinal_rank", "binary_probability", "bounded_quantity"}
    assert HORIZONS == {"next_week", "rest_of_season", "championship", "dynasty"}


def test_resolution_rule_is_required_and_complete():
    for missing in ("rule", "source", "resolve_on"):
        r = dict(base()["resolution_rule"])
        r.pop(missing)
        assert validate_claim(make_claim(**base(resolution_rule=r)))


def test_outcome_and_score_start_empty():
    c = make_claim(**base())
    assert c.outcome is None and c.score is None


def test_bounded_quantity_requires_a_bound():
    assert validate_claim(
        make_claim(**base(claim_type="bounded_quantity", assertion=120.0))
    )
    assert not validate_claim(
        make_claim(**base(claim_type="bounded_quantity", assertion=120.0, bound=200.0))
    )


def test_probability_must_be_within_zero_and_one():
    assert validate_claim(
        make_claim(**base(claim_type="binary_probability", assertion=1.4))
    )


def test_claim_binds_its_arm_trial_edition_and_run():
    c = make_claim(**base())
    assert c.arm_id == "full_rich" and c.trial_id == 1 and c.decision_run_id == "run-1"
    assert c.edition_id == "2025-wk01-recap"


def test_ledger_round_trips_through_persistence(tmp_path):
    """save_claims/load_claims are implemented HERE, not just named: K3.5's
    driver and K3.6's report both depend on them, and an earlier revision
    declared them in Interfaces with no creating step."""
    from scripts.claims_ledger import load_claims, save_claims

    cs = [make_claim(**base()), make_claim(**base(target="Boat"))]
    save_claims(cs, root=tmp_path)
    got = load_claims(root=tmp_path)
    # Set equality: the on-disk sort key is (arm_id, edition_id, trial_id,
    # claim_id), and both claims share the first three -- target order is not
    # part of the contract.
    assert {c.target for c in got} == {"General Ken-obi", "Boat"}
    assert not list(
        tmp_path.rglob("*.seal.json")
    ), "the ledger never enters the decisions tree"


def test_resolution_event_collapse_is_latest_wins(tmp_path):
    """A re-run appends a NEW event and changes the current view exactly once --
    never a double-count. current=False exposes the raw immutable event log."""
    from scripts.claims_ledger import ResolutionEvent, load_claims, save_claims

    c = make_claim(**base())
    save_claims([c], root=tmp_path)
    e1 = ResolutionEvent(
        claim_id=c.claim_id,
        outcome=5,
        score=3.0,
        resolved_at="2026-01-06T00:00:00Z",
        resolution_run_id="res-1",
    )
    e2 = ResolutionEvent(
        claim_id=c.claim_id,
        outcome=4,
        score=2.0,
        resolved_at="2026-01-07T00:00:00Z",
        resolution_run_id="res-2",
    )
    save_claims([e1], root=tmp_path, season=2025)
    save_claims([e2], root=tmp_path, season=2025)
    (got,) = load_claims(root=tmp_path)
    assert got.outcome == 4 and got.score == 2.0, "latest resolved_at wins, once"
    events = load_claims(root=tmp_path, current=False)
    assert [e.resolution_run_id for e in events] == ["res-1", "res-2"]
