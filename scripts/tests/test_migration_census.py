"""K2.3 — migration checks and the state leak census."""

import subprocess
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
