"""Tests for the chat provenance manifest generator (two-layer, portable).

Coverage:
  (a) CHECKOUT-PORTABLE HASHING -- code/text hashes equal the LF blob git stores,
      tolerating not-yet-tracked / working-tree-modified CODE_FILES (git
      hash-object of the worktree, not HEAD:path). Needs only committed code + git.
  (b) ROLE RESTRUCTURE -- parsed_messages/identity_chain are derived_intermediates;
      counts are private-derived; the public projection is symmetric.
  (c) RECEIPT-BOUND --write -- two-layer authorization + portable persist:
      happy path, and every rejection (missing/malformed/wrong-root + content-layer
      mismatches) leaves the target manifest BYTE-IDENTICAL.

Tests that need the gitignored private chat inputs SKIP when those are absent
(fresh CI checkout), mirroring the repo convention.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_chat_provenance as prov  # noqa: E402

SOURCE_ROOT = prov.SOURCE_ROOT
SCRIPT = SOURCE_ROOT / "scripts" / "generate_chat_provenance.py"
PRIVATE_INPUTS = [
    prov.CHAT_TXT_PATH,
    prov.PARSED_MESSAGES_PATH,
    prov.IDENTITY_CHAIN_PATH,
]

_HAS_GIT = shutil.which("git") is not None
_PRIVATE_PRESENT = all(p.exists() for p in PRIVATE_INPUTS)
_needs_private = pytest.mark.skipif(
    not _PRIVATE_PRESENT,
    reason="gitignored private chat inputs absent (present only locally)",
)


def _git_blob_sha256(relpath):
    """sha256 of the blob git would store for the CURRENT worktree content of
    `relpath` (via a throwaway index; works for untracked + dirty files too)."""
    idx_fd, idx_path = tempfile.mkstemp()
    os.close(idx_fd)
    try:
        env = dict(os.environ, GIT_INDEX_FILE=idx_path)

        def run(*a, **k):
            return subprocess.run(
                a, cwd=SOURCE_ROOT, env=env, check=True, capture_output=True, **k
            )

        run("git", "read-tree", "HEAD")
        run("git", "add", "--", relpath)
        blob = run("git", "cat-file", "blob", f":{relpath}").stdout
        return "sha256:" + hashlib.sha256(blob).hexdigest()
    finally:
        os.unlink(idx_path)


@pytest.mark.skipif(not _HAS_GIT, reason="git not available")
def test_code_hashes_match_working_tree_lf_blobs():
    """(a) Each code/text hash == the LF blob git stores for the WORKING TREE, so
    untracked (recompute_projection.py) / modified stages don't false-fail."""
    assert prov.CODE_FILES, "no code files declared"
    for path in prov.CODE_FILES:
        rel = path.resolve().relative_to(SOURCE_ROOT).as_posix()
        errors = []
        computed = prov.text_sha(path, errors)
        assert not errors, errors
        assert computed == _git_blob_sha256(rel), f"{rel}: not checkout-portable"


@pytest.mark.skipif(not _HAS_GIT, reason="git not available")
def test_text_sha_is_crlf_invariant(tmp_path):
    lf = tmp_path / "lf.py"
    crlf = tmp_path / "crlf.py"
    lf.write_bytes(b"a = 1\nb = 2\n")
    crlf.write_bytes(b"a = 1\r\nb = 2\r\n")
    errors = []
    assert prov.text_sha(lf, errors) == prov.text_sha(crlf, errors)
    assert not errors


@_needs_private
def test_compute_payload_clean_and_roles():
    """On an intact repo compute_payload has no errors and carries the SIX roles
    + counts, with parsed_messages/identity_chain under derived_intermediates."""
    errors = []
    payload = prov.compute_payload(errors, include_private=True)
    assert errors == [], errors
    for role in (
        "inputs_source",
        "inputs_data",
        "code",
        "outputs_derived",
        "inputs_private",
        "derived_intermediates",
    ):
        assert payload[role], f"empty role: {role}"
    assert payload["counts"]["messages"] > 0
    di = payload["derived_intermediates"]
    assert any(k.endswith("chat/parsed_messages.json") for k in di)
    assert any(k.endswith("chat/identity_chain.json") for k in di)
    # inputs_private is ONLY the raw source now.
    assert list(payload["inputs_private"]) == [
        next(k for k in payload["inputs_private"])
    ]
    assert any(k.endswith("chat/_chat.txt") for k in payload["inputs_private"])
    # No null hashes; media-catalog excluded.
    for role in (
        "inputs_source",
        "inputs_data",
        "code",
        "outputs_derived",
        "inputs_private",
        "derived_intermediates",
    ):
        for k, v in payload[role].items():
            assert isinstance(v, str) and v.startswith("sha256:"), (role, k, v)
    assert not any("media-catalog" in k for k in payload["outputs_derived"])


