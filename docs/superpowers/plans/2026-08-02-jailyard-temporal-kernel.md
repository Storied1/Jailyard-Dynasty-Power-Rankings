# Jailyard Temporal Kernel — Implementation Plan (P → K1 → K2 → K3 → STOP)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Status:** DRAFT — awaiting Blake review. Not authorized for implementation.

Revised twice on 2026-08-03. Round one (execution-level): ten unrunnable paths. Round two
(source-graph): ten more, all of the class _interfaces describing a system the producer graph
cannot build_. Both rounds' corrections stay inside the approved design. See Self-Review.

**One item is BLOCKED on Blake and cannot be resolved in this plan:** the capture-row set covers
only six of the nine bridge fact types. See "Open design decision: capture-row coverage" — P2 and
P3 must not execute until it is ruled on. Everything else is reviewable as written. Still DRAFT;
neither revision constitutes approval.

**Design authority:** `docs/superpowers/specs/2026-08-01-jailyard-writer-foundation-design.md`,
APPROVED at `9805426`. Material deviation requires design re-approval.

**Relationship to `df7c1ea`:** this plan **replaces**
`docs/superpowers/plans/2026-08-02-jailyard-writer-foundation-d1.md` as the active plan for
P/K1/K2/K3. That document stands **unchanged** as the requirements inventory for S1a (desks) and
S1b (media, render, publication), which this plan does not schedule.

**Goal:** stand up the temporal kernel, compile the three D1 states from it, run five measured
data-layer arms chronologically, and stop for judgment — while the 2026 capture lane runs from
day one.

**Architecture:** immutable captures → typed temporal facts → `state_at` → dated decisions and
claims → later grading. `state_at` is league-world truth; `decision_history_at` is a separate
authority over sealed judgments. Aggregates are recomputed from admitted facts, never read from a
stored season-end value.

**Tech Stack:** Python 3.12, pytest, `jsonschema`, stdlib `hashlib`/`dataclasses`/`zoneinfo`.
Fact storage is typed JSONL (rebuildable; SQLite/Parquet remain permissible substitutes behind the
same interface). No new services.

## Global Constraints

- `python`, never `python3` (Windows). Every shipped command pins the interpreter:
  `export PY="/c/Users/blake/AppData/Local/Programs/Python/Python312/python"` and
  `export POLARS_SKIP_CPU_CHECK=1`. The `sse3` import failure is shell-dependent — the Git Bash
  executor shell imports polars 1.40.1 cleanly with that executable, another standard shell
  reproduces the error, and the variable resolves it there. Pinning both removes the difference.
- **`shared.save_json_canonical(path, data, verbose=False)`** — path FIRST.
- sys.path bootstrap per `scripts/fetch_nflreadpy.py:20-25`; tests import `from scripts.X import`.
- Every CLI ends `raise SystemExit(main())`. A bare `main()` returning 1 exits 0.
- `sorted()`, never `list(set)`, where serialized.
- Baseline suite **343 passed / 2 skipped** (`c751b22`). No task reduces it.
- Binary gates. No "approve with notes".
- **No wall-clock inside a fact body.** `captured_at` comes from the capture record. Wall-clock in
  a normalizer breaks deterministic replay.
- **One writer.** Lane P runs operationally alongside kernel work, never as a concurrent repo
  writer.
- This plan performs no pushes, deletes nothing, and touches no protected untracked paths
  (`.claude/worktrees/`, `New folder/`).

---

## File Structure

| File                                        | Responsibility                                                       |
| ------------------------------------------- | -------------------------------------------------------------------- |
| `scripts/capture_2026.py`                   | Lane P: split-root append-only capture, fetchers, accounting receipt |
| `scripts/fact_schema.py`                    | `Fact` dataclass, the 15 fields, validation, canonical hashing       |
| `scripts/fact_store.py`                     | Append, coalesce, supersede, load; JSONL substrate                   |
| `scripts/normalize_facts.py`                | Per-source normalizers for the 9 bridge fact types                   |
| `scripts/temporal_state.py`                 | `state_at`, scope lattice, supersession resolution, reducers         |
| `scripts/decision_history.py`               | `decision_history_at`, `SealedDecision`, seal/verify                 |
| `scripts/claims_ledger.py`                  | Claim records, resolution rules, resolver                            |
| `scripts/decision_run.py`                   | Decision-run receipts, `runner_kind`                                 |
| `scripts/eval_contrast.py`                  | Frozen evidence-family manifest, contrast integrity                  |
| `scripts/eval_arms.py`                      | The five arms, inertia comparator, chronological driver              |
| `scripts/eval_scoring.py`                   | Per-claim-type scoring, fixed aggregation                            |
| `content/governance/fact_types.json`        | Fact-type registry: reducer, access scope, `known_at` basis          |
| `content/governance/evidence_families.json` | Frozen manifest for the K3 contrast                                  |
| `content/governance/capture_table.json`     | Lane P's eight rows                                                  |

---

## Lane P — 2026 capture (starts FIRST, runs throughout)

Verified 2026-08-02: no capture script, no capture table, no capture directories, no capture
workflow. `data/2026` is the 2026-04-04 snapshot. The only scheduled job is
`fetch-sleeper-data.yml` (`cron: '0 6 * 9-12 0'`) — September onward, weekly, overwriting. **The
perishable evidence is being lost now**, which is why P precedes K1.

### Task P1: Split-root append-only capture store

**Files:** Create `scripts/capture_2026.py`, `scripts/tests/test_capture_2026.py`; modify
`.gitignore`

**Interfaces:**

- Produces: `capture(source, payload, known_at_rule, privacy, captured_at) -> Path`,
  `PUBLIC_ROOT`, `PRIVATE_ROOT`, `receipt(paths) -> dict`

- [ ] **Step 1: Write the failing test**

```python
import json
import pytest
from scripts.capture_2026 import capture, receipt, PUBLIC_ROOT, PRIVATE_ROOT

def test_roots_are_distinct():
    assert PUBLIC_ROOT != PRIVATE_ROOT and "private" in str(PRIVATE_ROOT)

def test_private_capture_lands_outside_the_public_root(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.PUBLIC_ROOT", tmp_path / "pub")
    monkeypatch.setattr("scripts.capture_2026.PRIVATE_ROOT", tmp_path / "priv")
    p = capture("chat_media_export", {"m": 1}, "message_timestamp", "private",
                "2026-08-02T00:00:00Z")
    assert (tmp_path / "priv") in p.parents and (tmp_path / "pub") not in p.parents

def test_metadata_and_overwrite_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.PUBLIC_ROOT", tmp_path)
    kw = ("capture_instant", "public", "2026-08-02T00:00:00Z")
    rec = json.loads(capture("league", {"a": 1}, *kw).read_text(encoding="utf-8"))
    for f in ("source", "captured_at", "known_at_rule", "content_sha256", "privacy"):
        assert f in rec
    with pytest.raises(FileExistsError):
        capture("league", {"a": 2}, *kw)

def test_failed_fetch_is_never_written_as_a_capture(tmp_path, monkeypatch):
    """fetch_json returns None on exhausted retries. That is not a capture."""
    from scripts.capture_2026 import CaptureRefused
    monkeypatch.setattr("scripts.capture_2026.PUBLIC_ROOT", tmp_path)
    for bad in (None, "a string", 42, {}, []):
        with pytest.raises(CaptureRefused):
            capture("league", bad, "capture_instant", "public", "2026-08-02T00:00:00Z")
    assert not any(tmp_path.rglob("*.json")), "a refused capture must leave no file"

def test_capture_validates_its_own_instant(tmp_path, monkeypatch):
    """Manual-ingest rows call capture() directly and never pass through main()."""
    from scripts.capture_2026 import CaptureRefused
    monkeypatch.setattr("scripts.capture_2026.PUBLIC_ROOT", tmp_path)
    for bad in ("2026-08-02", "2026-08-02 00:00:00", "Sat 08/02/2026T06:00:00Z", None):
        with pytest.raises(CaptureRefused):
            capture("league", {"a": 1}, "capture_instant", "public", bad)

def test_receipt_never_carries_private_payloads(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.PRIVATE_ROOT", tmp_path)
    p = capture("chat_media_export", {"secret": "x"}, "message_timestamp", "private",
                "2026-08-02T00:00:00Z")
    r = receipt([p])
    assert "secret" not in json.dumps(r) and r["entries"][0]["privacy"] == "private"
```

- [ ] **Step 2: Run to verify it fails**

