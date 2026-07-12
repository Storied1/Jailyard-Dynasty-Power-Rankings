"""Corpus-INDEPENDENT --rebuild-check topology + instrument guards.

These reject BEFORE any rebuild (or mock run_rebuild), so they need NO private
chat inputs and therefore RUN IN FRESH CI -- unlike the private-gated full-rebuild
tier in test_chat_rebuild.py.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_chat_provenance as prov  # noqa: E402

REPO = prov.SOURCE_ROOT
SCRIPT = REPO / "scripts" / "generate_chat_provenance.py"


def _run(args, output_root):
    env = dict(
        os.environ, JAILYARD_OUTPUT_ROOT=str(output_root), PYTHONDONTWRITEBYTECODE="1"
    )
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )


# --- overlap / receipt-path / freshness (reject before any private read) ---- #


def test_requires_receipt():
    assert _run(["--rebuild-check"], REPO / "nope").returncode == 1


def test_rejects_output_root_equal_source():
    r = _run(["--rebuild-check", "--receipt", "x.json"], REPO)
    assert r.returncode == 1 and "SOURCE_ROOT" in (r.stdout + r.stderr)


def test_rejects_output_inside_source(tmp_path):
    r = _run(
        ["--rebuild-check", "--receipt", str(tmp_path / "r.json")],
        REPO / "inside_subdir",
    )
    assert r.returncode == 1 and "INSIDE" in (r.stdout + r.stderr)


def test_rejects_output_ancestor_of_source(tmp_path):
    r = _run(["--rebuild-check", "--receipt", str(tmp_path / "r.json")], REPO.parent)
    assert r.returncode == 1 and "ANCESTOR" in (r.stdout + r.stderr)


def _make_reentry_link(link, target):
    """symlink, or a Windows junction fallback (no admin needed)."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        return r.returncode == 0 and link.exists()
    return False


def test_rejects_symlink_or_junction_reentry(tmp_path):
    link = tmp_path / "reentry"
    if not _make_reentry_link(link, REPO / "chat"):
        pytest.skip("neither symlink nor junction could be created")
    r = _run(["--rebuild-check", "--receipt", str(tmp_path / "r.json")], link)
    assert r.returncode == 1  # resolves inside SOURCE_ROOT -> rejected


def test_rejects_nonfresh_output_root(tmp_path):
    out = tmp_path / "stale"
    (out / "content" / "chat").mkdir(parents=True)
    (out / "content" / "chat" / "arcs.json").write_text("{}", encoding="utf-8")
    r = _run(["--rebuild-check", "--receipt", str(tmp_path / "r.json")], out)
    assert r.returncode == 1 and "fresh" in (r.stdout + r.stderr)


def test_rejects_root_level_stale_file(tmp_path):
    # A ROOT-LEVEL extra (outside the 5 snapshot subtrees) must still fail freshness.
    out = tmp_path / "stale2"
    out.mkdir()
    (out / "stale.txt").write_text("x", encoding="utf-8")
    r = _run(["--rebuild-check", "--receipt", str(tmp_path / "r.json")], out)
    assert r.returncode == 1 and "fresh" in (r.stdout + r.stderr)


def test_rejects_receipt_inside_source(tmp_path):
    r = _run(
        ["--rebuild-check", "--receipt", str(REPO / "would_be_written.json")],
        tmp_path / "ext",
    )
    assert r.returncode == 1 and "inside SOURCE_ROOT" in (r.stdout + r.stderr)


# --- inventory over the WHOLE root (item 1): file/dir/type deviations -------- #


