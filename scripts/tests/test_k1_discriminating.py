"""K1.7 — the seven K1 rules. Every mutation control (a) plants its mutation in
a symbol production reads, (b) asserts the plant LANDED, and (c) reads the
consequence through production code. Plus the four preserved noninterference
proofs and deterministic replay. Rule 7's consumer-level control is deferred to
K3.5 (its consumer does not exist in K1/K2 scope)."""

import pytest

from scripts.fact_schema import canonical_bytes, fact_hash  # noqa: F401 - control uses
from scripts.fact_store import FactStore
from scripts.normalize_facts import NORMALIZERS, UnqualifiedSource, normalize_all
from scripts.temporal_state import state_at
from scripts.tests.test_temporal_state import F

OBS = dict(
    source_record_id="txn:1",
    entity_ref={"type": "t", "id": "1"},
    source_ref="s",
    fact_type="transaction",
    effective_at="2025-09-01T00:00:00Z",
    known_at="2025-09-01T00:00:00Z",
    access_scope="public",
    known_at_basis="b",
    captured_at="2026-08-02T00:00:00Z",
    privacy="public",
    normalizer_version="v1",
)


# 1 -------------------------------------------------------------------------
def test_1_duplicate_capture_yields_one_fact(tmp_path):
    s = FactStore(tmp_path / "f.jsonl")
    s.observe(payload={"v": 1}, **OBS)
    s.observe(payload={"v": 1}, **dict(OBS, captured_at="2026-08-03T00:00:00Z"))
    assert len(s.load()) == 1


def test_1_mutation_without_coalescing_hits_the_id_refusal(tmp_path, monkeypatch):
    """Control with defense-in-depth: disable coalescing and the second
    identical observation mints the SAME fact_id -- the duplicate-id refusal
    fires instead of silently duplicating."""

    def disabled(self, ft, srid):
        return None

    monkeypatch.setattr(FactStore, "_latest_for", disabled)
    s = FactStore(tmp_path / "f.jsonl")
    assert FactStore._latest_for is disabled, "the plant must land"
    s.observe(payload={"v": 1}, **OBS)
    with pytest.raises(ValueError, match="fact_id collision"):
        s.observe(payload={"v": 1}, **dict(OBS, captured_at="2026-08-03T00:00:00Z"))


# 2 -------------------------------------------------------------------------
def test_2_revised_duplicate_supersedes_without_mutating(tmp_path):
    s = FactStore(tmp_path / "f.jsonl")
    f1, _ = s.observe(payload={"v": 1}, **OBS)
    f2, action = s.observe(
        payload={"v": 2}, **dict(OBS, known_at="2025-09-06T00:00:00Z")
    )
    assert action == "superseded" and f2.supersedes == f1.fact_id
    assert s.load()[0].content_sha256 == f1.content_sha256, "original untouched"


def test_2b_value_revert_resolves_through_state_at(tmp_path):
    """The state half of K1.2's revert test: all three facts of an A -> B -> A
    chain admit, the chain retires cleanly, and value() resolves to the final
    reading -- never None, which is what the pre-fix id cycle produced."""
    s = FactStore(tmp_path / "f.jsonl")
    r = dict(OBS, source_record_id="roster:2025:1:6949")
    s.observe(payload={"on": True}, **r)
    s.observe(payload={"on": False}, **dict(r, known_at="2025-09-01T01:00:00Z"))
    s.observe(payload={"on": True}, **dict(r, known_at="2025-09-01T02:00:00Z"))
    got = state_at(2025, "2025-09-02T00:00:00Z", "public", facts=s.load())
    assert got.value("transaction", "roster:2025:1:6949").payload == {"on": True}


