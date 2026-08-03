# Jailyard Temporal Kernel — Implementation Plan (P → K1 → K2 → K3 → STOP)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Status:** DRAFT — awaiting Blake review. Not authorized for implementation.

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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "data" / "captures" / "2026" / "public"
PRIVATE_ROOT = ROOT / "private_captures" / "2026"      # gitignored, never staged
VALID_PRIVACY = {"public", "private"}


def content_sha256(obj) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def capture(source, payload, known_at_rule, privacy, captured_at):
    if privacy not in VALID_PRIVACY:
        raise ValueError(f"privacy must be one of {sorted(VALID_PRIVACY)}")
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

- [ ] **Step 4: Run to verify it passes** → 4 passed

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

**Interfaces:** Produces `SOURCE_FETCHERS`, `TRANSACTION_LEGS`, `load_capture_table()`

- [ ] **Step 1: Write the failing test**

```python
from scripts.capture_2026 import load_capture_table, TRANSACTION_LEGS, SOURCE_FETCHERS

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
```

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


def _get(suffix):
    from fetch_sleeper import fetch_json      # constant-host, validated helper
    return fetch_json(suffix)


SOURCE_FETCHERS = {
    "sleeper_league": lambda lid: _get(f"/league/{lid}"),
    "sleeper_users": lambda lid: _get(f"/league/{lid}/users"),
    "rosters": lambda lid: _get(f"/league/{lid}/rosters"),
    "draft": lambda lid: _get(f"/league/{lid}/drafts"),
    "transactions": lambda lid: {str(g): (_get(f"/league/{lid}/transactions/{g}") or [])
                                 for g in TRANSACTION_LEGS},
}
```

Write `capture-manual-ingest.md` with one section per manual row (`#projections`, `#injuries`,
`#chat`) giving the source, the exact `capture(...)` invocation, the `known_at` justification, and
for chat that it is private-class and lands in `PRIVATE_ROOT`.

- [ ] **Step 5: Run** → 5 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/capture_2026.py content/governance/capture_table.json docs/superpowers/plans/capture-manual-ingest.md scripts/tests/test_capture_2026.py
git commit -m "feat(capture): fetch per row, offseason-capable transaction legs"
```

---

### Task P3: Baseline capture, eight-row accounting, daily cadence

**Files:** Modify `scripts/capture_2026.py`; create
`.github/workflows/capture-preseason-2026.yml`, `scripts/tests/test_capture_accounting.py`

**Interfaces:** Produces `accounting_receipt(now_utc, league_id, dry_run=False) -> dict`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.capture_2026 import accounting_receipt, load_capture_table

def test_accounts_for_every_row():
    r = accounting_receipt("2026-08-02T00:00:00Z", None, dry_run=True)
    assert {e["source"] for e in r["rows"]} == {x["source"] for x in load_capture_table()}
    assert len(r["rows"]) == 8

def test_every_row_captured_or_unavailable_with_a_trigger():
    for e in accounting_receipt("2026-08-02T00:00:00Z", None, dry_run=True)["rows"]:
        assert e["status"] in {"captured", "unavailable"}
        if e["status"] == "unavailable":
            assert e["acquisition_trigger"], e["source"]

def test_draft_row_asserts_picks_and_order():
    r = accounting_receipt("2026-08-02T00:00:00Z", None, dry_run=True)
    d = next(e for e in r["rows"] if e["source"] == "draft")
    assert "pick_count" in d["assertions"] and "order_preserved" in d["assertions"]

def test_no_private_payload_in_the_receipt():
    assert "payload" not in json.dumps(
        accounting_receipt("2026-08-02T00:00:00Z", None, dry_run=True))
```

- [ ] **Step 2: Run to verify it fails** → `ImportError`

- [ ] **Step 3: Implement**

