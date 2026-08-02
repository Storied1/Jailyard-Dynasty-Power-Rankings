# Jailyard Writer Foundation — Implementation Plan (through D1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Status:** DRAFT — third revision, after review of `ac3f82a`. Awaiting Blake's approval. Not
authorized for implementation.

**Goal:** Make the minimum slice genuinely vertical — 2026 evidence durably preserved, every
writer-facing consumer bundle-bound, future evidence provably unable to reach an earlier edition,
and three canonical editions whose rankings show a model that became more informed — then stop.

**Architecture:** A season-qualified projection compiler is the sole trusted reader of raw stores;
every consumer reads a persisted bundle. Adapters declare the exact source identities they
consumed. Ranking judgment precedes prose and is mechanically grounded. Media is admitted at
compile time and verified byte-for-byte in the rendered HTML.

**Design authority:** `docs/superpowers/specs/2026-08-01-jailyard-writer-foundation-design.md`
(APPROVED at `072f4ea`).

## Global Constraints

- `python`, never `python3` (Windows).
- **`shared.save_json_canonical(path, data, verbose=False)`** — path FIRST.
- sys.path bootstrap per `scripts/fetch_nflreadpy.py:20-25`; tests import `from scripts.X import`.
- Every CLI ends `raise SystemExit(main())`. A bare `main()` returning 1 exits 0 — the live
  `analyze_chat.py` has exactly this defect.
- `sorted()`, never `list(set)`, where serialized.
- Baseline suite **343 passed / 2 skipped** (`c751b22`, 167s). No task reduces it.
- Binary gates. No "approve with notes".
- Cutoffs are exact UTC instants; `shared.admissible` is inclusive (`<=`), so a cutoff that must
  exclude an instant is set strictly prior.
- **Every adapter and the compiler read through an injectable `SOURCE_ROOT`.** No module-level
  absolute path may be read directly by an adapter. This is what makes truncation testable.
- **Two capture roots.** `data/captures/2026/public/` is tracked; `private_captures/` is
  gitignored and never staged.
- **One writer.** Lane P runs operationally alongside D1, never as a concurrent repo writer.
- This plan performs no pushes, publishes nothing, and touches no protected untracked paths.

---

## Corrections carried from the `ac3f82a` review

Each was verified against live code before acceptance.

| #   | Finding                                                                                                                                                                                                                                           | Verified |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| 1   | `week1_chat_context.json` declares cutoff `2025-09-09T06:59:59Z` and holds **28** result statements ("low scorer this week", "won by 15.2"). The preview adapter loaded it.                                                                       | ✅ live  |
| 2   | Pairings/standings/results/expanded/chat resolved through seasonless `content/weeks/week{N}_*` paths declaring season 2025                                                                                                                        | ✅       |
| 3   | `kickoff_source` appended `Z` to a local time-of-day. `nfl_game.schema.json:31`: _"Local kickoff time-of-day … not ISO8601. Combine with stadium timezone."_                                                                                      | ✅       |
| 4   | `HASHED_SOURCES` bound only `league_history.json` + 2 py files                                                                                                                                                                                    | ✅       |
| 5   | `compile_edition` `rmtree`'d the whole edition dir, destroying authored artifacts                                                                                                                                                                 | ✅       |
| 6   | `voice-bible.md` was barred while every rewired consumer must read it                                                                                                                                                                             | ✅       |
| 7   | `canon_checks.py:160-177` reads legacy chat artifacts; A2 rewired only the command                                                                                                                                                                | ✅       |
| 8   | `analyze_chat.py` writes via `OUT_LEAGUE_MEMORY/OUT_ARCS/OUT_PREDICTIONS/OUT_RELATIONSHIPS/OUT_CONSENSUS/PERSONAS_DIR`; there is no `OUTPUT_ROOT`, so the override was inert                                                                      | ✅       |
| 9   | No media assets exist in the repo tree                                                                                                                                                                                                            | ✅       |
| —   | **Refuted:** polars raising `sse3` on this machine. `python -c "import polars"` → **OK 1.40.1**. The _test_ defect (no skip, no `UnavailableEvidence` catch) is real and fixed; the runtime issue is not reproduced and no workaround is planned. | ❌       |

---

## Lane P — durable 2026 preservation

### Task P1: Capture store, split roots, receipts

**Files:** Create `scripts/capture_2026.py`, `scripts/tests/test_capture_2026.py`; modify
`.gitignore`

**Interfaces:** `capture(source, payload, known_at_rule, privacy, captured_at) -> Path`,
`PUBLIC_ROOT`, `PRIVATE_ROOT`, `receipt(paths) -> dict`

- [ ] **Step 1: Write the failing test**

```python
import json
import pytest
from scripts.capture_2026 import capture, receipt, PUBLIC_ROOT, PRIVATE_ROOT

def test_public_and_private_roots_are_distinct():
    assert PUBLIC_ROOT != PRIVATE_ROOT
    assert "private" in str(PRIVATE_ROOT)

def test_private_capture_lands_outside_the_public_root(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.PUBLIC_ROOT", tmp_path / "pub")
    monkeypatch.setattr("scripts.capture_2026.PRIVATE_ROOT", tmp_path / "priv")
    p = capture("chat_media_export", {"m": 1}, "message_timestamp", "private",
                "2026-08-02T00:00:00Z")
    assert (tmp_path / "priv") in p.parents
    assert (tmp_path / "pub") not in p.parents

def test_metadata_and_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.PUBLIC_ROOT", tmp_path)
    kw = ("capture_instant", "public", "2026-08-02T00:00:00Z")
    rec = json.loads(capture("league", {"a": 1}, *kw).read_text(encoding="utf-8"))
    for f in ("source", "captured_at", "known_at_rule", "content_sha256", "privacy"):
        assert f in rec
    with pytest.raises(FileExistsError):
        capture("league", {"a": 2}, *kw)

def test_receipt_never_contains_private_payloads(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.PRIVATE_ROOT", tmp_path)
    p = capture("chat_media_export", {"secret": "x"}, "message_timestamp", "private",
                "2026-08-02T00:00:00Z")
    r = receipt([p])
    assert "secret" not in json.dumps(r)
    assert r["entries"][0]["privacy"] == "private"
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

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


def _sha(obj):
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
        "privacy": privacy, "content_sha256": _sha(payload), "payload": payload})
    return path


def receipt(paths):
    """Metadata only. Private payloads never enter a receipt."""
    entries = []
    for p in sorted(paths):
        rec = json.loads(Path(p).read_text(encoding="utf-8"))
        entries.append({k: rec[k] for k in
                        ("source", "captured_at", "content_sha256", "privacy")})
    return {"count": len(entries), "entries": entries}
```

Add to `.gitignore`:

```
private_captures/
```

- [ ] **Step 4: Run** → 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_2026.py scripts/tests/test_capture_2026.py .gitignore
git commit -m "feat(capture): split public/private roots; receipts carry metadata only"
```

---

### Task P2: A working fetch per row; cadence through kickoff

`fetch_sleeper.py:172` uses `range(1, len(all_matchups) + 1)` — `range(1, 1)` preseason.

**Files:** Modify `scripts/capture_2026.py`; create `content/governance/capture_table.json`,
`docs/superpowers/plans/capture-manual-ingest.md`

**Interfaces:** `SOURCE_FETCHERS`, `TRANSACTION_LEGS`, `run_capture(now_utc, league_id)`,
`load_capture_table()`

- [ ] **Step 1: Write the failing test**

```python
from scripts.capture_2026 import load_capture_table, TRANSACTION_LEGS, SOURCE_FETCHERS

REQUIRED = {"sleeper_league", "sleeper_users", "rosters", "draft", "transactions"}

def test_minimum_rows_present():
    assert REQUIRED <= {r["source"] for r in load_capture_table()}

def test_every_row_has_a_fetcher_or_documented_manual_path():
    for r in load_capture_table():
        assert r["source"] in SOURCE_FETCHERS or r.get("manual_ingest_doc"), r["source"]

def test_transaction_legs_independent_of_scored_matchups():
    assert 1 in TRANSACTION_LEGS and max(TRANSACTION_LEGS) >= 18

def test_private_rows_declared_private():
    rows = {r["source"]: r for r in load_capture_table()}
    assert rows["chat_media_export"]["privacy"] == "private"
```

- [ ] **Step 2: Run to verify it fails** → `ImportError`

- [ ] **Step 3: Write the table** — same eight rows as the prior revision, with
      `chat_media_export` privacy `private` and a `manual_ingest_doc` on every
      `manual_export` row.

- [ ] **Step 4: Implement fetchers**

```python
TRANSACTION_LEGS = list(range(1, 19))      # never from len(all_matchups)

CAPTURE_TABLE_PATH = (Path(__file__).resolve().parents[1]
                      / "content" / "governance" / "capture_table.json")


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