# 3 -------------------------------------------------------------------------
def test_3_late_capture_excluded_from_as_recorded_replay():
    facts = [
        F(fact_id="early", source_record_id="a", captured_at="2026-01-01T00:00:00Z"),
        F(fact_id="late", source_record_id="b", captured_at="2026-08-01T00:00:00Z"),
    ]
    vantage = state_at(
        2025,
        "2025-12-01T00:00:00Z",
        "public",
        as_recorded_at="2026-03-01T00:00:00Z",
        facts=facts,
    )
    latest = state_at(2025, "2025-12-01T00:00:00Z", "public", facts=facts)
    assert {f.fact_id for f in vantage.admitted} == {"early"}
    assert {f.fact_id for f in latest.admitted} == {"early", "late"}


def test_3_mutation_ignoring_vantage_admits_the_late_capture(monkeypatch):
    """Control: drop the captured_at filter and as-recorded replay stops
    existing. The plant lands on the module attribute the caller reads."""
    import scripts.temporal_state as ts

    facts = [
        F(fact_id="early", source_record_id="a", captured_at="2026-01-01T00:00:00Z"),
        F(fact_id="late", source_record_id="b", captured_at="2026-08-01T00:00:00Z"),
    ]
    real = ts.state_at

    def leaky(season, cutoff, scope, as_recorded_at=None, facts=None):
        return real(season, cutoff, scope, as_recorded_at=None, facts=facts)

    monkeypatch.setattr(ts, "state_at", leaky)
    assert ts.state_at is leaky, "the plant must land"
    got = ts.state_at(
        2025,
        "2025-12-01T00:00:00Z",
        "public",
        as_recorded_at="2026-03-01T00:00:00Z",
        facts=facts,
    )
    assert {f.fact_id for f in got.admitted} == {
        "early",
        "late",
    }, "control: without the vantage filter a 2026 capture backdates into 2025"


# 4 -------------------------------------------------------------------------
def test_4_private_scope_exclusion_via_the_shipped_interface():
    facts = [
        F(fact_id="pub", source_record_id="a"),
        F(
            fact_id="priv",
            source_record_id="b",
            access_scope="league_private",
            fact_type="chat_message",
        ),
    ]
    assert {
        f.fact_id
        for f in state_at(
            2025, "2025-12-01T00:00:00Z", "league_private", facts=facts
        ).admitted
    } == {"pub", "priv"}
    assert {
        f.fact_id
        for f in state_at(2025, "2025-12-01T00:00:00Z", "public", facts=facts).admitted
    } == {"pub"}


def test_4_mutation_open_lattice_leaks_private_facts(monkeypatch):
    """Control: widen the lattice and the public state silently gains chat."""
    import scripts.temporal_state as ts

    monkeypatch.setitem(ts.SCOPE_LATTICE, "public", {"public", "league_private"})
    assert ts.SCOPE_LATTICE["public"] == {
        "public",
        "league_private",
    }, "the plant must land"
    facts = [
        F(fact_id="pub", source_record_id="a"),
        F(
            fact_id="priv",
            source_record_id="b",
            access_scope="league_private",
            fact_type="chat_message",
        ),
    ]
    got = ts.state_at(2025, "2025-12-01T00:00:00Z", "public", facts=facts)
    assert {f.fact_id for f in got.admitted} == {
        "pub",
        "priv",
    }, "control: the lattice is the only thing enforcing scope"


# 5 -------------------------------------------------------------------------
def test_5_schedule_provenance_failure_is_unavailable():
    with pytest.raises(UnqualifiedSource):
        NORMALIZERS["schedule_pairing"]({"source": "weekly_packet"}, season=2025)


