"""External-rebuild driver tests (2e / 2f-real / 2h / 2d-isolation / Gate-2).

These run the full chat DAG as subprocesses and need the gitignored private chat
inputs, so they SKIP on a fresh CI checkout and run only locally (Gate 2). The
fast provenance unit tests live in test_generate_chat_provenance.py.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_chat_provenance as prov  # noqa: E402
from shared import month_key_strict  # noqa: E402

REPO = prov.SOURCE_ROOT
SCRIPT = REPO / "scripts" / "generate_chat_provenance.py"
_PRIVATE = prov.CHAT_TXT_PATH.exists() and prov.PARSED_MESSAGES_PATH.exists()
pytestmark = pytest.mark.skipif(
    not _PRIVATE, reason="needs gitignored private chat inputs (local only)"
)

ROSTER_SLUGS = [
    "ben-chodos",
    "brent-boone",
    "david-hamburger",
    "harlow",
    "karim",
    "kevin-noble",
    "matt-russell",
    "neo",
    "oscar",
    "patrick-raue",
    "sacko",
    "zach",
]
SNAP_SUBS = ("chat", "content/chat", "content/weeks", "content/preseason-2025")


def _run(args, output_root, extra_env=None):
    env = dict(
        os.environ, JAILYARD_OUTPUT_ROOT=str(output_root), PYTHONDONTWRITEBYTECODE="1"
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )


def _snap(root, subs=SNAP_SUBS):
    root = Path(root)
    h = {}
    for sub in subs:
        d = root / sub
        if d.exists():
            for p in sorted(d.rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                    h[p.relative_to(root).as_posix()] = (
                        "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
                    )
    return h


def _independent_expected_paths():
    """Expected generated path set, declared from the CANONICAL repo corpus +
    roster -- INDEPENDENT of candidate builds A/B (catches a shared omission)."""
    parsed = json.loads(prov.PARSED_MESSAGES_PATH.read_text(encoding="utf-8"))
    msgs = parsed if isinstance(parsed, list) else parsed.get("messages", parsed)
    months = sorted({month_key_strict(m["timestamp_utc"]) for m in msgs})
    paths = {"chat/parsed_messages.json", "chat/identity_chain.json"}
    for n in (
        "arcs",
        "consensus",
        "fingerprints",
        "league-memory",
        "predictions",
        "relationships",
    ):
        paths.add(f"content/chat/{n}.json")
    for mo in months:
        paths.add(f"content/chat/.map_cache/{mo}_raw.json")
        paths.add(f"content/chat/.map_cache/{mo}.json")
    for s in ROSTER_SLUGS:
        paths.add(f"content/chat/personas/{s}.md")
    for w in range(1, 19):
        paths.add(f"content/weeks/week{w}_chat_context.json")
    paths.add("content/preseason-2025/preseason_chat_context.json")
    return paths


@pytest.fixture(scope="module")
def candidate(tmp_path_factory):
    """One full rebuild (explicit PYTHONHASHSEED=0) shared across the read-only
    assertions (2e/2f/2h) and as determinism seed A."""
    out = tmp_path_factory.mktemp("cand")
    receipt = out / "receipt.json"
    repo_before = _snap(REPO)
    r = _run(
        ["--rebuild-check", "--receipt", str(receipt)], out, {"PYTHONHASHSEED": "0"}
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert receipt.exists()
    assert _snap(REPO) == repo_before, "rebuild mutated the repo"
    return out, receipt


# --- 2e / 2f-real / 2h (reuse the shared candidate) ------------------------- #


def test_rebuild_matches_independent_inventory(candidate):
    out, _ = candidate
    assert set(_snap(out)) == _independent_expected_paths()


def test_receipt_bound_write_and_verify(candidate):
    out, receipt = candidate
    manifest = out / "provenance.json"
    assert (
        _run(
            ["--write", "--receipt", str(receipt), "--manifest", str(manifest)], out
        ).returncode
        == 0
    )
    assert _run(["--verify", "--manifest", str(manifest)], out).returncode == 0
    text = manifest.read_text(encoding="utf-8")
    assert prov.normalized_source_root() not in text  # portable: no absolute path
    assert "authorization" not in json.loads(text)


def test_verify_public_private_absent_and_tamper(candidate, tmp_path):
    out, receipt = candidate
    pub = tmp_path / "pub"
    shutil.copytree(out, pub)
    manifest = pub / "provenance.json"
    assert (
        _run(
            ["--write", "--receipt", str(receipt), "--manifest", str(manifest)], pub
        ).returncode
        == 0
    )
    shutil.rmtree(pub / "chat")  # private raw + derived intermediates GONE
    assert _run(["--verify-public", "--manifest", str(manifest)], pub).returncode == 0
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["code"][next(iter(data["code"]))] = "sha256:" + "0" * 64
    manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    assert _run(["--verify-public", "--manifest", str(manifest)], pub).returncode != 0


def test_portability_different_checkout_root(candidate, tmp_path):
    out, receipt = candidate
    m = tmp_path / "mirror"
    shutil.copytree(out, m)  # derived
    shutil.copytree(REPO / "scripts", m / "scripts")  # code
    (m / "chat").mkdir(exist_ok=True)
    shutil.copy2(REPO / "chat" / "_chat.txt", m / "chat" / "_chat.txt")
    (m / "content" / "chat").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPO / "content" / "chat" / "name-map.json",
        m / "content" / "chat" / "name-map.json",
    )
    (m / "content" / "weeks").mkdir(parents=True, exist_ok=True)
    for w in range(1, 19):
        shutil.copy2(
            REPO / "content" / "weeks" / f"week{w}_data.json",
            m / "content" / "weeks" / f"week{w}_data.json",
        )
    manifest = m / "content" / "chat" / "provenance.json"
    # Write the PORTABLE manifest from the CANDIDATE (OUTPUT_ROOT=out), placed at m.
    assert (
        _run(
            ["--write", "--receipt", str(receipt), "--manifest", str(manifest)], out
        ).returncode
        == 0
    )
    mscript = m / "scripts" / "generate_chat_provenance.py"

    def mrun(*args):
        env = dict(os.environ, JAILYARD_OUTPUT_ROOT=str(m), PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, "-B", str(mscript), *args, "--manifest", str(manifest)],
            cwd=m,
            env=env,
            capture_output=True,
            text=True,
        )

    assert mrun("--verify").returncode == 0
    shutil.rmtree(m / "chat")
    assert mrun("--verify-public").returncode == 0


# --- Determinism #1 (item 4): two EXPLICIT seeds + positive REDUCE detector -- #


def test_determinism_two_seeds_pathset_then_bytes(
    candidate, tmp_path_factory, monkeypatch
):
    """paths(A)==paths(B)==independent_expected, THEN raw bytes, across two DISTINCT
    explicit PYTHONHASHSEED in separate processes. Build B via run_rebuild so its
    dict doubles as the stale-MAP positive control (reduce_invoked=True)."""
    seed_a, seed_b = "0", "1"  # A = candidate (seed 0); B built here (seed 1)
    outA, _ = candidate
    outB = tmp_path_factory.mktemp("candB")
    monkeypatch.setenv("PYTHONHASHSEED", seed_b)
    resB = prov.run_rebuild(outB)
    assert (
        resB["completed"] is True and resB["reduce_invoked"] is True
    )  # positive control
    snapA, snapB, expected = _snap(outA), _snap(outB), _independent_expected_paths()
    assert set(snapA) == expected, sorted(set(snapA) ^ expected)
    assert set(snapB) == expected, sorted(set(snapB) ^ expected)
    diffs = [k for k in expected if snapA[k] != snapB[k]]
    assert (
        not diffs
    ), f"nondeterministic bytes (seeds {seed_a} vs {seed_b}): {diffs[:10]}"


# --- Stale-MAP (item 4): real driver + test-only detector -------------------- #


def _corrupt_one_raw(output_root):
    d = Path(output_root) / "content" / "chat" / ".map_cache"
    sorted(d.glob("*_raw.json"))[0].write_text("{ not valid json", encoding="utf-8")


def test_stale_map_detector_and_nonzero_exit(tmp_path, monkeypatch):
    """Inject a MAP-stage failure after a successful split. TEST-ONLY detector
    (run_rebuild dict) shows REDUCE not observed + analytics absent + exit_code!=0,
    AND the real cmd_rebuild_check driver returns a nonzero exit."""
    out = tmp_path / "cand"
    res = prov.run_rebuild(out, test_hooks={"split_chat_months": _corrupt_one_raw})
    assert res["completed"] is False
    assert res["reduce_invoked"] is False
    assert res["failed_stage"] == "map_chat_deterministic"
    assert res["exit_code"] != 0
    assert "content/chat/arcs.json" not in res["produced_paths"]  # analytics absent
    assert not (out / "content" / "chat" / "arcs.json").exists()
    # actual nonzero exit THROUGH the driver (OUTPUT_ROOT monkeypatched external).
    outB = tmp_path / "cand2"
    monkeypatch.setattr(prov, "OUTPUT_ROOT", outB)
    rc = prov.cmd_rebuild_check(
        tmp_path / "r.json", test_hooks={"split_chat_months": _corrupt_one_raw}
    )
    assert rc != 0


# --- 2d isolation (item 1): discriminating two-root poison-diff -------------- #


def _mirror_source(dst, poison=False):
    """A SOURCE/code mirror. `poison` also plants WRONG canonical-layout derived
    files: if any stage reads them, the candidate build would differ."""
    shutil.copytree(REPO / "scripts", dst / "scripts")
    (dst / "chat").mkdir(parents=True)
    shutil.copy2(REPO / "chat" / "_chat.txt", dst / "chat" / "_chat.txt")
    (dst / "content" / "chat").mkdir(parents=True)
    shutil.copy2(
        REPO / "content" / "chat" / "name-map.json",
        dst / "content" / "chat" / "name-map.json",
    )
    (dst / "content" / "weeks").mkdir(parents=True)
    for w in range(1, 19):
        shutil.copy2(
            REPO / "content" / "weeks" / f"week{w}_data.json",
            dst / "content" / "weeks" / f"week{w}_data.json",
        )
    if poison:
        (dst / "chat" / "parsed_messages.json").write_text(
            '{"messages":[{"sender":"X","text":"POISON","timestamp_utc":"2099-01-01T00:00:00Z",'
            '"is_system":false,"is_poll":false,"media":[]}]}',
            encoding="utf-8",
        )
        (dst / "chat" / "identity_chain.json").write_text(
            '{"by_roster_id":{}}', encoding="utf-8"
        )
        for n in (
            "arcs",
            "consensus",
            "fingerprints",
            "league-memory",
            "predictions",
            "relationships",
        ):
            (dst / "content" / "chat" / f"{n}.json").write_text(
                '{"POISON":true}', encoding="utf-8"
            )
        (dst / "content" / "chat" / "personas").mkdir()
        for s in ROSTER_SLUGS:
            (dst / "content" / "chat" / "personas" / f"{s}.md").write_text(
                "# POISON", encoding="utf-8"
            )
        for w in range(1, 19):
            (dst / "content" / "weeks" / f"week{w}_chat_context.json").write_text(
                '{"POISON":true}', encoding="utf-8"
            )
        (dst / "content" / "preseason-2025").mkdir(parents=True)
        (dst / "content" / "preseason-2025" / "preseason_chat_context.json").write_text(
            '{"POISON":true}', encoding="utf-8"
        )
        # WRONG canonical .map_cache raw-chunks + MAP results: if any stage reads
        # SOURCE .map_cache (present->use) instead of the OUTPUT candidate's, the
        # build diverges. Valid-but-wrong JSON so a bad read wouldn't crash.
        mc = dst / "content" / "chat" / ".map_cache"
        mc.mkdir()
        parsed = json.loads(prov.PARSED_MESSAGES_PATH.read_text(encoding="utf-8"))
        pmsgs = parsed if isinstance(parsed, list) else parsed.get("messages", parsed)
        for mo in sorted({month_key_strict(m["timestamp_utc"]) for m in pmsgs}):
            (mc / f"{mo}_raw.json").write_text(
                '{"messages":[],"month":"1999-01"}', encoding="utf-8"
            )
            (mc / f"{mo}.json").write_text('{"POISON":true}', encoding="utf-8")


def _rebuild_from_mirror(mirror, out):
    mscript = mirror / "scripts" / "generate_chat_provenance.py"
    env = dict(os.environ, JAILYARD_OUTPUT_ROOT=str(out), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(mscript),
            "--rebuild-check",
            "--receipt",
            str(out / "receipt.json"),
        ],
        cwd=mirror,
        env=env,
        capture_output=True,
        text=True,
    )


def test_isolation_poison_diff(tmp_path):
    mc, mp = tmp_path / "clean_mirror", tmp_path / "poison_mirror"
    _mirror_source(mc, poison=False)
    _mirror_source(mp, poison=True)
    bc, bp = tmp_path / "cand_clean", tmp_path / "cand_poison"
    rc = _rebuild_from_mirror(mc, bc)
    assert rc.returncode == 0, rc.stdout + rc.stderr
    rp = _rebuild_from_mirror(mp, bp)
    assert rp.returncode == 0, rp.stdout + rp.stderr
    # Byte-identical candidates -> no stage read the mirror's canonical derived.
    assert _snap(bc) == _snap(bp)


# --- 2h detector (item 2): an EXTRA REAL output file is rejected -------------- #


def test_verify_public_rejects_extra_real_output_file(candidate, tmp_path):
    """An EXTRA real content/weeks/*_chat_context.json is caught by the _outputs
    set-guard -> --verify-public fails. (Binds the output SET, not a subset.)"""
    out, receipt = candidate
    ext = tmp_path / "ext"
    shutil.copytree(out, ext)
    manifest = ext / "provenance.json"
    assert (
        _run(
            ["--write", "--receipt", str(receipt), "--manifest", str(manifest)], out
        ).returncode
        == 0
    )
    shutil.rmtree(ext / "chat")  # private absent (public)
    (ext / "content" / "weeks" / "week99_chat_context.json").write_text(
        '{"x":1}', encoding="utf-8"
    )
    assert _run(["--verify-public", "--manifest", str(manifest)], ext).returncode != 0
