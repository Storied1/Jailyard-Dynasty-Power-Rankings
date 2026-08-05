"""K2.3 — migration checks and the state leak census."""

import subprocess

import pytest
import sys
from pathlib import Path

from scripts.migration_census import state_leak_census, unmapped_legacy_fields

PY = sys.executable
REPO = Path(__file__).resolve().parents[2]


def test_every_legacy_field_found_a_fact_type():
    unmapped = unmapped_legacy_fields(2025)
    assert (
        not unmapped
    ), f"{len(unmapped)} legacy fields have no fact type: {unmapped[:8]}"


PRIVATE_PRESENT = (REPO / "private_editions" / "2025-preseason" / "state.json").exists()


def test_league_private_resolution_fails_closed_without_rehydration(tmp_path):
    """Portable proof of the production behavior on a clean checkout: without
    the private root, resolution refuses -- never a silent chat-free state."""
    import scripts.compile_state as cs

    with pytest.raises(
        FileNotFoundError, match="no compiled manifest|private state absent"
    ):
        cs.load_compiled_state(
            "2025-preseason",
            editions_root=REPO / "content" / "editions",
            private_root=tmp_path / "empty",
        )


@pytest.mark.skipif(
    not PRIVATE_PRESENT,
    reason="production private states absent (clean checkout); fail-closed proven above",
)
def test_compiled_states_carry_zero_future_entries():
    """By construction (known_at admission), proven mechanically over every
    knowledge-clock instant in each compiled state. Resolution goes through
    load_compiled_state -- the tracked state.json path is abolished."""
    for e in ("2025-preseason", "2025-wk01-preview", "2025-wk01-recap"):
        r = state_leak_census(e)
        assert r["future_entries"] == 0, f"{e}: {r['detail'][:5]}"
        assert r["is_decision_input"] is True


def test_legacy_packets_still_carry_the_46_and_are_no_longer_inputs():
    """Documents that the leaks were fixed BY CONSTRUCTION, not by patching
    packets: 32 h2h last_meeting + 13 highest_combined + 1 streak = 46."""
    r = state_leak_census("content/weeks", legacy=True)
    assert r["future_entries"] == 46
    assert r["is_decision_input"] is False
    classes = {"h2h": 0, "highest_combined": 0, "longest_losing_streak": 0}
    for d in r["detail"]:
        for c in classes:
            if c in d:
                classes[c] += 1
    assert classes == {"h2h": 32, "highest_combined": 13, "longest_losing_streak": 1}


def test_census_discovers_manifests_not_the_abolished_state_path():
    """The --all discovery keys on state_manifest.json; no compiled state.json
    exists anywhere under the tracked editions tree."""
    tracked_states = list((REPO / "content" / "editions").glob("*/compiled/state.json"))
    assert tracked_states == [], "the tracked state.json path is abolished"
    manifests = list(
        (REPO / "content" / "editions").glob("*/compiled/state_manifest.json")
    )
    assert len(manifests) == 3


def test_planted_unknown_nested_leaf_fails_the_recursive_census(tmp_path):
    """A planted unknown leaf at depth 2, inside an otherwise-mapped section,
    must be reported -- top-level mapping alone would wave it through."""
    import json as j

    from scripts.migration_census import unmapped_legacy_fields

    src = REPO / "content" / "weeks" / "week1_data.json"
    doc = j.loads(src.read_text(encoding="utf-8"))
    doc["matchups"][0]["speculative_nested_leaf"] = 1
    doc["planted_top_section"] = {"x": 1}
    fixture_dir = tmp_path / "weeks"
    fixture_dir.mkdir()
    (fixture_dir / "week1_data.json").write_text(j.dumps(doc), encoding="utf-8")
    unmapped = unmapped_legacy_fields(2025, weeks_dir=fixture_dir)
    assert any("speculative_nested_leaf" in u for u in unmapped), unmapped
    assert any("planted_top_section" in u for u in unmapped)


def test_deep_and_dict_section_plants_fail_with_exact_paths(tmp_path):
    """The two false-green shapes the depth approximation missed: a leaf deep
    inside a list-section subtree, and a direct field inside a dict-shaped
    section. Each plant is asserted to land and must appear as its exact
    normalized path."""
    import json as j

    from scripts.migration_census import unmapped_legacy_fields

    src = REPO / "content" / "weeks" / "week1_data.json"
    doc = j.loads(src.read_text(encoding="utf-8"))
    doc["matchups"][0]["h2h"]["last_meeting"]["planted_unknown_leaf"] = 1
    doc["historical_context"]["planted_unknown_leaf"] = 1
    assert "planted_unknown_leaf" in doc["matchups"][0]["h2h"]["last_meeting"]
    assert "planted_unknown_leaf" in doc["historical_context"], "plants must land"
    fixture_dir = tmp_path / "weeks"
    fixture_dir.mkdir()
    (fixture_dir / "week1_data.json").write_text(j.dumps(doc), encoding="utf-8")
    unmapped = unmapped_legacy_fields(2025, weeks_dir=fixture_dir)
    assert (
        "week1_data.json:matchups[].h2h.last_meeting.planted_unknown_leaf" in unmapped
    )
    assert "week1_data.json:historical_context.planted_unknown_leaf" in unmapped


@pytest.mark.skipif(
    not PRIVATE_PRESENT,
    reason="production private states absent (clean checkout)",
)
def test_census_fails_when_an_authoritative_compiled_artifact_is_mutated():
    """The leak census consumes the COMPLETE verified compilation contract: a
    corrupted source_hashes.json -- with state and manifest still internally
    self-consistent -- must fail the census."""
    sh = (
        REPO
        / "content"
        / "editions"
        / "2025-preseason"
        / "compiled"
        / "source_hashes.json"
    )
    original = sh.read_text(encoding="utf-8")
    mutated = original.replace('"sha256": "sha256:', '"sha256": "sha256:0', 1)
    assert mutated != original, "the plant must land"
    sh.write_text(mutated, encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="compiled contract failed verification"):
            state_leak_census("2025-preseason")
    finally:
        sh.write_text(original, encoding="utf-8")
    assert state_leak_census("2025-preseason")["future_entries"] == 0


def test_unsupported_season_is_rejected_not_vacuously_ok():
    with pytest.raises(ValueError, match="1901"):
        unmapped_legacy_fields(1901)
    r = subprocess.run(
        [PY, "scripts/migration_census.py", "--all", "--season", "1901"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1 and "FAIL" in r.stdout


@pytest.mark.skipif(
    not PRIVATE_PRESENT,
    reason="production private states absent (clean checkout)",
)
def test_cli_gates_and_flag_discipline():
    r = subprocess.run(
        [PY, "scripts/migration_census.py", "--all"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout and "46 future entries" in r.stdout
    bare = subprocess.run(
        [PY, "scripts/migration_census.py"], cwd=REPO, capture_output=True, text=True
    )
    assert bare.returncode == 2, "a bare invocation is a usage error, never a census"