```python
def _draft_assertions(payload):
    """A draft object is not proof. Prove picks AND order survived."""
    picks = payload if isinstance(payload, list) else (payload or {}).get("picks", [])
    nos = [p.get("pick_no") for p in picks if isinstance(p, dict)]
    return {"pick_count": len(picks),
            "order_preserved": bool(nos) and nos == sorted(nos) and None not in nos}


def accounting_receipt(now_utc, league_id, dry_run=False):
    rows = []
    for row in load_capture_table():
        src = row["source"]
        fetcher = SOURCE_FETCHERS.get(src)
        if fetcher is None:
            rows.append({"source": src, "status": "unavailable", "privacy": row["privacy"],
                         "acquisition_trigger": row["manual_ingest_doc"], "assertions": {}})
            continue
        if dry_run:
            rows.append({"source": src, "status": "captured", "privacy": row["privacy"],
                         "acquisition_trigger": None,
                         "assertions": {"pick_count": 0, "order_preserved": True}
                         if src == "draft" else {}})
            continue
        payload = fetcher(league_id)
        path = capture(src, payload, row["known_at_rule"], row["privacy"], now_utc)
        rec = json.loads(Path(path).read_text(encoding="utf-8"))
        rows.append({"source": src, "status": "captured", "privacy": row["privacy"],
                     "captured_at": rec["captured_at"],
                     "content_sha256": rec["content_sha256"],
                     "acquisition_trigger": None,
                     "assertions": _draft_assertions(payload) if src == "draft" else {}})
    return {"season": 2026, "generated_at": now_utc, "rows": rows}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--league-id")
    ap.add_argument("--now-utc", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    r = accounting_receipt(a.now_utc, a.league_id, dry_run=a.dry_run)
    save_json_canonical(
        PUBLIC_ROOT / "_receipts" / f"{a.now_utc.replace(':', '').replace('-', '')}.json", r)
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Take the baseline capture — do this before starting K1**

```bash
$PY scripts/capture_2026.py --league-id <2026_LEAGUE_ID> --now-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

- [ ] **Step 5: Stage the public root only**

```bash
git add data/captures/2026/public/
git status --short | grep -q private_captures && { echo "STOP: private capture staged"; exit 1; }
git commit -m "data(capture): baseline 2026 public capture with accounting receipt"
```

- [ ] **Step 6: Daily local capture until the workflow is activated**

A phase-boundary checkpoint is not a cadence. Register it so it survives an unattended day:

```bash
schtasks //Create //SC DAILY //ST 06:00 //TN "JailyardCapture2026" //TR \
  "cmd /c cd /d C:\\Users\\blake\\projects\\Jailyard-Dynasty-Power-Rankings && \
   C:\\Users\\blake\\AppData\\Local\\Programs\\Python\\Python312\\python.exe \
   scripts\\capture_2026.py --league-id <ID> --now-utc %DATE%T06:00:00Z"
```

The append-only store refuses same-instant overwrites, so a duplicate run is free.

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

## K1 — The temporal kernel

### Task K1.1: Fact schema

**Files:** Create `scripts/fact_schema.py`, `content/governance/fact_types.json`,
`scripts/tests/test_fact_schema.py`

**Interfaces:**

- Produces: `Fact` (frozen dataclass, 15 fields), `validate(fact) -> list[str]`,
  `fact_hash(payload) -> str`, `load_fact_types() -> dict`, `FACT_FIELDS`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.fact_schema import Fact, validate, FACT_FIELDS, load_fact_types

def mk(**over):
    base = dict(fact_id="f1", source_record_id="txn:1", entity_ref={"type": "player", "id": "6949"},
                source_ref="capture:2026/public/transactions/20260802T000000Z",
                fact_type="transaction", effective_at="2025-09-05T20:10:20Z",
                known_at="2025-09-05T20:10:20Z", access_scope="public",
                known_at_basis="effective_completion_instant", captured_at="2026-02-17T00:00:00Z",
                content_sha256="sha256:" + "a" * 64, privacy="public",
                normalizer_version="norm-v1", schema_version=1, supersedes=None)
    base.update(over)
    return Fact(**base)

def test_all_fifteen_fields_present():
    assert len(FACT_FIELDS) == 15
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


FACT_FIELDS = tuple(f.name for f in fields(Fact))


def load_fact_types():
    return load_json(FACT_TYPES_PATH, required=True)["types"]


