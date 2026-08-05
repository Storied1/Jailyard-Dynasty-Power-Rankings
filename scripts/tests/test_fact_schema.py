"""K1.1 — the fifteen-field temporal fact schema with fail-closed validation."""

import pytest

from scripts.fact_schema import (
    FACT_FIELDS,
    Fact,
    PayloadIntegrityError,
    canonical_bytes,
    canonical_instant,
    fact_hash,
    load_fact_types,
    validate,
)


def mk(**over):
    base = dict(
        fact_id="f1",
        source_record_id="txn:1",
        entity_ref={"type": "player", "id": "6949"},
        source_ref="capture:2026/public/transactions/20260802T000000Z",
        fact_type="transaction",
        effective_at="2025-09-05T20:10:20Z",
        known_at="2025-09-05T20:10:20Z",
        access_scope="public",
        known_at_basis="effective_completion_instant",
        captured_at="2026-02-17T00:00:00Z",
        content_sha256="sha256:" + "a" * 64,
        privacy="public",
        normalizer_version="norm-v1",
        schema_version=1,
        supersedes=None,
    )
    base.update(over)
    # `payload=` is the ergonomic call form; the field is payload_bytes. Derive
    # content_sha256 from the body UNLESS the caller pinned one deliberately
    # (the integrity test pins a deliberately wrong hash).
    if "payload" in base:
        body = base.pop("payload")
        base["payload_bytes"] = canonical_bytes(body)
        if "content_sha256" not in over:
            base["content_sha256"] = fact_hash(body)
    return Fact(**base)


def test_all_fifteen_fields_present():
    assert len(FACT_FIELDS) == 15
    assert not {"payload", "payload_bytes"} & set(
        FACT_FIELDS
    ), "the body is an attachment, never a contract field"
    for f in (
        "fact_id",
        "source_record_id",
        "entity_ref",
        "source_ref",
        "fact_type",
        "effective_at",
        "known_at",
        "access_scope",
        "known_at_basis",
        "captured_at",
        "content_sha256",
        "privacy",
        "normalizer_version",
        "schema_version",
        "supersedes",
    ):
        assert f in FACT_FIELDS


def test_payload_is_reachable_but_outside_the_contract():
    """K1.4's reducers read f.payload; the contract stays at fifteen fields."""
    assert mk().payload is None
    assert mk(payload={"home_pts": 120.5}).payload["home_pts"] == 120.5


def test_caller_cannot_mutate_a_hashed_payload():
    body = {"home_pts": 120.5}
    f = mk(payload=body)
    body["home_pts"] = 999.0  # caller mutates after construction
    assert f.payload["home_pts"] == 120.5
    f.payload["home_pts"] = 999.0  # and mutates what the getter handed back
    assert f.payload["home_pts"] == 120.5


def test_payload_hash_mismatch_is_refused():
    with pytest.raises(PayloadIntegrityError):
        mk(payload={"a": 1}, content_sha256=fact_hash({"a": 2}))


def test_missing_access_scope_is_invalid():
    assert validate(mk(access_scope=None))


def test_unknown_access_scope_is_invalid():
    assert validate(mk(access_scope="everyone"))


def test_known_at_before_effective_at_is_allowed_but_captured_before_known_is_not():
    assert not validate(
        mk(known_at="2025-09-05T20:10:20Z", captured_at="2026-01-01T00:00:00Z")
    )
    assert validate(
        mk(known_at="2026-01-01T00:00:00Z", captured_at="2025-01-01T00:00:00Z")
    )


def test_naive_or_date_only_timestamps_rejected():
    for bad in ("2025-09-05", "2025-09-05 20:10:20", "2025-09"):
        assert validate(mk(known_at=bad))


def test_instants_canonicalize_to_six_fractional_digits():
    """Whole-second and fractional inputs both land on the canonical form, so
    string comparison is chronological comparison."""
    f = mk()
    assert f.known_at == "2025-09-05T20:10:20.000000Z"
    g = mk(captured_at="2026-08-05T03:30:23.482196Z")
    assert g.captured_at == "2026-08-05T03:30:23.482196Z"
    assert canonical_instant("2025-09-05T20:10:20.5Z") == "2025-09-05T20:10:20.500000Z"
    assert canonical_instant("2025-09-05") is None
    assert canonical_instant(None) is None


def test_unregistered_fact_type_is_invalid():
    assert validate(mk(fact_type="speculative_type"))


def test_entity_ref_missing_a_required_key_is_invalid_even_with_extras():
    """A proper-subset test passes {"type","season"}; the superset test must not."""
    assert validate(mk(entity_ref={"type": "player", "season": 2025}))
    assert validate(mk(entity_ref={"id": "1", "week": 1}))
    assert not validate(mk(entity_ref={"type": "player", "id": "1", "week": 1}))


def test_fact_is_immutable():
    with pytest.raises(Exception):
        mk().known_at = "2026-01-01T00:00:00Z"


def test_fact_types_registry_covers_the_nine_bridge_types():
    reg = load_fact_types()
    for t in (
        "franchise_identity",
        "schedule_pairing",
        "matchup_result",
        "roster_membership",
        "transaction",
        "draft_pick",
        "chat_message",
        "historical_matchup",
        "nfl_game",
    ):
        assert t in reg, t
        assert reg[t]["reducer"] and reg[t]["default_access_scope"] in {
            "public",
            "league_private",
        }
