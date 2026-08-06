"""K3.4 — five arms, ablation by subtraction, per-arm inertia comparators."""

import pytest

from scripts.compile_state import EditionDescriptor
from scripts.eval_arms import ARMS, ArmUnavailable, bundle_for, inertia_comparator

PRESEASON = EditionDescriptor(
    "2025-preseason",
    2025,
    "preseason",
    "2025-09-03T23:59:59Z",
    "league_private",
    None,
    (),
)
PREVIEW = EditionDescriptor(
    "2025-wk01-preview",
    2025,
    "preview",
    "2025-09-05T00:19:59Z",
    "league_private",
    None,
    ("2025-preseason",),
)


def test_exactly_five_arms():
    assert set(ARMS) == {
        "record_points",
        "minimal_legal",
        "full_rich",
        "no_chat",
        "no_history",
    }


def test_no_prior_unchanged_arm_exists():
    assert "prior_unchanged" not in ARMS and "inertia" not in ARMS


def test_record_points_is_the_only_deterministic_arm():
    det = {a for a, spec in ARMS.items() if spec["runner_kind"] == "deterministic"}
    assert det == {"record_points"}


def test_record_points_uses_prior_season_standings_at_preseason():
    assert ARMS["record_points"]["preseason_basis"] == "prior_season_final_standings"


def test_no_chat_bundle_omits_chat(fake_state):
    b = bundle_for("no_chat", fake_state, "recap")
    assert "chat_message" not in b["families"] and "historical_matchup" in b["families"]


def test_no_history_ablates_every_pre_2025_type(fake_state):
    """The expected set is bound INDEPENDENTLY of ARMS -- comparing the ablation
    list against the constant that defines it is a tautology that cannot fail.
    In the nine-type bridge, historical_matchup is the ONLY type whose facts
    predate 2025 (verified against fact_types.json); if a second pre-2025 type
    is ever registered, THIS literal must grow with it and the tautological
    form would have silently passed."""
    independently_derived = {"historical_matchup"}
    b = bundle_for("no_history", fake_state, "recap")
    assert not (
        independently_derived & set(b["families"])
    ), "the design says 'full minus pre-2025 facts'"
    assert "chat_message" in b["families"]
    from scripts.eval_arms import PRE_2025_TYPES

    assert (
        PRE_2025_TYPES == independently_derived
    ), "ARMS' constant must match the independently-bound surface"


def test_minimal_bundle_is_a_strict_subset_of_full(fake_state):
    assert set(bundle_for("minimal_legal", fake_state, "recap")["families"]) < set(
        bundle_for("full_rich", fake_state, "recap")["families"]
    )


def test_structurally_absent_results_do_not_make_an_arm_unavailable(preseason_state):
    """A preseason state contains no 2025 results BY CONSTRUCTION. Treating that as
    missing evidence aborted the run before contrast could be judged."""
    b = bundle_for("full_rich", preseason_state, "preseason")
    assert "matchup_result" not in b["families"]


def test_record_points_has_an_executable_preseason_basis(preseason_state):
    """Its only family was matchup_result, which cannot exist at preseason -- so the
    prior-season-standings basis was unreachable metadata."""
    from scripts.eval_arms import required_families

    assert required_families("record_points", "preseason") == ["historical_matchup"]
    b = bundle_for("record_points", preseason_state, "preseason")
    assert b["ranking_basis"] == "prior_season_final_standings"
    assert b["standings"], "the basis must produce an actual ordering"


def test_no_inertia_comparator_at_preseason(seeded_seals):
    assert inertia_comparator("full_rich", 1, PRESEASON, root=seeded_seals) is None


def test_comparator_uses_the_same_arms_predecessor(seeded_seals):
    c = inertia_comparator("full_rich", 1, PREVIEW, root=seeded_seals)
    assert c is not None and c.arm_id == "full_rich" and c.trial_id == 1
    assert c.edition_id == "2025-preseason"


def test_comparator_absent_without_a_qualified_predecessor(seeded_seals):
    """no_chat has no seal in the same root: absent, never borrowed from full_rich."""
    assert inertia_comparator("no_chat", 1, PREVIEW, root=seeded_seals) is None


def test_unavailable_family_makes_its_arm_unavailable(fake_state_without_history):
    """No history to ablate = the ablation measures nothing. Distinct from the
    structurally-absent case above, which must NOT raise."""
    with pytest.raises(ArmUnavailable):
        bundle_for("no_history", fake_state_without_history, "recap")
