"""K3.4/K3.6 shared fixtures -- re-exported through scripts/tests/conftest.py.

`chat_message` is registered league_private, so the fixtures request a
league_private state: a public state would silently drop it and
test_no_chat_bundle_omits_chat would pass for the wrong reason.
"""

import pytest

from scripts.temporal_state import state_at
from scripts.tests.test_temporal_state import F

FAMILIES = (
    "franchise_identity",
    "draft_pick",
    "roster_membership",
    "historical_matchup",
    "chat_message",
    "nfl_game",
    "matchup_result",
    "schedule_pairing",
)


def _state(families):
    facts = [
        F(
            fact_id=t,
            source_record_id=t,
            fact_type=t,
            access_scope="league_private" if t == "chat_message" else "public",
        )
        for t in families
    ]
    return state_at(2025, "2025-12-01T00:00:00Z", "league_private", facts=facts)


@pytest.fixture
def fake_state():
    return _state(FAMILIES)


@pytest.fixture
def fake_state_without_history():
    return _state([t for t in FAMILIES if t != "historical_matchup"])


@pytest.fixture
def preseason_state():
    """No matchup_result -- structurally absent before week 1, not missing.
    Carries real historical_matchup payloads so standings() can order them."""
    from scripts.tests.test_reducers import M

    hist = [
        M(1, 2024, 1, "2024-09-08T23:00:00Z", "A", "B", 120.0, 100.0),
        M(2, 2024, 2, "2024-09-15T23:00:00Z", "A", "B", 90.0, 130.0),
        M(3, 2024, 3, "2024-09-22T23:00:00Z", "B", "A", 140.0, 110.0),
    ]
    hist = [
        F(
            **{
                **{
                    k: getattr(h, k)
                    for k in (
                        "source_record_id",
                        "entity_ref",
                        "source_ref",
                        "effective_at",
                        "known_at",
                        "access_scope",
                        "known_at_basis",
                        "captured_at",
                        "privacy",
                        "normalizer_version",
                    )
                },
                "fact_id": h.fact_id,
                "fact_type": "historical_matchup",
                "payload": h.payload,
            }
        )
        for h in hist
    ]
    others = [
        F(
            fact_id=t,
            source_record_id=t,
            fact_type=t,
            access_scope="league_private" if t == "chat_message" else "public",
        )
        for t in FAMILIES
        if t not in {"matchup_result", "historical_matchup"}
    ]
    return state_at(2025, "2025-09-03T23:59:59Z", "league_private", facts=hist + others)


