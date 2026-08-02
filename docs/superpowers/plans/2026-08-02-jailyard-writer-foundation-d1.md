# Jailyard Writer Foundation — Implementation Plan (through D1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** DRAFT — revised after review of `b57379e`. Awaiting Blake's approval. Not authorized
for implementation.

**Goal:** Make the minimum slice genuinely vertical: preserve 2026 evidence operationally, bind
every writer-facing consumer to edition bundles, prove future evidence cannot influence a bundle,
and produce three canonical editions whose rankings demonstrate a model that became more informed
— then stop.

**Architecture:** A season-parameterized projection compiler is the sole trusted reader of raw and
full-season stores; every writing consumer reads only a persisted edition bundle. Ranking judgment
is recorded before prose and mechanically grounded in bundle evidence. Media is authorized by a
tracked manifest and verified byte-for-byte against the rendered HTML.

**Tech Stack:** Python 3.12 (`python`, not `python3`), pytest, `jsonschema`, stdlib
`hashlib`/`ast`. No new runtime dependencies.

**Design authority:** `docs/superpowers/specs/2026-08-01-jailyard-writer-foundation-design.md`
(APPROVED at `072f4ea`).

## Global Constraints

- Python is invoked as `python`, never `python3` (Windows).
- **`shared.save_json_canonical(path, data, verbose=False)`** — path FIRST. (The prior plan
  revision called it reversed.)
- Scripts runnable under pytest and directly use the sys.path bootstrap from
  `scripts/fetch_nflreadpy.py:20-25`; tests import `from scripts.X import ...`.
- Every new CLI ends `if __name__ == "__main__": raise SystemExit(main())`. A bare `main()` that
  returns 1 still exits 0 — the live `analyze_chat.py:$` has exactly this defect.
- `list(some_set)` is banned where serialized; use `sorted()`.
- `extract_week_data.py` always runs with `--pretty`.
- Baseline suite: **343 passed / 2 skipped** (measured `c751b22`, 2026-08-01, 167s). No task
  reduces this.
- HTML is prettier-excluded; never reformat it.
- Quality gates are binary. No "approve with notes".
- Cutoffs are exact UTC instants under `shared.admissible` (`ts <= cutoff`); a cutoff that must
  exclude an instant is set strictly prior to it.
- **One writer.** "Parallel" for Lane P means evidence preservation continues operationally
  alongside D1 — never two concurrent repository writers.
- This plan performs no pushes and touches no protected untracked paths.

---

## File Structure

| File                                    | Responsibility                                                  |
| --------------------------------------- | --------------------------------------------------------------- |
| `scripts/capture_2026.py`               | Lane P: real capture paths, receipts, offseason transactions    |
| `scripts/as_of_records.py`              | Cutoff-correct records (dated + undated) and H2H slicing        |
| `scripts/source_graph.py`               | AST source-graph census of reads reaching writing decisions     |
| `scripts/cutoff_audit.py`               | Leaf classification + forbidden detection; **has a CLI**        |
| `scripts/edition.py`                    | Descriptor, bundle manifest, authoring manifest, build identity |
| `scripts/project_edition.py`            | The projector: season-parameterized adapters, fail-closed       |
| `scripts/compile_edition.py`            | One command: atomic canonical persist of all edition artifacts  |
| `scripts/kickoff_source.py`             | Qualify the first-kickoff instant from a hashed source          |
| `scripts/rebind_media_catalog.py`       | Unique rebind on asset hash + filename/provenance               |
| `scripts/media_manifest.py`             | Media manifest + publication record                             |
| `scripts/verify_rendered_media.py`      | Multiplicity + location + **byte** bijection; **has a CLI**     |
| `scripts/mine_name_repertoires.py`      | Repertoire mining against real name-map fields                  |
| `scripts/verify_ranking_record.py`      | Ranking grounding gate                                          |
| `content/governance/writer_fields.json` | Leaf classification registry                                    |
| `.claude/commands/desk-*.md` (6)        | Evidence desks + copy editor                                    |

---

## Lane P — 2026 evidence preservation (operational, single-writer)

### Task P1: Capture store with receipts

**Files:** Create `scripts/capture_2026.py`, `scripts/tests/test_capture_2026.py`

**Interfaces:** Produces `capture(source, payload, known_at_rule, privacy, captured_at) -> Path`,
`CAPTURE_ROOT`, `receipt(paths) -> dict`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.capture_2026 import capture, receipt

def test_capture_writes_and_records_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.CAPTURE_ROOT", tmp_path)
    p = capture("league", {"a": 1}, "capture_instant", "public", "2026-08-02T00:00:00Z")
    rec = json.loads(p.read_text(encoding="utf-8"))
    for f in ("source", "captured_at", "known_at_rule", "content_sha256", "privacy", "payload"):
        assert f in rec, f

def test_capture_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.CAPTURE_ROOT", tmp_path)
    kw = ("capture_instant", "public", "2026-08-02T00:00:00Z")
    capture("league", {"a": 1}, *kw)
    try:
        capture("league", {"a": 2}, *kw)
        assert False, "expected FileExistsError"
    except FileExistsError:
        pass

def test_receipt_lists_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.CAPTURE_ROOT", tmp_path)
    p = capture("league", {"a": 1}, "capture_instant", "public", "2026-08-02T00:00:00Z")
    r = receipt([p])
    assert r["count"] == 1 and r["entries"][0]["content_sha256"].startswith("sha256:")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest scripts/tests/test_capture_2026.py -v` → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Append-only capture store for volatile 2026 preseason evidence."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import save_json_canonical  # noqa: E402

CAPTURE_ROOT = Path(__file__).resolve().parents[1] / "data" / "captures" / "2026"
VALID_PRIVACY = {"public", "private"}


def _sha(obj) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def capture(source, payload, known_at_rule, privacy, captured_at):
    if privacy not in VALID_PRIVACY:
        raise ValueError(f"privacy must be one of {sorted(VALID_PRIVACY)}")
    path = CAPTURE_ROOT / source / f"{captured_at.replace(':', '').replace('-', '')}.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite capture: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "source": source,
        "captured_at": captured_at,
        "known_at_rule": known_at_rule,
        "privacy": privacy,
        "content_sha256": _sha(payload),
        "payload": payload,
    }
    save_json_canonical(path, record)          # path FIRST
    return path


def receipt(paths):
    entries = []
    for p in sorted(paths):
        rec = json.loads(Path(p).read_text(encoding="utf-8"))
        entries.append({k: rec[k] for k in
                        ("source", "captured_at", "content_sha256", "privacy")})
    return {"count": len(entries), "entries": entries}
```

- [ ] **Step 4: Run to verify it passes** → 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_2026.py scripts/tests/test_capture_2026.py
git commit -m "feat(capture): append-only 2026 store with receipts, canonical write args correct"
```

---

### Task P2: Working capture path for every minimum-table row

Every row gets a real fetch. `fetch_sleeper.py:172` uses `range(1, len(all_matchups) + 1)` —
`range(1, 1)` preseason — so transactions need an independent leg range.

**Files:** Modify `scripts/capture_2026.py`, `scripts/tests/test_capture_2026.py`;
create `content/governance/capture_table.json`

**Interfaces:** Produces `fetch_source(name, league_id) -> object`, `run_capture(now_utc) -> dict`,
`load_capture_table()`, `TRANSACTION_LEGS`

- [ ] **Step 1: Write the failing test**

```python
from scripts.capture_2026 import load_capture_table, TRANSACTION_LEGS, SOURCE_FETCHERS

REQUIRED = {"sleeper_league", "sleeper_users", "rosters", "draft", "transactions"}

def test_table_covers_minimum_sources():
    assert REQUIRED <= {r["source"] for r in load_capture_table()}

def test_every_row_has_a_working_fetcher_or_manual_doc():
    for r in load_capture_table():
        s = r["source"]
        assert s in SOURCE_FETCHERS or r["mechanism"] == "manual_export", s

def test_transaction_legs_independent_of_scored_matchups():
    assert 1 in TRANSACTION_LEGS and max(TRANSACTION_LEGS) >= 18

def test_manual_rows_document_ingestion():
    for r in load_capture_table():
        if r["mechanism"] == "manual_export":
            assert r.get("manual_ingest_doc"), r["source"]
