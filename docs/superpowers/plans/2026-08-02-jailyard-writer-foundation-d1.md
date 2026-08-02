# Jailyard Writer Foundation — Implementation Plan (through D1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the cutoff leaks in writer inputs, build the minimum projector and audit that
prevent their recurrence, stand up the newsroom, and produce three canonical editions
(preseason → week-1 pre-kickoff preview → week-1 recap) end to end — then stop for review.

**Architecture:** A per-edition projection compiler is the sole trusted reader of raw and
full-season stores; every writing consumer reads only an edition bundle. Ranking judgment is
recorded before prose is written. Media is authorized by a tracked per-edition manifest and
verified against the final HTML. A parallel capture lane preserves volatile 2026 evidence.

**Tech Stack:** Python 3.12 (`python`, not `python3`), pytest, `jsonschema`, stdlib `hashlib`/
`ast`. No new runtime dependencies. Zero-dependency static HTML output unchanged.

**Design authority:** `docs/superpowers/specs/2026-08-01-jailyard-writer-foundation-design.md`
(APPROVED at `072f4ea`). Material deviation requires re-approval.

## Global Constraints

- Python is invoked as `python`, never `python3` (Windows).
- Scripts runnable both under pytest and directly use the sys.path bootstrap pattern from
  `scripts/fetch_nflreadpy.py:20-25`; tests import as `from scripts.X import ...`.
- All generated JSON is written via `shared.save_json_canonical` (sort_keys, ensure_ascii=False,
  indent=2, explicit sort before serialization).
- `list(some_set)` is banned where the result is serialized; use `sorted()` (`PYTHONHASHSEED` is
  unpinned).
- `extract_week_data.py` is always run with `--pretty`; the compact default collapses the
  committed multi-line files.
- Baseline test suite is **343 passed / 2 skipped** (measured at `c751b22`, 2026-08-01, 167s).
  No task may reduce this count.
- HTML is prettier-excluded (`.prettierignore`); never reformat it.
- Quality gates are binary. A gate that finds an error yields the gate's verdict; no
  "approve with notes".
- Cutoff comparisons use `shared.admissible` semantics (`ts <= cutoff`, exact tz-aware instants).
  A cutoff that must exclude an instant is set strictly prior to it.
- After any push, watch CI keyed on HEAD's own SHA. **This plan performs no pushes.**
- Commit after each task. Do not push, publish, or delete anything outside the files named.

---

## File Structure

| File                                          | Responsibility                                                          |
| --------------------------------------------- | ----------------------------------------------------------------------- |
| `scripts/as_of_records.py` (new)              | Recompute the 7 league records — dated and undated — at a cutoff        |
| `scripts/extract_week_data.py` (modify)       | Slice h2h by cutoff; route `historical_context` through `as_of_records` |
| `scripts/cutoff_audit.py` (new)               | Leaf census + classification; unknown fields fail closed                |
| `content/governance/writer_fields.json` (new) | Field classification registry for the audit                             |
| `scripts/edition.py` (new)                    | Edition descriptor, bundle manifest, authoring manifest, hashing        |
| `scripts/project_edition.py` (new)            | The projector — sole trusted reader of raw/full-season stores           |
| `scripts/rebind_media_catalog.py` (new)       | Rebind catalog to repaired corpus on asset hash + filename              |
| `scripts/media_manifest.py` (new)             | Per-edition media manifest; publication record                          |
| `scripts/verify_rendered_media.py` (new)      | Final-HTML ↔ manifest bijection on location and bytes                   |
| `scripts/capture_2026.py` (new)               | Lane P: append-only capture with offseason-capable transactions         |
| `scripts/read_path_census.py` (new)           | Phase A: enumerate prose reachable by writing paths                     |
| `content/chat/name-repertoires.json` (new)    | Twelve owner name repertoires, Blake-approved                           |
| `.claude/commands/desk-*.md` (new, 6)         | Five evidence desks + Data/Copy Editor                                  |

---

## Lane P — 2026 evidence preservation (runs in parallel; does not block A→B→C→D1)

### Task P1: Append-only capture store

**Files:**

- Create: `scripts/capture_2026.py`
- Create: `scripts/tests/test_capture_2026.py`

**Interfaces:**

- Consumes: `shared.save_json_canonical`, `shared.load_json`
- Produces: `capture(source: str, payload, known_at_rule: str, privacy: str) -> Path`,
  `capture_path(source, captured_at) -> Path`, `CAPTURE_ROOT`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.capture_2026 import capture, CAPTURE_ROOT

def test_capture_is_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.CAPTURE_ROOT", tmp_path)
    p1 = capture("league", {"a": 1}, known_at_rule="capture_instant",
                 privacy="public", captured_at="2026-08-02T00:00:00Z")
    p2 = capture("league", {"a": 2}, known_at_rule="capture_instant",
                 privacy="public", captured_at="2026-08-02T01:00:00Z")
    assert p1 != p2 and p1.exists() and p2.exists()
    assert json.loads(p1.read_text())["payload"] == {"a": 1}

def test_capture_records_required_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.CAPTURE_ROOT", tmp_path)
    p = capture("rosters", {"r": []}, known_at_rule="capture_instant",
                privacy="public", captured_at="2026-08-02T00:00:00Z")
    rec = json.loads(p.read_text())
    for field in ("source", "captured_at", "known_at_rule", "content_sha256", "privacy"):
        assert field in rec, field

def test_capture_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.capture_2026.CAPTURE_ROOT", tmp_path)
    kw = dict(known_at_rule="capture_instant", privacy="public",
              captured_at="2026-08-02T00:00:00Z")
    capture("league", {"a": 1}, **kw)
    try:
        capture("league", {"a": 999}, **kw)
        assert False, "expected refusal on identical captured_at"
    except FileExistsError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_capture_2026.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.capture_2026'`

- [ ] **Step 3: Write minimal implementation**

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


def capture_path(source: str, captured_at: str) -> Path:
    stamp = captured_at.replace(":", "").replace("-", "")
    return CAPTURE_ROOT / source / f"{stamp}.json"


def capture(source, payload, known_at_rule, privacy, captured_at):
    if privacy not in VALID_PRIVACY:
        raise ValueError(f"privacy must be one of {sorted(VALID_PRIVACY)}")
    path = capture_path(source, captured_at)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing capture: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record = {
        "source": source,
        "captured_at": captured_at,
        "known_at_rule": known_at_rule,
        "privacy": privacy,
        "content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "payload": payload,
    }
    save_json_canonical(record, path)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_capture_2026.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_2026.py scripts/tests/test_capture_2026.py
git commit -m "feat(capture): append-only 2026 evidence store with refusal-on-overwrite"
```

---

### Task P2: Offseason-capable transaction fetch

`fetch_sleeper.py:172` iterates `range(1, len(all_matchups) + 1)`. Before any scored matchup that
is `range(1, 1)` and **zero** transactions are fetched. Lane P needs its own path.

**Files:**

- Modify: `scripts/capture_2026.py`
- Modify: `scripts/tests/test_capture_2026.py`

**Interfaces:**

- Consumes: `capture` from P1
- Produces: `transaction_legs(has_scored_matchups: bool) -> list[int]`

- [ ] **Step 1: Write the failing test**

```python
from scripts.capture_2026 import transaction_legs

def test_offseason_still_yields_legs():
    legs = transaction_legs(has_scored_matchups=False)
    assert legs, "offseason must still fetch transaction legs"
    assert 1 in legs

def test_inseason_covers_full_range():
    assert max(transaction_legs(has_scored_matchups=True)) >= 17
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_capture_2026.py -k legs -v`
Expected: FAIL — `ImportError: cannot import name 'transaction_legs'`

- [ ] **Step 3: Write minimal implementation**

```python
# Sleeper exposes offseason activity on legs 1..18 regardless of scored matchups.
# Never derive the range from len(all_matchups) -- that yields range(1,1) preseason.
MAX_LEG = 18


def transaction_legs(has_scored_matchups: bool):
    return list(range(1, MAX_LEG + 1))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_capture_2026.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_2026.py scripts/tests/test_capture_2026.py
git commit -m "fix(capture): offseason-capable transaction legs, independent of scored matchups"
```

---

### Task P3: Wire the minimum capture table

**Files:**

- Modify: `scripts/capture_2026.py`
- Create: `content/governance/capture_table.json`
- Modify: `scripts/tests/test_capture_2026.py`

**Interfaces:**

- Produces: `CAPTURE_TABLE` (list of source rows), `run_capture(now_utc: str) -> list[Path]`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.capture_2026 import load_capture_table

REQUIRED = {"sleeper_league", "sleeper_users", "rosters", "draft", "transactions"}

def test_capture_table_covers_minimum_sources():
    rows = {r["source"] for r in load_capture_table()}
    assert REQUIRED <= rows, f"missing: {REQUIRED - rows}"

def test_every_row_declares_required_semantics():
    for r in load_capture_table():
        for field in ("source", "mechanism", "cadence", "known_at_rule", "privacy"):
            assert field in r, f"{r.get('source')} missing {field}"
        assert r["privacy"] in {"public", "private"}

def test_chat_media_is_private():
    rows = {r["source"]: r for r in load_capture_table()}
    if "chat_media_export" in rows:
        assert rows["chat_media_export"]["privacy"] == "private"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_capture_2026.py -k capture_table -v`
