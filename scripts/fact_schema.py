"""The canonical temporal fact. Fifteen fields, three clocks, never conflated.

Contract: docs/superpowers/plans/2026-08-02-jailyard-temporal-kernel.md K1.1.
The fact contract is exactly fifteen fields; the observation body rides as a
non-contract `payload_bytes` attachment (persisted and hash-verified, never
part of identity). All three clocks are canonicalized to the six-fractional-
digit UTC form at the boundary so lexicographic order is chronological order.
"""

import functools
import hashlib
import json
import re
import sys
from dataclasses import dataclass, fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FACT_TYPES_PATH = ROOT / "content" / "governance" / "fact_types.json"

# Canonical form: ALWAYS six fractional digits. Phase-P envelopes carry
# microsecond captured_at values; a whole-second-only rule rejects every one
# of them, and mixed-width strings are not lexicographically comparable.
INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_INPUT_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
ACCESS_SCOPES = {"public", "league_private"}
PRIVACY = {"public", "private"}


def canonical_instant(s):
    """Admit exact whole-second or fractional UTC instants; emit the canonical
    six-digit form. Anything else (naive, date-only, month-only, non-string)
    returns None and validate() refuses the fact."""
    if not isinstance(s, str) or not _INPUT_INSTANT.match(s):
        return None
    head, _, frac = s[:-1].partition(".")
    return f"{head}.{frac.ljust(6, '0')}Z"


class PayloadIntegrityError(ValueError):
    """content_sha256 does not describe the bytes actually held. Never a warning."""


def canonical_bytes(payload) -> bytes:
    """One serialization, everywhere. The hash is over THESE bytes."""
    if isinstance(payload, bytes):
        return payload
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def fact_hash(payload) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class Fact:
    fact_id: str
    source_record_id: str
    entity_ref: dict
    source_ref: str
    fact_type: str
    effective_at: str
    known_at: str
    access_scope: str
    known_at_basis: str
    captured_at: str
    content_sha256: str
    privacy: str
    normalizer_version: str
    schema_version: int
    supersedes: str | None
    # Non-contract attachment: the observation body that content_sha256 hashes.
    # Excluded from FACT_FIELDS and from fact identity; PERSISTED by FactStore.
    # Held as canonical bytes so no caller keeps a mutable reference to hashed data.
    payload_bytes: bytes | None = None

    def __post_init__(self):
        # Canonicalize the three clocks at the boundary: after this, every
        # stored instant is the six-digit form and string order is time order.
        for name in ("effective_at", "known_at", "captured_at"):
            c = canonical_instant(getattr(self, name))
            if c is not None:
                object.__setattr__(self, name, c)
        if self.payload_bytes is None:
            return
        if not isinstance(self.payload_bytes, bytes):
            # Accept a dict at the call boundary, canonicalize immediately.
            object.__setattr__(
                self, "payload_bytes", canonical_bytes(self.payload_bytes)
            )
        actual = "sha256:" + hashlib.sha256(self.payload_bytes).hexdigest()
        if self.content_sha256 != actual:
            raise PayloadIntegrityError(
                f"content_sha256 {self.content_sha256} does not match payload {actual}"
            )

    @property
    def payload(self):
        """A fresh decode per access: the caller never holds the hashed representation."""
        return None if self.payload_bytes is None else json.loads(self.payload_bytes)


# Declared, not derived: `payload_bytes` is deliberately absent.
FACT_FIELDS = (
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
)
assert len(FACT_FIELDS) == 15
assert set(FACT_FIELDS) == {f.name for f in fields(Fact)} - {"payload_bytes"}


@functools.lru_cache(maxsize=1)
def load_fact_types():
    # validate() runs once per observed fact; without the cache a multi-season
    # normalize performs one file open + parse per fact. Tests that mutate the
    # registry call load_fact_types.cache_clear().
    return load_json(FACT_TYPES_PATH, required=True)["types"]


def validate(fact) -> list:
    """Empty list means valid. Every rule fails closed."""
    problems = []
    for name in (
        "fact_id",
        "source_record_id",
        "source_ref",
        "fact_type",
        "known_at_basis",
        "normalizer_version",
    ):
        if not getattr(fact, name):
            problems.append(f"{name}: required")
    for name in ("effective_at", "known_at", "captured_at"):
        v = getattr(fact, name)
        if not (isinstance(v, str) and INSTANT.match(v)):
            problems.append(
                f"{name}: must be an exact UTC instant (canonical six-digit form)"
            )
    if fact.access_scope not in ACCESS_SCOPES:
        problems.append(f"access_scope: must be one of {sorted(ACCESS_SCOPES)}")
    if fact.privacy not in PRIVACY:
        problems.append(f"privacy: must be one of {sorted(PRIVACY)}")
    if fact.fact_type not in load_fact_types():
        problems.append(f"fact_type: '{fact.fact_type}' is not registered")
    if not problems and fact.captured_at < fact.known_at:
        # We cannot have held it before it was knowable.
        problems.append("captured_at precedes known_at")
    # Superset test, not proper-subset: {"type","season"} must fail on the
    # missing id, and an extra contextual key must not disable the check.
    if not isinstance(fact.entity_ref, dict) or not {"type", "id"} <= set(
        fact.entity_ref
    ):
        problems.append("entity_ref: requires {type, id}")
    return problems