@pytest.mark.parametrize(
    "kind", ["extra-file", "missing-file", "root-level-file", "empty-dir"]
)
def test_inventory_mismatch_rejected_in_driver(tmp_path, monkeypatch, kind):
    """The driver rejects a candidate whose WHOLE-root entry set != expected --
    an extra file, a missing file, a ROOT-LEVEL file, or an empty unexpected DIR.
    run_rebuild is mocked (fast) but the real cmd_rebuild_check branch runs."""
    out = tmp_path / "cand"
    out.mkdir()
    monkeypatch.setattr(prov, "OUTPUT_ROOT", out)
    base = dict(prov.expected_generated_paths(out))  # {rel: 'file'|'dir'}
    produced = dict(base)
    if kind == "extra-file":
        produced["content/chat/EXTRA.json"] = "file"
    elif kind == "missing-file":
        produced.pop(next(k for k, v in base.items() if v == "file"))
    elif kind == "root-level-file":
        produced["stale.txt"] = "file"
    elif kind == "empty-dir":
        produced["weird_empty_dir"] = "dir"
    fake = {
        "completed": True,
        "failed_stage": None,
        "produced_paths": produced,
        "reduce_invoked": True,
        "exit_code": 0,
    }
    monkeypatch.setattr(prov, "run_rebuild", lambda *a, **k: fake)
    assert prov.cmd_rebuild_check(tmp_path / "r.json") == 1


# --- nonmutation instrument (item 3) ---------------------------------------- #


def test_code_surface_in_nonmutation_snapshot():
    """The nonmutation snapshot content-hashes scripts/*.py (dirs marked 'dir'),
    so a byte-change to an already-'M' tracked .py is caught."""
    snap = prov._fs_snapshot(REPO)
    assert "scripts/shared.py" in snap and snap["scripts/shared.py"].startswith(
        "sha256:"
    )
    # dirs are typed 'dir' (a file<->dir swap would flip the value and be caught).
    assert any(v == "dir" for v in snap.values())


def test_git_state_binds_index_content():
    """_git_state binds the staged index (blob shas), not just porcelain labels."""
    gs = prov._git_state(REPO)
    assert set(gs) >= {"head", "index"} and gs["index"]


def test_receipt_not_published_on_nonmutation_failure(tmp_path, monkeypatch):
    """A failed nonmutation proof publishes NO receipt and leaves a preexisting one
    byte-identical (temp -> replace only after the proof passes)."""
    out = tmp_path / "cand"
    out.mkdir()
    monkeypatch.setattr(prov, "OUTPUT_ROOT", out)
    monkeypatch.setattr(
        prov,
        "run_rebuild",
        lambda *a, **k: {
            "completed": True,
            "failed_stage": None,
            "produced_paths": prov.expected_generated_paths(out),
            "reduce_invoked": True,
            "exit_code": 0,
        },
    )
    monkeypatch.setattr(prov, "make_receipt", lambda errs: {"kind": "x", "payload": {}})
    monkeypatch.setattr(prov, "_fs_snapshot", lambda root: {})  # stable surfaces
    calls = {"n": 0}

    def fake_git(root):  # differs before vs after -> forces a nonmutation FAILURE
        calls["n"] += 1
        return {"head": "H", "index": f"idx{calls['n']}", "status": ""}

    monkeypatch.setattr(prov, "_git_state", fake_git)
    receipt_path = tmp_path / "r.json"
    receipt_path.write_text("SENTINEL", encoding="utf-8")  # preexisting
    assert prov.cmd_rebuild_check(receipt_path) == 1
    assert receipt_path.read_text(encoding="utf-8") == "SENTINEL"  # untouched
    assert not (tmp_path / "r.json.tmp").exists()  # no partial temp left behind


# --- A1: type-preserving, NON-FOLLOWING instrument schemas ------------------ #
# _fs_snapshot = kind + content-hash/link-target (nonmutation binding);
# _root_entries = kind ONLY, in the expected_generated_paths vocabulary, with
# link/reparse kinds distinguishable (=> always unexpected in the inventory).


def _file_symlink(link, target):
    try:
        link.symlink_to(target)
        return True
    except (OSError, NotImplementedError):
        return False


def _snapshot_tree(root):
    (root / "chat" / "sub").mkdir(parents=True)
    (root / "chat" / "sub" / "inner.txt").write_bytes(b"payload")
    (root / "chat" / "top.txt").write_bytes(b"top")


