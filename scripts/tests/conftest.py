"""Suite-purity gate: unit tests must not modify committed content artifacts.

A reduce_* disk side effect once let the unit-test suite CLOBBER committed
arcs.json with fixture data (2026-07-10, caught only by a downstream
populated-layer check). This autouse session fixture hashes the committed
content trees before and after the test session and fails loudly on drift,
so any future test with disk side effects is caught at the suite itself.
"""

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WATCHED_DIRS = [
    REPO_ROOT / "content" / "chat",
    REPO_ROOT / "content" / "weeks",
    REPO_ROOT / "content" / "preseason-2025",
]


def _content_digest() -> str:
    h = hashlib.sha256()
    for base in WATCHED_DIRS:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            # dot-files (e.g. .media_progress.json) are regenerable caches
            if p.is_file() and not p.name.startswith("."):
                h.update(str(p.relative_to(REPO_ROOT)).encode())
                h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture(autouse=True, scope="session")
def content_purity_gate():
    before = _content_digest()
    yield
    after = _content_digest()
    assert before == after, (
        "Test suite modified committed content/ artifacts -- some test has "
        "disk side effects. Generators must be pure functions with writes "
        "centralized in main() (see the 2026-07-10 reduce_arcs clobber)."
    )


# K3 eval fixtures (K3.4 Step 0): defined in conftest_eval.py, re-exported here
# so every test module sees them. The purity gate above stays intact.
from scripts.tests.conftest_eval import claim_factory  # noqa: E402, F401
from scripts.tests.conftest_eval import fake_state  # noqa: E402, F401
from scripts.tests.conftest_eval import fake_state_without_history  # noqa: E402, F401
from scripts.tests.conftest_eval import preseason_state  # noqa: E402, F401
from scripts.tests.conftest_eval import seeded_seals  # noqa: E402, F401