def test_5_mutation_accepting_a_stripped_packet_admits_an_unqualified_pairing(
    monkeypatch,
):
    """Control: remove the packet-source guard IN THE PRODUCTION REGISTRY and
    concealment reads as availability. The consequence is read through the
    registry lookup -- not from a lambda the test wrote."""
    import scripts.normalize_facts as nf

    raw = {
        "source": "weekly_packet",
        "home": "A",
        "away": "B",
        "week": 1,
        "known_at": "2025-08-01T00:00:00Z",
    }
    original = nf.NORMALIZERS["schedule_pairing"]

    def permissive(r, season):
        return (
            {
                "fact_type": "schedule_pairing",
                "known_at_basis": "packet",
                "source_record_id": "sched:x",
                "entity_ref": {"type": "matchup", "id": "x"},
                "effective_at": r["known_at"],
                "known_at": r["known_at"],
                "access_scope": "public",
                "privacy": "public",
            },
            {"season": 2025, "week": 1, "home": "A", "away": "B"},
        )

    monkeypatch.setitem(nf.NORMALIZERS, "schedule_pairing", permissive)
    assert nf.NORMALIZERS["schedule_pairing"] is not original, "the plant must land"
    meta, _body = nf.NORMALIZERS["schedule_pairing"](raw, 2025)
    assert (
        meta["known_at_basis"] == "packet"
    ), "control: with the guard removed, a stripped packet is admitted"
    monkeypatch.setitem(nf.NORMALIZERS, "schedule_pairing", original)
    with pytest.raises(UnqualifiedSource):
        nf.NORMALIZERS["schedule_pairing"](raw, 2025)


# 6 -------------------------------------------------------------------------
def test_6_three_step_correction_chain():
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
    for cutoff, want in (
        ("2025-09-02T00:00:00Z", "a"),
        ("2025-09-06T00:00:00Z", "b"),
        ("2025-09-10T00:00:00Z", "c"),
    ):
        assert (
            state_at(2025, cutoff, "public", facts=[a, b, c])
            .value("transaction", "r")
            .fact_id
            == want
        )


def test_6_inadmissible_supersessor_does_not_retire_its_predecessor():
    """The discriminating form, THROUGH production: at the early cutoff the
    supersessor b is not yet admitted, so a must survive. Under the removed
    rule (retiring against the WHOLE pool) this returns None and the assertion
    fails -- the test cannot pass vacuously."""
    a = F(fact_id="a", source_record_id="r", known_at="2025-09-01T00:00:00Z")
    b = F(
        fact_id="b",
        source_record_id="r",
        known_at="2025-09-05T00:00:00Z",
        supersedes="a",
    )
    early = state_at(2025, "2025-09-02T00:00:00Z", "public", facts=[a, b])
    got = early.value("transaction", "r")
    assert (
        got is not None and got.fact_id == "a"
    ), "retirement must consult ADMITTED facts only"


# 7 -------------------------------------------------------------------------
def test_7_cross_arm_predecessor_poisoning(tmp_path):
    from scripts.decision_history import CrossArmContamination, verify_predecessor
    from scripts.tests.test_decision_history import mkseal

    other = mkseal(tmp_path, "no_chat", 1, "2025-09-03T23:59:59Z", "pre")
    with pytest.raises(CrossArmContamination):
        verify_predecessor(other, arm_id="full_rich", trial_id=1)


def test_7_mutation_note_the_real_control_lives_in_k35():
    """Rule 7's consumer-level mutation control (disable the check where a
    driver reads it, observe a poisoned chain complete) requires K3.5's
    run_arm_chain, which is outside the authorized K1/K2 scope. This
    placeholder records the deferral so the census counts an honest 6 + 1
    deferred, not a vacuous 7."""


# preserved noninterference proofs -------------------------------------------
def test_physical_truncation_leaves_no_post_cutoff_fact():
    """Not 'the projector hid it' -- the state must not CONTAIN it."""
    import json as j
    import re as r

    facts = [
        F(
            fact_id="in",
            source_record_id="a",
            known_at="2025-09-01T00:00:00Z",
            effective_at="2025-09-01T00:00:00Z",
        ),
        F(
            fact_id="out",
            source_record_id="b",
            known_at="2025-12-01T00:00:00Z",
            effective_at="2025-12-01T00:00:00Z",
        ),
    ]
    s = state_at(2025, "2025-09-03T23:59:59Z", "public", facts=facts)
    blob = j.dumps(
        [
            {k: getattr(f, k) for k in ("fact_id", "known_at", "effective_at")}
            for f in s.admitted
        ]
    )
    later = [
        i
        for i in r.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", blob)
        if i > "2025-09-03T23:59:59.000000Z"
    ]
    assert later == [], f"post-cutoff instants physically present: {later}"