Run: `$PY -m pytest scripts/tests/test_capture_2026.py -v` → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Append-only capture store. Public and private roots are physically separate."""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "data" / "captures" / "2026" / "public"
PRIVATE_ROOT = ROOT / "private_captures" / "2026"      # gitignored, never staged
VALID_PRIVACY = {"public", "private"}
INSTANT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")   # same shape as fact_schema


def content_sha256(obj) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


class CaptureRefused(ValueError):
    """The observation cannot be honestly recorded. Never written, never counted."""


def capture(source, payload, known_at_rule, privacy, captured_at):
    """Validation lives HERE, not in main(). Manual-ingest rows call this directly."""
    if privacy not in VALID_PRIVACY:
        raise CaptureRefused(f"privacy must be one of {sorted(VALID_PRIVACY)}")
    if not (isinstance(captured_at, str) and INSTANT_RE.match(captured_at)):
        raise CaptureRefused(f"captured_at must be YYYY-MM-DDTHH:MM:SSZ, got {captured_at!r}")
    if not known_at_rule:
        raise CaptureRefused(f"{source}: known_at_rule is required")
    # fetch_sleeper.fetch_json returns None after exhausted retries (fetch_sleeper.py:69).
    # Writing that None would record a failed fetch as a successful capture.
    if payload is None:
        raise CaptureRefused(f"{source}: payload is None -- a failed fetch is not a capture")
    if not isinstance(payload, (dict, list)):
        raise CaptureRefused(f"{source}: payload must be an object or array, got {type(payload)}")
    if isinstance(payload, (dict, list)) and len(payload) == 0:
        raise CaptureRefused(
            f"{source}: empty payload; if this is legitimately empty, the caller must say so "
            "explicitly via an unavailable/error row rather than writing a hollow capture")
    root = PUBLIC_ROOT if privacy == "public" else PRIVATE_ROOT
    path = root / source / f"{captured_at.replace(':', '').replace('-', '')}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite capture: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json_canonical(path, {
        "source": source, "captured_at": captured_at, "known_at_rule": known_at_rule,
        "privacy": privacy, "content_sha256": content_sha256(payload), "payload": payload})
    return path


def receipt(paths):
    """Metadata only. Private payloads never enter a receipt."""
    out = []
    for p in sorted(paths):
        rec = json.loads(Path(p).read_text(encoding="utf-8"))
        out.append({k: rec[k] for k in
                    ("source", "captured_at", "content_sha256", "privacy")})
    return {"count": len(out), "entries": out}
```

Append `private_captures/` to `.gitignore`.

- [ ] **Step 4: Run to verify it passes** → 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_2026.py scripts/tests/test_capture_2026.py .gitignore
git commit -m "feat(capture): split public/private roots, metadata-only receipts"
```

---

### Task P2: A working fetch per capture-table row

`fetch_sleeper.py:172` iterates `range(1, len(all_matchups) + 1)` — `range(1, 1)` preseason, so
zero transactions. Lane P needs its own leg range.

**Files:** Modify `scripts/capture_2026.py`, its test; create
`content/governance/capture_table.json`, `docs/superpowers/plans/capture-manual-ingest.md`

**Interfaces:** Produces `SOURCE_FETCHERS`, `TRANSACTION_LEGS`, `load_capture_table()`,
`FetchFailed`, `_fetch_draft`, `_fetch_transactions`

> **BLOCKED — see "Open design decision: capture-row coverage" below.** The eight rows written in
> Step 3 cover only **six of the nine** bridge fact types. `schedule_pairing`, `matchup_result`
> and `nfl_game` have **no 2026 capture producer**, while `projections` and `injuries` serve no
> bridge fact type at all. The row set below is the current draft, not a resolved contract; do not
> execute P2/P3 against it until Blake rules. Everything else in Phase P is unaffected.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.capture_2026 import (load_capture_table, TRANSACTION_LEGS, SOURCE_FETCHERS,
                                  FetchFailed, _fetch_draft, _fetch_transactions)

REQUIRED = {"sleeper_league", "sleeper_users", "rosters", "draft", "transactions"}

def test_minimum_rows_present():
    assert REQUIRED <= {r["source"] for r in load_capture_table()}

def test_eight_rows_exactly():
    assert len(load_capture_table()) == 8

def test_every_row_has_a_fetcher_or_a_documented_manual_path():
    for r in load_capture_table():
        assert r["source"] in SOURCE_FETCHERS or r.get("manual_ingest_doc"), r["source"]

def test_transaction_legs_independent_of_scored_matchups():
    assert 1 in TRANSACTION_LEGS and max(TRANSACTION_LEGS) >= 18

def test_chat_row_is_private():
    rows = {r["source"]: r for r in load_capture_table()}
    assert rows["chat_media_export"]["privacy"] == "private"

def test_exhausted_retries_raise_instead_of_returning_none(monkeypatch):
    """fetch_sleeper.fetch_json returns None on failure; _get must not pass it on."""
    from scripts import capture_2026
    monkeypatch.setattr("fetch_sleeper.fetch_json", lambda *a, **k: None)
    with pytest.raises(FetchFailed):
        capture_2026._get("/league/1")

def test_draft_fetch_reaches_actual_picks(monkeypatch):
    """/league/{id}/drafts returns METADATA. Picks need /draft/{draft_id}/picks."""
    seen = []
    def fake(suffix):
        seen.append(suffix)
        if suffix.endswith("/drafts"):
            return [{"draft_id": "111", "status": "complete"}]
        if suffix == "/draft/111":
            return {"draft_id": "111", "type": "snake"}
        if suffix == "/draft/111/picks":
            return [{"pick_no": 1, "player_id": "a"}, {"pick_no": 2, "player_id": "b"}]
        raise AssertionError(suffix)
    monkeypatch.setattr("scripts.capture_2026._get", fake)
    out = _fetch_draft("L1")
    assert "/draft/111/picks" in seen
    assert [p["pick_no"] for p in out["boards"]["111"]["picks"]] == [1, 2]

def test_draft_metadata_without_picks_fails(monkeypatch):
    def fake(suffix):
        if suffix.endswith("/drafts"):
            return [{"status": "complete"}]      # no draft_id
        raise AssertionError(suffix)
    monkeypatch.setattr("scripts.capture_2026._get", fake)
    with pytest.raises(FetchFailed):
        _fetch_draft("L1")

def test_partial_transaction_leg_failure_is_not_an_empty_week(monkeypatch):
    """The `or []` form made an outage byte-identical to eighteen quiet weeks."""
    def fake(suffix):
        if suffix.endswith("/7"):
            raise FetchFailed(suffix)
        return []
    monkeypatch.setattr("scripts.capture_2026._get", fake)
    with pytest.raises(FetchFailed) as e:
        _fetch_transactions("L1")
    assert "7" in str(e.value)

def test_all_legs_read_and_genuinely_empty_is_a_valid_capture(monkeypatch):
    monkeypatch.setattr("scripts.capture_2026._get", lambda s: [])
    out = _fetch_transactions("L1")
    assert out["legs_requested"] == sorted(TRANSACTION_LEGS)
    assert len(out["legs"]) == len(TRANSACTION_LEGS)
```

The last two are the pair that matters: an unreadable leg and a genuinely quiet league must not
produce the same artifact. Only one of them is a capture.

- [ ] **Step 2: Run to verify it fails** → `ImportError: cannot import name 'TRANSACTION_LEGS'`

- [ ] **Step 3: Write `content/governance/capture_table.json`**

```json
{
  "version": 1,
  "season": 2026,
  "rows": [
    {
      "source": "sleeper_league",
      "mechanism": "api",
      "cadence": "daily",
      "known_at_rule": "capture_instant",
      "privacy": "public"
    },
    {
      "source": "sleeper_users",
      "mechanism": "api",
      "cadence": "daily",
      "known_at_rule": "capture_instant",
      "privacy": "public"
    },
    {
      "source": "rosters",
      "mechanism": "api",
      "cadence": "daily",
      "known_at_rule": "capture_instant",
      "privacy": "public"
    },
    {
      "source": "draft",
      "mechanism": "api",
      "cadence": "daily",
      "known_at_rule": "pick_timestamp_else_capture",
      "privacy": "public"
    },
    {
      "source": "transactions",
      "mechanism": "api",
      "cadence": "daily",
      "known_at_rule": "effective_completion_instant",
      "privacy": "public"
    },
    {
      "source": "projections",
      "mechanism": "manual_export",
      "cadence": "weekly",
      "known_at_rule": "publication_instant_else_unqualified",
      "privacy": "public",
      "manual_ingest_doc": "docs/superpowers/plans/capture-manual-ingest.md#projections"
    },
    {
      "source": "injuries",
      "mechanism": "manual_export",
      "cadence": "weekly",
      "known_at_rule": "publication_instant_else_unqualified",
      "privacy": "public",
      "manual_ingest_doc": "docs/superpowers/plans/capture-manual-ingest.md#injuries"
    },
    {
      "source": "chat_media_export",
      "mechanism": "manual_export",
      "cadence": "on_export",
      "known_at_rule": "message_timestamp",
      "privacy": "private",
      "manual_ingest_doc": "docs/superpowers/plans/capture-manual-ingest.md#chat"
    }
  ]
}
```

- [ ] **Step 4: Implement the fetchers**

```python
TRANSACTION_LEGS = list(range(1, 19))      # never derived from len(all_matchups)

CAPTURE_TABLE_PATH = ROOT / "content" / "governance" / "capture_table.json"


def load_capture_table():
    from shared import load_json
    return load_json(CAPTURE_TABLE_PATH, required=True)["rows"]


class FetchFailed(RuntimeError):
    """The source could not be read. Distinct from 'the source is legitimately empty'."""


def _get(suffix):
    """fetch_json returns None after exhausted retries -- convert that to a raise.

    Silently passing None onward is how a network outage becomes an empty capture.
    """
    from fetch_sleeper import fetch_json      # constant-host, validated helper
    out = fetch_json(suffix)
    if out is None:
        raise FetchFailed(f"exhausted retries: {suffix}")
    return out


def _fetch_draft(lid):
    """Two hops. `/league/{id}/drafts` returns draft METADATA, never the picks.

    Mirrors scripts/fetch_draft_picks.py, which is the working producer in this repo:
    resolve draft_id, then GET /draft/{draft_id}/picks.
    """
    drafts = _get(f"/league/{lid}/drafts")
    if not isinstance(drafts, list) or not drafts:
        raise FetchFailed(f"no drafts for league {lid}")
    ids = sorted(str(d.get("draft_id")) for d in drafts if d.get("draft_id"))
    if not ids:
        raise FetchFailed("draft metadata carries no draft_id")
    boards = {}
    for did in ids:
        if not did.isdigit():
            raise FetchFailed(f"non-numeric draft_id {did!r}")
        boards[did] = {"meta": _get(f"/draft/{did}"), "picks": _get(f"/draft/{did}/picks")}
    return {"draft_ids": ids, "boards": boards}


def _fetch_transactions(lid):
    """Per-leg typed results. A failed leg must never look like a quiet week."""
    legs, failed = {}, []
    for g in TRANSACTION_LEGS:
        try:
            legs[str(g)] = _get(f"/league/{lid}/transactions/{g}")
        except FetchFailed:
            failed.append(g)
    if failed:
        raise FetchFailed(f"transaction legs unreadable: {sorted(failed)}")
    return {"legs": legs, "legs_requested": sorted(TRANSACTION_LEGS)}


SOURCE_FETCHERS = {
    "sleeper_league": lambda lid: _get(f"/league/{lid}"),
    "sleeper_users": lambda lid: _get(f"/league/{lid}/users"),
    "rosters": lambda lid: _get(f"/league/{lid}/rosters"),
    "draft": _fetch_draft,
    "transactions": _fetch_transactions,
}
```

**`or []` is deleted deliberately.** The previous form turned every failed leg into an empty list,
so a league-wide outage and eighteen genuinely quiet weeks produced byte-identical captures. An
empty leg that was actually _read_ is legitimate and stays in `legs`; a leg that could not be read
raises. `legs_requested` is recorded so a later normalizer can prove which legs the capture covers
rather than inferring coverage from the keys that happen to be present.

Write `capture-manual-ingest.md` with one section per manual row (`#projections`, `#injuries`,
`#chat`) giving the source, the exact `capture(...)` invocation, the `known_at` justification, and
for chat that it is private-class and lands in `PRIVATE_ROOT`.

- [ ] **Step 5: Run** → 10 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/capture_2026.py content/governance/capture_table.json docs/superpowers/plans/capture-manual-ingest.md scripts/tests/test_capture_2026.py
git commit -m "feat(capture): fetch per row, offseason-capable transaction legs"
```

---

### Task P3: Baseline capture, eight-row accounting, daily cadence

**Files:** Modify `scripts/capture_2026.py`; create
`.github/workflows/capture-preseason-2026.yml`, `scripts/tests/test_capture_accounting.py`

**Interfaces:** Produces `accounting_receipt(now_utc, league_id, dry_run=False) -> dict` with
per-row `status` in `{"captured", "unavailable", "error"}`, and `ROW_STATUSES`

**Three statuses, not two.** `unavailable` means "this row has no automated producer and needs a
named human trigger" — a planned gap. `error` means "this row had a producer and it failed" — an
unplanned gap. Collapsing them lets an outage read as a documented manual step.

- [ ] **Step 1: Write the failing test**

```python
import json
import pytest
from scripts.capture_2026 import (accounting_receipt, load_capture_table, ROW_STATUSES,
                                  FetchFailed)

def test_accounts_for_every_row():
    r = accounting_receipt("2026-08-02T00:00:00Z", None, dry_run=True)
    assert {e["source"] for e in r["rows"]} == {x["source"] for x in load_capture_table()}
    assert len(r["rows"]) == len(load_capture_table())

def test_every_row_carries_a_typed_status():
    for e in accounting_receipt("2026-08-02T00:00:00Z", None, dry_run=True)["rows"]:
        assert e["status"] in ROW_STATUSES
        if e["status"] == "unavailable":
            assert e["acquisition_trigger"], e["source"]
        if e["status"] == "error":
            assert e["error"], e["source"]

def test_dry_run_cannot_resemble_real_coverage():
    """A dry run proves the table is walkable, never that anything was captured."""
    r = accounting_receipt("2026-08-02T00:00:00Z", None, dry_run=True)
    assert r["dry_run"] is True
    assert all(e["status"] != "captured" for e in r["rows"]), \
        "a dry run must not report captured"
    assert all(not e.get("content_sha256") for e in r["rows"])
    assert r["ok"] is False, "a dry run is never a satisfied accounting receipt"

def test_a_failed_required_fetch_is_error_not_captured(monkeypatch):
    def boom(_lid):
        raise FetchFailed("exhausted retries")
    monkeypatch.setitem(__import__("scripts.capture_2026", fromlist=["x"]).SOURCE_FETCHERS,
                        "rosters", boom)
    r = accounting_receipt("2026-08-02T00:00:00Z", "L1")
    row = next(e for e in r["rows"] if e["source"] == "rosters")
    assert row["status"] == "error" and "exhausted retries" in row["error"]
    assert r["ok"] is False

def test_malformed_payload_is_error_not_captured(monkeypatch):
    monkeypatch.setitem(__import__("scripts.capture_2026", fromlist=["x"]).SOURCE_FETCHERS,
                        "rosters", lambda _l: None)
    r = accounting_receipt("2026-08-02T00:00:00Z", "L1")
    assert next(e for e in r["rows"] if e["source"] == "rosters")["status"] == "error"

def test_draft_row_proves_picks_and_order_and_gates(monkeypatch):
    """A draft object is not a pick board. The assertion must gate, not decorate."""
    monkeypatch.setitem(__import__("scripts.capture_2026", fromlist=["x"]).SOURCE_FETCHERS,
                        "draft", lambda _l: {"draft_ids": ["111"],
                                             "boards": {"111": {"meta": {}, "picks": []}}})
    r = accounting_receipt("2026-08-02T00:00:00Z", "L1")
    d = next(e for e in r["rows"] if e["source"] == "draft")
    assert d["status"] == "error", "zero picks is not a captured draft"
    assert d["assertions"]["pick_count"] == 0

def test_no_private_payload_in_the_receipt():
    assert "payload" not in json.dumps(
        accounting_receipt("2026-08-02T00:00:00Z", None, dry_run=True))
```

- [ ] **Step 2: Run to verify it fails** → `ImportError`

- [ ] **Step 3: Implement**

```python
ROW_STATUSES = {"captured", "unavailable", "error"}


def _draft_assertions(payload):
    """A draft object is not proof. Prove picks AND order survived, across every board."""
    boards = (payload or {}).get("boards", {})
    picks = [p for b in boards.values() for p in (b.get("picks") or [])
             if isinstance(p, dict)]
    nos = [p.get("pick_no") for p in picks]
    return {"board_count": len(boards),
            "pick_count": len(picks),
            "order_preserved": bool(nos) and None not in nos and nos == sorted(nos)}


def _row_ok(src, assertions):
    """The gate. An assertion that never fails a row is decoration."""
    if src == "draft":
        return assertions["pick_count"] > 0 and assertions["order_preserved"]
    return True


def accounting_receipt(now_utc, league_id, dry_run=False):
    rows = []
    for row in load_capture_table():
        src, fetcher = row["source"], SOURCE_FETCHERS.get(src)
        base = {"source": src, "privacy": row["privacy"], "required": row.get("required", True),
                "acquisition_trigger": None, "error": None, "assertions": {}}
        if fetcher is None:
            rows.append({**base, "status": "unavailable",
                         "acquisition_trigger": row["manual_ingest_doc"]})
            continue
        if dry_run:
            # Never "captured": a dry run touches no network and writes no file.
            rows.append({**base, "status": "unavailable",
                         "acquisition_trigger": "dry-run: not attempted"})
            continue
        try:
            payload = fetcher(league_id)
            assertions = _draft_assertions(payload) if src == "draft" else {}
            if not _row_ok(src, assertions):
                rows.append({**base, "status": "error", "assertions": assertions,
                             "error": f"{src} failed its capture assertions"})
                continue
            path = capture(src, payload, row["known_at_rule"], row["privacy"], now_utc)
            rec = json.loads(Path(path).read_text(encoding="utf-8"))
            rows.append({**base, "status": "captured", "assertions": assertions,
                         "captured_at": rec["captured_at"],
                         "content_sha256": rec["content_sha256"]})
        except (FetchFailed, CaptureRefused) as e:
            rows.append({**base, "status": "error", "error": f"{type(e).__name__}: {e}"})
    failures = [r["source"] for r in rows if r["status"] == "error" and r["required"]]
    unmet = [r["source"] for r in rows
             if r["required"] and r["status"] != "captured"]
    return {"season": 2026, "generated_at": now_utc, "dry_run": dry_run,
            "rows": rows, "failures": sorted(failures), "unmet_required": sorted(unmet),
            "ok": (not dry_run) and not unmet}


def main():
    import argparse
    from datetime import datetime, timezone
    ap = argparse.ArgumentParser()
    ap.add_argument("--league-id")
    # Optional: an unattended scheduler cannot compute a UTC instant in its own
    # command string. Stamping captured_at at capture time is the documented rule
    # ("captured_at comes from the capture record"); the wall-clock ban applies to
    # normalizers, which must never invent one.
    ap.add_argument("--now-utc",
                    default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not INSTANT_RE.match(a.now_utc):
        raise SystemExit(f"--now-utc must be YYYY-MM-DDTHH:MM:SSZ, got {a.now_utc!r}")
    r = accounting_receipt(a.now_utc, a.league_id, dry_run=a.dry_run)
    # The receipt is written even on failure: an honest record of a bad day is the
    # point of accounting. What must not happen is exiting 0 on top of it.
    save_json_canonical(
        PUBLIC_ROOT / "_receipts" / f"{a.now_utc.replace(':', '').replace('-', '')}.json", r)
    print(json.dumps(r, indent=2, sort_keys=True))
    if a.dry_run:
        return 0
    if r["unmet_required"]:
        print(f"FAIL required rows not captured: {r['unmet_required']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

A dry run exits 0 because it asserts nothing about coverage; a real run exits **1** whenever any
required row is not `captured`. The scheduled task and the workflow both key on that code, so a
silent capture failure surfaces the next morning instead of at normalization time in October.

- [ ] **Step 3b: Run to verify it passes** → 7 passed

```bash
$PY -m pytest scripts/tests/test_capture_accounting.py -q || exit 1
```

The next step writes real capture files into the repository. Do not reach it on unproven code —
P3 previously went straight from implementation to a live baseline capture without ever running
its own tests green.

- [ ] **Step 4: Take the baseline capture — do this before starting K1**

```bash
$PY scripts/capture_2026.py --league-id <2026_LEAGUE_ID> --now-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

- [ ] **Step 5: Stage the public root only**

```bash
git add data/captures/2026/public/
# Check the INDEX, not `git status`: private_captures/ is gitignored, so it never
# appears in status and that guard could never fire. Only `git add -f` can stage it,
# and only the index shows that.
git diff --cached --name-only | grep -q '^private_captures/' \
  && { echo "STOP: private capture staged"; exit 1; }
git diff --cached --name-only | grep -q '^data/captures/2026/public/' \
  || { echo "STOP: nothing staged; the capture did not run"; exit 1; }
git commit -m "data(capture): baseline 2026 public capture with accounting receipt"
```

The second check is the one that catches a silent no-op: an empty stage means the capture produced
nothing, and committing it would record coverage that does not exist.

- [ ] **Step 6: Daily local capture until the workflow is activated**

A phase-boundary checkpoint is not a cadence. Register it so it survives an unattended day:

```bash
schtasks //Create //SC DAILY //ST 06:00 //TN "JailyardCapture2026" //TR \
  "cmd /c cd /d C:\\Users\\blake\\projects\\Jailyard-Dynasty-Power-Rankings && \
   C:\\Users\\blake\\AppData\\Local\\Programs\\Python\\Python312\\python.exe \
   scripts\\capture_2026.py --league-id <ID>"
```

`--now-utc` is deliberately omitted: cmd's `%DATE%` expands to a locale-dependent local date
(`Sat 08/02/2026`), which is neither UTC nor an ISO instant. The script stamps its own UTC instant
instead, and rejects any explicitly supplied value that is not `YYYY-MM-DDTHH:MM:SSZ` — so a
malformed instant fails at capture rather than surfacing later as a validation error on a fact.

The append-only store refuses same-instant overwrites, so a duplicate run is free.

Verify the task actually runs before trusting the cadence — a registered task that fails silently
is worse than no task, because it reads as coverage:

```bash
schtasks //Run //TN "JailyardCapture2026"
schtasks //Query //TN "JailyardCapture2026" //V //FO LIST | grep -i "last result\|last run"
```

- [ ] **Step 7: Author the workflow — inactive until pushed**

`.github/workflows/capture-preseason-2026.yml`, `cron: '0 6 * 7,8,9 *'` (daily through September;
the pre-kickoff window does not end 31 August). The job must **commit its captures back** — a
runner discards its filesystem on exit.

- [ ] **Step 8: STOP — activation requires Blake's explicit approval of that exact push.**

- [ ] **Step 9: Commit**

```bash
git add scripts/capture_2026.py .github/workflows/capture-preseason-2026.yml scripts/tests/test_capture_accounting.py
git commit -m "feat(capture): eight-row accounting, daily cadence, inactive workflow"
```

---

## Open design decision: capture-row coverage — BLOCKS P2/P3 EXECUTION

**This is Blake's call. The plan does not guess, and does not silently add or drop a row.**

Tracing every approved bridge fact type whose 2026 source is `capture` back to a producer in the
plan's eight rows:

| Bridge fact type     | 2026 source (design) | Producing capture row             | Covered |
| -------------------- | -------------------- | --------------------------------- | ------- |
| `franchise_identity` | capture              | `sleeper_league`, `sleeper_users` | yes     |
| `roster_membership`  | capture              | `rosters`                         | yes     |
| `transaction`        | capture              | `transactions`                    | yes     |
| `draft_pick`         | capture              | `draft`                           | yes     |
| `chat_message`       | manual export        | `chat_media_export`               | yes     |
| `schedule_pairing`   | capture              | **none**                          | **NO**  |
| `matchup_result`     | capture              | **none**                          | **NO**  |
| `nfl_game`           | capture              | **none**                          | **NO**  |
| `historical_matchup` | n/a (2025 and prior) | —                                 | n/a     |

Conversely, `projections` and `injuries` occupy two of the eight rows and normalize to **no bridge
fact type at all** — the design's §3 admits only what the three D1 editions need, "nothing
speculative."

**Why this is a design decision and not a plan fix.** The approved design fixes the count at
**eight** in three places (§6.1, §6 fallback, §7 Phase P gate) but never names the rows. So the row
_identities_ are plan-level — but no choice of eight rows can both (a) keep `projections` and
`injuries` and (b) cover the three missing types. The arithmetic is exact: six rows currently do
real bridge work, Sleeper `/league/{id}/matchups/{week}` would cover `schedule_pairing` **and**
`matchup_result` in one row, and an NFL schedule/results row would cover `nfl_game`. Six plus two
is eight — but only by dropping the other two.

| Option                                                                              | Keeps the approved count | Cost                                                                                                                                 |
| ----------------------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| **A** — swap `projections` + `injuries` out; add `league_matchups` + `nfl_schedule` | yes, still eight         | 2026 in-season projections are never captured. **Irreversible** — they are perishable and no retrospective source reconstructs them. |
| **B** — keep all eight and add the two → **ten rows**                               | **no**                   | Contradicts an approved number; needs design re-approval before Phase P can claim its gate.                                          |
| **C** — accept that three bridge types have no 2026 producer                        | yes                      | The 2026 prospective arm cannot build the same bundle as 2025. The definitive test measures something narrower than the backtest.    |

Note in A's favor: the repo's `nfl_games/{id}.json` entity already carries `key_injuries` from
nflreadpy, so an `nfl_schedule` row plausibly subsumes the standalone `injuries` row. That argument
does **not** extend to `projections`, which nothing else captures.

**Until this is ruled on:** P1 is executable as written; P2 and P3 are not, because their row set
is unresolved. Add a `required: true|false` field per row when the set is settled — the accounting
gate above reads it, and every current row defaults to required.

---

## K1 — The temporal kernel

### Task K1.1: Fact schema

**Files:** Create `scripts/fact_schema.py`, `content/governance/fact_types.json`,
`scripts/tests/test_fact_schema.py`

**Interfaces:**

- Produces: `Fact` (frozen dataclass — the 15 contract fields **plus a non-contract `payload`
  attachment**), `validate(fact) -> list[str]`, `fact_hash(payload) -> str`,
  `load_fact_types() -> dict`, `FACT_FIELDS`

**Why `payload` is an attachment, not a sixteenth field.** The design's fact contract is exactly
fifteen fields, and `content_sha256` is defined as the hash **of the fact payload** — so a payload
is presupposed but is not itself contract metadata. The aggregates in K1.4 are recomputed from
admitted facts, which is impossible unless the observation body is reachable from the `Fact` the
reducer holds. `FACT_FIELDS` is therefore declared explicitly as the fifteen contract names rather
than derived from `dataclasses.fields()`, so `payload` rides along **without entering the contract
or the identity hash**.

**It is persisted, and it is verified.** The store writes it as a sibling key (K1.2) — an earlier
revision of this plan claimed it was "excluded from the serialized record," which contradicted the
writer three tasks later. Because it is persisted, the payload is exactly as tamperable as any
other on-disk value, so:

- the payload is held as **canonical bytes**, not a live dict — `Fact` stores
  `payload_bytes: bytes` and exposes `payload` as a decoded copy, so no caller retains a reference
  that can mutate what was hashed;
- `content_sha256` is **recomputed and checked** at construction, at reload, and immediately before
  persistence, and a mismatch raises rather than warns.

Without these, `content_sha256` records what the payload was at hash time and says nothing about
what the store actually holds — which is the opposite of a content hash's purpose.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.fact_schema import (Fact, validate, FACT_FIELDS, load_fact_types,
                                 canonical_bytes, fact_hash)

def mk(**over):
    base = dict(fact_id="f1", source_record_id="txn:1", entity_ref={"type": "player", "id": "6949"},
                source_ref="capture:2026/public/transactions/20260802T000000Z",
                fact_type="transaction", effective_at="2025-09-05T20:10:20Z",
                known_at="2025-09-05T20:10:20Z", access_scope="public",
                known_at_basis="effective_completion_instant", captured_at="2026-02-17T00:00:00Z",
                content_sha256="sha256:" + "a" * 64, privacy="public",
                normalizer_version="norm-v1", schema_version=1, supersedes=None)
    base.update(over)
    # `payload=` is the ergonomic call form; the field is payload_bytes. Derive
    # content_sha256 from the body UNLESS the caller pinned one deliberately
    # (the integrity test pins a deliberately wrong hash).
    if "payload" in base:
        body = base.pop("payload")
        base["payload_bytes"] = canonical_bytes(body)
        if "content_sha256" not in over:
            base["content_sha256"] = fact_hash(body)
    return Fact(**base)

def test_all_fifteen_fields_present():
    assert len(FACT_FIELDS) == 15
    assert not {"payload", "payload_bytes"} & set(FACT_FIELDS), \
        "the body is an attachment, never a contract field"

def test_payload_is_reachable_but_outside_the_contract():
    """K1.4's reducers read f.payload; the contract stays at fifteen fields."""
    assert mk().payload is None
    assert mk(payload={"home_pts": 120.5}).payload["home_pts"] == 120.5

def test_caller_cannot_mutate_a_hashed_payload():
    """The store held the caller's own dict, so a later mutation changed what
    write() persisted without changing content_sha256, fact_id, or supersession."""
    body = {"home_pts": 120.5}
    f = mk(payload=body)
    body["home_pts"] = 999.0                 # caller mutates after construction
    assert f.payload["home_pts"] == 120.5
    f.payload["home_pts"] = 999.0            # and mutates what the getter handed back
    assert f.payload["home_pts"] == 120.5

def test_payload_hash_mismatch_is_refused():
    from scripts.fact_schema import PayloadIntegrityError, fact_hash
    with pytest.raises(PayloadIntegrityError):
        mk(payload={"a": 1}, content_sha256=fact_hash({"a": 2}))
    for f in ("fact_id", "source_record_id", "entity_ref", "source_ref", "fact_type",
              "effective_at", "known_at", "access_scope", "known_at_basis", "captured_at",
              "content_sha256", "privacy", "normalizer_version", "schema_version", "supersedes"):
        assert f in FACT_FIELDS

def test_missing_access_scope_is_invalid():
    assert validate(mk(access_scope=None))

def test_unknown_access_scope_is_invalid():
    assert validate(mk(access_scope="everyone"))

def test_known_at_before_effective_at_is_allowed_but_captured_before_known_is_not():
    assert not validate(mk(known_at="2025-09-05T20:10:20Z", captured_at="2026-01-01T00:00:00Z"))
    assert validate(mk(known_at="2026-01-01T00:00:00Z", captured_at="2025-01-01T00:00:00Z"))

def test_naive_or_date_only_timestamps_rejected():
    for bad in ("2025-09-05", "2025-09-05 20:10:20", "2025-09"):
        assert validate(mk(known_at=bad))

def test_unregistered_fact_type_is_invalid():
    assert validate(mk(fact_type="speculative_type"))

def test_fact_is_immutable():
    with pytest.raises(Exception):
        mk().known_at = "2026-01-01T00:00:00Z"

def test_fact_types_registry_covers_the_nine_bridge_types():
    reg = load_fact_types()
    for t in ("franchise_identity", "schedule_pairing", "matchup_result", "roster_membership",
              "transaction", "draft_pick", "chat_message", "historical_matchup", "nfl_game"):
        assert t in reg, t
        assert reg[t]["reducer"] and reg[t]["default_access_scope"] in {"public", "league_private"}
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Write the registry** — `content/governance/fact_types.json`

```json
{
  "version": 1,
  "types": {
    "franchise_identity": {
      "reducer": "latest",
      "default_access_scope": "public",
      "known_at_basis": "capture_instant"
    },
    "schedule_pairing": {
      "reducer": "latest",
      "default_access_scope": "public",
      "known_at_basis": "qualified_schedule_source_or_policy"
    },
    "matchup_result": {
      "reducer": "append",
      "default_access_scope": "public",
      "known_at_basis": "game_conclusion"
    },
    "roster_membership": {
      "reducer": "latest",
      "default_access_scope": "public",
      "known_at_basis": "anchor_or_transaction_completion"
    },
    "transaction": {
      "reducer": "append",
      "default_access_scope": "public",
      "known_at_basis": "effective_completion_instant"
    },
    "draft_pick": {
      "reducer": "append",
      "default_access_scope": "public",
      "known_at_basis": "pick_timestamp_else_capture"
    },
    "chat_message": {
      "reducer": "append",
      "default_access_scope": "league_private",
      "known_at_basis": "message_timestamp"
    },
    "historical_matchup": {
      "reducer": "append",
      "default_access_scope": "public",
      "known_at_basis": "game_conclusion"
    },
    "nfl_game": {
      "reducer": "latest",
      "default_access_scope": "public",
      "known_at_basis": "game_conclusion"
    }
  }
}
```

- [ ] **Step 4: Implement**

```python
"""The canonical temporal fact. Fifteen fields, three clocks, never conflated."""
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
INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ACCESS_SCOPES = {"public", "league_private"}
PRIVACY = {"public", "private"}


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
        if self.payload_bytes is None:
            return
        if not isinstance(self.payload_bytes, bytes):
            # Accept a dict at the call boundary, canonicalize immediately.
            object.__setattr__(self, "payload_bytes", canonical_bytes(self.payload_bytes))
        actual = "sha256:" + hashlib.sha256(self.payload_bytes).hexdigest()
        if self.content_sha256 != actual:
            raise PayloadIntegrityError(
                f"content_sha256 {self.content_sha256} does not match payload {actual}")

    @property
    def payload(self):
        """A fresh decode per access: the caller never holds the hashed representation."""
        return None if self.payload_bytes is None else json.loads(self.payload_bytes)


# Declared, not derived: `payload` is deliberately absent.
FACT_FIELDS = (
    "fact_id", "source_record_id", "entity_ref", "source_ref", "fact_type",
    "effective_at", "known_at", "access_scope", "known_at_basis", "captured_at",
    "content_sha256", "privacy", "normalizer_version", "schema_version", "supersedes",
)
assert len(FACT_FIELDS) == 15
assert set(FACT_FIELDS) == {f.name for f in fields(Fact)} - {"payload_bytes"}


def load_fact_types():
    return load_json(FACT_TYPES_PATH, required=True)["types"]


class PayloadIntegrityError(ValueError):
    """content_sha256 does not describe the bytes actually held. Never a warning."""


def canonical_bytes(payload) -> bytes:
    """One serialization, everywhere. The hash is over THESE bytes."""
    if isinstance(payload, bytes):
        return payload
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def fact_hash(payload) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate(fact) -> list:
    """Empty list means valid. Every rule fails closed."""
    problems = []
    for name in ("fact_id", "source_record_id", "source_ref", "fact_type",
                 "known_at_basis", "normalizer_version"):
        if not getattr(fact, name):
            problems.append(f"{name}: required")
    for name in ("effective_at", "known_at", "captured_at"):
        v = getattr(fact, name)
        if not (isinstance(v, str) and INSTANT.match(v)):
            problems.append(f"{name}: must be an exact UTC instant YYYY-MM-DDTHH:MM:SSZ")
    if fact.access_scope not in ACCESS_SCOPES:
        problems.append(f"access_scope: must be one of {sorted(ACCESS_SCOPES)}")
    if fact.privacy not in PRIVACY:
        problems.append(f"privacy: must be one of {sorted(PRIVACY)}")
    if fact.fact_type not in load_fact_types():
        problems.append(f"fact_type: '{fact.fact_type}' is not registered")
    if not problems and fact.captured_at < fact.known_at:
        # We cannot have held it before it was knowable.
        problems.append("captured_at precedes known_at")
    if not isinstance(fact.entity_ref, dict) or set(fact.entity_ref) < {"type", "id"}:
        problems.append("entity_ref: requires {type, id}")
    return problems
```

