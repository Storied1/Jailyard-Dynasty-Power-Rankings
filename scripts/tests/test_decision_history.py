"""K1.5 — arm-scoped decision history: suffix contract, portable locators,
exclusive-create, receipt binding, retrospective label, verify_tree."""

import json
from pathlib import Path

import pytest

from scripts.decision_history import (
    CrossArmContamination,
    decision_history_at,
    load_decision,
    seal,
    verify_predecessor,
    verify_tree,
)
from scripts.fact_schema import fact_hash


def mkseal(tmp, arm, trial, cutoff, eid):
    # A real (closed) receipt must exist BEFORE sealing -- the seal opens it,
    # verifies its bytes, and binds path AND content hash.
    d = Path(tmp) / "2025" / arm / f"trial{trial}"
    d.mkdir(parents=True, exist_ok=True)
    receipt = {
        "run_id": "run-1",
        "ended_at": "2026-08-05T00:00:00Z",
        "output_decision_hash": "sha256:" + "0" * 64,
    }
    rr = d / f"{eid}.run.json"
    rr.write_text(json.dumps(receipt), encoding="utf-8")
    return seal(
        root=tmp,
        edition_id=eid,
        season=2025,
        cutoff_utc="{}".format(cutoff),
        arm_id=arm,
        trial_id=trial,
        state_hash="sha256:" + "a" * 64,
        ranking={"entries": []},
        claims=[],
        run_id="run-1",
        run_receipt_path=rr,
        run_receipt_hash=fact_hash(receipt),
    )


def test_history_is_scoped_to_arm_and_trial(tmp_path):
    mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    mkseal(tmp_path, "no_chat", 1, "2025-09-03T23:59:59Z", "pre")
    got = decision_history_at(
        2025, "2025-09-05T00:00:00Z", "full_rich", 1, root=tmp_path
    )
    assert len(got) == 1 and got[0].arm_id == "full_rich"


def test_only_strictly_earlier_seals_are_returned(tmp_path):
    mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    mkseal(tmp_path, "full_rich", 1, "2025-09-09T06:59:59Z", "recap")
    got = decision_history_at(
        2025, "2025-09-09T06:59:59Z", "full_rich", 1, root=tmp_path
    )
    assert [s.edition_id for s in got] == ["pre"]


def test_preseason_has_no_history(tmp_path):
    assert (
        decision_history_at(2025, "2025-09-03T23:59:59Z", "full_rich", 1, root=tmp_path)
        == []
    )


def test_cross_arm_predecessor_is_rejected(tmp_path):
    other = mkseal(tmp_path, "no_chat", 1, "2025-09-03T23:59:59Z", "pre")
    with pytest.raises(CrossArmContamination):
        verify_predecessor(other, arm_id="full_rich", trial_id=1)


def test_cross_trial_predecessor_is_rejected(tmp_path):
    other = mkseal(tmp_path, "full_rich", 2, "2025-09-03T23:59:59Z", "pre")
    with pytest.raises(CrossArmContamination):
        verify_predecessor(other, arm_id="full_rich", trial_id=1)


def test_seal_is_immutable_hashed_and_labeled(tmp_path):
    s = mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    assert s.decision_hash.startswith("sha256:")
    assert s.label == "retrospective_backtest", "design §6: the label is explicit"
    with pytest.raises(Exception):
        s.arm_id = "no_chat"


def test_directory_holds_exactly_the_declared_file_species(tmp_path):
    """The naming contract IS the collision guard: a future writer adding a
    fifth species is caught here, not by a consumer's TypeError."""
    mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    d = tmp_path / "2025" / "full_rich" / "trial1"
    assert sorted(p.name for p in d.iterdir()) == [
        "pre.claims.json",
        "pre.ranking.json",
        "pre.run.json",
        "pre.seal.json",
    ]


def test_history_ignores_planted_body_files(tmp_path):
    """A stray {ed}.ranking.json must never parse as a seal."""
    mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    d = tmp_path / "2025" / "full_rich" / "trial1"
    (d / "stray.ranking.json").write_text('{"entries": []}', encoding="utf-8")
    got = decision_history_at(
        2025, "2025-09-05T00:00:00Z", "full_rich", 1, root=tmp_path
    )
    assert len(got) == 1 and got[0].edition_id == "pre"


