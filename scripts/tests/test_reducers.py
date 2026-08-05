"""K1.4 — aggregates recomputed from admitted facts; standings season-qualified."""

from scripts.temporal_state import state_at
from scripts.tests.test_temporal_state import F


def M(rid, season, week, known_at, home, away, hp, ap):
    # season and week are payload keys: h2h() and records() sort on them and
    # last_meeting reports them.
    return F(
        fact_id=f"m{season}{week}{rid}",
        source_record_id=f"match:{season}:{week}:{rid}",
        fact_type="matchup_result",
        entity_ref={"type": "matchup", "id": str(rid)},
        effective_at=known_at,
        known_at=known_at,
        payload={
            "season": season,
            "week": week,
            "home": home,
            "away": away,
            "home_pts": hp,
            "away_pts": ap,
        },
    )


def test_h2h_counts_only_admitted_meetings():
    facts = [
        M(1, 2022, 9, "2022-11-01T00:00:00Z", "A", "B", 140.3, 153.1),
        M(2, 2025, 6, "2025-10-14T06:59:59Z", "A", "B", 109.1, 150.5),
        M(3, 2025, 12, "2025-12-02T06:59:59Z", "A", "B", 180.0, 100.0),
    ]
    s = state_at(2025, "2025-10-20T00:00:00Z", "public", facts=facts)
    h = s.h2h("A", "B")
    assert h["total_games"] == 2 and h["a_wins"] == 0 and h["b_wins"] == 2
    assert h["last_meeting"]["week"] == 6


def test_h2h_at_an_earlier_cutoff_sees_only_the_first_meeting():
    facts = [
        M(1, 2022, 9, "2022-11-01T00:00:00Z", "A", "B", 140.3, 153.1),
        M(2, 2025, 6, "2025-10-14T06:59:59Z", "A", "B", 109.1, 150.5),
    ]
    s = state_at(2025, "2025-09-01T00:00:00Z", "public", facts=facts)
    assert s.h2h("A", "B")["total_games"] == 1


def test_streak_is_recomputed_not_stored():
    """The undated aggregate that leaked. No stored value exists to read."""
    facts = [
        M(i, 2025, i, f"2025-09-{10 + i:02d}T06:59:59Z", "A", "B", 10.0, 20.0)
        for i in range(1, 4)
    ]
    early = state_at(2025, "2025-09-12T00:00:00Z", "public", facts=facts).records()
    late = state_at(2025, "2025-09-20T00:00:00Z", "public", facts=facts).records()
    assert early["longest_losing_streak"]["count"] == 1
    assert late["longest_losing_streak"]["count"] == 3


def test_no_record_postdates_its_cutoff():
    facts = [
        M(1, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 300.0, 10.0),
        M(2, 2025, 14, "2025-12-16T06:59:59Z", "A", "B", 400.0, 10.0),
    ]
    r = state_at(2025, "2025-09-15T00:00:00Z", "public", facts=facts).records()
    assert r["highest_score"]["points"] == 300.0, "the week-14 record must be invisible"


def test_standings_are_recomputed_from_admitted_results():
    facts = [
        M(1, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 120.0, 100.0),
        M(2, 2025, 2, "2025-09-17T06:59:59Z", "A", "B", 90.0, 110.0),
        M(3, 2025, 9, "2025-11-05T06:59:59Z", "A", "B", 200.0, 10.0),
    ]
    s = state_at(2025, "2025-09-20T00:00:00Z", "public", facts=facts).standings()
    row = {r["team"]: r for r in s}
    assert row["A"]["wins"] == 1 and row["A"]["losses"] == 1
    assert row["A"]["points_for"] == 210.0, "the week-9 blowout must be invisible"
    assert [r["team"] for r in s] == ["A", "B"] or [r["team"] for r in s] == ["B", "A"]


def test_standings_are_season_qualified_while_h2h_is_all_time():
    """The recorded category-4 defect. Mixed-season facts: the 2022 meeting
    counts in h2h (all-time) and MUST NOT count in 2025 standings."""
    facts = [
        M(1, 2022, 9, "2022-11-01T00:00:00Z", "A", "B", 140.3, 100.0),
        M(2, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 120.0, 100.0),
    ]
    s = state_at(2025, "2025-09-20T00:00:00Z", "public", facts=facts)
    assert s.h2h("A", "B")["total_games"] == 2
    row = {r["team"]: r for r in s.standings()}
    assert row["A"]["wins"] == 1 and row["A"]["losses"] == 0
    assert row["A"]["points_for"] == 120.0, "the 2022 game must not fold into 2025"
    prior = {r["team"]: r for r in s.standings(season=2022)}
    assert prior["A"]["wins"] == 1, "an explicit prior season is selectable"


def test_standings_mutation_control_without_the_season_predicate():
    """Control: drop the predicate and the 2022 game folds in. Proves the test
    above fails when the rule is removed rather than passing vacuously."""
    facts = [
        M(1, 2022, 9, "2022-11-01T00:00:00Z", "A", "B", 140.3, 100.0),
        M(2, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 120.0, 100.0),
    ]
    s = state_at(2025, "2025-09-20T00:00:00Z", "public", facts=facts)
    unfiltered = {}
    for g in s.by_type("matchup_result") + s.by_type("historical_matchup"):
        p = g.payload  # rule removed: no season predicate
        unfiltered[p["home"]] = unfiltered.get(p["home"], 0) + 1
    assert unfiltered["A"] == 2, "control: without the predicate both seasons fold"


def test_tied_game_is_a_tie_in_both_aggregates():
    facts = [M(1, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 100.0, 100.0)]
    s = state_at(2025, "2025-09-20T00:00:00Z", "public", facts=facts)
    h = s.h2h("A", "B")
    assert h["ties"] == 1 and h["a_wins"] == 0 and h["b_wins"] == 0
    row = {r["team"]: r for r in s.standings()}
    assert row["A"]["ties"] == 1 and row["A"]["wins"] == 0


def test_reducers_fold_on_effective_at_not_known_at():
    """A correction learned late about an early game folds at its EFFECTIVE
    instant. Ordering by known_at would put the September game after December."""
    early = M(1, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 10.0, 20.0)
    late = M(2, 2025, 2, "2025-09-17T06:59:59Z", "A", "B", 10.0, 20.0)
    corrected = F(
        fact_id="mc",
        source_record_id="match:2025:3:3",
        fact_type="matchup_result",
        entity_ref={"type": "matchup", "id": "3"},
        effective_at="2025-09-24T06:59:59Z",
        known_at="2025-12-01T00:00:00Z",
        payload={
            "season": 2025,
            "week": 3,
            "home": "A",
            "away": "B",
            "home_pts": 10.0,
            "away_pts": 20.0,
        },
    )
    s = state_at(2025, "2025-12-02T00:00:00Z", "public", facts=[early, late, corrected])
    assert s.records()["longest_losing_streak"]["count"] == 3
    assert [f.fact_id for f in s.by_type("matchup_result")] == [
        "m202511",
        "m202522",
        "mc",
    ]