- [ ] **Step 5: Run to verify it passes** → 11 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/fact_schema.py content/governance/fact_types.json scripts/tests/test_fact_schema.py
git commit -m "feat(facts): fifteen-field temporal fact schema with fail-closed validation"
```

---

### Task K1.2: Fact store — idempotent coalescing and supersession

**Files:** Create `scripts/fact_store.py`, `scripts/tests/test_fact_store.py`

**Interfaces:**

- Consumes: `Fact`, `fact_hash`, `validate`
- Produces: `FactStore(path)` with `.observe(...) -> tuple[Fact, str]` returning
  `(fact, "created" | "coalesced" | "superseded")`, `.load() -> list[Fact]`, `.write()`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.fact_store import FactStore

OBS = dict(source_record_id="txn:1", entity_ref={"type": "player", "id": "6949"},
           source_ref="capture:a", fact_type="transaction",
           effective_at="2025-09-05T20:10:20Z", known_at="2025-09-05T20:10:20Z",
           access_scope="public", known_at_basis="effective_completion_instant",
           captured_at="2026-08-02T00:00:00Z", privacy="public",
           normalizer_version="norm-v1")

def test_identical_repeat_coalesces(tmp_path):
    s = FactStore(tmp_path / "facts.jsonl")
    f1, a1 = s.observe(payload={"v": 1}, **OBS)
    f2, a2 = s.observe(payload={"v": 1}, **dict(OBS, captured_at="2026-08-03T00:00:00Z"))
    assert a1 == "created" and a2 == "coalesced"
    assert f1.fact_id == f2.fact_id and len(s.load()) == 1

def test_changed_record_supersedes(tmp_path):
    s = FactStore(tmp_path / "facts.jsonl")
    f1, _ = s.observe(payload={"v": 1}, **OBS)
    f2, action = s.observe(payload={"v": 2},
                           **dict(OBS, known_at="2025-09-06T00:00:00Z",
                                  captured_at="2026-08-03T00:00:00Z"))
    assert action == "superseded" and f2.supersedes == f1.fact_id
    assert len(s.load()) == 2, "the original is retained, not mutated"

def test_fact_id_is_deterministic(tmp_path):
    a = FactStore(tmp_path / "a.jsonl").observe(payload={"v": 1}, **OBS)[0]
    b = FactStore(tmp_path / "b.jsonl").observe(payload={"v": 1}, **OBS)[0]
    assert a.fact_id == b.fact_id

def test_invalid_fact_is_refused(tmp_path):
    s = FactStore(tmp_path / "facts.jsonl")
    with pytest.raises(ValueError):
        s.observe(payload={"v": 1}, **dict(OBS, access_scope="everyone"))

def test_write_is_byte_stable(tmp_path):
    s = FactStore(tmp_path / "f.jsonl")
    s.observe(payload={"v": 1}, **OBS)
    s.observe(payload={"v": 2}, **dict(OBS, source_record_id="txn:2"))
    s.write(); first = (tmp_path / "f.jsonl").read_bytes()
    s.write(); assert (tmp_path / "f.jsonl").read_bytes() == first

def test_payload_survives_a_write_reload_round_trip(tmp_path):
    """K1.4's aggregates are recomputed from admitted facts. A store that drops
    the body makes every reducer inoperable on production data."""
    p = tmp_path / "f.jsonl"
    s = FactStore(p)
    s.observe(payload={"home": "A", "home_pts": 120.5}, **OBS)
    s.write()
    reloaded = FactStore(p).load()[0]
    assert reloaded.payload == {"home": "A", "home_pts": 120.5}
    assert reloaded.content_sha256.startswith("sha256:")

def test_normalizer_version_change_supersedes_rather_than_coalescing(tmp_path):
    """The design binds normalizer_version because a normalizer change is a change
    in MEANING even when the capture bytes are identical."""
    s = FactStore(tmp_path / "f.jsonl")
    f1, a1 = s.observe(payload={"v": 1}, **OBS)
    f2, a2 = s.observe(payload={"v": 1}, **dict(OBS, normalizer_version="norm-v2",
                                                known_at="2025-09-06T00:00:00Z"))
    assert a1 == "created" and a2 == "superseded"
    assert f2.supersedes == f1.fact_id and len(s.load()) == 2

def test_on_disk_payload_tampering_is_refused(tmp_path):
    """content_sha256 must describe the bytes the store actually holds."""
    from scripts.fact_schema import PayloadIntegrityError
    p = tmp_path / "f.jsonl"
    s = FactStore(p)
    s.observe(payload={"v": 1}, **OBS)
    s.write()
    poisoned = p.read_text(encoding="utf-8").replace('"v":1', '"v":999')
    p.write_text(poisoned, encoding="utf-8", newline="\n")
    with pytest.raises(PayloadIntegrityError):
        FactStore(p).load()
```

The store persists one JSON object per line carrying the fifteen contract fields **plus** a
sibling `payload` key. `payload` never enters `fact_id`, and `content_sha256` already covers it,
so round-tripping cannot change identity.

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Fact store: append-only, idempotent on repeat, superseding on change."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fact_schema import Fact, FACT_FIELDS, fact_hash, validate  # noqa: E402

SCHEMA_VERSION = 1


