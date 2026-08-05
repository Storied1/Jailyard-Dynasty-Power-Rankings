"""Fact store: append-only, idempotent on repeat, superseding on change.

Contract: docs/superpowers/plans/2026-08-02-jailyard-temporal-kernel.md K1.2.
Identity binds (fact_type, source_record_id, content, known_at,
normalizer_version, supersedes); resolution is (fact_type, source_record_id)-
keyed; instants are canonicalized BEFORE identity and coalescing so mixed
whole-second/fractional forms of the same instant coalesce in both orders.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Package form FIRST (the capture_optional_2026.py pattern): under pytest this
# module is scripts.fact_store while a bare import would load a SECOND
# fact_schema whose PayloadIntegrityError is a different class -- the on-disk
# tamper test would then not catch the exception its own store raises.
try:
    from scripts.fact_schema import (
        FACT_FIELDS,
        Fact,  # noqa: E402
        PayloadIntegrityError,
        canonical_bytes,
        canonical_instant,
        fact_hash,
        validate,
    )
except ImportError:  # pragma: no cover - direct-run fallback
    from fact_schema import (
        FACT_FIELDS,
        Fact,  # noqa: E402
        PayloadIntegrityError,
        canonical_bytes,
        canonical_instant,
        fact_hash,
        validate,
    )

SCHEMA_VERSION = 1


class FactStore:
    def __init__(self, path):
        self.path = Path(path)
        self._facts = []
        self._ids = set()
        self._by_key = {}  # (fact_type, source_record_id) -> [facts]
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    body = rec.pop("payload", None)
                    # Fact.__post_init__ re-verifies content_sha256 against these
                    # bytes, so on-disk tampering raises PayloadIntegrityError here
                    # rather than silently entering a state.
                    self._append(
                        Fact(
                            **rec,
                            payload_bytes=(
                                None if body is None else canonical_bytes(body)
                            ),
                        )
                    )

    def load(self):
        return list(self._facts)

    def _append(self, fact):
        self._facts.append(fact)
        self._ids.add(fact.fact_id)
        self._by_key.setdefault((fact.fact_type, fact.source_record_id), []).append(
            fact
        )

    def _latest_for(self, fact_type, source_record_id):
        # Keyed on (fact_type, source_record_id): resolution must never let two
        # types sharing a record id supersede each other. Prefix disjointness in
        # the normalizers is a convention; this is the mechanism.
        candidates = self._by_key.get((fact_type, source_record_id), [])
        superseded = {f.supersedes for f in candidates if f.supersedes}
        live = [f for f in candidates if f.fact_id not in superseded]
        return max(live, key=lambda f: (f.known_at, f.fact_id)) if live else None

    def observe(self, payload, **meta):
        """Returns (fact, 'created' | 'coalesced' | 'superseded')."""
        # Canonicalize BEFORE identity and coalescing: fact_id hashes
        # meta["known_at"] and the coalescing `meaning` tuple compares raw meta
        # values, so a whole-second and a six-digit form of the SAME instant
        # would otherwise mint two ids and never coalesce.
        for name in ("effective_at", "known_at", "captured_at"):
            if name in meta:
                c = canonical_instant(meta[name])
                if c is not None:
                    meta[name] = c
        digest = fact_hash(payload)
        prior = self._latest_for(meta["fact_type"], meta["source_record_id"])
        # Coalesce only when the OBSERVATION AND ITS MEANING are both unchanged.
        # The design binds normalizer_version into every fact precisely because a
        # normalizer change is a change in meaning even when the bytes are
        # identical; comparing content_sha256 alone would discard a norm-v2
        # reading of the same capture as a duplicate of its norm-v1 predecessor.
        # Design section 1: "Identical repeats coalesce ... updates nothing" is
        # UNCONDITIONAL on time -- capture-instant-based types (franchise
        # identity) get a new known_at every envelope, and putting the clocks in
        # this tuple would turn four identical daily captures into a
        # supersession chain of identical payloads instead of one fact whose
        # first-held instant stands.
        meaning = (
            "normalizer_version",
            "access_scope",
            "known_at_basis",
            "fact_type",
            "privacy",
        )
        unchanged = (
            prior is not None
            and prior.content_sha256 == digest
            and all(getattr(prior, k) == meta.get(k) for k in meaning)
        )
        if unchanged:
            return prior, "coalesced"  # identical repeat: nothing changes
        supersedes = prior.fact_id if prior is not None else None
        fact = Fact(
            # normalizer_version is part of identity: a norm-v2 reading of the
            # same bytes at the same instant is a DIFFERENT fact. `supersedes` is
            # ALSO identity: an A -> B -> A value revert at a stable known_at
            # would otherwise mint the original id again, creating a supersession
            # CYCLE that empties state_at's retirement set. `type` is identity
            # because resolution is (fact_type, srid)-keyed -- with identical
            # content/time/version under two types, an id omitting fact_type
            # collides and the duplicate refusal below would REJECT a legitimate
            # observation.
            fact_id=fact_hash(
                {
                    "type": meta["fact_type"],
                    "srid": meta["source_record_id"],
                    "content": digest,
                    "known_at": meta["known_at"],
                    "norm": meta["normalizer_version"],
                    "supersedes": supersedes,
                }
            ).replace("sha256:", "fact:"),
            content_sha256=digest,
            schema_version=SCHEMA_VERSION,
            supersedes=supersedes,
            payload_bytes=canonical_bytes(
                payload
            ),  # canonicalized once, then immutable
            **{k: v for k, v in meta.items() if k in FACT_FIELDS},
        )
        if fact.fact_id in self._ids:
            # Never a warning: a duplicate id forks the supersession graph.
            raise ValueError(f"fact_id collision: {fact.fact_id}")
        problems = validate(fact)
        if problems:
            raise ValueError(f"invalid fact: {problems}")
        self._append(fact)
        return fact, ("superseded" if prior is not None else "created")

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(
            self._facts,
            key=lambda f: (f.fact_type, f.source_record_id, f.known_at, f.fact_id),
        )
        for f in ordered:  # verify before persisting, never after
            if (
                f.payload_bytes is not None
                and fact_hash(f.payload_bytes) != f.content_sha256
            ):
                raise PayloadIntegrityError(
                    f"{f.fact_id}: payload does not match its hash"
                )
        body = "\n".join(
            json.dumps(
                {**{k: getattr(f, k) for k in FACT_FIELDS}, "payload": f.payload},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            for f in ordered
        )
        self.path.write_text(
            body + ("\n" if body else ""), encoding="utf-8", newline="\n"
        )