def test_locators_are_relative_posix_and_hash_is_location_independent(tmp_path):
    """Machine-absolute locators are a host leak into a tracked file and make
    decision_hash differ per machine (the Phase-P portable-locator law)."""
    s = mkseal(tmp_path / "rootA", "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    t = mkseal(tmp_path / "rootB", "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    for loc in (s.ranking_path, s.claims_path, s.run_receipt_path):
        assert "\\" not in loc and not Path(loc).is_absolute()
    assert (
        s.decision_hash == t.decision_hash
    ), "same logical seal, same hash, any parent dir"
    assert load_decision(s, tmp_path / "rootA")[0] == {"entries": []}


def test_seal_refuses_to_overwrite_a_crashed_attempts_body(tmp_path):
    """Exclusive-create on the BODIES too: a pre-existing ranking body is
    refused, never truncated."""
    d = tmp_path / "2025" / "full_rich" / "trial1"
    d.mkdir(parents=True)
    (d / "pre.ranking.json").write_text('{"stale": true}', encoding="utf-8")
    with pytest.raises(FileExistsError):
        mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")


def test_seal_refuses_an_open_or_tampered_receipt(tmp_path):
    d = tmp_path / "2025" / "full_rich" / "trial1"
    d.mkdir(parents=True)
    open_receipt = {"run_id": "r", "ended_at": None, "output_decision_hash": None}
    rr = d / "pre.run.json"
    rr.write_text(json.dumps(open_receipt), encoding="utf-8")
    common = dict(
        root=tmp_path,
        edition_id="pre",
        season=2025,
        cutoff_utc="2025-09-03T23:59:59Z",
        arm_id="full_rich",
        trial_id=1,
        state_hash="sha256:" + "a" * 64,
        ranking={"entries": []},
        claims=[],
        run_id="r",
        run_receipt_path=rr,
    )
    with pytest.raises(ValueError, match="OPEN run receipt"):
        seal(**common, run_receipt_hash=fact_hash(open_receipt))
    with pytest.raises(ValueError, match="does not match run_receipt_hash"):
        seal(**common, run_receipt_hash="sha256:" + "f" * 64)


def test_verify_tree_catches_each_mutation_class(tmp_path):
    """Seal-body, ranking-body, receipt, label, and lineage mutations must each
    be caught -- and the pristine tree verifies clean."""
    mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    checked, failures = verify_tree(tmp_path)
    assert (checked, failures) == (1, [])

    d = tmp_path / "2025" / "full_rich" / "trial1"

    def mutate(name, transform):
        p = d / name
        original = p.read_text(encoding="utf-8")
        p.write_text(transform(original), encoding="utf-8")
        _, fails = verify_tree(tmp_path)
        p.write_text(original, encoding="utf-8")
        assert fails, f"mutation of {name} must be caught"
        return fails[0][1]

    problems = mutate("pre.ranking.json", lambda s: s.replace("[]", '[{"x": 1}]'))
    assert any("body" in p for p in problems)
    problems = mutate("pre.run.json", lambda s: s.replace("run-1", "run-9"))
    assert any("receipt hash" in p for p in problems)
    problems = mutate(
        "pre.seal.json", lambda s: s.replace("retrospective_backtest", "prospective")
    )
    # A label edit also breaks decision_hash -- both findings are correct.
    assert any("label" in p or "decision_hash" in p for p in problems)
    problems = mutate(
        "pre.seal.json",
        lambda s: s.replace(
            '"predecessor_decision_hash":null',
            f'"predecessor_decision_hash":"sha256:{"9" * 64}"',
        ),
    )
    assert any("lineage" in p or "decision_hash" in p for p in problems)


def test_verify_tree_lineage_resolves_within_arm_and_trial(tmp_path):
    pre = mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    d = Path(tmp_path) / "2025" / "full_rich" / "trial1"
    receipt = {
        "run_id": "run-2",
        "ended_at": "2026-08-05T00:10:00Z",
        "output_decision_hash": "sha256:" + "1" * 64,
    }
    rr = d / "preview.run.json"
    rr.write_text(json.dumps(receipt), encoding="utf-8")
    seal(
        root=tmp_path,
        edition_id="preview",
        season=2025,
        cutoff_utc="2025-09-05T00:19:59Z",
        arm_id="full_rich",
        trial_id=1,
        state_hash="sha256:" + "b" * 64,
        ranking={"entries": []},
        claims=[],
        run_id="run-2",
        run_receipt_path=rr,
        run_receipt_hash=fact_hash(receipt),
        predecessor_decision_hash=pre.decision_hash,
    )
    checked, failures = verify_tree(tmp_path)
    assert (checked, failures) == (2, [])