def fact_hash(payload) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


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

- [ ] **Step 5: Run to verify it passes** → 8 passed

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
    import pytest
    s = FactStore(tmp_path / "facts.jsonl")
    with pytest.raises(ValueError):
        s.observe(payload={"v": 1}, **dict(OBS, access_scope="everyone"))

def test_write_is_byte_stable(tmp_path):
    s = FactStore(tmp_path / "f.jsonl")
    s.observe(payload={"v": 1}, **OBS)
    s.observe(payload={"v": 2}, **dict(OBS, source_record_id="txn:2"))
    s.write(); first = (tmp_path / "f.jsonl").read_bytes()
    s.write(); assert (tmp_path / "f.jsonl").read_bytes() == first
```

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
                    self._facts.append(Fact(**json.loads(line)))

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
        if prior is not None and prior.content_sha256 == digest:
            return prior, "coalesced"          # identical repeat: nothing changes
        fact = Fact(
            fact_id=fact_hash({"srid": meta["source_record_id"], "content": digest,
                               "known_at": meta["known_at"]}).replace("sha256:", "fact:"),
            content_sha256=digest, schema_version=SCHEMA_VERSION,
            supersedes=(prior.fact_id if prior is not None else None),
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
        body = "\n".join(
            json.dumps({k: getattr(f, k) for k in FACT_FIELDS},
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            for f in ordered)
        self.path.write_text(body + ("\n" if body else ""), encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Run to verify it passes** → 5 passed

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
        return [f for f in self.admitted if f.fact_type == fact_type]

    def value(self, source_record_id):
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


def _load_default_facts(season):
    from fact_store import FactStore
    root = Path(__file__).resolve().parents[1]
    return FactStore(root / "data" / "facts" / f"{season}.jsonl").load()
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
    return F(fact_id=f"m{rid}", source_record_id=f"match:{season}:{week}:{rid}",
             fact_type="matchup_result", entity_ref={"type": "matchup", "id": str(rid)},
             effective_at=known_at, known_at=known_at,
             payload_for_test={"home": home, "away": away, "home_pts": hp, "away_pts": ap})

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
```

`F` gains a `payload_for_test` passthrough so reducer tests can carry a body; production facts
carry their payload in the store beside the hash.

- [ ] **Step 2: Run to verify it fails** → `AttributeError: 'LeagueState' object has no attribute 'h2h'`

- [ ] **Step 3: Implement** — add to `LeagueState`

```python
    def h2h(self, a, b):
        """Head-to-head from admitted meetings only. Never a stored aggregate."""
        games = [f for f in self.by_type("matchup_result") + self.by_type("historical_matchup")
                 if {f.payload["home"], f.payload["away"]} == {a, b}]
        games.sort(key=lambda f: (f.payload["season"], f.payload["week"]))
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
        for g in sorted(games, key=lambda f: (f.payload["season"], f.payload["week"])):
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


def _winner(p):
    return p["home"] if p["home_pts"] > p["away_pts"] else p["away"]
```

- [ ] **Step 4: Run to verify it passes** → 4 passed

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
  `decision_history_at(season, cutoff, arm_id, trial_id) -> list[SealedDecision]`,
  `CrossArmContamination`

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


def seal(root, edition_id, season, cutoff_utc, arm_id, trial_id, state_hash,
         ranking, claims, run_id):
    rh, ch = fact_hash(ranking), fact_hash(claims)
    body = {"edition_id": edition_id, "season": season, "cutoff_utc": cutoff_utc,
            "arm_id": arm_id, "trial_id": trial_id, "state_hash": state_hash,
            "run_id": run_id, "ranking_hash": rh, "claims_hash": ch}
    s = SealedDecision(**body, decision_hash=fact_hash(body))
    p = Path(root) / f"{season}" / arm_id / f"trial{trial_id}" / f"{edition_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        raise FileExistsError(f"seal already exists and is immutable: {p}")
    save_json_canonical(p, asdict(s))
    return s


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


