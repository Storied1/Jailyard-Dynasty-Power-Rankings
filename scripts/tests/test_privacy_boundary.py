"""Privacy-boundary acceptance tests (contract section 6, "Privacy boundary").

A1 scope: I6, I37, I38, I39, I40, I41 — enforced BEFORE any private write.
I15's receipt-content half arrives with A3's accounting receipt.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.capture_2026 import CaptureError, capture, staging_guard
from scripts.shared import REPO_ROOT
from scripts.tests.test_capture_2026 import valid_kwargs


def private_kwargs(tmp_path, **overrides):
    return valid_kwargs(
        tmp_path,
        access_scope="league_private",
        privacy="private",
        **overrides,
    )


def git(*args, cwd=REPO_ROOT):
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# I6 — private components are written only under the private root
# ---------------------------------------------------------------------------


def test_private_component_stays_outside_tracked_roots(tmp_path):
    path = capture(
        "chat_export",
        {"messages_requested": ["2026-08"], "messages": [{"ts": "x"}]},
        **private_kwargs(tmp_path),
    )
    private_root = (tmp_path / "private").resolve()
    public_root = (tmp_path / "public").resolve()
    assert path.resolve().is_relative_to(private_root)
    assert not path.resolve().is_relative_to(public_root)
    assert not public_root.exists() or not list(public_root.rglob("*.json"))


# ---------------------------------------------------------------------------
# I37 — .gitignore covers both private roots, proven by git check-ignore
# ---------------------------------------------------------------------------


def test_git_check_ignore_covers_both_private_roots():
    for probe in (
        "private_captures/2026/chat_export/20260901T000000Z.json",
        "private_bundles/2026/2026-preseason/full_rich/bundle.json",
    ):
        result = git("check-ignore", "-q", probe)
        assert result.returncode == 0, f"{probe} is NOT gitignored"


# ---------------------------------------------------------------------------
# I38 — zero tracked paths under either private root
# ---------------------------------------------------------------------------


def test_git_ls_files_reports_no_tracked_private_paths():
    result = git("ls-files", "--", "private_captures", "private_bundles")
    assert result.returncode == 0
    assert (
        result.stdout.strip() == ""
    ), f"tracked private paths found: {result.stdout!r}"


# ---------------------------------------------------------------------------
# I39 — resolved-path containment blocks traversal
# ---------------------------------------------------------------------------


def test_resolved_path_containment_blocks_traversal(tmp_path):
    payload = {"messages_requested": ["2026-08"], "messages": [{"ts": "x"}]}
    for evil_sid in ("..", "../escape", "a/../../b", "a\\..\\b"):
        with pytest.raises(CaptureError):
            capture(evil_sid, payload, **private_kwargs(tmp_path))
    private_root = tmp_path / "private"
    assert not private_root.exists() or not list(private_root.rglob("*.json"))
    # nothing escaped into the tmp parent either
    assert not list(tmp_path.glob("*.json"))


# ---------------------------------------------------------------------------
# I40 — a symlink / junction / reparse point escaping the private root is
# rejected rather than followed
# ---------------------------------------------------------------------------


def _make_dir_link(link: Path, target: Path) -> bool:
    """Create a directory symlink (POSIX) or junction (Windows). False if unavailable."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except OSError:
        pass
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    return False


def test_symlink_or_reparse_point_escape_rejected(tmp_path):
    private_root = tmp_path / "private"
    private_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    link = private_root / "chat_export"
    if not _make_dir_link(link, outside):
        pytest.skip("cannot create symlink or junction on this host")

    with pytest.raises(CaptureError):
        capture(
            "chat_export",
            {"messages_requested": ["2026-08"], "messages": [{"ts": "x"}]},
            **private_kwargs(tmp_path),
        )
    assert list(outside.rglob("*.json")) == [], "write escaped the private root"


# ---------------------------------------------------------------------------
# I41 — the index staging guard fails on any staged private path
# (git status cannot work: an ignored path never appears there)
# ---------------------------------------------------------------------------


def test_index_staging_guard_fails_on_staged_private_path(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert git("init", "-q", cwd=repo).returncode == 0

    ok, offending = staging_guard(repo_root=repo)
    assert ok and offending == []

    private_file = repo / "private_captures" / "2026" / "x.json"
    private_file.parent.mkdir(parents=True)
    private_file.write_text("{}", encoding="utf-8")
    assert git("add", "-f", "private_captures/2026/x.json", cwd=repo).returncode == 0

    ok, offending = staging_guard(repo_root=repo)
    assert not ok
    assert offending == ["private_captures/2026/x.json"]
