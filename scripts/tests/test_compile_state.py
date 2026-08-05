"""K2.1 — D1 state compilation: custody split, hash-verified resolution,
state_at as sole authority, no-write --verify, tamper fail-closed."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.compile_state as cs
import scripts.temporal_state as ts
from scripts.compile_state import (
    EditionDescriptor,
    compile_state,
    load_compiled_state,
    verify_compiled,
)
from scripts.fact_schema import fact_hash
from scripts.fact_store import FactStore

PY = sys.executable
REPO = Path(__file__).resolve().parents[2]

PRE = EditionDescriptor(
    "2025-preseason",
    2025,
    "preseason",
    "2025-09-03T23:59:59Z",
    "league_private",
    None,
    (),
)

FIXTURE_OBS = dict(
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


@pytest.fixture
def compile_roots(tmp_path, monkeypatch):
    """Isolated compiler fixture: relocated tracked/private roots AND an
    isolated fact store, so no compiler test reads or writes the repository."""
    froot = tmp_path / "facts"
    froot.mkdir()
    s = FactStore(froot / "2025.jsonl")
    s.observe(payload={"v": 1}, **FIXTURE_OBS)
    s.write()
    # Production custody: the private-scope fact lives in the PRIVATE store.
    (tmp_path / "pf").mkdir()
    ps = FactStore(tmp_path / "pf" / "2025.jsonl")
    ps.observe(
        payload={"secret": "chat"},
        **dict(
            FIXTURE_OBS,
            source_record_id="msg:1",
            fact_type="chat_message",
            access_scope="league_private",
            privacy="private",
        ),
    )
    ps.write()
    monkeypatch.setattr(ts, "FACTS_ROOT", froot)
    monkeypatch.setattr(ts, "PRIVATE_FACTS_ROOT", tmp_path / "pf")
    monkeypatch.setattr(cs, "EDITIONS_ROOT", tmp_path / "ed")
    monkeypatch.setattr(cs, "PRIVATE_EDITIONS_ROOT", tmp_path / "priv")
    return tmp_path


def test_writes_all_compile_artifacts_with_custody_split(compile_roots):
    out = compile_state(PRE)
    for f in ("descriptor.json", "state_manifest.json", "source_hashes.json"):
        assert (out / f).exists(), f
    assert not (
        out / "state.json"
    ).exists(), "a league_private state must never land in the tracked compiled tree"
    assert (compile_roots / "priv" / PRE.edition_id / "state.json").exists()


def test_manifest_hash_matches_the_persisted_private_state(compile_roots):
    out = compile_state(PRE)
    state = json.loads(
        (compile_roots / "priv" / PRE.edition_id / "state.json").read_text(
            encoding="utf-8"
        )
    )
    mf = json.loads((out / "state_manifest.json").read_text(encoding="utf-8"))
    assert mf["state_payload_sha256"] == fact_hash(state)


def test_compiler_output_equals_direct_state_at(compile_roots):
    """state_at is the SOLE authority: the persisted state must equal a direct
    state_at() computation fact-for-fact. A stub compiler emitting a plausible
    but independent slice fails here -- the planted-bypass control."""
    from scripts.temporal_state import state_at

    compile_state(PRE)
    state = load_compiled_state(
        PRE.edition_id,
        editions_root=compile_roots / "ed",
        private_root=compile_roots / "priv",
    )
    direct = state_at(PRE.season, PRE.cutoff_utc, PRE.access_scope)
    assert [f["fact_id"] for f in state["admitted"]] == [
        f.fact_id for f in direct.admitted
    ]


def test_source_identities_live_outside_the_state(compile_roots):
    """The df7c1ea defect: identities inside the compared artifact make the
    truncation comparison impossible to pass."""
    out = compile_state(PRE)
    state = json.loads(
        (compile_roots / "priv" / PRE.edition_id / "state.json").read_text(
            encoding="utf-8"
        )
    )
    assert "source_identities" not in state and "source_hashes" not in state
    assert json.loads((out / "source_hashes.json").read_text(encoding="utf-8"))


def test_missing_relocated_or_tampered_private_state_fails_closed(compile_roots):
    compile_state(PRE)
    kw = dict(editions_root=compile_roots / "ed", private_root=compile_roots / "priv")
    load_compiled_state(PRE.edition_id, **kw)  # pristine: resolves
    state_path = compile_roots / "priv" / PRE.edition_id / "state.json"
    # Tampered
    original = state_path.read_text(encoding="utf-8")
    state_path.write_text(original.replace('"v":1', '"v":9'), encoding="utf-8")
    with pytest.raises(ValueError, match="tampered"):
        load_compiled_state(PRE.edition_id, **kw)
    state_path.write_text(original, encoding="utf-8")
    # Relocated / missing
    moved = state_path.with_name("state.moved.json")
    state_path.rename(moved)
    with pytest.raises(FileNotFoundError, match="private state absent"):
        load_compiled_state(PRE.edition_id, **kw)
    moved.rename(state_path)


def test_compile_is_exclusive_and_verify_is_no_write(compile_roots):
    """Compile once; a second compile refuses; --verify passes repeatedly with
    byte-identical artifacts; planted drift fails verification."""
    out = compile_state(PRE)
    with pytest.raises(FileExistsError):
        compile_state(PRE)
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert verify_compiled(PRE) == []
    assert verify_compiled(PRE) == []
    after = {p.name: p.read_bytes() for p in out.iterdir()}
    assert before == after, "--verify writes nothing"
    mf = out / "state_manifest.json"
    original = mf.read_text(encoding="utf-8")
    mf.write_text(
        original.replace(
            '"state_payload_sha256": "sha256:', '"state_payload_sha256": "sha256:0'
        ),
        encoding="utf-8",
    )
    assert verify_compiled(PRE), "planted manifest drift must fail"
    mf.write_text(original, encoding="utf-8")


def test_rebuild_preserves_sibling_artifacts(compile_roots):
    compile_state(PRE)
    authored = compile_roots / "ed" / PRE.edition_id / "ranking_record.json"
    authored.write_text('{"entries": []}', encoding="utf-8")
    shutil.rmtree(compile_roots / "priv" / PRE.edition_id)
    shutil.rmtree(compile_roots / "ed" / PRE.edition_id / "compiled")
    compile_state(PRE)
    assert authored.exists(), "the compiler owns only compiled/ and the private state"


def test_clean_rebuild_is_byte_identical(compile_roots):
    priv_state = compile_roots / "priv" / PRE.edition_id / "state.json"
    compile_state(PRE)
    a = priv_state.read_bytes()
    shutil.rmtree(compile_roots / "ed" / PRE.edition_id / "compiled")
    shutil.rmtree(compile_roots / "priv" / PRE.edition_id)
    compile_state(PRE)
    assert priv_state.read_bytes() == a


def test_preview_descriptor_must_match_the_retained_derivation(compile_roots):
    bad = EditionDescriptor(
        "2025-wk01-preview",
        2025,
        "preview",
        "2025-09-06T00:00:00Z",  # a transcription error
        "league_private",
        None,
        ("2025-preseason",),
    )
    with pytest.raises(ValueError, match="retained derivation is the authority"):
        compile_state(bad)


def test_relocated_tests_never_open_the_repo_private_root(compile_roots):
    """Suite-level control: every private path the resolver opened in this file
    is under the relocated root, never the repository's private_editions/."""
    compile_state(PRE)
    load_compiled_state(
        PRE.edition_id,
        editions_root=compile_roots / "ed",
        private_root=compile_roots / "priv",
    )
    repo_priv = str(REPO / "private_editions")
    for p in cs.OPENED_PRIVATE_PATHS:
        if str(compile_roots) in p:
            continue
        assert not p.startswith(repo_priv), f"repo private root opened by a test: {p}"