def run_capture(now_utc, league_id):
    written = []
    for row in load_capture_table():
        fn = SOURCE_FETCHERS.get(row["source"])
        if fn is None:
            continue                          # manual rows: see manual_ingest_doc
        written.append(capture(row["source"], fn(league_id),
                               row["known_at_rule"], row["privacy"], now_utc))
    return receipt(written)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--league-id", required=True)
    ap.add_argument("--now-utc", required=True)
    a = ap.parse_args()
    print(json.dumps(run_capture(a.now_utc, a.league_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Write `capture-manual-ingest.md`** — one section per manual row stating source,
      the exact `capture(...)` call, the `known_at` justification, and for chat that the export
      is private-class and lands in `PRIVATE_ROOT`.

- [ ] **Step 6: Run** → 4 passed

- [ ] **Step 7: Commit**

```bash
git add scripts/capture_2026.py content/governance/capture_table.json docs/superpowers/plans/capture-manual-ingest.md scripts/tests/test_capture_2026.py
git commit -m "feat(capture): working fetch per source; offseason-capable legs"
```

---

### Task P3: Baseline capture now; durable cadence behind approval

- [ ] **Step 1: Take the baseline capture immediately**

```bash
python scripts/capture_2026.py --league-id <2026_LEAGUE_ID> --now-utc <ISO8601Z>
```

This is the point of Lane P — evidence is disappearing now. Do it before Phase A.

- [ ] **Step 2: Stage ONLY the public root**

```bash
git add data/captures/2026/public/
git status --short | grep private_captures && echo "STOP: private capture staged" && exit 1
git commit -m "data(capture): baseline 2026 public capture"
```

Never `git add data/captures/2026/` wholesale — that path is public-only by construction, but the
guard above is the check that it stayed that way.

- [ ] **Step 3: Author the cadence workflow — do NOT activate it**

Create `.github/workflows/capture-preseason-2026.yml` with
`cron: '0 6 * 7,8,9 *'` — daily through **September**, because the pre-kickoff window does not end
on August 31. The job must **commit its captures back**, not merely run the CLI; a runner
discards its filesystem on exit, so a workflow that only invokes the CLI preserves nothing.

The existing `fetch-sleeper-data.yml` (`cron: '0 6 * 9-12 0'`) is weekly and overwriting — it is
not this lane and does not substitute for it.

- [ ] **Step 4: STOP — workflow activation requires Blake's explicit approval of that exact push**

This plan performs no pushes, so the workflow will not become active during D1. Local checkpoint
captures cover the gap (Step 5).

- [ ] **Step 5: Local checkpoint captures at every phase boundary**

Re-run the CLI at the end of Phase A, Phase B, and Phase C. Each is a fresh timestamped capture;
the append-only store makes repeats free and refuses overwrites.

- [ ] **Step 6: Commit the workflow file (inactive until pushed)**

```bash
git add .github/workflows/capture-preseason-2026.yml
git commit -m "chore(capture): daily preseason cadence workflow, inactive pending approval"
```

---

## Phase A — Install the boundary

### Task A1: Source-graph census (AST) — then STOP

**Files:** Create `scripts/source_graph.py`, `scripts/tests/test_source_graph.py`

**Interfaces:** `read_edges()`, `barred_edges()`, `CONSUMERS`, `BARRED_TARGETS`,
`ALLOWED_EDITORIAL_RULES`

- [ ] **Step 1: Write the failing test**

```python
from scripts.source_graph import (read_edges, barred_edges, CONSUMERS,
                                  BARRED_TARGETS, ALLOWED_EDITORIAL_RULES)

def test_consumers_include_transitively_invoked_scripts():
    for c in ("write-preseason", "write-week", "edit-week", "edit-preseason",
              "canon_checks", "local_draft", "pick-media", "resolve_media",
              "render-week", "render-preseason", "verify_week_content"):
        assert c in CONSUMERS, c

def test_voice_bible_is_an_allowed_rule_not_barred():
    assert "voice-bible.md" in ALLOWED_EDITORIAL_RULES
    assert "voice-bible.md" not in BARRED_TARGETS

def test_edges_are_resolved_reads():
    for e in read_edges():
        assert e["kind"] in {"python_open", "python_constant_path", "command_declared_input"}
        assert e["target"]

def test_canon_checks_legacy_reads_are_detected():
    targets = {e["target"] for e in barred_edges() if e["consumer"] == "canon_checks"}
    assert any("chat_context" in t for t in targets), \
        "canon_checks.py:160-177 reads legacy chat artifacts and must be caught"
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

# Commands AND the python consumers D1 invokes directly or transitively.
CONSUMERS = {
    "write-preseason", "write-week", "edit-week", "edit-preseason", "canon-check",
    "pick-media", "render-week", "render-preseason",
    "canon_checks", "local_draft", "batch_drafts", "resolve_media",
    "verify_week_content", "verify_ranking_record",
}

# Versioned editorial rules a consumer MAY read (surgically cleaned in A3).
ALLOWED_EDITORIAL_RULES = {"voice-bible.md"}

BARRED_TARGETS = (
    "team-profiles.json", "preseason-2026",
    "league_history.json", "player_arcs", "franchises",
    "media_picks.json", "media_cache.json", "content/chat/",
    "_data_expanded.json", "_chat_context.json", "_data.json",
)


def _py_edges(py):
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    consts = {n.targets[0].id: ast.unparse(n.value) for n in ast.walk(tree)
              if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if fn not in {"open", "load_json", "read_text", "read_bytes"}:
            continue
        arg = ast.unparse(node.args[0]) if node.args else ""
        out.append({"consumer": py.stem, "target": consts.get(arg, arg),
                    "line": node.lineno,
                    "kind": "python_constant_path" if arg in consts else "python_open"})
    return out


def _md_edges(md):
    return [{"consumer": md.stem, "target": m.group(1), "line": i,
             "kind": "command_declared_input"}
            for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1)
            for m in re.finditer(r"`([^`]+\.(?:json|md|html))`", line)]


def read_edges():
    edges = []
    for py in sorted((ROOT / "scripts").glob("*.py")):
        if py.stem in CONSUMERS:
            edges += _py_edges(py)
    for md in sorted((ROOT / ".claude" / "commands").glob("*.md")):
        if md.stem in CONSUMERS:
            edges += _md_edges(md)
    return edges


def barred_edges():
    return [e for e in read_edges()
            if any(b in e["target"] for b in BARRED_TARGETS)
            and not any(a in e["target"] for a in ALLOWED_EDITORIAL_RULES)]


def main():
    import json
    print(json.dumps({"all": read_edges(), "barred": barred_edges()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run** → 4 passed

- [ ] **Step 5: Produce the census**

```bash
python scripts/source_graph.py > docs/superpowers/plans/source-graph-census-2026-08-02.json
```

- [ ] **Step 6: STOP — Blake reviews before A2 mutates anything.**

- [ ] **Step 7: Commit the census only**

```bash
git add scripts/source_graph.py scripts/tests/test_source_graph.py docs/superpowers/plans/source-graph-census-2026-08-02.json
git commit -m "feat(census): AST source graph incl. transitively invoked scripts"
```

---

### Task A2: Rewire every consumer, including the scripts D1 invokes

**Files:** Modify the eight command `.md` files, `scripts/canon_checks.py`,
`scripts/local_draft.py`, `scripts/batch_drafts.py`, `scripts/resolve_media.py`,
`scripts/verify_week_content.py`; create `scripts/tests/test_writer_access_boundary.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.source_graph import barred_edges

def test_no_consumer_reads_a_barred_target():
    offending = barred_edges()
    assert not offending, f"{len(offending)} barred reads remain: {offending[:5]}"

def test_canon_checks_consumes_the_bundle():
    import ast
    from pathlib import Path
    src = Path("scripts/canon_checks.py").read_text(encoding="utf-8")
    assert "--edition" in src, "canon_checks must accept an edition, not week/preseason paths"
    assert "chat_context.json" not in src
```

- [ ] **Step 2: Run to verify it fails** → many offending edges

- [ ] **Step 3: Rewire**

Declared inputs for every consumer become exactly:

1. `content/editions/<edition_id>/bundle.json`
2. approved prior editions' `content.json` (continuity consumers only)
3. `content/voice-bible.md` — allowed versioned editorial rule
4. `content/editions/<edition_id>/ranking_record.json`
5. `content/editions/<edition_id>/media_manifest.json` (resolver, renderers)

`canon_checks.py` gains `--edition <dir>` and validates the bundle's chat component in place of
`preseason_chat_context.json` / `week{N}_chat_context.json` (`:160-177`). Delete
`write-preseason.md:47-53` ("use as inspiration") and `:72-75` (2026 tone precedent), and
`write-week.md:7-25`'s whole-voice-bible + team-profile input list.

- [ ] **Step 4: Run** → boundary clean; suite ≥ 343/2

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/ scripts/canon_checks.py scripts/local_draft.py scripts/batch_drafts.py scripts/resolve_media.py scripts/verify_week_content.py scripts/tests/test_writer_access_boundary.py
git commit -m "refactor(boundary): bundle-only inputs incl. canon_checks; voice bible allowed"
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
    assert not quotes, f"{len(quotes)} excerpts remain"

def test_abstract_grammar_retained():
    t = VB.read_text(encoding="utf-8")
    for m in ("Pattern 1", "Pattern 12", "Anti-Patterns", "Cold Open Essay"):
        assert m in t, m

def test_no_stale_handle_table():
    assert "@kharlo_w" not in VB.read_text(encoding="utf-8")

def test_declares_a_rule_version():
    assert "rule_version:" in VB.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify it fails** → all four

- [ ] **Step 3: Edit** — delete every `>` example under §1 (`:16-20`, `:38-46`, `:64-70`,
      `:100-106`, `:122-126`, `:148-152`) and all of §5; replace §2's handle table with a pointer
      to the repertoire; add `rule_version: voice-v1` at the top so the authoring manifest can
      bind it. **No replacement exemplar is required for the first edition.**

- [ ] **Step 4: Run** → 4 passed

- [ ] **Step 5: Commit**

```bash
git add content/voice-bible.md scripts/tests/test_voice_bible_clean.py
git commit -m "refactor(voice): strip excerpts; versioned rule; repertoire pointer"
```

---

### Task A4: Disable `analyze_chat.py` execution for D1

The prior override assigned an unused `OUTPUT_ROOT`; the live script writes through
`OUT_LEAGUE_MEMORY`, `OUT_ARCS`, `OUT_PREDICTIONS`, `OUT_RELATIONSHIPS`, `OUT_CONSENSUS`,
`PERSONAS_DIR` — all still active. The lean fix is to disable execution outright.

**Files:** Modify `scripts/analyze_chat.py`, `scripts/build_chat_context.py`;
create `scripts/tests/test_producer_quarantine.py`

- [ ] **Step 1: Write the failing test**

```python
import ast, hashlib, subprocess, sys
from pathlib import Path

CANONICAL = ["content/chat/league-memory.json", "content/chat/arcs.json",
             "content/chat/predictions.json", "content/chat/relationships.json",
             "content/chat/consensus.json"]

def _hashes():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in CANONICAL if Path(p).exists()}

def test_execution_is_disabled_and_exits_nonzero():
    before = _hashes()
    r = subprocess.run([sys.executable, "scripts/analyze_chat.py"],
                       capture_output=True, text=True)
    assert r.returncode != 0, "bare main() would exit 0"
    assert "disabled" in (r.stdout + r.stderr).lower()
    assert _hashes() == before, "canonical analytics must be untouched"

def test_no_override_flag_exists():
    src = Path("scripts/analyze_chat.py").read_text(encoding="utf-8")
    assert "--inspect-to-scratch" not in src, \
        "no inspection path for D1; a partial redirect leaves OUT_* live"

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
DISABLED_MSG = (
    "analyze_chat.py is DISABLED for the D1 program. It message-ID-joins the pre-repair "
    "media catalog and writes through OUT_LEAGUE_MEMORY / OUT_ARCS / OUT_PREDICTIONS / "
    "OUT_RELATIONSHIPS / OUT_CONSENSUS / PERSONAS_DIR -- the exact analytics the canonical "
    "builder consumes. No inspection override is provided: a partial redirect leaves those "
    "constants live. Re-enable only after the catalog is rebound and this script enters "
    "generate_chat_provenance.py CODE_FILES."
)


def main():
    print(DISABLED_MSG, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Keep the original body as `_legacy_main()` (unreferenced) so nothing is lost to git history.
In `build_chat_context.py`: delete `MEDIA_CATALOG_PATH` (`:38`), the `media_catalog` parameter
(`:358`), and the lookup (`:381-382`).

- [ ] **Step 4: Run tests; re-verify provenance**

```bash
python -m pytest scripts/tests/test_producer_quarantine.py -v
python scripts/generate_chat_provenance.py --verify
```

`build_chat_context.py` is in `CODE_FILES`; rebuild the receipt via `--rebuild-check` then
`--write --receipt <path>`. Never hand-edit the manifest.

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_chat.py scripts/build_chat_context.py content/chat/provenance.json scripts/tests/test_producer_quarantine.py
git commit -m "fix(chat): disable analyze_chat execution; remove dead media enrichment"
```

---

### Task A5: Strip prose from generated artifacts

**Files:** Modify `scripts/extract_week_data.py`, `scripts/generate_franchise_wings.py:294-301`;
create `scripts/tests/test_no_prose_in_generated.py`

- [ ] **Step 1: Write the failing test**

```python
import glob, json

def test_week_packets_carry_no_prose():
    for fp in glob.glob("content/weeks/week*_data.json"):
        b = json.dumps(json.load(open(fp, encoding="utf-8")))
        assert '"essay_snippet"' not in b and '"roast"' not in b, fp

def test_franchise_wings_carry_no_prose():
    for fp in glob.glob("data/franchises/*.json"):
        if fp.endswith("_index.json"):
            continue
        assert '"roast"' not in json.dumps(json.load(open(fp, encoding="utf-8"))), fp
```

- [ ] **Step 2: Run to verify it fails** → both

- [ ] **Step 3: Remove `essay_snippet`/`roast` from `team_profiles_summary`; delete `"roast"`
      from `voice_bible_callbacks`.**

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

## Phase B — Repair, compiler, real audit

### Task B1: Cutoff-sliced H2H

**Files:** Create `scripts/as_of_records.py`, `scripts/tests/test_as_of_records.py`

Verified `entry` shape: `{"games":[{"season","week","pts","opp_pts"}],"wins","losses","pf","pa"}`
oriented to the first owner id in `oid1|oid2`.

- [ ] **Step 1: Write the failing test**

```python
from scripts.as_of_records import slice_h2h

ENTRY = {"games": [{"season": 2022, "week": 9, "pts": 140.3, "opp_pts": 153.12},
                   {"season": 2025, "week": 6, "pts": 109.1, "opp_pts": 150.46},
                   {"season": 2025, "week": 12, "pts": 180.0, "opp_pts": 100.0}],
         "wins": 1, "losses": 2}

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
    assert slice_h2h(ENTRY, 2021, 1, inclusive=True)["last_meeting"] is None
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Cutoff-correct league records and H2H. All reads go through SOURCE_ROOT."""
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT                      # injectable; tests point this at a fixture corpus


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
                              "score": f"{last['pts']}-{last['opp_pts']}"} if last else None)}
```

- [ ] **Step 4: Run** → 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/as_of_records.py scripts/tests/test_as_of_records.py
git commit -m "feat(asof): cutoff-sliced H2H via injectable SOURCE_ROOT"
```

---

### Task B2: Records including undated aggregates

Verified: `longest_losing_streak` = 8 / 9 / 10 through 2024, 2025 wk1, 2025 wk2.
`longest_win_streak` = 11 at every cutoff — accidentally safe, still recomputed.

**Files:** Modify `scripts/as_of_records.py`, `scripts/tests/test_as_of_records.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.as_of_records import as_of_records

def test_losing_streak_recomputed():
    assert as_of_records(2024, 99)["longest_losing_streak"]["count"] == 8
    assert as_of_records(2025, 1)["longest_losing_streak"]["count"] == 9
    assert as_of_records(2025, 2)["longest_losing_streak"]["count"] == 10

def test_win_streak_stable_but_recomputed():
    for s, w in [(2024, 99), (2025, 1), (2025, 17)]:
        assert as_of_records(s, w)["longest_win_streak"]["count"] == 11

def test_dated_records_never_postdate_cutoff():
    for k, v in as_of_records(2025, 1).items():
        if isinstance(v, dict) and v.get("season") is not None:
            assert (v["season"], v.get("week") or 0) <= (2025, 1), k

def test_all_seven_keys():
    assert set(as_of_records(2025, 5)) == {
        "highest_score", "lowest_winning_score", "biggest_blowout", "highest_combined",
        "lowest_combined", "longest_win_streak", "longest_losing_streak"}
```

- [ ] **Step 2: Run to verify it fails** → `ImportError`

- [ ] **Step 3: Implement** — mirrors `fetch_sleeper.py:741-775` and `:962-1002`; streaks skip
      playoff games, dated records do not. `load_all_games` globs
      `SOURCE_ROOT / "data" / "*" / "season_combined.json"` (not `ROOT`), which is what makes the
      truncation fixture in B12 effective.

```python
def load_all_games(seasons=None):
    games = []
    for fp in sorted(glob.glob(str(SOURCE_ROOT / "data" / "*" / "season_combined.json"))):
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
                games.append({"season": int(year), "week": wd["week"],
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
            rec["biggest_blowout"] = {"margin": round(margin, 2), "winner": hi, "loser": lo,
                                      "score": f"{max(g['p1'], g['p2']):.1f}-"
                                               f"{min(g['p1'], g['p2']):.1f}",
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

- [ ] **Step 4: Run** → 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/as_of_records.py scripts/tests/test_as_of_records.py
git commit -m "feat(asof): recompute all seven records at cutoff incl. undated streaks"
```

---

### Task B3: Wire the repair; census 46 → 0

**Files:** Modify `scripts/extract_week_data.py:562-577`, `:1028`;
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
        for k in ("longest_losing_streak", "longest_win_streak"):
            assert hc[k]["count"] == exp[k]["count"], f"{fp} {k}"
```

- [ ] **Step 2: Run to verify it fails** → 45 dated; week-1 streak 10 ≠ 9

- [ ] **Step 3: Wire** — `entry["h2h"] = slice_h2h(h2h_entry, season, week_num, inclusive=True)`
      and `result["historical_context"] = as_of_records(season, week_num, inclusive=True)`.

- [ ] **Step 4: Re-extract packets AND companions in the same pass**

```bash
python scripts/extract_week_data.py --all --pretty
python scripts/generate_expanded_week.py            # bare run covers weeks 1-18
python -m pytest scripts/tests/test_packet_cutoff_clean.py -v
python -m pytest scripts/tests/ -q
```

`generate_expanded_week.py` accepts only `--week` (default: all 1-18) and `--season`.
`c5b6b50` regenerated week data without companions and left 32 season-end Elo values leaking.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_week_data.py content/weeks/ data/2025/nfl_games/_expanded_manifest.json scripts/tests/test_packet_cutoff_clean.py
git commit -m "fix(data): cutoff-slice h2h, recompute records -- 46 leaks to zero"
```

---

### Task B4: `verify_h2h_claims` becomes an error

The comparison is reachable only when the **ranking entry** carries `team_name`
(`verify_week_content.py:917`, guarded `:927`/`:946`).

**Files:** Modify `scripts/verify_week_content.py:892-949`, its test file

- [ ] **Step 1: Write the failing test**

```python
from scripts.verify_week_content import verify_h2h_claims

DATA = {"matchups": [{"team1": {"team_name": "Alpha"}, "team2": {"team_name": "Beta"},
                      "h2h": {"team1_wins": 1, "team2_wins": 1, "total_games": 2}}]}

def test_wrong_claim_is_error():
    e, w = [], []
    verify_h2h_claims({"rankings": [{"rank": 1, "team_name": "Alpha",
                                     "blurb": "You are 9-0 all-time against them."}]},
                      DATA, e, w)
    assert e

def test_correct_claim_no_error():
    e, w = [], []
    verify_h2h_claims({"rankings": [{"rank": 1, "team_name": "Alpha",
                                     "blurb": "You are 1-1 all-time against them."}]},
                      DATA, e, w)
    assert not e
```

- [ ] **Step 2: Run to verify it fails** → lands in `warnings`

- [ ] **Step 3: Change `warnings.append` → `errors.append` at `:946-950`.**

- [ ] **Step 4: Run suite.** Weeks 1-6 may now fail — **expected; they are filler being
      replaced. Do not repair their prose.**

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_week_content.py scripts/tests/test_verify_week_content.py
git commit -m "fix(verify): H2H mismatches are errors; test reaches the branch"
```

---

### Task B5: Leaf audit — complete registry for BOTH kinds, with a CLI

**Files:** Create `scripts/cutoff_audit.py`, `content/governance/writer_fields.json`,
`scripts/tests/test_cutoff_audit.py`

- [ ] **Step 1: Write the failing test**

```python
import glob, json
from scripts.cutoff_audit import audit_object, classify, load_registry

REG = load_registry()

def test_registry_covers_both_kinds():
    assert {"week_packet", "edition_bundle"} <= set(REG)

def test_unknown_field_fails_closed():
    r = audit_object(REG, "week_packet", {"essay": "x", "surprise": {"z": 1}})
    assert not r["ok"] and any("/surprise/z" in u for u in r["unclassified"])

def test_present_forbidden_leaf_fails():
    reg = {"week_packet": {"forbidden": ["/secret/*"], "static-legal": ["/a"]}}
    r = audit_object(reg, "week_packet", {"a": 1, "secret": {"x": 2}})
    assert not r["ok"] and r["forbidden_present"]

def test_every_week_packet_leaf_classified():
    for fp in glob.glob("content/weeks/week*_data.json"):
        r = audit_object(REG, "week_packet", json.load(open(fp, encoding="utf-8")))
        assert r["ok"], f"{fp}: {r['unclassified'][:5]}"

def test_undated_aggregate_not_static_legal():
    assert classify(REG, "week_packet",
                    "/historical_context/longest_losing_streak/count") == "cutoff-filtered"

def test_equal_specificity_conflict_fails_closed():
    bad = {"week_packet": {"static-legal": ["/x/*"], "cutoff-filtered": ["/x/*"]}}
    assert not audit_object(bad, "week_packet", {"x": {"y": 1}})["ok"]
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Write the registry — both kinds, explicitly**

```json
{
  "version": 1,
  "week_packet": {
    "static-legal": [
      "/meta/season",
      "/meta/type",
      "/season_context/total_weeks"
    ],
    "cutoff-filtered": [
      "/meta/week",
      "/matchups/*/h2h/*",
      "/matchups/*/h2h/last_meeting/*",
      "/historical_context/*/*",
      "/standings/*/*",
      "/previous_weeks_summary/*/*",
      "/season_context/*",
      "/awards/*/*",
      "/matchups/*/*",
      "/next_matchups/*/*",
      "/team_profiles_summary/*/*"
    ],
    "forbidden": []
  },
  "edition_bundle": {
    "static-legal": [
      "/descriptor_id",
      "/name_repertoires/version",
      "/name_repertoires/owners/*/handle",
      "/name_repertoires/owners/*/team",
      "/name_repertoires/owners/*/first",
      "/name_repertoires/owners/*/surname",
      "/name_repertoires/owners/*/roster_id",
      "/name_repertoires/owners/*/register_notes",
      "/draft/*/*",
      "/source_identities/*/*"
    ],
    "cutoff-filtered": [
      "/records/*/*",
      "/h2h/*/*",
      "/h2h/*/last_meeting/*",
      "/rosters/*/players/*",
      "/pairings/*/*",
      "/standings/*/*",
      "/results/*/*/*",
      "/results/*/*",
      "/player_game_context/*/*",
      "/chat/*/*",
      "/chat/*/*/*",
      "/prior_editions/*/*",
      "/prior_editions/*/*/*",
      "/media_candidates/*/*",
      "/name_repertoires/owners/*/observed/*/*",
      "/unavailable/*/*"
    ],
    "forbidden": [
      "/team_profiles_summary/*/essay_snippet",
      "/team_profiles_summary/*/roast",
      "/*/voice_bible_callbacks/*"
    ]
  }
}
```

- [ ] **Step 4: Implement** (`leaf_pointers`, `classify` with equal-specificity conflict,
      `audit_object` returning `ok`/`unclassified`/`forbidden_present`, and a `main()` CLI
      auditing `content/weeks/week*_data.json` as `week_packet` and
      `content/editions/*/bundle.json` as `edition_bundle`, exiting 1 on any failure).

```python
def audit_object(reg, kind, obj):
    unclassified, forbidden = [], []
    for ptr in sorted(set(leaf_pointers(obj))):
        try:
            cls = classify(reg, kind, ptr)
        except ValueError as exc:
            unclassified.append(str(exc)); continue
        if cls is None:
            unclassified.append(ptr)
        elif cls == "forbidden":
            forbidden.append(ptr)
    return {"ok": not unclassified and not forbidden,
            "unclassified": unclassified, "forbidden_present": forbidden}
```

- [ ] **Step 5: Run** → 6 passed; `python scripts/cutoff_audit.py --all` exits 0

- [ ] **Step 6: Commit**

```bash
git add scripts/cutoff_audit.py content/governance/writer_fields.json scripts/tests/test_cutoff_audit.py
git commit -m "feat(audit): complete registry for week packets and edition bundles"
```

---

### Task B6: Controls that reach the shipped rejection path

The prior controls compared a planted value with `as_of_records` **inside the test** — that proves
arithmetic, not that the system rejects anything. These drive the shipped audit and CLI.

**Files:** Create `scripts/tests/test_audit_positive_controls.py`

- [ ] **Step 1: Write the test**

```python
import copy, json, subprocess, sys
from scripts.cutoff_audit import audit_object, load_registry

REG = load_registry()

def _bundle():
    return json.load(open("content/editions/2025-wk01-recap/bundle.json", encoding="utf-8"))

def test_unknown_field_rejected_by_shipped_audit():
    b = copy.deepcopy(_bundle()); b["brand_new_block"] = {"leak": 1}
    r = audit_object(REG, "edition_bundle", b)
    assert not r["ok"] and any("brand_new_block" in u for u in r["unclassified"])

def test_planted_forbidden_leaf_rejected_by_shipped_audit():
    b = copy.deepcopy(_bundle())
    b.setdefault("team_profiles_summary", {})["x"] = {"roast": "you stink"}
    r = audit_object(REG, "edition_bundle", b)
    assert not r["ok"] and r["forbidden_present"]

def test_planted_dated_leak_rejected_via_cli(tmp_path):
    b = copy.deepcopy(_bundle())
    b["records"]["highest_combined"] = {"points": 999.0, "teams": "X vs Y",
                                        "score": "1-2", "season": 2025, "week": 14,
                                        "planted_marker": True}     # unclassified leaf
    p = tmp_path / "leaky.json"; p.write_text(json.dumps(b), encoding="utf-8")
    r = subprocess.run([sys.executable, "scripts/cutoff_audit.py",
                        "--path", str(p), "--kind", "edition_bundle"],
                       capture_output=True, text=True)
    assert r.returncode == 1, "shipped CLI must reject the leaky bundle"

def test_planted_undated_leak_rejected_via_cli(tmp_path):
    b = copy.deepcopy(_bundle())
    b["records"]["longest_losing_streak"] = {"count": 10, "team": "Noble FFT",
                                             "owner_id": "x", "season_end_value": True}
    p = tmp_path / "leaky2.json"; p.write_text(json.dumps(b), encoding="utf-8")
    r = subprocess.run([sys.executable, "scripts/cutoff_audit.py",
                        "--path", str(p), "--kind", "edition_bundle"],
                       capture_output=True, text=True)
    assert r.returncode == 1

def test_clean_bundle_passes_cli():
    r = subprocess.run([sys.executable, "scripts/cutoff_audit.py", "--all"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
```

- [ ] **Step 2: Run** → 5 passed (run after B11 so a real bundle exists)

- [ ] **Step 3: Commit**

```bash
git add scripts/tests/test_audit_positive_controls.py
git commit -m "test(audit): controls drive the shipped audit and its CLI exit code"
```

---

### Task B7: Edition identity

**Files:** Create `scripts/edition.py`, `scripts/tests/test_edition.py`

**Interfaces:** `EditionDescriptor`, `payload_hash`, `bundle_manifest`, `authoring_manifest`,
`build_identity`

`EditionDescriptor` now declares its predecessors explicitly — globbing published editions lets a
rebuild admit its own future.

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.edition import (EditionDescriptor, bundle_manifest, authoring_manifest,
                             payload_hash, build_identity)

D = EditionDescriptor("2025-wk01-recap", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1",
                      predecessors=[{"edition_id": "2025-wk01-preview",
                                     "authoring_manifest_sha256": "sha256:aa",
                                     "cutoff_utc": "2025-09-04T23:19:59Z"}])

def test_hash_order_invariant():
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})

def test_bundle_manifest_not_self_referential():
    bm = bundle_manifest(D, {"src": "sha256:aa"}, "code-v1", {"x": 1})
    assert bm["bundle_payload_sha256"] == payload_hash({"x": 1})
    assert "bundle_manifest_sha256" not in bm

def test_bundle_manifest_carries_declared_predecessors():
    bm = bundle_manifest(D, {}, "code-v1", {})
    assert bm["descriptor"]["predecessors"][0]["edition_id"] == "2025-wk01-preview"

def test_authoring_manifest_has_no_media_and_binds_ranking():
    bm = bundle_manifest(D, {}, "code-v1", {})
    am = authoring_manifest(bm, ["sha256:aa"], {"voice": "voice-v1"},
                            {"essay": "e"}, {"entries": [1]})
    assert "media_manifest_sha256" not in am
    assert am["ranking_record_sha256"] == payload_hash({"entries": [1]})

def test_build_identity_excludes_final_hashes():
    assert "sha256" not in json.dumps(build_identity(D, "code-v1"))
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Edition identity: descriptor, build identity, bundle and authoring manifests."""
import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class EditionDescriptor:
    edition_id: str
    season: int
    kind: str                       # preseason | preview | recap | finale
    cutoff_utc: str
    results_through_week: int
    policy_version: str
    predecessors: tuple = ()        # [{edition_id, authoring_manifest_sha256, cutoff_utc}]


def payload_hash(obj) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def build_identity(descriptor, projection_code_version):
    return {"edition_id": descriptor.edition_id, "cutoff_utc": descriptor.cutoff_utc,
            "projection_code_version": projection_code_version}


def bundle_manifest(descriptor, source_hashes, projection_code_version, payload):
    d = asdict(descriptor)
    d["predecessors"] = [dict(p) for p in descriptor.predecessors]
    return {"descriptor": d,
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

- [ ] **Step 4: Run** → 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/edition.py scripts/tests/test_edition.py
git commit -m "feat(edition): declared predecessors; non-circular manifests"
```

---

### Task B8: Kickoff instant with real timezone conversion

`nfl_game.schema.json:31` states `kickoff` is a **local time-of-day, not ISO8601 — combine with
stadium timezone**. Appending `Z` turns a 20:20 ET kickoff into 20:20 UTC.

**Files:** Create `scripts/kickoff_source.py`, `content/governance/venue_timezones.json`,
`scripts/tests/test_kickoff_source.py`

**Interfaces:** `first_kickoff_instant(season) -> dict` with `instant_utc` and `source_hashes`;
`strictly_before(instant, seconds)`; `UnavailableEvidence`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.kickoff_source import (first_kickoff_instant, strictly_before,
                                    UnavailableEvidence, to_utc)

def test_local_time_is_converted_not_suffixed():
    # 20:20 America/New_York on 2025-09-04 is 00:20Z the NEXT day.
    assert to_utc("2025-09-04", "20:20", "America/New_York") == "2025-09-05T00:20:00Z"
    assert to_utc("2025-09-04", "20:20", "America/New_York") != "2025-09-04T20:20:00Z"

def test_missing_timezone_fails_closed():
    with pytest.raises(UnavailableEvidence):
        to_utc("2025-09-04", "20:20", None)

def test_result_carries_every_source_hash():
    try:
        out = first_kickoff_instant(2025)
    except UnavailableEvidence:
        pytest.skip("schedule parquet absent; run scripts/fetch_nflreadpy.py first")
    assert out["instant_utc"].endswith("Z")
    assert len(out["source_hashes"]) >= 2      # schedule + timezone map
    assert all(v.startswith("sha256:") for v in out["source_hashes"].values())

def test_missing_schedule_fails_closed(monkeypatch):
    monkeypatch.setattr("scripts.kickoff_source.SCHEDULE_PATH",
                        __import__("pathlib").Path("does/not/exist.parquet"))
    with pytest.raises(UnavailableEvidence):
        first_kickoff_instant(2025)

def test_strictly_before_is_strictly_before():
    assert strictly_before("2025-09-05T00:20:00Z") == "2025-09-05T00:19:59Z"
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Qualify the first-kickoff instant. Never manufacture UTC by appending Z."""
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_PATH = ROOT / "data" / "external" / "schedules_2025.parquet"
TZ_MAP_PATH = ROOT / "content" / "governance" / "venue_timezones.json"


class UnavailableEvidence(RuntimeError):
    """A cutoff that cannot be qualified is unavailable. Never guessed."""


def _sha(p):
    return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()


def to_utc(gameday, gametime, tzname):
    if not tzname:
        raise UnavailableEvidence(
            f"no timezone for kickoff {gameday} {gametime}; the schema states gametime is a "
            "local time-of-day that must be combined with venue timezone")
    local = datetime.strptime(f"{gameday} {gametime}", "%Y-%m-%d %H:%M").replace(
        tzinfo=ZoneInfo(tzname))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def first_kickoff_instant(season):
    if not SCHEDULE_PATH.exists():
        raise UnavailableEvidence(
            f"{SCHEDULE_PATH} absent -- run `python scripts/fetch_nflreadpy.py`. "
            "A preview cutoff may not be hard-coded or inferred.")
    if not TZ_MAP_PATH.exists():
        raise UnavailableEvidence(f"{TZ_MAP_PATH} absent; cannot convert local kickoffs")
    import json
    import polars as pl
    tzmap = json.loads(TZ_MAP_PATH.read_text(encoding="utf-8"))["by_team"]
    df = pl.read_parquet(SCHEDULE_PATH).filter(
        (pl.col("season") == season) & (pl.col("week") == 1))
    instants = []
    for row in df.iter_rows(named=True):
        gd, gt, home = row.get("gameday"), row.get("gametime"), row.get("home_team")
        if not (gd and gt):
            continue
        instants.append(to_utc(gd, gt, tzmap.get(home)))
    if not instants:
        raise UnavailableEvidence(f"no qualified week-1 kickoff for {season}")
    return {"instant_utc": min(instants),
            "source_hashes": {"schedules": _sha(SCHEDULE_PATH),
                              "venue_timezones": _sha(TZ_MAP_PATH)}}


def strictly_before(instant_utc, seconds=1):
    dt = datetime.fromisoformat(instant_utc.replace("Z", "+00:00"))
    return (dt - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
```

`content/governance/venue_timezones.json` maps every NFL home team abbreviation to an IANA zone
(`{"by_team": {"PHI": "America/New_York", ...}}`). A team absent from the map raises
`UnavailableEvidence` rather than defaulting.

**Note on runtime:** `import polars` was verified working on this machine (`polars 1.40.1`). No
`sse3` workaround is included; if that error ever appears, it is a fresh finding, not a known
condition.

- [ ] **Step 4: Run** → 5 passed (the schedule test skips cleanly when the parquet is absent)

- [ ] **Step 5: Commit**

```bash
git add scripts/kickoff_source.py content/governance/venue_timezones.json scripts/tests/test_kickoff_source.py
git commit -m "feat(cutoff): real timezone conversion for kickoff; hash every source"
```

---

### Task B9: Season-qualified adapters that declare their sources

Every adapter returns `(payload, source_identities)`. Reads go through `SOURCE_ROOT`. **The chat
adapter projects at the descriptor's exact cutoff and never reuses
`week1_chat_context.json`** — that file declares cutoff `2025-09-09T06:59:59Z` and holds 28
result statements.

**Files:** Create `scripts/project_edition.py`, `scripts/tests/test_project_edition.py`

**Interfaces:** `project(descriptor) -> dict`, `reconstruct_roster(season, cutoff_utc)`,
`adapter_for(name)`, `REQUIRED_BY_KIND`, `SOURCE_ROOT`, `effective_instant`

- [ ] **Step 1: Write the failing test**

```python
import json
import pytest
from scripts.edition import EditionDescriptor
from scripts.project_edition import (project, reconstruct_roster, adapter_for,
                                     REQUIRED_BY_KIND, effective_instant)
from scripts.kickoff_source import UnavailableEvidence

PREVIEW = EditionDescriptor("p", 2025, "preview", "2025-09-04T23:19:59Z", 0, "v1")
RECAP = EditionDescriptor("r", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1")

def test_every_required_source_present_or_unavailable():
    for d in (PREVIEW, RECAP):
        b = project(d)
        un = {u["source"] for u in b["unavailable"]}
        for name in REQUIRED_BY_KIND[d.kind]:
            assert name in b and (b[name] is not None or name in un), name

def test_every_component_declares_source_identity():
    b = project(RECAP)
    for name in REQUIRED_BY_KIND["recap"]:
        if b[name] is not None:
            assert name in b["source_identities"], f"{name} declared no source identity"

def test_preview_chat_excludes_post_kickoff_results():
    b = project(PREVIEW)
    blob = json.dumps(b["chat"] or {})
    for phrase in ("low scorer this week", "won by", "high scorer this week"):
        assert phrase not in blob, f"preview chat contains hindsight: {phrase}"

def test_preview_chat_declares_the_descriptor_cutoff():
    b = project(PREVIEW)
    assert (b["chat"] or {}).get("meta", {}).get("temporal_cutoff_utc") == PREVIEW.cutoff_utc

def test_preview_has_no_week1_outcomes():
    b = project(PREVIEW)
    for p in b["pairings"]:
        assert "points1" not in p and "winner" not in p
    assert all(s["record"] == "0-0" for s in b["standings"])

def test_preview_roster_excludes_post_kickoff_add():
    r = reconstruct_roster(2025, "2025-09-04T23:19:59Z")
    assert "6949" not in [str(p) for p in r.get("6", {}).get("players", [])]

def test_missing_effective_instant_is_unavailable():
    with pytest.raises(UnavailableEvidence):
        effective_instant({"created": 1725000000000})

def test_season_mismatch_fails_closed():
    d2024 = EditionDescriptor("c", 2024, "recap", "2024-09-10T06:59:59Z", 1, "v1")
    b = project(d2024)
    un = {u["source"] for u in b["unavailable"]}
    for name in ("pairings", "standings", "results", "player_game_context"):
        if b.get(name) is not None:
            assert b["source_identities"][name]["season"] == 2024, \
                f"{name} served a non-2024 source to a 2024 descriptor"
        else:
            assert name in un

def test_unregistered_adapter_fails_closed():
    with pytest.raises(KeyError):
        adapter_for("speculative_d2_source")
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""The projector. Sole trusted reader; every read goes through SOURCE_ROOT."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import as_of_records as aor  # noqa: E402
from kickoff_source import UnavailableEvidence  # noqa: E402
from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT                       # injectable; B12 points this at a truncated corpus

REQUIRED_BY_KIND = {
    "preseason": ["records", "h2h", "rosters", "draft", "chat", "name_repertoires",
                  "media_candidates"],
    "preview": ["records", "h2h", "rosters", "draft", "pairings", "standings", "chat",
                "prior_editions", "name_repertoires", "media_candidates"],
    "recap": ["records", "h2h", "rosters", "draft", "pairings", "standings", "results",
              "player_game_context", "chat", "prior_editions", "name_repertoires",
              "media_candidates"],
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


def _sd(season):
    return SOURCE_ROOT / "data" / str(season)


def _weekly(season, week, suffix):
    """Season-qualified weekly packet. The seasonless content/weeks/ path is 2025-only."""
    p = SOURCE_ROOT / "content" / "seasons" / str(season) / "weeks" / f"week{week}{suffix}"
    if not p.exists():
        raise UnavailableEvidence(
            f"{p} absent: no season-{season} weekly artifact. The legacy "
            f"content/weeks/week{week}{suffix} declares season 2025 and may not serve "
            f"a season-{season} descriptor.")
    return p


def effective_instant(txn):
    ms = txn.get("status_updated")
    if ms is None:
        raise UnavailableEvidence(
            f"transaction {txn.get('transaction_id')} has no status_updated; "
            "`created` is NOT an acceptable fallback")
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def reconstruct_roster(season, cutoff_utc):
    cutoff = datetime.fromisoformat(cutoff_utc.replace("Z", "+00:00"))
    base = load_json(_sd(season) / "rosters.json", required=True)
    rosters = {str(r["roster_id"]): {"players": list(r.get("players") or [])} for r in base}
    txns = load_json(_sd(season) / "transactions.json", required=True)
    events = [(effective_instant(t), t) for leg in sorted(txns, key=int)
              for t in txns[leg] if t.get("status") == "complete"]
    for when, t in sorted(events, key=lambda e: e[0], reverse=True):
        if when <= cutoff:
            break
        for pid, rid in (t.get("adds") or {}).items():
            pl = rosters.get(str(rid), {}).get("players", [])
            if pid in pl:
                pl.remove(pid)
        for pid, rid in (t.get("drops") or {}).items():
            rosters.setdefault(str(rid), {"players": []})["players"].append(pid)
    return rosters


def _ident(season, path, extra=None):
    import hashlib
    p = Path(path)
    out = {"season": season, "path": str(p.relative_to(SOURCE_ROOT)),
           "sha256": "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()}
    if extra:
        out.update(extra)
    return out


@adapter("records")
def _records(d):
    return (aor.as_of_records(d.season, d.results_through_week,
                              inclusive=(d.kind != "preview")),
            {"season": d.season, "derived_from": "season_combined", "cutoff": d.cutoff_utc})


@adapter("h2h")
def _h2h(d):
    p = SOURCE_ROOT / "data" / "league_history.json"
    hist = load_json(p, required=True)
    return ({k: aor.slice_h2h(v, d.season, d.results_through_week,
                              inclusive=(d.kind != "preview"))
             for k, v in (hist.get("h2h") or {}).items()},
            _ident(d.season, p))


@adapter("rosters")
def _rosters(d):
    return reconstruct_roster(d.season, d.cutoff_utc), _ident(d.season, _sd(d.season) / "rosters.json")


@adapter("draft")
def _draft(d):
    p = _sd(d.season) / "draft_picks.json"
    return load_json(p, required=True), _ident(d.season, p)


@adapter("pairings")
def _pairings(d):
    wk = max(d.results_through_week, 1)
    p = _weekly(d.season, wk, "_data.json")
    packet = load_json(p, required=True)
    out = []
    for m in packet.get("matchups", []):
        pair = {"team1": m["team1"]["team_name"], "team2": m["team2"]["team_name"]}
        if d.kind != "preview":
            pair.update({"points1": m["team1"]["points"], "points2": m["team2"]["points"],
                         "winner": m.get("winner")})
        out.append(pair)
    return out, _ident(d.season, p)


@adapter("standings")
def _standings(d):
    if d.kind == "preview":
        p = _sd(d.season) / "users.json"
        users = load_json(p, required=True)
        return ([{"team_name": (u.get("metadata") or {}).get("team_name") or u["display_name"],
                  "record": "0-0"} for u in users], _ident(d.season, p))
    p = _weekly(d.season, d.results_through_week, "_data.json")
    return load_json(p, required=True)["standings"], _ident(d.season, p)


@adapter("results")
def _results(d):
    p = _weekly(d.season, d.results_through_week, "_data.json")
    packet = load_json(p, required=True)
    return {"matchups": packet["matchups"], "awards": packet.get("awards")}, _ident(d.season, p)


@adapter("player_game_context")
def _pgc(d):
    p = _weekly(d.season, d.results_through_week, "_data_expanded.json")
    return load_json(p, required=True).get("games", {}), _ident(d.season, p)


@adapter("chat")
def _chat(d):
    """Project chat AT THE DESCRIPTOR CUTOFF. Never reuse a recap-cutoff artifact."""
    import subprocess
    out = SOURCE_ROOT / "content" / "editions" / d.edition_id / "_chat_projection.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_chat_context.py"),
                        "--season", str(d.season), "--cutoff-utc", d.cutoff_utc,
                        "--out", str(out), "--no-ai"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise UnavailableEvidence(f"chat projection failed at {d.cutoff_utc}: {r.stderr[:200]}")
    ctx = load_json(out, required=True)
    got = (ctx.get("meta") or {}).get("temporal_cutoff_utc")
    if got != d.cutoff_utc:
        raise UnavailableEvidence(
            f"chat projection declares cutoff {got}, descriptor requires {d.cutoff_utc}")
    return ctx, _ident(d.season, out, {"cutoff": d.cutoff_utc})


@adapter("prior_editions")
def _prior(d):
    """Only DECLARED predecessors. Globbing lets a rebuild admit its own future."""
    out, idents = [], []
    for pred in d.predecessors:
        ed = SOURCE_ROOT / "content" / "editions" / pred["edition_id"]
        am = ed / "authoring_manifest.json"
        if not am.exists():
            raise UnavailableEvidence(f"declared predecessor {pred['edition_id']} not authored")
        if pred["cutoff_utc"] >= d.cutoff_utc:
            raise UnavailableEvidence(
                f"predecessor {pred['edition_id']} cutoff {pred['cutoff_utc']} is not before "
                f"{d.cutoff_utc}")
        import hashlib
        actual = "sha256:" + hashlib.sha256(am.read_bytes()).hexdigest()
        if actual != pred["authoring_manifest_sha256"]:
            raise UnavailableEvidence(
                f"predecessor {pred['edition_id']} manifest hash mismatch")
        out.append({"edition_id": pred["edition_id"],
                    "ranking_record": load_json(ed / "ranking_record.json", required=True),
                    "content": load_json(ed / "content.json", required=True)})
        idents.append({"edition_id": pred["edition_id"], "sha256": actual})
    return out, {"season": d.season, "predecessors": idents}


@adapter("name_repertoires")
def _names(d):
    p = SOURCE_ROOT / "content" / "chat" / "name-repertoires.json"
    return load_json(p, required=True), _ident(d.season, p)


@adapter("media_candidates")
def _media(d):
    """Cutoff-projected rebound catalog. Without this the picker has no authorized source."""
    p = SOURCE_ROOT / "content" / "chat" / "media-catalog-rebound.json"
    if not p.exists():
        raise UnavailableEvidence("rebound media catalog absent; league media unavailable")
    cat = load_json(p, required=True)
    eligible = [e for e in cat["entries"]
                if e["timestamp_utc"] <= d.cutoff_utc and "personal" not in e["tags"]]
    return eligible, _ident(d.season, p, {"cutoff": d.cutoff_utc,
                                          "eligible": len(eligible),
                                          "total": len(cat["entries"])})


def project(descriptor):
    payload, unavailable, idents = {}, [], {}
    for name in REQUIRED_BY_KIND[descriptor.kind]:
        try:
            value, ident = adapter_for(name)(descriptor)
            payload[name] = value
            idents[name] = ident
        except (UnavailableEvidence, FileNotFoundError) as exc:
            payload[name] = None
            unavailable.append({"source": name, "reason": str(exc)})
    payload["unavailable"] = unavailable
    payload["source_identities"] = idents
    payload["descriptor_id"] = descriptor.edition_id
    return payload
```

**Prerequisite:** `build_chat_context.py` gains `--cutoff-utc` and `--out`. Its existing
`--week`-driven cutoff derivation stays for legacy use; the projector always passes an explicit
instant.

**Prerequisite:** season-qualified weekly artifacts. Move/copy the 2025 packets to
`content/seasons/2025/weeks/` (the legacy `content/weeks/` path stays for the existing site
pages). A 2024 descriptor finds nothing there and correctly reports unavailable.

- [ ] **Step 4: Run** → 9 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/project_edition.py scripts/build_chat_context.py content/seasons/ scripts/tests/test_project_edition.py
git commit -m "feat(projector): season-qualified adapters, declared sources, cutoff-projected chat"
```

---

### Task B10: Desk evidence coverage

**Files:** Create `content/governance/desk_contracts.json`, `scripts/tests/test_desk_coverage.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.edition import EditionDescriptor
from scripts.project_edition import project

CONTRACTS = json.load(open("content/governance/desk_contracts.json", encoding="utf-8"))

def test_every_desk_gets_contracted_evidence_or_unavailable():
    d = EditionDescriptor("r", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1")
    b = project(d)
    un = {u["source"] for u in b["unavailable"]}
    for desk, needs in CONTRACTS["recap"].items():
        for n in needs:
            assert n in b, f"{desk} needs {n}"
            assert b[n] is not None or n in un, f"{desk}: {n} silently None"
```

- [ ] **Step 2: Run to verify it fails** → file missing

- [ ] **Step 3: Write the contracts** — culture gets `["chat", "name_repertoires",
  "media_candidates"]`; power-rankings `["records", "standings", "results",
  "prior_editions"]`; game `["player_game_context", "results"]`; history `["h2h", "records"]`;
      continuity `["prior_editions", "pairings"]`; copy-editor
      `["results", "standings", "records", "h2h"]`. Preview and preseason variants drop the
      sources their kind does not require.

- [ ] **Step 4: Run** → passes

- [ ] **Step 5: Commit**

```bash
git add content/governance/desk_contracts.json scripts/tests/test_desk_coverage.py
git commit -m "test(desks): contracted evidence present or explicitly unavailable"
```

---

### Task B11: Compiler — authoritative, non-destructive, complete hashes

The prior compiler `rmtree`'d the whole edition directory, destroying `ranking_record.json`,
`content.json`, `authoring_manifest.json`, `media_manifest.json`, and `publication.json` on any
rebuild.

**Files:** Create `scripts/compile_edition.py`, `scripts/author_edition.py`,
`scripts/tests/test_compile_edition.py`

**Interfaces:** `compile_edition(descriptor) -> Path` writing only into `<edition>/compiled/`;
`author_edition(...)` writing `authoring_manifest.json`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path
from scripts.edition import EditionDescriptor, payload_hash
from scripts.compile_edition import compile_edition, COMPILED_SUBDIR

D = EditionDescriptor("t", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1")

def test_writes_all_compile_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    out = compile_edition(D)
    for f in ("descriptor.json", "bundle.json", "bundle_manifest.json",
              "build_identity.json", "source_hashes.json"):
        assert (out / f).exists(), f
    assert out.name == COMPILED_SUBDIR

def test_rebuild_preserves_authored_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    compile_edition(D)
    authored = tmp_path / D.edition_id / "ranking_record.json"
    authored.write_text('{"entries": []}', encoding="utf-8")
    compile_edition(D)                                  # rebuild
    assert authored.exists(), "rebuild must not destroy authored artifacts"

def test_manifest_hash_matches_payload(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    out = compile_edition(D)
    assert json.loads((out / "bundle_manifest.json").read_text())["bundle_payload_sha256"] \
        == payload_hash(json.loads((out / "bundle.json").read_text()))

def test_source_hashes_cover_every_declared_component(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    out = compile_edition(D)
    bundle = json.loads((out / "bundle.json").read_text())
    sh = json.loads((out / "source_hashes.json").read_text())
    for name, ident in bundle["source_identities"].items():
        assert name in sh, f"{name} consumed but not hashed into the manifest"

def test_missing_required_source_identity_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    monkeypatch.setattr("scripts.compile_edition.REQUIRE_IDENTITY", True)
    bad = EditionDescriptor("b", 2024, "recap", "2024-09-10T06:59:59Z", 1, "v1")
    try:
        compile_edition(bad)
        assert False, "expected failure on unidentified sources"
    except Exception:
        pass

def test_clean_rebuild_byte_identical(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    a = (compile_edition(D) / "bundle.json").read_bytes()
    shutil.rmtree(tmp_path / D.edition_id / COMPILED_SUBDIR)
    b = (compile_edition(D) / "bundle.json").read_bytes()
    assert a == b
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""Compile one edition into a compiler-owned subdirectory. Authored files are untouched."""
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
COMPILED_SUBDIR = "compiled"
CODE_VERSION = "projector-v1"
REQUIRE_IDENTITY = True


def compile_edition(descriptor):
    if descriptor.kind not in REQUIRED_BY_KIND:
        raise ValueError(f"unknown edition kind: {descriptor.kind}")
    edition_dir = EDITIONS_ROOT / descriptor.edition_id
    final = edition_dir / COMPILED_SUBDIR
    staging = edition_dir / f".{COMPILED_SUBDIR}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        payload = project(descriptor)
        idents = payload["source_identities"]
        if REQUIRE_IDENTITY:
            missing = [n for n in REQUIRED_BY_KIND[descriptor.kind]
                       if payload.get(n) is not None and n not in idents]
            if missing:
                raise ValueError(f"components without source identity: {missing}")
        # Aggregate EVERY consumed source, not a hard-coded shortlist.
        sources = {name: ident for name, ident in idents.items()}
        sources["_code"] = {
            "project_edition.py": _sha(ROOT / "scripts" / "project_edition.py"),
            "as_of_records.py": _sha(ROOT / "scripts" / "as_of_records.py"),
        }
        for pred in descriptor.predecessors:
            sources[f"_predecessor:{pred['edition_id']}"] = {
                "authoring_manifest_sha256": pred["authoring_manifest_sha256"],
                "cutoff_utc": pred["cutoff_utc"]}
        mf = bundle_manifest(descriptor, {k: str(v) for k, v in sources.items()},
                             CODE_VERSION, payload)
        save_json_canonical(staging / "descriptor.json", asdict(descriptor))
        save_json_canonical(staging / "bundle.json", payload)
        save_json_canonical(staging / "bundle_manifest.json", mf)
        save_json_canonical(staging / "build_identity.json",
                            build_identity(descriptor, CODE_VERSION))
        save_json_canonical(staging / "source_hashes.json", sources)
        if final.exists():
            shutil.rmtree(final)          # ONLY the compiled subdir
        staging.rename(final)
        return final
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _sha(p):
    import hashlib
    return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    import argparse, json as _j
    from edition import EditionDescriptor
    ap = argparse.ArgumentParser()
    ap.add_argument("--descriptor", required=True)
    a = ap.parse_args()
    raw = _j.load(open(a.descriptor, encoding="utf-8"))
    raw["predecessors"] = tuple(raw.get("predecessors", ()))
    print(compile_edition(EditionDescriptor(**raw)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the executable authoring step** — `scripts/author_edition.py`:

```python
"""Bind bundle manifest + predecessors + rule versions + content + ranking into the
authoring manifest. This is what editorial approval binds."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edition import authoring_manifest  # noqa: E402
from shared import load_json, save_json_canonical  # noqa: E402


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", required=True)
    ap.add_argument("--voice-rule-version", required=True)
    a = ap.parse_args()
    ed = Path(a.edition)
    bm = load_json(ed / "compiled" / "bundle_manifest.json", required=True)
    content = load_json(ed / "content.json", required=True)
    ranking = load_json(ed / "ranking_record.json", required=True)
    preds = [p["authoring_manifest_sha256"]
             for p in bm["descriptor"].get("predecessors", [])]
    am = authoring_manifest(bm, preds, {"voice": a.voice_rule_version}, content, ranking)
    save_json_canonical(ed / "authoring_manifest.json", am)
    print(json.dumps(am, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run** → 6 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/compile_edition.py scripts/author_edition.py scripts/tests/test_compile_edition.py
git commit -m "feat(compile): compiler-owned subdir, full source aggregation, authoring step"
```

---

### Task B12: Real temporal isolation and a season-isolating canary

**Files:** Create `scripts/tests/test_noninterference.py`, `scripts/tests/fixtures/truncate.py`

- [ ] **Step 1: Write the test**

```python
import json, shutil
from pathlib import Path
import pytest
from scripts.edition import EditionDescriptor
from scripts.compile_edition import compile_edition, COMPILED_SUBDIR
from scripts.tests.fixtures.truncate import build_truncated_root

REC = EditionDescriptor("ni", 2025, "recap", "2025-09-09T06:59:59Z", 1, "v1")


def _compile_against(root, editions_root, monkeypatch, descriptor=REC):
    monkeypatch.setattr("scripts.project_edition.SOURCE_ROOT", root)
    monkeypatch.setattr("scripts.as_of_records.SOURCE_ROOT", root)
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", editions_root)
    return (compile_edition(descriptor) / "bundle.json").read_bytes()


def test_full_vs_physically_truncated_is_byte_identical(tmp_path, monkeypatch):
    """Rows AFTER the cutoff are physically removed from the truncated corpus."""
    full = Path(".")
    truncated = build_truncated_root(tmp_path / "trunc", cutoff_season=2025, cutoff_week=1)
    a = _compile_against(full, tmp_path / "ea", monkeypatch)
    b = _compile_against(truncated, tmp_path / "eb", monkeypatch)
    assert a == b, "future rows influenced the bundle"


def test_positive_control_leaky_corpus_is_detected(tmp_path, monkeypatch):
    """Plant a future row; an honest gate must see a DIFFERENT bundle."""
    truncated = build_truncated_root(tmp_path / "t2", cutoff_season=2025, cutoff_week=1)
    leaky = build_truncated_root(tmp_path / "t3", cutoff_season=2025, cutoff_week=1,
                                 plant_future_week=17)
    a = _compile_against(truncated, tmp_path / "ec", monkeypatch)
    b = _compile_against(leaky, tmp_path / "ed", monkeypatch)
    assert a != b, "detector is inert: a planted future row changed nothing"


def test_planted_undated_future_evidence_is_detected(tmp_path, monkeypatch):
    truncated = build_truncated_root(tmp_path / "t4", cutoff_season=2025, cutoff_week=1)
    leaky = build_truncated_root(tmp_path / "t5", cutoff_season=2025, cutoff_week=1,
                                 plant_streak_extension=True)
    a = json.loads(_compile_against(truncated, tmp_path / "ee", monkeypatch))
    b = json.loads(_compile_against(leaky, tmp_path / "ef", monkeypatch))
    assert a["records"]["longest_losing_streak"] != b["records"]["longest_losing_streak"]


def test_canary_asserts_season_provenance_not_just_compilation(tmp_path, monkeypatch):
    canary = EditionDescriptor("canary-2024", 2024, "recap", "2024-09-10T06:59:59Z", 1, "v1")
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    out = compile_edition(canary)
    bundle = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    un = {u["source"] for u in bundle["unavailable"]}
    for name, ident in bundle["source_identities"].items():
        assert ident.get("season") == 2024, \
            f"{name} served season {ident.get('season')} to a 2024 descriptor"
    for name in ("pairings", "standings", "results", "player_game_context"):
        assert bundle[name] is None and name in un, \
            f"{name} must be unavailable for 2024 -- a 2025 packet may not serve it"


def test_2024_descriptor_consuming_a_2025_packet_fails(tmp_path, monkeypatch):
    from scripts.project_edition import _weekly
    from scripts.kickoff_source import UnavailableEvidence
    with pytest.raises(UnavailableEvidence):
        _weekly(2024, 1, "_data.json")


@pytest.mark.parametrize("edition_id", ["2025-preseason", "2025-wk01-preview",
                                        "2025-wk01-recap"])
def test_clean_rebuild_reproduces_each_real_d1_bundle(edition_id, tmp_path, monkeypatch):
    src = Path("content/editions") / edition_id / "descriptor.json"
    raw = json.loads(src.read_text(encoding="utf-8"))
    raw["predecessors"] = tuple(raw.get("predecessors", ()))
    d = EditionDescriptor(**raw)
    monkeypatch.setattr("scripts.compile_edition.EDITIONS_ROOT", tmp_path)
    a = (compile_edition(d) / "bundle.json").read_bytes()
    shutil.rmtree(tmp_path / d.edition_id / COMPILED_SUBDIR)
    b = (compile_edition(d) / "bundle.json").read_bytes()
    assert a == b
```

- [ ] **Step 2: Write the fixture builder** — `scripts/tests/fixtures/truncate.py`

```python
"""Build a source root with post-cutoff rows PHYSICALLY REMOVED."""
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def build_truncated_root(dest, cutoff_season, cutoff_week,
                         plant_future_week=None, plant_streak_extension=False):
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    for rel in ("data", "content/seasons", "content/chat", "content/editions"):
        src = REPO / rel
        if src.exists():
            shutil.copytree(src, dest / rel, dirs_exist_ok=True)

    for sc in sorted((dest / "data").glob("*/season_combined.json")):
        year = int(sc.parent.name) if sc.parent.name.isdigit() else None
        if year is None:
            continue
        data = json.loads(sc.read_text(encoding="utf-8"))
        if year > cutoff_season:
            data["weeks"] = []
        elif year == cutoff_season:
            keep = [w for w in data.get("weeks", []) if w["week"] <= cutoff_week]
            if plant_future_week:
                future = [w for w in data.get("weeks", []) if w["week"] == plant_future_week]
                keep += future                      # deliberate leak
            if plant_streak_extension:
                extra = [w for w in data.get("weeks", []) if w["week"] == cutoff_week + 1]
                keep += extra                       # extends undated streaks
            data["weeks"] = keep
        sc.write_text(json.dumps(data), encoding="utf-8")

    lh = dest / "data" / "league_history.json"
    if lh.exists():
        hist = json.loads(lh.read_text(encoding="utf-8"))
        for entry in (hist.get("h2h") or {}).values():
            entry["games"] = [g for g in entry["games"]
                              if g["season"] < cutoff_season
                              or (g["season"] == cutoff_season and g["week"] <= cutoff_week)]
        lh.write_text(json.dumps(hist), encoding="utf-8")
    return dest
```

- [ ] **Step 3: Run.** All must pass. **If `test_full_vs_physically_truncated` fails, a real leak
      exists — fix the adapter, never the test.** If the positive control passes trivially
      (`a == b` with a planted row), the detector is inert and must be fixed before D1.

- [ ] **Step 4: Commit**

```bash
git add scripts/tests/test_noninterference.py scripts/tests/fixtures/truncate.py
git commit -m "test(audit): physical truncation, planted-leak controls, season-isolating canary"
```

---

### Task B13: Rebind the catalog — resolve the protected asset root first

No media assets exist in the repository tree (verified). The protected root is an execution
dependency, not an assumption.

**Files:** Create `scripts/rebind_media_catalog.py`, `content/governance/media_roots.json`,
`scripts/tests/test_rebind_media_catalog.py`

- [ ] **Step 1: Resolve the protected root — a decision gate, not a step to skip**

Write `content/governance/media_roots.json`:

```json
{
  "version": 1,
  "protected_source_root": null,
  "authorized_publish_root": "media/",
  "note": "protected_source_root is the local, gitignored directory holding original league media. Until Blake supplies it, league media is UNAVAILABLE and the media_candidates adapter reports so."
}
```

**If Blake cannot supply a protected root, league media is unavailable for D1** — the editions
run on GIPHY and custom media only. Do not assume 1205/1205 will rebind.

- [ ] **Step 2: Write the failing test**

```python
import json
import pytest
from scripts.rebind_media_catalog import rebind, AmbiguousBinding, protected_root

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

def test_unresolved_protected_root_is_unavailable():
    cfg = json.load(open("content/governance/media_roots.json", encoding="utf-8"))
    if cfg["protected_source_root"] is None:
        with pytest.raises(FileNotFoundError):
            protected_root()

def test_binds_on_filename_and_content_hash(assets):
    e = rebind(CAT, MSGS, assets)["entries"][0]
    assert e["message_id"] == 999 and e["sender"] == "Right"
    assert e["asset_sha256"].startswith("sha256:")

def test_asset_root_required():
    with pytest.raises(ValueError):
        rebind(CAT, MSGS, None)

def test_missing_asset_is_unbound_not_null_hashed(tmp_path):
    out = rebind(CAT, MSGS, str(tmp_path))
    assert not out["entries"] and out["unbound"][0]["reason"].startswith("asset absent")

def test_all_rebound_items_unreviewed(assets):
    assert rebind(CAT, MSGS, assets)["entries"][0]["publication"] == "unreviewed"

def test_uncatalogued_reported(assets):
    assert "b.mp4" in rebind(CAT, MSGS, assets)["uncatalogued"]

def test_ambiguous_filename_fails(assets):
    dupes = MSGS + [{"id": 1001, "timestamp_utc": "2024-03-03T00:00:00Z",
                     "sender": "Third", "media": ["a.mp4"]}]
    with pytest.raises(AmbiguousBinding):
        rebind(CAT, dupes, assets)

def test_ambiguous_content_hash_fails(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"same")
    (tmp_path / "c.mp4").write_bytes(b"same")
    cat = CAT + [{"filename": "c.mp4", "description": "dup", "tags": []}]
    msgs = MSGS + [{"id": 1002, "timestamp_utc": "2024-04-04T00:00:00Z",
                    "sender": "Fourth", "media": ["c.mp4"]}]
    with pytest.raises(AmbiguousBinding):
        rebind(cat, msgs, str(tmp_path))
```

- [ ] **Step 3: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 4: Implement** — binding on `(content hash, filename)`, ambiguity failing on either
      key, `asset_root` required, missing assets unbound with a reason, `main()` requiring
      `--asset-root` (defaulting to `protected_root()` and exiting nonzero when unresolved), and
      output at `content/chat/media-catalog-rebound.json`.

- [ ] **Step 5: Run**

```bash
python -m pytest scripts/tests/test_rebind_media_catalog.py -v
python scripts/rebind_media_catalog.py --asset-root "$(python -c 'import json;print(json.load(open("content/governance/media_roots.json"))["protected_source_root"] or "")')"
```

If the root is unresolved the command exits nonzero and league media stays unavailable — the
correct outcome, not a failure to work around.

- [ ] **Step 6: Commit**

```bash
git add scripts/rebind_media_catalog.py content/governance/media_roots.json scripts/tests/test_rebind_media_catalog.py
git commit -m "feat(media): rebind with resolved protected root or explicit unavailability"
```

---

### Task B14: Media admission and byte-level render verification

**Files:** Create `scripts/media_manifest.py`, `scripts/verify_rendered_media.py`,
`scripts/tests/test_media_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.media_manifest import manifest_entry, build_manifest, publication_record
from scripts.verify_rendered_media import verify_render

CUTOFF = "2025-09-09T06:59:59Z"
CANDIDATES = [
    {"filename": "a.png", "asset_sha256": "sha256:aa", "timestamp_utc": "2025-09-01T00:00:00Z",
     "tags": ["meme"], "publication": "approved"},
    {"filename": "late.png", "asset_sha256": "sha256:bb", "timestamp_utc": "2025-12-01T00:00:00Z",
     "tags": ["meme"], "publication": "approved"},
    {"filename": "kid.png", "asset_sha256": "sha256:cc", "timestamp_utc": "2025-09-01T00:00:00Z",
     "tags": ["personal"], "publication": "approved"},
]

def _entry(**kw):
    base = dict(slot="s1", source_class="league_media", filename="a.png",
                source_locator="protected/a.png", source_sha="sha256:aa",
                publish_sha="sha256:aa", publish_location="media/2025/a.png",
                transformation="none", selection_provenance="culture desk, joke reuse check",
                cutoff_utc=CUTOFF, candidates=CANDIDATES)
    base.update(kw); return manifest_entry(**base)

def test_post_cutoff_league_media_rejected():
    with pytest.raises(ValueError):
        _entry(filename="late.png", source_sha="sha256:bb", publish_sha="sha256:bb")

def test_personal_tagged_media_barred():
    with pytest.raises(ValueError):
        _entry(filename="kid.png", source_sha="sha256:cc", publish_sha="sha256:cc")

def test_selection_provenance_required():
    with pytest.raises(ValueError):
        _entry(selection_provenance=None)

def test_transformation_decision_required():
    with pytest.raises(ValueError):
        _entry(transformation=None)

def test_publish_location_required():
    with pytest.raises(ValueError):
        _entry(publish_location=None)

def test_custom_path_must_be_inside_authorized_root():
    with pytest.raises(ValueError):
        manifest_entry(slot="c1", source_class="custom", cutoff_utc=CUTOFF, candidates=[],
                       publish_location="../../etc/passwd", publish_sha="sha256:cc",
                       temporal="non_evidentiary_decoration",
                       selection_provenance="p", transformation="none")

def test_giphy_requires_persisted_result():
    with pytest.raises(ValueError):
        manifest_entry(slot="g1", source_class="giphy", cutoff_utc=CUTOFF, candidates=[],
                       publish_location="https://giphy.com/x.gif", giphy_id=None,
                       temporal="non_evidentiary_decoration",
                       selection_provenance="p", transformation="none")

def test_manifest_binds_edition_and_authoring_manifest():
    mf = build_manifest("2025-wk01-recap", {"content_sha256": "sha256:c"}, "policy-v1", [_entry()])
    assert mf["edition_id"] == "2025-wk01-recap"
    assert mf["authoring_manifest_sha256"].startswith("sha256:")

def test_only_approved_entries_may_ship():
    with pytest.raises(ValueError):
        build_manifest("e", {}, "policy-v1", [_entry(publication_decision="unreviewed")])

def test_verifier_detects_multiplicity_location_and_bytes(tmp_path):
    mf = {"slots": [_entry()]}
    ok, p = verify_render('<img src="media/2025/a.png"><img src="media/2025/a.png">', mf, ".")
    assert not ok and any("multiplicity" in x for x in p)
    ok, p = verify_render('<img src="media/2025/rogue.png">', mf, ".")
    assert not ok and any("rogue" in x for x in p) and any("not rendered" in x for x in p)
    ok, p = verify_render('<img src="protected/a.png">', mf, ".")
    assert not ok and any("protected" in x for x in p)
    d = tmp_path / "media" / "2025"; d.mkdir(parents=True)
    (d / "a.png").write_bytes(b"WRONG")
    ok, p = verify_render('<img src="media/2025/a.png">', mf, str(tmp_path))
    assert not ok and any("bytes" in x for x in p)

def test_unresolved_slot_fails_not_disappears():
    mf = {"slots": [_entry(), _entry(slot="s2", publish_location="media/2025/b.png")]}
    ok, p = verify_render('<img src="media/2025/a.png">', mf, ".")
    assert not ok and any("b.png" in x for x in p)

def test_publication_record_binds_three():
    rec = publication_record({"content_sha256": "sha256:c"}, {"slots": []}, "<html></html>")
    for k in ("authoring_manifest_sha256", "media_manifest_sha256",
              "rendered_html_sha256", "result"):
        assert k in rec
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — `manifest_entry` now takes `cutoff_utc` and `candidates` and
      **enforces admission**: the filename must appear in `candidates`; its `timestamp_utc` must
      be `<= cutoff_utc`; `personal` tags are barred; `selection_provenance` and `transformation`
      are required; league media binds source locator + SHA and a publish SHA + authorized
      location; custom paths stay under `media/` and hash-match; GIPHY persists id + resolved
      result. `build_manifest` rejects any entry not `approved`. `verify_render` compares
      multiplicity (`Counter`), location, protected-path leakage, and **actual bytes**.

- [ ] **Step 4: Add the consumer tests** — `scripts/tests/test_media_consumers.py`:

```python
import ast
from pathlib import Path

def test_resolver_and_renderers_read_only_the_manifest():
    for f in ("scripts/resolve_media.py", ".claude/commands/render-week.md",
              ".claude/commands/render-preseason.md"):
        src = Path(f).read_text(encoding="utf-8")
        assert "media_manifest.json" in src, f
        for banned in ("media-catalog.json", "media_picks.json", "media_cache.json"):
            assert banned not in src, f"{f} still reads {banned}"

def test_renderers_embed_publish_location_not_source_locator():
    src = Path("scripts/resolve_media.py").read_text(encoding="utf-8")
    assert "publish" in src and "source_locator" not in src
```

- [ ] **Step 5: Run** → 12 + 2 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/media_manifest.py scripts/verify_rendered_media.py scripts/resolve_media.py .claude/commands/render-*.md scripts/tests/test_media_manifest.py scripts/tests/test_media_consumers.py
git commit -m "feat(media): cutoff+privacy admission, approved-derivative consumption, byte verify"
```

---

## Phase C — Newsroom that proves intelligence

### Task C1: Name repertoires — honest about what is discovered

The miner validates **seeded** forms (real name, handle, aliases, WhatsApp key, team words). It
does not discover unseeded shorthand. Two options; this plan takes the second and says so.

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
    assert all(o["handle"] for o in out["owners"])     # sleeper_handle
    assert all(o["team"] for o in out["owners"])       # team_name

def test_output_declares_its_method_honestly():
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    assert rep["method"] == "occurrence_validated_seeded_plus_manual_forms"

def test_seeded_forms_are_occurrence_validated():
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    for o in rep["owners"]:
        for f in o["observed"]:
            assert f["count"] > 0 and f.get("example_message_id") is not None

def test_manual_forms_are_marked_and_reviewed():
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    for o in rep["owners"]:
        for f in o.get("manual_forms", []):
            assert f["source"] == "blake_authored" and f.get("register")

def test_handles_match_sleeper_truth():
    users = json.load(open("data/2025/users.json", encoding="utf-8"))
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    assert {o["handle"] for o in rep["owners"]} == {u["display_name"] for u in users}
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — seed from `real_name`, `sleeper_handle`, `team_name`, `aliases`,
      map key and team words; count occurrences with an example message id; emit
      `"method": "occurrence_validated_seeded_plus_manual_forms"` and an empty `manual_forms` list
      per owner.

- [ ] **Step 4: Generate, author manual forms, then STOP for approval**

```bash
python scripts/mine_name_repertoires.py
python -m pytest scripts/tests/test_name_repertoires.py -v
```

Blake adds earned nicknames and shorthand the miner cannot discover to `manual_forms`, each with
a `register` note. **Review gate — names land like roasts; they should make the owner laugh, not
wince.** The repertoire reaches desks only through the bundle's `name_repertoires` component
(B9), never by direct read.

- [ ] **Step 5: Commit after approval**

```bash
git add scripts/mine_name_repertoires.py content/chat/name-repertoires.json scripts/tests/test_name_repertoires.py
git commit -m "feat(voice): occurrence-validated repertoire plus authored forms, bundle-served"
```

---

### Task C2: Desk commands

**Files:** Create six `.claude/commands/desk-*.md`; `scripts/tests/test_desk_commands.py`

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
              "content/chat/arcs.json", "media-catalog.json", "team-profiles.json",
              "content/weeks/"]
    for d in DESKS:
        t = Path(f".claude/commands/desk-{d}.md").read_text(encoding="utf-8")
        for b in banned:
            assert b not in t, f"desk-{d} declares {b}"

def test_desk_names_match_contracts():
    assert set(DESKS) == set(CONTRACTS["recap"].keys())

def test_desks_return_evidence_not_prose():
    for d in DESKS:
        assert "never prose" in Path(f".claude/commands/desk-{d}.md").read_text(
            encoding="utf-8").lower()
```

- [ ] **Step 2: Run to verify it fails** → files missing

- [ ] **Step 3: Author the six commands** — inputs limited to
      `content/editions/<edition_id>/compiled/bundle.json` and `content/voice-bible.md`; output is
      `{desk, edition_id, findings:[{claim, evidence_refs, confidence, candidate_angle}],
  unavailable:[]}` where every `evidence_refs` entry is a JSON pointer resolving in the
      bundle. Remits as in the design; the continuity desk is voice memory over
      `prior_editions`.

- [ ] **Step 4: Run** → 4 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/desk-*.md scripts/tests/test_desk_commands.py
git commit -m "feat(newsroom): six desks, bundle-only inputs, resolvable evidence refs"
```

---

### Task C3: Ranking grounding gate

**Files:** Create `scripts/schemas/ranking_record.schema.json`,
`scripts/verify_ranking_record.py`, `scripts/tests/test_ranking_record.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from scripts.verify_ranking_record import verify_ranking_record

TEAMS = [f"T{i}" for i in range(1, 13)]
BUNDLE = {"standings": [{"team_name": t} for t in TEAMS],
          "results": {"matchups": [{"a": 1}]}}
PRED = {"entries": [{"team": t, "proposed_rank": i} for i, t in enumerate(TEAMS, 1)]}

def _rec(**over):
    e = [{"team": t, "prior_rank": i, "proposed_rank": i, "movement": "steady",
          "decisive_evidence": ["/standings/0"], "contrary_evidence": "small sample so far",
          "coherence": "held position on results"} for i, t in enumerate(TEAMS, 1)]
    r = {"entries": e}; r.update(over); return r

def test_teams_must_equal_bundle_franchises():
    r = _rec(); r["entries"][0]["team"] = "Invented FC"
    ok, p = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("franchise" in x for x in p)

def test_predecessor_team_identity_must_match():
    bad_pred = {"entries": [{"team": "Someone Else", "proposed_rank": 1}]}
    ok, p = verify_ranking_record(_rec(), BUNDLE, bad_pred)
    assert not ok and any("predecessor" in x for x in p)

def test_prior_rank_must_equal_predecessor_proposed_rank():
    r = _rec(); r["entries"][2]["prior_rank"] = 11
    ok, p = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("prior_rank" in x for x in p)

def test_schema_is_loaded_and_enforced():
    r = _rec(); del r["entries"][0]["coherence"]
    ok, p = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("schema" in x.lower() for x in p)

def test_twelve_distinct_and_ranks_one_to_twelve():
    r = _rec(); r["entries"] = r["entries"][:11]
    assert not verify_ranking_record(r, BUNDLE, PRED)[0]

def test_unchanged_rank_still_needs_evidence():
    r = _rec(); r["entries"][3]["decisive_evidence"] = []
    ok, p = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("evidence" in x for x in p)

def test_evidence_ref_must_resolve():
    r = _rec(); r["entries"][2]["decisive_evidence"] = ["/no/such/pointer"]
    ok, p = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("resolve" in x for x in p)

def test_crossing_identifies_displaced_team():
    r = _rec()
    r["entries"][4].update(prior_rank=5, proposed_rank=3, movement="up_2",
                           coherence="we played well")
    ok, p = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("displaced" in x for x in p)

def test_reversal_acknowledges_prior_judgment():
    r = _rec()
    r["entries"][0].update(prior_rank=1, proposed_rank=9, movement="down_8",
                           coherence="passed by T2 T3 T4 T5 T6 T7 T8 T9")
    ok, p = verify_ranking_record(r, BUNDLE, PRED)
    assert not ok and any("prior judgment" in x for x in p)

def test_preseason_has_no_predecessor_but_still_needs_evidence():
    r = _rec()
    for e in r["entries"]:
        e["prior_rank"] = None; e["movement"] = "steady"
    ok, p = verify_ranking_record(r, BUNDLE, None)
    assert ok, p

def test_clean_record_passes():
    assert verify_ranking_record(_rec(), BUNDLE, PRED)[0]
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — load and enforce `ranking_record.schema.json` via
      `jsonschema.Draft202012Validator` (schema failures become problems prefixed `schema:`);
      require the record's team set to equal `{s["team_name"] for s in bundle["standings"]}`;
      require the predecessor's team set to match; require `prior_rank ==` the predecessor's
      `proposed_rank` for that team; plus the evidence/crossing/reversal rules from the prior
      revision. `main()` takes `--record --bundle [--predecessor]`.

- [ ] **Step 4: Run** → 11 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/schemas/ranking_record.schema.json scripts/verify_ranking_record.py scripts/tests/test_ranking_record.py
git commit -m "feat(rankings): schema-enforced gate bound to bundle franchises and predecessor"
```

---

### Task C4: Bake-off — ranking-first in BOTH arms

**Files:** Create `.claude/commands/bakeoff.md`, `content/editions/_bakeoff/rubric.json`,
`scripts/tests/test_bakeoff_record.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

R = json.load(open("content/editions/_bakeoff/rubric.json", encoding="utf-8"))

def test_each_arm_produces_a_gated_ranking_before_prose():
    assert R["arm_sequence"] == ["ranking_record", "verify_ranking_record", "prose"]

def test_rubric_scores_ranking_and_prose():
    dims = {d["name"] for d in R["dimensions"]}
    assert {"ranking_grounding", "ranking_judgment", "factual_corrections",
            "unique_evidence", "phrase_repetition", "owner_specificity",
            "survived_blake_edit"} <= dims

def test_ranking_outranks_prose_in_the_rule():
    assert "weaker ranking judgment loses" in R["rule"]

def test_decision_record_shape():
    for f in ("winner", "loser_disposal", "scores", "decided_at_utc", "pipeline_for_later_editions"):
        assert f in R["decision_record_fields"], f

def test_command_states_later_editions_follow_the_winner():
    t = Path(".claude/commands/bakeoff.md").read_text(encoding="utf-8").lower()
    assert "later editions follow the winning pipeline" in t
```

- [ ] **Step 2: Run to verify it fails** → file missing

- [ ] **Step 3: Write the rubric and command**

```json
{
  "version": 1,
  "arm_sequence": ["ranking_record", "verify_ranking_record", "prose"],
  "dimensions": [
    {
      "name": "ranking_grounding",
      "how": "verify_ranking_record problem count (lower wins)"
    },
    {
      "name": "ranking_judgment",
      "how": "Blake's qualitative call on the ordering"
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
      "how": "repeated constructions (lower wins)"
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
    "pipeline_for_later_editions",
    "notes"
  ],
  "rule": "Compare ranking/prose PAIRS. A candidate with better prose but weaker ranking judgment loses."
}
```

`.claude/commands/bakeoff.md`: each arm **first** authors its own `ranking_record.json` and passes
`verify_ranking_record.py`, **then** writes prose from that judgment. Score the pairs, record the
decision at `content/editions/_bakeoff/decision.json`, delete the losing pipeline's command files,
and state plainly: **later editions follow the winning pipeline** — D1b and D1c do not assume the
desks won.

- [ ] **Step 4: Run** → 5 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/bakeoff.md content/editions/_bakeoff/rubric.json scripts/tests/test_bakeoff_record.py
git commit -m "feat(newsroom): ranking-first bake-off; winner governs later editions"
```

---

### Task C5: Edition mode for the verifier

`verify_week_content.py:1554` builds `week{N}_content.json`; `--week 0` seeks a nonexistent file.

**Files:** Modify `scripts/verify_week_content.py`; create `scripts/tests/test_verify_edition_mode.py`

- [ ] **Step 1: Write the failing test**

```python
import subprocess, sys

def test_edition_mode_exists():
    r = subprocess.run([sys.executable, "scripts/verify_week_content.py",
                        "--edition", "content/editions/2025-preseason", "--pretty"],
                       capture_output=True, text=True)
    assert r.returncode in (0, 1), r.stderr[:200]
    assert "week0" not in r.stderr

def test_week_zero_rejected():
    r = subprocess.run([sys.executable, "scripts/verify_week_content.py", "--week", "0"],
                       capture_output=True, text=True)
    assert r.returncode != 0
```

- [ ] **Step 2: Run to verify it fails** → `--edition` unrecognized

- [ ] **Step 3: Add `--edition`** resolving `content.json`, `compiled/bundle.json`, and
      `ranking_record.json`; reject `--week 0`; skip week-only Tier-1 checks for
      `kind == "preseason"`.

- [ ] **Step 4: Run; suite ≥ 343/2**

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_week_content.py scripts/tests/test_verify_edition_mode.py
git commit -m "feat(verify): edition mode replaces the nonexistent week-0 path"
```

---

## D1 — Three editions, then STOP

**Exact sequence per edition:**

```
descriptor → compile_edition → bundle_manifest
  → desks (bake-off on the first, ranking-first in BOTH arms)
  → RANKING RECORD → verify_ranking_record → prose written FROM it
  → author_edition (authoring_manifest.json)
  → Blake's separate ranking approval
  → editorial approval bound to that authoring manifest (review-log line)
  → media manifest → render → verify_rendered_media (bytes) → publication record → commit
```

### Task D1a: Preseason

- [ ] **Step 1: Descriptor** at `content/editions/2025-preseason/descriptor.json` —
      `kind: "preseason"`, `cutoff_utc: "2025-09-03T23:59:59Z"`, `results_through_week: 0`,
      `predecessors: []`.

- [ ] **Step 2: Compile and audit**

```bash
python scripts/compile_edition.py --descriptor content/editions/2025-preseason/descriptor.json
python scripts/cutoff_audit.py --all
python scripts/canon_checks.py --edition content/editions/2025-preseason
```

- [ ] **Step 3: Bake-off** (`/bakeoff`) — each arm authors and gates its ranking record, then
      writes prose. Record the decision; delete the loser; note which pipeline D1b/D1c follow.

- [ ] **Step 4: Gate the ranking**

```bash
python scripts/verify_ranking_record.py \
  --record content/editions/2025-preseason/ranking_record.json \
  --bundle content/editions/2025-preseason/compiled/bundle.json
```

`prior_rank` is `null` throughout; **evidence is still required**.

- [ ] **Step 5: Verify content, then bind the authoring manifest**

```bash
python scripts/verify_week_content.py --edition content/editions/2025-preseason --pretty
python scripts/author_edition.py --edition content/editions/2025-preseason --voice-rule-version voice-v1
```

- [ ] **Step 6: Blake approves the ranking separately from the prose**, then `/edit-preseason` →
      APPROVE with a `review-log.jsonl` line bound to `authoring_manifest.json`'s hash.

- [ ] **Step 7: Media, render, byte-verify, publish**

```bash
python scripts/verify_rendered_media.py preseason-2025.html \
  content/editions/2025-preseason/media_manifest.json
```

- [ ] **Step 8: Commit**

```bash
git add content/editions/2025-preseason/ preseason-2025.html content/review-log.jsonl
git commit -m "content(2025-preseason): first canonical edition through the full system"
```

---

### Task D1b: Week-1 pre-kickoff preview

- [ ] **Step 1: Qualify the cutoff through the compiler, not by hand**

```bash
python scripts/fetch_nflreadpy.py
python -c "
from scripts.kickoff_source import first_kickoff_instant, strictly_before
r = first_kickoff_instant(2025)
print(strictly_before(r['instant_utc']), r['source_hashes'])"
```

Write the returned instant into the descriptor. **Do not hand-write source hashes into
`source_hashes.json`** — compilation regenerates that file; the kickoff identity travels through
the descriptor and is aggregated by the compiler.

Declare `predecessors: [{edition_id: "2025-preseason", authoring_manifest_sha256: <hash>,
cutoff_utc: "2025-09-03T23:59:59Z"}]`.

- [ ] **Step 2: Compile and assert emptiness**

```bash
python scripts/compile_edition.py --descriptor content/editions/2025-wk01-preview/descriptor.json
python -m pytest scripts/tests/test_project_edition.py -v
```

The preview chat must declare the preview cutoff and contain none of the 28 result statements.

- [ ] **Steps 3-8:** desks (winning pipeline) → ranking record → gate → prose → `author_edition`
      → ranking approval → editorial approval → media → render → byte verify → publish → commit.
      Add the nav entry to `config.js`.

---

### Task D1c: Week-1 recap

- [ ] **Step 1: Descriptor** — `kind: "recap"`, `results_through_week: 1`,
      `cutoff_utc: "2025-09-09T06:59:59Z"`, `predecessors: [preseason, preview]` with their
      authoring-manifest hashes and cutoffs.

- [ ] **Step 2: Compile.** Week-1 results present; week-2 absent; predecessor ordering enforced.

- [ ] **Steps 3-8:** as D1b. The continuity desk grades the preview's picks and the preseason's
      claims — the first edition where receipts resolve.

---

### Task D1d: PRODUCT GATE — stop

- [ ] **Step 1: Full sweep**

```bash
python -m pytest scripts/tests/ -q
python scripts/cutoff_audit.py --all
python scripts/generate_chat_provenance.py --verify
python -m pytest scripts/tests/test_noninterference.py -v
```

- [ ] **Step 2: Review packet** — census 46 → 0; 0 structurally unsliced H2H (from 98); three
      ranking records with gate output; `review-log.jsonl`; byte-verifier output per edition; the
      bake-off decision; truncation and canary results; a side-by-side against the old week-1
      filler.

- [ ] **Step 3: Answer in writing**

> **Did the model become visibly more informed across the three editions?**

Cite specific ranking movements justified by evidence absent from the prior edition. If no,
revise the source and desk contracts before D2.

- [ ] **Step 4: STOP.**

---

## Self-Review — affected contracts only

**Temporal isolation.** `SOURCE_ROOT` is injectable in `as_of_records` and `project_edition`; B12
builds a corpus with post-cutoff rows physically deleted and requires byte-identical bundles, with
two planted-leak controls (dated week-17 row; undated streak extension) that must produce
_different_ bundles. The chat adapter projects at the descriptor cutoff and refuses a projection
whose declared cutoff differs — the specific defect that let `week1_chat_context.json`
(cutoff `2025-09-09T06:59:59Z`, 28 result statements) reach the preview. The `edition_bundle`
registry is written out in full; controls drive the shipped `audit_object` and CLI exit code.

**Season isolation.** Weekly artifacts resolve through `content/seasons/{season}/weeks/`; the
legacy seasonless path cannot serve a non-2025 descriptor. Every adapter returns a source identity
carrying its season, and the canary asserts `ident["season"] == 2024` per component rather than
"records are non-null".

**Cutoff qualification.** `to_utc` converts through `ZoneInfo`; a missing venue timezone raises
`UnavailableEvidence`. Both the schedule and timezone-map hashes are returned. The polars claim
was **refuted** (`polars 1.40.1` imports cleanly here) and no workaround is planned; the test
defect it accompanied is fixed with a real `pytest.skip` and an `UnavailableEvidence` path.

**Compiler.** Adapters declare sources; the compiler aggregates all of them plus code and declared
predecessors; unidentified components fail closed. Predecessors are declared with hashes and
cutoff ordering enforced — no globbing, so a rebuild cannot admit its own future.
`compile_edition` owns only `<edition>/compiled/` and a rebuild preserves authored artifacts.
`author_edition.py` is the missing executable step producing `authoring_manifest.json`.

**Boundary.** `voice-bible.md` is an allowed versioned editorial rule, so the boundary test can
pass; `canon_checks.py` is in `CONSUMERS` and rewired to `--edition`. `analyze_chat.py` execution
is disabled outright — a partial redirect left `OUT_*` and `PERSONAS_DIR` live.

**Phase 0.** Public and private roots are separate, `private_captures/` is gitignored, receipts
carry metadata only, staging is public-only with a guard. Cadence runs through September; the
workflow commits its captures and stays inactive pending Blake's explicit approval of that push,
with local checkpoint captures covering D1.

**Rankings and media.** Both bake-off arms author and gate a ranking record before prose, and the
winner governs later editions. The ranking gate loads its schema, binds teams to bundle
franchises, and requires `prior_rank` to equal the predecessor's `proposed_rank`. The rebound
catalog becomes the bundle's `media_candidates`; manifest construction enforces cutoff and bars
`personal` tags; the render verifier compares multiplicity, location, and bytes; consumer tests
prove the resolver and both renderers read only the manifest's approved publication derivative.

**Open execution dependency.** `protected_source_root` is `null` until Blake supplies it. Until
then league media is **unavailable** and the editions run on GIPHY and custom media. No media
assets exist in the repository, so 1205/1205 rebinding is not assumed.