def test_fs_snapshot_identical_trees_control(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _snapshot_tree(a)
    _snapshot_tree(b)
    assert prov._fs_snapshot(a) == prov._fs_snapshot(b)


def test_fs_snapshot_detects_nested_file_to_symlink_swap(tmp_path):
    """Same-content file->symlink substitution (NESTED, not root-level) must
    change the nonmutation snapshot -- a following read_bytes() sees equal
    bytes and misses it."""
    a, b = tmp_path / "a", tmp_path / "b"
    _snapshot_tree(a)
    _snapshot_tree(b)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"payload")
    victim = b / "chat" / "sub" / "inner.txt"
    victim.unlink()
    if not _file_symlink(victim, outside):
        pytest.skip("file symlinks unavailable (no privilege / not supported)")
    assert prov._fs_snapshot(a) != prov._fs_snapshot(b)


def test_fs_snapshot_detects_nested_dir_to_link_swap(tmp_path):
    """Same-content dir->symlink/junction substitution (NESTED) must change the
    snapshot; a follower descends and sees identical contents."""
    a, b = tmp_path / "a", tmp_path / "b"
    _snapshot_tree(a)
    _snapshot_tree(b)
    clone = tmp_path / "clone_sub"
    shutil.copytree(b / "chat" / "sub", clone)
    shutil.rmtree(b / "chat" / "sub")
    if not _make_reentry_link(b / "chat" / "sub", clone):
        pytest.skip("neither symlink nor junction could be created")
    assert prov._fs_snapshot(a) != prov._fs_snapshot(b)


def test_root_entries_normal_inventory_control(tmp_path):
    """A valid all-regular candidate: kind-only values in EXACTLY the
    expected_generated_paths vocabulary, equal to the _with_dirs expansion."""
    root = tmp_path / "root"
    _snapshot_tree(root)
    entries = prov._root_entries(root)
    assert entries == prov._with_dirs({"chat/sub/inner.txt", "chat/top.txt"})
    assert set(entries.values()) <= {"file", "dir"}


def test_root_entries_distinguishes_file_symlink(tmp_path):
    root = tmp_path / "root"
    _snapshot_tree(root)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"payload")
    link = root / "chat" / "linked.txt"
    if not _file_symlink(link, outside):
        pytest.skip("file symlinks unavailable (no privilege / not supported)")
    entries = prov._root_entries(root)
    assert entries["chat/linked.txt"] not in ("file", "dir")


def test_root_entries_distinguishes_dir_link_and_never_descends(tmp_path):
    """A dir-shaped link is NOT 'dir' (so it can never satisfy an expected
    inventory) and its children are NEVER enumerated (no reparse descent)."""
    root = tmp_path / "root"
    _snapshot_tree(root)
    clone = tmp_path / "clone_sub"
    shutil.copytree(root / "chat" / "sub", clone)
    shutil.rmtree(root / "chat" / "sub")
    if not _make_reentry_link(root / "chat" / "sub", clone):
        pytest.skip("neither symlink nor junction could be created")
    entries = prov._root_entries(root)
    assert entries["chat/sub"] not in ("file", "dir")
    assert not any(k.startswith("chat/sub/") for k in entries)


# --- A2: _git_state binds exact WORKTREE content (types+bytes), not labels -- #
# Temp repos ONLY -- never the live repo. Hooks disabled (core.hooksPath ->
# nonexistent dir) so global pre-commit hooks can't fire inside tests.

_HAS_GIT = shutil.which("git") is not None
_needs_git = pytest.mark.skipif(not _HAS_GIT, reason="git not available")


def _init_repo(tmp_path):
    repo = tmp_path / "trepo"
    repo.mkdir()

    def g(*a):
        r = subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
        assert r.returncode == 0, f"git {a}: {r.stderr}"
        return r.stdout

    g("init", "-q")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    g("config", "core.hooksPath", str(repo / ".nohooks"))  # no global hooks
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "init", "--no-verify")
    return repo, g


@_needs_git
def test_git_state_happy_path_stable(tmp_path):
    """No change between calls -> identical state (an always-differ stub or a
    nondeterministic walk would fail here)."""
    repo, g = _init_repo(tmp_path)
    assert prov._git_state(repo) == prov._git_state(repo)