NORMALIZERS = {
    "schedule_pairing": _schedule_pairing,
    "transaction": _transaction,
    "chat_message": _chat_message,
    # franchise_identity, matchup_result, roster_membership, draft_pick,
    # historical_matchup and nfl_game follow the same shape: derive an exact
    # known_at from the type's registered basis, or raise UnqualifiedSource.
}
```

Each remaining normalizer is written the same way against its registered
`known_at_basis` in `fact_types.json`. `historical_matchup` reads
`data/{2022,2023,2024}/season_combined.json` with `known_at` = each game's conclusion.

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
"""The seven K1 rules. Each test is accompanied by a mutation proving it can fail."""
import pytest
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

# 3 -------------------------------------------------------------------------
def test_3_late_capture_excluded_from_as_recorded_replay():
    facts = [F(fact_id="early", source_record_id="a", captured_at="2026-01-01T00:00:00Z"),
             F(fact_id="late", source_record_id="b", captured_at="2026-08-01T00:00:00Z")]
    vantage = state_at(2025, "2025-12-01T00:00:00Z", "public",
                       as_recorded_at="2026-03-01T00:00:00Z", facts=facts)
    latest = state_at(2025, "2025-12-01T00:00:00Z", "public", facts=facts)
    assert {f.fact_id for f in vantage.admitted} == {"early"}
    assert {f.fact_id for f in latest.admitted} == {"early", "late"}

# 4 -------------------------------------------------------------------------
def test_4_private_scope_exclusion_via_the_shipped_interface():
    facts = [F(fact_id="pub", source_record_id="a"),
             F(fact_id="priv", source_record_id="b", access_scope="league_private",
               fact_type="chat_message")]
    assert {f.fact_id for f in state_at(2025, "2025-12-01T00:00:00Z",
                                        "league_private", facts=facts).admitted} == {"pub", "priv"}
    assert {f.fact_id for f in state_at(2025, "2025-12-01T00:00:00Z",
                                        "public", facts=facts).admitted} == {"pub"}

# 5 -------------------------------------------------------------------------
def test_5_schedule_provenance_failure_is_unavailable():
    with pytest.raises(UnqualifiedSource):
        NORMALIZERS["schedule_pairing"]({"source": "weekly_packet"}, season=2025)

# 6 -------------------------------------------------------------------------
def test_6_three_step_correction_chain():
    a = F(fact_id="a", source_record_id="r", known_at="2025-09-01T00:00:00Z")
    b = F(fact_id="b", source_record_id="r", known_at="2025-09-05T00:00:00Z", supersedes="a")
    c = F(fact_id="c", source_record_id="r", known_at="2025-09-09T00:00:00Z", supersedes="b")
    for cutoff, want in (("2025-09-02T00:00:00Z", "a"), ("2025-09-06T00:00:00Z", "b"),
                         ("2025-09-10T00:00:00Z", "c")):
        assert state_at(2025, cutoff, "public", facts=[a, b, c]).value("r").fact_id == want

# 7 -------------------------------------------------------------------------
def test_7_cross_arm_predecessor_poisoning(tmp_path):
    other = seal(root=tmp_path, edition_id="pre", season=2025,
                 cutoff_utc="2025-09-03T23:59:59Z", arm_id="no_chat", trial_id=1,
                 state_hash="sha256:" + "a" * 64, ranking={"entries": []}, claims=[],
                 run_id="r1")
    with pytest.raises(CrossArmContamination):
        verify_predecessor(other, arm_id="full_rich", trial_id=1)

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

- [ ] **Step 2: Run** → 9 passed. **If any mutation control passes without its rule disabled, the
      rule is not doing work — fix the rule, never the test.**

- [ ] **Step 3: Run the full suite**

```bash
$PY -m pytest scripts/tests/ -q
```

Expected: ≥ 343 passed / 2 skipped, plus the new tests.

- [ ] **Step 4: Commit**

```bash
git add scripts/tests/test_k1_discriminating.py
git commit -m "test(kernel): seven discriminating rules with mutation controls"
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
`CLAIM_TYPES`, `HORIZONS`

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

**Interfaces:** `DecisionRun`, `open_run(...)`, `close_run(run, output_decision_hash)`,
`RUNNER_KINDS`

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