@_needs_private
def test_public_projection_is_symmetric():
    """Public projection omits counts + inputs_private + derived_intermediates,
    and _public_view(full) equals the recomputed public payload."""
    full = prov.compute_payload([], include_private=True)
    public = prov.compute_payload([], include_private=False)
    for k in prov.PRIVATE_PAYLOAD_KEYS:
        assert k not in public
    assert prov._public_view(full) == public


def test_normalized_source_root_portable():
    n = prov.normalized_source_root()
    assert "\\" not in n  # forward slashes only
    assert n == n.lower() or os.name != "nt"  # normcase lowercases on Windows


@_needs_private
def test_public_projection_exact_role_set():
    """The public projection has EXACTLY the public roles -- no private role leaks."""
    public = prov.compute_payload([], include_private=False)
    assert set(public) == {
        "schema",
        "note",
        "generation",
        "inputs_source",
        "inputs_data",
        "code",
        "outputs_derived",
    }


def _write_full_manifest(tmp_path):
    manifest = tmp_path / "provenance.json"
    full = prov.compute_payload([], include_private=True)
    manifest.write_text(
        json.dumps(full, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


@_needs_private
def test_verify_public_baseline_passes(tmp_path):
    assert prov.cmd_verify(_write_full_manifest(tmp_path), public=True) == 0


@_needs_private
@pytest.mark.parametrize("mut", ["missing-only", "extra-only"])
def test_verify_public_fails_on_missing_or_extra_public_path(tmp_path, mut):
    """De-confounded: each mutation starts from a FRESH valid manifest, so an
    'ignore-extras' impl cannot pass the extra-only case by riding a still-missing
    key. (A REAL extra output FILE is proven in test_chat_rebuild.py.)"""
    manifest = _write_full_manifest(tmp_path)
    d = json.loads(manifest.read_text(encoding="utf-8"))
    if mut == "missing-only":
        d["code"].pop(next(iter(d["code"])))
    else:  # extra-only
        d["outputs_derived"]["content/chat/EXTRA.json"] = "sha256:" + "0" * 64
    manifest.write_text(json.dumps(d, indent=2), encoding="utf-8")
    assert prov.cmd_verify(manifest, public=True) != 0


# --- Receipt-bound --write (2f) --------------------------------------------- #


def _write_receipt(tmp_path, receipt):
    p = tmp_path / "receipt.json"
    p.write_text(json.dumps(receipt), encoding="utf-8")
    return p


@_needs_private
def test_receipt_bound_write_happy_path(tmp_path):
    """Matching receipt + matching on-disk payload -> write succeeds; the persisted
    manifest verifies AND carries neither normalized_source_root nor an absolute
    source path (portable)."""
    receipt = prov.make_receipt([])
    rpath = _write_receipt(tmp_path, receipt)
    manifest = tmp_path / "provenance.json"
    assert prov.cmd_write(manifest, rpath) == 0
    assert manifest.exists()
    assert prov.cmd_verify(manifest, public=False) == 0
    assert prov.cmd_verify(manifest, public=True) == 0
    text = manifest.read_text(encoding="utf-8")
    data = json.loads(text)
    # No authorization/identity BINDING field, and no absolute checkout path value.
    # (The `note` legitimately mentions the phrase to document the design.)
    assert "authorization" not in data
    assert "normalized_source_root" not in data
    assert prov.normalized_source_root() not in text


@_needs_private
def test_cli_default_is_verify_not_write(tmp_path):
    """Bare invocation is --verify (default), NOT a write: a missing manifest ->
    nonzero and NO file created."""
    manifest = tmp_path / "provenance.json"
    r = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--manifest", str(manifest)],
        cwd=SOURCE_ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert not manifest.exists()


def test_write_requires_receipt(tmp_path):
    manifest = tmp_path / "provenance.json"
    assert prov.cmd_write(manifest, None) == 1
    assert not manifest.exists()


def _sentinel_manifest(tmp_path):
    """A pre-existing manifest whose bytes must survive every rejected write."""
    m = tmp_path / "provenance.json"
    m.write_text('{"sentinel": true}\n', encoding="utf-8")
    return m, m.read_bytes()


@_needs_private
@pytest.mark.parametrize(
    "mutate,label",
    [
        (lambda r: r.update(kind="bogus/9"), "malformed-kind"),
        (
            lambda r: r["authorization"].update(
                normalized_source_root="/somewhere/else"
            ),
            "wrong-root",
        ),
        (
            lambda r: r["payload"]["code"].update(
                {next(iter(r["payload"]["code"])): "sha256:" + "0" * 64}
            ),
            "code-only",
        ),
        (
            lambda r: r["payload"]["inputs_data"].update(
                {next(iter(r["payload"]["inputs_data"])): "sha256:" + "0" * 64}
            ),
            "data-only",
        ),
        (
            lambda r: r["payload"]["outputs_derived"].update(
                {next(iter(r["payload"]["outputs_derived"])): "sha256:" + "0" * 64}
            ),
            "output-only",
        ),
        (
            lambda r: r["payload"]["derived_intermediates"].update(
                {
                    next(iter(r["payload"]["derived_intermediates"])): "sha256:"
                    + "0" * 64
                }
            ),
            "derived-intermediate-only",
        ),
        (
            lambda r: r["payload"]["inputs_private"].update(
                {next(iter(r["payload"]["inputs_private"])): "sha256:" + "0" * 64}
            ),
            "raw-input-only",
        ),
        (
            lambda r: r["payload"]["generation"].__setitem__("season", 1999),
            "rebuild-parameter-only",
        ),
        (
            lambda r: r["payload"]["inputs_source"].update(
                {next(iter(r["payload"]["inputs_source"])): "sha256:" + "0" * 64}
            ),
            "source-only",
        ),
        (
            lambda r: r["payload"]["outputs_derived"].pop(
                next(iter(r["payload"]["outputs_derived"]))
            ),
            "missing-output",
        ),
        (
            lambda r: r["payload"]["outputs_derived"].__setitem__(
                "content/chat/BOGUS.json", "sha256:" + "0" * 64
            ),
            "extra-output",
        ),
    ],
)
def test_receipt_rejections_leave_manifest_byte_identical(tmp_path, mutate, label):
    """Missing/malformed/wrong-root + every content-layer mismatch is REJECTED,
    and the target manifest stays byte-identical (write only ever mutates on
    success). An always-reject impl is caught by the happy-path test above."""
    receipt = prov.make_receipt([])
    mutate(receipt)
    rpath = _write_receipt(tmp_path, receipt)
    manifest, before = _sentinel_manifest(tmp_path)
    assert prov.cmd_write(manifest, rpath) == 1, f"{label} should reject"
    assert manifest.read_bytes() == before, f"{label} mutated the manifest"


@_needs_private
def test_receipt_missing_file_rejected(tmp_path):
    manifest, before = _sentinel_manifest(tmp_path)
    assert prov.cmd_write(manifest, tmp_path / "nope.json") == 1
    assert manifest.read_bytes() == before


# --- _guard_content_chat_dir: planted REAL unexpected file (Gate-4 [4d]) ---- #


def test_guard_content_chat_dir_happy_path(tmp_path, monkeypatch):
    """Only classified *.json present -> no errors (guard isn't always-reject)."""
    d = tmp_path / "content" / "chat"
    d.mkdir(parents=True)
    for name in prov.DERIVED_ANALYTICS:
        (d / name).write_text("{}", encoding="utf-8")
    (d / "name-map.json").write_text("{}", encoding="utf-8")  # known non-pipeline
    monkeypatch.setattr(prov, "CONTENT_CHAT_OUT_DIR", d)
    errors = []
    prov._guard_content_chat_dir(errors)
    assert errors == []


def test_guard_content_chat_dir_rejects_planted_unclassified_json(
    tmp_path, monkeypatch
):
    """A REAL unexpected content/chat/*.json on disk (not a manifest tamper or
    inventory-set mutation) must fail closed with the unclassified error."""
    d = tmp_path / "content" / "chat"
    d.mkdir(parents=True)
    for name in prov.DERIVED_ANALYTICS:
        (d / name).write_text("{}", encoding="utf-8")
    (d / "ROGUE_ANALYTICS.json").write_text("{}", encoding="utf-8")  # planted
    monkeypatch.setattr(prov, "CONTENT_CHAT_OUT_DIR", d)
    errors = []
    prov._guard_content_chat_dir(errors)
    assert any("unclassified" in e and "ROGUE_ANALYTICS.json" in e for e in errors)