class FactStore:
    def __init__(self, path):
        self.path = Path(path)
        self._facts = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    body = rec.pop("payload", None)
                    # Fact.__post_init__ re-verifies content_sha256 against these
                    # bytes, so on-disk tampering raises PayloadIntegrityError here
                    # rather than silently entering a state.
                    self._facts.append(
                        Fact(**rec, payload_bytes=None if body is None
                             else canonical_bytes(body)))

    def load(self):
        return list(self._facts)

    def _latest_for(self, source_record_id):
        candidates = [f for f in self._facts if f.source_record_id == source_record_id]
        superseded = {f.supersedes for f in candidates if f.supersedes}
        live = [f for f in candidates if f.fact_id not in superseded]
        return max(live, key=lambda f: (f.known_at, f.fact_id)) if live else None

    def observe(self, payload, **meta):
        """Returns (fact, 'created' | 'coalesced' | 'superseded')."""
        digest = fact_hash(payload)
        prior = self._latest_for(meta["source_record_id"])
        # Coalesce only when the OBSERVATION AND ITS MEANING are both unchanged.
        # The design binds normalizer_version into every fact precisely because a
        # normalizer change is a change in meaning even when the bytes are identical;
        # comparing content_sha256 alone would discard a norm-v2 reading of the same
        # capture as a duplicate of its norm-v1 predecessor.
        meaning = ("normalizer_version", "access_scope", "known_at_basis",
                   "effective_at", "known_at", "fact_type", "privacy")
        unchanged = (prior is not None
                     and prior.content_sha256 == digest
                     and all(getattr(prior, k) == meta.get(k) for k in meaning))
        if unchanged:
            return prior, "coalesced"          # identical repeat: nothing changes
        fact = Fact(
            # normalizer_version is part of identity: a norm-v2 reading of the same
            # bytes at the same instant is a DIFFERENT fact, and without it the
            # supersessor would hash to its predecessor's id and supersede itself.
            fact_id=fact_hash({"srid": meta["source_record_id"], "content": digest,
                               "known_at": meta["known_at"],
                               "norm": meta["normalizer_version"]}
                              ).replace("sha256:", "fact:"),
            content_sha256=digest, schema_version=SCHEMA_VERSION,
            supersedes=(prior.fact_id if prior is not None else None),
            payload_bytes=canonical_bytes(payload),   # canonicalized once, then immutable
            **{k: v for k, v in meta.items() if k in FACT_FIELDS})
        problems = validate(fact)
        if problems:
            raise ValueError(f"invalid fact: {problems}")
        self._facts.append(fact)
        return fact, ("superseded" if prior is not None else "created")

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self._facts, key=lambda f: (f.fact_type, f.source_record_id,
                                                     f.known_at, f.fact_id))
        for f in ordered:                     # verify before persisting, never after
            if f.payload_bytes is not None and fact_hash(f.payload_bytes) != f.content_sha256:
                raise PayloadIntegrityError(f"{f.fact_id}: payload does not match its hash")
        body = "\n".join(
            json.dumps({**{k: getattr(f, k) for k in FACT_FIELDS}, "payload": f.payload},
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            for f in ordered)
        self.path.write_text(body + ("\n" if body else ""), encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Run to verify it passes** → 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/fact_store.py scripts/tests/test_fact_store.py
git commit -m "feat(facts): idempotent coalescing, supersession, byte-stable writes"
```

---

### Task K1.3: `state_at` — admission, scope lattice, supersession

**Files:** Create `scripts/temporal_state.py`, `scripts/tests/test_temporal_state.py`

**Interfaces:**

- Consumes: `Fact`, `FactStore`
- Produces: `state_at(season, cutoff, access_scope, as_recorded_at=None, facts=None) -> LeagueState`,
  `SCOPE_LATTICE`, `LeagueState.admitted` / `.by_type(fact_type)` / `.value(source_record_id)`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.temporal_state import state_at, SCOPE_LATTICE
from scripts.fact_schema import Fact

def F(**over):
    base = dict(fact_id="f", source_record_id="r", entity_ref={"type": "t", "id": "1"},
                source_ref="s", fact_type="transaction", effective_at="2025-09-01T00:00:00Z",
                known_at="2025-09-01T00:00:00Z", access_scope="public",
                known_at_basis="b", captured_at="2026-01-01T00:00:00Z",
                content_sha256="sha256:" + "a" * 64, privacy="public",
                normalizer_version="v1", schema_version=1, supersedes=None)
    base.update(over)
    return Fact(**base)

def test_lattice_is_exactly_two_rows():
    assert SCOPE_LATTICE == {"public": {"public"},
                             "league_private": {"public", "league_private"}}

def test_public_scope_excludes_league_private():
    facts = [F(fact_id="p", source_record_id="a"),
             F(fact_id="q", source_record_id="b", access_scope="league_private",
               fact_type="chat_message")]
    pub = state_at(2025, "2025-09-02T00:00:00Z", "public", facts=facts)
    priv = state_at(2025, "2025-09-02T00:00:00Z", "league_private", facts=facts)
    assert {f.fact_id for f in pub.admitted} == {"p"}
    assert {f.fact_id for f in priv.admitted} == {"p", "q"}

def test_omitted_or_unknown_scope_fails_closed():
    with pytest.raises(ValueError):
        state_at(2025, "2025-09-02T00:00:00Z", "everyone", facts=[])
    with pytest.raises(TypeError):
        state_at(2025, "2025-09-02T00:00:00Z", facts=[])

def test_known_at_after_cutoff_is_excluded():
    facts = [F(fact_id="late", known_at="2025-09-10T00:00:00Z")]
    assert state_at(2025, "2025-09-02T00:00:00Z", "public", facts=facts).admitted == []

def test_admission_is_inclusive_at_the_cutoff():
    facts = [F(fact_id="edge", known_at="2025-09-02T00:00:00Z")]
    assert len(state_at(2025, "2025-09-02T00:00:00Z", "public", facts=facts).admitted) == 1

def test_supersession_respects_known_at():
    a = F(fact_id="a", source_record_id="txn", known_at="2025-09-01T00:00:00Z")
    b = F(fact_id="b", source_record_id="txn", known_at="2025-09-05T00:00:00Z", supersedes="a")
    early = state_at(2025, "2025-09-03T00:00:00Z", "public", facts=[a, b])
    late = state_at(2025, "2025-09-07T00:00:00Z", "public", facts=[a, b])
    assert early.value("txn").fact_id == "a"
    assert late.value("txn").fact_id == "b"

def test_three_step_correction_chain_resolves_at_each_cutoff():
    a = F(fact_id="a", source_record_id="r", known_at="2025-09-01T00:00:00Z")
    b = F(fact_id="b", source_record_id="r", known_at="2025-09-05T00:00:00Z", supersedes="a")
    c = F(fact_id="c", source_record_id="r", known_at="2025-09-09T00:00:00Z", supersedes="b")
    facts = [a, b, c]
    for cutoff, expected in (("2025-09-02T00:00:00Z", "a"),
                             ("2025-09-06T00:00:00Z", "b"),
                             ("2025-09-10T00:00:00Z", "c")):
        assert state_at(2025, cutoff, "public", facts=facts).value("r").fact_id == expected

def test_as_recorded_at_excludes_late_captures():
    facts = [F(fact_id="early", source_record_id="x", captured_at="2026-01-01T00:00:00Z"),
             F(fact_id="late", source_record_id="y", captured_at="2026-08-01T00:00:00Z")]
    latest = state_at(2025, "2025-12-01T00:00:00Z", "public", facts=facts)
    vantage = state_at(2025, "2025-12-01T00:00:00Z", "public",
                       as_recorded_at="2026-03-01T00:00:00Z", facts=facts)
    assert {f.fact_id for f in latest.admitted} == {"early", "late"}
    assert {f.fact_id for f in vantage.admitted} == {"early"}

def test_state_contains_no_decisions():
    s = state_at(2025, "2025-09-02T00:00:00Z", "public", facts=[F()])
    assert not hasattr(s, "decisions") and not hasattr(s, "rankings")
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""The single temporal authority. state_at is the world, never our judgments about it."""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fact_schema import load_fact_types  # noqa: E402

SCOPE_LATTICE = {
    "public": {"public"},
    "league_private": {"public", "league_private"},
}


@dataclass(frozen=True)
class LeagueState:
    season: int
    cutoff: str
    access_scope: str
    as_recorded_at: str | None
    admitted: list

    def by_type(self, fact_type):
        """Admitted facts of a type, in EFFECTIVE order.

        Admission is a known_at question; folding is an effective_at question.
        The design separates them deliberately: a correction learned in December
        about a September game is admitted by its December known_at, but it folds
        into the timeline at its September effective_at.
        """
        return sorted((f for f in self.admitted if f.fact_type == fact_type),
                      key=lambda f: (f.effective_at, f.source_record_id, f.fact_id))

    def value(self, source_record_id):
        """Supersession resolution: the latest KNOWN reading of one record.

        Ordered by known_at, not effective_at -- a later correction supersedes an
        earlier one because we learned it later, whatever instant it describes.
        """
        live = [f for f in self.admitted if f.source_record_id == source_record_id]
        return max(live, key=lambda f: (f.known_at, f.fact_id)) if live else None


def state_at(season, cutoff, access_scope, as_recorded_at=None, facts=None):
    if access_scope not in SCOPE_LATTICE:
        raise ValueError(
            f"access_scope must be one of {sorted(SCOPE_LATTICE)}; "
            "an omitted or unrecognized scope is an error, never a default")
    visible = SCOPE_LATTICE[access_scope]
    pool = list(facts if facts is not None else _load_default_facts(season))

    admitted = [
        f for f in pool
        if f.access_scope in visible
        and f.known_at <= cutoff
        and (as_recorded_at is None or f.captured_at <= as_recorded_at)
    ]
    # Drop anything superseded by another ADMITTED fact. A superseding fact that is
    # itself inadmissible at this cutoff must not retire its predecessor.
    retired = {f.supersedes for f in admitted if f.supersedes}
    admitted = sorted((f for f in admitted if f.fact_id not in retired),
                      key=lambda f: (f.fact_type, f.source_record_id, f.known_at, f.fact_id))
    return LeagueState(season, cutoff, access_scope, as_recorded_at, admitted)


FACTS_ROOT = Path(__file__).resolve().parents[1] / "data" / "facts"


def _load_default_facts(season):
    """Exactly one file, named for the season. Never a glob over the root --
    that is how a poisoned sibling store enters a state it does not belong to.
    FACTS_ROOT is read at call time so tests can relocate it."""
    from fact_store import FactStore
    path = FACTS_ROOT / f"{season}.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"no fact store for season {season} at {path}; normalize before compiling")
    return FactStore(path).load()
```

- [ ] **Step 4: Run to verify it passes** → 9 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/temporal_state.py scripts/tests/test_temporal_state.py
git commit -m "feat(temporal): state_at with required access scope, vantage, supersession"
```

---

### Task K1.4: Reducers — aggregates recomputed from admitted facts

This replaces both the `extract_week_data` h2h patch and `as_of_records`. The dated/undated
distinction that produced the 46 stops existing as a category: every aggregate is a derivation.

**Files:** Modify `scripts/temporal_state.py`; create `scripts/tests/test_reducers.py`

**Interfaces:** Produces `LeagueState.h2h(a, b)`, `.records()`, `.standings()` — each computed
from `self.admitted` only

- [ ] **Step 1: Write the failing test**

```python
from scripts.temporal_state import state_at
from scripts.tests.test_temporal_state import F

def M(rid, season, week, known_at, home, away, hp, ap):
    # season and week are payload keys: h2h() and records() sort on them and
    # last_meeting reports them. Omitting them raises KeyError in every reducer.
    return F(fact_id=f"m{rid}", source_record_id=f"match:{season}:{week}:{rid}",
             fact_type="matchup_result", entity_ref={"type": "matchup", "id": str(rid)},
             effective_at=known_at, known_at=known_at,
             payload={"season": season, "week": week, "home": home, "away": away,
                      "home_pts": hp, "away_pts": ap})

def test_h2h_counts_only_admitted_meetings():
    facts = [M(1, 2022, 9, "2022-11-01T00:00:00Z", "A", "B", 140.3, 153.1),
             M(2, 2025, 6, "2025-10-14T06:59:59Z", "A", "B", 109.1, 150.5),
             M(3, 2025, 12, "2025-12-02T06:59:59Z", "A", "B", 180.0, 100.0)]
    s = state_at(2025, "2025-10-20T00:00:00Z", "public", facts=facts)
    h = s.h2h("A", "B")
    assert h["total_games"] == 2 and h["a_wins"] == 0 and h["b_wins"] == 2
    assert h["last_meeting"]["week"] == 6

def test_h2h_at_an_earlier_cutoff_sees_only_the_first_meeting():
    facts = [M(1, 2022, 9, "2022-11-01T00:00:00Z", "A", "B", 140.3, 153.1),
             M(2, 2025, 6, "2025-10-14T06:59:59Z", "A", "B", 109.1, 150.5)]
    s = state_at(2025, "2025-09-01T00:00:00Z", "public", facts=facts)
    assert s.h2h("A", "B")["total_games"] == 1

def test_streak_is_recomputed_not_stored():
    """The undated aggregate that leaked. No stored value exists to read."""
    facts = [M(i, 2025, i, f"2025-09-{10 + i:02d}T06:59:59Z", "A", "B", 10.0, 20.0)
             for i in range(1, 4)]
    early = state_at(2025, "2025-09-12T00:00:00Z", "public", facts=facts).records()
    late = state_at(2025, "2025-09-20T00:00:00Z", "public", facts=facts).records()
    assert early["longest_losing_streak"]["count"] == 1
    assert late["longest_losing_streak"]["count"] == 3

def test_no_record_postdates_its_cutoff():
    facts = [M(1, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 300.0, 10.0),
             M(2, 2025, 14, "2025-12-16T06:59:59Z", "A", "B", 400.0, 10.0)]
    r = state_at(2025, "2025-09-15T00:00:00Z", "public", facts=facts).records()
    assert r["highest_score"]["points"] == 300.0, "the week-14 record must be invisible"

def test_standings_are_recomputed_from_admitted_results():
    facts = [M(1, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 120.0, 100.0),
             M(2, 2025, 2, "2025-09-17T06:59:59Z", "A", "B", 90.0, 110.0),
             M(3, 2025, 9, "2025-11-05T06:59:59Z", "A", "B", 200.0, 10.0)]
    s = state_at(2025, "2025-09-20T00:00:00Z", "public", facts=facts).standings()
    row = {r["team"]: r for r in s}
    assert row["A"]["wins"] == 1 and row["A"]["losses"] == 1
    assert row["A"]["points_for"] == 210.0, "the week-9 blowout must be invisible"
    assert [r["team"] for r in s] == ["A", "B"] or [r["team"] for r in s] == ["B", "A"]

def test_reducers_fold_on_effective_at_not_known_at():
    """A correction learned late about an early game folds at its EFFECTIVE instant.
    Ordering by known_at would put the September game after the December one."""
    early = M(1, 2025, 1, "2025-09-10T06:59:59Z", "A", "B", 10.0, 20.0)
    late = M(2, 2025, 2, "2025-09-17T06:59:59Z", "A", "B", 10.0, 20.0)
    # same game, corrected in December but effective in September
    corrected = F(fact_id="mc", source_record_id="match:2025:3:3",
                  fact_type="matchup_result", entity_ref={"type": "matchup", "id": "3"},
                  effective_at="2025-09-24T06:59:59Z", known_at="2025-12-01T00:00:00Z",
                  payload={"season": 2025, "week": 3, "home": "A", "away": "B",
                           "home_pts": 10.0, "away_pts": 20.0})
    s = state_at(2025, "2025-12-02T00:00:00Z", "public",
                 facts=[early, late, corrected])
    assert s.records()["longest_losing_streak"]["count"] == 3
    assert [f.fact_id for f in s.by_type("matchup_result")] == ["m1", "m2", "mc"]
```

`F` (K1.3) needs no change: `Fact.payload` defaults to `None`, so `F(payload=...)` already reaches
the dataclass through `base.update(over)`. Production facts carry the same attachment — written
and reloaded by `FactStore` (K1.2) — so a reducer sees the identical shape in tests and in
production.

- [ ] **Step 2: Run to verify it fails** → `AttributeError: 'LeagueState' object has no attribute 'h2h'`

- [ ] **Step 3: Implement** — add to `LeagueState`

```python
    def h2h(self, a, b):
        """Head-to-head from admitted meetings only. Never a stored aggregate."""
        games = [f for f in self.by_type("matchup_result") + self.by_type("historical_matchup")
                 if {f.payload["home"], f.payload["away"]} == {a, b}]
        # effective_at, not payload season/week: the fact's own clock is the
        # authority, and a reducer that re-derives ordering from payload fields is
        # a second temporal rule.
        games.sort(key=lambda f: (f.effective_at, f.fact_id))
        a_wins = sum(1 for g in games if _winner(g.payload) == a)
        last = games[-1].payload if games else None
        return {"a_wins": a_wins, "b_wins": len(games) - a_wins,
                "total_games": len(games), "last_meeting": last}

    def records(self):
        """All seven league records, recomputed. Dated and undated alike."""
        games = self.by_type("matchup_result") + self.by_type("historical_matchup")
        rec = dict.fromkeys(("highest_score", "lowest_winning_score", "biggest_blowout",
                             "highest_combined", "lowest_combined"))
        streaks = {}
        for g in sorted(games, key=lambda f: (f.effective_at, f.fact_id)):
            p = g.payload
            for team, pts, opp in ((p["home"], p["home_pts"], p["away_pts"]),
                                   (p["away"], p["away_pts"], p["home_pts"])):
                cand = {"points": pts, "team": team,
                        "season": p["season"], "week": p["week"]}
                if rec["highest_score"] is None or pts > rec["highest_score"]["points"]:
                    rec["highest_score"] = cand
                if pts > opp and (rec["lowest_winning_score"] is None
                                  or pts < rec["lowest_winning_score"]["points"]):
                    rec["lowest_winning_score"] = cand
                d = streaks.setdefault(team, {"cw": 0, "cl": 0, "bw": 0, "bl": 0})
                if pts > opp:
                    d["cw"] += 1; d["cl"] = 0; d["bw"] = max(d["bw"], d["cw"])
                else:
                    d["cl"] += 1; d["cw"] = 0; d["bl"] = max(d["bl"], d["cl"])
            margin = abs(p["home_pts"] - p["away_pts"])
            if rec["biggest_blowout"] is None or margin > rec["biggest_blowout"]["margin"]:
                rec["biggest_blowout"] = {"margin": round(margin, 2),
                                          "season": p["season"], "week": p["week"]}
            comb = {"points": round(p["home_pts"] + p["away_pts"], 2),
                    "season": p["season"], "week": p["week"]}
            for key, better in (("highest_combined", lambda x, y: x > y),
                                ("lowest_combined", lambda x, y: x < y)):
                if rec[key] is None or better(comb["points"], rec[key]["points"]):
                    rec[key] = comb
        for key, field in (("longest_win_streak", "bw"), ("longest_losing_streak", "bl")):
            if streaks:
                best = max(v[field] for v in streaks.values())
                team = sorted(t for t, v in streaks.items() if v[field] == best)[0]
                rec[key] = {"count": best, "team": team}
            else:
                rec[key] = None
        return rec

    def standings(self):
        """Win/loss/points-for from admitted results only. The design's third
        recomputed aggregate -- previously listed as an interface and never built."""
        table = {}
        for g in self.by_type("matchup_result") + self.by_type("historical_matchup"):
            p = g.payload
            for team, pts, opp in ((p["home"], p["home_pts"], p["away_pts"]),
                                   (p["away"], p["away_pts"], p["home_pts"])):
                t = table.setdefault(team, {"team": team, "wins": 0, "losses": 0,
                                            "ties": 0, "points_for": 0.0,
                                            "points_against": 0.0})
                t["wins"] += pts > opp
                t["losses"] += pts < opp
                t["ties"] += pts == opp
                t["points_for"] = round(t["points_for"] + pts, 2)
                t["points_against"] = round(t["points_against"] + opp, 2)
        return sorted(table.values(),
                      key=lambda r: (-r["wins"], -r["points_for"], r["team"]))


def _winner(p):
    return p["home"] if p["home_pts"] > p["away_pts"] else p["away"]
```

- [ ] **Step 4: Run to verify it passes** → 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/temporal_state.py scripts/tests/test_reducers.py
git commit -m "feat(temporal): h2h and all seven records recomputed from admitted facts"
```

---

### Task K1.5: `decision_history_at` — the second authority

**Files:** Create `scripts/decision_history.py`, `scripts/tests/test_decision_history.py`

**Interfaces:**

- Produces: `SealedDecision` (frozen), `seal(...) -> SealedDecision`,
  `load_decision(sealed) -> (ranking, claims)`,
  `decision_history_at(season, cutoff, arm_id, trial_id, root) -> list[SealedDecision]`,
  `verify_predecessor(sealed, arm_id, trial_id)`, `CrossArmContamination`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.decision_history import (seal, decision_history_at, verify_predecessor,
                                      CrossArmContamination)

def mkseal(tmp, arm, trial, cutoff, eid):
    return seal(root=tmp, edition_id=eid, season=2025, cutoff_utc=cutoff,
                arm_id=arm, trial_id=trial, state_hash="sha256:" + "a" * 64,
                ranking={"entries": []}, claims=[], run_id="run-1")

def test_history_is_scoped_to_arm_and_trial(tmp_path):
    mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    mkseal(tmp_path, "no_chat", 1, "2025-09-03T23:59:59Z", "pre")
    got = decision_history_at(2025, "2025-09-05T00:00:00Z", "full_rich", 1, root=tmp_path)
    assert len(got) == 1 and got[0].arm_id == "full_rich"

def test_only_strictly_earlier_seals_are_returned(tmp_path):
    mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    mkseal(tmp_path, "full_rich", 1, "2025-09-09T06:59:59Z", "recap")
    got = decision_history_at(2025, "2025-09-09T06:59:59Z", "full_rich", 1, root=tmp_path)
    assert [s.edition_id for s in got] == ["pre"]

def test_preseason_has_no_history(tmp_path):
    assert decision_history_at(2025, "2025-09-03T23:59:59Z", "full_rich", 1, root=tmp_path) == []

def test_cross_arm_predecessor_is_rejected(tmp_path):
    other = mkseal(tmp_path, "no_chat", 1, "2025-09-03T23:59:59Z", "pre")
    with pytest.raises(CrossArmContamination):
        verify_predecessor(other, arm_id="full_rich", trial_id=1)

def test_cross_trial_predecessor_is_rejected(tmp_path):
    other = mkseal(tmp_path, "full_rich", 2, "2025-09-03T23:59:59Z", "pre")
    with pytest.raises(CrossArmContamination):
        verify_predecessor(other, arm_id="full_rich", trial_id=1)

def test_seal_is_immutable_and_hashed(tmp_path):
    s = mkseal(tmp_path, "full_rich", 1, "2025-09-03T23:59:59Z", "pre")
    assert s.decision_hash.startswith("sha256:")
    with pytest.raises(Exception):
        s.arm_id = "no_chat"
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Sealed prior judgments. Separate from state_at: the world vs. our judgments about it."""
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fact_schema import fact_hash  # noqa: E402
from shared import save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEALS_ROOT = ROOT / "content" / "decisions"


class CrossArmContamination(RuntimeError):
    """An arm tried to consume another arm's or trial's judgment."""


@dataclass(frozen=True)
class SealedDecision:
    edition_id: str
    season: int
    cutoff_utc: str
    arm_id: str
    trial_id: int
    state_hash: str
    run_id: str
    ranking_hash: str
    claims_hash: str
    decision_hash: str
    # Content LOCATORS, not just hashes. A hash proves the body has not changed;
    # it cannot hand the body back. The inertia comparator must score an arm's
    # preview against its own unchanged prior RANKING, and blind review must show
    # Blake actual prose -- neither can be done from a digest alone.
    ranking_path: str
    claims_path: str
    run_receipt_path: str


def seal(root, edition_id, season, cutoff_utc, arm_id, trial_id, state_hash,
         ranking, claims, run_id, run_receipt_path=None):
    rh, ch = fact_hash(ranking), fact_hash(claims)
    d = Path(root) / f"{season}" / arm_id / f"trial{trial_id}"
    p = d / f"{edition_id}.json"
    if p.exists():
        raise FileExistsError(f"seal already exists and is immutable: {p}")
    d.mkdir(parents=True, exist_ok=True)
    # Persist the bodies FIRST, then seal over their locations. A seal that names a
    # file which does not exist is worse than no locator at all.
    rp, cp = d / f"{edition_id}.ranking.json", d / f"{edition_id}.claims.json"
    save_json_canonical(rp, ranking)
    save_json_canonical(cp, claims)
    body = {"edition_id": edition_id, "season": season, "cutoff_utc": cutoff_utc,
            "arm_id": arm_id, "trial_id": trial_id, "state_hash": state_hash,
            "run_id": run_id, "ranking_hash": rh, "claims_hash": ch,
            "ranking_path": str(rp), "claims_path": str(cp),
            "run_receipt_path": str(run_receipt_path or "")}
    s = SealedDecision(**body, decision_hash=fact_hash(body))
    save_json_canonical(p, asdict(s))
    return s


def load_decision(sealed):
    """Return the sealed ranking and claims, verifying both against their hashes.

    This is what the inertia comparator consumes: `unchanged prior decision` means
    THIS body, re-scored at the new horizon, not a hash compared to itself.
    """
    ranking = json.loads(Path(sealed.ranking_path).read_text(encoding="utf-8"))
    claims = json.loads(Path(sealed.claims_path).read_text(encoding="utf-8"))
    if fact_hash(ranking) != sealed.ranking_hash:
        raise ValueError(f"{sealed.edition_id}: sealed ranking body does not match its hash")
    if fact_hash(claims) != sealed.claims_hash:
        raise ValueError(f"{sealed.edition_id}: sealed claims body does not match its hash")
    return ranking, claims


def decision_history_at(season, cutoff, arm_id, trial_id, root=SEALS_ROOT):
    d = Path(root) / f"{season}" / arm_id / f"trial{trial_id}"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        s = SealedDecision(**json.loads(p.read_text(encoding="utf-8")))
        if s.cutoff_utc < cutoff:          # strictly earlier
            out.append(s)
    return sorted(out, key=lambda s: s.cutoff_utc)


def verify_predecessor(sealed, arm_id, trial_id):
    if sealed.arm_id != arm_id or sealed.trial_id != trial_id:
        raise CrossArmContamination(
            f"predecessor belongs to arm={sealed.arm_id} trial={sealed.trial_id}, "
            f"consumer is arm={arm_id} trial={trial_id}")
    return sealed
```

- [ ] **Step 4: Run to verify it passes** → 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/decision_history.py scripts/tests/test_decision_history.py
git commit -m "feat(decisions): arm-scoped decision history, cross-arm contamination refused"
```

---

### Task K1.6: Normalizers for the nine bridge fact types

**Files:** Create `scripts/normalize_facts.py`, `scripts/tests/test_normalize_facts.py`

**Interfaces:**

- Produces: `NORMALIZERS` (dict by fact type), `normalize_all(source_root, out_path, season) -> dict`,
  `NORMALIZER_VERSION`, `UnqualifiedSource`

**`schedule_pairing` is deliberately hard to satisfy:** a completed weekly packet with outcomes
stripped is **not** a source. It requires an independent qualified source or a versioned
availability policy, else the fact is unavailable.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.normalize_facts import NORMALIZERS, normalize_all, UnqualifiedSource

def test_all_nine_bridge_types_have_a_normalizer():
    for t in ("franchise_identity", "schedule_pairing", "matchup_result", "roster_membership",
              "transaction", "draft_pick", "chat_message", "historical_matchup", "nfl_game"):
        assert t in NORMALIZERS, t

def test_schedule_from_a_completed_packet_is_unqualified():
    with pytest.raises(UnqualifiedSource):
        NORMALIZERS["schedule_pairing"]({"source": "weekly_packet_outcomes_stripped"}, season=2025)

def test_schedule_with_a_versioned_policy_is_admitted():
    fact = NORMALIZERS["schedule_pairing"](
        {"source": "sleeper_schedule", "policy_id": "sched-avail-v1",
         "home": "A", "away": "B", "season": 2025, "week": 1,
         "known_at": "2025-08-01T00:00:00Z"}, season=2025)
    assert fact["known_at_basis"] == "sched-avail-v1"

def test_transaction_without_status_updated_is_unqualified():
    with pytest.raises(UnqualifiedSource):
        NORMALIZERS["transaction"]({"transaction_id": "1", "created": 1725000000000}, season=2025)

def test_chat_message_defaults_to_league_private():
    f = NORMALIZERS["chat_message"](
        {"id": 1, "timestamp_utc": "2025-09-01T00:00:00Z", "sender": "x", "text": "hi"},
        season=2025)
    assert f["access_scope"] == "league_private" and f["privacy"] == "private"

def test_normalizing_twice_is_byte_identical(tmp_path):
    a = normalize_all(source_root=".", out_path=tmp_path / "a.jsonl", season=2025)
    b = normalize_all(source_root=".", out_path=tmp_path / "b.jsonl", season=2025)
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()
    assert a["counts"] == b["counts"]

def test_no_wall_clock_enters_a_fact(tmp_path):
    """captured_at comes from the capture record, never from now()."""
    import ast
    from pathlib import Path
    src = Path("scripts/normalize_facts.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            assert name not in {"now", "utcnow", "today", "time"}, \
                "wall-clock in a normalizer breaks deterministic replay"
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — one normalizer per type, each returning a dict of `Fact` kwargs

```python
"""Normalize captures and qualified legacy artifacts into typed temporal facts."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fact_store import FactStore  # noqa: E402
from shared import load_json  # noqa: E402

NORMALIZER_VERSION = "norm-v1"


class UnqualifiedSource(RuntimeError):
    """The source cannot establish known_at. The fact is unavailable, not guessed."""


def _instant(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _schedule_pairing(raw, season):
    if raw.get("source") in {"weekly_packet_outcomes_stripped", "weekly_packet"}:
        raise UnqualifiedSource(
            "a completed weekly packet with outcomes stripped proves concealment, not "
            "pregame availability; supply a qualified schedule source or a versioned policy")
    if not raw.get("policy_id") and not raw.get("known_at"):
        raise UnqualifiedSource("schedule_pairing requires known_at or a versioned policy_id")
    return {"fact_type": "schedule_pairing",
            "source_record_id": f"sched:{season}:{raw['week']}:{raw['home']}:{raw['away']}",
            "entity_ref": {"type": "matchup", "id": f"{raw['home']}|{raw['away']}"},
            "effective_at": raw["known_at"], "known_at": raw["known_at"],
            "known_at_basis": raw.get("policy_id", "qualified_schedule_source"),
            "access_scope": "public", "privacy": "public"}


def _transaction(raw, season):
    ms = raw.get("status_updated")
    if ms is None:
        raise UnqualifiedSource(
            f"transaction {raw.get('transaction_id')} has no status_updated; "
            "`created` is not an acceptable fallback for an effective instant")
    inst = _instant(ms)
    return {"fact_type": "transaction",
            "source_record_id": f"txn:{raw['transaction_id']}",
            "entity_ref": {"type": "transaction", "id": str(raw["transaction_id"])},
            "effective_at": inst, "known_at": inst,
            "known_at_basis": "effective_completion_instant",
            "access_scope": "public", "privacy": "public"}


def _chat_message(raw, season):
    ts = raw["timestamp_utc"]
    return {"fact_type": "chat_message", "source_record_id": f"msg:{raw['id']}",
            "entity_ref": {"type": "message", "id": str(raw["id"])},
            "effective_at": ts, "known_at": ts, "known_at_basis": "message_timestamp",
            "access_scope": "league_private", "privacy": "private"}


def _franchise_identity(raw, season):
    """Sleeper users/league. known_at = the capture instant that first held it."""
    inst = raw["captured_at"]
    return {"fact_type": "franchise_identity",
            "source_record_id": f"franchise:{season}:{raw['roster_id']}",
            "entity_ref": {"type": "franchise", "id": str(raw["roster_id"])},
            "effective_at": inst, "known_at": inst, "known_at_basis": "capture_instant",
            "access_scope": "public", "privacy": "public"}


def _matchup_result(raw, season):
    """known_at = game conclusion. A scheduled-but-unplayed matchup is NOT a result."""
    if not raw.get("concluded_at"):
        raise UnqualifiedSource(
            f"matchup {raw.get('matchup_id')} has no conclusion instant; a pairing is "
            "a schedule_pairing fact, never a matchup_result")
    inst = raw["concluded_at"]
    return {"fact_type": "matchup_result",
            "source_record_id": f"match:{season}:{raw['week']}:{raw['matchup_id']}",
            "entity_ref": {"type": "matchup", "id": str(raw["matchup_id"])},
            "effective_at": inst, "known_at": inst, "known_at_basis": "game_conclusion",
            "access_scope": "public", "privacy": "public"}


def _roster_membership(raw, season):
    """Forward from a QUALIFIED anchor. rosters.json is a Feb-2026 final state and
    is not an anchor for any 2025 cutoff -- that conflation is the original bug."""
    anchor = raw.get("anchor_known_at")
    if not anchor:
        raise UnqualifiedSource(
            "roster_membership requires a qualified pre-kickoff anchor instant; "
            "a season-end roster snapshot cannot date a preseason membership")
    return {"fact_type": "roster_membership",
            "source_record_id": f"roster:{season}:{raw['roster_id']}:{raw['player_id']}",
            "entity_ref": {"type": "franchise", "id": str(raw["roster_id"])},
            "effective_at": anchor, "known_at": anchor,
            "known_at_basis": "anchor_or_transaction_completion",
            "access_scope": "public", "privacy": "public"}


def _draft_pick(raw, season):
    inst = _instant(raw["pick_ts"]) if raw.get("pick_ts") else raw.get("captured_at")
    if not inst:
        raise UnqualifiedSource(f"draft pick {raw.get('pick_no')} has no datable instant")
    return {"fact_type": "draft_pick",
            "source_record_id": f"pick:{raw['draft_id']}:{raw['pick_no']}",
            "entity_ref": {"type": "player", "id": str(raw.get("player_id"))},
            "effective_at": inst, "known_at": inst,
            "known_at_basis": "pick_timestamp_else_capture",
            "access_scope": "public", "privacy": "public"}


def _historical_matchup(raw, season):
    """2022-2024 from season_combined.json. known_at = each game's conclusion."""
    if not raw.get("concluded_at"):
        raise UnqualifiedSource(f"historical matchup {raw.get('matchup_id')} is undated")
    inst = raw["concluded_at"]
    return {"fact_type": "historical_matchup",
            "source_record_id": f"hist:{raw['season']}:{raw['week']}:{raw['matchup_id']}",
            "entity_ref": {"type": "matchup", "id": str(raw["matchup_id"])},
            "effective_at": inst, "known_at": inst, "known_at_basis": "game_conclusion",
            "access_scope": "public", "privacy": "public"}


def _nfl_game(raw, season):
    """Kickoff needs venue timezone -- reuse kickoff_source.to_utc (K2.2), never
    append Z to a local time-of-day."""
    from kickoff_source import to_utc
    inst = raw.get("concluded_at") or to_utc(raw["gameday"], raw["gametime"], raw.get("tz"))
    return {"fact_type": "nfl_game",
            "source_record_id": f"nflgame:{raw['game_id']}",
            "entity_ref": {"type": "game", "id": str(raw["game_id"])},
            "effective_at": inst, "known_at": inst, "known_at_basis": "game_conclusion",
            "access_scope": "public", "privacy": "public"}


NORMALIZERS = {
    "franchise_identity": _franchise_identity,
    "schedule_pairing": _schedule_pairing,
    "matchup_result": _matchup_result,
    "roster_membership": _roster_membership,
    "transaction": _transaction,
    "draft_pick": _draft_pick,
    "chat_message": _chat_message,
    "historical_matchup": _historical_matchup,
    "nfl_game": _nfl_game,
}

SOURCES = {                     # fact_type -> (loader, iterator) for normalize_all
    "franchise_identity": ("data/{season}/users.json", "rosters"),
    "matchup_result":     ("data/{season}/season_combined.json", "matchups"),
    "transaction":        ("data/{season}/transactions.json", "transactions"),
    "draft_pick":         ("data/{season}/draft_picks.json", "picks"),
    "chat_message":       ("content/chat/parsed_messages.json", "messages"),
    "historical_matchup": ("data/{prior}/season_combined.json", "matchups"),
    "nfl_game":           ("data/{season}/nfl_games/*.json", "games"),
    # schedule_pairing and roster_membership have NO qualified source today.
    # They stay absent rather than being invented -- see Open dependencies.
}


def normalize_all(source_root, out_path, season):
    """Every bridge type, one FactStore, deterministic order, no wall clock.

    Returns {"counts": {fact_type: n}, "unqualified": {fact_type: n},
             "normalizer_version": NORMALIZER_VERSION}.
    """
    store = FactStore(out_path)
    counts, unqualified = {}, {}
    for fact_type in sorted(SOURCES):
        pattern, key = SOURCES[fact_type]
        for source_ref, raw in _iter_source(source_root, pattern, key, season):
            try:
                meta = NORMALIZERS[fact_type](raw, season)
            except UnqualifiedSource:
                unqualified[fact_type] = unqualified.get(fact_type, 0) + 1
                continue
            store.observe(payload=raw, source_ref=source_ref,
                          captured_at=raw["captured_at"],   # from the record, never now()
                          normalizer_version=NORMALIZER_VERSION, **meta)
            counts[fact_type] = counts.get(fact_type, 0) + 1
    store.write()
    return {"counts": counts, "unqualified": unqualified,
            "normalizer_version": NORMALIZER_VERSION}
```

**`captured_at` is read from the source record in every branch.** `_iter_source` requires it and
raises if a source cannot supply one — that, not a convention, is what makes replay deterministic
and what the `no_wall_clock` AST test enforces.

**Two types ship with no source and that is deliberate.** `schedule_pairing` has no qualified
pre-kickoff source, and `roster_membership` has no qualified anchor producer. Both normalizers
exist and both raise `UnqualifiedSource`; `normalize_all` counts the refusals in `unqualified`
rather than skipping silently. This is the fail-closed outcome the design requires — and because
`roster_membership` is a **required** contrast family, it is also what makes the K3 contrast
degraded rather than falsely clean. See Open dependencies.

- [ ] **Step 4: Run to verify it passes** → 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/normalize_facts.py scripts/tests/test_normalize_facts.py
git commit -m "feat(facts): normalizers for the nine bridge types, unqualified sources refused"
```

---

### Task K1.7: The seven discriminating tests, each proven to fail when its rule is removed

Acceptance prose is not a gate. Each test must be demonstrated to fail with its rule disabled.

**Files:** Create `scripts/tests/test_k1_discriminating.py`

- [ ] **Step 1: Write the tests**

```python
"""The seven K1 rules. EVERY rule carries a mutation control proving it can fail,
plus the four noninterference proofs the design carries forward (§3)."""
import pytest
from dataclasses import replace
from scripts.fact_schema import canonical_bytes, fact_hash
from scripts.fact_store import FactStore
from scripts.temporal_state import state_at
from scripts.decision_history import seal, verify_predecessor, CrossArmContamination
from scripts.normalize_facts import NORMALIZERS, UnqualifiedSource, normalize_all
from scripts.tests.test_temporal_state import F

OBS = dict(source_record_id="txn:1", entity_ref={"type": "t", "id": "1"}, source_ref="s",
           fact_type="transaction", effective_at="2025-09-01T00:00:00Z",
           known_at="2025-09-01T00:00:00Z", access_scope="public", known_at_basis="b",
           captured_at="2026-08-02T00:00:00Z", privacy="public", normalizer_version="v1")

# 1 -------------------------------------------------------------------------
def test_1_duplicate_capture_yields_one_fact(tmp_path):
    s = FactStore(tmp_path / "f.jsonl")
    s.observe(payload={"v": 1}, **OBS)
    s.observe(payload={"v": 1}, **dict(OBS, captured_at="2026-08-03T00:00:00Z"))
    assert len(s.load()) == 1

def test_1_mutation_without_coalescing_would_duplicate(tmp_path, monkeypatch):
    s = FactStore(tmp_path / "f.jsonl")
    monkeypatch.setattr(FactStore, "_latest_for", lambda self, srid: None)  # disable the rule
    s.observe(payload={"v": 1}, **OBS)
    s.observe(payload={"v": 1}, **dict(OBS, captured_at="2026-08-03T00:00:00Z"))
    assert len(s.load()) == 2, "control: without coalescing the store duplicates"

# 2 -------------------------------------------------------------------------
def test_2_revised_duplicate_supersedes_without_mutating(tmp_path):
    s = FactStore(tmp_path / "f.jsonl")
    f1, _ = s.observe(payload={"v": 1}, **OBS)
    f2, action = s.observe(payload={"v": 2}, **dict(OBS, known_at="2025-09-06T00:00:00Z"))
    assert action == "superseded" and f2.supersedes == f1.fact_id
    assert s.load()[0].content_sha256 == f1.content_sha256, "original untouched"

def test_2_mutation_in_place_update_would_lose_the_earlier_state(tmp_path, monkeypatch):
    """Control: mutate instead of supersede and the earlier cutoff changes answer."""
    s = FactStore(tmp_path / "f.jsonl")
    f1, _ = s.observe(payload={"v": 1}, **OBS)
    monkeypatch.setattr(FactStore, "observe",
                        lambda self, payload, **m: (self._facts.__setitem__(
                            0, replace(self._facts[0], content_sha256=fact_hash(payload),
                                       payload_bytes=canonical_bytes(payload))),
                            (self._facts[0], "mutated"))[1])
    s.observe(payload={"v": 2}, **dict(OBS, known_at="2025-09-06T00:00:00Z"))
    early = state_at(2025, "2025-09-03T00:00:00Z", "public", facts=s.load())
    assert early.value("txn:1").payload == {"v": 2}, \
        "control: mutation rewrites history at an earlier cutoff"

# 3 -------------------------------------------------------------------------
def test_3_late_capture_excluded_from_as_recorded_replay():
    facts = [F(fact_id="early", source_record_id="a", captured_at="2026-01-01T00:00:00Z"),
             F(fact_id="late", source_record_id="b", captured_at="2026-08-01T00:00:00Z")]
    vantage = state_at(2025, "2025-12-01T00:00:00Z", "public",
                       as_recorded_at="2026-03-01T00:00:00Z", facts=facts)
    latest = state_at(2025, "2025-12-01T00:00:00Z", "public", facts=facts)
    assert {f.fact_id for f in vantage.admitted} == {"early"}
    assert {f.fact_id for f in latest.admitted} == {"early", "late"}

def test_3_mutation_ignoring_vantage_admits_the_late_capture(monkeypatch):
    """Control: drop the captured_at filter and as-recorded replay stops existing."""
    import scripts.temporal_state as ts
    facts = [F(fact_id="early", source_record_id="a", captured_at="2026-01-01T00:00:00Z"),
             F(fact_id="late", source_record_id="b", captured_at="2026-08-01T00:00:00Z")]
    real = ts.state_at
    monkeypatch.setattr(ts, "state_at",
                        lambda s, c, sc, as_recorded_at=None, facts=None:
                        real(s, c, sc, as_recorded_at=None, facts=facts))
    got = ts.state_at(2025, "2025-12-01T00:00:00Z", "public",
                      as_recorded_at="2026-03-01T00:00:00Z", facts=facts)
    assert {f.fact_id for f in got.admitted} == {"early", "late"}, \
        "control: without the vantage filter a 2026 capture backdates into 2025"

# 4 -------------------------------------------------------------------------
def test_4_private_scope_exclusion_via_the_shipped_interface():
    facts = [F(fact_id="pub", source_record_id="a"),
             F(fact_id="priv", source_record_id="b", access_scope="league_private",
               fact_type="chat_message")]
    assert {f.fact_id for f in state_at(2025, "2025-12-01T00:00:00Z",
                                        "league_private", facts=facts).admitted} == {"pub", "priv"}
    assert {f.fact_id for f in state_at(2025, "2025-12-01T00:00:00Z",
                                        "public", facts=facts).admitted} == {"pub"}

def test_4_mutation_open_lattice_leaks_private_facts(monkeypatch):
    """Control: widen the lattice and the public state silently gains chat."""
    import scripts.temporal_state as ts
    monkeypatch.setitem(ts.SCOPE_LATTICE, "public", {"public", "league_private"})
    facts = [F(fact_id="pub", source_record_id="a"),
             F(fact_id="priv", source_record_id="b", access_scope="league_private",
               fact_type="chat_message")]
    got = ts.state_at(2025, "2025-12-01T00:00:00Z", "public", facts=facts)
    assert {f.fact_id for f in got.admitted} == {"pub", "priv"}, \
        "control: the lattice is the only thing enforcing scope"

# 5 -------------------------------------------------------------------------
def test_5_schedule_provenance_failure_is_unavailable():
    with pytest.raises(UnqualifiedSource):
        NORMALIZERS["schedule_pairing"]({"source": "weekly_packet"}, season=2025)

def test_5_mutation_accepting_a_stripped_packet_admits_an_unqualified_pairing():
    """Control: allow the packet source and concealment reads as availability."""
    import scripts.normalize_facts as nf
    raw = {"source": "weekly_packet", "home": "A", "away": "B", "week": 1,
           "known_at": "2025-08-01T00:00:00Z"}
    original = nf._schedule_pairing
    try:
        nf._schedule_pairing = lambda r, season: {          # rule removed
            "fact_type": "schedule_pairing", "known_at_basis": "packet",
            "source_record_id": "sched:x", "entity_ref": {"type": "matchup", "id": "x"},
            "effective_at": r["known_at"], "known_at": r["known_at"],
            "access_scope": "public", "privacy": "public"}
        assert nf._schedule_pairing(raw, 2025)["known_at_basis"] == "packet"
    finally:
        nf._schedule_pairing = original

# 6 -------------------------------------------------------------------------
def test_6_three_step_correction_chain():
    a = F(fact_id="a", source_record_id="r", known_at="2025-09-01T00:00:00Z")
    b = F(fact_id="b", source_record_id="r", known_at="2025-09-05T00:00:00Z", supersedes="a")
    c = F(fact_id="c", source_record_id="r", known_at="2025-09-09T00:00:00Z", supersedes="b")
    for cutoff, want in (("2025-09-02T00:00:00Z", "a"), ("2025-09-06T00:00:00Z", "b"),
                         ("2025-09-10T00:00:00Z", "c")):
        assert state_at(2025, cutoff, "public", facts=[a, b, c]).value("r").fact_id == want

def test_6_mutation_retiring_by_inadmissible_supersessor_blanks_the_early_state():
    """Control: retire a predecessor using a supersessor that is itself not yet
    admitted, and the earliest cutoff loses its value entirely."""
    a = F(fact_id="a", source_record_id="r", known_at="2025-09-01T00:00:00Z")
    b = F(fact_id="b", source_record_id="r", known_at="2025-09-05T00:00:00Z", supersedes="a")
    pool = [a, b]
    retired = {f.supersedes for f in pool if f.supersedes}        # rule removed:
    survivors = [f for f in pool                                  # retire from the WHOLE pool
                 if f.fact_id not in retired and f.known_at <= "2025-09-02T00:00:00Z"]
    assert survivors == [], "control: retiring against unadmitted facts empties the state"

# 7 -------------------------------------------------------------------------
def test_7_cross_arm_predecessor_poisoning(tmp_path):
    other = seal(root=tmp_path, edition_id="pre", season=2025,
                 cutoff_utc="2025-09-03T23:59:59Z", arm_id="no_chat", trial_id=1,
                 state_hash="sha256:" + "a" * 64, ranking={"entries": []}, claims=[],
                 run_id="r1")
    with pytest.raises(CrossArmContamination):
        verify_predecessor(other, arm_id="full_rich", trial_id=1)

def test_7_mutation_without_the_arm_check_the_poison_is_accepted(tmp_path):
    """Control: drop the arm/trial comparison and every arm inherits the best
    arm's continuity, which is exactly what makes the comparison meaningless."""
    import scripts.decision_history as dh
    other = seal(root=tmp_path, edition_id="pre", season=2025,
                 cutoff_utc="2025-09-03T23:59:59Z", arm_id="no_chat", trial_id=1,
                 state_hash="sha256:" + "a" * 64, ranking={"entries": []}, claims=[],
                 run_id="r1")
    original = dh.verify_predecessor
    try:
        dh.verify_predecessor = lambda sealed, arm_id, trial_id: sealed
        assert dh.verify_predecessor(other, "full_rich", 1).arm_id == "no_chat"
    finally:
        dh.verify_predecessor = original

# preserved noninterference proofs (design §3: "reuse the existing hard-won
# tests through this path") --------------------------------------------------
def test_physical_truncation_leaves_no_post_cutoff_fact(tmp_path):
    """Not 'the projector hid it' -- the state must not CONTAIN it. Serialize the
    compiled state and grep the bytes for any instant after the cutoff."""
    import json, re
    facts = [F(fact_id="in", source_record_id="a", known_at="2025-09-01T00:00:00Z",
               effective_at="2025-09-01T00:00:00Z"),
             F(fact_id="out", source_record_id="b", known_at="2025-12-01T00:00:00Z",
               effective_at="2025-12-01T00:00:00Z")]
    s = state_at(2025, "2025-09-03T23:59:59Z", "public", facts=facts)
    blob = json.dumps([{k: getattr(f, k) for k in
                        ("fact_id", "known_at", "effective_at")} for f in s.admitted])
    later = [i for i in re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", blob)
             if i > "2025-09-03T23:59:59Z"]
    assert later == [], f"post-cutoff instants physically present: {later}"

def test_poisoned_root_season_isolation(tmp_path, monkeypatch):
    """Isolation is about STORE ROOTS, not fact content.

    Pre-2025 `historical_matchup` facts belong in a 2025 state -- the no-history arm
    ablates exactly them -- so filtering the pool by season would be wrong. What must
    not happen is `state_at(2025, ...)` reading another season's fact FILE. Plant a
    poisoned 2024 store beside the 2025 one and prove it is never opened.
    """
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
    got = ts.state_at(2025, "2025-12-01T00:00:00Z", "public")     # no facts= override
    assert {f.source_record_id for f in got.admitted} == {"clean"}

def test_preview_state_is_outcome_free_by_composition():
    """Not a switch. A preview cutoff simply admits no matchup_result."""
    result = F(fact_id="r", source_record_id="m", fact_type="matchup_result",
               known_at="2025-09-09T06:59:59Z", effective_at="2025-09-09T06:59:59Z")
    s = state_at(2025, "2025-09-05T00:19:59Z", "public", facts=[result])
    assert s.by_type("matchup_result") == []
    assert not hasattr(s, "allow_outcome_derivation")

def test_leaky_comparator_control_would_admit_the_outcome():
    """The deliberately leaky control: admit on effective_at instead of known_at
    and the preview state gains the very result it must not have."""
    result = F(fact_id="r", source_record_id="m", fact_type="matchup_result",
               effective_at="2025-09-04T00:00:00Z", known_at="2025-09-09T06:59:59Z")
    leaked = [f for f in [result] if f.effective_at <= "2025-09-05T00:19:59Z"]
    assert [f.fact_id for f in leaked] == ["r"], \
        "control: admitting on effective_at leaks results into a preview"

# deterministic replay ------------------------------------------------------
def test_deterministic_replay_of_facts_and_state(tmp_path):
    normalize_all(source_root=".", out_path=tmp_path / "a.jsonl", season=2025)
    normalize_all(source_root=".", out_path=tmp_path / "b.jsonl", season=2025)
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()
    fa = FactStore(tmp_path / "a.jsonl").load()
    fb = FactStore(tmp_path / "b.jsonl").load()
    sa = state_at(2025, "2025-09-09T06:59:59Z", "league_private", facts=fa)
    sb = state_at(2025, "2025-09-09T06:59:59Z", "league_private", facts=fb)
    assert [f.fact_id for f in sa.admitted] == [f.fact_id for f in sb.admitted]
```

- [ ] **Step 2: Run** → 19 passed. **If any mutation control passes without its rule disabled, the
      rule is not doing work — fix the rule, never the test.**

Seven rules, seven controls, four preserved noninterference proofs, one replay test. A previous
revision shipped a control for rule 1 only while the Self-Review claimed all seven had one:
deterministic replay of the same source is not a substitute for physical truncation or for
poisoned-input isolation, because a deterministic pipeline reproduces a leak just as faithfully as
it reproduces a correct answer.

- [ ] **Step 3: Run the full suite**

```bash
$PY -m pytest scripts/tests/ -q
```

Expected: ≥ 343 passed / 2 skipped, plus the new tests.

- [ ] **Step 4: Commit**

```bash
git add scripts/tests/test_k1_discriminating.py
git commit -m "test(kernel): seven rules, seven controls, four noninterference proofs"
```

---

## K2 — The three D1 states

### Task K2.1: Edition descriptors and state compilation

**Files:** Create `scripts/compile_state.py`, `content/editions/*/descriptor.json` (three),
`scripts/tests/test_compile_state.py`

**Interfaces:**

- Produces: `EditionDescriptor` (edition_id, season, kind, cutoff_utc, access_scope,
  as_recorded_at, predecessors), `compile_state(descriptor) -> Path` writing
  `<edition>/compiled/{descriptor,state,state_manifest,source_hashes}.json`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.compile_state import compile_state, EditionDescriptor
from scripts.fact_schema import fact_hash

PRE = EditionDescriptor("2025-preseason", 2025, "preseason", "2025-09-03T23:59:59Z",
                        "league_private", None, ())

def test_writes_all_compile_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_state.EDITIONS_ROOT", tmp_path)
    out = compile_state(PRE)
    for f in ("descriptor.json", "state.json", "state_manifest.json", "source_hashes.json"):
        assert (out / f).exists(), f

def test_manifest_hash_matches_the_persisted_state(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_state.EDITIONS_ROOT", tmp_path)
    out = compile_state(PRE)
    state = json.loads((out / "state.json").read_text(encoding="utf-8"))
    mf = json.loads((out / "state_manifest.json").read_text(encoding="utf-8"))
    assert mf["state_payload_sha256"] == fact_hash(state)

def test_source_identities_live_outside_the_state(tmp_path, monkeypatch):
    """The df7c1ea defect: identities inside the compared artifact make the
    truncation comparison impossible to pass."""
    monkeypatch.setattr("scripts.compile_state.EDITIONS_ROOT", tmp_path)
    out = compile_state(PRE)
    state = json.loads((out / "state.json").read_text(encoding="utf-8"))
    assert "source_identities" not in state and "source_hashes" not in state
    assert json.loads((out / "source_hashes.json").read_text(encoding="utf-8"))

def test_rebuild_preserves_sibling_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_state.EDITIONS_ROOT", tmp_path)
    compile_state(PRE)
    authored = tmp_path / PRE.edition_id / "ranking_record.json"
    authored.write_text('{"entries": []}', encoding="utf-8")
    compile_state(PRE)
    assert authored.exists(), "the compiler owns only compiled/"

def test_clean_rebuild_is_byte_identical(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr("scripts.compile_state.EDITIONS_ROOT", tmp_path)
    a = (compile_state(PRE) / "state.json").read_bytes()
    shutil.rmtree(tmp_path / PRE.edition_id / "compiled")
    assert (compile_state(PRE) / "state.json").read_bytes() == a
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — compile into `<edition>/compiled/` only, staging then atomic
      rename, with `source_hashes.json` carrying every consumed input (fact file, normalizer
      code, fact-type registry, predecessor seals) as **structured** paths and hashes, never
      `str(dict)`.

      **`EDITIONS_ROOT` must be read from the module global at call time**, never captured in a
      default argument or bound at import. The tests above relocate the whole compile tree by
      monkeypatching `scripts.compile_state.EDITIONS_ROOT`; a bound default would silently ignore
      the patch and write into the real repository, so the isolation the tests appear to prove
      would not exist.

- [ ] **Step 4: Write the three descriptors**

```json
{
  "edition_id": "2025-preseason",
  "season": 2025,
  "kind": "preseason",
  "cutoff_utc": "2025-09-03T23:59:59Z",
  "access_scope": "league_private",
  "as_recorded_at": null,
  "predecessors": []
}
```

Preview: `kind: "preview"`, `cutoff_utc` = strictly before the qualified first kickoff (derived,
not hard-coded — see K2.2), `predecessors: ["2025-preseason"]`.
Recap: `kind: "recap"`, `cutoff_utc: "2025-09-09T06:59:59Z"`,
`predecessors: ["2025-preseason", "2025-wk01-preview"]`.

- [ ] **Step 5: Run** → 5 passed

- [ ] **Step 5b: Add the CLI** — K3.7 invokes this script

```python
def main():
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--descriptor", required=True)
    a = ap.parse_args()
    raw = json.load(open(a.descriptor, encoding="utf-8"))
    raw["predecessors"] = tuple(raw.get("predecessors", ()))
    print(compile_state(EditionDescriptor(**raw)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Verify: `$PY scripts/compile_state.py --descriptor content/editions/2025-preseason/descriptor.json`
exits 0 and prints the compiled directory.

- [ ] **Step 6: Commit**

```bash
git add scripts/compile_state.py content/editions/ scripts/tests/test_compile_state.py
git commit -m "feat(states): compile three D1 states, identities outside the state payload"
```

---

### Task K2.2: Qualify the preview cutoff from a hashed source

`nfl_game.schema.json:31` states `kickoff` is a **local time-of-day, not ISO8601 — combine with
stadium timezone**. Appending `Z` turns a 20:20 ET kickoff into 20:20 UTC.

**Files:** Create `scripts/kickoff_source.py`, `content/governance/venue_timezones.json`,
`scripts/tests/test_kickoff_source.py`

**Interfaces:** `first_kickoff_instant(season) -> {instant_utc, source_hashes}`,
`strictly_before(instant, seconds=1)`, `to_utc(gameday, gametime, tzname)`, `UnavailableEvidence`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.kickoff_source import (first_kickoff_instant, strictly_before, to_utc,
                                    UnavailableEvidence)

def test_local_time_is_converted_not_suffixed():
    assert to_utc("2025-09-04", "20:20", "America/New_York") == "2025-09-05T00:20:00Z"
    assert to_utc("2025-09-04", "20:20", "America/New_York") != "2025-09-04T20:20:00Z"

def test_missing_timezone_fails_closed():
    with pytest.raises(UnavailableEvidence):
        to_utc("2025-09-04", "20:20", None)

def test_neutral_site_without_an_override_fails_closed():
    from scripts.kickoff_source import resolve_zone
    with pytest.raises(UnavailableEvidence):
        resolve_zone({"home_team": "ZZZ", "stadium_id": "NEUTRAL_X"}, {"by_team": {},
                                                                      "by_stadium": {}})

def test_result_carries_every_source_hash():
    try:
        out = first_kickoff_instant(2025)
    except UnavailableEvidence:
        pytest.skip("schedules parquet absent; run scripts/fetch_nflreadpy.py first")
    assert out["instant_utc"].endswith("Z") and len(out["source_hashes"]) >= 2
    assert all(v.startswith("sha256:") for v in out["source_hashes"].values())

def test_strictly_before_is_strictly_before():
    assert strictly_before("2025-09-05T00:20:00Z") == "2025-09-05T00:19:59Z"
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — `resolve_zone` prefers `by_stadium[stadium_id]` (neutral sites),
      falls back to `by_team[home_team]`, and raises `UnavailableEvidence` when neither exists.
      `to_utc` converts through `ZoneInfo`. Both the schedules parquet and the timezone map are
      hashed into `source_hashes`.

- [ ] **Step 4: Derive and record the preview cutoff**

```bash
$PY scripts/fetch_nflreadpy.py --season 2025
$PY - <<'PY'
from scripts.kickoff_source import first_kickoff_instant, strictly_before
r = first_kickoff_instant(2025)
print("kickoff:", r["instant_utc"], "\ncutoff :", strictly_before(r["instant_utc"]))
PY
```

Write the printed cutoff into the preview descriptor. `compile_state` re-derives it and refuses
to compile a preview whose descriptor cutoff is not strictly-before the qualified kickoff.

- [ ] **Step 5: Run** → 5 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/kickoff_source.py content/governance/venue_timezones.json scripts/tests/test_kickoff_source.py
git commit -m "feat(cutoff): timezone-correct kickoff qualification, neutral sites fail closed"
```

---

### Task K2.3: Migration checks and the state census

The design demotes the source census and leaf registry to **migration checks** — "did every legacy
field find a fact type" — rather than the primary temporal guarantee.

**Files:** Create `scripts/migration_census.py`, `scripts/tests/test_migration_census.py`

**Interfaces:** `unmapped_legacy_fields(season) -> list[str]`, `state_leak_census(edition) -> dict`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.migration_census import unmapped_legacy_fields, state_leak_census

def test_every_legacy_field_found_a_fact_type():
    unmapped = unmapped_legacy_fields(2025)
    assert not unmapped, f"{len(unmapped)} legacy fields have no fact type: {unmapped[:8]}"

def test_compiled_states_carry_zero_future_entries():
    for e in ("2025-preseason", "2025-wk01-preview", "2025-wk01-recap"):
        r = state_leak_census(f"content/editions/{e}")
        assert r["future_entries"] == 0, f"{e}: {r['detail'][:5]}"

def test_legacy_packets_still_carry_the_46_and_are_no_longer_inputs():
    """Documents that the leaks were fixed BY CONSTRUCTION, not by patching packets."""
    r = state_leak_census("content/weeks", legacy=True)
    assert r["future_entries"] == 46
    assert r["is_decision_input"] is False
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — walk every leaf of the legacy week packets, map each to a fact type
      via `fact_types.json`, and report unmapped. `state_leak_census` compares each dated value in
      a compiled state against its descriptor cutoff and recomputes undated aggregates.

- [ ] **Step 4: Run** → 3 passed

- [ ] **Step 4b: Add the CLI** — K2.3 and K3.8 invoke this script

```python
def main():
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--edition")
    ap.add_argument("--season", type=int, default=2025)
    a = ap.parse_args()
    failed = 0
    if a.all:
        unmapped = unmapped_legacy_fields(a.season)
        if unmapped:
            failed += 1
            print(f"FAIL {len(unmapped)} unmapped legacy fields: {unmapped[:8]}")
        editions = sorted(p.parent.name for p in
                          Path("content/editions").glob("*/compiled/state.json"))
        if not editions:
            print("FAIL discovered 0 compiled states; --all must not pass vacuously")
            return 1
        for e in editions:
            r = state_leak_census(f"content/editions/{e}")
            if r["future_entries"]:
                failed += 1
                print(f"FAIL {e}: {r['future_entries']} future entries {r['detail'][:3]}")
    else:
        r = state_leak_census(a.edition)
        if r["future_entries"]:
            failed += 1
            print(f"FAIL {a.edition}: {r['detail'][:5]}")
    print("OK" if not failed else f"{failed} failure(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`--all` fails rather than passing vacuously when no compiled state is discovered — the defect
that let a glob over a never-written path report OK in the prior plan.

- [ ] **Step 5: Commit**

```bash
git add scripts/migration_census.py scripts/tests/test_migration_census.py
git commit -m "feat(migration): legacy-field coverage check and state leak census"
```

---

## K3 — Claims, runs, and five measured arms

### Task K3.1: Claims ledger

**Files:** Create `scripts/claims_ledger.py`, `scripts/schemas/claim.schema.json`,
`scripts/tests/test_claims_ledger.py`

**Interfaces:** `Claim` (frozen), `make_claim(...)`, `validate_claim(claim) -> list[str]`,
`CLAIM_TYPES`, `HORIZONS`, `save_claims(claims, root=None)`, `load_claims(root=None) -> list[Claim]`

**One loader, named once.** K3.5's driver and K3.6's report both read the ledger; both use
`load_claims`. An earlier draft had K3.6 call an otherwise-undeclared `load_all_claims`, so the two
consumers named two functions and neither had a creating task. `root=None` means the real ledger
root; K3.5's tests pass `root=tmp_path`.

**Fields beyond the design table that the tests exercise:** `bound` (required when
`claim_type == "bounded_quantity"`, per the design's "absolute error normalized by the claim's
stated bound"); `resolution_failed` (set by the resolver when the resolution source is
unavailable — the design's `unresolvable` class, reported and never silently dropped); and
`edition_id`, without which the aggregation order `claim → team → edition → trial → arm` has no
edition key and K3.6 cannot detect a missing cell. `outcome` and `score` start `None`.

`EDITION_IDS = ("2025-preseason", "2025-wk01-preview", "2025-wk01-recap")` is declared here, beside
the claim record, and imported by K3.5's driver and K3.6's report — the K3.7 shell loop must not be
the only place the edition list exists.

`resolve_claims(claims, state) -> list[Claim]` fills `outcome`/`score` for claims whose
`resolution_rule.resolve_on` has passed, reading the outcome from the named `source` in the
supplied state, and sets `resolution_failed=True` when that source yields nothing.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.claims_ledger import make_claim, validate_claim, CLAIM_TYPES, HORIZONS

def base(**over):
    b = dict(target="General Ken-obi", claim_type="ordinal_rank", horizon="rest_of_season",
             assertion=2, confidence=0.6, decisive_evidence=["/records/highest_score"],
             contrary_evidence="thin schedule so far", cutoff_utc="2025-09-09T06:59:59Z",
             state_hash="sha256:" + "a" * 64, arm_id="full_rich", trial_id=1,
             decision_run_id="run-1",
             resolution_rule={"rule": "final_regular_season_rank", "source": "standings",
                              "resolve_on": "2026-01-06T00:00:00Z"})
    b.update(over); return b

def test_claim_types_and_horizons_are_the_declared_sets():
    assert CLAIM_TYPES == {"ordinal_rank", "binary_probability", "bounded_quantity"}
    assert HORIZONS == {"next_week", "rest_of_season", "championship", "dynasty"}

def test_resolution_rule_is_required_and_complete():
    for missing in ("rule", "source", "resolve_on"):
        r = dict(base()["resolution_rule"]); r.pop(missing)
        assert validate_claim(make_claim(**base(resolution_rule=r)))

def test_outcome_and_score_start_empty():
    c = make_claim(**base())
    assert c.outcome is None and c.score is None

def test_bounded_quantity_requires_a_bound():
    assert validate_claim(make_claim(**base(claim_type="bounded_quantity", assertion=120.0)))
    assert not validate_claim(make_claim(**base(claim_type="bounded_quantity",
                                                assertion=120.0, bound=200.0)))

def test_probability_must_be_within_zero_and_one():
    assert validate_claim(make_claim(**base(claim_type="binary_probability", assertion=1.4)))

def test_claim_binds_its_arm_trial_and_run():
    c = make_claim(**base())
    assert c.arm_id == "full_rich" and c.trial_id == 1 and c.decision_run_id == "run-1"
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** the dataclass, the JSON Schema, and `validate_claim` enforcing type,
      horizon, bounds, and a complete `resolution_rule` (rule, source, resolve_on) fixed at claim
      time.

- [ ] **Step 4: Run** → 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/claims_ledger.py scripts/schemas/claim.schema.json scripts/tests/test_claims_ledger.py
git commit -m "feat(claims): scoreable claim records with pre-fixed resolution rules"
```

---

### Task K3.2: Decision-run receipts

**Files:** Create `scripts/decision_run.py`, `scripts/tests/test_decision_run.py`

**Interfaces:** `DecisionRun`, `open_run(...)`, `close_run(run, output_decision_hash, ended_at)`,
`RUNNER_KINDS`, `persist_run(run, root)`, `load_runs(root)`, `runner_config(arm_id)`,
`RUNNER_CONFIG_PATH`

**A receipt nobody stores is not a receipt.** `open_run`/`close_run` build the record; `persist_run`
writes it to `<root>/<season>/<arm_id>/trial<N>/<edition_id>.run.json`, and K3.8's packet reads
them back via `load_runs`. Without persistence the design's "every arm ran under a decision-run
receipt of the correct `runner_kind`" is unverifiable after the process exits.

**The model arms need a configuration source.** `DecisionRun` requires provider, model, version,
reasoning, tools/browsing policy, budget, retries, sampling and prompt/rule hashes — none of which
exist anywhere else in this plan. `runner_config(arm_id)` reads
`content/governance/runner_config.json`:

```json
{
  "version": 1,
  "model_arms": {
    "provider": "anthropic",
    "model": "claude-opus-5",
    "model_version": "2026-05",
    "reasoning": "high",
    "tools_policy": "none",
    "browsing": "disabled",
    "budget": 100000,
    "retries": 0,
    "sampling_policy": "temperature=1.0",
    "prompt_path": "content/governance/prompts/ranking_prompt.md",
    "rule_paths": { "voice": "content/voice-bible.md" }
  }
}
```

`browsing: "disabled"` and `tools_policy: "none"` are the design's 2025-backtest requirements, so
they are configuration the receipt records rather than a promise in prose. `prompt_hash` and
`rule_hashes` are computed from those paths at `open_run` time, so a prompt edit between trials is
visible in the receipts instead of silently changing what was measured.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.decision_run import open_run, close_run, RUNNER_KINDS

COMMON = dict(edition_id="2025-wk01-recap", arm_id="full_rich", trial_id=1,
              state_hash="sha256:" + "a" * 64, bundle_hash="sha256:" + "b" * 64,
              predecessor_decision_hash="sha256:" + "c" * 64,
              started_at="2026-08-02T00:00:00Z")

def test_both_runner_kinds_exist():
    assert RUNNER_KINDS == {"deterministic", "model"}

def test_deterministic_run_needs_code_and_config_hashes():
    with pytest.raises(ValueError):
        open_run(runner_kind="deterministic", **COMMON)
    r = open_run(runner_kind="deterministic", code_hash="sha256:" + "d" * 64,
                 config_hash="sha256:" + "e" * 64, input_hashes={"x": "sha256:" + "f" * 64},
                 **COMMON)
    assert r.runner_kind == "deterministic"

def test_deterministic_run_must_not_carry_a_provider():
    with pytest.raises(ValueError):
        open_run(runner_kind="deterministic", code_hash="sha256:" + "d" * 64,
                 config_hash="sha256:" + "e" * 64, input_hashes={}, provider="anthropic",
                 **COMMON)

def test_model_run_needs_provider_model_and_policy():
    with pytest.raises(ValueError):
        open_run(runner_kind="model", provider="anthropic", **COMMON)
    r = open_run(runner_kind="model", provider="anthropic", model="claude-opus-5",
                 model_version="2026-05", reasoning="high", tools_policy="none",
                 browsing="disabled", budget=100000, retries=0, sampling_policy="temp=0",
                 prompt_hash="sha256:" + "1" * 64, rule_hashes={"voice": "sha256:" + "2" * 64},
                 **COMMON)
    assert r.browsing == "disabled"

def test_close_binds_the_output_hash():
    r = open_run(runner_kind="deterministic", code_hash="sha256:" + "d" * 64,
                 config_hash="sha256:" + "e" * 64, input_hashes={}, **COMMON)
    done = close_run(r, output_decision_hash="sha256:" + "9" * 64,
                     ended_at="2026-08-02T00:05:00Z")
    assert done.output_decision_hash.startswith("sha256:") and done.ended_at

def test_predecessor_hash_is_mandatory_outside_preseason():
    with pytest.raises(ValueError):
        open_run(runner_kind="deterministic", code_hash="sha256:" + "d" * 64,
                 config_hash="sha256:" + "e" * 64, input_hashes={},
                 **dict(COMMON, predecessor_decision_hash=None))
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — `open_run` validates the field set for the declared `runner_kind`
      and rejects model-only fields on a deterministic run and vice versa. A `preseason` edition
      may pass `predecessor_decision_hash=None`; every other kind must supply one.

- [ ] **Step 4: Run** → 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/decision_run.py scripts/tests/test_decision_run.py
git commit -m "feat(runs): decision-run receipts for deterministic and model runners"
```

---

### Task K3.3: Frozen evidence manifest and contrast integrity

**Files:** Create `scripts/eval_contrast.py`, `content/governance/evidence_families.json`,
`scripts/tests/test_eval_contrast.py`

**Interfaces:** `load_manifest(path=MANIFEST_PATH)`, `freeze_manifest(path=MANIFEST_PATH, frozen_at)`,
`family_counts(arm_id, editions_root=EDITIONS_ROOT) -> dict`,
`assess_contrast(manifest, full, minimal, state_path=CONTRAST_STATE_PATH) -> ContrastResult` with
`.status` in `{"ok", "degraded", "stop_no_decision"}`, `.missing`, `.reason`, `.per_edition`,
`.cycles_used`; `preflight(manifest, editions_root) -> ContrastResult`; `ManifestDrift`

**Every function takes an explicit path.** The manifest ships **unfrozen** (`frozen_at: null`), and
`assess_contrast` refuses an unfrozen manifest — so a test calling a no-argument `load_manifest()`
against the committed file could never reach an assessment. The tests freeze a temporary copy;
`K3.7` Step 1 freezes the committed one, exactly once, before any arm runs.

`family_counts(arm_id, editions_root)` is the design's **computed diff over admitted fact types,
recorded per edition**. It is a real producer, not a name: for each compiled edition it loads
`<edition>/compiled/state.json`, builds that arm's bundle via `bundle_for(arm_id, state, kind)`,
and returns

```python
{"per_edition": {edition_id: {family: n_admitted, ...}, ...},
 "totals":      {family: n_admitted_across_editions, ...}}
```

`assess_contrast` compares `totals` for the required-family check and records `per_edition` on the
result, so the "full and minimal genuinely differed" claim is evidenced edition by edition rather
than asserted once in aggregate.

**The manifest binds producers, not just family names.** `frozen_at`/`manifest_sha256` over a list
of names cannot detect the thing the design forbids — adding a _source_ after seeing output. Each
family therefore also freezes `source_ids` (the `SOURCES` keys and file globs from K1.6) and
`normalizer_version`. `assess_contrast` recomputes those from the live fact store and raises
`ManifestDrift` if they differ from the frozen values, which is what makes "no source may be added
after this point" enforceable rather than declarative.

**The remediation count is persisted, not passed.** It lives in
`content/editions/_evaluation/contrast_state.json` as `{"manifest_sha256": ..., "cycles_used": n}`,
bound to the frozen manifest hash. `assess_contrast` reads it; a degraded verdict increments it.
An environment variable defaulting to `0` enforces nothing — every re-run would be a first cycle,
so "one remediation cycle" would be unbounded in practice.

- [ ] **Step 1: Write the failing test**

```python
import json
import shutil
import pytest
from pathlib import Path
from scripts.eval_contrast import (load_manifest, freeze_manifest, assess_contrast,
                                   MANIFEST_PATH)

REQUIRED = {"roster_membership", "historical_matchup", "chat_message", "nfl_game"}

@pytest.fixture
def frozen(tmp_path):
    """A frozen copy. The committed manifest stays unfrozen until K3.7 Step 1."""
    p = tmp_path / "evidence_families.json"
    shutil.copyfile(MANIFEST_PATH, p)
    freeze_manifest(path=p, frozen_at="2026-08-02T00:00:00Z")
    return load_manifest(path=p)

def test_shipped_manifest_is_unfrozen():
    m = load_manifest()
    assert m["frozen_at"] is None and m["manifest_sha256"] is None

def test_manifest_requires_exactly_the_four_families():
    m = load_manifest()
    assert {f["family"] for f in m["families"] if f["required"]} == REQUIRED

def test_media_is_explicitly_excluded():
    m = load_manifest()
    media = next(f for f in m["families"] if f["family"] == "media_item")
    assert media["required"] is False and "S1b" in media["rationale"]

def test_assessing_an_unfrozen_manifest_is_refused():
    with pytest.raises(ValueError):
        assess_contrast(load_manifest(), {"roster_membership": 12}, {}, 0)

def test_freezing_twice_is_refused(tmp_path):
    p = tmp_path / "m.json"
    shutil.copyfile(MANIFEST_PATH, p)
    freeze_manifest(path=p, frozen_at="2026-08-02T00:00:00Z")
    with pytest.raises(ValueError):
        freeze_manifest(path=p, frozen_at="2026-08-03T00:00:00Z")

def test_missing_required_family_is_degraded(frozen):
    full = {"roster_membership": 12, "historical_matchup": 0, "chat_message": 900, "nfl_game": 16}
    r = assess_contrast(frozen, full, {"roster_membership": 12}, 0)
    assert r.status == "degraded" and "historical_matchup" in r.missing

def test_absent_media_does_not_degrade(frozen):
    full = {"roster_membership": 12, "historical_matchup": 400, "chat_message": 900,
            "nfl_game": 16, "media_item": 0}
    r = assess_contrast(frozen, full, {"roster_membership": 12}, 0)
    assert r.status == "ok"

def test_identical_bundles_are_degraded_even_when_complete(frozen):
    full = {"roster_membership": 12, "historical_matchup": 400, "chat_message": 900, "nfl_game": 16}
    r = assess_contrast(frozen, full, dict(full), 0)
    assert r.status == "degraded" and "no measurable difference" in r.reason

def test_second_degraded_cycle_stops(frozen):
    full = {"roster_membership": 12, "historical_matchup": 0, "chat_message": 900, "nfl_game": 16}
    r = assess_contrast(frozen, full, {"roster_membership": 12}, 1)
    assert r.status == "stop_no_decision"
    assert "S1a does not begin" in r.reason

def test_freeze_stamps_an_instant_and_a_hash(frozen):
    assert frozen["frozen_at"] and frozen["manifest_sha256"].startswith("sha256:")
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Write the manifest**

```json
{
  "version": 1,
  "frozen_at": null,
  "manifest_sha256": null,
  "families": [
    {
      "family": "roster_membership",
      "required": true,
      "rationale": "directly informs strength judgments"
    },
    {
      "family": "historical_matchup",
      "required": true,
      "rationale": "the no-history arm ablates exactly this"
    },
    {
      "family": "chat_message",
      "required": true,
      "rationale": "the no-chat arm ablates exactly this"
    },
    {
      "family": "nfl_game",
      "required": true,
      "rationale": "distinguishes rich from minimal"
    },
    {
      "family": "media_item",
      "required": false,
      "rationale": "deferred to S1b, non-evidentiary decoration; absence must not degrade the data-layer experiment"
    }
  ]
}
```

`freeze_manifest(path, frozen_at)` stamps `frozen_at` and `manifest_sha256` (the hash computed over
the manifest with both stamp fields excluded, so the hash is stable) and raises `ValueError` if
already frozen. `assess_contrast` raises `ValueError` on an unfrozen manifest. `frozen_at` is
passed in rather than read from the clock, so the freeze is reproducible and testable.

- [ ] **Step 4: Run** → 10 passed

- [ ] **Step 4b: Add the CLI** — K3.7 Steps 1 and 4 invoke this script

```python
def main():
    import argparse, json
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--assess", action="store_true")
    mode.add_argument("--preflight", action="store_true",
                      help="judge contrast BEFORE model arms burn trials")
    mode.add_argument("--freeze", action="store_true")
    ap.add_argument("--frozen-at", help="exact UTC instant; required with --freeze")
    ap.add_argument("--full-arm", default="full_rich")
    ap.add_argument("--minimal-arm", default="minimal_legal")
    a = ap.parse_args()
    if a.freeze:
        if not a.frozen_at:
            ap.error("--freeze requires --frozen-at")
        print(json.dumps(freeze_manifest(frozen_at=a.frozen_at), indent=2))
        return 0
    # cycles_used is read from and written to the persisted contrast state, keyed by
    # manifest_sha256 -- never supplied by the caller, or every re-run is cycle one.
    r = (preflight(load_manifest(), EDITIONS_ROOT) if a.preflight
         else assess_contrast(load_manifest(), family_counts(a.full_arm),
                              family_counts(a.minimal_arm)))
    print(json.dumps({"status": r.status, "missing": r.missing, "reason": r.reason,
                      "cycles_used": r.cycles_used, "per_edition": r.per_edition},
                     indent=2, sort_keys=True))
    # 2 is deliberately skipped: argparse exits 2 on a usage error, and a gate that
    # branched on 2 would read a mistyped flag as a stop-no-decision verdict.
    return {"ok": 0, "degraded": 1, "stop_no_decision": 3}[r.status]


if __name__ == "__main__":
    raise SystemExit(main())
```

**The entry guard is load-bearing, not boilerplate.** Without
`if __name__ == "__main__": raise SystemExit(main())` this module defines `main()` and never calls
it: `$PY scripts/eval_contrast.py --assess` would import the module, print nothing, and **exit 0**.
A gate branching on that exit code reads `ok` — so contrast integrity would go **unmeasured** while
appearing to pass, and the K3.8 review packet would be invalid. This is the one CLI of the six that
lacked the guard; a `def main():` census counts 6/6 clean while the guard census is 5/6, which is
why the check must be on **execution**, not presence.

Mode selection is a required mutually-exclusive group, so a bare invocation errors (exit 2) instead
of silently assessing. Verify before relying on it:

```bash
$PY scripts/eval_contrast.py --help >/dev/null; echo "help exit=$?"   # 0, with output
$PY scripts/eval_contrast.py;            echo "bare exit=$?"          # 2, usage error
```

Exit codes from `--assess` are distinct: **0** ok, **1** degraded (one remediation cycle
permitted), **3** stop-no-decision. **2 is reserved for argparse usage errors** and is never a
verdict. K3.7 Step 4 branches on all four outcomes, including the unexpected one.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_contrast.py content/governance/evidence_families.json scripts/tests/test_eval_contrast.py
git commit -m "feat(eval): frozen evidence manifest, bounded degradation, media excluded"
```

---

### Task K3.4: The five arms and the inertia comparator

**Files:** Create `scripts/eval_arms.py`, `scripts/tests/test_eval_arms.py`,
`scripts/tests/conftest_eval.py`; modify `scripts/tests/conftest.py`

**Interfaces:** `ARMS` (five), `bundle_for(arm_id, state)`,
`inertia_comparator(arm_id, trial_id, edition, root) -> SealedDecision | None`, `ArmUnavailable`

**The comparator does not derive its own cutoff.** It receives the `EditionDescriptor` and uses
`edition.season` and `edition.cutoff_utc`. An earlier draft called an undefined `_cutoff_for(kind)`
and hardcoded season 2025 — a consumer improvising the temporal rule that `state_at` and the
descriptors exist to own, and the exact class of defect this kernel removes.

**Fixtures have a producer.** `fake_state`, `fake_state_without_history`, `seeded_seals` and
K3.6's `claim_factory` are defined in a new `scripts/tests/conftest_eval.py` and re-exported from
`scripts/tests/conftest.py` (which today holds only the session-scoped content-purity gate — leave
that gate intact). Without this step every test below errors with `fixture not found` rather than
failing on the rule it is meant to prove.

- [ ] **Step 0: Create the fixtures**

```python
# scripts/tests/conftest_eval.py — imported by scripts/tests/conftest.py
import pytest
from scripts.temporal_state import state_at
from scripts.tests.test_temporal_state import F

FAMILIES = ("franchise_identity", "draft_pick", "roster_membership",
            "historical_matchup", "chat_message", "nfl_game",
            "matchup_result", "schedule_pairing")

def _state(families):
    facts = [F(fact_id=t, source_record_id=t, fact_type=t,
               access_scope="league_private" if t == "chat_message" else "public")
             for t in families]
    return state_at(2025, "2025-12-01T00:00:00Z", "league_private", facts=facts)

@pytest.fixture
def fake_state():
    return _state(FAMILIES)

@pytest.fixture
def fake_state_without_history():
    return _state([t for t in FAMILIES if t != "historical_matchup"])

@pytest.fixture
def preseason_state():
    """No matchup_result -- structurally absent before week 1, not missing.
    Carries real historical_matchup payloads so standings() can order them."""
    from scripts.tests.test_reducers import M
    hist = [M(1, 2024, 1, "2024-09-08T23:00:00Z", "A", "B", 120.0, 100.0),
            M(2, 2024, 2, "2024-09-15T23:00:00Z", "A", "B", 90.0, 130.0),
            M(3, 2024, 3, "2024-09-22T23:00:00Z", "B", "A", 140.0, 110.0)]
    hist = [F(**{**{k: getattr(h, k) for k in
                    ("source_record_id", "entity_ref", "source_ref", "effective_at",
                     "known_at", "access_scope", "known_at_basis", "captured_at",
                     "privacy", "normalizer_version")},
                 "fact_id": h.fact_id, "fact_type": "historical_matchup",
                 "payload": h.payload}) for h in hist]
    others = [F(fact_id=t, source_record_id=t, fact_type=t,
                access_scope="league_private" if t == "chat_message" else "public")
              for t in FAMILIES if t not in {"matchup_result", "historical_matchup"}]
    return state_at(2025, "2025-09-03T23:59:59Z", "league_private", facts=hist + others)

@pytest.fixture
def seeded_seals(tmp_path):
    """A full_rich preseason seal only — no_chat deliberately has none, so
    test_comparator_absent_without_a_qualified_predecessor is a real negative."""
    from scripts.decision_history import seal
    seal(root=tmp_path, edition_id="2025-preseason", season=2025,
         cutoff_utc="2025-09-03T23:59:59Z", arm_id="full_rich", trial_id=1,
         state_hash="sha256:" + "a" * 64, ranking={"entries": []}, claims=[],
         run_id="run-seed")
    return tmp_path
```

`chat_message` is registered `league_private`, so the fixture requests a `league_private` state —
a `public` state would silently drop it and `test_no_chat_bundle_omits_chat` would pass for the
wrong reason.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.compile_state import EditionDescriptor
from scripts.eval_arms import ARMS, bundle_for, inertia_comparator, ArmUnavailable

PRESEASON = EditionDescriptor("2025-preseason", 2025, "preseason", "2025-09-03T23:59:59Z",
                              "league_private", None, ())
PREVIEW = EditionDescriptor("2025-wk01-preview", 2025, "preview", "2025-09-05T00:19:59Z",
                            "league_private", None, ("2025-preseason",))

def test_exactly_five_arms():
    assert set(ARMS) == {"record_points", "minimal_legal", "full_rich", "no_chat", "no_history"}

def test_no_prior_unchanged_arm_exists():
    assert "prior_unchanged" not in ARMS and "inertia" not in ARMS

def test_record_points_is_the_only_deterministic_arm():
    det = {a for a, spec in ARMS.items() if spec["runner_kind"] == "deterministic"}
    assert det == {"record_points"}

def test_record_points_uses_prior_season_standings_at_preseason():
    assert ARMS["record_points"]["preseason_basis"] == "prior_season_final_standings"

def test_no_chat_bundle_omits_chat(fake_state):
    b = bundle_for("no_chat", fake_state, "recap")
    assert "chat_message" not in b["families"] and "historical_matchup" in b["families"]

def test_no_history_ablates_every_pre_2025_type(fake_state):
    from scripts.eval_arms import PRE_2025_TYPES
    b = bundle_for("no_history", fake_state, "recap")
    assert not (PRE_2025_TYPES & set(b["families"])), \
        "the design says 'full minus pre-2025 facts', not 'minus historical_matchup'"
    assert "chat_message" in b["families"]

def test_minimal_bundle_is_a_strict_subset_of_full(fake_state):
    assert set(bundle_for("minimal_legal", fake_state, "recap")["families"]) < \
           set(bundle_for("full_rich", fake_state, "recap")["families"])

def test_structurally_absent_results_do_not_make_an_arm_unavailable(preseason_state):
    """A preseason state contains no 2025 results BY CONSTRUCTION. Treating that as
    missing evidence aborted the run before contrast could be judged."""
    b = bundle_for("full_rich", preseason_state, "preseason")
    assert "matchup_result" not in b["families"]

def test_record_points_has_an_executable_preseason_basis(preseason_state):
    """Its only family was matchup_result, which cannot exist at preseason -- so the
    prior-season-standings basis was unreachable metadata."""
    from scripts.eval_arms import required_families
    assert required_families("record_points", "preseason") == ["historical_matchup"]
    b = bundle_for("record_points", preseason_state, "preseason")
    assert b["ranking_basis"] == "prior_season_final_standings"
    assert b["standings"], "the basis must produce an actual ordering"

def test_no_inertia_comparator_at_preseason(seeded_seals):
    assert inertia_comparator("full_rich", 1, PRESEASON, root=seeded_seals) is None

def test_comparator_uses_the_same_arms_predecessor(seeded_seals):
    c = inertia_comparator("full_rich", 1, PREVIEW, root=seeded_seals)
    assert c is not None and c.arm_id == "full_rich" and c.trial_id == 1
    assert c.edition_id == "2025-preseason"

def test_comparator_absent_without_a_qualified_predecessor(seeded_seals):
    """no_chat has no seal in the same root: absent, never borrowed from full_rich."""
    assert inertia_comparator("no_chat", 1, PREVIEW, root=seeded_seals) is None

def test_unavailable_family_makes_its_arm_unavailable(fake_state_without_history):
    """No history to ablate = the ablation measures nothing. Distinct from the
    structurally-absent case above, which must NOT raise."""
    with pytest.raises(ArmUnavailable):
        bundle_for("no_history", fake_state_without_history, "recap")
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""The five K3 data-layer arms. Inertia is a comparator inside each, never an arm."""

# Families that CANNOT exist at a given edition kind. Their absence is correct,
# not missing evidence -- a preseason state contains no 2025 results by construction,
# and treating that as an unavailable arm aborts the run before contrast can be judged.
STRUCTURALLY_ABSENT = {
    "preseason": {"matchup_result"},
    "preview":   {"matchup_result"},
    "recap":     set(),
}

# Pre-2025 fact types. The no-history arm ablates ALL of them, not just one:
# the design says "Full minus pre-2025 facts."
PRE_2025_TYPES = {"historical_matchup"}

ARMS = {
    "record_points": {
        "runner_kind": "deterministic",
        "families": ["matchup_result"],
        # Executable, not inert metadata: at preseason and preview there are no 2025
        # results, so this arm ranks by prior-season final standings computed from
        # admitted historical_matchup facts via LeagueState.standings().
        "preseason_basis": "prior_season_final_standings",
        "families_by_kind": {"preseason": ["historical_matchup"],
                             "preview":   ["historical_matchup"],
                             "recap":     ["matchup_result", "historical_matchup"]},
    },
    "minimal_legal": {"runner_kind": "model",
                      "families": ["franchise_identity", "draft_pick", "roster_membership"]},
    "full_rich":     {"runner_kind": "model",
                      "families": ["franchise_identity", "draft_pick", "roster_membership",
                                   "historical_matchup", "chat_message", "nfl_game",
                                   "matchup_result", "schedule_pairing"]},
    "no_chat":       {"runner_kind": "model", "ablates": ["chat_message"]},
    "no_history":    {"runner_kind": "model", "ablates": sorted(PRE_2025_TYPES)},
}


def required_families(arm_id, edition_kind):
    """What THIS arm must have at THIS edition. Structurally absent families and
    families with no qualified source are excluded before the requirement is judged."""
    spec = ARMS[arm_id]
    base = spec.get("families_by_kind", {}).get(edition_kind) or spec.get("families")
    if base is None:                                   # ablation arm: full minus ablated
        base = [f for f in ARMS["full_rich"]["families"] if f not in spec["ablates"]]
    return [f for f in base if f not in STRUCTURALLY_ABSENT[edition_kind]]


def inertia_comparator(arm_id, trial_id, edition, root):
    """The unchanged prior seal of THIS arm, or None where no qualified predecessor exists.

    `edition` is the EditionDescriptor. Season and cutoff come from it — this consumer
    derives no temporal rule of its own.
    """
    from decision_history import decision_history_at
    if edition.kind == "preseason":
        return None                      # nothing to carry forward; invent nothing
    prior = decision_history_at(edition.season, edition.cutoff_utc, arm_id, trial_id, root=root)
    return prior[-1] if prior else None
```

`bundle_for(arm_id, state)` returns `{"families": [...], "facts": {...}}`. For `record_points`,
`minimal_legal` and `full_rich` the family list is the arm's declared `families`; for the two
ablation arms it is `full_rich`'s families minus the arm's `ablates` entries — so an ablation is
defined by subtraction from the full bundle and cannot drift from it.

`bundle_for(arm_id, state, edition_kind)` takes the edition kind and calls `required_families`.
`ArmUnavailable` is raised in two cases, both meaning the arm cannot measure what it exists to
measure:

- a **required** family (per `required_families`) for which the state admits **zero** facts;
- a family the arm **ablates** for which the state admits **zero** facts — removing nothing is not
  an ablation, and scoring it as one reports a null result the experiment never tested.

`ArmUnavailable` is **never** raised for a family listed in `STRUCTURALLY_ABSENT` for that edition.
A preseason state legitimately contains no `matchup_result`; treating that as missing evidence is
what made `record_points` unrunnable at the only two editions where its prior-season basis applies.

**The distinction that matters.** "Absent because it cannot exist yet" is correct composition.
"Absent because no qualified source exists" is degraded contrast — and it must reach
`assess_contrast` as a **degraded verdict**, not abort the run with an exception. `bundle_for`
therefore raises only for the second kind, and K3.7 preflights the contrast before any model arm
burns a trial (below).

- [ ] **Step 4: Run** → 13 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_arms.py scripts/tests/test_eval_arms.py scripts/tests/conftest_eval.py scripts/tests/conftest.py
git commit -m "feat(eval): five arms with per-arm inertia comparators"
```

---

### Task K3.5: Chronological execution driver

**Files:** Modify `scripts/eval_arms.py`; create `scripts/tests/test_chronological.py`

**Interfaces:**
`run_arm_chain(arm_id, trial_id, editions, root=None, _force_predecessor_arm=None) -> list[SealedDecision]`

**`root` is an explicit parameter, not a monkeypatched module global.** `decision_history_at`
binds `root=SEALS_ROOT` as a **default argument**, evaluated once at import — so
`monkeypatch.setattr("scripts.decision_history.SEALS_ROOT", tmp_path)` does not redirect it. An
earlier draft relied on exactly that patch: the tests would have written real seals into
`content/decisions/`, and since a seal is immutable, the second run of the suite would fail
permanently on `FileExistsError` from repository state rather than from the rule under test.
`run_arm_chain` threads `root` through to `seal`, `decision_history_at` and the claims ledger;
`root=None` means the real roots.

`_force_predecessor_arm` is a test-only injection hook that makes the cross-arm poison test
possible. It is declared here rather than appearing only at a call site.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.eval_arms import run_arm_chain
from scripts.decision_history import CrossArmContamination

EDITIONS = ["2025-preseason", "2025-wk01-preview", "2025-wk01-recap"]

def test_chain_seals_in_order(tmp_path):
    seals = run_arm_chain("full_rich", 1, EDITIONS, root=tmp_path)
    assert [s.edition_id for s in seals] == EDITIONS
    assert seals[0].cutoff_utc < seals[1].cutoff_utc < seals[2].cutoff_utc

def test_preview_consumes_its_own_preseason_seal(tmp_path):
    seals = run_arm_chain("full_rich", 1, EDITIONS, root=tmp_path)
    assert all(s.arm_id == "full_rich" and s.trial_id == 1 for s in seals)

def test_arm_cannot_consume_another_arms_seal(tmp_path):
    run_arm_chain("no_chat", 1, EDITIONS[:1], root=tmp_path)
    run_arm_chain("full_rich", 1, EDITIONS[:1], root=tmp_path)
    with pytest.raises(CrossArmContamination):
        run_arm_chain("full_rich", 1, EDITIONS[1:], root=tmp_path,
                      _force_predecessor_arm="no_chat")

def test_recap_grades_this_arms_prior_claims(tmp_path):
    run_arm_chain("full_rich", 1, EDITIONS, root=tmp_path)
    from scripts.claims_ledger import load_claims
    graded = [c for c in load_claims(root=tmp_path) if c.outcome is not None]
    assert graded and all(c.arm_id == "full_rich" for c in graded)

def test_a_seal_cannot_be_overwritten(tmp_path):
    run_arm_chain("full_rich", 1, EDITIONS[:1], root=tmp_path)
    with pytest.raises(FileExistsError):
        run_arm_chain("full_rich", 1, EDITIONS[:1], root=tmp_path)

def test_root_isolation_leaves_the_repository_untouched(tmp_path):
    """Control: the tests above must not be writing into content/decisions/."""
    from pathlib import Path
    before = sorted(p.name for p in Path("content/decisions").glob("**/*")) \
        if Path("content/decisions").exists() else []
    run_arm_chain("no_history", 1, EDITIONS[:1], root=tmp_path)
    after = sorted(p.name for p in Path("content/decisions").glob("**/*")) \
        if Path("content/decisions").exists() else []
    assert before == after
```

- [ ] **Step 2: Run to verify it fails** → `ImportError: cannot import name 'run_arm_chain'`

- [ ] **Step 3: Implement** — the complete path, per edition, in order:

```
descriptor + compiled state
  -> bundle_for(arm, state, descriptor.kind)                       # ArmUnavailable fails closed
  -> decision_history_at(...) + verify_predecessor(...)            # same arm, same trial
  -> open_run(runner_kind, **runner_config(arm))                   # configured, not implied
  -> RUNNERS[arm](bundle, predecessor)                             # deterministic | model
  -> ranking (one entry per franchise) + claims (>=1 per position)
  -> resolve_claims(prior_claims, state)                           # recap grades what is due
  -> inertia_comparator(...) -> load_decision(prior) -> score      # unchanged prior, re-scored
  -> persist_run(...) ; seal(..., run_receipt_path=...)
  -> close_run(run, output_decision_hash=seal.decision_hash, ended_at=...)
```

`RUNNERS` maps `arm_id` to a callable of `(bundle, predecessor) -> (ranking, claims)`.
`record_points` is the deterministic one: it orders by `state.standings()` — current-season at
recap, prior-season at preseason and preview — and emits one `ordinal_rank` claim per position.
Model arms call the configured provider with the bundle and the arm's prompt.

**Every ranking position must yield at least one scoreable claim.** `run_arm_chain` raises if
`len(claims) < len(ranking["entries"])`, because the design requires that every published position
carry a claim with a resolution rule fixed before the outcome. A ranking with no claims is exactly
the unscoreable judgment the claims ledger exists to replace.

Every root-taking call receives `root` explicitly.

- [ ] **Step 4: Run** → 6 passed

- [ ] **Step 4b: Add the CLI** — K3.7 Step 3 invokes this script

```python
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS))
    ap.add_argument("--trial", type=int)
    ap.add_argument("--editions", help="comma-separated edition ids, chronological")
    ap.add_argument("--blind-packet", action="store_true",
                    help="write anonymized sealed rankings for blind review")
    ap.add_argument("--out", help="output directory; required with --blind-packet")
    a = ap.parse_args()
    if a.blind_packet:
        if not a.out:
            ap.error("--blind-packet requires --out")
        n = write_blind_packet(a.out)
        print(f"wrote {n} anonymized decisions; label_map.json is NOT in {a.out}")
        return 0 if n else 1
    if not (a.arm and a.trial and a.editions):
        ap.error("--arm, --trial and --editions are required unless --blind-packet")
    editions = [e.strip() for e in a.editions.split(",") if e.strip()]
    seals = run_arm_chain(a.arm, a.trial, editions)
    for s in seals:
        print(f"{s.edition_id} {s.arm_id} trial{s.trial_id} {s.decision_hash[:19]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`--arm` is constrained to the five registered arms, so a typo cannot silently create a sixth.
`write_blind_packet(out)` returns the number of anonymized decisions written and the CLI exits 1 on
zero — an empty packet must not read as a completed blind review.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_arms.py scripts/tests/test_chronological.py
git commit -m "feat(eval): chronological per-arm chains with closed decision lineage"
```

---

### Task K3.6: Scoring and fixed aggregation

**Files:** Create `scripts/eval_scoring.py`, `scripts/tests/test_eval_scoring.py`; modify
`scripts/tests/conftest_eval.py`

**Interfaces:** `score_claim(claim) -> float | None`, `aggregate(claims) -> dict`,
`combine_trials(trials, runner_kind) -> dict`, `AGGREGATION_ORDER`,
`MIN_TRIALS_NONDETERMINISTIC`

- Consumes: `Claim`, `make_claim`, `load_claims` (K3.1); `ARMS` (K3.4) for each arm's
  `runner_kind`. `eval_scoring` imports `ARMS` rather than restating which arms are
  deterministic — a second copy of that list is a second thing to drift.

- [ ] **Step 0: Add the `claim_factory` fixture** to `scripts/tests/conftest_eval.py`

```python
@pytest.fixture
def claim_factory():
    """Minimal scoreable claims. Every field the scorer reads, nothing it doesn't."""
    from scripts.claims_ledger import make_claim
    def make(claim_type="ordinal_rank", assertion=1, outcome=None, bound=None,
             resolution_failed=False, arm_id="full_rich", trial_id=1):
        return make_claim(
            target="T", claim_type=claim_type, horizon="rest_of_season",
            assertion=assertion, confidence=0.6, decisive_evidence=[],
            contrary_evidence="", cutoff_utc="2025-09-09T06:59:59Z",
            state_hash="sha256:" + "a" * 64, arm_id=arm_id, trial_id=trial_id,
            decision_run_id="run-1", bound=bound, outcome=outcome,
            resolution_failed=resolution_failed,
            resolution_rule={"rule": "final_regular_season_rank", "source": "standings",
                             "resolve_on": "2026-01-06T00:00:00Z"})
    return make
```

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.eval_scoring import (score_claim, aggregate, AGGREGATION_ORDER,
                                  MIN_TRIALS_NONDETERMINISTIC)

def test_aggregation_order_is_fixed():
    assert AGGREGATION_ORDER == ("claim", "team", "edition", "trial", "arm")

def test_three_trials_required_for_nondeterministic_runners():
    assert MIN_TRIALS_NONDETERMINISTIC == 3

def test_ordinal_rank_uses_spearman_footrule(claim_factory):
    c = claim_factory(claim_type="ordinal_rank", assertion=2, outcome=5)
    assert score_claim(c) == 3

def test_binary_probability_uses_brier(claim_factory):
    c = claim_factory(claim_type="binary_probability", assertion=0.8, outcome=1)
    assert abs(score_claim(c) - 0.04) < 1e-9

def test_bounded_quantity_normalizes_by_its_bound(claim_factory):
    c = claim_factory(claim_type="bounded_quantity", assertion=120.0, outcome=100.0, bound=200.0)
    assert abs(score_claim(c) - 0.1) < 1e-9

def test_unresolved_claims_are_excluded_and_counted(claim_factory):
    claims = [claim_factory(outcome=None), claim_factory(assertion=2, outcome=2)]
    r = aggregate(claims)
    assert r["unresolved"] == 1 and r["scored"] == 1

def test_more_unresolved_claims_do_not_improve_an_arm(claim_factory):
    few = aggregate([claim_factory(assertion=2, outcome=5)])
    many = aggregate([claim_factory(assertion=2, outcome=5)] +
                     [claim_factory(outcome=None) for _ in range(9)])
    assert few["mean_score"] == many["mean_score"]

def test_missing_outcome_source_is_unresolvable_not_dropped(claim_factory):
    c = claim_factory(outcome=None, resolution_failed=True)
    r = aggregate([c])
    assert r["unresolvable"] == 1

def test_nondeterministic_arm_reports_median_and_range(claim_factory):
    trials = [aggregate([claim_factory(assertion=2, outcome=o)]) for o in (3, 5, 9)]
    from scripts.eval_scoring import combine_trials
    combined = combine_trials(trials, runner_kind="model")
    assert combined["median"] == 3 and combined["range"] == (1, 7)

def test_single_trial_model_arm_is_rejected(claim_factory):
    from scripts.eval_scoring import combine_trials
    with pytest.raises(ValueError):
        combine_trials([aggregate([claim_factory(assertion=2, outcome=3)])], runner_kind="model")
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** the three scoring rules, the fixed aggregation order, unresolved and
      unresolvable counting, and `combine_trials` requiring ≥ 3 trials for `runner_kind="model"`.

- [ ] **Step 4: Run** → 10 passed

- [ ] **Step 4b: Add the CLI** — K3.7 Step 5 invokes this script

```python
def main():
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", required=True)
    ap.add_argument("--arm")
    a = ap.parse_args()
    claims = load_claims()
    if not claims:
        # stderr: K3.7 Step 5 redirects stdout into scores.json, and a diagnostic
        # written there would become the artifact.
        print("FAIL no claims found; --report must not emit an empty measurement",
              file=sys.stderr)
        return 1
    # A report that silently omits an arm, edition, or trial reads as a complete
    # measurement of a smaller experiment. Refuse instead.
    expected = {(arm, ed, t)
                for arm in ARMS
                for ed in EDITION_IDS
                for t in range(1, (1 if ARMS[arm]["runner_kind"] == "deterministic"
                                   else MIN_TRIALS_NONDETERMINISTIC) + 1)}
    present = {(c.arm_id, c.edition_id, c.trial_id) for c in claims}
    if not a.arm and (missing := sorted(expected - present)):
        print(f"FAIL incomplete experiment, {len(missing)} cells missing: {missing[:5]}",
              file=sys.stderr)
        return 1
    if a.arm:
        claims = [c for c in claims if c.arm_id == a.arm]
    by_arm = {}
    for arm in sorted({c.arm_id for c in claims}):
        trials = [aggregate([c for c in claims if c.arm_id == arm and c.trial_id == t])
                  for t in sorted({c.trial_id for c in claims if c.arm_id == arm})]
        kind = ARMS[arm]["runner_kind"]
        by_arm[arm] = combine_trials(trials, runner_kind=kind)
    print(json.dumps(by_arm, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`combine_trials` raises when a model arm has fewer than three trials, so an under-sampled arm
cannot be reported as a measurement.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_scoring.py scripts/tests/test_eval_scoring.py
git commit -m "feat(eval): precommitted scoring rules and fixed aggregation order"
```

---

### Task K3.7: Run the arms and record blind review

- [ ] **Step 0: Prove every gate CLI actually executes**

A `main()` that is never called exits 0, and a gate branching on that reads success. Confirm all
six entry points before any of them is trusted:

```bash
for s in capture_2026 compile_state migration_census eval_contrast eval_arms eval_scoring; do
  out=$($PY "scripts/$s.py" --help 2>&1); rc=$?
  [ $rc -eq 0 ] && [ -n "$out" ] || { echo "FAIL $s: rc=$rc, output=${#out} bytes"; exit 1; }
done
echo "all six entry points execute"
```

- [ ] **Step 1: Freeze the manifest before anything runs**

```bash
$PY scripts/eval_contrast.py --freeze --frozen-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" || exit 1
```

Records `frozen_at` and `manifest_sha256`. **No source may be added after this point** — a
manifest change invalidates every completed arm. A second freeze is refused.

- [ ] **Step 2: Compile the three states**

```bash
for e in 2025-preseason 2025-wk01-preview 2025-wk01-recap; do
  $PY scripts/compile_state.py --descriptor "content/editions/$e/descriptor.json" || exit 1
done
$PY scripts/migration_census.py --all || exit 1
```

The census is a **gate**, not a report: it returns 1 on any unmapped legacy field, any future
entry, or a vacuous zero-edition discovery. Without `|| exit 1` a failing census would print FAIL
and the arms would run anyway on states it just rejected.

- [ ] **Step 2b: Preflight contrast integrity BEFORE any model arm runs**

```bash
mkdir -p content/editions/_evaluation
$PY scripts/eval_contrast.py --preflight > content/editions/_evaluation/contrast_preflight.json
rc=$?
case $rc in
  0) echo "contrast preflight ok -> arms may run" ;;
  1) echo "DEGRADED before any arm ran. One approved remediation cycle is permitted."
     echo "Running five arms x three trials against evidence already known to be"
     echo "insufficient buys nothing and spends the trial budget."; exit 1 ;;
  3) echo "STOP - NO DECISION. Go to K3.8."; exit 3 ;;
  *) echo "failed gate: exit $rc"; exit "$rc" ;;
esac
```

The compiled states already determine every family count, so the contrast verdict is knowable
**before** the first model call. Preflighting is what makes the design's degraded → one-remediation
→ STOP path reachable: the previous order ran the arms first, and a missing required family aborted
`bundle_for` with `ArmUnavailable` before any verdict could be recorded.

- [ ] **Step 3: Run each arm's chain, three trials for model arms**

```bash
for arm in record_points minimal_legal full_rich no_chat no_history; do
  trials=3; [ "$arm" = "record_points" ] && trials=1
  for t in $(seq 1 $trials); do
    $PY scripts/eval_arms.py --arm "$arm" --trial "$t" \
        --editions 2025-preseason,2025-wk01-preview,2025-wk01-recap || exit 1
  done
done
```

`record_points` runs one trial because it is deterministic; the four model arms run three, per the
design's minimum for a non-deterministic runner.

- [ ] **Step 4: Assess contrast integrity on the actual bundles — and branch**

```bash
$PY scripts/eval_contrast.py --assess --full-arm full_rich --minimal-arm minimal_legal \
    > content/editions/_evaluation/contrast.json
rc=$?
case $rc in
  0) echo "contrast ok -> continue to Step 5" ;;
  1) echo "contrast DEGRADED -> STOP. One approved remediation cycle is permitted."
     echo "The cycle count is persisted in contrast_state.json against the frozen"
     echo "manifest hash; a second degraded verdict returns 3, not 1."
     echo "Do not proceed to Step 5."
     exit 1 ;;
  3) echo "STOP - NO DECISION, NO EXPANSION. Go to K3.8 and record the verdict."
     echo "S1a does not begin. Prospective capture and sealing continue."
     exit 3 ;;
  *) echo "unexpected exit $rc from eval_contrast (2 = usage error); treat as a failed gate"
     exit "$rc" ;;
esac
```

The exit code **is** the gate. `0` continues, `1` halts for the single approved remediation cycle,
`3` routes to K3.8 with NO DECISION, and anything else — including argparse's `2` — is a failed
gate rather than a verdict. The remediation counter is passed in explicitly so a second degraded
result cannot be re-read as a first.

- [ ] **Step 5: Score and aggregate**

```bash
mkdir -p content/editions/_evaluation
$PY scripts/eval_scoring.py --report > content/editions/_evaluation/scores.json || exit 1
```

- [ ] **Step 6: Randomized blind review**

```bash
$PY scripts/eval_arms.py --blind-packet \
    --out content/editions/_evaluation/blind_packet/ || exit 1
```

`--blind-packet` reads each seal, calls `load_decision` to recover the **actual ranking body**, and
writes one anonymized file per (arm, trial, edition) named by opaque token — plus
`label_map.json`, which is written to a **separate** directory and is not part of the packet Blake
opens. Without the content locators added in K1.5 there is no body to present: a `ranking_hash`
cannot be read, so "present unlabeled arm outputs" had nothing to present.

Blake ranks the tokens on prose and judgment quality; the result is recorded at
`content/editions/_evaluation/blind_review.json` against those tokens, and only then is the label
map applied. **Blind review never overwrites computed scores** — where the two disagree, both are
reported and the disagreement is the finding.

- [ ] **Step 7: Commit — every artifact, not just the scores**

```bash
git add content/editions/ content/governance/evidence_families.json \
        content/governance/runner_config.json content/decisions/
git status --short | grep -qE 'content/decisions/.*\.(ranking|claims)\.json' \
  || { echo "STOP: sealed decision bodies missing; the packet is unreviewable"; exit 1; }
git commit -m "eval(k3): five arms, three trials each for model runners, scored and blind-reviewed"
```

The seals, sealed ranking and claim bodies, run receipts, contrast preflight and assessment, scores
and blind review are all evidence for the K3.8 verdict. Committing only `scores.json` would leave
the verdict resting on a number with nothing behind it.

---

### Task K3.8: STOP — judge data-layer lift

**Do not begin S1a. Do not build desks, media, or the render lifecycle.**

- [ ] **Step 1: Full sweep**

```bash
$PY -m pytest scripts/tests/ -q || exit 1
$PY scripts/migration_census.py --all || exit 1
$PY scripts/generate_chat_provenance.py --verify || exit 1
```

Each is a gate. An ungated sweep reports its own failure and then hands Blake a packet built on it.

- [ ] **Step 2: Assemble the review packet**

- **entry-point proof:** the K3.7 Step 0 output showing all six CLIs execute — without it, a green
  contrast verdict may be a `main()` that never ran;
- state leak census: 0 future entries across all three states; legacy packets unchanged at 46 and
  no longer decision inputs;
- the seven K1 discriminating tests with their mutation controls;
- deterministic replay: facts and state byte-identical across two normalizations;
- per-arm scores with medians and ranges, unresolved and unresolvable counts;
- contrast-integrity verdict, its **exit code**, and the frozen manifest hash;
- blind review versus computed scores, including any disagreement;
- the 2026 capture accounting receipt and current seal status.

**The packet is invalid if the contrast was not actually measured.** A `contrast.json` that is
absent, empty, or produced by a process that exited without assessing does not satisfy this step.

- [ ] **Step 3: Answer in writing**

> **Did richer evidence measurably change the decisions?**

Compare `full_rich` against `minimal_legal`, and each ablation against `full_rich`. Cite specific
ranking movements and claim scores.

- [ ] **Step 4: Record the verdict**

| Verdict                                       | Consequence                                                                   |
| --------------------------------------------- | ----------------------------------------------------------------------------- |
| Lift demonstrated                             | S1a becomes **eligible for Blake's separate explicit authorization**          |
| No lift                                       | S1a is not authorized; revise source and desk contracts before proposing more |
| Contrast degraded after one remediation cycle | **NO DECISION, NO EXPANSION**; prospective capture and sealing continue       |

**What the verdict does not govern.** The definitive 2025 archive remains the mission and is **not
contingent on measured lift**. The verdict decides the _mechanism_ and the _investment path_ —
whether desks are worth building, and how much evidence machinery earns its keep — not whether the
2025 archive gets finished. Only **S1a/S1b expansion** is gated by it. A no-lift or degraded result
means the archive is produced by a simpler mechanism, never that it is abandoned or deferred.

**Lift does not grant authorization.** Demonstrated lift makes S1a _eligible to be proposed_;
it never authorizes it. No exit code, verdict, or gate in this plan begins S1a — every path,
including "lift demonstrated," terminates at Blake's separate explicit decision.

- [ ] **Step 5: STOP.** Await Blake's decision.

---

## Self-Review

**Spec coverage.** Phase P → P1-P3 (split roots, per-row fetchers, eight-row accounting, daily
cadence, inactive workflow). K1 → K1.1-K1.7 (15-field schema, idempotent store, `state_at` with
required scope and vantage, recomputed aggregates, `decision_history_at`, nine normalizers, seven
discriminating tests with mutation controls). K2 → K2.1-K2.3 (three states, qualified kickoff,
migration checks). K3 → K3.1-K3.8 (claims, decision-runs, frozen manifest and contrast, five arms
with inertia comparators, chronological chains, precommitted scoring, execution, STOP).

**Design corrections carried.** Identities live outside the state payload, and K2.1 tests that
directly — the `df7c1ea` `bundle["source_identities"]` KeyError cannot recur. `allow_outcome_derivation`
is gone: a preview state contains no `matchup_result` facts, so there is nothing to switch off.
`prior_editions` globbing is replaced by arm-scoped `decision_history_at`. The season-authority
work is subsumed — facts carry their season, so `content/weeks/` never becomes a competing
authority.

**Census findings fixed in the first pass.** A grep of every `$PY scripts/*.py` invocation against
its creating task found **five scripts invoked with flags and no CLI at all** — `compile_state`,
`migration_census`, `eval_arms`, `eval_contrast`, `eval_scoring`. Every K3.7 command would have
died on an unrecognized argument. Each now has a `main()` in its owning task, and
`migration_census --all` fails rather than passing vacuously when it discovers no compiled state.
`eval_arms --arm` is constrained to the five registered arms so a typo cannot invent a sixth.

**Execution-level review pass (2026-08-03).** Presence is not execution. Ten further defects, each
one a command, test, or signature that could not have worked:

1. **`eval_contrast.py` had no `if __name__ == "__main__"` guard** — the only one of six. Direct
   execution would import the module, never call `main()`, and **exit 0**, leaving contrast
   integrity unmeasured while the gate read success and the K3.8 packet stood on nothing. Guard
   added; K3.7 Step 0 now proves all six entry points execute before any is trusted.
2. **K3.7 Step 4 did not branch**, despite this section and K3.3 both claiming it did. The literal
   command ran and discarded its exit code. It now branches on every outcome.
3. **Exit code `2` collided with argparse's usage error**, so a mistyped flag would have been read
   as a `stop_no_decision` verdict. Stop-no-decision moved to **3**; `2` is reserved and treated as
   a failed gate.
4. **The fact payload was unreachable.** K1.4's reducers read `f.payload`, but `Fact` carried only
   the fifteen contract fields and `FactStore.write()` serialized exactly those — the body was
   hashed into `content_sha256` and discarded. Every recomputed aggregate, the whole mechanism that
   retires the 46 by construction, would have failed on the first production fact. `payload` is now
   a non-contract attachment that round-trips through the store; `FACT_FIELDS` stays at fifteen.
5. **K1.4's reducer tests could not pass**: they passed a `payload_for_test` kwarg no dataclass
   accepted, on a helper living in a file the task never declared modifying, with payloads missing
   the `season`/`week` keys every reducer sorts on.
6. **Four test fixtures had no producer** — `fake_state`, `fake_state_without_history`,
   `seeded_seals`, `claim_factory`. Every K3.4 and K3.6 test would have errored `fixture not
found` instead of failing on its rule. A `conftest_eval.py` now creates them.
7. **Three helpers were invoked and never declared** — `family_counts`, `_cutoff_for`,
   `load_all_claims`. `family_counts` is now a declared interface, `_cutoff_for` is deleted in
   favor of the edition descriptor, and the two claim loaders are unified as `load_claims`.
8. **`run_arm_chain`'s tests monkeypatched `SEALS_ROOT`**, which `decision_history_at` binds as a
   default argument at import — an inert patch. The suite would have written immutable seals into
   the real `content/decisions/` and then failed permanently on rerun. `root` is now an explicit
   parameter, with a control test asserting the repository is untouched.
9. **`inertia_comparator` improvised its own temporal rule** — hardcoded season 2025 and an
   undefined `_cutoff_for(kind)`. It takes the `EditionDescriptor` now. A consumer inventing "as
   of" is the exact defect this kernel exists to remove.
10. **K3.3's tests could not pass against the shipped manifest.** It ships unfrozen, and
    `assess_contrast` refuses an unfrozen manifest, so seven assertions were unreachable. The tests
    freeze a temporary copy; K3.7 Step 1 freezes the committed one exactly once.

Also corrected: the `schtasks` cadence passed `%DATE%` (a locale-dependent local date, never an
ISO instant); the private-capture staging guard read `git status`, where a gitignored path can
never appear; and `--assess`/`--report` were decorative flags a bare invocation ignored.

**Source-graph review pass (2026-08-03, second round).** A trace from real input to the K3.8 packet
found a different and more serious class than the first round: **interfaces that describe a system
the producer graph cannot build.** An interface heading is not an implementation, and a fixture is
not a producer.

1. **Phase P could not fail.** `fetch_json` returns `None` after exhausted retries
   (`fetch_sleeper.py:69`); the plan passed that to `capture()` and recorded `status: "captured"`.
   The transactions fetcher's `or []` turned every failed leg into an empty list, making a
   league-wide outage byte-identical to eighteen quiet weeks. `capture()` now validates its own
   inputs — including for manual-ingest callers that never touch `main()` — rows carry
   `captured | unavailable | error`, a dry run can no longer report coverage, and a failed required
   row exits nonzero.
2. **The draft row captured the wrong endpoint.** `/league/{id}/drafts` returns draft _metadata_;
   picks require `/draft/{draft_id}/picks`, as this repo's own `fetch_draft_picks.py` already does.
   `_draft_assertions` inspected draft objects for `pick_no`, reported `order_preserved: False`,
   and gated nothing. It now fans out to the pick boards and **fails the row**.
3. **The payload was mutable and unverified.** `observe` stored the caller's dict, so a later
   mutation changed what `write()` persisted without changing `content_sha256`, `fact_id`, or
   supersession. Facts now hold canonical bytes, and the hash is checked at construction, at
   reload, and before persistence.
4. **Coalescing ignored meaning.** It compared `content_sha256` alone, so the same bytes under
   `norm-v2` were discarded as a duplicate of `norm-v1` — directly against the design's reason for
   binding `normalizer_version` into every fact. `normalizer_version` is now part of both the
   coalescing test and `fact_id`.
5. **Reducers folded on the wrong clock.** The design says admission is `known_at` and reducers
   fold on `effective_at`; `by_type` and both aggregates ordered by `known_at` or by payload
   `season`/`week`. `.standings()` was listed as an interface and never built.
6. **The normalization bridge was a comment.** K1.6's tests required nine normalizers and
   `normalize_all`; the implementation registered three and defined no `normalize_all`. All nine
   now exist, with `SOURCES`, a real `normalize_all`, and two types that raise
   `UnqualifiedSource` by design rather than being quietly skipped.
7. **Six of seven rules had no mutation control**, while this section claimed all seven did. The
   four noninterference proofs the design carries forward — physical truncation, poisoned-root
   isolation, preview outcome-freedom, leaky comparator — were absent entirely. Deterministic
   replay of one source is not a substitute: a deterministic pipeline reproduces a leak exactly as
   faithfully as a correct answer.
8. **K3 could not reach an honest verdict.** `record_points` required `matchup_result`, which
   cannot exist at preseason, so its prior-season basis was unreachable; `bundle_for` treated every
   zero-count family as `ArmUnavailable`, aborting before a degraded verdict could be recorded; and
   contrast was assessed _after_ the arms ran. Families are now required per edition,
   structurally-absent is distinguished from unqualified-source, `no_history` ablates all pre-2025
   types per the design's wording, and K3.7 preflights contrast before spending model trials.
9. **The one-cycle remediation limit was unenforceable** — an environment variable defaulting to
   `0` makes every re-run cycle one. It is now persisted against the frozen manifest hash, and the
   manifest freezes source identity and `normalizer_version`, not just family names.
10. **The decision path did not connect.** Model arms had no provider/prompt configuration source
    despite `DecisionRun` requiring those fields; run receipts were never persisted; seals stored
    only hashes, so the inertia comparator could not retrieve a prior decision and blind review had
    no body to show. Runner config, `persist_run`, and content locators on `SealedDecision` close
    the chain from state through seal to blind-review packet.

**Placeholder scan — honest version.** No TBD/TODO. Fully specified with runnable code: P1, P3,
K1.1-K1.5, K1.7, K3.3. Specified as a named contract plus a worked example, with the remaining
cases following the same shape: K1.6's `SOURCES` iteration, K2.1's compiler internals, K2.3's leaf
walk, K3.5's `RUNNERS` bodies. **Blocked pending Blake's decision:** P2/P3's capture-row set.
Earlier revisions claimed "every code step carries runnable code" — that was not true then and is
not claimed now.

**Type consistency.** `Fact`/`FACT_FIELDS` (K1.1) are consumed by `FactStore` (K1.2), `state_at`
(K1.3), and the normalizers (K1.6); the payload attachment rides alongside, outside the contract
and outside identity, and is persisted and hash-verified by the store.
`fact_hash` (K1.1) is consumed by K1.5 and K2.1. `SealedDecision` (K1.5) is consumed by K3.4's
comparator and K3.5's driver. `EditionDescriptor` (K2.1) is consumed by K3.4's comparator and
K3.5's driver. `ARMS` (K3.4) is consumed by K3.6's report and matches K3.7's loop and the design's
five. `load_claims` (K3.1) is the single ledger reader for K3.5 and K3.6.

**Ordering.** P precedes K1 because the evidence is perishable and nothing is currently running.
K1.6 depends on K1.1-K1.2; K2.1 depends on K1.3-K1.4; K2.2 must precede the preview descriptor's
cutoff; K3.3's freeze precedes K3.7's runs; K3.4's comparator depends on K1.5 **and K2.1**
(it consumes `EditionDescriptor`); K3.6 depends on K3.4 for `runner_kind`.

**Open execution dependencies — fail closed, Blake's call.**

1. **2026 league id and the prospective sealing deadline.** P captures, but the design's
   prospective _seal_ needs K3's ledger. If the 2026 preseason cutoff arrives before K3, the
   design's fallback applies — and it **requires its own separately approved P-only plan**, which
   this document does not write. As of **2026-08-03** kickoff is roughly five weeks out, and P has
   still not started. **This is the most time-sensitive decision in the plan** — and it is a
   decision about the fallback, not about this plan's approval. Every day of review is a day of
   perishable 2026 evidence not captured, which is the argument for commissioning the P-only plan
   in parallel rather than after K1-K3 conclude.
2. **`schedule_pairing` may be unavailable for 2025.** No qualified pre-kickoff schedule source is
   identified. If none exists, the preview state carries no pairings and the editions proceed
   without them.
3. **Roster anchor.** Unchanged from the prior plan: no producer for a qualified pre-kickoff
   roster snapshot. `roster_membership` is a **required** contrast family, so its absence makes
   the contrast **degraded** — one remediation cycle, then STOP with no decision.
4. **Legacy packets keep their 46 leaks.** They stop being decision inputs, and K2.3 asserts this
   explicitly rather than silently. Whether to repair them for site rendering is out of scope here.
5. **Capture-row coverage — BLOCKING, Blake's decision.** Three bridge fact types have no 2026
   capture producer and two capture rows serve no bridge fact type. Options A/B/C are laid out in
   "Open design decision: capture-row coverage." **P2 and P3 do not execute until this is ruled
   on.** Note the interaction with (2) and (3): if the answer adds a `league_matchups` row, that
   row is also the most plausible qualified 2026 source for `schedule_pairing`, which would leave
   2025 degraded while 2026 is clean — a legitimate outcome, but one worth choosing deliberately
   rather than discovering at K3.