**Interfaces:** `load_manifest()`, `freeze_manifest()`, `assess_contrast(manifest, full, minimal,
remediation_cycles_used) -> ContrastResult` with `.status` in
`{"ok", "degraded", "stop_no_decision"}`

- [ ] **Step 1: Write the failing test**

```python
from scripts.eval_contrast import load_manifest, assess_contrast

REQUIRED = {"roster_membership", "historical_matchup", "chat_message", "nfl_game"}

def test_manifest_requires_exactly_the_four_families():
    m = load_manifest()
    assert {f["family"] for f in m["families"] if f["required"]} == REQUIRED

def test_media_is_explicitly_excluded():
    m = load_manifest()
    media = next(f for f in m["families"] if f["family"] == "media_item")
    assert media["required"] is False and "S1b" in media["rationale"]

def test_missing_required_family_is_degraded():
    full = {"roster_membership": 12, "historical_matchup": 0, "chat_message": 900, "nfl_game": 16}
    r = assess_contrast(load_manifest(), full, {"roster_membership": 12}, 0)
    assert r.status == "degraded" and "historical_matchup" in r.missing

def test_absent_media_does_not_degrade():
    full = {"roster_membership": 12, "historical_matchup": 400, "chat_message": 900,
            "nfl_game": 16, "media_item": 0}
    r = assess_contrast(load_manifest(), full, {"roster_membership": 12}, 0)
    assert r.status == "ok"

def test_identical_bundles_are_degraded_even_when_complete():
    full = {"roster_membership": 12, "historical_matchup": 400, "chat_message": 900, "nfl_game": 16}
    r = assess_contrast(load_manifest(), full, dict(full), 0)
    assert r.status == "degraded" and "no measurable difference" in r.reason

def test_second_degraded_cycle_stops():
    full = {"roster_membership": 12, "historical_matchup": 0, "chat_message": 900, "nfl_game": 16}
    r = assess_contrast(load_manifest(), full, {"roster_membership": 12}, 1)
    assert r.status == "stop_no_decision"
    assert "S1a does not begin" in r.reason

def test_manifest_hash_is_frozen_before_arms_run():
    m = load_manifest()
    assert m.get("frozen_at") and m.get("manifest_sha256", "").startswith("sha256:")
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

`freeze_manifest()` stamps `frozen_at` and `manifest_sha256` and refuses to run if already frozen;
`assess_contrast` refuses an unfrozen manifest.

- [ ] **Step 4: Run** → 7 passed

- [ ] **Step 4b: Add the CLI** — K3.7 Step 4 invokes this script

```python
def main():
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--assess", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--full-arm", default="full_rich")
    ap.add_argument("--minimal-arm", default="minimal_legal")
    ap.add_argument("--remediation-cycles-used", type=int, default=0)
    a = ap.parse_args()
    if a.freeze:
        print(json.dumps(freeze_manifest(), indent=2))
        return 0
    r = assess_contrast(load_manifest(), family_counts(a.full_arm),
                        family_counts(a.minimal_arm), a.remediation_cycles_used)
    print(json.dumps({"status": r.status, "missing": r.missing, "reason": r.reason}, indent=2))
    return {"ok": 0, "degraded": 1, "stop_no_decision": 2}[r.status]
```

Exit codes are distinct: **0** ok, **1** degraded (one remediation cycle permitted), **2**
stop-no-decision. K3.7 Step 4 branches on them.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_contrast.py content/governance/evidence_families.json scripts/tests/test_eval_contrast.py
git commit -m "feat(eval): frozen evidence manifest, bounded degradation, media excluded"
```

---

### Task K3.4: The five arms and the inertia comparator

**Files:** Create `scripts/eval_arms.py`, `scripts/tests/test_eval_arms.py`

**Interfaces:** `ARMS` (five), `bundle_for(arm_id, state)`, `inertia_comparator(arm_id, trial_id,
edition_kind, root) -> SealedDecision | None`, `ArmUnavailable`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.eval_arms import ARMS, bundle_for, inertia_comparator, ArmUnavailable

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
    b = bundle_for("no_chat", fake_state)
    assert "chat_message" not in b["families"] and "historical_matchup" in b["families"]