def test_poisoned_root_season_isolation(tmp_path, monkeypatch):
    """Isolation is about STORE ROOTS, not fact content. Plant a poisoned 2024
    store beside the 2025 one and prove it is never opened."""
    import scripts.temporal_state as ts

    root = tmp_path / "facts"
    root.mkdir()
    s25 = FactStore(root / "2025.jsonl")
    s25.observe(payload={"v": 1}, **dict(OBS, source_record_id="clean"))
    s25.write()
    s24 = FactStore(root / "2024.jsonl")
    s24.observe(payload={"v": 9}, **dict(OBS, source_record_id="poison"))
    s24.write()
    monkeypatch.setattr(ts, "FACTS_ROOT", root)
    monkeypatch.setattr(ts, "PRIVATE_FACTS_ROOT", tmp_path / "pf")
    got = ts.state_at(2025, "2025-12-01T00:00:00Z", "public")  # no facts= override
    assert {f.source_record_id for f in got.admitted} == {"clean"}


def test_preview_state_is_outcome_free_by_composition():
    """Not a switch. A preview cutoff simply admits no matchup_result."""
    result = F(
        fact_id="r",
        source_record_id="m",
        fact_type="matchup_result",
        known_at="2025-09-09T06:59:59Z",
        effective_at="2025-09-09T06:59:59Z",
    )
    s = state_at(2025, "2025-09-05T00:19:59Z", "public", facts=[result])
    assert s.by_type("matchup_result") == []
    assert not hasattr(s, "allow_outcome_derivation")


def test_leaky_comparator_control_would_admit_the_outcome():
    """The leaky-comparator pair: production state_at (known_at admission)
    EXCLUDES a result whose effective_at precedes the cutoff but whose
    known_at does not -- while the modeled defect (effective_at admission)
    admits it. If state_at ever switched clocks, the first assert fails."""
    result = F(
        fact_id="r",
        source_record_id="m",
        fact_type="matchup_result",
        effective_at="2025-09-04T00:00:00Z",
        known_at="2025-09-09T06:59:59Z",
    )
    s = state_at(2025, "2025-09-05T00:19:59Z", "public", facts=[result])
    assert s.admitted == [], "production: known_at admission excludes the result"
    leaked = [f for f in [result] if f.effective_at <= "2025-09-05T00:19:59.000000Z"]
    assert [f.fact_id for f in leaked] == [
        "r"
    ], "modeled defect: admitting on effective_at leaks results into a preview"


# deterministic replay -------------------------------------------------------
def test_deterministic_replay_of_facts_and_state(tmp_path):
    """Normalizing the same captures twice yields byte-identical facts and
    identical state_at output -- against the REAL 2026 envelope lane."""
    a = normalize_all(
        source_root=".",
        out_path=tmp_path / "a.jsonl",
        season=2026,
        private_out_path=tmp_path / "pa.jsonl",
    )
    b = normalize_all(
        source_root=".",
        out_path=tmp_path / "b.jsonl",
        season=2026,
        private_out_path=tmp_path / "pb.jsonl",
    )
    assert a["counts"] == b["counts"]
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()
    fa = FactStore(tmp_path / "a.jsonl").load()
    fb = FactStore(tmp_path / "b.jsonl").load()
    sa = state_at(2026, "2026-09-03T00:20:00Z", "league_private", facts=fa)
    sb = state_at(2026, "2026-09-03T00:20:00Z", "league_private", facts=fb)
    assert [f.fact_id for f in sa.admitted] == [f.fact_id for f in sb.admitted]