def synthetic_chain_states():
    """Three per-edition LeagueStates with EVERY family sourced -- what the K3.5
    driver tests inject. The real 2025 store has zero roster_membership and
    schedule_pairing facts (open dependency 3), so bundle_for on the real
    compiled states raises ArmUnavailable for every model arm; the driver's
    mechanics are proven on synthetic states, and the real-store degradation is
    the CONTRAST lane's finding, not a test failure."""
    from scripts.tests.test_reducers import M

    identities = [
        ("1", "GauchoTrain", "General Ken-obi", "510013812276232192"),
        ("2", "bchodos", "Kittler on the Roof", "510013812276232193"),
        ("3", "kharlow", "Burden of Etienne-y Woody", "510013812276232194"),
    ]
    facts = []
    for rid, display, team, owner in identities:
        facts.append(
            F(
                fact_id=f"fi{rid}",
                source_record_id=f"franchise:2025:{rid}",
                fact_type="franchise_identity",
                entity_ref={"type": "franchise", "id": rid},
                payload={
                    "roster_id": rid,
                    "season": 2025,
                    "display_name": display,
                    "team_name": team,
                    "owner_id": owner,
                },
            )
        )
        facts.append(
            F(
                fact_id=f"dp{rid}",
                source_record_id=f"draft:2025:{rid}",
                fact_type="draft_pick",
                entity_ref={"type": "franchise", "id": rid},
                payload={
                    "roster_id": rid,
                    "round": 1,
                    "pick_no": int(rid),
                    "season": 2025,
                },
            )
        )
        facts.append(
            F(
                fact_id=f"rm{rid}",
                source_record_id=f"roster:2025:{rid}",
                fact_type="roster_membership",
                entity_ref={"type": "franchise", "id": rid},
                payload={"roster_id": rid, "players": [f"p{rid}a", f"p{rid}b"]},
            )
        )
    facts.append(
        F(
            fact_id="chat1",
            source_record_id="chat:1",
            fact_type="chat_message",
            access_scope="league_private",
            privacy="private",
            payload={
                "text": "General Ken-obi is toast this year",
                "sender": "GauchoTrain",
            },
        )
    )
    facts.append(
        F(
            fact_id="nfl1",
            source_record_id="nfl:2025_01_ARI_NO",
            fact_type="nfl_game",
            entity_ref={"type": "nfl_game", "id": "2025_01_ARI_NO"},
            payload={
                "game_id": "2025_01_ARI_NO",
                "home_team": "NO",
                "away_team": "ARI",
            },
        )
    )
    facts.append(
        F(
            fact_id="sp1",
            source_record_id="pair:2025:1",
            fact_type="schedule_pairing",
            entity_ref={"type": "matchup", "id": "1"},
            payload={"season": 2025, "week": 1, "home": "1", "away": "2"},
        )
    )
    hist = [
        M(1, 2024, 1, "2024-09-08T23:00:00Z", "1", "2", 120.0, 100.0),
        M(2, 2024, 2, "2024-09-15T23:00:00Z", "1", "3", 90.0, 130.0),
        M(3, 2024, 3, "2024-09-22T23:00:00Z", "2", "3", 140.0, 110.0),
    ]
    facts += [
        F(
            **{
                **{
                    k: getattr(h, k)
                    for k in (
                        "source_record_id",
                        "entity_ref",
                        "source_ref",
                        "effective_at",
                        "known_at",
                        "access_scope",
                        "known_at_basis",
                        "captured_at",
                        "privacy",
                        "normalizer_version",
                    )
                },
                "fact_id": h.fact_id,
                "fact_type": "historical_matchup",
                "payload": h.payload,
            }
        )
        for h in hist
    ]
    # Week-1 2025 results: known AFTER the preview cutoff, admitted only at recap.
    facts += [
        M(1, 2025, 1, "2025-09-08T23:00:00Z", "1", "2", 131.4, 101.2),
        M(2, 2025, 1, "2025-09-08T23:10:00Z", "3", "1", 99.0, 120.0),
    ]
    cutoffs = {
        "2025-preseason": "2025-09-03T23:59:59Z",
        "2025-wk01-preview": "2025-09-05T00:19:59Z",
        "2025-wk01-recap": "2025-09-09T06:59:59Z",
    }
    return {
        eid: state_at(2025, cutoff, "league_private", facts=facts)
        for eid, cutoff in cutoffs.items()
    }


@pytest.fixture
def chain_states():
    return synthetic_chain_states()


@pytest.fixture
def claim_factory():
    """Minimal scoreable claims. Every field the scorer reads, nothing it doesn't."""
    from scripts.claims_ledger import make_claim

    def make(
        claim_type="ordinal_rank",
        assertion=1,
        outcome=None,
        bound=None,
        resolution_failed=False,
        arm_id="full_rich",
        trial_id=1,
        edition_id="2025-wk01-recap",
    ):
        # edition_id is load-bearing: the K3.6 completeness gate keys cells on
        # (arm_id, edition_id, trial_id) -- a factory omitting it collapses the
        # grid to 5 cells against 39 expected and --report refuses forever.
        return make_claim(
            target="T",
            claim_type=claim_type,
            horizon="rest_of_season",
            assertion=assertion,
            confidence=0.6,
            decisive_evidence=[],
            contrary_evidence="",
            cutoff_utc="2025-09-09T06:59:59Z",
            state_hash="sha256:" + "a" * 64,
            arm_id=arm_id,
            trial_id=trial_id,
            decision_run_id="run-1",
            edition_id=edition_id,
            bound=bound,
            outcome=outcome,
            resolution_failed=resolution_failed,
            resolution_rule={
                "rule": "final_regular_season_rank",
                "source": "standings",
                "resolve_on": "2026-01-06T00:00:00Z",
            },
        )

    return make


@pytest.fixture
def seeded_seals(tmp_path):
    """A full_rich preseason seal only — no_chat deliberately has none, so
    test_comparator_absent_without_a_qualified_predecessor is a real negative.
    Sealed via K1.5's test helper so the closed-receipt precondition holds."""
    from scripts.tests.test_decision_history import mkseal

    mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "2025-preseason")
    return tmp_path