@_needs_git
def test_git_state_detects_restaged_blob(tmp_path):
    """(i) Replace + restage an already-staged blob: porcelain label stays the
    same but the staged content changed -> state must differ."""
    repo, g = _init_repo(tmp_path)
    (repo / "a.txt").write_text("staged-1\n", encoding="utf-8")
    g("add", "a.txt")
    s1 = prov._git_state(repo)
    (repo / "a.txt").write_text("staged-2\n", encoding="utf-8")
    g("add", "a.txt")
    s2 = prov._git_state(repo)
    assert s1 != s2


@_needs_git
def test_git_state_detects_rechanged_modified_worktree_file(tmp_path):
    """(ii) An already-' M' file changes AGAIN (unstaged): porcelain label and
    index blob both unchanged -> only exact worktree bytes can catch it."""
    repo, g = _init_repo(tmp_path)
    (repo / "a.txt").write_text("dirty-1\n", encoding="utf-8")  # now ' M'
    s1 = prov._git_state(repo)
    (repo / "a.txt").write_text("dirty-2\n", encoding="utf-8")  # still ' M'
    s2 = prov._git_state(repo)
    assert s1 != s2


@_needs_git
def test_git_state_detects_type_change(tmp_path):
    """(iii) A tracked path's filesystem object TYPE changes (file -> dir with
    same-name inner content): state must differ."""
    repo, g = _init_repo(tmp_path)
    s1 = prov._git_state(repo)
    (repo / "a.txt").unlink()
    (repo / "a.txt").mkdir()
    (repo / "a.txt" / "inner.txt").write_text("v1\n", encoding="utf-8")
    s2 = prov._git_state(repo)
    assert s1 != s2


@_needs_git
def test_git_state_detects_untracked_byte_change(tmp_path):
    """(iv) An already-untracked file's BYTES change while its '??' status path
    stays identical -> only content binding of untracked entries catches it."""
    repo, g = _init_repo(tmp_path)
    (repo / "u.txt").write_text("u-1\n", encoding="utf-8")  # '?? u.txt'
    s1 = prov._git_state(repo)
    (repo / "u.txt").write_text("u-2\n", encoding="utf-8")  # still '?? u.txt'
    s2 = prov._git_state(repo)
    assert s1 != s2


# --- A3: failed receipt PUBLICATION leaves no temp and returns nonzero ------ #


def test_receipt_tmp_cleaned_on_replace_failure(tmp_path, monkeypatch):
    """os.replace fails DURING publication (proof already passed): nonzero
    return, preexisting target byte-identical, and NO temp receipt left. The
    older nonmutation-failure test fails BEFORE publication begins -- this one
    fails inside it."""
    out = tmp_path / "cand"
    out.mkdir()
    monkeypatch.setattr(prov, "OUTPUT_ROOT", out)
    monkeypatch.setattr(
        prov,
        "run_rebuild",
        lambda *a, **k: {
            "completed": True,
            "failed_stage": None,
            "produced_paths": prov.expected_generated_paths(out),
            "reduce_invoked": True,
            "exit_code": 0,
        },
    )
    monkeypatch.setattr(prov, "make_receipt", lambda errs: {"kind": "x", "payload": {}})
    monkeypatch.setattr(prov, "_fs_snapshot", lambda root: {})
    monkeypatch.setattr(prov, "_git_state", lambda root: {"head": "H"})  # stable

    def boom(src, dst):
        raise OSError("simulated: target locked")

    monkeypatch.setattr(prov.os, "replace", boom)
    receipt_path = tmp_path / "r.json"
    receipt_path.write_text("SENTINEL", encoding="utf-8")  # preexisting
    assert prov.cmd_rebuild_check(receipt_path) == 1  # nonzero, not an exception
    assert receipt_path.read_text(encoding="utf-8") == "SENTINEL"
    files_left = sorted(f.name for f in tmp_path.iterdir() if f.is_file())
    assert files_left == ["r.json"]  # no unique-tmp or .tmp leftovers either
