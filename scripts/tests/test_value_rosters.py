"""The valuation desk's acceptance tests.

The desk had three confirmed defects in its scratch prototypes, each found by
adversarial verification. The load-bearing half of this suite pins those
defects so they cannot be reintroduced:

  BUG 1  season_aggregates.weeks_played counts roster weeks, not appearances
         (Burrow 2023: 17 "played" weeks, 8 of them 0.0). Rates must come
         from weekly[] rows where fantasy_points > 0.
  BUG 2  a minimum-games threshold deleted contrary seasons (McCaffrey scored
         as the league's best player off 2023 because his 4-game 2024 fell
         under the cut). Every season the career covers is scored.
  BUG 3  rookie value anchored to the rookie's own position's replacement
         made a pick-17 rookie QB outrank Mahomes. Rookie value is expressed
         directly in points-over-replacement, position-neutral.

Plus the desk's contract: two axes (present strength, asset value), tiers
rather than a false 1-12, an uncertainty band per team, no 2025 leakage, and
deterministic output.
"""

from pathlib import Path

import pytest

from scripts.value_rosters import (
    age_at_cutoff,
    age_multiplier,
    assign_tiers,
    best_lineup,
    build_desk,
    player_seasons,
    player_value,
    replacement_levels,
    rookie_over_replacement,
)

REPO = Path(__file__).resolve().parents[2]
BUNDLE = REPO / "private_bundles" / "preseason-2025" / "preseason_evidence.json"
PLAYERS = REPO / "data" / "players.json"

_needs_private = pytest.mark.skipif(
    not (BUNDLE.exists() and PLAYERS.exists()),
    reason="gitignored private bundle / players.json absent (local only)",
)


def _weekly(rows):
    """rows: list of (season, week, points) -> arc-style weekly list."""
    return [
        {"season": s, "week": w, "fantasy_points": p, "started": False}
        for s, w, p in rows
    ]


# ---- BUG 1: appearances come from weekly[], not weeks_played --------------------


def test_zero_point_roster_weeks_are_not_appearances():
    # 17 roster weeks, only 9 with points on the board (a Burrow 2023 shape).
    rows = [(2023, w, 15.2) for w in range(1, 10)]
    rows += [(2023, w, 0.0) for w in range(10, 18)]
    seasons = player_seasons(_weekly(rows))
    total, games = seasons[2023]
    assert games == 9, "appearances must count scoring weeks, not roster weeks"
    assert total == pytest.approx(15.2 * 9)


# ---- BUG 2: every season the career covers is scored ----------------------------


def test_short_contrary_season_is_not_deleted():
    # A McCaffrey shape: elite 2023, four bad games in 2024. The 2024 season
    # must drag the blend down, never silently vanish under a threshold.
    rows = [(2023, w, 22.3) for w in range(1, 17)]
    rows += [(2024, w, 10.0) for w in range(1, 5)]
    v = player_value(_weekly(rows))
    assert v["rate"] is not None
    assert v["rate"] < 22.3, "the 4-game 2024 must count against the rate"
    # with weights 2024=0.70 / 2023=0.30 the blend sits nearer the bad season
    assert v["rate"] == pytest.approx(0.70 * 10.0 + 0.30 * 22.3)


def test_availability_charges_missed_weeks():
    # Same player: rate is per appearance, avail is per season week, so a
    # 4-appearance season must show a large rate-vs-avail gap.
    rows = [(2024, w, 20.0) for w in range(1, 5)]
    v = player_value(_weekly(rows))
    assert v["rate"] == pytest.approx(20.0)
    assert v["avail"] == pytest.approx(80.0 / 17)


# ---- no 2025 leakage -------------------------------------------------------------


def test_post_cutoff_seasons_are_invisible():
    rows = [(2024, w, 10.0) for w in range(1, 18)]
    poisoned = rows + [(2025, w, 99.9) for w in range(1, 18)]
    assert player_value(_weekly(rows)) == player_value(_weekly(poisoned))


# ---- BUG 3: rookie value is position-neutral over-replacement --------------------


def test_rookie_value_ignores_position():
    assert rookie_over_replacement(1) > rookie_over_replacement(12)
    # decays to zero, never negative
    assert rookie_over_replacement(72) == 0.0
    # capped by the peak: no rookie estimate may exceed the configured peak
    assert rookie_over_replacement(1, rookie_peak=6.0) <= 6.0


def test_rookie_cannot_outrank_a_proven_elite():
    # pick-17 rookie (any position) vs a 22-ppg proven QB whose replacement
    # level is 15: the veteran's 7.0 over-replacement must win.
    rookie = rookie_over_replacement(17)
    veteran_over = 22.0 - 15.0
    assert rookie < veteran_over


# ---- replacement levels ----------------------------------------------------------


def test_replacement_is_the_nth_best():
    pool = {"QB": sorted([20.0 - i for i in range(20)], reverse=True)}
    # 12 QB started, no flex allowance: replacement is the 12th best = 9.0
    repl = replacement_levels(pool, started={"QB": 12}, flex_extra={})
    assert repl["QB"] == pytest.approx(9.0)