def test_no_history_bundle_omits_pre_2025_facts(fake_state):
    b = bundle_for("no_history", fake_state)
    assert "historical_matchup" not in b["families"] and "chat_message" in b["families"]

def test_minimal_bundle_is_a_strict_subset_of_full(fake_state):
    assert set(bundle_for("minimal_legal", fake_state)["families"]) < \
           set(bundle_for("full_rich", fake_state)["families"])

def test_no_inertia_comparator_at_preseason(tmp_path):
    assert inertia_comparator("full_rich", 1, "preseason", root=tmp_path) is None

def test_comparator_uses_the_same_arms_predecessor(tmp_path, seeded_seals):
    c = inertia_comparator("full_rich", 1, "preview", root=tmp_path)
    assert c is not None and c.arm_id == "full_rich" and c.trial_id == 1

def test_comparator_absent_without_a_qualified_predecessor(tmp_path):
    assert inertia_comparator("no_chat", 1, "preview", root=tmp_path) is None

def test_unavailable_family_makes_its_arm_unavailable(fake_state_without_history):
    with pytest.raises(ArmUnavailable):
        bundle_for("no_history", fake_state_without_history)
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""The five K3 data-layer arms. Inertia is a comparator inside each, never an arm."""
ARMS = {
    "record_points": {"runner_kind": "deterministic", "families": ["matchup_result"],
                      "preseason_basis": "prior_season_final_standings"},
    "minimal_legal": {"runner_kind": "model",
                      "families": ["franchise_identity", "draft_pick", "roster_membership"]},
    "full_rich":     {"runner_kind": "model",
                      "families": ["franchise_identity", "draft_pick", "roster_membership",
                                   "historical_matchup", "chat_message", "nfl_game",
                                   "matchup_result", "schedule_pairing"]},
    "no_chat":       {"runner_kind": "model", "ablates": ["chat_message"]},
    "no_history":    {"runner_kind": "model", "ablates": ["historical_matchup"]},
}


def inertia_comparator(arm_id, trial_id, edition_kind, root):
    """The unchanged prior seal of THIS arm, or None where no qualified predecessor exists."""
    from decision_history import decision_history_at
    if edition_kind == "preseason":
        return None                      # nothing to carry forward; invent nothing
    prior = decision_history_at(2025, _cutoff_for(edition_kind), arm_id, trial_id, root=root)
    return prior[-1] if prior else None
```

- [ ] **Step 4: Run** → 11 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_arms.py scripts/tests/test_eval_arms.py
git commit -m "feat(eval): five arms with per-arm inertia comparators"
```

---

### Task K3.5: Chronological execution driver

**Files:** Modify `scripts/eval_arms.py`; create `scripts/tests/test_chronological.py`

**Interfaces:** `run_arm_chain(arm_id, trial_id, editions) -> list[SealedDecision]`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.eval_arms import run_arm_chain
from scripts.decision_history import CrossArmContamination

EDITIONS = ["2025-preseason", "2025-wk01-preview", "2025-wk01-recap"]

def test_chain_seals_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.decision_history.SEALS_ROOT", tmp_path)
    seals = run_arm_chain("full_rich", 1, EDITIONS)
    assert [s.edition_id for s in seals] == EDITIONS
    assert seals[0].cutoff_utc < seals[1].cutoff_utc < seals[2].cutoff_utc

def test_preview_consumes_its_own_preseason_seal(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.decision_history.SEALS_ROOT", tmp_path)
    seals = run_arm_chain("full_rich", 1, EDITIONS)
    assert all(s.arm_id == "full_rich" and s.trial_id == 1 for s in seals)

def test_arm_cannot_consume_another_arms_seal(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.decision_history.SEALS_ROOT", tmp_path)
    run_arm_chain("no_chat", 1, EDITIONS[:1])
    with pytest.raises(CrossArmContamination):
        run_arm_chain("full_rich", 1, EDITIONS[1:], _force_predecessor_arm="no_chat")

def test_recap_grades_this_arms_prior_claims(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.decision_history.SEALS_ROOT", tmp_path)
    seals = run_arm_chain("full_rich", 1, EDITIONS)
    from scripts.claims_ledger import load_claims
    graded = [c for c in load_claims(root=tmp_path) if c.outcome is not None]
    assert graded and all(c.arm_id == "full_rich" for c in graded)

def test_a_seal_cannot_be_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.decision_history.SEALS_ROOT", tmp_path)
    run_arm_chain("full_rich", 1, EDITIONS[:1])
    with pytest.raises(FileExistsError):
        run_arm_chain("full_rich", 1, EDITIONS[:1])
```

- [ ] **Step 2: Run to verify it fails** → `ImportError: cannot import name 'run_arm_chain'`

- [ ] **Step 3: Implement** — for each edition in order: load the compiled state, build the arm's
      bundle, resolve the predecessor via `decision_history_at` + `verify_predecessor`, open a
      decision run, produce ranking + claims, grade any resolvable prior claims, seal, close the
      run.

- [ ] **Step 4: Run** → 5 passed

- [ ] **Step 4b: Add the CLI** — K3.7 Step 3 invokes this script

```python
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--trial", type=int, required=True)
    ap.add_argument("--editions", required=True,
                    help="comma-separated edition ids, in chronological order")
    a = ap.parse_args()
    editions = [e.strip() for e in a.editions.split(",") if e.strip()]
    seals = run_arm_chain(a.arm, a.trial, editions)
    for s in seals:
        print(f"{s.edition_id} {s.arm_id} trial{s.trial_id} {s.decision_hash[:19]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`--arm` is constrained to the five registered arms, so a typo cannot silently create a sixth.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval_arms.py scripts/tests/test_chronological.py
git commit -m "feat(eval): chronological per-arm chains with closed decision lineage"
```

---

### Task K3.6: Scoring and fixed aggregation

**Files:** Create `scripts/eval_scoring.py`, `scripts/tests/test_eval_scoring.py`

**Interfaces:** `score_claim(claim) -> float | None`, `aggregate(claims) -> dict`,
`AGGREGATION_ORDER`, `MIN_TRIALS_NONDETERMINISTIC`

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
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--arm")
    a = ap.parse_args()
    claims = load_all_claims()
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

- [ ] **Step 1: Freeze the manifest before anything runs**

```bash
$PY -c "from scripts.eval_contrast import freeze_manifest; print(freeze_manifest())"
```

Records `frozen_at` and `manifest_sha256`. **No source may be added after this point** — a
manifest change invalidates every completed arm.

- [ ] **Step 2: Compile the three states**

```bash
for e in 2025-preseason 2025-wk01-preview 2025-wk01-recap; do
  $PY scripts/compile_state.py --descriptor "content/editions/$e/descriptor.json" || exit 1
done
$PY scripts/migration_census.py --all
```

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

- [ ] **Step 4: Assess contrast integrity**

```bash
$PY scripts/eval_contrast.py --assess --full-arm full_rich --minimal-arm minimal_legal
```

If this returns `degraded`, **one** approved remediation cycle is permitted. If it returns
`stop_no_decision`, go directly to K3.8 and record NO DECISION.

- [ ] **Step 5: Score and aggregate**

```bash
$PY scripts/eval_scoring.py --report > content/editions/_evaluation/scores.json
```

- [ ] **Step 6: Randomized blind review**

Present unlabeled arm outputs to Blake in randomized order for ranking on prose and judgment
quality. Record at `content/editions/_evaluation/blind_review.json` with the label mapping sealed
separately. **Blind review never overwrites computed scores** — where the two disagree, both are
reported and the disagreement is the finding.

- [ ] **Step 7: Commit**

```bash
git add content/editions/ content/governance/evidence_families.json
git commit -m "eval(k3): five arms, three trials each for model runners, scored and blind-reviewed"
```

---

### Task K3.8: STOP — judge data-layer lift

**Do not begin S1a. Do not build desks, media, or the render lifecycle.**

- [ ] **Step 1: Full sweep**

```bash
$PY -m pytest scripts/tests/ -q
$PY scripts/migration_census.py --all
$PY scripts/generate_chat_provenance.py --verify
```

- [ ] **Step 2: Assemble the review packet**

- state leak census: 0 future entries across all three states; legacy packets unchanged at 46 and
  no longer decision inputs;
- the seven K1 discriminating tests with their mutation controls;
- deterministic replay: facts and state byte-identical across two normalizations;
- per-arm scores with medians and ranges, unresolved and unresolvable counts;
- contrast-integrity verdict and the frozen manifest hash;
- blind review versus computed scores, including any disagreement;
- the 2026 capture accounting receipt and current seal status.

- [ ] **Step 3: Answer in writing**

> **Did richer evidence measurably change the decisions?**

Compare `full_rich` against `minimal_legal`, and each ablation against `full_rich`. Cite specific
ranking movements and claim scores.

- [ ] **Step 4: Record the verdict**

| Verdict                                       | Consequence                                                                   |
| --------------------------------------------- | ----------------------------------------------------------------------------- |
| Lift demonstrated                             | S1a is authorized by Blake — desks built, writer-vs-desks comparison run      |
| No lift                                       | S1a is not authorized; revise source and desk contracts before proposing more |
| Contrast degraded after one remediation cycle | **NO DECISION, NO EXPANSION**; prospective capture and sealing continue       |

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

**Census findings fixed in this pass.** A grep of every `$PY scripts/*.py` invocation against
its creating task found **five scripts invoked with flags and no CLI at all** — `compile_state`,
`migration_census`, `eval_arms`, `eval_contrast`, `eval_scoring`. Every K3.7 command would have
died on an unrecognized argument. Each now has a `main()` in its owning task, and
`migration_census --all` fails rather than passing vacuously when it discovers no compiled state.
`eval_contrast` returns distinct exit codes (0 ok / 1 degraded / 2 stop-no-decision) so K3.7 Step
4 can branch on them, and `eval_arms --arm` is constrained to the five registered arms so a typo
cannot invent a sixth.

**Placeholder scan.** No TBD/TODO. Every code step carries runnable code; every test step carries
real assertions; every command is interpreter-pinned and exact.

**Type consistency.** `Fact`/`FACT_FIELDS` (K1.1) are consumed by `FactStore` (K1.2), `state_at`
(K1.3), and the normalizers (K1.6). `fact_hash` (K1.1) is consumed by K1.5 and K2.1.
`SealedDecision` (K1.5) is consumed by K3.4's comparator and K3.5's driver. `ARMS` keys (K3.4)
match the arms in K3.7's loop and the design's five.

**Ordering.** P precedes K1 because the evidence is perishable and nothing is currently running.
K1.6 depends on K1.1-K1.2; K2.1 depends on K1.3-K1.4; K2.2 must precede the preview descriptor's
cutoff; K3.3's freeze precedes K3.7's runs; K3.4's comparator depends on K1.5.

**Open execution dependencies — fail closed, Blake's call.**

1. **2026 league id and the prospective sealing deadline.** P captures, but the design's
   prospective _seal_ needs K3's ledger. If the 2026 preseason cutoff arrives before K3, the
   design's fallback applies — and it **requires its own separately approved P-only plan**, which
   this document does not write. Given today is 2026-08-02 and kickoff is roughly five weeks out,
   **this is the most time-sensitive decision in the plan.**
2. **`schedule_pairing` may be unavailable for 2025.** No qualified pre-kickoff schedule source is
   identified. If none exists, the preview state carries no pairings and the editions proceed
   without them.
3. **Roster anchor.** Unchanged from the prior plan: no producer for a qualified pre-kickoff
   roster snapshot. `roster_membership` is a **required** contrast family, so its absence makes
   the contrast **degraded** — one remediation cycle, then STOP with no decision.
4. **Legacy packets keep their 46 leaks.** They stop being decision inputs, and K2.3 asserts this
   explicitly rather than silently. Whether to repair them for site rendering is out of scope here.