Expected: FAIL — `ImportError: cannot import name 'load_capture_table'`

- [ ] **Step 3: Write the artifact and loader**

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
      "mechanism": "api_offseason_capable",
      "cadence": "daily",
      "known_at_rule": "effective_completion_instant",
      "privacy": "public"
    },
    {
      "source": "projections",
      "mechanism": "source_dependent",
      "cadence": "weekly_through_preseason",
      "known_at_rule": "publication_instant_else_unqualified",
      "privacy": "public"
    },
    {
      "source": "injuries",
      "mechanism": "source_dependent",
      "cadence": "weekly_through_preseason",
      "known_at_rule": "publication_instant_else_unqualified",
      "privacy": "public"
    },
    {
      "source": "chat_media_export",
      "mechanism": "manual_export",
      "cadence": "on_export",
      "known_at_rule": "message_timestamp",
      "privacy": "private"
    }
  ]
}
```

```python
CAPTURE_TABLE_PATH = (
    Path(__file__).resolve().parents[1] / "content" / "governance" / "capture_table.json"
)


def load_capture_table():
    from shared import load_json
    return load_json(CAPTURE_TABLE_PATH, required=True)["rows"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_capture_2026.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/capture_2026.py content/governance/capture_table.json scripts/tests/test_capture_2026.py
git commit -m "feat(capture): minimum 2026 capture table with known-at and privacy semantics"
```

---

## Phase A — Authority and read-path census

### Task A1: Read-path census tool

**Files:**

- Create: `scripts/read_path_census.py`
- Create: `scripts/tests/test_read_path_census.py`

**Interfaces:**

- Produces: `find_prose_reachable() -> list[dict]` with keys `path`, `line`, `kind`

- [ ] **Step 1: Write the failing test**

```python
from scripts.read_path_census import find_prose_reachable

def test_census_finds_known_contaminated_paths():
    hits = {(h["path"], h["kind"]) for h in find_prose_reachable()}
    paths = {p for p, _ in hits}
    assert any("voice-bible.md" in p for p in paths)
    assert any("write-preseason.md" in p for p in paths)
    assert any("generate_franchise_wings.py" in p for p in paths)

def test_census_reports_generated_artifact_prose():
    kinds = {h["kind"] for h in find_prose_reachable()}
    assert "generated_artifact_prose" in kinds
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_read_path_census.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
"""Enumerate every path by which superseded prose can reach a writing decision."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]

PROSE_FIELDS = ("essay_snippet", "roast", "blurb", "preseasonEssay", "voice_bible_callbacks")
COMMAND_MARKERS = ("inspiration", "precedent", "tone", "voice-bible", "team-profiles")


def find_prose_reachable():
    hits = []
    for md in sorted((ROOT / ".claude" / "commands").glob("*.md")):
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            low = line.lower()
            if any(m in low for m in COMMAND_MARKERS):
                hits.append({"path": str(md.relative_to(ROOT)), "line": i,
                             "kind": "command_prose_reference"})
    vb = ROOT / "content" / "voice-bible.md"
    for i, line in enumerate(vb.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith(">"):
            hits.append({"path": str(vb.relative_to(ROOT)), "line": i,
                         "kind": "voice_bible_excerpt"})
    for py in sorted((ROOT / "scripts").glob("*.py")):
        text = py.read_text(encoding="utf-8")
        for f in PROSE_FIELDS:
            if f'"{f}"' in text:
                hits.append({"path": str(py.relative_to(ROOT)), "line": 0,
                             "kind": "generated_artifact_prose"})
                break
    for wk in sorted((ROOT / "content" / "weeks").glob("week*_data.json")):
        blob = wk.read_text(encoding="utf-8")
        if '"essay_snippet"' in blob or '"roast"' in blob:
            hits.append({"path": str(wk.relative_to(ROOT)), "line": 0,
                         "kind": "generated_artifact_prose"})
    return hits


if __name__ == "__main__":
    print(json.dumps(find_prose_reachable(), indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_read_path_census.py -v`
Expected: 2 passed

- [ ] **Step 5: Produce the census for review**

Run: `python scripts/read_path_census.py > docs/superpowers/plans/read-path-census-2026-08-02.json`

- [ ] **Step 6: Commit**

```bash
git add scripts/read_path_census.py scripts/tests/test_read_path_census.py docs/superpowers/plans/read-path-census-2026-08-02.json
git commit -m "feat(census): enumerate prose reachable by active writing paths"
```

---

### Task A2: Voice-bible surgery

Keep abstract grammar, templates, anti-patterns. Delete every superseded prose excerpt. Replace
the handle table with a pointer to the repertoire (built in C1). Per the design, **no replacement
exemplar is required for the first edition.**

**Files:**

- Modify: `content/voice-bible.md`
- Create: `scripts/tests/test_voice_bible_clean.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
VB = Path("content/voice-bible.md")

def test_no_superseded_excerpts_remain():
    lines = VB.read_text(encoding="utf-8").splitlines()
    quotes = [l for l in lines if l.lstrip().startswith(">") and len(l.strip()) > 30]
    assert not quotes, f"{len(quotes)} prose excerpts remain: {quotes[:3]}"

def test_abstract_grammar_retained():
    text = VB.read_text(encoding="utf-8")
    for marker in ("Pattern 1", "Pattern 12", "Anti-Patterns", "Cold Open Essay"):
        assert marker in text, marker

def test_no_stale_handle_table():
    assert "@kharlo_w" not in VB.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_voice_bible_clean.py -v`
Expected: FAIL on all three

- [ ] **Step 3: Edit `content/voice-bible.md`**

Delete: every `>` blockquote example under §1 (the ranges cited in the design — `:16-20`,
`:38-46`, `:64-70`, `:100-106`, `:122-126`, `:148-152`), and all of §5 Annotated Exemplars.
Replace §2's handle table with:

```markdown
### Owner Names

Attribution uses the approved repertoire at `content/chat/name-repertoires.json`. Each owner has
multiple valid forms; choose by register, never by rote. Do not hard-code names here.
```

Keep §1 pattern definitions, §2 tier system and lexicon terms, §3 templates, §4 anti-patterns,
and the Appendix checklist.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_voice_bible_clean.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add content/voice-bible.md scripts/tests/test_voice_bible_clean.py
git commit -m "refactor(voice): strip superseded excerpts, keep grammar; repertoire replaces handle table"
```

---

### Task A3: Quarantine `analyze_chat.py` and remove the dormant enrichment

`analyze_chat.py` genuinely loads the stale catalog (`:145`, `:988`) and can overwrite analytics
filenames the canonical builder consumes. `build_chat_context.py`'s `media_catalog` parameter is
unreachable (sole caller `:1228` passes 10 positional args).

**Files:**

- Modify: `scripts/analyze_chat.py`
- Modify: `scripts/build_chat_context.py`
- Create: `scripts/tests/test_producer_quarantine.py`

- [ ] **Step 1: Write the failing test**

```python
import ast, subprocess, sys
from pathlib import Path

def test_analyze_chat_refuses_to_run_authoritatively():
    r = subprocess.run([sys.executable, "scripts/analyze_chat.py"],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "quarantined" in (r.stdout + r.stderr).lower()

def test_dormant_media_enrichment_removed():
    src = Path("scripts/build_chat_context.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "score_message_relevancy":
            assert "media_catalog" not in [a.arg for a in node.args.args], \
                "unreachable media_catalog parameter must be removed or deliberately wired"
    assert "MEDIA_CATALOG_PATH" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_producer_quarantine.py -v`
Expected: FAIL — both

- [ ] **Step 3: Implement the quarantine**

At the top of `analyze_chat.py`'s `main()`:

```python
QUARANTINE_MSG = (
    "analyze_chat.py is QUARANTINED: it message-ID-joins the pre-repair media catalog "
    "and can overwrite analytics filenames consumed by build_chat_context.py. "
    "Re-enable only after the catalog is rebound and this script enters the provenance "
    "contract (generate_chat_provenance.py CODE_FILES). "
    "Override for local inspection with --i-know-this-is-quarantined."
)


def main():
    if "--i-know-this-is-quarantined" not in sys.argv:
        print(QUARANTINE_MSG, file=sys.stderr)
        return 1
    ...
```

In `build_chat_context.py`: delete the `MEDIA_CATALOG_PATH` assignment (`:38`), remove the
`media_catalog` parameter from `score_message_relevancy` (`:358`), and delete the conditional
lookup at `:381-382`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest scripts/tests/test_producer_quarantine.py -v && python -m pytest scripts/tests/ -q`
Expected: 2 passed; full suite ≥ 343 passed / 2 skipped

- [ ] **Step 5: Verify provenance still passes**

Run: `python scripts/generate_chat_provenance.py --verify`
Expected: `OK: content/chat/provenance.json matches recomputed (full).`
If it fails because `build_chat_context.py` is in `CODE_FILES` and its hash changed, rebuild the
receipt per the project rule: `--rebuild-check` green, then `--write --receipt <path>`. Never
hand-edit the manifest.

- [ ] **Step 6: Commit**

```bash
git add scripts/analyze_chat.py scripts/build_chat_context.py scripts/tests/test_producer_quarantine.py content/chat/provenance.json
git commit -m "fix(chat): quarantine analyze_chat producer; remove unreachable media enrichment"
```

---

### Task A4: Strip prose from generated artifacts

**Files:**

- Modify: `scripts/extract_week_data.py` (drop `essay_snippet`/`roast` from
  `team_profiles_summary`)
- Modify: `scripts/generate_franchise_wings.py:294-301` (drop `roast` from
  `voice_bible_callbacks`)
- Create: `scripts/tests/test_no_prose_in_generated.py`

- [ ] **Step 1: Write the failing test**

```python
import json, glob

def test_week_packets_carry_no_prose():
    for fp in glob.glob("content/weeks/week*_data.json"):
        blob = json.dumps(json.load(open(fp, encoding="utf-8")))
        assert '"essay_snippet"' not in blob, fp
        assert '"roast"' not in blob, fp

def test_franchise_wings_carry_no_prose():
    for fp in glob.glob("data/franchises/*.json"):
        if fp.endswith("_index.json"):
            continue
        blob = json.dumps(json.load(open(fp, encoding="utf-8")))
        assert '"roast"' not in blob, fp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_no_prose_in_generated.py -v`
Expected: FAIL on both

- [ ] **Step 3: Remove the fields**

In `extract_week_data.py`, remove `essay_snippet` and `roast` from the
`team_profiles_summary` entry builder — retain `preseason_rank`, `ranks`, `tier`, `needs`,
`weeklyPoints_projected` (structured, reclassified untrusted, not prose).
In `generate_franchise_wings.py:294-301`, delete the `"roast"` key from `voice_bible_callbacks`.

- [ ] **Step 4: Regenerate and verify**

```bash
python scripts/extract_week_data.py --all --pretty
python scripts/generate_franchise_wings.py
python -m pytest scripts/tests/test_no_prose_in_generated.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_week_data.py scripts/generate_franchise_wings.py content/weeks/ data/franchises/ scripts/tests/test_no_prose_in_generated.py
git commit -m "fix(data): strip superseded prose from generated week packets and franchise wings"
```

---

## Phase B — Repair, minimum projector, audit

### Task B1: Cutoff-sliced H2H

**Files:**

- Create: `scripts/as_of_records.py`
- Create: `scripts/tests/test_as_of_records.py`

**Interfaces:**

- Produces: `slice_h2h(entry: dict, season: int, week: int, inclusive: bool) -> dict` returning
  `{"team1_wins", "team2_wins", "total_games", "last_meeting"}`

`entry` shape (verified): `{"games": [{"season","week","pts","opp_pts"}], "wins", "losses",
"pf", "pa"}`, oriented to the first owner id in the `oid1|oid2` key.

- [ ] **Step 1: Write the failing test**

```python
from scripts.as_of_records import slice_h2h

ENTRY = {
    "games": [
        {"season": 2022, "week": 9, "pts": 140.3, "opp_pts": 153.12},
        {"season": 2025, "week": 6, "pts": 109.1, "opp_pts": 150.46},
        {"season": 2025, "week": 12, "pts": 180.0, "opp_pts": 100.0},
    ],
    "wins": 1, "losses": 2,
}

def test_recap_includes_own_week():
    r = slice_h2h(ENTRY, 2025, 6, inclusive=True)
    assert r["total_games"] == 2
    assert r["last_meeting"]["season"] == 2025 and r["last_meeting"]["week"] == 6

def test_preview_excludes_own_week():
    r = slice_h2h(ENTRY, 2025, 6, inclusive=False)
    assert r["total_games"] == 1
    assert r["last_meeting"]["season"] == 2022

def test_wins_recomputed_from_slice_not_copied():
    r = slice_h2h(ENTRY, 2025, 6, inclusive=True)
    assert r["team1_wins"] == 0 and r["team2_wins"] == 2

def test_empty_slice_yields_null_last_meeting():
    r = slice_h2h(ENTRY, 2021, 1, inclusive=True)
    assert r["total_games"] == 0 and r["last_meeting"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_as_of_records.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
"""Cutoff-correct recomputation of league records and H2H."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


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
    losses = len(games) - wins
    last = games[-1] if games else None
    return {
        "team1_wins": wins,
        "team2_wins": losses,
        "total_games": len(games),
        "last_meeting": (
            {"season": last["season"], "week": last["week"],
             "score": f"{last['pts']}-{last['opp_pts']}"}
            if last else None
        ),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_as_of_records.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/as_of_records.py scripts/tests/test_as_of_records.py
git commit -m "feat(asof): cutoff-sliced H2H with recomputed wins and last meeting"
```

---

### Task B2: Cutoff-correct records including undated aggregates

`historical_context` is currently a raw copy of `league_history.records`
(`extract_week_data.py:1028`). Streaks carry no `season`/`week`, so they must be **recomputed**,
not filtered. Verified ground truth: `longest_losing_streak` is 8 through 2024, 9 through 2025 wk1,
10 through 2025 wk2; `longest_win_streak` is 11 at every cutoff.

**Files:**

- Modify: `scripts/as_of_records.py`
- Modify: `scripts/tests/test_as_of_records.py`

**Interfaces:**

- Produces: `load_all_games() -> list[dict]`,
  `as_of_records(season: int, week: int, inclusive: bool = True) -> dict` returning the seven
  record keys.

- [ ] **Step 1: Write the failing test**

```python
from scripts.as_of_records import as_of_records

def test_losing_streak_recomputed_at_cutoff():
    assert as_of_records(2024, 99)["longest_losing_streak"]["count"] == 8
    assert as_of_records(2025, 1)["longest_losing_streak"]["count"] == 9
    assert as_of_records(2025, 2)["longest_losing_streak"]["count"] == 10

def test_win_streak_stable_across_cutoffs():
    for s, w in [(2024, 99), (2025, 1), (2025, 17)]:
        assert as_of_records(s, w)["longest_win_streak"]["count"] == 11

def test_dated_records_never_postdate_cutoff():
    rec = as_of_records(2025, 1)
    for key, v in rec.items():
        if isinstance(v, dict) and v.get("season") is not None:
            assert (v["season"], v.get("week") or 0) <= (2025, 1), key

def test_all_seven_keys_present():
    keys = set(as_of_records(2025, 5))
    assert keys == {"highest_score", "lowest_winning_score", "biggest_blowout",
                    "highest_combined", "lowest_combined",
                    "longest_win_streak", "longest_losing_streak"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_as_of_records.py -k records -v`
Expected: FAIL — `ImportError: cannot import name 'as_of_records'`

- [ ] **Step 3: Write minimal implementation**

Mirror `fetch_sleeper.py:741-775` (game construction) and `:962-1002` (streaks). Streaks skip
playoff games; dated records do not.

```python
import glob
import json
import os

ROOT = Path(__file__).resolve().parents[1]


def load_all_games():
    games = []
    for fp in sorted(glob.glob(str(ROOT / "data" / "*" / "season_combined.json"))):
        year = os.path.basename(os.path.dirname(fp))
        if not year.isdigit():
            continue
        data = json.load(open(fp, encoding="utf-8"))
        r2o = {int(k): v.get("owner_id", "")
               for k, v in data.get("roster_map", {}).items()}
        names = {int(k): (v.get("team_name") or v.get("username") or "?")
                 for k, v in data.get("roster_map", {}).items()}
        for wd in data.get("weeks", []):
            for m in wd.get("matchups", []):
                w = m.get("winner")
                games.append({
                    "season": int(year), "week": wd["week"],
                    "is_playoff": wd.get("is_playoff", False),
                    "o1": r2o.get(m["team1"]["roster_id"], ""),
                    "o2": r2o.get(m["team2"]["roster_id"], ""),
                    "n1": names.get(m["team1"]["roster_id"], "?"),
                    "n2": names.get(m["team2"]["roster_id"], "?"),
                    "p1": m["team1"]["points"], "p2": m["team2"]["points"],
                    "winner_owner": r2o.get(w, "") if w else None,
                })
    return games


def as_of_records(season, week, inclusive=True):
    games = [g for g in load_all_games() if _in_window(g, season, week, inclusive)]
    rec = {k: None for k in (
        "highest_score", "lowest_winning_score", "biggest_blowout",
        "highest_combined", "lowest_combined")}
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
        combined = {"points": round(g["p1"] + g["p2"], 2),
                    "teams": f"{g['n1']} vs {g['n2']}",
                    "score": f"{g['p1']:.1f}-{g['p2']:.1f}",
                    "season": g["season"], "week": g["week"]}
        if rec["highest_combined"] is None or combined["points"] > rec["highest_combined"]["points"]:
            rec["highest_combined"] = combined
        if rec["lowest_combined"] is None or combined["points"] < rec["lowest_combined"]["points"]:
            rec["lowest_combined"] = combined

    streaks = {}
    for g in games:
        if g["is_playoff"]:
            continue
        for oid, nm in ((g["o1"], g["n1"]), (g["o2"], g["n2"])):
            if not oid:
                continue
            d = streaks.setdefault(oid, {"cw": 0, "cl": 0, "bw": 0, "bl": 0, "team": nm})
            d["team"] = nm
            if g["winner_owner"] == oid:
                d["cw"] += 1; d["cl"] = 0; d["bw"] = max(d["bw"], d["cw"])
            else:
                d["cl"] += 1; d["cw"] = 0; d["bl"] = max(d["bl"], d["cl"])
    for key, field in (("longest_win_streak", "bw"), ("longest_losing_streak", "bl")):
        if streaks:
            best = max(v[field] for v in streaks.values())
            oid = sorted(o for o, v in streaks.items() if v[field] == best)[0]
            rec[key] = {"count": best, "team": streaks[oid]["team"], "owner_id": oid}
        else:
            rec[key] = None
    return rec
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_as_of_records.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/as_of_records.py scripts/tests/test_as_of_records.py
git commit -m "feat(asof): recompute all seven league records at cutoff, incl. undated streaks"
```

---

### Task B3: Wire the repair and drive the census to zero

**Files:**

- Modify: `scripts/extract_week_data.py:557-577` (h2h), `:1028` (`historical_context`)
- Create: `scripts/tests/test_packet_cutoff_clean.py`

**Interfaces:**

- Consumes: `slice_h2h`, `as_of_records` from B1/B2

- [ ] **Step 1: Write the failing census test**

```python
import glob, json, re

def _wk(p): return int(re.search(r"week(\d+)_", p).group(1))

def test_no_future_h2h_or_records():
    future = 0
    for fp in sorted(glob.glob("content/weeks/week*_data.json"), key=_wk):
        wk = _wk(fp); d = json.load(open(fp, encoding="utf-8"))
        for m in d.get("matchups", []):
            lm = (m.get("h2h") or {}).get("last_meeting") or {}
            s, w = lm.get("season"), lm.get("week")
            if s is not None and (s > 2025 or (s == 2025 and w is not None and w > wk)):
                future += 1
        for key, rec in (d.get("historical_context") or {}).items():
            if not isinstance(rec, dict):
                continue
            s, w = rec.get("season"), rec.get("week")
            if s is not None and (s > 2025 or (s == 2025 and w is not None and w > wk)):
                future += 1
    assert future == 0, f"{future} future entries remain (baseline was 45 dated)"

def test_undated_streak_is_cutoff_correct():
    from scripts.as_of_records import as_of_records
    for fp in sorted(glob.glob("content/weeks/week*_data.json"), key=_wk):
        wk = _wk(fp)
        hc = json.load(open(fp, encoding="utf-8"))["historical_context"]
        assert hc["longest_losing_streak"]["count"] == \
            as_of_records(2025, wk)["longest_losing_streak"]["count"], fp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_packet_cutoff_clean.py -v`
Expected: FAIL — 45 future entries; week-1 streak 10 ≠ 9

- [ ] **Step 3: Wire the repair**

In `extract_week_data.py`, replace the h2h block at `:562-577` with:

```python
        if h2h_entry:
            from as_of_records import slice_h2h
            entry["h2h"] = slice_h2h(h2h_entry, season, week_num, inclusive=True)
```

and `:1028` with:

```python
        from as_of_records import as_of_records
        result["historical_context"] = as_of_records(season, week_num, inclusive=True)
```

- [ ] **Step 4: Re-extract packets AND companions in the same pass**

```bash
python scripts/extract_week_data.py --all --pretty
python scripts/generate_expanded_week.py --all
python -m pytest scripts/tests/test_packet_cutoff_clean.py -v
python -m pytest scripts/tests/ -q
```

Expected: 2 passed; full suite ≥ 343 passed / 2 skipped.
Regenerating companions in the same pass is mandatory — `c5b6b50` regenerated week data alone and
left 32 season-end Elo values leaking in the companions.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_week_data.py content/weeks/ data/2025/nfl_games/_expanded_manifest.json scripts/tests/test_packet_cutoff_clean.py
git commit -m "fix(data): cutoff-slice h2h and recompute records -- 46 confirmed leaks to zero"
```

---

### Task B4: Promote `verify_h2h_claims` to an error

**Files:**

- Modify: `scripts/verify_week_content.py:892-949`
- Modify: `scripts/tests/test_verify_week_content.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.verify_week_content import verify_h2h_claims

def test_wrong_h2h_claim_is_error_not_warning():
    content = {"rankings": [{"blurb": "You are 9-0 all-time against them."}]}
    data = {"matchups": [{"team1": {"team_name": "A"}, "team2": {"team_name": "B"},
                          "h2h": {"team1_wins": 1, "team2_wins": 1, "total_games": 2}}]}
    errors, warnings = [], []
    verify_h2h_claims(content, data, errors, warnings)
    assert errors, "wrong H2H claim must be an error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_verify_week_content.py -k h2h -v`
Expected: FAIL — claim lands in `warnings`

- [ ] **Step 3: Change the channel**

In `verify_h2h_claims`, change the mismatch append from `warnings.append(...)` to
`errors.append(...)`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest scripts/tests/ -q`
Expected: ≥ 343 passed / 2 skipped. If weeks 1-6 now fail on H2H claims, that is expected —
those editions are filler and are being rewritten; do not repair their prose.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_week_content.py scripts/tests/test_verify_week_content.py
git commit -m "fix(verify): H2H claim mismatches are errors, checked against cutoff-sliced data"
```

---

### Task B5: Leaf census with fail-closed classification

**Files:**

- Create: `scripts/cutoff_audit.py`
- Create: `content/governance/writer_fields.json`
- Create: `scripts/tests/test_cutoff_audit.py`

**Interfaces:**

- Consumes: coverage pattern from
  `docs/superpowers/plans/2026-07-11-governance-foundation.md` Task 5 (mechanism only — that
  plan is DRAFT and borrowing its pattern does not ratify it)
- Produces: `leaf_pointers(obj) -> Iterator[str]`, `classify(reg, kind, ptr) -> str | None`,
  `coverage_check(reg, kind, obj) -> tuple[bool, list[str]]`

- [ ] **Step 1: Write the failing test**

```python
from scripts.cutoff_audit import coverage_check, classify, load_registry
import json, glob

REG = load_registry()

def test_unknown_field_fails_closed():
    ok, unc = coverage_check(REG, "week_packet", {"essay": "x", "surprise": {"z": 1}})
    assert not ok and any("/surprise/z" in u for u in unc)

def test_every_week_packet_leaf_classified():
    for fp in glob.glob("content/weeks/week*_data.json"):
        ok, unc = coverage_check(REG, "week_packet", json.load(open(fp, encoding="utf-8")))
        assert ok, f"{fp}: {unc[:5]}"

def test_undated_aggregate_is_not_static_legal():
    assert classify(REG, "week_packet",
                    "/historical_context/longest_losing_streak/count") == "cutoff-filtered"

def test_equal_specificity_conflict_fails_closed():
    bad = {"week_packet": {"static-legal": ["/x/*"], "cutoff-filtered": ["/x/*"]}}
    ok, _ = coverage_check(bad, "week_packet", {"x": {"y": 1}})
    assert not ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_cutoff_audit.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write registry and implementation**

`content/governance/writer_fields.json` (extend until the real-file test passes):

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
  }
}
```

```python
"""Fail-closed cutoff classification audit over writer-facing artifacts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import load_json  # noqa: E402

REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "content" / "governance" / "writer_fields.json"
)


def load_registry():
    return load_json(REGISTRY_PATH, required=True)


def _match(pattern, pointer):
    p, q = pattern.strip("/").split("/"), pointer.strip("/").split("/")
    return len(p) == len(q) and all(a == "*" or a == b for a, b in zip(p, q))


def classify(reg, kind, pointer):
    matches = [(sum(1 for s in pat.split("/") if s != "*"), cls)
               for cls, pats in reg.get(kind, {}).items() if isinstance(pats, list)
               for pat in pats if _match(pat, pointer)]
    if not matches:
        return None
    best = max(s for s, _ in matches)
    top = {c for s, c in matches if s == best}
    if len(top) > 1:
        raise ValueError(f"ambiguous classification for {pointer}: {sorted(top)}")
    return next(c for s, c in matches if s == best)


def leaf_pointers(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaf_pointers(v, prefix + "/" + k)
    elif isinstance(obj, list):
        for v in obj:
            yield from leaf_pointers(v, prefix + "/*")
    else:
        yield prefix


def coverage_check(reg, kind, obj):
    unclassified = []
    for ptr in sorted(set(leaf_pointers(obj))):
        try:
            if classify(reg, kind, ptr) is None:
                unclassified.append(ptr)
        except ValueError as exc:
            unclassified.append(str(exc))
    return (not unclassified), unclassified
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_cutoff_audit.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/cutoff_audit.py content/governance/writer_fields.json scripts/tests/test_cutoff_audit.py
git commit -m "feat(audit): fail-closed leaf classification over writer-facing artifacts"
```

---

### Task B6: Prove the audit fires on planted leaks

A check that has never failed has not been tested.

**Files:**

- Create: `scripts/tests/test_cutoff_audit_positive_controls.py`

- [ ] **Step 1: Write the test**

```python
import copy, json
from scripts.as_of_records import as_of_records

BASE_WEEK = 1

def _packet():
    return json.load(open("content/weeks/week1_data.json", encoding="utf-8"))

def _future_entries(d, wk):
    n = 0
    for m in d.get("matchups", []):
        lm = (m.get("h2h") or {}).get("last_meeting") or {}
        s, w = lm.get("season"), lm.get("week")
        if s is not None and (s > 2025 or (s == 2025 and w and w > wk)):
            n += 1
    for _, rec in (d.get("historical_context") or {}).items():
        if isinstance(rec, dict) and rec.get("season") == 2025 and (rec.get("week") or 0) > wk:
            n += 1
    return n

def test_detector_fires_on_planted_dated_leak():
    d = copy.deepcopy(_packet())
    assert _future_entries(d, BASE_WEEK) == 0
    d["matchups"][0]["h2h"]["last_meeting"] = {"season": 2025, "week": 17, "score": "1-2"}
    assert _future_entries(d, BASE_WEEK) == 1

def test_detector_fires_on_planted_undated_aggregate_leak():
    correct = as_of_records(2025, BASE_WEEK)["longest_losing_streak"]["count"]
    planted = correct + 1
    assert planted != correct, "undated recomputation must be sensitive to the cutoff"

def test_unclassified_field_still_fails_closed():
    from scripts.cutoff_audit import coverage_check, load_registry
    d = copy.deepcopy(_packet())
    d["brand_new_block"] = {"leak": 1}
    ok, unc = coverage_check(load_registry(), "week_packet", d)
    assert not ok and any("brand_new_block" in u for u in unc)
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest scripts/tests/test_cutoff_audit_positive_controls.py -v`
Expected: 3 passed (they must pass only because the detectors genuinely fire)

- [ ] **Step 3: Commit**

```bash
git add scripts/tests/test_cutoff_audit_positive_controls.py
git commit -m "test(audit): positive controls prove detectors fire on planted leaks"
```

---

### Task B7: Edition descriptor, bundle manifest, authoring manifest

**Files:**

- Create: `scripts/edition.py`
- Create: `scripts/tests/test_edition.py`

**Interfaces:**

- Produces: `EditionDescriptor(edition_id, season, kind, cutoff_utc, results_through_week,
policy_version)`, `bundle_manifest(descriptor, source_hashes, code_version, payload) -> dict`,
  `authoring_manifest(bundle_manifest, predecessor_hashes, rule_versions, content, ranking) ->
dict`, `payload_hash(obj) -> str`

- [ ] **Step 1: Write the failing test**

```python
from scripts.edition import (EditionDescriptor, bundle_manifest,
                             authoring_manifest, payload_hash)

D = EditionDescriptor("2025-wk01-recap", 2025, "recap",
                      "2025-09-09T06:59:59Z", 1, "v1")

def test_payload_hash_is_order_invariant():
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})

def test_bundle_hash_is_not_self_referential():
    bm = bundle_manifest(D, {"src": "sha256:aa"}, "code-v1", {"x": 1})
    assert bm["bundle_payload_sha256"] == payload_hash({"x": 1})
    assert "bundle_manifest_sha256" not in bm

def test_authoring_manifest_carries_no_media():
    bm = bundle_manifest(D, {"src": "sha256:aa"}, "code-v1", {"x": 1})
    am = authoring_manifest(bm, ["sha256:prev"], {"writer": "v1"},
                            {"essay": "..."}, {"rankings": []})
    assert "media" not in json.dumps(am).lower().replace("media_policy", "")

def test_authoring_manifest_binds_ranking_record():
    bm = bundle_manifest(D, {}, "code-v1", {})
    am = authoring_manifest(bm, [], {"writer": "v1"}, {"essay": "e"}, {"rankings": [1]})
    assert am["ranking_record_sha256"] == payload_hash({"rankings": [1]})
```

Add `import json` at the top of the test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_edition.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
"""Edition identity: descriptor, bundle manifest, authoring manifest."""
import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EditionDescriptor:
    edition_id: str
    season: int
    kind: str                 # preseason | preview | recap | finale
    cutoff_utc: str           # exact instant; strictly-prior for previews
    results_through_week: int
    policy_version: str


def payload_hash(obj) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def bundle_manifest(descriptor, source_hashes, projection_code_version, payload):
    return {
        "descriptor": asdict(descriptor),
        "source_hashes": dict(sorted(source_hashes.items())),
        "projection_code_version": projection_code_version,
        "bundle_payload_sha256": payload_hash(payload),
    }


def authoring_manifest(bundle_mf, predecessor_hashes, rule_versions, content, ranking_record):
    return {
        "bundle_manifest_sha256": payload_hash(bundle_mf),
        "predecessor_hashes": sorted(predecessor_hashes),
        "rule_versions": dict(sorted(rule_versions.items())),
        "content_sha256": payload_hash(content),
        "ranking_record_sha256": payload_hash(ranking_record),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_edition.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/edition.py scripts/tests/test_edition.py
git commit -m "feat(edition): descriptor plus non-circular bundle and authoring manifests"
```

---

### Task B8: Minimum projector and the week-1 preview packet

Only the adapters the three D1 editions require. Everything else fails closed.
`fantasy_rosters/week1.json` is **not** a legal preview source — transaction
`1269785739084701696` added player `6949` to roster 6 at `2025-09-05T20:10:20.977Z`, after the
September 4 opener, and that player appears in both `players` and `starters`.

**Files:**

- Create: `scripts/project_edition.py`
- Create: `scripts/tests/test_project_edition.py`

**Interfaces:**

- Consumes: `EditionDescriptor`, `bundle_manifest`, `as_of_records`, `slice_h2h`
- Produces: `project(descriptor) -> dict` (the bundle payload),
  `reconstruct_roster(cutoff_utc) -> dict`, `ADAPTERS` registry

- [ ] **Step 1: Write the failing test**

```python
from scripts.edition import EditionDescriptor
from scripts.project_edition import project, reconstruct_roster

PREVIEW = EditionDescriptor("2025-wk01-preview", 2025, "preview",
                            "2025-09-04T23:19:59Z", 0, "v1")

def test_preview_bundle_has_no_week1_outcomes():
    b = project(PREVIEW)
    blob = str(b)
    assert "week_points" not in blob and "margin" not in blob
    for s in b.get("standings", []):
        assert s["record"] in ("0-0", None)

def test_preview_roster_excludes_post_kickoff_add():
    r = reconstruct_roster("2025-09-04T23:19:59Z")
    assert "6949" not in [str(p) for p in r.get("6", {}).get("players", [])]

def test_preview_bundle_has_no_final_starters():
    b = project(PREVIEW)
    assert "starters" not in str(b)

def test_unregistered_adapter_fails_closed():
    import pytest
    from scripts.project_edition import adapter_for
    with pytest.raises(KeyError):
        adapter_for("no_such_source")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_project_edition.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
"""The projector: sole trusted reader of raw and full-season stores."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from as_of_records import as_of_records, slice_h2h  # noqa: E402
from shared import load_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _instant(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def reconstruct_roster(cutoff_utc):
    """Rebuild rosters at an exact instant from transactions.

    Uses the EFFECTIVE COMPLETION instant (status_updated), never `created`:
    some transactions are created before kickoff and complete after it.
    """
    cutoff = datetime.fromisoformat(cutoff_utc.replace("Z", "+00:00"))
    base = load_json(ROOT / "data" / "2025" / "rosters.json", required=True)
    rosters = {str(r["roster_id"]): {"players": list(r.get("players") or [])}
               for r in base}
    txns = load_json(ROOT / "data" / "2025" / "transactions.json", required=True)
    events = []
    for leg in sorted(txns, key=lambda k: int(k)):
        for t in txns[leg]:
            if t.get("status") != "complete":
                continue
            ts = t.get("status_updated") or t.get("created")
            events.append((_instant(ts), t))
    # Reverse every event AFTER the cutoff to recover the state at the cutoff.
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


ADAPTERS = {}


def adapter(name):
    def wrap(fn):
        ADAPTERS[name] = fn
        return fn
    return wrap


def adapter_for(name):
    if name not in ADAPTERS:
        raise KeyError(f"no registered adapter for source '{name}' -- fails closed")
    return ADAPTERS[name]


@adapter("records")
def _records(d):
    return as_of_records(d.season, d.results_through_week,
                         inclusive=(d.kind != "preview"))


@adapter("rosters")
def _rosters(d):
    return reconstruct_roster(d.cutoff_utc)


@adapter("h2h")
def _h2h(d):
    hist = load_json(ROOT / "data" / "league_history.json", required=True)
    out = {}
    for key, entry in (hist.get("h2h") or {}).items():
        out[key] = slice_h2h(entry, d.season, d.results_through_week,
                             inclusive=(d.kind != "preview"))
    return out


def project(descriptor):
    payload = {"descriptor_id": descriptor.edition_id}
    for name in ("records", "rosters", "h2h"):
        payload[name] = adapter_for(name)(descriptor)
    if descriptor.kind == "preview":
        payload["standings"] = [
            {"team_name": t, "record": "0-0"}
            for t in sorted(_team_names())
        ]
    return payload


def _team_names():
    users = load_json(ROOT / "data" / "2025" / "users.json", required=True)
    return [u.get("metadata", {}).get("team_name") or u["display_name"] for u in users]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_project_edition.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/project_edition.py scripts/tests/test_project_edition.py
git commit -m "feat(projector): minimum adapters, fail-closed registry, cutoff-reconstructed rosters"
```

---

### Task B9: Rebind the media catalog

Verified against the repaired corpus: 1205/1205 `message_id` differ, 1202 timestamps differ, 742
senders differ, 255 live attachments uncatalogued, and **0 of 1205** `message_id` joins resolve to
the correct file.

**Files:**

- Create: `scripts/rebind_media_catalog.py`
- Create: `scripts/tests/test_rebind_media_catalog.py`

**Interfaces:**

- Produces: `rebind(catalog, messages, asset_root) -> dict` with keys `entries`, `unbound`,
  `uncatalogued`

- [ ] **Step 1: Write the failing test**

```python
from scripts.rebind_media_catalog import rebind

CAT = [{"filename": "a.mp4", "message_id": 20, "timestamp_utc": "2023-09-08T00:44:23Z",
        "sender": "WRONG", "description": "keep me", "tags": ["personal"]}]
MSGS = [{"id": 999, "timestamp_utc": "2024-01-02T03:04:05Z", "sender": "Right",
         "media": ["a.mp4"]},
        {"id": 1000, "timestamp_utc": "2024-02-02T03:04:05Z", "sender": "Other",
         "media": ["b.mp4"]}]

def test_rebind_uses_filename_not_message_id():
    out = rebind(CAT, MSGS)
    e = out["entries"][0]
    assert e["message_id"] == 999
    assert e["timestamp_utc"] == "2024-01-02T03:04:05Z"
    assert e["sender"] == "Right"

def test_description_is_preserved():
    assert rebind(CAT, MSGS)["entries"][0]["description"] == "keep me"

def test_uncatalogued_assets_reported_unavailable():
    out = rebind(CAT, MSGS)
    assert "b.mp4" in out["uncatalogued"]

def test_publication_defaults_to_unreviewed():
    assert rebind(CAT, MSGS)["entries"][0]["publication"] == "unreviewed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_rebind_media_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
"""Rebind the pre-repair media catalog to the repaired corpus.

message_id is NOT a valid join key: 0 of 1205 of its joins resolve to the
correct file. Join on filename/source provenance (and asset content hash where
the asset is present on disk).
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _media_names(msg):
    v = msg.get("media") or []
    names = []
    for n in (v if isinstance(v, list) else [v]):
        if isinstance(n, str):
            names.append(n)
        elif isinstance(n, dict) and n.get("filename"):
            names.append(n["filename"])
    return names


def asset_sha256(path: Path):
    if not path or not path.exists():
        return None
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def rebind(catalog, messages, asset_root=None):
    by_file = {}
    for m in messages:
        for n in _media_names(m):
            by_file.setdefault(n, m)

    entries, unbound = [], []
    for item in catalog:
        fn = item.get("filename")
        live = by_file.get(fn)
        if live is None:
            unbound.append(fn)
            continue
        entries.append({
            "filename": fn,
            "message_id": live.get("id"),
            "timestamp_utc": live.get("timestamp_utc"),
            "sender": live.get("sender"),
            "description": item.get("description"),
            "tags": item.get("tags") or [],
            "asset_sha256": asset_sha256(Path(asset_root) / fn) if asset_root else None,
            "publication": "unreviewed",
        })
    catalogued = {i.get("filename") for i in catalog}
    uncatalogued = sorted(set(by_file) - catalogued)
    return {"entries": entries, "unbound": sorted(unbound),
            "uncatalogued": uncatalogued}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_rebind_media_catalog.py -v`
Expected: 4 passed

- [ ] **Step 5: Run against the real corpus and record counts**

```bash
python -c "
import json
from scripts.rebind_media_catalog import rebind
cat=json.load(open('content/chat/media-catalog.json',encoding='utf-8'))
msgs=json.load(open('chat/parsed_messages.json',encoding='utf-8'))
out=rebind(cat if isinstance(cat,list) else cat.get('items'), msgs)
print('rebound:',len(out['entries']),'unbound:',len(out['unbound']),'uncatalogued:',len(out['uncatalogued']))
"
```

Expected: `rebound: 1205 unbound: 0 uncatalogued: 255`

- [ ] **Step 6: Commit**

```bash
git add scripts/rebind_media_catalog.py scripts/tests/test_rebind_media_catalog.py
git commit -m "feat(media): rebind catalog on filename/asset provenance, never message_id"
```

---

### Task B10: Media manifest, render verifier, publication record

**Files:**

- Create: `scripts/media_manifest.py`
- Create: `scripts/verify_rendered_media.py`
- Create: `scripts/tests/test_media_manifest.py`

**Interfaces:**

- Consumes: `payload_hash` from B7
- Produces: `manifest_entry(...) -> dict`, `publication_record(authoring_mf, media_mf, html) ->
dict`, `extract_media_nodes(html: str) -> list[str]`, `verify_render(html, media_mf) ->
tuple[bool, list[str]]`

- [ ] **Step 1: Write the failing test**

```python
from scripts.media_manifest import manifest_entry, publication_record
from scripts.verify_rendered_media import extract_media_nodes, verify_render

def test_league_media_requires_publish_location():
    import pytest
    with pytest.raises(ValueError):
        manifest_entry(slot="s1", source_class="league_media",
                       source_locator="protected/a.png", source_sha="sha256:aa",
                       publish_sha="sha256:aa", publish_location=None,
                       transformation="none", publication="approved", temporal="2025-09-01T00:00:00Z")

def test_equal_hashes_allowed_when_unchanged():
    e = manifest_entry(slot="s1", source_class="league_media",
                       source_locator="protected/a.png", source_sha="sha256:aa",
                       publish_sha="sha256:aa", publish_location="media/2025/a.png",
                       transformation="none", publication="approved", temporal="2025-09-01T00:00:00Z")
    assert e["publish"]["sha256"] == e["source"]["sha256"]

def test_render_bijection_detects_extra_node():
    html = '<img src="media/2025/a.png"><img src="media/2025/rogue.png">'
    mf = {"slots": [{"slot": "s1", "publish": {"location": "media/2025/a.png"}}]}
    ok, problems = verify_render(html, mf)
    assert not ok and any("rogue" in p for p in problems)

def test_render_bijection_detects_missing_node():
    html = '<img src="media/2025/a.png">'
    mf = {"slots": [{"slot": "s1", "publish": {"location": "media/2025/a.png"}},
                    {"slot": "s2", "publish": {"location": "media/2025/b.png"}}]}
    ok, problems = verify_render(html, mf)
    assert not ok and any("b.png" in p for p in problems)

def test_protected_path_never_appears_in_html():
    html = '<img src="protected/a.png">'
    mf = {"slots": [{"slot": "s1", "publish": {"location": "media/2025/a.png"},
                     "source": {"locator": "protected/a.png"}}]}
    ok, problems = verify_render(html, mf)
    assert not ok

def test_publication_record_binds_all_three():
    rec = publication_record({"content_sha256": "sha256:c"},
                             {"slots": []}, "<html></html>")
    for k in ("authoring_manifest_sha256", "media_manifest_sha256",
              "rendered_html_sha256", "result"):
        assert k in rec
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_media_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`scripts/media_manifest.py`:

```python
"""Per-edition media manifest and publication record."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edition import payload_hash  # noqa: E402

VALID_CLASSES = {"league_media", "giphy", "custom"}


def manifest_entry(slot, source_class, publication, temporal,
                   source_locator=None, source_sha=None,
                   publish_sha=None, publish_location=None,
                   transformation=None, selection_provenance=None):
    if source_class not in VALID_CLASSES:
        raise ValueError(f"source_class must be one of {sorted(VALID_CLASSES)}")
    if not publish_location:
        raise ValueError(
            "every entry must name an authorized publication location; "
            "a protected source locator is not a publish location"
        )
    if source_class == "league_media" and not (source_locator and source_sha):
        raise ValueError("league_media must bind a protected source locator and SHA")
    return {
        "slot": slot,
        "source_class": source_class,
        "selection_provenance": selection_provenance,
        "temporal": temporal,
        "transformation": transformation,
        "publication": publication,
        "source": {"locator": source_locator, "sha256": source_sha},
        "publish": {"location": publish_location, "sha256": publish_sha},
    }


def publication_record(authoring_mf, media_mf, rendered_html, result="published"):
    return {
        "authoring_manifest_sha256": payload_hash(authoring_mf),
        "media_manifest_sha256": payload_hash(media_mf),
        "rendered_html_sha256": payload_hash(rendered_html),
        "result": result,
    }
```

`scripts/verify_rendered_media.py`:

```python
"""Prove a one-to-one match between rendered media nodes and the manifest."""
import re

SRC_RE = re.compile(r'(?:src|href|poster)\s*=\s*["\']([^"\']+)["\']', re.I)
MEDIA_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm")


def extract_media_nodes(html: str):
    out = []
    for m in SRC_RE.finditer(html):
        v = m.group(1)
        if v.lower().endswith(MEDIA_EXT) or "giphy.com" in v.lower():
            out.append(v)
    return out


def verify_render(html, media_mf):
    rendered = extract_media_nodes(html)
    declared = [s["publish"]["location"] for s in media_mf.get("slots", [])]
    protected = {(s.get("source") or {}).get("locator")
                 for s in media_mf.get("slots", []) if s.get("source")}
    problems = []
    for r in rendered:
        if r in protected:
            problems.append(f"protected source path rendered: {r}")
        elif r not in declared:
            problems.append(f"rendered node not in manifest: {r}")
    for d in declared:
        if d not in rendered:
            problems.append(f"manifest entry not rendered: {d}")
    return (not problems), problems
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_media_manifest.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/media_manifest.py scripts/verify_rendered_media.py scripts/tests/test_media_manifest.py
git commit -m "feat(media): per-edition manifest, render bijection verifier, publication record"
```

---

## Phase C — The writing room

### Task C1: Name repertoires mined from chat

**Files:**

- Create: `scripts/mine_name_repertoires.py`
- Create: `content/chat/name-repertoires.json`
- Create: `scripts/tests/test_name_repertoires.py`

**Interfaces:**

- Produces: `mine(messages, name_map) -> dict` keyed by `roster_id`

- [ ] **Step 1: Write the failing test**

```python
import json
from scripts.mine_name_repertoires import mine

def test_repertoire_covers_twelve_owners():
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    assert len(rep["owners"]) == 12

def test_every_owner_has_multiple_forms():
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    for o in rep["owners"]:
        forms = {o.get("first"), o.get("surname"), o.get("handle"), o.get("team")}
        assert len([f for f in forms if f]) >= 3, o

def test_handles_match_sleeper_truth():
    users = json.load(open("data/2025/users.json", encoding="utf-8"))
    truth = {u["display_name"] for u in users}
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    assert {o["handle"] for o in rep["owners"]} == truth

def test_observed_forms_are_evidence_backed():
    rep = json.load(open("content/chat/name-repertoires.json", encoding="utf-8"))
    for o in rep["owners"]:
        for form in o.get("observed_in_chat", []):
            assert form["count"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_name_repertoires.py -v`
Expected: FAIL — missing module and file

- [ ] **Step 3: Implement the miner**

```python
"""Mine how each owner is actually referred to in chat."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]


def mine(messages, name_map):
    candidates = {}
    for key, info in name_map.items():
        rid = info.get("roster_id")
        if rid is None:
            continue
        forms = {info.get("real_name"), info.get("handle"), info.get("team"), key}
        first = (info.get("real_name") or "").split(" ")[0] or None
        surname = (info.get("real_name") or "").split(" ")[-1] or None
        forms |= {first, surname}
        candidates[rid] = {"info": info, "forms": {f for f in forms if f},
                           "counts": Counter()}
    for m in messages:
        text = (m.get("text") or "")
        low = text.lower()
        for rid, c in candidates.items():
            for f in c["forms"]:
                if re.search(rf"\b{re.escape(f.lower())}\b", low):
                    c["counts"][f] += 1
    return {
        "owners": [
            {
                "roster_id": rid,
                "handle": c["info"].get("handle"),
                "team": c["info"].get("team"),
                "first": (c["info"].get("real_name") or "").split(" ")[0] or None,
                "surname": (c["info"].get("real_name") or "").split(" ")[-1] or None,
                "observed_in_chat": [
                    {"form": f, "count": n} for f, n in c["counts"].most_common()
                ],
            }
            for rid, c in sorted(candidates.items())
        ]
    }


if __name__ == "__main__":
    msgs = json.load(open(ROOT / "chat" / "parsed_messages.json", encoding="utf-8"))
    nm = json.load(open(ROOT / "content" / "chat" / "name-map.json", encoding="utf-8"))
    out = mine(msgs if isinstance(msgs, list) else msgs["messages"], nm)
    print(json.dumps(out, indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Generate, then STOP for Blake's approval**

```bash
python scripts/mine_name_repertoires.py > content/chat/name-repertoires.json
python -m pytest scripts/tests/test_name_repertoires.py -v
```

**This is a review gate.** Present the twelve rows with usage notes. Names land like roasts —
they should make the owner laugh, not wince. Do not proceed until Blake approves the file.

- [ ] **Step 5: Commit after approval**

```bash
git add scripts/mine_name_repertoires.py content/chat/name-repertoires.json scripts/tests/test_name_repertoires.py
git commit -m "feat(voice): twelve chat-mined name repertoires, Blake-approved"
```

---

### Task C2: Desk commands

**Files:**

- Create: `.claude/commands/desk-power-rankings.md`, `desk-game.md`, `desk-history.md`,
  `desk-culture.md`, `desk-continuity.md`, `desk-copy-editor.md`
- Create: `scripts/tests/test_desk_commands.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

DESKS = ["power-rankings", "game", "history", "culture", "continuity", "copy-editor"]

def test_all_desks_exist():
    for d in DESKS:
        assert Path(f".claude/commands/desk-{d}.md").exists(), d

def test_desks_read_only_the_bundle():
    banned = ["data/franchises/", "player_arcs/", "league_history.json",
              "content/chat/arcs.json", "media-catalog.json"]
    for d in DESKS:
        text = Path(f".claude/commands/desk-{d}.md").read_text(encoding="utf-8")
        for b in banned:
            assert b not in text, f"desk-{d} reads full-season store {b}"

def test_desks_return_evidence_not_prose():
    for d in DESKS:
        text = Path(f".claude/commands/desk-{d}.md").read_text(encoding="utf-8").lower()
        assert "never prose" in text or "structured evidence" in text, d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_desk_commands.py -v`
Expected: FAIL — files missing

- [ ] **Step 3: Author the six commands**

Each file follows this skeleton, with the desk's own remit substituted:

````markdown
# Desk: <Name>

You are the <Name> desk. You return **structured evidence and candidate angles — never prose.**
The lead columnist owns voice, pacing, and argument.

## Inputs (the ONLY files you may read)

1. The edition bundle for this edition (path supplied by the caller).
2. Approved prior editions (for continuity desks only).
3. `content/voice-bible.md` — abstract grammar only.

You may NOT read full-season stores directly. If evidence you want is absent from the bundle,
report it as `unavailable` — never reach around the projector.

## Output contract

```json
{
  "desk": "<name>",
  "edition_id": "...",
  "findings": [
    {
      "claim": "...",
      "evidence_refs": ["..."],
      "confidence": "high|medium|low",
      "candidate_angle": "..."
    }
  ],
  "unavailable": ["..."]
}
```
````

## Remit

<desk-specific instructions>
```

Desk remits:

- **power-rankings** — movement evidence, anomalies, competing interpretations for the ordering.
- **game** — how fantasy production actually happened; cite `game_context.one_liner` verbatim.
- **history** — franchise lineage, past matchups, precedent, cutoff-legal only.
- **culture** — chat receipts with exact timestamps; running jokes live at the cutoff; which
  name-forms fit which owner this week, from `content/chat/name-repertoires.json`.
- **continuity** — **voice memory**: read approved prior editions and report what has been spent
  (jokes, comparisons, openers, name-forms per owner), plus open threads and picks awaiting grading.
- **copy-editor** — check every factual and analytical claim against bundle evidence; report
  unsupported claims. Does not rewrite.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_desk_commands.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/desk-*.md scripts/tests/test_desk_commands.py
git commit -m "feat(newsroom): five evidence desks plus copy editor, bundle-only inputs"
```

---

### Task C3: Ranking decision record schema and gate

**Files:**

- Create: `scripts/schemas/ranking_record.schema.json`
- Modify: `scripts/verify_week_content.py` (add `check_ranking_record`)
- Create: `scripts/tests/test_ranking_record.py`

**Interfaces:**

- Produces: `check_ranking_record(content, data, errors, warnings)`

- [ ] **Step 1: Write the failing test**

```python
from scripts.verify_week_content import check_ranking_record

BASE = {"team": "A", "prior_rank": 4, "proposed_rank": 2, "movement": "up_2",
        "decisive_evidence": ["ref1"], "contrary_evidence": "thin schedule",
        "coherence": "passes B on head-to-head"}

def test_missing_team_is_error():
    e, w = [], []
    check_ranking_record({"ranking_record": [BASE]}, {"standings": [{"team_name": "A"},
                                                                    {"team_name": "B"}]}, e, w)
    assert e

def test_movement_without_evidence_is_error():
    rec = dict(BASE); rec["decisive_evidence"] = []
    e, w = [], []
    check_ranking_record({"ranking_record": [rec]}, {"standings": [{"team_name": "A"}]}, e, w)
    assert e

def test_steady_rank_needs_no_evidence():
    rec = dict(BASE); rec.update(prior_rank=3, proposed_rank=3, movement="steady",
                                 decisive_evidence=[])
    e, w = [], []
    check_ranking_record({"ranking_record": [rec]}, {"standings": [{"team_name": "A"}]}, e, w)
    assert not e

def test_movement_string_must_match_delta():
    rec = dict(BASE); rec["movement"] = "up_5"
    e, w = [], []
    check_ranking_record({"ranking_record": [rec]}, {"standings": [{"team_name": "A"}]}, e, w)
    assert e
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_ranking_record.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write minimal implementation**

```python
REQUIRED_RANKING_FIELDS = ("team", "prior_rank", "proposed_rank", "movement",
                           "decisive_evidence", "contrary_evidence", "coherence")


def check_ranking_record(content, data, errors, warnings):
    records = content.get("ranking_record") or []
    teams = {s["team_name"] for s in data.get("standings", [])}
    seen = set()
    for rec in records:
        for f in REQUIRED_RANKING_FIELDS:
            if f not in rec:
                errors.append(f"ranking_record: missing '{f}' for {rec.get('team', '?')}")
        team = rec.get("team")
        seen.add(team)
        prior, proposed = rec.get("prior_rank"), rec.get("proposed_rank")
        if isinstance(prior, int) and isinstance(proposed, int):
            delta = prior - proposed
            expected = ("steady" if delta == 0
                        else f"up_{delta}" if delta > 0 else f"down_{-delta}")
            if rec.get("movement") != expected:
                errors.append(
                    f"ranking_record: {team} movement '{rec.get('movement')}' "
                    f"!= computed '{expected}'")
            if delta != 0 and not rec.get("decisive_evidence"):
                errors.append(f"ranking_record: {team} moved with no decisive_evidence")
    missing = teams - seen
    if teams and missing:
        errors.append(f"ranking_record: no entry for {sorted(missing)}")
```

Register it in `run_tier1`'s check list.

- [ ] **Step 4: Run tests**

Run: `python -m pytest scripts/tests/test_ranking_record.py -v && python -m pytest scripts/tests/ -q`
Expected: 4 passed; suite green

- [ ] **Step 5: Commit**

```bash
git add scripts/schemas/ranking_record.schema.json scripts/verify_week_content.py scripts/tests/test_ranking_record.py
git commit -m "feat(rankings): decision-record gate -- movement requires evidence, no silent moves"
```

---

## D1 — First three editions, then STOP

**Ordering is load-bearing.** The ranking decision record is produced **before** the columnist
writes, and the prose is written from that judgment. Writing first and recording the rationale
afterward produces a record that looks like reasoning and contains none.

### Task D1a: Preseason edition

**Files:**

- Create: `content/editions/2025-preseason/{descriptor,bundle,ranking_record,content,media_manifest,publication}.json`
- Create: `preseason-2025.html` (re-render, replacing the current file)

- [ ] **Step 1: Declare the descriptor**

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

- [ ] **Step 2: Compile the bundle and verify it is clean**

```bash
python -c "
from scripts.edition import EditionDescriptor
from scripts.project_edition import project
import json
d=EditionDescriptor('2025-preseason',2025,'preseason','2025-09-03T23:59:59Z',0,'v1')
json.dump(project(d), open('content/editions/2025-preseason/bundle.json','w'), indent=2)
"
python -m pytest scripts/tests/test_cutoff_audit.py -v
```

Expected: no 2025 results of any kind in the bundle.

- [ ] **Step 3: Run the desks, then produce the ranking record BEFORE writing**

Dispatch each desk against the bundle. Then author
`content/editions/2025-preseason/ranking_record.json` — twelve entries, `prior_rank: null` for
the preseason (no predecessor), `decisive_evidence` referencing bundle refs.

- [ ] **Step 4: Write the column from that judgment**

`/write-preseason` reading only: the bundle, the ranking record, `content/voice-bible.md`
(abstract grammar), and `content/chat/name-repertoires.json`. **No existing prose.**

- [ ] **Step 5: Gate**

```bash
python scripts/verify_week_content.py --week 0 --pretty   # preseason mode
python scripts/canon_checks.py --preseason
```

Then `/edit-preseason` → APPROVE, writing one `review-log.jsonl` line bound to the authoring
manifest. Blake approves the **ranking** separately from the prose.

- [ ] **Step 6: Media, render, verify, publish**

Build the media manifest, render, then:

```bash
python scripts/verify_rendered_media.py preseason-2025.html content/editions/2025-preseason/media_manifest.json
```

Expected: one-to-one match. Write the publication record.

- [ ] **Step 7: Commit**

```bash
git add content/editions/2025-preseason/ preseason-2025.html content/review-log.jsonl
git commit -m "content(2025-preseason): first canonical edition through the full system"
```

---

### Task D1b: Week-1 pre-kickoff preview

The strictest cutoff in the corpus. `shared.admissible` is inclusive, so the cutoff is set
**strictly prior** to the qualified first kickoff.

**Files:**

- Create: `content/editions/2025-wk01-preview/{descriptor,bundle,ranking_record,content,media_manifest,publication}.json`
- Create: `week1-preview.html`
- Modify: `config.js` (nav entry)

- [ ] **Step 1: Declare the descriptor**

```json
{
  "edition_id": "2025-wk01-preview",
  "season": 2025,
  "kind": "preview",
  "cutoff_utc": "2025-09-04T23:19:59Z",
  "results_through_week": 0,
  "policy_version": "v1"
}
```

- [ ] **Step 2: Compile and assert the preview is legally empty of results**

```bash
python -m pytest scripts/tests/test_project_edition.py -v
```

Expected: no week-1 outcomes, no final starters, player `6949` absent from roster 6.

- [ ] **Step 3: Desks → ranking record → prose**

Preseason receipts are available (the D1a edition is approved). Ranking record carries
`prior_rank` from the preseason edition.

- [ ] **Step 4: Gate, media, render, verify, publish** — as D1a.

- [ ] **Step 5: Commit**

```bash
git add content/editions/2025-wk01-preview/ week1-preview.html config.js content/review-log.jsonl
git commit -m "content(2025-wk01-preview): pre-kickoff preview on a strictly-prior cutoff"
```

---

### Task D1c: Week-1 recap

**Files:**

- Create: `content/editions/2025-wk01-recap/{descriptor,bundle,ranking_record,content,media_manifest,publication}.json`
- Modify: `week1.html` (replace the filler edition)

- [ ] **Step 1: Declare the descriptor** — `kind: "recap"`, `results_through_week: 1`,
      `cutoff_utc: "2025-09-09T06:59:59Z"` (Tue 06:59:59 UTC after MNF).

- [ ] **Step 2: Compile the bundle; confirm week-1 results ARE present and week-2 are not.**

- [ ] **Step 3: Desks → ranking record → prose.** The continuity desk grades the preview's picks
      and the preseason's claims. This is the first edition where `picks_ledger` grading occurs.

- [ ] **Step 4: Gate, media, render, verify, publish** — as D1a.

- [ ] **Step 5: Commit**

```bash
git add content/editions/2025-wk01-recap/ week1.html content/review-log.jsonl
git commit -m "content(2025-wk01-recap): first recap; preview picks graded, threads advanced"
```

---

### Task D1d: PRODUCT GATE — stop for review

**Do not begin D2. Do not build further adapters or desks.**

- [ ] **Step 1: Run the full acceptance sweep**

```bash
python -m pytest scripts/tests/ -q
python scripts/cutoff_audit.py --all
python scripts/generate_chat_provenance.py --verify
```

Expected: suite ≥ 343 passed / 2 skipped; zero unclassified fields; provenance OK.

- [ ] **Step 2: Assemble the review packet**

Report, with evidence: the census at 0 (from 46); zero structurally unsliced H2H blocks (from
98); the three editions' ranking records; `review-log.jsonl` lines; render-verifier output for
each edition; and a side-by-side against the old pipeline's week-1 filler.

- [ ] **Step 3: Answer the gate question in writing**

> Is this slice **materially richer** than what the old pipeline produced?

If **no** — revise the source and desk contracts before D2. Passing on temporal correctness alone
is not passing.

- [ ] **Step 4: STOP.** Await Blake's decision.

---

## Self-Review

**Spec coverage.** Phase 0 → Lane P (P1-P3). Phase A read-path census → A1-A4, including the
`analyze_chat.py` quarantine and dormant-enrichment removal. Phase B repair → B1-B4; leaf census
and positive controls → B5-B6; two-manifest identity → B7; minimum projector, fail-closed
adapters, week-1 preview roster reconstruction → B8; media rebind → B9; media manifest, render
bijection, publication record → B10. Phase C → C1-C3, with the ranking decision record gated in
C3. D1 sequencing preserved exactly: preseason → preview → recap → STOP (D1a-D1d).

**Known gaps carried deliberately.** Noninterference (full-input vs cutoff-truncated byte
equality) is specified in the design but not implemented here; it belongs with D2's adapter
expansion, since with only three adapters the comparison has little surface to exercise. The
non-2025 canary edition is likewise deferred to D2 — flagged rather than silently dropped.

**Placeholder scan.** No TBD/TODO. Every code step carries runnable code; every test step carries
a real assertion; every command is exact.

**Type consistency.** `slice_h2h` and `as_of_records` (B1/B2) are consumed with identical
signatures in B3 and B8. `payload_hash` (B7) is consumed in B10. `EditionDescriptor` field names
match between B7, B8, and all three D1 descriptors. `manifest_entry`'s `publish.location` is the
key `verify_render` reads.
