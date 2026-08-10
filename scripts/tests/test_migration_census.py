"""The state leak census: zero post-cutoff facts in every decision input."""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.migration_census import state_leak_census, unmapped_packet_fields

PY = sys.executable
REPO = Path(__file__).resolve().parents[2]


def test_every_packet_field_found_a_fact_type():
    unmapped = unmapped_packet_fields(2025)
    assert (
        not unmapped
    ), f"{len(unmapped)} packet fields have no fact type: {unmapped[:8]}"


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


def test_writer_packets_are_active_inputs_with_zero_future_entries():
    """The production contract: every active writer packet is cutoff-safe.
    The planted-leak tests below prove each detector fires."""
    r = state_leak_census("content/weeks", packets=True)
    assert r["future_entries"] == 0, r["detail"][:5]
    assert r["is_decision_input"] is True


def _packet_fixture(tmp_path, mutate):
    """Copy the real week1 packet, apply a plant, return the fixture dir."""
    import json as j

    src = REPO / "content" / "weeks" / "week1_data.json"
    doc = j.loads(src.read_text(encoding="utf-8"))
    mutate(doc)
    fixture_dir = tmp_path / "weeks"
    fixture_dir.mkdir()
    (fixture_dir / "week1_data.json").write_text(j.dumps(doc), encoding="utf-8")
    return fixture_dir


def test_planted_future_h2h_meeting_fails_the_packet_census(tmp_path):
    def plant(doc):
        doc["matchups"][0]["h2h"]["last_meeting"] = {
            "season": 2025,
            "week": 12,
            "score": "163.68-128.96",
        }
        assert doc["matchups"][0]["h2h"]["last_meeting"]["week"] == 12

    fixture = _packet_fixture(tmp_path, plant)
    r = state_leak_census("content/weeks", packets=True, weeks_dir=fixture)
    assert r["future_entries"] == 1
    assert "h2h last_meeting wk12" in r["detail"][0]


def test_planted_future_highest_combined_fails_the_packet_census(tmp_path):
    def plant(doc):
        doc["historical_context"]["highest_combined"] = {
            "points": 385.7,
            "score": "191.1-194.6",
            "season": 2025,
            "teams": "Kittler on the Roof vs Rasheeing the Scene",
            "week": 14,
        }

    fixture = _packet_fixture(tmp_path, plant)
    r = state_leak_census("content/weeks", packets=True, weeks_dir=fixture)
    assert r["future_entries"] == 1
    assert "highest_combined wk14" in r["detail"][0]


def test_planted_overstated_streak_fails_the_packet_census(tmp_path):
    def plant(doc):
        doc["historical_context"]["longest_losing_streak"] = {
            "count": 99,
            "owner_id": "x",
            "team": "Noble FFT",
        }

    fixture = _packet_fixture(tmp_path, plant)
    r = state_leak_census("content/weeks", packets=True, weeks_dir=fixture)
    assert r["future_entries"] == 1
    assert "longest_losing_streak 99" in r["detail"][0]


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

    from scripts.migration_census import unmapped_packet_fields

    src = REPO / "content" / "weeks" / "week1_data.json"
    doc = j.loads(src.read_text(encoding="utf-8"))
    doc["matchups"][0]["speculative_nested_leaf"] = 1
    doc["planted_top_section"] = {"x": 1}
    fixture_dir = tmp_path / "weeks"
    fixture_dir.mkdir()
    (fixture_dir / "week1_data.json").write_text(j.dumps(doc), encoding="utf-8")
    unmapped = unmapped_packet_fields(2025, weeks_dir=fixture_dir)
    assert any("speculative_nested_leaf" in u for u in unmapped), unmapped
    assert any("planted_top_section" in u for u in unmapped)


def test_deep_and_dict_section_plants_fail_with_exact_paths(tmp_path):
    """The two false-green shapes the depth approximation missed: a leaf deep
    inside a list-section subtree, and a direct field inside a dict-shaped
    section. Each plant is asserted to land and must appear as its exact
    normalized path."""
    import json as j

    from scripts.migration_census import unmapped_packet_fields

    src = REPO / "content" / "weeks" / "week1_data.json"
    doc = j.loads(src.read_text(encoding="utf-8"))
    doc["matchups"][0]["h2h"]["last_meeting"]["planted_unknown_leaf"] = 1
    doc["historical_context"]["planted_unknown_leaf"] = 1
    assert "planted_unknown_leaf" in doc["matchups"][0]["h2h"]["last_meeting"]
    assert "planted_unknown_leaf" in doc["historical_context"], "plants must land"
    fixture_dir = tmp_path / "weeks"
    fixture_dir.mkdir()
    (fixture_dir / "week1_data.json").write_text(j.dumps(doc), encoding="utf-8")
    unmapped = unmapped_packet_fields(2025, weeks_dir=fixture_dir)
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
    original = sh.read_bytes()
    mutated = original.replace(b'"sha256": "sha256:', b'"sha256": "sha256:0', 1)
    assert mutated != original, "the plant must land"
    sh.write_bytes(mutated)
    try:
        with pytest.raises(ValueError, match="compiled contract failed verification"):
            state_leak_census("2025-preseason")
    finally:
        # byte-exact restore: verification must never mutate tracked bytes
        sh.write_bytes(original)
    assert sh.read_bytes() == original
    assert state_leak_census("2025-preseason")["future_entries"] == 0


def test_unsupported_season_is_rejected_not_vacuously_ok():
    with pytest.raises(ValueError, match="1901"):
        unmapped_packet_fields(1901)
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
    assert "OK" in r.stdout and "writer packets: 0 future entries" in r.stdout
    bare = subprocess.run(
        [PY, "scripts/migration_census.py"], cwd=REPO, capture_output=True, text=True
    )
    assert bare.returncode == 2, "a bare invocation is a usage error, never a census"


def test_cli_fails_by_exit_code_on_a_planted_packet_leak(tmp_path):
    """The production gate is the CLI: a planted post-cutoff value in the
    packet directory must turn --all red by exit code, not by prose."""
    import json as j

    src = REPO / "content" / "weeks" / "week1_data.json"
    doc = j.loads(src.read_text(encoding="utf-8"))
    doc["matchups"][0]["h2h"]["last_meeting"] = {
        "season": 2025,
        "week": 17,
        "score": "148.7-105.74",
    }
    fixture_dir = tmp_path / "weeks"
    fixture_dir.mkdir()
    (fixture_dir / "week1_data.json").write_text(j.dumps(doc), encoding="utf-8")
    r = subprocess.run(
        [
            PY,
            "scripts/migration_census.py",
            "--all",
            "--weeks-dir",
            str(fixture_dir),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL writer packets" in r.stdout and "wk17" in r.stdout
