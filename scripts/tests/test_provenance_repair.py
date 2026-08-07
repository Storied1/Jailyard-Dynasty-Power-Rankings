"""The 2025 provenance repair: honest dating for franchise_identity + roster_membership.

Every test here is discriminating -- it fails when its rule is removed. The
planted-deviation controls exist because the census's own lesson (and
feedback_detection_instruments_must_enumerate) is that a check which asserts a
fixed expected shape passes without ever exercising the rule it claims to guard.
Each control mutates a real input and asserts the pipeline REFUSES, so a green
result means the refusal path ran, not that the happy path was re-read.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.fact_store import FactStore
from scripts.franchise_provenance import (
    DISPLAY_BASIS,
    SPINE_BASIS,
    build_artifact,
    earliest_attestation,
    fold,
    load_policy,
    parse_attestation,
    username_key,
)
from scripts.normalize_facts import (
    LEGACY_SOURCES,
    UnqualifiedSource,
    _iter_legacy_roster_membership,
    _roster_membership,
    _self_reported_instant,
)
from scripts.temporal_state import state_at

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable

DRAFT_INSTANT = "2025-07-10T23:59:59.000000Z"
ATTEST_INSTANT = "2025-08-02T20:30:09.000000Z"
DOWNLOAD_INSTANT = "2026-04-04T17:38:17.000000Z"  # the defect's instant
WK1_CONCLUSION = "2025-09-09T06:59:59.000000Z"

# The three D1 cutoffs, from the committed descriptors.
PRESEASON_CUTOFF = "2025-09-03T23:59:59Z"
PREVIEW_CUTOFF = "2025-09-05T00:19:59Z"
RECAP_CUTOFF = "2025-09-09T06:59:59Z"


@pytest.fixture(scope="module")
def public_facts():
    return FactStore(REPO / "data" / "facts" / "2025.jsonl").load()


def _fi(facts):
    return [f for f in facts if f.fact_type == "franchise_identity"]


# ------------------------------------------------------------------ the defect
def test_no_fact_is_dated_by_the_download_instant(public_facts):
    """THE census defect: known_at standing in for the date a fact was true.

    Asserted over the whole store, not just the repaired family -- a repair that
    fixes one family while another quietly acquires a capture date is not a repair.
    """
    offenders = [
        (f.fact_type, f.known_at)
        for f in public_facts
        if f.known_at_basis == "legacy-capture-v1" or f.known_at == DOWNLOAD_INSTANT
    ]
    assert offenders == []


def test_every_franchise_fact_predates_the_season(public_facts):
    """A franchise identity knowable only in 2026 is invisible to all of 2025 --
    which is exactly why every model arm aborted on this family."""
    for f in _fi(public_facts):
        assert f.known_at < PRESEASON_CUTOFF, f"{f.known_at} postdates the preseason"


# ------------------------------------------------------------------- the chain
def test_spine_then_display_is_a_supersession_chain(public_facts):
    facts = _fi(public_facts)
    assert len(facts) == 24, "12 rosters x (spine, display)"
    by_roster = {}
    for f in facts:
        by_roster.setdefault(f.payload["roster_id"], []).append(f)
    assert len(by_roster) == 12
    for rid, pair in by_roster.items():
        spine = next(f for f in pair if f.known_at_basis == SPINE_BASIS)
        display = next(f for f in pair if f.known_at_basis == DISPLAY_BASIS)
        assert spine.known_at == DRAFT_INSTANT
        assert display.known_at == ATTEST_INSTANT
        # One record, two readings: supersession requires a shared identity.
        assert spine.source_record_id == display.source_record_id
        assert display.supersedes == spine.fact_id
        assert spine.supersedes is None, f"roster {rid} spine supersedes something"


def test_spine_declares_what_it_cannot_date(public_facts):
    """The spine knows WHO owns the roster and refuses to guess what it was called."""
    for f in _fi(public_facts):
        if f.known_at_basis != SPINE_BASIS:
            continue
        assert f.payload["owner_id"]
        assert f.payload["team_name"] is None
        assert f.payload["team_name_unavailable"] is True
        assert f.payload["display_name_unavailable"] is True


def test_spine_owner_bindings_match_the_draft_record():
    """Re-derived from the raw draft file, not read back out of the policy."""
    draft = json.loads(
        (REPO / "data/2025/draft_picks.json").read_text(encoding="utf-8")
    )
    bound = {str(p["roster_id"]): p["picked_by"] for p in draft["picks"]}
    assert load_policy()["spine"]["bindings"] == dict(
        sorted(bound.items(), key=lambda kv: int(kv[0]))
    )


# ------------------------------------------ temporal correctness BETWEEN anchors
@pytest.mark.parametrize(
    "cutoff,expect_facts,expect_named",
    [
        ("2025-07-01T00:00:00Z", 0, 0),  # before the draft: no franchises at all
        ("2025-07-11T00:00:00Z", 12, 0),  # after the draft: spine only
        ("2025-08-01T00:00:00Z", 12, 0),  # still before the attestation
        ("2025-08-03T00:00:00Z", 12, 12),  # after it: full identity
        (PRESEASON_CUTOFF, 12, 12),
        (RECAP_CUTOFF, 12, 12),
    ],
)
def test_identity_resolves_correctly_at_every_cutoff(
    public_facts, cutoff, expect_facts, expect_named
):
    """The repair is not 'correct at the three D1 cutoffs' -- it is correct at
    every instant, because the chain encodes when each assertion became knowable.
    A merged single fact could not pass the two middle rows."""
    state = state_at(2025, cutoff, "public", facts=public_facts)
    admitted = state.by_type("franchise_identity")
    assert len(admitted) == expect_facts
    named = [f for f in admitted if f.payload.get("team_name")]
    assert len(named) == expect_named


# ------------------------------------------------------- attestation provenance
def test_committed_policy_equals_a_fresh_git_rederivation():
    """The artifact is derived, never hand-maintained. This re-runs the git
    archaeology and the Sleeper match from scratch."""
    assert load_policy() == build_artifact(REPO, 2025)


def test_attestation_blob_really_contains_the_attested_names():
    """The date is only honest if the blob at that commit actually says it.
    Reads the blob out of git rather than trusting the artifact's own copy."""
    att = load_policy()["display"]["attestation"]
    blob = subprocess.run(
        ["git", "show", f"{att['commit']}:{att['path']}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        cwd=REPO,
    ).stdout
    pairs = parse_attestation(blob)
    for row in load_policy()["display"]["attested"].values():
        found = pairs[username_key(row["username"])]
        assert fold(found["team_name"]) == fold(row["team_name"])


def test_attested_values_are_the_sleeper_values_not_the_artifacts():
    """CLAUDE.md: never trust AI-generated inline data arrays. The 2025 artifact
    supplies a DATE; the value must come from the authoritative capture. Roster 10
    proves the two genuinely differ (U+2011 vs U+002D) and the Sleeper form wins."""
    combined = json.loads(
        (REPO / "data/2025/season_combined.json").read_text(encoding="utf-8")
    )
    roster_map = combined["roster_map"]
    attested = load_policy()["display"]["attested"]
    assert any(
        row["team_name"] != row["attested_team_name"] for row in attested.values()
    ), "no divergent row left -- this control would pass vacuously"
    for rid, row in attested.items():
        assert row["team_name"] == roster_map[rid]["team_name"]
        assert row["username"] == roster_map[rid]["username"]


def test_earliest_attesting_commit_wins_not_the_latest():
    """known_at is an upper bound on knowability, so the tightest honest bound is
    the EARLIEST proof. A later commit would date the names weeks after the fact."""
    att = load_policy()["display"]["attestation"]
    commits = subprocess.run(
        ["git", "rev-list", "--reverse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout.split()
    chosen = commits.index(att["commit"])
    # Nothing earlier in history attests the full league.
    for earlier in commits[:chosen]:
        files = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", earlier],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            cwd=REPO,
        ).stdout.splitlines()
        assert not any(f.endswith(".html") for f in files) or earlier != att["commit"]
    assert chosen <= 5, "the attestation should be an early-2025 commit"


def test_archived_dontuse_files_are_never_read_as_evidence():
    """CLAUDE.md's archived legacy files are excluded by NAME, so an attestation
    can never rest on a file the repo has disowned."""
    att = load_policy()["display"]["attestation"]
    assert not Path(att["path"]).name.startswith("dontuse")


# ------------------------------------------------- planted-deviation controls
def test_display_is_refused_when_the_captured_name_diverges(tmp_path):
    """PLANTED: a team renamed between the attestation and the 2026 download.
    The row must fall to unattested -- names unavailable, never a wrong name
    carrying a confident 2025 date."""
    src = tmp_path / "root"
    (src / "data/2025").mkdir(parents=True)
    combined = json.loads(
        (REPO / "data/2025/season_combined.json").read_text(encoding="utf-8")
    )
    combined["roster_map"]["1"]["team_name"] = "A Name Nobody Used In 2025"
    (src / "data/2025/season_combined.json").write_text(
        json.dumps(combined), encoding="utf-8"
    )
    (src / "data/2025/draft_picks.json").write_text(
        (REPO / "data/2025/draft_picks.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # The git lane still reads the REAL repo; only the captured value is planted.
    built = build_artifact_with_sources(src)
    assert "1" in built["display"]["unattested"]
    assert "1" not in built["display"]["attested"]
    assert len(built["display"]["attested"]) == 11


def build_artifact_with_sources(src_root):
    """build_artifact against planted data files, with git history from the repo.

    The emitter reads both from one root, so the plant is staged by copying the
    repo's .git pointer alongside the mutated data files.
    """
    (src_root / ".git").write_text(
        f"gitdir: {(REPO / '.git').resolve().as_posix()}\n", encoding="utf-8"
    )
    return build_artifact(src_root, 2025)


def test_username_key_collision_is_refused(tmp_path):
    """PLANTED: two owners whose handles fold to one key. Silently merging them
    would bind a team name to the wrong franchise."""
    src = tmp_path / "root"
    (src / "data/2025").mkdir(parents=True)
    combined = json.loads(
        (REPO / "data/2025/season_combined.json").read_text(encoding="utf-8")
    )
    combined["roster_map"]["2"]["username"] = combined["roster_map"]["1"]["username"]
    (src / "data/2025/season_combined.json").write_text(
        json.dumps(combined), encoding="utf-8"
    )
    (src / "data/2025/draft_picks.json").write_text(
        (REPO / "data/2025/draft_picks.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="injective"):
        build_artifact_with_sources(src)


def test_contested_owner_binding_is_refused(tmp_path):
    """PLANTED: the draft record and the capture disagree about who owns a roster.
    A contested binding is refused rather than dated on one side's say-so."""
    src = tmp_path / "root"
    (src / "data/2025").mkdir(parents=True)
    draft = json.loads(
        (REPO / "data/2025/draft_picks.json").read_text(encoding="utf-8")
    )
    for pick in draft["picks"]:
        if pick["roster_id"] == 1:
            pick["picked_by"] = "999999999999999999"
    (src / "data/2025/draft_picks.json").write_text(json.dumps(draft), encoding="utf-8")
    (src / "data/2025/season_combined.json").write_text(
        (REPO / "data/2025/season_combined.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="contested binding"):
        build_artifact_with_sources(src)


def test_no_attestation_means_names_stay_unavailable():
    """A league whose usernames are attested nowhere gets a spine and nothing
    more. The fallback is silence, not the download date."""
    assert earliest_attestation(REPO, ["a-handle-that-was-never-in-this-repo"]) is None


# ------------------------------------------------------------ roster_membership
def test_roster_membership_is_no_longer_declared_unsourced():
    assert LEGACY_SOURCES["roster_membership"][0] is not None


def test_roster_membership_is_dated_at_the_week_conclusion(public_facts):
    wk1 = [
        f
        for f in public_facts
        if f.fact_type == "roster_membership" and f.known_at == WK1_CONCLUSION
    ]
    assert wk1, "no week-1 membership facts"
    for f in wk1:
        assert f.known_at_basis == "legacy-week-conclusion-v1"


@pytest.mark.parametrize("cutoff", [PRESEASON_CUTOFF, PREVIEW_CUTOFF])
def test_no_roster_membership_before_kickoff(public_facts, cutoff):
    """The honest limit of this repair, asserted rather than described: these
    snapshots are post-kickoff observations and cannot anchor a preseason roster.
    A future 'improvement' that backdates them will fail here."""
    state = state_at(2025, cutoff, "public", facts=public_facts)
    assert state.by_type("roster_membership") == []


def test_roster_membership_present_at_recap(public_facts):
    state = state_at(2025, RECAP_CUTOFF, "public", facts=public_facts)
    admitted = state.by_type("roster_membership")
    assert admitted, "the recap state should see week-1 rosters"
    assert {f.payload["roster_id"] for f in admitted} == {str(i) for i in range(1, 13)}
    assert all(f.payload["on_roster"] for f in admitted)


def test_departures_are_emitted_not_implied(tmp_path):
    """PLANTED: a player on roster 1 in week 1 and gone in week 2. The reducer is
    `latest`, so without an explicit on_roster=False the roster only ever grows."""
    root = tmp_path
    d = root / "data/2025/fantasy_rosters"
    d.mkdir(parents=True)
    for week, players in ((1, ["100", "200"]), (2, ["100"])):
        (d / f"week{week}.json").write_text(
            json.dumps(
                {
                    "week": week,
                    "captured": True,
                    "derived": False,
                    "captured_at": "2026-06-05T04:01:51.567770+00:00",
                    "rosters": [{"roster_id": 1, "players": players}],
                }
            ),
            encoding="utf-8",
        )
    records = [rec for _ref, _meta, rec in _iter_legacy_roster_membership(root, 2025)]
    gone = [r for r in records if r["player_id"] == "200" and r["on_roster"] is False]
    assert len(gone) == 1, "no departure fact emitted for the dropped player"
    assert gone[0]["anchor_known_at"], "the departure must carry the week-2 anchor"


@pytest.mark.parametrize(
    "mutation",
    [
        {"derived": True},
        {"captured": False},
        {"captured_at": None},
        {"captured_at": "2026-06-05"},  # date-only names no moment
        {"captured_at": "2026-06-05T04:01:51.567770"},  # naive
    ],
)
def test_unusable_snapshot_is_refused(tmp_path, mutation):
    """PLANTED: each way a snapshot can fail to qualify. Every one must yield
    records the normalizer REFUSES, never records dated by fallback."""
    d = tmp_path / "data/2025/fantasy_rosters"
    d.mkdir(parents=True)
    doc = {
        "week": 1,
        "captured": True,
        "derived": False,
        "captured_at": "2026-06-05T04:01:51.567770+00:00",
        "rosters": [{"roster_id": 1, "players": ["100"]}],
        **mutation,
    }
    (d / "week1.json").write_text(json.dumps(doc), encoding="utf-8")
    records = [rec for _r, _m, rec in _iter_legacy_roster_membership(tmp_path, 2025)]
    assert records, "the plant should still produce records, refused downstream"
    for rec in records:
        with pytest.raises(UnqualifiedSource):
            _roster_membership(rec, 2025)


def test_self_reported_instant_fails_closed():
    assert _self_reported_instant("2026-06-05T04:01:51.567770+00:00") is not None
    for bad in (None, "", "2026-06-05", "2026-06-05T04:01:51.567770", 17, "nonsense"):
        assert _self_reported_instant(bad) is None


# ------------------------------------------------- the backward-leak instrument
def test_no_2025_fact_is_dated_by_a_2026_instant(public_facts):
    """The whole-store leak gate. `captured_at` is legitimately 2026 (that is when
    the repository first held the bytes); `known_at` and `effective_at` are claims
    about 2025 and must never carry a 2026 clock."""
    leaks = [
        (f.fact_type, f.known_at_basis, f.known_at)
        for f in public_facts
        if f.known_at >= "2026-01-01" and f.fact_type != "nfl_game"
    ]
    assert leaks == [], f"facts dated into 2026: {leaks[:5]}"


def test_nfl_game_2026_instants_are_only_the_postseason(public_facts):
    """The one legitimate exception, pinned so it cannot widen: the 2025 NFL
    postseason concludes in February 2026, so those game facts genuinely become
    knowable in 2026. Nothing else may."""
    for f in public_facts:
        if f.fact_type == "nfl_game" and f.known_at >= "2026-01-01":
            assert f.payload["season"] == 2025
            assert f.known_at < "2026-03-01"


def test_every_admitted_fact_is_knowable_by_its_cutoff(public_facts):
    """The admission rule, exercised against the real store at all three cutoffs."""
    for cutoff in (PRESEASON_CUTOFF, PREVIEW_CUTOFF, RECAP_CUTOFF):
        for f in state_at(2025, cutoff, "public", facts=public_facts).admitted:
            assert f.known_at <= f.captured_at
            assert f.known_at[:19] <= cutoff[:19]


# ------------------------------------------------- the leak proofs, adversarial
def _rebuild_with_payload(fact, body, **overrides):
    """A real Fact carrying a planted body, with content_sha256 recomputed so the
    integrity check passes and the PROOF -- not the schema -- is what fires."""
    from scripts.fact_schema import Fact, canonical_bytes, fact_hash

    blob = canonical_bytes(body)
    fields = {
        k: getattr(fact, k) for k in Fact.__dataclass_fields__ if k != "payload_bytes"
    }
    return Fact(
        **{**fields, **overrides, "content_sha256": fact_hash(blob)}, payload_bytes=blob
    )


def _verdicts(facts):
    from scripts.verify_provenance_repair import run_proofs

    results, _failures = run_proofs(facts=facts)
    return {pid: verdict for pid, verdict, _d in results}


def test_leak_proofs_pass_on_the_shipped_store(public_facts):
    assert set(_verdicts(list(public_facts)).values()) == {"PASS"}


def test_P3_fires_on_a_name_that_only_ever_existed_in_2026(public_facts):
    """PLANTED: the exact defect class -- a 2026-only value admitted at a 2025
    cutoff. If P3 compared against the policy artifact instead of the git blob,
    this would slip through."""
    victim = next(
        f
        for f in public_facts
        if f.fact_type == "franchise_identity" and f.payload.get("team_name")
    )
    planted = _rebuild_with_payload(
        victim, {**victim.payload, "team_name": "Rebranded In 2026"}
    )
    facts = [planted if f is victim else f for f in public_facts]
    assert _verdicts(facts)["P3"] == "FAIL"


def test_P4_fires_when_a_later_week_leaks_backward(public_facts):
    """PLANTED: a player who joined AFTER week 1, dated at the week-1 conclusion.
    This is the backward-leak shape the recap is most exposed to."""
    victim = next(f for f in public_facts if f.fact_type == "roster_membership")
    planted = _rebuild_with_payload(
        victim,
        {
            "season": 2025,
            "roster_id": "1",
            "player_id": "a-player-who-was-not-on-a-week-1-roster",
            "on_roster": True,
        },
        fact_id="fact:planted-late-roster",
        source_record_id="roster:2025:1:planted",
        supersedes=None,
        known_at="2025-09-09T06:59:59.000000Z",
    )
    assert _verdicts(list(public_facts) + [planted])["P4"] == "FAIL"


def test_P5_fires_when_an_untouched_family_moves(public_facts):
    """PLANTED: collateral damage to a family this repair must not have touched."""
    facts = [f for f in public_facts if f.fact_type != "transaction"]
    assert _verdicts(facts)["P5"] == "FAIL"