# ---- lineup solver ----------------------------------------------------------------


def test_flex_takes_the_best_remaining_skill_player():
    pool = [
        ("QB", "q1", 5.0),
        ("RB", "r1", 9.0),
        ("RB", "r2", 8.0),
        ("RB", "r3", 7.5),  # should land in FLEX
        ("WR", "w1", 6.0),
        ("WR", "w2", 5.0),
        ("WR", "w3", 4.0),
        ("TE", "t1", 3.0),
    ]
    starters_total, depth, chosen = best_lineup(pool)
    slots = [c[0] for c in chosen]
    assert slots.count("RB") == 2 and "FLEX" in slots
    flex = next(c for c in chosen if c[0] == "FLEX")
    assert flex[2] == "r3"
    assert starters_total == pytest.approx(5 + 9 + 8 + 7.5 + 6 + 5 + 4 + 3)
    assert depth == 0.0  # nothing left on the bench


def test_streamed_slots_do_not_differentiate():
    # K/DEF/DL/LB/DB never enter the pool: a kicker with a huge number
    # contributes nothing to the lineup value.
    pool = [("QB", "q1", 5.0), ("K", "k1", 99.0)]
    starters_total, _, chosen = best_lineup(pool)
    assert starters_total == pytest.approx(5.0)
    assert all(c[0] != "K" for c in chosen)


# ---- the asset axis ---------------------------------------------------------------


def test_age_multiplier_declines_with_age():
    assert age_multiplier("RB", 24.0) > age_multiplier("RB", 30.0)
    assert age_multiplier("QB", 30.0) > age_multiplier("RB", 30.0)
    # bounded on both ends
    for pos in ("QB", "RB", "WR", "TE"):
        for age in (21.0, 27.0, 34.0, 41.0):
            assert 0.0 < age_multiplier(pos, age) <= 1.25


def test_age_is_computed_at_the_cutoff_not_today():
    # birth_date is the only cutoff-safe field; the players.json `age` field
    # is stamped at fetch time and may be a 2026 age.
    assert age_at_cutoff("2000-09-03") == pytest.approx(25.0, abs=0.01)
    assert age_at_cutoff("2000-09-04") < 25.0
    assert age_at_cutoff(None) is None


# ---- tiers and uncertainty --------------------------------------------------------


def test_clearly_separated_scores_split_into_tiers():
    scores = {"A": 60.0, "B": 58.0, "C": 30.0, "D": 29.0}
    bands = {k: (1, 2) for k in ("A", "B")} | {k: (3, 4) for k in ("C", "D")}
    tiers = assign_tiers(scores, bands)
    assert tiers["A"] == tiers["B"] == 1
    assert tiers["C"] == tiers["D"] == 2


def test_overlapping_bands_share_a_tier():
    scores = {"A": 50.0, "B": 49.0, "C": 48.0}
    bands = {"A": (1, 2), "B": (1, 3), "C": (2, 3)}
    tiers = assign_tiers(scores, bands)
    assert len(set(tiers.values())) == 1


# ---- integration: the real desk ---------------------------------------------------


@_needs_private
def test_desk_end_to_end_shape_and_determinism():
    desk1 = build_desk(runs=40, seed=11)
    desk2 = build_desk(runs=40, seed=11)
    assert desk1 == desk2, "the desk must be deterministic"

    teams = desk1["teams"]
    assert len(teams) == 12
    for axis in ("present", "asset"):
        ranks = sorted(t[axis]["rank"] for t in teams)
        assert ranks == list(range(1, 13))
        for t in teams:
            lo, hi = t[axis]["rank_band"]
            assert 1 <= lo <= t[axis]["rank"] <= hi <= 12
            assert t[axis]["tier"] >= 1
    # tiers are contiguous in rank order on each axis
    for axis in ("present", "asset"):
        by_rank = sorted(teams, key=lambda t: t[axis]["rank"])
        tiers = [t[axis]["tier"] for t in by_rank]
        assert tiers == sorted(tiers), "tiers must be monotone in rank"
    # the record of what the desk does not encode must be present
    assert any("pick" in s.lower() for s in desk1["not_encoded"])
    # tiers must carry real structure: an all-tier-1 table means the tiering
    # input was too loose (one high-variance team chain-bridging the field)
    for axis in ("present", "asset"):
        assert len({t[axis]["tier"] for t in teams}) >= 3


@_needs_private
def test_desk_matches_the_known_consensus_top_and_ben():
    """Four independent methods agreed: Zach/Blake/Brent are the top three on
    present strength and Ben is not top-2. If the productionised desk breaks
    that, the desk is wrong, not the finding."""
    desk = build_desk(runs=40, seed=11)
    by_owner = {t["owner"]: t for t in desk["teams"]}
    top3 = {t["owner"] for t in desk["teams"] if t["present"]["rank"] <= 3}
    assert top3 == {"Zach", "Blake", "Brent"}
    assert by_owner["Ben"]["present"]["rank"] >= 4
