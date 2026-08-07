"""K3.3 — frozen evidence manifest, bounded degradation, producer-drift gates."""

import json as j

import pytest

from scripts.eval_contrast import (
    MANIFEST_PATH,
    assess_contrast,
    freeze_manifest,
    load_manifest,
)

REQUIRED = {"roster_membership", "historical_matchup", "chat_message", "nfl_game"}


def _unfrozen_copy(tmp_path, name="evidence_families.json", sync_producers=True):
    """A copy with the stamps cleared. Freeze-state-agnostic: K3.7 Step 1
    freezes the COMMITTED manifest exactly once, and these tests must keep
    proving the same rules before AND after that -- a fixture that freezes the
    committed copy directly breaks permanently the moment the plan succeeds.

    `sync_producers` rewrites each family's producer view from the LIVE source
    map. The rules under test here are about degradation and cycle bounds, not
    about what the committed v1 manifest happened to declare in August 2026; a
    fixture pinned to that snapshot fails on any legitimate producer change and
    reports it as a bug in the rule. The drift itself is asserted separately, by
    test_committed_manifest_drifts_on_roster_membership.
    """
    doc = j.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    doc["frozen_at"] = None
    doc["manifest_sha256"] = None
    if sync_producers:
        from scripts.eval_contrast import _recomputed_producers

        live = _recomputed_producers()
        for fam in doc["families"]:
            fam.update(live[fam["family"]])
    p = tmp_path / name
    p.write_text(j.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    return p


@pytest.fixture
def frozen(tmp_path):
    """A frozen copy, from an explicitly unfrozen base."""
    p = _unfrozen_copy(tmp_path)
    freeze_manifest(path=p, frozen_at="2026-08-02T00:00:00Z")
    return load_manifest(path=p)


def FC(totals, unavailable=None):
    """family_counts result shape -- what assess_contrast ACTUALLY receives in
    production. Round-two tests passed flat maps and a positional cycle count;
    implemented to those tests, the production path found none of the required
    families and reported DEGRADED on every run regardless of the evidence."""
    return {
        "totals": totals,
        "per_edition": {"2025-wk01-recap": dict(totals)},
        "unavailable": dict(unavailable or {}),
    }


def test_manifest_freeze_state_is_coherent():
    """True BEFORE and AFTER K3.7 Step 1 freezes the committed file -- asserting
    `frozen_at is None` outright made the plan's own success break the K3.8
    suite gate permanently."""
    m = load_manifest()
    assert (m["frozen_at"] is None) == (m["manifest_sha256"] is None)


def test_manifest_requires_exactly_the_four_families():
    m = load_manifest()
    assert {f["family"] for f in m["families"] if f["required"]} == REQUIRED


def test_media_is_explicitly_excluded():
    m = load_manifest()
    media = next(f for f in m["families"] if f["family"] == "media_item")
    assert media["required"] is False and "S1b" in media["rationale"]


def test_assessing_an_unfrozen_manifest_is_refused(tmp_path):
    unfrozen = load_manifest(path=_unfrozen_copy(tmp_path, "m.json"))
    assert unfrozen["frozen_at"] is None
    with pytest.raises(ValueError):
        assess_contrast(
            unfrozen,
            FC({"roster_membership": 12}),
            FC({}),
            state_path=tmp_path / "state.json",
        )


def test_freezing_twice_is_refused(tmp_path):
    p = _unfrozen_copy(tmp_path, "m.json")
    freeze_manifest(path=p, frozen_at="2026-08-02T00:00:00Z")
    with pytest.raises(ValueError):
        freeze_manifest(path=p, frozen_at="2026-08-03T00:00:00Z")


def test_missing_required_family_is_degraded(frozen, tmp_path):
    full = FC(
        {
            "roster_membership": 12,
            "historical_matchup": 0,
            "chat_message": 900,
            "nfl_game": 16,
        }
    )
    r = assess_contrast(
        frozen, full, FC({"roster_membership": 12}), state_path=tmp_path / "state.json"
    )
    assert r.status == "degraded" and "historical_matchup" in r.missing


def test_declared_unavailable_family_is_degraded_not_clean(frozen, tmp_path):
    """normalize_all's recorded refusal must reach the verdict as degradation --
    the clean-but-empty trap."""
    full = FC(
        {
            "roster_membership": 0,
            "historical_matchup": 400,
            "chat_message": 900,
            "nfl_game": 16,
        },
        unavailable={"roster_membership": "no qualified anchor"},
    )
    r = assess_contrast(frozen, full, FC({}), state_path=tmp_path / "state.json")
    assert r.status == "degraded" and "roster_membership" in r.missing


def test_absent_media_does_not_degrade(frozen, tmp_path):
    full = FC(
        {
            "roster_membership": 12,
            "historical_matchup": 400,
            "chat_message": 900,
            "nfl_game": 16,
            "media_item": 0,
        }
    )
    r = assess_contrast(
        frozen, full, FC({"roster_membership": 12}), state_path=tmp_path / "state.json"
    )
    assert r.status == "ok"


def test_identical_bundles_are_degraded_even_when_complete(frozen, tmp_path):
    full = FC(
        {
            "roster_membership": 12,
            "historical_matchup": 400,
            "chat_message": 900,
            "nfl_game": 16,
        }
    )
    r = assess_contrast(
        frozen, full, FC(dict(full["totals"])), state_path=tmp_path / "state.json"
    )
    assert r.status == "degraded" and "no measurable difference" in r.reason


def test_second_degraded_cycle_stops_via_the_persisted_counter(frozen, tmp_path):
    """TWO CALLS against one state file. The counter is read from and written to
    disk, keyed by manifest_sha256 -- if assess_contrast took it from a parameter
    or env var this test fails, which is the point: every re-run would otherwise
    be cycle one and 'one remediation cycle' would be unbounded in practice."""
    sp = tmp_path / "contrast_state.json"
    full = FC(
        {
            "roster_membership": 12,
            "historical_matchup": 0,
            "chat_message": 900,
            "nfl_game": 16,
        }
    )
    first = assess_contrast(frozen, full, FC({"roster_membership": 12}), state_path=sp)
    assert first.status == "degraded" and first.cycles_used == 1
    on_disk = j.loads(sp.read_text(encoding="utf-8"))
    assert on_disk == {"manifest_sha256": frozen["manifest_sha256"], "cycles_used": 1}
    second = assess_contrast(frozen, full, FC({"roster_membership": 12}), state_path=sp)
    assert second.status == "stop_no_decision"
    assert "S1a does not begin" in second.reason


def test_freeze_stamps_an_instant_and_a_hash(frozen):
    assert frozen["frozen_at"] and frozen["manifest_sha256"].startswith("sha256:")


def test_manifest_source_and_version_drift_are_failed_gates(frozen, tmp_path):
    """Planted drift must LAND and produce ManifestDrift (CLI exit 4): an added
    source_id and a bumped normalizer_version each differ from the frozen
    values recomputed from the availability report."""
    from scripts.eval_contrast import ManifestDrift, _recomputed_producers

    live = _recomputed_producers()  # from the persisted report + source maps
    added = {
        f: dict(v, source_ids=v["source_ids"] + ["planted:new_source"])
        for f, v in live.items()
    }
    assert added != live, "the source plant must land"
    bumped = {f: dict(v, normalizer_version="norm-v2") for f, v in live.items()}
    assert bumped != live, "the version plant must land"
    for planted in (added, bumped):
        with pytest.raises(ManifestDrift):
            assess_contrast(
                frozen,
                FC({"roster_membership": 12}),
                FC({}),
                state_path=tmp_path / "s.json",
                _producers=planted,
            )


def test_committed_manifest_drifts_on_roster_membership():
    """The freeze binds the LIVE producer surface, and it no longer matches.

    This test used to assert live == frozen. That stopped being true when the
    2025 provenance repair SOURCED `roster_membership`, which the manifest had
    frozen as "declared unsourced (open dependency 3); frozen as such".

    The drift is real, intentional and deliberately NOT repaired:

      * The design's contrast-integrity rule is that changing the manifest
        invalidates every completed arm and restarts the comparison. K3 spent
        0 of 36 authorized model invocations, so nothing is invalidated.
      * K3 was ruled DORMANT on 2026-08-06. Re-freezing the manifest is a K3
        action and is not authorized. The frozen file is a record of a
        precommitment, not a live gate.

    So the assertion is inverted and pinned: exactly ONE family drifts, it is
    `roster_membership`, and production --assess therefore refuses to start.
    Whoever revives K3 must re-freeze against the repaired store first, and this
    test is where they will find out.
    """
    from scripts.eval_contrast import _recomputed_producers

    live = _recomputed_producers()
    drifted = {
        fam["family"]
        for fam in load_manifest()["families"]
        if fam["source_ids"] != live[fam["family"]]["source_ids"]
        or fam["normalizer_version"] != live[fam["family"]]["normalizer_version"]
    }
    assert drifted == {"roster_membership"}


def test_assess_refuses_the_committed_manifest_until_it_is_re_frozen(tmp_path):
    """The consequence, exercised rather than described: with the committed
    producer view, assess_contrast raises rather than quietly comparing against
    a manifest that no longer describes the store."""
    from scripts.eval_contrast import ManifestDrift

    stale = _unfrozen_copy(tmp_path, sync_producers=False)
    freeze_manifest(path=stale, frozen_at="2026-08-02T00:00:00Z")
    with pytest.raises(ManifestDrift, match="roster_membership"):
        assess_contrast(
            load_manifest(path=stale),
            FC({f: 1 for f in REQUIRED}),
            FC({"franchise_identity": 1}),
            state_path=tmp_path / "s.json",
        )


def test_degraded_preflight_leaves_the_cycle_counter_unchanged(frozen, tmp_path):
    """Preflight is ADVISORY: it must never consume the one remediation cycle,
    or a degraded preflight would spend the only cycle before assess ever ran."""
    from scripts.eval_contrast import preflight

    sp = tmp_path / "contrast_state.json"
    full = FC(
        {
            "roster_membership": 12,
            "historical_matchup": 0,
            "chat_message": 900,
            "nfl_game": 16,
        }
    )
    r = preflight(
        frozen, _full=full, _minimal=FC({"roster_membership": 12}), state_path=sp
    )
    assert r.status == "degraded"
    assert not sp.exists(), "a preflight must not write the cycle counter"


def test_preflight_and_assess_agree_on_identical_inputs(frozen, tmp_path):
    from scripts.eval_contrast import preflight

    full = FC(
        {
            "roster_membership": 12,
            "historical_matchup": 400,
            "chat_message": 900,
            "nfl_game": 16,
        }
    )
    minimal = FC({"roster_membership": 12})
    p = preflight(frozen, _full=full, _minimal=minimal, state_path=tmp_path / "s1.json")
    a = assess_contrast(frozen, full, minimal, state_path=tmp_path / "s2.json")
    assert (p.status, p.missing) == (a.status, a.missing) == ("ok", [])