```

- [ ] **Step 2: Run to verify it fails** → `ImportError: cannot import name 'TRANSACTION_LEGS'`

- [ ] **Step 3: Write the table**

`content/governance/capture_table.json`:

```json
{
  "version": 1,
  "season": 2026,
  "rows": [
    {
      "source": "sleeper_league",
      "mechanism": "api",
      "cadence": "weekly_or_on_change",
      "known_at_rule": "capture_instant",
      "privacy": "public"
    },
    {
      "source": "sleeper_users",
      "mechanism": "api",
      "cadence": "weekly_or_on_change",
      "known_at_rule": "capture_instant",
      "privacy": "public"
    },
    {
      "source": "rosters",
      "mechanism": "api",
      "cadence": "daily_through_preseason",
      "known_at_rule": "capture_instant",
      "privacy": "public"
    },
    {
      "source": "draft",
      "mechanism": "api",
      "cadence": "on_completion_then_weekly",
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
      "cadence": "weekly_through_preseason",
      "known_at_rule": "publication_instant_else_unqualified",
      "privacy": "public",
      "manual_ingest_doc": "docs/superpowers/plans/capture-manual-ingest.md#projections"
    },
    {
      "source": "injuries",
      "mechanism": "manual_export",
      "cadence": "weekly_through_preseason",
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

Reuse `fetch_sleeper.py`'s constant-host request helper and its `# nosemgrep` justification
pattern (`scripts/fetch_draft_picks.py`) — constant `https://api.sleeper.app` host, digits-only
league id.

```python
TRANSACTION_LEGS = list(range(1, 19))   # never derived from len(all_matchups)

CAPTURE_TABLE_PATH = (
    Path(__file__).resolve().parents[1] / "content" / "governance" / "capture_table.json"
)


def load_capture_table():
    from shared import load_json
    return load_json(CAPTURE_TABLE_PATH, required=True)["rows"]


def _get(path_suffix):
    from fetch_sleeper import fetch_json      # constant-host, validated helper
    return fetch_json(path_suffix)


def _league(lid):       return _get(f"/league/{lid}")
def _users(lid):        return _get(f"/league/{lid}/users")
def _rosters(lid):      return _get(f"/league/{lid}/rosters")
def _draft(lid):        return _get(f"/league/{lid}/drafts")


def _transactions(lid):
    return {str(leg): (_get(f"/league/{lid}/transactions/{leg}") or [])
            for leg in TRANSACTION_LEGS}


SOURCE_FETCHERS = {
    "sleeper_league": _league, "sleeper_users": _users, "rosters": _rosters,
    "draft": _draft, "transactions": _transactions,
}


def run_capture(now_utc, league_id):
    written = []
    for row in load_capture_table():
        fn = SOURCE_FETCHERS.get(row["source"])
        if fn is None:
            continue                     # manual_export rows: see manual_ingest_doc
        written.append(capture(row["source"], fn(league_id),
                               row["known_at_rule"], row["privacy"], now_utc))
    return receipt(written)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--league-id", required=True)
    ap.add_argument("--now-utc", required=True)
    args = ap.parse_args()
    print(json.dumps(run_capture(args.now_utc, args.league_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Write the manual-ingest doc**

Create `docs/superpowers/plans/capture-manual-ingest.md` with one section per manual row
(`#projections`, `#injuries`, `#chat`) stating: where the export comes from, the exact
`capture(...)` invocation to ingest it, and the `known_at` justification. The chat section states
that the export is private-class and never leaves the local boundary.

- [ ] **Step 6: Run tests** → 4 passed; suite still ≥ 343/2

- [ ] **Step 7: Commit**

```bash
git add scripts/capture_2026.py content/governance/capture_table.json docs/superpowers/plans/capture-manual-ingest.md scripts/tests/test_capture_2026.py
git commit -m "feat(capture): working fetch path per source, offseason-capable transaction legs"
```

---

### Task P3: Produce the baseline capture and name the cadence

- [ ] **Step 1: Take the initial capture**

```bash
python scripts/capture_2026.py --league-id <2026_LEAGUE_ID> --now-utc <ISO8601Z>
```

Expected: a receipt listing five public sources with content hashes; files under
`data/captures/2026/<source>/`.

- [ ] **Step 2: Ingest any available manual rows** per `capture-manual-ingest.md`.

- [ ] **Step 3: Name the recurring trigger**

Add to `.github/workflows/` a preseason capture workflow with
`cron: '0 6 * 7,8 *'` (daily 06:00 UTC through July–August), invoking the same CLI. This
supplements — does not replace — the existing September-onward fetch, whose
`cron: '0 6 * 9-12 0'` is why nothing ran before September.

- [ ] **Step 4: Commit**

```bash
git add data/captures/2026/ .github/workflows/capture-preseason-2026.yml
git commit -m "data(capture): baseline 2026 capture + daily preseason cadence"
```

---

## Phase A — Install the writer-access boundary

### Task A1: Source-graph census (AST, not markers) — then STOP

**Files:** Create `scripts/source_graph.py`, `scripts/tests/test_source_graph.py`

**Interfaces:** Produces `read_edges() -> list[dict]` with `consumer`, `target`, `line`, `kind`;
`CONSUMERS` (the design's named consumer list); `BARRED_TARGETS`

- [ ] **Step 1: Write the failing test**

```python
from scripts.source_graph import read_edges, CONSUMERS, BARRED_TARGETS

def test_consumer_list_matches_design():
    assert CONSUMERS >= {"write-preseason", "write-week", "edit-week", "edit-preseason",
                         "local_draft", "pick-media", "resolve_media",
                         "render-week", "render-preseason", "verify_week_content"}

def test_edges_are_resolved_reads_not_marker_hits():
    for e in read_edges():
        assert e["kind"] in {"python_open", "python_constant_path", "command_declared_input"}
        assert e["target"], e

def test_known_barred_reads_are_detected():
    targets = {e["target"] for e in read_edges()}
    assert any("team-profiles.json" in t for t in targets)
    assert any("player_arcs" in t or "franchises" in t or "league_history" in t
               for t in targets)
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Source graph: which consumers read which artifacts, resolved not guessed."""
import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]

CONSUMERS = {
    "write-preseason", "write-week", "edit-week", "edit-preseason", "canon-check",
    "local_draft", "pick-media", "resolve_media", "render-week", "render-preseason",
    "verify_week_content", "batch_drafts",
}

BARRED_TARGETS = (
    "team-profiles.json", "preseason-2026", "voice-bible.md",
    "league_history.json", "player_arcs", "franchises",
    "media_picks.json", "media_cache.json", "content/chat/",
    "_data_expanded.json", "_chat_context.json",
)


def _py_read_edges(py: Path):
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    consts = {n.targets[0].id: ast.unparse(n.value)
              for n in ast.walk(tree)
              if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    edges = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if fn not in {"open", "load_json", "read_text", "read_bytes"}:
            continue
        arg = ast.unparse(node.args[0]) if node.args else ""
        resolved = consts.get(arg, arg)
        edges.append({"consumer": py.stem, "target": resolved,
                      "line": node.lineno,
                      "kind": "python_constant_path" if arg in consts else "python_open"})
    return edges


def _md_read_edges(md: Path):
    edges = []
    for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        for m in re.finditer(r"`([^`]+\.(?:json|md|html))`", line):
            edges.append({"consumer": md.stem, "target": m.group(1), "line": i,
                          "kind": "command_declared_input"})
    return edges


def read_edges():
    edges = []
    for py in sorted((ROOT / "scripts").glob("*.py")):
        if py.stem in CONSUMERS:
            edges += _py_read_edges(py)
    for md in sorted((ROOT / ".claude" / "commands").glob("*.md")):
        if md.stem in CONSUMERS:
            edges += _md_read_edges(md)
    return edges


def barred_edges():
    return [e for e in read_edges()
            if any(b in e["target"] for b in BARRED_TARGETS)]


def main():
    import json
    print(json.dumps({"all": read_edges(), "barred": barred_edges()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests** → 3 passed

- [ ] **Step 5: Produce the census**

```bash
python scripts/source_graph.py > docs/superpowers/plans/source-graph-census-2026-08-02.json
```

- [ ] **Step 6: STOP — Blake reviews the census before any file is mutated**

Present the barred-edge list with per-consumer rewiring proposals. **No file in A2-A4 is modified
until Blake approves this census.** The design requires no authoritative surface be deleted
before its replacement is identified; this gate is where that is checked.

- [ ] **Step 7: Commit the census only**

```bash
git add scripts/source_graph.py scripts/tests/test_source_graph.py docs/superpowers/plans/source-graph-census-2026-08-02.json
git commit -m "feat(census): AST source graph of consumer reads; awaiting review before rewiring"
```

---

### Task A2: Rewire every consumer to bundle-only inputs

**Files:** Modify `.claude/commands/{write-week,write-preseason,edit-week,edit-preseason,canon-check,pick-media,render-week,render-preseason}.md`; `scripts/local_draft.py`, `scripts/batch_drafts.py`, `scripts/resolve_media.py`, `scripts/verify_week_content.py`
Create `scripts/tests/test_writer_access_boundary.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.source_graph import barred_edges

ALLOWED_EXCEPTIONS = {
    ("verify_week_content", "content/chat/name-map.json"),   # static identity map
}

def test_no_consumer_reads_a_barred_target():
    offending = [e for e in barred_edges()
                 if (e["consumer"], e["target"]) not in ALLOWED_EXCEPTIONS]
    assert not offending, f"{len(offending)} barred reads remain: {offending[:5]}"
```

- [ ] **Step 2: Run to verify it fails** → many offending edges

- [ ] **Step 3: Rewire**

Each consumer's declared inputs become exactly:

1. `content/editions/<edition_id>/bundle.json`
2. approved prior editions under `content/editions/*/content.json` (continuity consumers only)
3. `content/voice-bible.md` — abstract grammar only
4. `content/editions/<edition_id>/ranking_record.json` (writer, editors)
5. `content/editions/<edition_id>/media_manifest.json` (resolver, renderers)

Delete from `write-preseason.md` the "use as inspiration" instruction (`:47-53`) and the
2026-prose "tone precedent" block (`:72-75`). Delete from `write-week.md` the whole-voice-bible +
team-profile-essay input list (`:7-25`) and replace with the five inputs above.

- [ ] **Step 4: Run tests** → boundary test passes; suite ≥ 343/2

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/ scripts/local_draft.py scripts/batch_drafts.py scripts/resolve_media.py scripts/verify_week_content.py scripts/tests/test_writer_access_boundary.py
git commit -m "refactor(boundary): every writing consumer reads bundles only; barred reads fail tests"
```

---

### Task A3: Voice-bible surgery

**Files:** Modify `content/voice-bible.md`; create `scripts/tests/test_voice_bible_clean.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
VB = Path("content/voice-bible.md")

def test_no_superseded_excerpts_remain():
    quotes = [l for l in VB.read_text(encoding="utf-8").splitlines()
              if l.lstrip().startswith(">") and len(l.strip()) > 30]
    assert not quotes, f"{len(quotes)} excerpts remain: {quotes[:3]}"

def test_abstract_grammar_retained():
    text = VB.read_text(encoding="utf-8")
    for m in ("Pattern 1", "Pattern 12", "Anti-Patterns", "Cold Open Essay"):
        assert m in text, m

def test_no_stale_handle_table():
    assert "@kharlo_w" not in VB.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify it fails** → all three

- [ ] **Step 3: Edit** — delete every `>` example under §1 (`:16-20`, `:38-46`, `:64-70`,
      `:100-106`, `:122-126`, `:148-152`) and all of §5. Replace §2's handle table with a pointer
      to the approved repertoire (built in C1). Keep §1 definitions, §3 templates, §4
      anti-patterns, Appendix. **No replacement exemplar is required for the first edition** —
      the grammar is operative without examples, per the design.

- [ ] **Step 4: Run tests** → 3 passed

- [ ] **Step 5: Commit**

```bash
git add content/voice-bible.md scripts/tests/test_voice_bible_clean.py
git commit -m "refactor(voice): strip superseded excerpts; grammar retained; repertoire pointer"
```

---

### Task A4: Make `analyze_chat.py` incapable of authoritative overwrite

**Files:** Modify `scripts/analyze_chat.py`, `scripts/build_chat_context.py`;
create `scripts/tests/test_producer_quarantine.py`

- [ ] **Step 1: Write the failing test**

```python
import ast, subprocess, sys
from pathlib import Path

def test_quarantined_run_exits_nonzero():
    r = subprocess.run([sys.executable, "scripts/analyze_chat.py"],
                       capture_output=True, text=True)
    assert r.returncode != 0, "bare main() would exit 0 -- needs sys.exit(main())"
    assert "quarantin" in (r.stdout + r.stderr).lower()

def test_override_cannot_write_canonical_paths():
    src = Path("scripts/analyze_chat.py").read_text(encoding="utf-8")
    assert "SCRATCH_ROOT" in src
    tree = ast.parse(src)
    consts = {n.targets[0].id for n in ast.walk(tree)
              if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    assert "OUTPUT_ROOT" not in consts or "SCRATCH_ROOT" in consts

def test_dormant_media_enrichment_removed():
    src = Path("scripts/build_chat_context.py").read_text(encoding="utf-8")
    assert "MEDIA_CATALOG_PATH" not in src
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == "score_message_relevancy":
            assert "media_catalog" not in [a.arg for a in n.args.args]
```

- [ ] **Step 2: Run to verify it fails** → exits 0; enrichment present

- [ ] **Step 3: Implement**

```python
SCRATCH_ROOT = Path(__file__).resolve().parents[1] / "tmp" / "analyze_chat_scratch"

QUARANTINE_MSG = (
    "analyze_chat.py is QUARANTINED: it message-ID-joins the pre-repair media catalog "
    "and could overwrite analytics filenames consumed by build_chat_context.py. "
    "Re-enable only after the catalog is rebound and this script enters the provenance "
    "contract (generate_chat_provenance.py CODE_FILES). "
    "Inspection only: --inspect-to-scratch (writes under tmp/analyze_chat_scratch, never "
    "content/chat)."
)


def main():
    if "--inspect-to-scratch" not in sys.argv:
        print(QUARANTINE_MSG, file=sys.stderr)
        return 1
    global OUTPUT_ROOT
    OUTPUT_ROOT = SCRATCH_ROOT          # all writes redirected; canonical paths unreachable
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    ...


if __name__ == "__main__":
    raise SystemExit(main())            # bare main() would exit 0 on return 1
```

In `build_chat_context.py`: delete the `MEDIA_CATALOG_PATH` assignment (`:38`), remove the
`media_catalog` parameter from `score_message_relevancy` (`:358`), delete the lookup (`:381-382`).

- [ ] **Step 4: Run tests, then re-verify provenance**

```bash
python -m pytest scripts/tests/test_producer_quarantine.py -v
python scripts/generate_chat_provenance.py --verify
```

`build_chat_context.py` is in `CODE_FILES`, so its hash changes. Rebuild the receipt the approved
way: `--rebuild-check` green, then `--write --receipt <path>`. Never hand-edit the manifest.

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_chat.py scripts/build_chat_context.py content/chat/provenance.json scripts/tests/test_producer_quarantine.py
git commit -m "fix(chat): analyze_chat scratch-only; sys.exit(main()); remove dead enrichment"
```

---

### Task A5: Strip prose from generated artifacts

**Files:** Modify `scripts/extract_week_data.py` (`team_profiles_summary`),
`scripts/generate_franchise_wings.py:294-301`; create `scripts/tests/test_no_prose_in_generated.py`

- [ ] **Step 1: Write the failing test**

```python
import glob, json

def test_week_packets_carry_no_prose():
    for fp in glob.glob("content/weeks/week*_data.json"):
        blob = json.dumps(json.load(open(fp, encoding="utf-8")))
        assert '"essay_snippet"' not in blob and '"roast"' not in blob, fp

def test_franchise_wings_carry_no_prose():
    for fp in glob.glob("data/franchises/*.json"):
        if fp.endswith("_index.json"):
            continue
        assert '"roast"' not in json.dumps(json.load(open(fp, encoding="utf-8"))), fp
```

- [ ] **Step 2: Run to verify it fails** → both

- [ ] **Step 3: Remove `essay_snippet` and `roast` from the `team_profiles_summary` builder;
      delete `"roast"` from `voice_bible_callbacks`.**

- [ ] **Step 4: Regenerate and test**

```bash
python scripts/extract_week_data.py --all --pretty
python scripts/generate_franchise_wings.py
python -m pytest scripts/tests/test_no_prose_in_generated.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_week_data.py scripts/generate_franchise_wings.py content/weeks/ data/franchises/ scripts/tests/test_no_prose_in_generated.py
git commit -m "fix(data): strip prose from generated packets and franchise wings"
```

---

## Phase B — Repair, compiler, and the mandatory audit

### Task B1: Cutoff-sliced H2H

**Files:** Create `scripts/as_of_records.py`, `scripts/tests/test_as_of_records.py`

**Interfaces:** Produces `slice_h2h(entry, season, week, inclusive) -> dict`

Verified `entry` shape: `{"games":[{"season","week","pts","opp_pts"}], "wins","losses","pf","pa"}`
oriented to the first owner id in the `oid1|oid2` key.

- [ ] **Step 1: Write the failing test**

```python
from scripts.as_of_records import slice_h2h

ENTRY = {"games": [
    {"season": 2022, "week": 9, "pts": 140.3, "opp_pts": 153.12},
    {"season": 2025, "week": 6, "pts": 109.1, "opp_pts": 150.46},
    {"season": 2025, "week": 12, "pts": 180.0, "opp_pts": 100.0}], "wins": 1, "losses": 2}

def test_recap_includes_own_week():
    r = slice_h2h(ENTRY, 2025, 6, inclusive=True)
    assert r["total_games"] == 2 and r["last_meeting"]["week"] == 6

def test_preview_excludes_own_week():
    r = slice_h2h(ENTRY, 2025, 6, inclusive=False)
    assert r["total_games"] == 1 and r["last_meeting"]["season"] == 2022

def test_wins_recomputed_not_copied():
    r = slice_h2h(ENTRY, 2025, 6, inclusive=True)
    assert r["team1_wins"] == 0 and r["team2_wins"] == 2

def test_empty_slice_null_last_meeting():
    r = slice_h2h(ENTRY, 2021, 1, inclusive=True)
    assert r["total_games"] == 0 and r["last_meeting"] is None
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Cutoff-correct league records and H2H."""
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]


def _in_window(g, season, week, inclusive):
    if g["season"] < season:
        return True
    if g["season"] > season:
        return False
    return g["week"] <= week if inclusive else g["week"] < week


def slice_h2h(entry, season, week, inclusive=True):
    games = [g for g in (entry.get("games") or [])
             if _in_window(g, season, week, inclusive)]
    wins = sum(1 for g in games if g["pts"] > g["opp_pts"])
    last = games[-1] if games else None
    return {"team1_wins": wins, "team2_wins": len(games) - wins,
            "total_games": len(games),
            "last_meeting": ({"season": last["season"], "week": last["week"],
                              "score": f"{last['pts']}-{last['opp_pts']}"}
                             if last else None)}
```

- [ ] **Step 4: Run to verify it passes** → 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/as_of_records.py scripts/tests/test_as_of_records.py
git commit -m "feat(asof): cutoff-sliced H2H with recomputed wins"
```

---

### Task B2: Records including undated aggregates, season-parameterized

Verified ground truth: `longest_losing_streak` = 8 through 2024, 9 through 2025 wk1, 10 through
2025 wk2. `longest_win_streak` = 11 at every cutoff (accidentally safe, still recomputed).

**Files:** Modify `scripts/as_of_records.py`, `scripts/tests/test_as_of_records.py`

**Interfaces:** Produces `load_all_games(seasons=None)`, `as_of_records(season, week, inclusive=True)`

- [ ] **Step 1: Write the failing test**

```python
from scripts.as_of_records import as_of_records

def test_losing_streak_recomputed_at_cutoff():
    assert as_of_records(2024, 99)["longest_losing_streak"]["count"] == 8
    assert as_of_records(2025, 1)["longest_losing_streak"]["count"] == 9
    assert as_of_records(2025, 2)["longest_losing_streak"]["count"] == 10

def test_win_streak_stable_but_still_recomputed():
    for s, w in [(2024, 99), (2025, 1), (2025, 17)]:
        assert as_of_records(s, w)["longest_win_streak"]["count"] == 11

def test_dated_records_never_postdate_cutoff():
    for k, v in as_of_records(2025, 1).items():
        if isinstance(v, dict) and v.get("season") is not None:
            assert (v["season"], v.get("week") or 0) <= (2025, 1), k

def test_all_seven_keys_present():
    assert set(as_of_records(2025, 5)) == {
        "highest_score", "lowest_winning_score", "biggest_blowout",
        "highest_combined", "lowest_combined", "longest_win_streak",
        "longest_losing_streak"}
```

- [ ] **Step 2: Run to verify it fails** → `ImportError`

- [ ] **Step 3: Implement** (mirrors `fetch_sleeper.py:741-775` and `:962-1002`; streaks skip
      playoff games, dated records do not)

```python
def load_all_games(seasons=None):
    games = []
    for fp in sorted(glob.glob(str(ROOT / "data" / "*" / "season_combined.json"))):
        year = os.path.basename(os.path.dirname(fp))
        if not year.isdigit() or (seasons and int(year) not in seasons):
            continue
        data = json.load(open(fp, encoding="utf-8"))
        r2o = {int(k): v.get("owner_id", "") for k, v in data.get("roster_map", {}).items()}
        nm = {int(k): (v.get("team_name") or v.get("username") or "?")
              for k, v in data.get("roster_map", {}).items()}
        for wd in data.get("weeks", []):
            for m in wd.get("matchups", []):
                w = m.get("winner")
                games.append({
                    "season": int(year), "week": wd["week"],
                    "is_playoff": wd.get("is_playoff", False),
                    "o1": r2o.get(m["team1"]["roster_id"], ""),
                    "o2": r2o.get(m["team2"]["roster_id"], ""),
                    "n1": nm.get(m["team1"]["roster_id"], "?"),
                    "n2": nm.get(m["team2"]["roster_id"], "?"),
                    "p1": m["team1"]["points"], "p2": m["team2"]["points"],
                    "winner_owner": r2o.get(w, "") if w else None})
    return games


def as_of_records(season, week, inclusive=True):
    games = [g for g in load_all_games() if _in_window(g, season, week, inclusive)]
    rec = dict.fromkeys(("highest_score", "lowest_winning_score", "biggest_blowout",
                         "highest_combined", "lowest_combined"))
    for g in games:
        for pts, opp, me, them in ((g["p1"], g["p2"], g["n1"], g["n2"]),
                                   (g["p2"], g["p1"], g["n2"], g["n1"])):
            cand = {"points": pts, "team": me, "opponent": them,
                    "season": g["season"], "week": g["week"]}
            if rec["highest_score"] is None or pts > rec["highest_score"]["points"]:
                rec["highest_score"] = cand
            if pts > opp and (rec["lowest_winning_score"] is None
                              or pts < rec["lowest_winning_score"]["points"]):
                rec["lowest_winning_score"] = cand
        margin = abs(g["p1"] - g["p2"])
        if rec["biggest_blowout"] is None or margin > rec["biggest_blowout"]["margin"]:
            hi, lo = (g["n1"], g["n2"]) if g["p1"] >= g["p2"] else (g["n2"], g["n1"])
            rec["biggest_blowout"] = {
                "margin": round(margin, 2), "winner": hi, "loser": lo,
                "score": f"{max(g['p1'], g['p2']):.1f}-{min(g['p1'], g['p2']):.1f}",
                "season": g["season"], "week": g["week"]}
        comb = {"points": round(g["p1"] + g["p2"], 2),
                "teams": f"{g['n1']} vs {g['n2']}",
                "score": f"{g['p1']:.1f}-{g['p2']:.1f}",
                "season": g["season"], "week": g["week"]}
        if rec["highest_combined"] is None or comb["points"] > rec["highest_combined"]["points"]:
            rec["highest_combined"] = comb
        if rec["lowest_combined"] is None or comb["points"] < rec["lowest_combined"]["points"]:
            rec["lowest_combined"] = comb

    st = {}
    for g in games:
        if g["is_playoff"]:
            continue
        for oid, nm2 in ((g["o1"], g["n1"]), (g["o2"], g["n2"])):
            if not oid:
                continue
            d = st.setdefault(oid, {"cw": 0, "cl": 0, "bw": 0, "bl": 0, "team": nm2})
            d["team"] = nm2
            if g["winner_owner"] == oid:
                d["cw"] += 1; d["cl"] = 0; d["bw"] = max(d["bw"], d["cw"])
            else:
                d["cl"] += 1; d["cw"] = 0; d["bl"] = max(d["bl"], d["cl"])
    for key, field in (("longest_win_streak", "bw"), ("longest_losing_streak", "bl")):
        if st:
            best = max(v[field] for v in st.values())
            oid = sorted(o for o, v in st.items() if v[field] == best)[0]
            rec[key] = {"count": best, "team": st[oid]["team"], "owner_id": oid}
        else:
            rec[key] = None
    return rec
```

- [ ] **Step 4: Run to verify it passes** → 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/as_of_records.py scripts/tests/test_as_of_records.py
git commit -m "feat(asof): recompute all seven records at cutoff incl. undated streaks"
```

---

### Task B3: Wire the repair; census 46 → 0

**Files:** Modify `scripts/extract_week_data.py:562-577` and `:1028`;
create `scripts/tests/test_packet_cutoff_clean.py`

- [ ] **Step 1: Write the failing test**

```python
import glob, json, re
from scripts.as_of_records import as_of_records

def _wk(p): return int(re.search(r"week(\d+)_", p).group(1))

def test_no_future_dated_entries():
    future = 0
    for fp in sorted(glob.glob("content/weeks/week*_data.json"), key=_wk):
        wk = _wk(fp); d = json.load(open(fp, encoding="utf-8"))
        for m in d.get("matchups", []):
            lm = (m.get("h2h") or {}).get("last_meeting") or {}
            s, w = lm.get("season"), lm.get("week")
            if s is not None and (s > 2025 or (s == 2025 and w and w > wk)):
                future += 1
        for _, rec in (d.get("historical_context") or {}).items():
            if not isinstance(rec, dict):
                continue
            s, w = rec.get("season"), rec.get("week")
            if s is not None and (s > 2025 or (s == 2025 and w and w > wk)):
                future += 1
    assert future == 0, f"{future} future entries remain (baseline 45 dated)"

def test_undated_aggregates_cutoff_correct():
    for fp in sorted(glob.glob("content/weeks/week*_data.json"), key=_wk):
        wk = _wk(fp)
        hc = json.load(open(fp, encoding="utf-8"))["historical_context"]
        exp = as_of_records(2025, wk)
        assert hc["longest_losing_streak"]["count"] == exp["longest_losing_streak"]["count"], fp
        assert hc["longest_win_streak"]["count"] == exp["longest_win_streak"]["count"], fp
```

- [ ] **Step 2: Run to verify it fails** → 45 dated + week-1 streak 10 ≠ 9

- [ ] **Step 3: Wire**

```python
        if h2h_entry:
            from as_of_records import slice_h2h
            entry["h2h"] = slice_h2h(h2h_entry, season, week_num, inclusive=True)
```

```python
        from as_of_records import as_of_records
        result["historical_context"] = as_of_records(season, week_num, inclusive=True)
```

- [ ] **Step 4: Re-extract packets AND companions in the same pass**

```bash
python scripts/extract_week_data.py --all --pretty
python scripts/generate_expanded_week.py            # bare run covers weeks 1-18
python -m pytest scripts/tests/test_packet_cutoff_clean.py -v
python -m pytest scripts/tests/ -q
```

`generate_expanded_week.py` accepts only `--week` (default: all 1-18) and `--season`. Passing
`--all` exits nonzero on an unrecognized argument.

Regenerating companions in the same pass is mandatory — `c5b6b50` regenerated week data alone and
left 32 season-end Elo values leaking in the companions.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_week_data.py content/weeks/ data/2025/nfl_games/_expanded_manifest.json scripts/tests/test_packet_cutoff_clean.py
git commit -m "fix(data): cutoff-slice h2h, recompute records -- 46 confirmed leaks to zero"
```

---

### Task B4: `verify_h2h_claims` becomes an error

The comparison is reachable only when the **ranking entry** carries `team_name`
(`verify_week_content.py:917`, guarded at `:927` and `:946`). The prior plan's test omitted it and
never reached the branch.

**Files:** Modify `scripts/verify_week_content.py:892-949`, `scripts/tests/test_verify_week_content.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.verify_week_content import verify_h2h_claims

def test_wrong_h2h_claim_is_error():
    content = {"rankings": [{"rank": 1, "team_name": "Alpha",
                             "blurb": "You are 9-0 all-time against them."}]}
    data = {"matchups": [{"team1": {"team_name": "Alpha"}, "team2": {"team_name": "Beta"},
                          "h2h": {"team1_wins": 1, "team2_wins": 1, "total_games": 2}}]}
    errors, warnings = [], []
    verify_h2h_claims(content, data, errors, warnings)
    assert errors, "unverifiable H2H claim must be an error"

def test_correct_claim_produces_no_error():
    content = {"rankings": [{"rank": 1, "team_name": "Alpha",
                             "blurb": "You are 1-1 all-time against them."}]}
    data = {"matchups": [{"team1": {"team_name": "Alpha"}, "team2": {"team_name": "Beta"},
                          "h2h": {"team1_wins": 1, "team2_wins": 1, "total_games": 2}}]}
    errors, warnings = [], []
    verify_h2h_claims(content, data, errors, warnings)
    assert not errors
```

- [ ] **Step 2: Run to verify it fails** → claim lands in `warnings`

- [ ] **Step 3: Change `warnings.append(...)` to `errors.append(...)` at `:946-950`.**

- [ ] **Step 4: Run suite.** Weeks 1-6 may now fail on H2H claims. **Expected — those editions are
      filler being replaced. Do not repair their prose.**

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_week_content.py scripts/tests/test_verify_week_content.py
git commit -m "fix(verify): H2H mismatches are errors; test reaches the branch via team_name"
```

---

### Task B5: Leaf classification with forbidden detection and a CLI

**Files:** Create `scripts/cutoff_audit.py`, `content/governance/writer_fields.json`,
`scripts/tests/test_cutoff_audit.py`

**Interfaces:** Produces `leaf_pointers`, `classify`, `audit_object(reg, kind, obj) -> dict` with
`unclassified` and `forbidden_present`; `main()` CLI

- [ ] **Step 1: Write the failing test**

```python
import glob, json
from scripts.cutoff_audit import audit_object, classify, load_registry

REG = load_registry()

def test_unknown_field_fails_closed():
    r = audit_object(REG, "week_packet", {"essay": "x", "surprise": {"z": 1}})
    assert not r["ok"] and any("/surprise/z" in u for u in r["unclassified"])

def test_present_forbidden_leaf_fails():
    reg = {"week_packet": {"forbidden": ["/secret/*"], "static-legal": ["/a"]}}
    r = audit_object(reg, "week_packet", {"a": 1, "secret": {"x": 2}})
    assert not r["ok"] and r["forbidden_present"], "forbidden must fail, not merely classify"

def test_every_week_packet_leaf_classified():
    for fp in glob.glob("content/weeks/week*_data.json"):
        r = audit_object(REG, "week_packet", json.load(open(fp, encoding="utf-8")))
        assert r["ok"], f"{fp}: {r['unclassified'][:5]} {r['forbidden_present'][:5]}"

def test_undated_aggregate_not_static_legal():
    assert classify(REG, "week_packet",
                    "/historical_context/longest_losing_streak/count") == "cutoff-filtered"

def test_equal_specificity_conflict_fails_closed():
    bad = {"week_packet": {"static-legal": ["/x/*"], "cutoff-filtered": ["/x/*"]}}
    assert not audit_object(bad, "week_packet", {"x": {"y": 1}})["ok"]
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** (registry as in the prior revision, plus:)

```python
def audit_object(reg, kind, obj):
    unclassified, forbidden = [], []
    for ptr in sorted(set(leaf_pointers(obj))):
        try:
            cls = classify(reg, kind, ptr)
        except ValueError as exc:
            unclassified.append(str(exc))
            continue
        if cls is None:
            unclassified.append(ptr)
        elif cls == "forbidden":
            forbidden.append(ptr)
    return {"ok": not unclassified and not forbidden,
            "unclassified": unclassified, "forbidden_present": forbidden}


def main():
    import argparse, glob as _g, json as _j
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--path")
    ap.add_argument("--kind", default="week_packet")
    args = ap.parse_args()
    reg = load_registry()
    targets = ([("week_packet", p) for p in sorted(_g.glob("content/weeks/week*_data.json"))]
               + [("edition_bundle", p) for p in sorted(_g.glob("content/editions/*/bundle.json"))]
               ) if args.all else [(args.kind, args.path)]
    failed = 0
    for kind, p in targets:
        r = audit_object(reg, kind, _j.load(open(p, encoding="utf-8")))
        if not r["ok"]:
            failed += 1
            print(f"FAIL {p}: unclassified={r['unclassified'][:5]} "
                  f"forbidden={r['forbidden_present'][:5]}")
    print("OK" if not failed else f"{failed} file(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes** → 5 passed; `python scripts/cutoff_audit.py --all`
      exits 0

- [ ] **Step 5: Commit**

```bash
git add scripts/cutoff_audit.py content/governance/writer_fields.json scripts/tests/test_cutoff_audit.py
git commit -m "feat(audit): leaf classification with forbidden detection and a working CLI"
```

---

### Task B6: Positive controls that exercise the production audit

The prior revision's controls called a test-local detector and asserted `correct + 1 != correct`.
These call the shipped audit.

**Files:** Create `scripts/tests/test_audit_positive_controls.py`

- [ ] **Step 1: Write the test**

```python
import copy, json, subprocess, sys
from scripts.cutoff_audit import audit_object, load_registry
from scripts.as_of_records import as_of_records

REG = load_registry()

def _packet():
    return json.load(open("content/weeks/week1_data.json", encoding="utf-8"))

def test_production_audit_flags_unknown_field():
    d = copy.deepcopy(_packet()); d["brand_new_block"] = {"leak": 1}
    r = audit_object(REG, "week_packet", d)
    assert not r["ok"] and any("brand_new_block" in u for u in r["unclassified"])

def test_production_audit_flags_forbidden_leaf():
    reg = copy.deepcopy(REG)
    reg["week_packet"].setdefault("forbidden", []).append("/historical_context/highest_combined/season")
    r = audit_object(reg, "week_packet", _packet())
    assert not r["ok"] and r["forbidden_present"]

def test_production_recompute_detects_planted_dated_leak():
    """The shipped recomputation, not a test-local detector, disagrees with a planted value."""
    d = copy.deepcopy(_packet())
    d["historical_context"]["highest_combined"] = {"points": 999.0, "teams": "X vs Y",
                                                   "score": "1-2", "season": 2025, "week": 14}
    expected = as_of_records(2025, 1)["highest_combined"]
    assert d["historical_context"]["highest_combined"] != expected

def test_production_recompute_detects_planted_undated_leak():
    d = copy.deepcopy(_packet())
    d["historical_context"]["longest_losing_streak"]["count"] = 10   # season-end value
    assert d["historical_context"]["longest_losing_streak"]["count"] != \
        as_of_records(2025, 1)["longest_losing_streak"]["count"]

def test_audit_cli_exits_nonzero_on_failure(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"unknown_root": {"x": 1}}), encoding="utf-8")
    r = subprocess.run([sys.executable, "scripts/cutoff_audit.py", "--path", str(bad)],
                       capture_output=True, text=True)
    assert r.returncode == 1, "CLI must exit nonzero when the audit fails"
```

- [ ] **Step 2: Run** → 5 passed

- [ ] **Step 3: Commit**

```bash
git add scripts/tests/test_audit_positive_controls.py
git commit -m "test(audit): controls exercise the shipped audit and its CLI exit code"
```

---

### Task B7: Edition identity

**Files:** Create `scripts/edition.py`, `scripts/tests/test_edition.py`

**Interfaces:** Produces `EditionDescriptor`, `payload_hash`, `bundle_manifest`,
`authoring_manifest`, `build_identity`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.edition import (EditionDescriptor, bundle_manifest, authoring_manifest,
                             payload_hash, build_identity)

D = EditionDescriptor("2025-wk01-recap", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1")

def test_hash_order_invariant():
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})

def test_bundle_manifest_not_self_referential():
    bm = bundle_manifest(D, {"src": "sha256:aa"}, "code-v1", {"x": 1})
    assert bm["bundle_payload_sha256"] == payload_hash({"x": 1})
    assert "bundle_manifest_sha256" not in bm

def test_authoring_manifest_has_no_media():
    bm = bundle_manifest(D, {}, "code-v1", {})
    am = authoring_manifest(bm, [], {"writer": "v1"}, {"essay": "e"}, {"rankings": [1]})
    assert "media_manifest_sha256" not in am

def test_authoring_manifest_binds_ranking():
    bm = bundle_manifest(D, {}, "code-v1", {})
    am = authoring_manifest(bm, [], {"writer": "v1"}, {"essay": "e"}, {"rankings": [1]})
    assert am["ranking_record_sha256"] == payload_hash({"rankings": [1]})

def test_build_identity_excludes_final_hashes():
    bi = build_identity(D, "code-v1")
    assert bi["edition_id"] == "2025-wk01-recap" and "sha256" not in json.dumps(bi)
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Edition identity: descriptor, build identity, bundle and authoring manifests."""
import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EditionDescriptor:
    edition_id: str
    season: int
    kind: str                 # preseason | preview | recap | finale
    cutoff_utc: str
    results_through_week: int
    policy_version: str


def payload_hash(obj) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def build_identity(descriptor, projection_code_version):
    """Carried BY components. Never the enclosing bundle's final hash."""
    return {"edition_id": descriptor.edition_id,
            "cutoff_utc": descriptor.cutoff_utc,
            "projection_code_version": projection_code_version}


def bundle_manifest(descriptor, source_hashes, projection_code_version, payload):
    return {"descriptor": asdict(descriptor),
            "source_hashes": dict(sorted(source_hashes.items())),
            "projection_code_version": projection_code_version,
            "bundle_payload_sha256": payload_hash(payload)}


def authoring_manifest(bundle_mf, predecessor_hashes, rule_versions, content, ranking_record):
    return {"bundle_manifest_sha256": payload_hash(bundle_mf),
            "predecessor_hashes": sorted(predecessor_hashes),
            "rule_versions": dict(sorted(rule_versions.items())),
            "content_sha256": payload_hash(content),
            "ranking_record_sha256": payload_hash(ranking_record)}
```

- [ ] **Step 4: Run to verify it passes** → 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/edition.py scripts/tests/test_edition.py
git commit -m "feat(edition): descriptor, build identity, non-circular manifests"
```

---

### Task B8: Qualify the kickoff instant from a hashed source

`data/2025/nfl_games/*.json` carries `kickoff` as **time-of-day only** (`"13:00"`) with no date,
so it cannot qualify a cutoff alone. The date lives in `data/external/schedules_2025.parquet`
(gitignored, refreshed by `fetch_nflreadpy.py`).

**Files:** Create `scripts/kickoff_source.py`, `scripts/tests/test_kickoff_source.py`

**Interfaces:** Produces `first_kickoff_instant(season) -> tuple[str, str]` returning
`(instant_iso_z, source_sha256)`; raises `UnavailableEvidence` when unqualified

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.kickoff_source import first_kickoff_instant, UnavailableEvidence

def test_returns_instant_and_source_hash():
    inst, sha = first_kickoff_instant(2025)
    assert inst.endswith("Z") and sha.startswith("sha256:")

def test_missing_source_fails_closed(monkeypatch):
    monkeypatch.setattr("scripts.kickoff_source.SCHEDULE_PATH",
                        __import__("pathlib").Path("does/not/exist.parquet"))
    with pytest.raises(UnavailableEvidence):
        first_kickoff_instant(2025)
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Qualify the first-kickoff instant from an authoritative, hashed source."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_PATH = ROOT / "data" / "external" / "schedules_2025.parquet"


class UnavailableEvidence(RuntimeError):
    """Raised when a cutoff cannot be qualified. Never guess a cutoff."""


def first_kickoff_instant(season):
    if not SCHEDULE_PATH.exists():
        raise UnavailableEvidence(
            f"{SCHEDULE_PATH} absent -- run `python scripts/fetch_nflreadpy.py` first. "
            "A preview cutoff may not be hard-coded or inferred."
        )
    import polars as pl
    df = pl.read_parquet(SCHEDULE_PATH).filter(
        (pl.col("season") == season) & (pl.col("week") == 1))
    stamps = [f"{d}T{t}:00Z" for d, t in
              zip(df["gameday"].to_list(), df["gametime"].to_list()) if d and t]
    if not stamps:
        raise UnavailableEvidence(f"no qualified week-1 kickoff for {season}")
    sha = "sha256:" + hashlib.sha256(SCHEDULE_PATH.read_bytes()).hexdigest()
    return min(stamps), sha


def strictly_before(instant_iso_z, seconds=1):
    from datetime import datetime, timedelta, timezone
    dt = datetime.fromisoformat(instant_iso_z.replace("Z", "+00:00"))
    return (dt - timedelta(seconds=seconds)).astimezone(
        timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 4: Run** → 2 passed (first test skips gracefully if the parquet is absent — refresh
      with `python scripts/fetch_nflreadpy.py` before D1b)

- [ ] **Step 5: Commit**

```bash
git add scripts/kickoff_source.py scripts/tests/test_kickoff_source.py
git commit -m "feat(cutoff): qualify first-kickoff from hashed schedule source; fail closed"
```

---

### Task B9: The D1 evidence matrix — exactly the adapters the three editions need

| Adapter               | preseason | preview | recap | Source                                      |
| --------------------- | --------- | ------- | ----- | ------------------------------------------- |
| `records`             | ✓         | ✓       | ✓     | `as_of_records`                             |
| `h2h`                 | ✓         | ✓       | ✓     | `league_history.h2h` sliced                 |
| `rosters`             | ✓         | ✓       | ✓     | reconstructed from transactions             |
| `draft`               | ✓         | ✓       | ✓     | `data/{season}/draft_picks.json`            |
| `pairings`            | —         | ✓       | ✓     | matchups with outcomes stripped for preview |
| `chat`                | ✓         | ✓       | ✓     | cutoff-projected chat context               |
| `prior_editions`      | —         | ✓       | ✓     | approved rankings/predictions/threads       |
| `results`             | —         | —       | ✓     | week-N matchups, scores, standings          |
| `player_game_context` | —         | —       | ✓     | `weekN_data_expanded.games`                 |

**Files:** Create `scripts/project_edition.py`, `scripts/tests/test_project_edition.py`

**Interfaces:** Produces `project(descriptor) -> dict`, `reconstruct_roster(season, cutoff_utc)`,
`adapter_for(name)`, `REQUIRED_BY_KIND`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.edition import EditionDescriptor
from scripts.project_edition import (project, reconstruct_roster, adapter_for,
                                     REQUIRED_BY_KIND)

PREVIEW = EditionDescriptor("2025-wk01-preview", 2025, "preview",
                            "2025-09-04T23:19:59Z", 0, "v1")
RECAP = EditionDescriptor("2025-wk01-recap", 2025, "recap",
                          "2025-09-09T06:59:59Z", 1, "v1")

def test_every_required_source_present_or_unavailable():
    for d in (PREVIEW, RECAP):
        b = project(d)
        for name in REQUIRED_BY_KIND[d.kind]:
            assert name in b, f"{d.kind} missing {name}"
            assert b[name] is not None or name in b.get("unavailable", []), name

def test_preview_has_no_week1_outcomes():
    b = project(PREVIEW)
    for p in b["pairings"]:
        assert "points" not in p and "winner" not in p
    assert all(s["record"] == "0-0" for s in b["standings"])

def test_preview_roster_excludes_post_kickoff_add():
    r = reconstruct_roster(2025, "2025-09-04T23:19:59Z")
    assert "6949" not in [str(p) for p in r.get("6", {}).get("players", [])]

def test_recap_has_results_preview_does_not():
    assert project(RECAP)["results"] is not None
    assert "results" not in REQUIRED_BY_KIND["preview"]

def test_unregistered_adapter_fails_closed():
    with pytest.raises(KeyError):
        adapter_for("speculative_d2_source")

def test_missing_effective_instant_is_unavailable_not_created_fallback():
    from scripts.project_edition import effective_instant, UnavailableEvidence
    with pytest.raises(UnavailableEvidence):
        effective_instant({"created": 1725000000000})   # no status_updated
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** (season-parameterized; no hard-coded `data/2025`)

```python
"""The projector: sole trusted reader of raw and full-season stores."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from as_of_records import as_of_records, slice_h2h  # noqa: E402
from kickoff_source import UnavailableEvidence  # noqa: E402
from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_BY_KIND = {
    "preseason": ["records", "h2h", "rosters", "draft", "chat"],
    "preview": ["records", "h2h", "rosters", "draft", "pairings", "chat",
                "prior_editions", "standings"],
    "recap": ["records", "h2h", "rosters", "draft", "pairings", "chat",
              "prior_editions", "standings", "results", "player_game_context"],
}

ADAPTERS = {}


def adapter(name):
    def wrap(fn):
        ADAPTERS[name] = fn
        return fn
    return wrap


def adapter_for(name):
    if name not in ADAPTERS:
        raise KeyError(f"no adapter registered for '{name}' -- fails closed")
    return ADAPTERS[name]


def season_dir(season):
    return ROOT / "data" / str(season)


def effective_instant(txn):
    ms = txn.get("status_updated")
    if ms is None:
        raise UnavailableEvidence(
            f"transaction {txn.get('transaction_id')} has no status_updated; "
            "`created` is NOT an acceptable fallback for an effective instant"
        )
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def reconstruct_roster(season, cutoff_utc):
    cutoff = datetime.fromisoformat(cutoff_utc.replace("Z", "+00:00"))
    base = load_json(season_dir(season) / "rosters.json", required=True)
    rosters = {str(r["roster_id"]): {"players": list(r.get("players") or [])} for r in base}
    txns = load_json(season_dir(season) / "transactions.json", required=True)
    events = []
    for leg in sorted(txns, key=lambda k: int(k)):
        for t in txns[leg]:
            if t.get("status") != "complete":
                continue
            events.append((effective_instant(t), t))
    for when, t in sorted(events, key=lambda e: e[0], reverse=True):
        if when <= cutoff:
            break
        for pid, rid in (t.get("adds") or {}).items():
            plist = rosters.get(str(rid), {}).get("players", [])
            if pid in plist:
                plist.remove(pid)
        for pid, rid in (t.get("drops") or {}).items():
            rosters.setdefault(str(rid), {"players": []})["players"].append(pid)
    return rosters


@adapter("records")
def _records(d):
    return as_of_records(d.season, d.results_through_week, inclusive=(d.kind != "preview"))


@adapter("h2h")
def _h2h(d):
    hist = load_json(ROOT / "data" / "league_history.json", required=True)
    return {k: slice_h2h(v, d.season, d.results_through_week,
                         inclusive=(d.kind != "preview"))
            for k, v in (hist.get("h2h") or {}).items()}


@adapter("rosters")
def _rosters(d):
    return reconstruct_roster(d.season, d.cutoff_utc)


@adapter("draft")
def _draft(d):
    return load_json(season_dir(d.season) / "draft_picks.json", required=True)


@adapter("pairings")
def _pairings(d):
    wk = max(d.results_through_week, 1)
    packet = load_json(ROOT / "content" / "weeks" / f"week{wk}_data.json", required=True)
    out = []
    for m in packet.get("matchups", []):
        pair = {"team1": m["team1"]["team_name"], "team2": m["team2"]["team_name"]}
        if d.kind != "preview":
            pair.update({"points1": m["team1"]["points"], "points2": m["team2"]["points"],
                         "winner": m.get("winner")})
        out.append(pair)
    return out


@adapter("standings")
def _standings(d):
    if d.kind == "preview":
        users = load_json(season_dir(d.season) / "users.json", required=True)
        return [{"team_name": (u.get("metadata") or {}).get("team_name") or u["display_name"],
                 "record": "0-0"} for u in users]
    wk = d.results_through_week
    return load_json(ROOT / "content" / "weeks" / f"week{wk}_data.json",
                     required=True)["standings"]


@adapter("results")
def _results(d):
    wk = d.results_through_week
    p = load_json(ROOT / "content" / "weeks" / f"week{wk}_data.json", required=True)
    return {"matchups": p["matchups"], "awards": p.get("awards")}


@adapter("player_game_context")
def _pgc(d):
    wk = d.results_through_week
    exp = load_json(ROOT / "content" / "weeks" / f"week{wk}_data_expanded.json",
                    required=True)
    return exp.get("games", {})


@adapter("chat")
def _chat(d):
    wk = d.results_through_week
    path = (ROOT / "content" / "preseason-2025" / "preseason_chat_context.json"
            if d.kind == "preseason"
            else ROOT / "content" / "weeks" / f"week{max(wk, 1)}_chat_context.json")
    return load_json(path, required=True)


@adapter("prior_editions")
def _prior(d):
    out = []
    for ed in sorted((ROOT / "content" / "editions").glob("*")):
        pub = ed / "publication.json"
        if not pub.exists():
            continue
        out.append({"edition_id": ed.name,
                    "ranking_record": load_json(ed / "ranking_record.json", required=True),
                    "content": load_json(ed / "content.json", required=True)})
    return out


def project(descriptor):
    payload, unavailable = {}, []
    for name in REQUIRED_BY_KIND[descriptor.kind]:
        try:
            payload[name] = adapter_for(name)(descriptor)
        except (UnavailableEvidence, FileNotFoundError) as exc:
            payload[name] = None
            unavailable.append({"source": name, "reason": str(exc)})
    payload["unavailable"] = unavailable
    return payload
```

- [ ] **Step 4: Run to verify it passes** → 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/project_edition.py scripts/tests/test_project_edition.py
git commit -m "feat(projector): D1 evidence matrix, season-parameterized, qualified instants only"
```

---

### Task B10: Desk evidence coverage test

**Files:** Create `content/governance/desk_contracts.json`, `scripts/tests/test_desk_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.edition import EditionDescriptor
from scripts.project_edition import project

CONTRACTS = json.load(open("content/governance/desk_contracts.json", encoding="utf-8"))

def test_every_desk_gets_its_contracted_evidence_or_unavailable():
    d = EditionDescriptor("2025-wk01-recap", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1")
    bundle = project(d)
    unavailable = {u["source"] for u in bundle.get("unavailable", [])}
    for desk, needs in CONTRACTS["recap"].items():
        for n in needs:
            assert n in bundle, f"{desk} needs {n}, absent from bundle"
            assert bundle[n] is not None or n in unavailable, \
                f"{desk}: {n} is silently None without an unavailable record"
```

- [ ] **Step 2: Run to verify it fails** → file missing

- [ ] **Step 3: Write the contracts**

```json
{
  "recap": {
    "power-rankings": ["records", "standings", "results", "prior_editions"],
    "game": ["player_game_context", "results"],
    "history": ["h2h", "records"],
    "culture": ["chat"],
    "continuity": ["prior_editions", "pairings"],
    "copy-editor": ["results", "standings", "records", "h2h"]
  },
  "preview": {
    "power-rankings": ["records", "standings", "prior_editions"],
    "game": ["rosters", "draft"],
    "history": ["h2h", "records"],
    "culture": ["chat"],
    "continuity": ["prior_editions", "pairings"],
    "copy-editor": ["rosters", "records", "h2h"]
  },
  "preseason": {
    "power-rankings": ["records", "rosters", "draft"],
    "game": ["rosters", "draft"],
    "history": ["h2h", "records"],
    "culture": ["chat"],
    "continuity": [],
    "copy-editor": ["rosters", "draft", "records"]
  }
}
```

- [ ] **Step 4: Run** → passes

- [ ] **Step 5: Commit**

```bash
git add content/governance/desk_contracts.json scripts/tests/test_desk_coverage.py
git commit -m "test(desks): every desk receives contracted evidence or an unavailable record"
```

---

### Task B11: One compiler command — atomic canonical persist

**Files:** Create `scripts/compile_edition.py`, `scripts/tests/test_compile_edition.py`

**Interfaces:** Produces `compile_edition(descriptor) -> Path`; writes `descriptor.json`,
`bundle.json`, `bundle_manifest.json`, `build_identity.json`, `source_hashes.json`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path
from scripts.edition import EditionDescriptor, payload_hash
from scripts.compile_edition import compile_edition

D = EditionDescriptor("test-ed", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1")

def test_writes_all_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    out = compile_edition(D)
    for f in ("descriptor.json", "bundle.json", "bundle_manifest.json",
              "build_identity.json", "source_hashes.json"):
        assert (out / f).exists(), f

def test_manifest_hash_matches_persisted_payload(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    out = compile_edition(D)
    bundle = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    mf = json.loads((out / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert mf["bundle_payload_sha256"] == payload_hash(bundle)

def test_clean_rebuild_is_byte_identical(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    first = (compile_edition(D) / "bundle.json").read_bytes()
    import shutil; shutil.rmtree(tmp_path / D.edition_id)
    second = (compile_edition(D) / "bundle.json").read_bytes()
    assert first == second

def test_partial_failure_leaves_no_edition_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    bad = EditionDescriptor("bad-ed", 2025, "no_such_kind", "2025-01-01T00:00:00Z", 1, "v1")
    try:
        compile_edition(bad)
    except Exception:
        pass
    assert not (tmp_path / "bad-ed").exists(), "atomic: no partial edition dir"
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Compile one edition: atomic, canonical, fully manifested."""
import hashlib
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edition import bundle_manifest, build_identity  # noqa: E402
from project_edition import REQUIRED_BY_KIND, project  # noqa: E402
from shared import save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EDITIONS_ROOT = ROOT / "content" / "editions"
CODE_VERSION = "projector-v1"

HASHED_SOURCES = [
    ROOT / "data" / "league_history.json",
    ROOT / "scripts" / "project_edition.py",
    ROOT / "scripts" / "as_of_records.py",
]


def _file_sha(p: Path):
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def compile_edition(descriptor):
    if descriptor.kind not in REQUIRED_BY_KIND:
        raise ValueError(f"unknown edition kind: {descriptor.kind}")
    final = EDITIONS_ROOT / descriptor.edition_id
    staging = EDITIONS_ROOT / f".{descriptor.edition_id}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        payload = project(descriptor)
        sources = {str(p.relative_to(ROOT)): _file_sha(p) for p in HASHED_SOURCES}
        mf = bundle_manifest(descriptor, sources, CODE_VERSION, payload)
        save_json_canonical(staging / "descriptor.json", asdict(descriptor))
        save_json_canonical(staging / "bundle.json", payload)
        save_json_canonical(staging / "bundle_manifest.json", mf)
        save_json_canonical(staging / "build_identity.json",
                            build_identity(descriptor, CODE_VERSION))
        save_json_canonical(staging / "source_hashes.json", sources)
        if final.exists():
            shutil.rmtree(final)
        staging.rename(final)
        return final
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main():
    import argparse, json as _j
    from edition import EditionDescriptor
    ap = argparse.ArgumentParser()
    ap.add_argument("--descriptor", required=True)
    args = ap.parse_args()
    d = EditionDescriptor(**_j.load(open(args.descriptor, encoding="utf-8")))
    print(compile_edition(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes** → 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/compile_edition.py scripts/tests/test_compile_edition.py
git commit -m "feat(compile): atomic canonical edition compile with full manifest set"
```

---

### Task B12: Noninterference and the non-2025 canary — required BEFORE D1

The prior revision deferred both to D2. That contradicts approved Phase-B acceptance and would
certify a 2025-shaped system as reusable without testing reuse.

**Files:** Create `scripts/tests/test_noninterference.py`

- [ ] **Step 1: Write the test**

```python
import json, shutil
from pathlib import Path
from scripts.edition import EditionDescriptor
from scripts.compile_edition import compile_edition

REC = EditionDescriptor("ni-recap", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1")

def _bundle_bytes(d, tmp, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp)
    return (compile_edition(d) / "bundle.json").read_bytes()

def test_full_input_vs_truncated_is_byte_identical(tmp_path, monkeypatch):
    """Truncating inputs to the cutoff must not change the bundle."""
    full = _bundle_bytes(REC, tmp_path / "a", monkeypatch)
    truncated = _bundle_bytes(REC, tmp_path / "b", monkeypatch)
    assert full == truncated

def test_positive_control_detects_inequality(tmp_path, monkeypatch):
    """Prove the comparison can fail: a later cutoff must yield a different bundle."""
    a = _bundle_bytes(REC, tmp_path / "c", monkeypatch)
    later = EditionDescriptor("ni-recap", 2025, "recap", "2025-09-16T06:59:59Z", 2, "v1")
    b = _bundle_bytes(later, tmp_path / "d", monkeypatch)
    assert a != b, "detector is inert -- it cannot distinguish cutoffs"

def test_non_2025_canary_compiles(tmp_path, monkeypatch):
    """The same season-parameterized path must serve a non-2025 season."""
    canary = EditionDescriptor("canary-2024-wk01", 2024, "recap",
                               "2024-09-10T06:59:59Z", 1, "v1")
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    out = compile_edition(canary)
    bundle = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["records"] is not None
    assert "2025" not in json.dumps(bundle.get("unavailable", [])), \
        "canary failed on a hard-coded 2025 path"

def test_clean_rebuild_reproduces_every_d1_bundle(tmp_path, monkeypatch):
    for d in (REC,):
        monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path / d.edition_id)
        one = (compile_edition(d) / "bundle.json").read_bytes()
        shutil.rmtree(tmp_path / d.edition_id)
        two = (compile_edition(d) / "bundle.json").read_bytes()
        assert one == two
```

- [ ] **Step 2: Run.** Expected: all pass. If the canary fails, a hard-coded `data/2025` path
      remains in B9 — fix it before proceeding. **This is the point of the canary.**

- [ ] **Step 3: Commit**

```bash
git add scripts/tests/test_noninterference.py
git commit -m "test(audit): noninterference with positive control, clean rebuild, 2024 canary"
```

---

### Task B13: Rebind the media catalog uniquely and persist it

Verified: 1205/1205 `message_id` differ, 1202 timestamps differ, 742 senders differ, 255
uncatalogued, **0 of 1205** `message_id` joins correct. `chat/parsed_messages.json` is a dict with
`messages`/`metadata` — the prior revision passed the container.

**Files:** Create `scripts/rebind_media_catalog.py`, `scripts/tests/test_rebind_media_catalog.py`;
output `content/chat/media-catalog-rebound.json`

**Interfaces:** Produces `rebind(catalog, messages, asset_root) -> dict`; `main()` CLI

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.rebind_media_catalog import rebind, AmbiguousBinding

CAT = [{"filename": "a.mp4", "message_id": 20, "timestamp_utc": "2023-09-08T00:44:23Z",
        "sender": "WRONG", "description": "keep me", "tags": ["personal"]}]
MSGS = [{"id": 999, "timestamp_utc": "2024-01-02T03:04:05Z", "sender": "Right",
         "media": ["a.mp4"]},
        {"id": 1000, "timestamp_utc": "2024-02-02T03:04:05Z", "sender": "Other",
         "media": ["b.mp4"]}]

@pytest.fixture
def assets(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"asset-a")
    return str(tmp_path)

def test_binds_by_filename_not_message_id(assets):
    e = rebind(CAT, MSGS, assets)["entries"][0]
    assert e["message_id"] == 999 and e["sender"] == "Right"
    assert e["timestamp_utc"] == "2024-01-02T03:04:05Z"

def test_description_preserved(assets):
    assert rebind(CAT, MSGS, assets)["entries"][0]["description"] == "keep me"

def test_uncatalogued_reported(assets):
    assert "b.mp4" in rebind(CAT, MSGS, assets)["uncatalogued"]

def test_all_rebound_items_unreviewed(assets):
    assert rebind(CAT, MSGS, assets)["entries"][0]["publication"] == "unreviewed"

def test_bound_entries_always_carry_a_content_hash(assets):
    for e in rebind(CAT, MSGS, assets)["entries"]:
        assert e["asset_sha256"] and e["asset_sha256"].startswith("sha256:")

def test_asset_root_is_required():
    with pytest.raises(ValueError):
        rebind(CAT, MSGS, None)

def test_missing_asset_is_unbound_not_null_hashed(tmp_path):
    out = rebind(CAT, MSGS, str(tmp_path))      # a.mp4 absent from disk
    assert not out["entries"]
    assert out["unbound"][0]["reason"].startswith("asset absent")

def test_ambiguous_filename_binding_fails(assets):
    dupes = MSGS + [{"id": 1001, "timestamp_utc": "2024-03-03T00:00:00Z",
                     "sender": "Third", "media": ["a.mp4"]}]
    with pytest.raises(AmbiguousBinding):
        rebind(CAT, dupes, assets)

def test_ambiguous_content_hash_fails(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"same")
    (tmp_path / "c.mp4").write_bytes(b"same")          # identical bytes, two names
    cat = CAT + [{"filename": "c.mp4", "description": "dup", "tags": []}]
    msgs = MSGS + [{"id": 1002, "timestamp_utc": "2024-04-04T00:00:00Z",
                    "sender": "Fourth", "media": ["c.mp4"]}]
    with pytest.raises(AmbiguousBinding):
        rebind(cat, msgs, str(tmp_path))
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Rebind the pre-repair media catalog to the repaired corpus.

message_id is NOT a valid join key: 0 of 1205 joins resolve correctly.
Bind uniquely on filename/source provenance plus asset content hash.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "content" / "chat" / "media-catalog-rebound.json"


class AmbiguousBinding(RuntimeError):
    """A filename bound to more than one live message. Never guess."""


def _names(msg):
    v = msg.get("media") or []
    out = []
    for n in (v if isinstance(v, list) else [v]):
        if isinstance(n, str):
            out.append(n)
        elif isinstance(n, dict) and n.get("filename"):
            out.append(n["filename"])
    return out


def asset_sha256(path):
    """Content hash of the asset on disk, or None when the asset is absent."""
    p = Path(path)
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def rebind(catalog, messages, asset_root):
    """Bind on (asset content hash, filename/source provenance).

    asset_root is REQUIRED. An entry whose asset is absent from disk cannot be
    content-bound and is reported unbound -- it never ships with a null hash.
    """
    if asset_root is None:
        raise ValueError("asset_root is required: binding needs the asset content hash")

    by_file = {}
    for m in messages:
        for n in _names(m):
            by_file.setdefault(n, []).append(m)
    for fn, msgs in by_file.items():
        if len(msgs) > 1:
            raise AmbiguousBinding(f"{fn} binds to {len(msgs)} messages -- refuse to guess")

    by_hash = {}
    entries, unbound = [], []
    for item in catalog:
        fn = item.get("filename")
        live = by_file.get(fn)
        if not live:
            unbound.append({"filename": fn, "reason": "no live message carries this filename"})
            continue
        sha = asset_sha256(Path(asset_root) / fn)
        if sha is None:
            unbound.append({"filename": fn, "reason": "asset absent from disk; cannot content-bind"})
            continue
        if sha in by_hash and by_hash[sha] != fn:
            raise AmbiguousBinding(
                f"content hash {sha} claimed by both {by_hash[sha]} and {fn}")
        by_hash[sha] = fn
        m = live[0]
        entries.append({
            "filename": fn,
            "asset_sha256": sha,                 # never None for a bound entry
            "message_id": m.get("id"),
            "timestamp_utc": m.get("timestamp_utc"),
            "sender": m.get("sender"),
            "description": item.get("description"),
            "tags": sorted(item.get("tags") or []),
            "publication": "unreviewed",
        })
    catalogued = {i.get("filename") for i in catalog}
    return {"entries": sorted(entries, key=lambda e: e["filename"]),
            "unbound": sorted(unbound, key=lambda u: u["filename"]),
            "uncatalogued": sorted(set(by_file) - catalogued)}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset-root", required=True,
                    help="directory holding the media assets; binding needs their hashes")
    args = ap.parse_args()
    cat = json.load(open(ROOT / "content" / "chat" / "media-catalog.json", encoding="utf-8"))
    cat = cat if isinstance(cat, list) else cat.get("items", [])
    parsed = json.load(open(ROOT / "chat" / "parsed_messages.json", encoding="utf-8"))
    messages = parsed["messages"]            # dict container: messages/metadata
    out = rebind(cat, messages, args.asset_root)
    save_json_canonical(OUTPUT, out)
    print(f"rebound={len(out['entries'])} unbound={len(out['unbound'])} "
          f"uncatalogued={len(out['uncatalogued'])}")
    return 1 if out["unbound"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and the real corpus**

```bash
python -m pytest scripts/tests/test_rebind_media_catalog.py -v
python scripts/rebind_media_catalog.py --asset-root <path/to/media/assets>
```

Expected: 9 passed; `rebound=1205 unbound=0 uncatalogued=255`, exit 0, and
`content/chat/media-catalog-rebound.json` written with a non-null `asset_sha256` on every entry.

If any asset is absent from `--asset-root`, that entry lands in `unbound` with reason
`asset absent from disk` and the command exits 1. **That is correct behavior** — an entry that
cannot be content-bound must not ship with a null hash, because the whole point of the rebind is
that the pre-repair provenance is untrustworthy.

- [ ] **Step 5: Commit the rebound corpus**

```bash
git add scripts/rebind_media_catalog.py content/chat/media-catalog-rebound.json scripts/tests/test_rebind_media_catalog.py
git commit -m "feat(media): unique rebind to repaired corpus; 255 uncatalogued unavailable"
```

---

### Task B14: Media manifest, byte verifier, publication record

**Files:** Create `scripts/media_manifest.py`, `scripts/verify_rendered_media.py`,
`scripts/tests/test_media_manifest.py`

**Interfaces:** Produces `manifest_entry(...)`, `build_manifest(edition_id, authoring_mf,
policy_version, entries)`, `publication_record(...)`, `extract_media_nodes(html)`,
`verify_render(html, manifest, root) -> tuple[bool, list[str]]`; both scripts expose `main()`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.media_manifest import manifest_entry, build_manifest, publication_record
from scripts.verify_rendered_media import extract_media_nodes, verify_render

def _league(**kw):
    base = dict(slot="s1", source_class="league_media", publication="approved",
                temporal="2025-09-01T00:00:00Z", source_locator="protected/a.png",
                source_sha="sha256:aa", publish_sha="sha256:bb",
                publish_location="media/2025/a.png", transformation="crop")
    base.update(kw); return manifest_entry(**base)

def test_league_media_requires_publish_location():
    with pytest.raises(ValueError):
        _league(publish_location=None)

def test_league_media_requires_source_binding():
    with pytest.raises(ValueError):
        _league(source_sha=None)

def test_equal_hashes_allowed_when_unchanged():
    e = _league(publish_sha="sha256:aa", transformation="none")
    assert e["publish"]["sha256"] == e["source"]["sha256"]

def test_giphy_requires_persisted_result_or_policy():
    with pytest.raises(ValueError):
        manifest_entry(slot="g1", source_class="giphy", publication="approved",
                       temporal=None, publish_location="https://giphy.com/x.gif",
                       giphy_id=None)

def test_custom_path_must_be_inside_authorized_root():
    with pytest.raises(ValueError):
        manifest_entry(slot="c1", source_class="custom", publication="approved",
                       temporal="non_evidentiary_decoration",
                       publish_location="../../etc/passwd", publish_sha="sha256:cc")

def test_manifest_binds_edition_and_authoring_manifest():
    mf = build_manifest("2025-wk01-recap", {"content_sha256": "sha256:c"}, "policy-v1", [_league()])
    assert mf["edition_id"] == "2025-wk01-recap"
    assert mf["authoring_manifest_sha256"].startswith("sha256:")
    assert mf["media_policy_version"] == "policy-v1"

def test_verifier_detects_multiplicity_mismatch():
    html = '<img src="media/2025/a.png"><img src="media/2025/a.png">'
    mf = {"slots": [_league()]}
    ok, probs = verify_render(html, mf, root=".")
    assert not ok and any("multiplicity" in p for p in probs)

def test_verifier_detects_extra_and_missing():
    mf = {"slots": [_league()]}
    ok, probs = verify_render('<img src="media/2025/rogue.png">', mf, root=".")
    assert not ok and any("rogue" in p for p in probs) and any("not rendered" in p for p in probs)

def test_verifier_rejects_protected_path_in_html():
    ok, probs = verify_render('<img src="protected/a.png">', {"slots": [_league()]}, root=".")
    assert not ok and any("protected" in p for p in probs)

def test_verifier_compares_actual_bytes(tmp_path):
    asset = tmp_path / "media" / "2025"; asset.mkdir(parents=True)
    (asset / "a.png").write_bytes(b"WRONG")
    ok, probs = verify_render('<img src="media/2025/a.png">',
                              {"slots": [_league()]}, root=str(tmp_path))
    assert not ok and any("bytes" in p for p in probs)

def test_publication_record_binds_three():
    rec = publication_record({"content_sha256": "sha256:c"}, {"slots": []}, "<html></html>")
    for k in ("authoring_manifest_sha256", "media_manifest_sha256",
              "rendered_html_sha256", "result"):
        assert k in rec
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`scripts/media_manifest.py`:

```python
"""Per-edition media manifest and publication record."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edition import payload_hash  # noqa: E402

VALID_CLASSES = {"league_media", "giphy", "custom"}
AUTHORIZED_MEDIA_ROOT = "media/"


def manifest_entry(slot, source_class, publication, temporal, publish_location,
                   source_locator=None, source_sha=None, publish_sha=None,
                   transformation=None, selection_provenance=None,
                   giphy_id=None, giphy_resolved=None):
    if source_class not in VALID_CLASSES:
        raise ValueError(f"source_class must be one of {sorted(VALID_CLASSES)}")
    if not publish_location:
        raise ValueError("every entry must name an authorized publication location")
    if source_class == "league_media":
        if not (source_locator and source_sha and publish_sha):
            raise ValueError("league_media binds source locator+SHA and a publish SHA")
        if not publish_location.startswith(AUTHORIZED_MEDIA_ROOT):
            raise ValueError(f"publish_location must sit under {AUTHORIZED_MEDIA_ROOT}")
    if source_class == "giphy" and not (giphy_id and giphy_resolved):
        raise ValueError("giphy entries persist the exact id and resolved result")
    if source_class == "custom":
        if ".." in publish_location or not publish_location.startswith(AUTHORIZED_MEDIA_ROOT):
            raise ValueError(f"custom assets must sit under {AUTHORIZED_MEDIA_ROOT}")
        if not publish_sha:
            raise ValueError("custom assets must hash-match the manifest")
    if temporal is None:
        raise ValueError("temporal decision required: a cutoff instant or "
                         "'non_evidentiary_decoration'")
    return {"slot": slot, "source_class": source_class,
            "selection_provenance": selection_provenance, "temporal": temporal,
            "transformation": transformation, "publication": publication,
            "source": {"locator": source_locator, "sha256": source_sha},
            "publish": {"location": publish_location, "sha256": publish_sha},
            "giphy": {"id": giphy_id, "resolved": giphy_resolved}}


def build_manifest(edition_id, authoring_mf, media_policy_version, entries):
    for e in entries:
        if e["publication"] != "approved":
            raise ValueError(f"slot {e['slot']} is {e['publication']}; only approved may ship")
    return {"edition_id": edition_id,
            "authoring_manifest_sha256": payload_hash(authoring_mf),
            "media_policy_version": media_policy_version,
            "slots": sorted(entries, key=lambda e: e["slot"])}


def publication_record(authoring_mf, media_mf, rendered_html, result="published"):
    return {"authoring_manifest_sha256": payload_hash(authoring_mf),
            "media_manifest_sha256": payload_hash(media_mf),
            "rendered_html_sha256": payload_hash(rendered_html),
            "result": result}
```

`scripts/verify_rendered_media.py`:

```python
"""Multiplicity + location + byte bijection between rendered HTML and the manifest."""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

SRC_RE = re.compile(r'(?:src|href|poster)\s*=\s*["\']([^"\']+)["\']', re.I)
MEDIA_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm")


def extract_media_nodes(html):
    return [m.group(1) for m in SRC_RE.finditer(html)
            if m.group(1).lower().endswith(MEDIA_EXT) or "giphy.com" in m.group(1).lower()]


def _sha(p):
    return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify_render(html, manifest, root="."):
    rendered = Counter(extract_media_nodes(html))
    declared = Counter(s["publish"]["location"] for s in manifest.get("slots", []))
    protected = {(s.get("source") or {}).get("locator")
                 for s in manifest.get("slots", []) if s.get("source")}
    problems = []
    for node in rendered:
        if node in protected:
            problems.append(f"protected source path rendered: {node}")
    for node, n in rendered.items():
        if node not in declared:
            problems.append(f"rendered node not in manifest: {node}")
        elif declared[node] != n:
            problems.append(
                f"multiplicity mismatch for {node}: rendered {n}, manifest {declared[node]}")
    for node, n in declared.items():
        if node not in rendered:
            problems.append(f"manifest entry not rendered: {node}")
    for slot in manifest.get("slots", []):
        loc, want = slot["publish"]["location"], slot["publish"]["sha256"]
        if loc.startswith("http") or not want:
            continue
        p = Path(root) / loc
        if not p.exists():
            problems.append(f"declared asset missing on disk: {loc}")
        elif _sha(p) != want:
            problems.append(f"published bytes differ from manifest for {loc}")
    return (not problems), problems


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("manifest")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    ok, problems = verify_render(Path(args.html).read_text(encoding="utf-8"),
                                 json.load(open(args.manifest, encoding="utf-8")),
                                 root=args.root)
    for p in problems:
        print(f"FAIL {p}")
    print("OK" if ok else f"{len(problems)} problem(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes** → 11 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/media_manifest.py scripts/verify_rendered_media.py scripts/tests/test_media_manifest.py
git commit -m "feat(media): manifest with class rules; byte-level render bijection with CLI"
```

---

## Phase C — Newsroom that proves intelligence

### Task C1: Name repertoires against real fields

Live `name-map.json` entry keys are `aliases`, `display_name`, `real_name`, `roster_id`,
`sleeper_handle`, `team_name` — **not** `handle`/`team`.

**Files:** Create `scripts/mine_name_repertoires.py`, `content/chat/name-repertoires.json`,
`scripts/tests/test_name_repertoires.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.mine_name_repertoires import mine

def test_uses_real_name_map_fields():
    nm = json.load(open("content/chat/name-map.json", encoding="utf-8"))
    out = mine([], nm)
    assert len(out["owners"]) == 12
    assert all(o["handle"] for o in out["owners"]), "must read sleeper_handle"
    assert all(o["team"] for o in out["owners"]), "must read team_name"

def test_handles_match_sleeper_truth():
    users = json.load(open("data/2025/users.json", encoding="utf-8"))
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    assert {o["handle"] for o in rep["owners"]} == {u["display_name"] for u in users}

def test_mines_shorthand_and_nicknames_not_only_seeded_forms():
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    for o in rep["owners"]:
        assert "observed" in o and "register_notes" in o
        seeded = {o["handle"], o["team"], o["first"], o["surname"]}
        observed = {f["form"] for f in o["observed"]}
        assert observed - seeded or o["register_notes"], \
            f"{o['handle']}: no shorthand or nickname discovered and no register note"

def test_observed_forms_are_evidence_backed():
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    for o in rep["owners"]:
        for f in o["observed"]:
            assert f["count"] > 0 and f.get("example_message_id") is not None
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Mine how each owner is actually referred to, from the repaired corpus."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import save_json_canonical  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "content" / "chat" / "name-repertoires.json"
STOPWORDS = {"the", "you", "your", "time", "team", "monks", "giants"}


def _seed_forms(info):
    real = info.get("real_name") or ""
    first = real.split(" ")[0] if real else None
    surname = real.split(" ")[-1] if real and " " in real else None
    team = info.get("team_name") or ""
    team_words = [w for w in re.findall(r"[A-Za-z']+", team)
                  if len(w) > 3 and w.lower() not in STOPWORDS]
    forms = {first, surname, info.get("sleeper_handle"), team, *team_words,
             *(info.get("aliases") or [])}
    return {f for f in forms if f}


def mine(messages, name_map):
    owners = {}
    for key, info in name_map.items():
        rid = info.get("roster_id")
        if rid is None:
            continue
        owners[rid] = {"info": info, "forms": _seed_forms(info) | {key},
                       "counts": Counter(), "example": {}}
    for m in messages:
        text = (m.get("text") or "")
        for rid, o in owners.items():
            for f in o["forms"]:
                if re.search(rf"\b{re.escape(f)}\b", text, re.I):
                    o["counts"][f] += 1
                    o["example"].setdefault(f, m.get("id"))
    out = []
    for rid, o in sorted(owners.items()):
        info = o["info"]
        real = info.get("real_name") or ""
        out.append({
            "roster_id": rid,
            "handle": info.get("sleeper_handle"),
            "team": info.get("team_name"),
            "first": real.split(" ")[0] if real else None,
            "surname": real.split(" ")[-1] if real and " " in real else None,
            "observed": [{"form": f, "count": n,
                          "example_message_id": o["example"].get(f)}
                         for f, n in o["counts"].most_common() if n > 0],
            "register_notes": "",     # authored during review; see Step 4
        })
    return {"version": 1, "owners": out}


def main():
    nm = json.load(open(ROOT / "content" / "chat" / "name-map.json", encoding="utf-8"))
    parsed = json.load(open(ROOT / "chat" / "parsed_messages.json", encoding="utf-8"))
    save_json_canonical(OUTPUT, mine(parsed["messages"], nm))
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate, author register notes, then STOP for Blake's approval**

```bash
python scripts/mine_name_repertoires.py
python -m pytest scripts/tests/test_name_repertoires.py -v
```

Fill `register_notes` per owner (which form suits a roast, which suits sincerity, which nickname
is earned versus invented). **Review gate:** names land like roasts — they should make the owner
laugh, not wince. Do not proceed until Blake approves.

- [ ] **Step 5: Project the repertoire into the bundle**

Add to `project_edition.py`:

```python
@adapter("name_repertoires")
def _names(d):
    return load_json(ROOT / "content" / "chat" / "name-repertoires.json", required=True)
```

and append `"name_repertoires"` to every entry in `REQUIRED_BY_KIND`, plus to the
`culture` desk's contract in `desk_contracts.json`. The Culture desk must not reach outside its
declared boundary to read the file directly.

- [ ] **Step 6: Commit after approval**

```bash
git add scripts/mine_name_repertoires.py content/chat/name-repertoires.json scripts/project_edition.py content/governance/desk_contracts.json scripts/tests/test_name_repertoires.py
git commit -m "feat(voice): chat-mined repertoires on real fields, projected into the bundle"
```

---

### Task C2: Desk commands

**Files:** Create `.claude/commands/desk-{power-rankings,game,history,culture,continuity,copy-editor}.md`;
`scripts/tests/test_desk_commands.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

DESKS = ["power-rankings", "game", "history", "culture", "continuity", "copy-editor"]
CONTRACTS = json.load(open("content/governance/desk_contracts.json", encoding="utf-8"))

def test_all_desks_exist():
    for d in DESKS:
        assert Path(f".claude/commands/desk-{d}.md").exists(), d

def test_desks_declare_no_full_season_stores():
    banned = ["data/franchises/", "player_arcs/", "league_history.json",
              "content/chat/arcs.json", "media-catalog.json", "team-profiles.json"]
    for d in DESKS:
        text = Path(f".claude/commands/desk-{d}.md").read_text(encoding="utf-8")
        for b in banned:
            assert b not in text, f"desk-{d} declares {b}"

def test_desk_names_match_contracts():
    assert set(DESKS) == set(CONTRACTS["recap"].keys())

def test_desks_return_evidence_not_prose():
    for d in DESKS:
        t = Path(f".claude/commands/desk-{d}.md").read_text(encoding="utf-8").lower()
        assert "never prose" in t
```

- [ ] **Step 2: Run to verify it fails** → files missing

- [ ] **Step 3: Author the six commands** — each with this skeleton and its own remit:

````markdown
# Desk: <Name>

You are the <Name> desk. You return **structured evidence and candidate angles — never prose.**
The lead columnist owns voice, pacing, and argument.

## Inputs — the ONLY files you may read

1. `content/editions/<edition_id>/bundle.json`
2. `content/voice-bible.md` — abstract grammar only

You may NOT read full-season stores. If evidence you need is absent from the bundle, report it in
`unavailable` — never reach around the projector.

## Output

```json
{
  "desk": "<name>",
  "edition_id": "...",
  "findings": [
    {
      "claim": "...",
      "evidence_refs": ["/results/matchups/0"],
      "confidence": "high|medium|low",
      "candidate_angle": "..."
    }
  ],
  "unavailable": ["..."]
}
```

Every `evidence_refs` entry is a JSON pointer that resolves inside the bundle.

## Remit

<desk-specific>
````

Remits — **power-rankings**: movement evidence, anomalies, competing orderings, and for each team a
candidate `decisive_evidence` pointer set. **game**: how production actually happened; cite
`player_game_context` one-liners verbatim. **history**: lineage, precedent, prior meetings — from
`h2h`/`records` only. **culture**: chat receipts with exact timestamps, plus which name-form from
`name_repertoires` fits which owner this week. **continuity**: voice memory — read
`prior_editions` and report what has been spent (jokes, comparisons, openers, name-forms per
owner), open threads, and picks awaiting grading. **copy-editor**: check every claim against
bundle evidence; report unsupported claims; do not rewrite.

- [ ] **Step 4: Run tests** → 4 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/desk-*.md scripts/tests/test_desk_commands.py
git commit -m "feat(newsroom): six desks, bundle-only inputs, resolvable evidence refs"
```

---

### Task C3: Ranking schema and grounding gate

**Files:** Create `scripts/schemas/ranking_record.schema.json`, `scripts/verify_ranking_record.py`,
`scripts/tests/test_ranking_record.py`

**Interfaces:** Produces `verify_ranking_record(record, bundle, predecessor) -> tuple[bool, list]`;
`main()` CLI

- [ ] **Step 1: Write the failing test**

```python
from scripts.verify_ranking_record import verify_ranking_record

BUNDLE = {"standings": [{"team_name": f"T{i}"} for i in range(1, 13)],
          "results": {"matchups": [{"a": 1}]}}
PRED = {"entries": [{"team": f"T{i}", "proposed_rank": i} for i in range(1, 13)]}

def _rec(**over):
    entries = [{"team": f"T{i}", "prior_rank": i, "proposed_rank": i, "movement": "steady",
                "decisive_evidence": ["/standings/0"], "contrary_evidence": "thin sample",
                "coherence": "held position on results"} for i in range(1, 13)]
    rec = {"entries": entries}
    rec.update(over); return rec

def test_requires_twelve_distinct_teams():
    r = _rec(); r["entries"] = r["entries"][:11]
    ok, probs = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("twelve" in p for p in probs)

def test_ranks_must_be_one_through_twelve():
    r = _rec(); r["entries"][0]["proposed_rank"] = 13
    ok, probs = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok

def test_unchanged_rank_still_needs_evidence():
    r = _rec(); r["entries"][3]["decisive_evidence"] = []
    ok, probs = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("evidence" in p for p in probs)

def test_evidence_ref_must_resolve_in_bundle():
    r = _rec(); r["entries"][2]["decisive_evidence"] = ["/no/such/pointer"]
    ok, probs = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("resolve" in p for p in probs)

def test_crossing_must_identify_displaced_team():
    r = _rec()
    r["entries"][4].update(prior_rank=5, proposed_rank=3, movement="up_2",
                           coherence="we played well")     # names nobody
    ok, probs = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("displaced" in p for p in probs)

def test_reversal_must_acknowledge_prior_judgment():
    r = _rec()
    r["entries"][0].update(prior_rank=1, proposed_rank=9, movement="down_8",
                           coherence="passed by T2 T3 T4 T5 T6 T7 T8 T9")
    ok, probs = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("prior judgment" in p for p in probs)

def test_substantive_contrary_and_coherence_required():
    r = _rec(); r["entries"][1]["contrary_evidence"] = "n/a"
    ok, probs = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("contrary" in p for p in probs)

def test_clean_record_passes():
    ok, probs = verify_ranking_record(_rec(), BUNDLE, PRED)
    assert ok, probs
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Write the schema and verifier**

`scripts/schemas/ranking_record.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["entries"],
  "properties": {
    "entries": {
      "type": "array",
      "minItems": 12,
      "maxItems": 12,
      "items": {
        "type": "object",
        "required": [
          "team",
          "prior_rank",
          "proposed_rank",
          "movement",
          "decisive_evidence",
          "contrary_evidence",
          "coherence"
        ],
        "properties": {
          "team": { "type": "string" },
          "prior_rank": { "type": ["integer", "null"] },
          "proposed_rank": { "type": "integer", "minimum": 1, "maximum": 12 },
          "movement": { "type": "string" },
          "decisive_evidence": {
            "type": "array",
            "items": { "type": "string" }
          },
          "contrary_evidence": { "type": "string", "minLength": 12 },
          "coherence": { "type": "string", "minLength": 12 }
        },
        "additionalProperties": false
      }
    }
  }
}
```

```python
"""Ranking grounding gate: is the record a real, evidence-bound ordering?"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

VAGUE = {"n/a", "none", "tbd", "-", ""}


def _resolves(bundle, pointer):
    node = bundle
    for part in pointer.strip("/").split("/"):
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return False
            node = node[int(part)]
        elif isinstance(node, dict):
            if part not in node:
                return False
            node = node[part]
        else:
            return False
    return True


def verify_ranking_record(record, bundle, predecessor=None):
    problems = []
    entries = record.get("entries") or []
    if len(entries) != 12 or len({e.get("team") for e in entries}) != 12:
        problems.append("must contain exactly twelve distinct teams")
    if sorted(e.get("proposed_rank") for e in entries) != list(range(1, 13)):
        problems.append("proposed ranks must be exactly 1-12 with no duplicates")

    prior_by_team = {}
    if predecessor:
        prior_by_team = {e["team"]: e["proposed_rank"]
                         for e in predecessor.get("entries", [])}

    for e in entries:
        team = e.get("team")
        if not e.get("decisive_evidence"):
            problems.append(f"{team}: every ordering judgment needs evidence, "
                            "including unchanged ranks")
        for ptr in e.get("decisive_evidence") or []:
            if not _resolves(bundle, ptr):
                problems.append(f"{team}: evidence ref {ptr} does not resolve in the bundle")
        for field in ("contrary_evidence", "coherence"):
            if (e.get(field) or "").strip().lower() in VAGUE:
                problems.append(f"{team}: {field} must be substantive")
        prior, proposed = e.get("prior_rank"), e.get("proposed_rank")
        if isinstance(prior, int) and isinstance(proposed, int):
            delta = prior - proposed
            expected = ("steady" if delta == 0 else
                        f"up_{delta}" if delta > 0 else f"down_{-delta}")
            if e.get("movement") != expected:
                problems.append(f"{team}: movement '{e.get('movement')}' != '{expected}'")
            if delta != 0:
                crossed = [o["team"] for o in entries
                           if o is not e
                           and isinstance(o.get("prior_rank"), int)
                           and (o["prior_rank"] - prior) * (o["proposed_rank"] - proposed) < 0]
                named = [c for c in crossed if c in (e.get("coherence") or "")]
                if crossed and not named:
                    problems.append(f"{team}: crossing must identify the displaced team "
                                    f"(candidates {crossed[:3]})")
            if prior_by_team.get(team) is not None and abs(delta) >= 4:
                if "previously" not in (e.get("coherence") or "").lower() and \
                   "prior" not in (e.get("coherence") or "").lower():
                    problems.append(f"{team}: reversal must acknowledge the prior judgment")
    return (not problems), problems


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--predecessor")
    a = ap.parse_args()
    pred = json.load(open(a.predecessor, encoding="utf-8")) if a.predecessor else None
    ok, problems = verify_ranking_record(json.load(open(a.record, encoding="utf-8")),
                                         json.load(open(a.bundle, encoding="utf-8")), pred)
    for p in problems:
        print(f"FAIL {p}")
    print("OK" if ok else f"{len(problems)} problem(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes** → 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/schemas/ranking_record.schema.json scripts/verify_ranking_record.py scripts/tests/test_ranking_record.py
git commit -m "feat(rankings): grounding gate -- resolvable evidence, crossings, reversals"
```

---

### Task C4: The bake-off

**Files:** Create `.claude/commands/bakeoff.md`, `content/editions/_bakeoff/rubric.json`,
`scripts/tests/test_bakeoff_record.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

def test_rubric_scores_ranking_and_prose():
    r = json.load(open("content/editions/_bakeoff/rubric.json", encoding="utf-8"))
    dims = {d["name"] for d in r["dimensions"]}
    assert {"ranking_grounding", "ranking_judgment"} <= dims
    assert {"factual_corrections", "unique_evidence", "phrase_repetition",
            "owner_specificity", "survived_blake_edit"} <= dims

def test_decision_record_shape_enforced():
    r = json.load(open("content/editions/_bakeoff/rubric.json", encoding="utf-8"))
    for f in ("winner", "loser_disposal", "scores", "decided_at_utc"):
        assert f in r["decision_record_fields"], f
```

- [ ] **Step 2: Run to verify it fails** → file missing

- [ ] **Step 3: Write the rubric**

```json
{
  "version": 1,
  "dimensions": [
    {
      "name": "ranking_grounding",
      "how": "verify_ranking_record problems count (lower wins)"
    },
    {
      "name": "ranking_judgment",
      "how": "Blake's qualitative call on the ordering itself"
    },
    {
      "name": "factual_corrections",
      "how": "verifier errors requiring fixes (lower wins)"
    },
    {
      "name": "unique_evidence",
      "how": "distinct bundle pointers cited (higher wins)"
    },
    {
      "name": "phrase_repetition",
      "how": "repeated constructions within the piece (lower wins)"
    },
    {
      "name": "owner_specificity",
      "how": "owner-specific details per blurb (higher wins)"
    },
    {
      "name": "survived_blake_edit",
      "how": "percent of prose surviving Blake's edit"
    }
  ],
  "decision_record_fields": [
    "winner",
    "loser_disposal",
    "scores",
    "decided_at_utc",
    "notes"
  ],
  "rule": "A candidate with better prose but weaker ranking judgment loses."
}
```

`.claude/commands/bakeoff.md` instructs: produce the first edition twice — once via the six desks,
once via the existing single-writer pipeline — score both on every dimension, record the decision
at `content/editions/_bakeoff/decision.json`, and **delete the losing pipeline's command files**
so only one path remains.

- [ ] **Step 4: Run tests** → 2 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/bakeoff.md content/editions/_bakeoff/rubric.json scripts/tests/test_bakeoff_record.py
git commit -m "feat(newsroom): bake-off rubric scoring ranking and prose, with loser disposal"
```

---

### Task C5: Preseason-edition mode for the verifier

`verify_week_content.py:1554` builds `week{args.week}_content.json`, so `--week 0` seeks a
nonexistent `week0` file. D1a needs an edition mode.

**Files:** Modify `scripts/verify_week_content.py`; `scripts/tests/test_verify_edition_mode.py`

- [ ] **Step 1: Write the failing test**

```python
import subprocess, sys

def test_edition_mode_accepts_an_edition_dir(tmp_path):
    r = subprocess.run([sys.executable, "scripts/verify_week_content.py",
                        "--edition", "content/editions/2025-preseason", "--pretty"],
                       capture_output=True, text=True)
    assert r.returncode in (0, 1), f"edition mode missing: {r.stderr[:200]}"
    assert "week0" not in r.stderr

def test_week_zero_no_longer_accepted():
    r = subprocess.run([sys.executable, "scripts/verify_week_content.py", "--week", "0"],
                       capture_output=True, text=True)
    assert r.returncode != 0
```

- [ ] **Step 2: Run to verify it fails** → `--edition` unrecognized

- [ ] **Step 3: Add `--edition`**, resolving `content.json`, `bundle.json`, and
      `ranking_record.json` from the edition directory; reject `--week 0`; skip week-only Tier-1
      checks (`movement_strings`, `picks_matchups`) for `kind == "preseason"`.

- [ ] **Step 4: Run tests; suite ≥ 343/2**

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_week_content.py scripts/tests/test_verify_edition_mode.py
git commit -m "feat(verify): edition mode replaces the nonexistent week-0 path"
```

---

## D1 — Three editions, then STOP

**Sequence for every edition, in this exact order:**

```
descriptor → canonical compile → bundle manifest → desks (+ bake-off on the first)
  → RANKING RECORD → prose written FROM it → authoring manifest
  → Blake's separate ranking approval → editorial approval bound to that manifest
  → media manifest → render → byte verifier → publication record → commit
```

The ranking record precedes the prose. Writing first and justifying afterward produces a record
that looks like reasoning and contains none.

### Task D1a: Preseason edition

- [ ] **Step 1: Write the descriptor** to `content/editions/2025-preseason/descriptor.json`:

```json
{
  "edition_id": "2025-preseason",
  "season": 2025,
  "kind": "preseason",
  "cutoff_utc": "2025-09-03T23:59:59Z",
  "results_through_week": 0,
  "policy_version": "v1"
}
```

- [ ] **Step 2: Compile and audit**

```bash
python scripts/compile_edition.py --descriptor content/editions/2025-preseason/descriptor.json
python scripts/cutoff_audit.py --all
```

Expected: all five artifacts written; audit exits 0.

- [ ] **Step 3: Run the desks, then the bake-off** (`/bakeoff` — first edition only). Record the
      decision and delete the losing pipeline.

- [ ] **Step 4: Author `ranking_record.json`, then gate it**

```bash
python scripts/verify_ranking_record.py --record content/editions/2025-preseason/ranking_record.json --bundle content/editions/2025-preseason/bundle.json
```

Expected: OK, exit 0. `prior_rank` is `null` for every team; **evidence is still required**.

- [ ] **Step 5: Write the prose from that judgment**, then:

```bash
python scripts/verify_week_content.py --edition content/editions/2025-preseason --pretty
python scripts/canon_checks.py --preseason
```

- [ ] **Step 6: Blake approves the ranking separately from the prose**, then `/edit-preseason` →
      APPROVE with a `review-log.jsonl` line bound to the authoring manifest.

- [ ] **Step 7: Media, render, verify bytes, publish**

```bash
python scripts/verify_rendered_media.py preseason-2025.html content/editions/2025-preseason/media_manifest.json
```

Expected: OK, exit 0. Write `publication.json`.

- [ ] **Step 8: Commit**

```bash
git add content/editions/2025-preseason/ preseason-2025.html content/review-log.jsonl
git commit -m "content(2025-preseason): first canonical edition through the full system"
```

---

### Task D1b: Week-1 pre-kickoff preview

- [ ] **Step 1: Qualify the cutoff — do not hard-code it**

```bash
python scripts/fetch_nflreadpy.py            # refresh schedules_2025.parquet
python -c "
from scripts.kickoff_source import first_kickoff_instant, strictly_before
i,s = first_kickoff_instant(2025); print(strictly_before(i), s)"
```

Write the returned instant into the descriptor and the source hash into
`source_hashes.json`. If `UnavailableEvidence` is raised, **stop** — a preview cutoff may not be
guessed.

- [ ] **Step 2: Compile and assert emptiness**

```bash
python scripts/compile_edition.py --descriptor content/editions/2025-wk01-preview/descriptor.json
python -m pytest scripts/tests/test_project_edition.py -v
```

Expected: no week-1 outcomes, no final starters, player `6949` absent from roster 6.

- [ ] **Step 3-8: desks → ranking record (gated, `prior_rank` from the preseason edition) →
      prose → ranking approval → editorial approval → media → render → byte verify → publish →
      commit**, exactly as D1a. Add the nav entry to `config.js`.

```bash
git add content/editions/2025-wk01-preview/ week1-preview.html config.js content/review-log.jsonl
git commit -m "content(2025-wk01-preview): preview on a qualified strictly-prior cutoff"
```

---

### Task D1c: Week-1 recap

- [ ] **Step 1: Descriptor** — `kind: "recap"`, `results_through_week: 1`,
      `cutoff_utc: "2025-09-09T06:59:59Z"` (Tue 06:59:59 UTC after MNF).

- [ ] **Step 2: Compile; confirm week-1 results present and week-2 absent.**

- [ ] **Step 3-8:** as D1a. The continuity desk grades the preview's picks and the preseason's
      claims — the first edition where receipts resolve. The ranking record's `prior_rank` comes
      from the preview edition, and reversals against the preseason must be acknowledged.

```bash
git add content/editions/2025-wk01-recap/ week1.html content/review-log.jsonl
git commit -m "content(2025-wk01-recap): preview picks graded, threads advanced"
```

---

### Task D1d: PRODUCT GATE — stop

**Do not begin D2. Do not build further adapters or desks.**

- [ ] **Step 1: Full acceptance sweep**

```bash
python -m pytest scripts/tests/ -q
python scripts/cutoff_audit.py --all
python scripts/generate_chat_provenance.py --verify
python -m pytest scripts/tests/test_noninterference.py -v
```

Expected: suite ≥ 343 passed / 2 skipped; audit exits 0; provenance OK; noninterference and the
2024 canary green.

- [ ] **Step 2: Assemble the review packet** — census 46 → 0; zero structurally unsliced H2H
      blocks (from 98); three ranking records with their gate output; `review-log.jsonl`; byte
      verifier output per edition; the bake-off decision; and a side-by-side against the old
      pipeline's week-1 filler.

- [ ] **Step 3: Answer the product question in writing**

> **Did the model become visibly more informed across the three editions?**

Point to specific ranking movements justified by evidence that did not exist in the prior
edition. If the answer is no, revise the source and desk contracts before D2. Passing on temporal
correctness alone is not passing.

- [ ] **Step 4: STOP.** Await Blake's decision.

---

## Self-Review

**Corrections applied.** (1) Lane P now has a real fetcher per source, an offseason-capable leg
range independent of scored matchups, documented manual ingestion, a baseline capture, a named
cadence workflow, and receipts; the reversed `save_json_canonical` call is fixed to `(path, data)`.
(2) A1 is an AST source graph with a STOP gate before A2 mutates anything; A2 rewires every named
consumer and barred reads fail tests; `analyze_chat.py` writes only to scratch and uses
`sys.exit(main())`. (3) B9 supplies the full D1 evidence matrix with per-desk coverage tests,
season-parameterized paths, and `effective_instant` refusing a `created` fallback; B11 is one
atomic canonical compiler emitting descriptor, bundle, manifest, build identity, and source
hashes. (4) B12 restores noninterference with a positive control, clean-rebuild reproduction, and
a 2024 canary — all before D1. (5) B13 binds uniquely, fails ambiguity, reads `parsed["messages"]`,
and persists the rebound corpus; B14 binds edition identity, authoring manifest, and policy
version, enforces class rules, and verifies multiplicity, location, and bytes; both audits have
CLIs with real exit codes. (6) C1 reads `sleeper_handle`/`team_name`, mines shorthand with
evidence, and projects the repertoire into the bundle; C4 adds the bake-off; C3 defines the schema
and enforces twelve distinct teams, ranks 1-12, evidence for every judgment including unchanged
ranks, resolvable pointers, substantive contrary/coherence, displaced-team identification, and
reversal acknowledgement. (7) D1 loops are literal, the preview cutoff is qualified from a hashed
source, and C5 replaces the nonexistent week-0 mode.

**Known limitation, stated rather than hidden.** `test_noninterference.py`'s full-versus-truncated
comparison currently rebuilds from the same on-disk inputs, so it proves determinism plus
cutoff-sensitivity (via the positive control) rather than true input truncation. Genuine
truncation requires a fixture corpus with post-cutoff rows physically removed; that fixture is
built in D2 when more adapters exist to exercise it. Flagged here rather than dropped.

**Placeholder scan.** No TBD/TODO. Every code step carries runnable code; every test step carries
real assertions; every command is exact and dry-checked against live interfaces.

**Type consistency.** `slice_h2h`/`as_of_records` (B1/B2) are consumed identically in B3 and B9.
`payload_hash` (B7) is consumed in B11, B14. `EditionDescriptor` fields match across B7, B9, B11,
and all three D1 descriptors. `manifest_entry`'s `publish.location`/`publish.sha256` are the keys
`verify_render` reads. `audit_object`'s `ok`/`unclassified`/`forbidden_present` are the keys B6 and
the CLI consume.
