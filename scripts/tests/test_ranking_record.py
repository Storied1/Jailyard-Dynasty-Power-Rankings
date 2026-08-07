"""The week-1 recap ranking record: twelve positions, every reference resolving."""

import json
from pathlib import Path

import pytest

from scripts.compile_state import load_compiled_state
from scripts.eval_arms import rehydrate_state
from scripts.ranking_record import (
    UnresolvedReference,
    _assert_resolvable,
    build_record,
    render,
)

REPO = Path(__file__).resolve().parents[2]
EDITION = "2025-wk01-recap"


@pytest.fixture(scope="module")
def record():
    return build_record(EDITION, week=1)


def test_twelve_contiguous_positions(record):
    assert [p["rank"] for p in record["positions"]] == list(range(1, 13))
    assert len({p["roster_id"] for p in record["positions"]}) == 12


def test_every_position_is_named(record):
    """The repair's payoff, asserted: before it, franchise_identity admitted ZERO
    facts at this cutoff and a ranking could only have named roster ids."""
    unnamed = [p["roster_id"] for p in record["positions"] if not p["team_name"]]
    assert unnamed == []


def test_every_position_carries_resolving_evidence(record):
    state = rehydrate_state(load_compiled_state(EDITION))
    available = {f.fact_id for f in state.admitted}
    for p in record["positions"]:
        ev = p["evidence"]
        assert ev["identity"]["fact_id"] in available
        assert ev["week_result"]["fact_id"] in available
        assert ev["roster"]["fact_ids"] and set(ev["roster"]["fact_ids"]) <= available
        assert ev["draft"]["fact_ids"] and set(ev["draft"]["fact_ids"]) <= available
        assert set(ev["prior_season"]["fact_ids"]) <= available
    assert record["citation_count"] > 0


def test_unresolvable_citation_is_refused():
    """PLANTED: a citation the state cannot resolve. The record must refuse to
    exist rather than ship a dangling reference."""
    state = rehydrate_state(load_compiled_state(EDITION))
    bogus = {
        "edition_id": EDITION,
        "positions": [{"evidence": {"fact_id": "fact:nope"}}],
    }
    with pytest.raises(UnresolvedReference):
        _assert_resolvable(bogus, state)


def test_ordering_matches_an_independent_derivation(record):
    """Re-derived from raw season_combined -- a different path to the same answer,
    not a re-read of the fact store."""
    raw = json.loads(
        (REPO / "data/2025/season_combined.json").read_text(encoding="utf-8")
    )
    wk1 = next(w for w in raw["weeks"] if w["week"] == 1)
    rows = []
    for m in wk1["matchups"]:
        for a, b in ((m["team1"], m["team2"]), (m["team2"], m["team1"])):
            rows.append((str(a["roster_id"]), a["points"], b["points"]))
    rows.sort(key=lambda r: (-(r[1] > r[2]), -r[1], int(r[0])))
    assert [p["roster_id"] for p in record["positions"]] == [r[0] for r in rows]
    for p, r in zip(record["positions"], rows):
        assert p["points_for"] == pytest.approx(r[1])


def test_one_week_means_six_and_six(record):
    wins = sum(
        p["evidence"]["week_result"]["outcome"] == "W" for p in record["positions"]
    )
    assert wins == 6
    assert all(p["record"] in ("1-0", "0-1") for p in record["positions"])


def test_the_record_declares_what_its_ordering_ignores(record):
    """An ordering that hides its own thinness invites being read as a judgment."""
    assert record["ordering_rule"]
    assert len(record["what_this_ordering_does_not_encode"]) >= 3
    # Evidence the state HOLDS but the ordering does not consult, counted openly.
    unused = record["evidence_available_but_unused_by_the_ordering"]
    assert unused["chat_message"] > 0
    assert unused["roster_membership"] > 0


def test_prior_season_is_labelled_all_games_not_final_standings(record):
    """standings() folds playoff games too. Calling that a 'finish' would be an
    aggregate that merely looks plausible."""
    for p in record["positions"]:
        prior = p["evidence"]["prior_season"]
        assert "all admitted games" in prior["basis"]
        assert prior["games"] >= 14


def test_render_is_plain_and_prose_free(record):
    text = render(record)
    assert text.count("\n") > 12
    for position in record["positions"]:
        assert (position["team_name"] or "").strip() in text