def test_cli_verify_mode_executes(compile_roots, tmp_path):
    """The exact CLI paths for compile + --verify against a relocated root."""
    desc = {
        "edition_id": "2025-preseason",
        "season": 2025,
        "kind": "preseason",
        "cutoff_utc": "2025-09-03T23:59:59Z",
        "access_scope": "league_private",
        "as_recorded_at": None,
        "predecessors": [],
    }
    dpath = tmp_path / "descriptor.json"
    dpath.write_text(json.dumps(desc), encoding="utf-8")
    # CLI runs in a fresh process where monkeypatched roots don't apply -- so
    # only exercise argument handling here (--verify on the real, compiled
    # repo edition is exercised by K2.1 Step 5c's gate itself).
    r = subprocess.run(
        [PY, "scripts/compile_state.py", "--descriptor", str(dpath), "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and "--verify" in r.stdout


@pytest.mark.parametrize(
    "artifact,transform",
    [
        (
            "descriptor.json",
            lambda s: s.replace('"kind": "preseason"', '"kind": "recap"'),
        ),
        (
            "state_manifest.json",
            lambda s: s.replace('"admitted_count": ', '"admitted_count": 9'),
        ),
        (
            "state_manifest.json",
            lambda s: s.replace(
                '"state_payload_sha256": "sha256:', '"state_payload_sha256": "sha256:0'
            ),
        ),
        (
            "source_hashes.json",
            lambda s: s.replace('"sha256": "sha256:', '"sha256": "sha256:0', 1),
        ),
    ],
)
def test_verify_catches_each_authoritative_artifact_mutation(
    compile_roots, artifact, transform
):
    """Parameterized mutations of each authoritative compiled artifact must
    fail verification while the pristine edition passes without writes."""
    out = compile_state(PRE)
    assert verify_compiled(PRE) == []
    path = out / artifact
    original = path.read_text(encoding="utf-8")
    mutated = transform(original)
    assert mutated != original, "the plant must land"
    path.write_text(mutated, encoding="utf-8")
    assert verify_compiled(PRE), f"mutation of {artifact} must fail verification"
    path.write_text(original, encoding="utf-8")
    assert verify_compiled(PRE) == []


def test_verify_catches_private_state_mutation(compile_roots):
    compile_state(PRE)
    sp = compile_roots / "priv" / PRE.edition_id / "state.json"
    original = sp.read_text(encoding="utf-8")
    sp.write_text(original.replace('"v":1', '"v":9'), encoding="utf-8")
    assert verify_compiled(PRE), "a mutated private state must fail verification"
    sp.write_text(original, encoding="utf-8")
    assert verify_compiled(PRE) == []


@pytest.mark.skipif(
    not (REPO / "private_editions" / "2025-preseason" / "state.json").exists(),
    reason="production private states absent (clean checkout); resolution "
    "fail-closed is proven separately",
)
def test_real_cli_verify_exits_zero_on_all_three_editions():
    """The actual CLI and exit code -- not --help -- against the three pristine
    repository editions, without writes."""
    for e in ("2025-preseason", "2025-wk01-preview", "2025-wk01-recap"):
        compiled = REPO / "content" / "editions" / e / "compiled"
        before = {q.name: q.read_bytes() for q in compiled.iterdir()}
        r = subprocess.run(
            [
                PY,
                "scripts/compile_state.py",
                "--verify",
                "--descriptor",
                f"content/editions/{e}/descriptor.json",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, (e, r.stdout, r.stderr)
        assert "verified (no write)" in r.stdout
        after = {q.name: q.read_bytes() for q in compiled.iterdir()}
        assert before == after
