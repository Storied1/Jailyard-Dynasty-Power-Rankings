"""K1.3 — state_at: required scope, lattice, vantage, admitted-only supersession."""

import pytest

from scripts.fact_schema import Fact, canonical_bytes, fact_hash
from scripts.temporal_state import SCOPE_LATTICE, state_at


def F(**over):
    base = dict(
        fact_id="f",
        source_record_id="r",
        entity_ref={"type": "t", "id": "1"},
        source_ref="s",
        fact_type="transaction",
        effective_at="2025-09-01T00:00:00Z",
        known_at="2025-09-01T00:00:00Z",
        access_scope="public",
        known_at_basis="b",
        captured_at="2026-01-01T00:00:00Z",
        content_sha256="sha256:" + "a" * 64,
        privacy="public",
        normalizer_version="v1",
        schema_version=1,
        supersedes=None,
    )
    base.update(over)
    # Mirror K1.1's mk(): `payload=` is the ergonomic call form; the dataclass
    # field is payload_bytes, and content_sha256 must match the body or
    # __post_init__ raises PayloadIntegrityError. K1.4's M() and K3's fixtures
    # all construct through this path.
    if "payload" in base:
        body = base.pop("payload")
        base["payload_bytes"] = canonical_bytes(body)
        if "content_sha256" not in over:
            base["content_sha256"] = fact_hash(body)
    return Fact(**base)


def test_lattice_is_exactly_two_rows():
    assert SCOPE_LATTICE == {
        "public": {"public"},
        "league_private": {"public", "league_private"},
    }


def test_public_scope_excludes_league_private():
    facts = [
        F(fact_id="p", source_record_id="a"),
        F(
            fact_id="q",
            source_record_id="b",
            access_scope="league_private",
            fact_type="chat_message",
        ),
    ]
    pub = state_at(2025, "2025-09-02T00:00:00Z", "public", facts=facts)
    priv = state_at(2025, "2025-09-02T00:00:00Z", "league_private", facts=facts)
    assert {f.fact_id for f in pub.admitted} == {"p"}
    assert {f.fact_id for f in priv.admitted} == {"p", "q"}


def test_omitted_or_unknown_scope_fails_closed():
    with pytest.raises(ValueError):
        state_at(2025, "2025-09-02T00:00:00Z", "everyone", facts=[])
    with pytest.raises(TypeError):
        state_at(2025, "2025-09-02T00:00:00Z", facts=[])


def test_known_at_after_cutoff_is_excluded():
    facts = [F(fact_id="late", known_at="2025-09-10T00:00:00Z")]
    assert state_at(2025, "2025-09-02T00:00:00Z", "public", facts=facts).admitted == []


def test_admission_is_inclusive_at_the_cutoff():
    facts = [F(fact_id="edge", known_at="2025-09-02T00:00:00Z")]
    assert (
        len(state_at(2025, "2025-09-02T00:00:00Z", "public", facts=facts).admitted) == 1
    )


def test_cutoff_comparison_is_canonical_on_both_sides():
    """A fact one microsecond past a whole-second cutoff must be excluded --
    mixed-width string comparison would admit it."""
    facts = [F(fact_id="late", known_at="2025-09-02T00:00:00.000001Z")]
    assert state_at(2025, "2025-09-02T00:00:00Z", "public", facts=facts).admitted == []
    with pytest.raises(ValueError):
        state_at(2025, "2025-09-02", "public", facts=facts)


def test_supersession_respects_known_at():
    a = F(fact_id="a", source_record_id="txn", known_at="2025-09-01T00:00:00Z")
    b = F(
        fact_id="b",
        source_record_id="txn",
        known_at="2025-09-05T00:00:00Z",
        supersedes="a",
    )
    early = state_at(2025, "2025-09-03T00:00:00Z", "public", facts=[a, b])
    late = state_at(2025, "2025-09-07T00:00:00Z", "public", facts=[a, b])
    assert early.value("transaction", "txn").fact_id == "a"
    assert late.value("transaction", "txn").fact_id == "b"


def test_three_step_correction_chain_resolves_at_each_cutoff():
    a = F(fact_id="a", source_record_id="r", known_at="2025-09-01T00:00:00Z")
    b = F(
        fact_id="b",
        source_record_id="r",
        known_at="2025-09-05T00:00:00Z",
        supersedes="a",
    )
    c = F(
        fact_id="c",
        source_record_id="r",
        known_at="2025-09-09T00:00:00Z",
        supersedes="b",
    )
    facts = [a, b, c]
    for cutoff, expected in (
        ("2025-09-02T00:00:00Z", "a"),
        ("2025-09-06T00:00:00Z", "b"),
        ("2025-09-10T00:00:00Z", "c"),
    ):
        assert (
            state_at(2025, cutoff, "public", facts=facts)
            .value("transaction", "r")
            .fact_id
            == expected
        )


def test_as_recorded_at_excludes_late_captures():
    facts = [
        F(fact_id="early", source_record_id="x", captured_at="2026-01-01T00:00:00Z"),
        F(fact_id="late", source_record_id="y", captured_at="2026-08-01T00:00:00Z"),
    ]
    latest = state_at(2025, "2025-12-01T00:00:00Z", "public", facts=facts)
    vantage = state_at(
        2025,
        "2025-12-01T00:00:00Z",
        "public",
        as_recorded_at="2026-03-01T00:00:00Z",
        facts=facts,
    )
    assert {f.fact_id for f in latest.admitted} == {"early", "late"}
    assert {f.fact_id for f in vantage.admitted} == {"early"}


def test_state_contains_no_decisions():
    s = state_at(2025, "2025-09-02T00:00:00Z", "public", facts=[F()])
    assert not hasattr(s, "decisions") and not hasattr(s, "rankings")
