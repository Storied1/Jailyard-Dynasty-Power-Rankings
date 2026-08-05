"""K1.2 — idempotent coalescing, revert-safe supersession, type-bound identity."""

import pytest

from scripts.fact_store import FactStore

OBS = dict(
    source_record_id="txn:1",
    entity_ref={"type": "player", "id": "6949"},
    source_ref="capture:a",
    fact_type="transaction",
    effective_at="2025-09-05T20:10:20Z",
    known_at="2025-09-05T20:10:20Z",
    access_scope="public",
    known_at_basis="effective_completion_instant",
    captured_at="2026-08-02T00:00:00Z",
    privacy="public",
    normalizer_version="norm-v1",
)


def test_identical_repeat_coalesces(tmp_path):
    s = FactStore(tmp_path / "facts.jsonl")
    f1, a1 = s.observe(payload={"v": 1}, **OBS)
    f2, a2 = s.observe(
        payload={"v": 1}, **dict(OBS, captured_at="2026-08-03T00:00:00Z")
    )
    assert a1 == "created" and a2 == "coalesced"
    assert f1.fact_id == f2.fact_id and len(s.load()) == 1


def test_changed_record_supersedes(tmp_path):
    s = FactStore(tmp_path / "facts.jsonl")
    f1, _ = s.observe(payload={"v": 1}, **OBS)
    f2, action = s.observe(
        payload={"v": 2},
        **dict(
            OBS, known_at="2025-09-06T00:00:00Z", captured_at="2026-08-03T00:00:00Z"
        ),
    )
    assert action == "superseded" and f2.supersedes == f1.fact_id
    assert len(s.load()) == 2, "the original is retained, not mutated"


def test_fact_id_is_deterministic(tmp_path):
    a = FactStore(tmp_path / "a.jsonl").observe(payload={"v": 1}, **OBS)[0]
    b = FactStore(tmp_path / "b.jsonl").observe(payload={"v": 1}, **OBS)[0]
    assert a.fact_id == b.fact_id


def test_invalid_fact_is_refused(tmp_path):
    s = FactStore(tmp_path / "facts.jsonl")
    with pytest.raises(ValueError):
        s.observe(payload={"v": 1}, **dict(OBS, access_scope="everyone"))


def test_write_is_byte_stable(tmp_path):
    s = FactStore(tmp_path / "f.jsonl")
    s.observe(payload={"v": 1}, **OBS)
    s.observe(payload={"v": 2}, **dict(OBS, source_record_id="txn:2"))
    s.write()
    first = (tmp_path / "f.jsonl").read_bytes()
    s.write()
    assert (tmp_path / "f.jsonl").read_bytes() == first


def test_payload_survives_a_write_reload_round_trip(tmp_path):
    """K1.4's aggregates are recomputed from admitted facts. A store that drops
    the body makes every reducer inoperable on production data."""
    p = tmp_path / "f.jsonl"
    s = FactStore(p)
    s.observe(payload={"home": "A", "home_pts": 120.5}, **OBS)
    s.write()
    reloaded = FactStore(p).load()[0]
    assert reloaded.payload == {"home": "A", "home_pts": 120.5}
    assert reloaded.content_sha256.startswith("sha256:")


def test_normalizer_version_change_supersedes_rather_than_coalescing(tmp_path):
    """The design binds normalizer_version because a normalizer change is a
    change in MEANING even when the capture bytes are identical."""
    s = FactStore(tmp_path / "f.jsonl")
    f1, a1 = s.observe(payload={"v": 1}, **OBS)
    f2, a2 = s.observe(
        payload={"v": 1},
        **dict(OBS, normalizer_version="norm-v2", known_at="2025-09-06T00:00:00Z"),
    )
    assert a1 == "created" and a2 == "superseded"
    assert f2.supersedes == f1.fact_id and len(s.load()) == 2


def test_on_disk_payload_tampering_is_refused(tmp_path):
    """content_sha256 must describe the bytes the store actually holds."""
    from scripts.fact_schema import PayloadIntegrityError

    p = tmp_path / "f.jsonl"
    s = FactStore(p)
    s.observe(payload={"v": 1}, **OBS)
    s.write()
    poisoned = p.read_text(encoding="utf-8").replace('"v":1', '"v":999')
    p.write_text(poisoned, encoding="utf-8", newline="\n")
    with pytest.raises(PayloadIntegrityError):
        FactStore(p).load()


def test_value_revert_mints_three_distinct_ids_not_a_cycle(tmp_path):
    """A -> B -> A at a stable known_at (roster drop/re-add before the anchor
    moves). Without `supersedes` in the identity hash the third observation
    re-mints the first fact_id and the supersession graph becomes a cycle.
    (The state-resolution half of this scenario lives in K1.7's
    test_2b_value_revert_resolves_through_state_at -- temporal_state.py does
    not exist yet at this task.)"""
    s = FactStore(tmp_path / "f.jsonl")
    r = dict(OBS, source_record_id="roster:2025:1:6949", fact_type="transaction")
    f1, _ = s.observe(payload={"on": True}, **r)
    f2, _ = s.observe(payload={"on": False}, **r)
    f3, _ = s.observe(payload={"on": True}, **r)
    assert len({f1.fact_id, f2.fact_id, f3.fact_id}) == 3 and len(s.load()) == 3
    assert f2.supersedes == f1.fact_id and f3.supersedes == f2.fact_id


def test_mixed_instant_forms_coalesce_in_both_orders(tmp_path):
    """Same store, same instant, whole-second and six-digit forms, BOTH orders:
    the second observation must coalesce (no new fact) and the on-disk bytes
    must be unchanged by the repeat. Without canonicalization inside observe(),
    identity hashes the raw string and the two forms mint two facts."""
    pairs = (
        ("2025-09-05T20:10:20Z", "2025-09-05T20:10:20.000000Z"),
        ("2025-09-05T20:10:20.000000Z", "2025-09-05T20:10:20Z"),
    )
    for n, (first, second) in enumerate(pairs):
        s = FactStore(tmp_path / f"f-{n}.jsonl")
        f1, a1 = s.observe(
            payload={"v": 1}, **dict(OBS, known_at=first, effective_at=first)
        )
        s.write()
        before = s.path.read_bytes()
        f2, a2 = s.observe(
            payload={"v": 1}, **dict(OBS, known_at=second, effective_at=second)
        )
        s.write()
        assert a1 == "created" and a2 == "coalesced" and f1.fact_id == f2.fact_id
        assert s.path.read_bytes() == before, "a coalesced repeat changes no byte"


def test_same_record_id_under_two_types_never_cross_supersedes(tmp_path):
    """Prefix disjointness is a convention in nine f-strings; the mechanism is
    (fact_type, source_record_id) resolution AND fact_type inside fact_id.
    IDENTICAL content, instants, and normalizer version -- a differing payload
    would mask an id collision, and the collision refusal would reject this
    perfectly legitimate second observation."""
    s = FactStore(tmp_path / "f.jsonl")
    a, act_a = s.observe(payload={"v": 1}, **OBS)
    b, act_b = s.observe(
        payload={"v": 1},
        **dict(OBS, fact_type="matchup_result", known_at_basis="game_conclusion"),
    )
    assert act_a == "created" and act_b == "created"
    assert a.fact_id != b.fact_id, "fact_type must be bound into identity"
    assert b.supersedes is None and len(s.load()) == 2
