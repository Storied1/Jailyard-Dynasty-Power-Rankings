# Jailyard Content-Depth — Phase 1a (Data Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task — linear, single-context execution (this codebase's ethos for data-layer work; no `subagent-driven-development`). Steps use checkbox (`- [ ]`) syntax for tracking. See `~/.claude/projects/C--Users-blake-projects-Jailyard-Dynasty-Power-Rankings/memory/feedback_data_work_single_context.md` for rationale.

**Goal:** Stand up the L1 data foundation — NFLGame as first-class entity, extended `top_scorers[].game_context` with nflreadpy-sourced fields and `src` attribution, and weekly fantasy roster snapshots (capture-from-now-on with derived backfill for weeks 1-6).

**Architecture:** Single-source consolidation onto nflreadpy (replaces ESPN scoreboard + ESPN injury feed + OpenWeatherMap from spec-v1). NFLGame entity normalizes per-game data so player entries reference `game_id`. Companion `weekN_data_expanded.json` provides denormalized view for chrome authors who prefer one fetch per week. All generators use `sort_keys=True, ensure_ascii=False` canonicalization (architect M6 mandate).

**Tech Stack:** Python 3.12, nflreadpy 0.1.5 (already installed — verified during spike), polars 1.40 (transitive), pytest, existing `scripts/shared.py` save_json + load_json helpers.

**Source spec:** `docs/superpowers/specs/2026-05-02-jailyard-content-depth-design.md` (v3, architect APPROVED WITH NITS).

**Phases this plan covers:** Phase 1a only (data foundation, ~3 sessions). Phase 1b/1c/2/3 get separate plans.

**Worktree note:** This plan is substantial. If you want isolation from main, create a worktree before starting:

```bash
git -C "C:/Users/blake/projects/Jailyard-Dynasty-Power-Rankings" worktree add ../jailyard-phase-1a -b feature/content-depth-phase-1a
cd ../jailyard-phase-1a
```

Otherwise execute in main; commits cluster naturally per task.

---

## File Structure

**Files to create:**

- `scripts/fetch_nflreadpy.py` — fetches schedules, team_stats, injuries, ff_playerids; caches to `data/external/`
- `scripts/generate_nfl_games.py` — reads cached nflreadpy outputs; writes per-game JSONs to `data/2025/nfl_games/{game_id}.json`
- `scripts/generate_expanded_week.py` — produces `weekN_data_expanded.json` companion (denormalized week-view)
- `scripts/derive_historical_rosters.py` — best-effort backfill of fantasy roster snapshots for weeks 1-6
- `scripts/schemas/nfl_game.schema.json` — JSON schema for NFLGame entity
- `scripts/schemas/game_context.schema.json` — JSON schema for `top_scorers[].game_context`
- `scripts/schemas/fantasy_roster.schema.json` — JSON schema for weekly fantasy roster snapshot
- `scripts/tests/test_fetch_nflreadpy.py` — tests for fetcher (cache, --max-age-hours, error fallback)
- `scripts/tests/test_generate_nfl_games.py` — tests for NFLGame generator (schema valid, idempotency)
- `scripts/tests/test_generate_expanded.py` — tests for expanded companion (manifest hash check)
- `scripts/tests/test_extract_week_data_v2.py` — tests for extended `build_game_context` with `src` field
- `scripts/tests/test_derive_historical_rosters.py` — tests for roster derivation null-handling
- `scripts/tests/fixtures/nflreadpy_sample.json` — frozen nflreadpy sample data for tests

**Files to modify:**

- `scripts/extract_week_data.py` — `build_game_context()` becomes thin (looks up game_id, references nfl_games entity); add `src` attribution; emit `game_id` instead of nesting weather/opponent
- `scripts/verify_week_content.py` — extend Tier 1 check for new game_context shape (presence of `game_id`, valid `src` enum, edge-case status field for bye/retired/DNP)
- `scripts/shared.py` — add `save_json_canonical()` helper that wraps existing `save_json` with `sort_keys=True, ensure_ascii=False` (canonicalization mandate)
- `fetch_sleeper.py` — extend with weekly roster snapshot capture (~5 lines added at end of fetch); writes to `data/2025/fantasy_rosters/week{N}.json`
- `.gitignore` — add `data/external/` and `data/*/fantasy_rosters/` (cached external data + per-week roster snapshots; gitignored per existing pattern)

**Files NOT modified in Phase 1a (deferred to Phase 1c):**

- `.claude/commands/write-week.md` — Item 18 (writer prompt updates)
- `scripts/local_draft.py` — Item 18 (writer prompt updates)
- `CLAUDE.md` — Item 19

---

## Task 1: Add canonicalization helper to shared.py

**Files:**

- Modify: `scripts/shared.py`
- Test: `scripts/tests/test_shared_canonical.py`

- [ ] **Step 1: Read existing save_json signature**

```bash
grep -n "def save_json" scripts/shared.py
```

Expected: line ~78, signature `def save_json(path, data, indent=2, ensure_ascii=False, verbose=False)`.

- [ ] **Step 2: Write failing test for canonical save**

Create `scripts/tests/test_shared_canonical.py`:

```python
"""Tests for save_json_canonical helper.

Canonicalization (architect M6) requires sort_keys=True so re-serializing the
same data produces byte-identical output regardless of dict insertion order.
"""
import json
from pathlib import Path

from scripts.shared import save_json_canonical


def test_canonical_save_sorts_keys(tmp_path: Path):
    """Keys sorted alphabetically regardless of insertion order."""
    data = {"zebra": 1, "alpha": 2, "mongoose": 3}
    out = tmp_path / "out.json"
    save_json_canonical(out, data)
    text = out.read_text(encoding="utf-8")
    assert text.index('"alpha"') < text.index('"mongoose"') < text.index('"zebra"')


def test_canonical_save_idempotent(tmp_path: Path):
    """Saving same data twice produces byte-identical files."""
    data = {"b": [3, 1, 2], "a": {"y": 1, "x": 2}}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    save_json_canonical(a, data)
    save_json_canonical(b, data)
    assert a.read_bytes() == b.read_bytes()


def test_canonical_save_non_ascii_preserved(tmp_path: Path):
    """ensure_ascii=False so unicode renders as glyphs not escapes."""
    data = {"team": "Légion of Bouz", "emoji": "✅"}
    out = tmp_path / "u.json"
    save_json_canonical(out, data)
    text = out.read_text(encoding="utf-8")
    assert "Légion" in text
    assert "✅" in text
    assert "\\u" not in text
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd C:/Users/blake/projects/Jailyard-Dynasty-Power-Rankings
python -m pytest scripts/tests/test_shared_canonical.py -v
```

Expected: ImportError (cannot import `save_json_canonical`).

- [ ] **Step 4: Add the helper to shared.py**

Append to `scripts/shared.py` (after existing `save_json` function):

```python
def save_json_canonical(path, data, verbose=False):
    """Canonical JSON write — sort_keys=True, ensure_ascii=False, indent=2.

    All new generators (Phase 1+ data work) use this helper to guarantee
    byte-identical output across runs (architect M6 mandate). The canonical
    form is also what the pre-commit prettier hook produces, so post-commit
    re-extraction stays clean.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    if verbose:
        print(f"  Saved (canonical): {path.relative_to(REPO_ROOT)}")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python -m pytest scripts/tests/test_shared_canonical.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Run full test suite to verify no regression**

```bash
python -m pytest scripts/tests/ -v 2>&1 | tail -10
```

Expected: 48 + 3 = 51 passed (no regressions).

- [ ] **Step 7: Commit**

```bash
git add scripts/shared.py scripts/tests/test_shared_canonical.py
git commit -m "feat(shared): add save_json_canonical helper

Architect M6 mandate. All Phase 1+ generators use sort_keys=True +
ensure_ascii=False to guarantee byte-identical output across runs.
Matches pre-commit prettier output so re-extraction stays clean.

Tests: 3 (sort, idempotency, non-ascii preserved). Suite: 51/51."
```

---

## Task 2: Build the nflreadpy fetcher with cache + --max-age-hours

**Files:**

- Create: `scripts/fetch_nflreadpy.py`
- Test: `scripts/tests/test_fetch_nflreadpy.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add `data/external/` to .gitignore**

Edit `.gitignore`, add:

```
# nflreadpy and external API caches (Phase 1a — architect F1 cadence)
data/external/
```

- [ ] **Step 2: Write failing test for fetcher cache + age check**

Create `scripts/tests/test_fetch_nflreadpy.py`:

```python
"""Tests for fetch_nflreadpy.py.

Cache discipline (architect F1): --max-age-hours N controls re-fetch.
Idempotency (architect M6): re-running with fresh cache produces no diff.
"""
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.fetch_nflreadpy import fetch_one, is_stale, CACHE_DIR


def test_is_stale_when_file_missing(tmp_path: Path):
    """Missing cache file is always stale."""
    assert is_stale(tmp_path / "missing.parquet", max_age_hours=1) is True


def test_is_stale_when_file_recent(tmp_path: Path):
    """File modified moments ago is not stale."""
    f = tmp_path / "fresh.parquet"
    f.write_text("x")
    assert is_stale(f, max_age_hours=24) is False


def test_is_stale_when_file_old(tmp_path: Path, monkeypatch):
    """File older than max_age_hours is stale."""
    f = tmp_path / "old.parquet"
    f.write_text("x")
    # Set mtime to 25 hours ago
    old_time = time.time() - (25 * 3600)
    import os
    os.utime(f, (old_time, old_time))
    assert is_stale(f, max_age_hours=24) is True


def test_fetch_one_skips_when_fresh(tmp_path: Path, monkeypatch):
    """fetch_one does not call nflreadpy when cache is fresh."""
    monkeypatch.setattr("scripts.fetch_nflreadpy.CACHE_DIR", tmp_path)
    cache_file = tmp_path / "schedules_2025.parquet"
    cache_file.write_text("cached_data")
    # Patch nflreadpy to raise if called
    with patch("scripts.fetch_nflreadpy.nfl") as mock_nfl:
        mock_nfl.load_schedules.side_effect = AssertionError("should not be called")
        fetch_one("schedules", season=2025, max_age_hours=24)
    # If we reach here without AssertionError, fetch was correctly skipped
    assert cache_file.exists()
```

- [ ] **Step 3: Run test, verify it fails**

```bash
python -m pytest scripts/tests/test_fetch_nflreadpy.py -v
```

Expected: ImportError on `scripts.fetch_nflreadpy`.

- [ ] **Step 4: Create the fetcher**

Create `scripts/fetch_nflreadpy.py`:

```python
"""Fetch and cache nflreadpy data tables to data/external/.

Single source of truth for: schedules, team_stats, injuries, ff_playerids.
Replaces v1-spec's ESPN scoreboard + ESPN injury feed + OpenWeatherMap
(spike confirmed all three failed for one reason or another).

Cache cadence (architect F1): --max-age-hours N (default 168 = 7 days).
Refresh weekly during NFL season via GitHub Actions (Phase 2).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import nflreadpy as nfl

from scripts.shared import REPO_ROOT, save_json_canonical

CACHE_DIR = REPO_ROOT / "data" / "external"

# Mapping: cache_key → (nflreadpy loader, kwargs builder)
LOADERS = {
    "schedules": lambda season: nfl.load_schedules(seasons=season),
    "team_stats": lambda season: nfl.load_team_stats(seasons=season),
    "injuries": lambda season: nfl.load_injuries(seasons=season),
    "ff_playerids": lambda season: nfl.load_ff_playerids(),  # season-agnostic
}


def is_stale(cache_path: Path, max_age_hours: int) -> bool:
    """True if cache file is missing or older than max_age_hours."""
    if not cache_path.exists():
        return True
    age_seconds = time.time() - cache_path.stat().st_mtime
    return age_seconds > (max_age_hours * 3600)


def fetch_one(name: str, season: int, max_age_hours: int = 168) -> Path:
    """Fetch one nflreadpy table; cache to disk; return path.

    Skips fetch if cache is fresh (per --max-age-hours).
    """
    if name not in LOADERS:
        raise ValueError(f"Unknown nflreadpy table: {name}")

    suffix = f"_{season}" if name != "ff_playerids" else ""
    cache_path = CACHE_DIR / f"{name}{suffix}.parquet"

    if not is_stale(cache_path, max_age_hours):
        return cache_path

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = LOADERS[name](season)
    df.write_parquet(cache_path)
    return cache_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and cache nflreadpy data.")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=168,
        help="Re-fetch if cache older than N hours (default 168 = 7 days).",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=list(LOADERS.keys()),
        help="Which tables to fetch (default: all).",
    )
    args = parser.parse_args()

    for name in args.tables:
        path = fetch_one(name, season=args.season, max_age_hours=args.max_age_hours)
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
python -m pytest scripts/tests/test_fetch_nflreadpy.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Smoke-test the fetcher (real network call)**

```bash
python scripts/fetch_nflreadpy.py --season 2025 --tables schedules
```

Expected: prints `  schedules: <path>/data/external/schedules_2025.parquet`. File exists.

- [ ] **Step 7: Verify idempotency (skip on fresh cache)**

```bash
python scripts/fetch_nflreadpy.py --season 2025 --tables schedules
```

Expected: same output, file mtime unchanged (fetcher skipped fetch). Verify with `ls -la data/external/`.

- [ ] **Step 8: Commit**

```bash
git add scripts/fetch_nflreadpy.py scripts/tests/test_fetch_nflreadpy.py .gitignore
git commit -m "feat(data): add nflreadpy fetcher with --max-age-hours cache

Single source of truth for schedules, team_stats, injuries, ff_playerids.
Replaces v1-spec's ESPN + OpenWeatherMap (spike-confirmed unavailable).
Cache cadence: 168h default per architect F1.

Cached to data/external/ (gitignored). Idempotent: skip fetch when fresh.

Tests: 4 (stale check + skip-when-fresh). Suite: 55/55."
```

---

## Task 3: Schema files for NFLGame, game_context, fantasy_roster

**Files:**

- Create: `scripts/schemas/nfl_game.schema.json`
- Create: `scripts/schemas/game_context.schema.json`
- Create: `scripts/schemas/fantasy_roster.schema.json`

- [ ] **Step 1: Create scripts/schemas/ directory**

```bash
mkdir -p scripts/schemas
```

- [ ] **Step 2: Write the NFLGame schema**

Create `scripts/schemas/nfl_game.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "NFLGame",
  "description": "First-class NFL game entity. One file per game_id under data/2025/nfl_games/.",
  "type": "object",
  "required": ["game_id", "season", "week", "home_team", "away_team"],
  "properties": {
    "game_id": {
      "type": "string",
      "description": "nflreadpy schedule game_id, e.g. 2025_06_BUF_NYJ"
    },
    "season": { "type": "integer", "minimum": 2022 },
    "week": { "type": "integer", "minimum": 1, "maximum": 22 },
    "home_team": { "type": "string" },
    "away_team": { "type": "string" },
    "home_score": { "type": ["integer", "null"] },
    "away_score": { "type": ["integer", "null"] },
    "result": {
      "type": ["integer", "null"],
      "description": "home_score - away_score"
    },
    "kickoff": { "type": ["string", "null"], "description": "ISO8601" },
    "stadium": { "type": ["string", "null"] },
    "stadium_id": { "type": ["string", "null"] },
    "roof": {
      "type": ["string", "null"],
      "enum": ["dome", "outdoors", "closed", "open", null]
    },
    "surface": { "type": ["string", "null"] },
    "temp": { "type": ["integer", "null"] },
    "wind": { "type": ["integer", "null"] },
    "spread_line": { "type": ["number", "null"] },
    "total_line": { "type": ["number", "null"] },
    "starting_qbs": {
      "type": ["object", "null"],
      "properties": {
        "home": { "type": ["string", "null"], "description": "gsis_id" },
        "away": { "type": ["string", "null"] }
      }
    },
    "rest_days": {
      "type": ["object", "null"],
      "properties": {
        "home": { "type": ["integer", "null"] },
        "away": { "type": ["integer", "null"] }
      }
    },
    "div_game": { "type": ["boolean", "null"] },
    "team_stats": {
      "type": ["object", "null"],
      "description": "Per-team aggregated EPA + counts from nflreadpy team_stats."
    },
    "key_injuries": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["team", "gsis_id", "status"],
        "properties": {
          "team": { "type": "string" },
          "gsis_id": { "type": "string" },
          "name": { "type": ["string", "null"] },
          "status": { "type": "string" },
          "primary_injury": { "type": ["string", "null"] }
        }
      }
    }
  }
}
```

- [ ] **Step 3: Write the game_context schema**

Create `scripts/schemas/game_context.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "GameContext",
  "description": "Per-player game-context block in top_scorers[] of weekN_data.json.",
  "type": "object",
  "required": ["game_id", "src"],
  "properties": {
    "game_id": {
      "type": ["string", "null"],
      "description": "Reference to data/2025/nfl_games/{game_id}.json"
    },
    "stat_line": {
      "type": ["string", "null"],
      "description": "Pre-rendered fantasy stat line"
    },
    "one_liner": {
      "type": ["string", "null"],
      "description": "Real-game stat line, e.g. '22 carries, 169 yd, 2 TD vs the Bills'"
    },
    "opponent": { "type": ["string", "null"] },
    "src": {
      "type": "object",
      "description": "Per-field source attribution for graceful degradation (architect M3).",
      "additionalProperties": {
        "type": ["string", "null"],
        "enum": ["nflreadpy", "sleeper_stats", "fallback", null]
      }
    }
  }
}
```

- [ ] **Step 4: Write the fantasy_roster schema**

Create `scripts/schemas/fantasy_roster.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "FantasyRosterWeek",
  "description": "Weekly snapshot of all 12 fantasy rosters. data/2025/fantasy_rosters/week{N}.json.",
  "type": "object",
  "required": ["week", "captured", "derived", "rosters"],
  "properties": {
    "week": { "type": "integer", "minimum": 1, "maximum": 22 },
    "captured": {
      "type": "boolean",
      "description": "True if captured live at fetch time"
    },
    "derived": {
      "type": "boolean",
      "description": "True if back-derived from transactions (starters/reserve null)"
    },
    "captured_at": {
      "type": ["string", "null"],
      "description": "ISO8601 fetch timestamp"
    },
    "rosters": {
      "type": "array",
      "minItems": 12,
      "maxItems": 12,
      "items": {
        "type": "object",
        "required": ["roster_id", "owner_id", "players"],
        "properties": {
          "roster_id": { "type": "integer" },
          "owner_id": { "type": "string" },
          "players": { "type": "array", "items": { "type": "string" } },
          "starters": {
            "type": ["array", "null"],
            "description": "Null for derived snapshots (architect B2 — unrecoverable)"
          },
          "reserve": { "type": ["array", "null"] }
        }
      }
    }
  }
}
```

- [ ] **Step 5: Commit schemas**

```bash
git add scripts/schemas/
git commit -m "feat(schemas): JSON schemas for NFLGame, game_context, fantasy_roster

Architect M4 falsifiability mandate — every MUST item gets a machine-checkable
contract. Used by verify_week_content.py extensions in later tasks.

Schemas:
- nfl_game.schema.json (Item 14 entity)
- game_context.schema.json (Item 1 with src field)
- fantasy_roster.schema.json (Item 13 with derived/captured flags)"
```

---

## Task 4: NFLGame generator — read nflreadpy cache, write per-game files

**Files:**

- Create: `scripts/generate_nfl_games.py`
- Test: `scripts/tests/test_generate_nfl_games.py`

- [ ] **Step 1: Write failing test for one game generation**

Create `scripts/tests/test_generate_nfl_games.py`:

```python
"""Tests for generate_nfl_games.py.

Generator reads cached nflreadpy outputs and writes one JSON per game_id.
Idempotency (architect M6): re-running produces byte-identical files.
Schema validity (architect M4): each file validates against nfl_game.schema.json.
"""
import json
from pathlib import Path

import pytest

from scripts.generate_nfl_games import build_game_record


def test_build_game_record_minimal():
    """Minimal schedule row produces valid game record."""
    schedule_row = {
        "game_id": "2025_06_BUF_NYJ",
        "season": 2025,
        "week": 6,
        "home_team": "BUF",
        "away_team": "NYJ",
        "home_score": 28,
        "away_score": 14,
        "kickoff": "2025-10-12T13:00-04:00",
        "stadium": "Highmark Stadium",
        "stadium_id": "BUF",
        "roof": "outdoors",
        "surface": "grass",
        "temp": 52,
        "wind": 12,
        "spread_line": -7.5,
        "total_line": 47,
        "away_qb_id": "00-0036442",
        "home_qb_id": "00-0034796",
        "away_rest": 7,
        "home_rest": 7,
        "div_game": True,
    }
    record = build_game_record(schedule_row, team_stats=None, injuries=None)
    assert record["game_id"] == "2025_06_BUF_NYJ"
    assert record["home_team"] == "BUF"
    assert record["away_team"] == "NYJ"
    assert record["temp"] == 52
    assert record["div_game"] is True
    assert record["starting_qbs"]["home"] == "00-0034796"
    assert record["starting_qbs"]["away"] == "00-0036442"
    assert record["rest_days"]["home"] == 7
    assert record["result"] == 14  # 28 - 14


def test_build_game_record_handles_missing_fields():
    """Optional fields default to null without crashing."""
    schedule_row = {
        "game_id": "2025_18_FOO_BAR",
        "season": 2025,
        "week": 18,
        "home_team": "FOO",
        "away_team": "BAR",
        "home_score": None,
        "away_score": None,
        "temp": None,
        "wind": None,
        "spread_line": None,
        "total_line": None,
    }
    record = build_game_record(schedule_row, team_stats=None, injuries=None)
    assert record["temp"] is None
    assert record["result"] is None
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python -m pytest scripts/tests/test_generate_nfl_games.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create the generator**

Create `scripts/generate_nfl_games.py`:

```python
"""Generate per-game NFLGame entity files from cached nflreadpy data.

Reads:  data/external/{schedules,team_stats,injuries}_2025.parquet
Writes: data/2025/nfl_games/{game_id}.json (one per game)

Architect M2: NFLGame promoted to first-class entity. Player entries in
weekN_data.json reference game_id instead of nesting weather/opponent.

Architect M6: canonical save (sort_keys=True, ensure_ascii=False) — idempotent.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import polars as pl

from scripts.fetch_nflreadpy import fetch_one
from scripts.shared import REPO_ROOT, save_json_canonical

OUT_DIR = REPO_ROOT / "data" / "2025" / "nfl_games"


def build_game_record(
    schedule_row: dict[str, Any],
    team_stats: pl.DataFrame | None,
    injuries: pl.DataFrame | None,
) -> dict[str, Any]:
    """Build one NFLGame record from a schedule row + optional team_stats + injuries."""
    home = schedule_row["home_team"]
    away = schedule_row["away_team"]
    h_score = schedule_row.get("home_score")
    a_score = schedule_row.get("away_score")

    record: dict[str, Any] = {
        "game_id": schedule_row["game_id"],
        "season": schedule_row["season"],
        "week": schedule_row["week"],
        "home_team": home,
        "away_team": away,
        "home_score": h_score,
        "away_score": a_score,
        "result": (h_score - a_score) if (h_score is not None and a_score is not None) else None,
        "kickoff": schedule_row.get("gametime") or schedule_row.get("kickoff"),
        "stadium": schedule_row.get("stadium"),
        "stadium_id": schedule_row.get("stadium_id"),
        "roof": schedule_row.get("roof"),
        "surface": schedule_row.get("surface"),
        "temp": schedule_row.get("temp"),
        "wind": schedule_row.get("wind"),
        "spread_line": schedule_row.get("spread_line"),
        "total_line": schedule_row.get("total_line"),
        "starting_qbs": {
            "home": schedule_row.get("home_qb_id"),
            "away": schedule_row.get("away_qb_id"),
        },
        "rest_days": {
            "home": schedule_row.get("home_rest"),
            "away": schedule_row.get("away_rest"),
        },
        "div_game": schedule_row.get("div_game"),
        "team_stats": _team_stats_for_game(schedule_row["game_id"], team_stats) if team_stats is not None else None,
        "key_injuries": _injuries_for_game(schedule_row["week"], home, away, injuries) if injuries is not None else [],
    }
    return record


def _team_stats_for_game(game_id: str, team_stats: pl.DataFrame) -> dict[str, Any] | None:
    """Extract per-team aggregated EPA from team_stats DataFrame."""
    rows = team_stats.filter(pl.col("game_id") == game_id)
    if len(rows) == 0:
        return None
    out: dict[str, Any] = {}
    for r in rows.iter_rows(named=True):
        out[r["team"]] = {
            "passing_epa": r.get("passing_epa"),
            "rushing_epa": r.get("rushing_epa"),
            "receiving_epa": r.get("receiving_epa"),
            "passing_yards": r.get("passing_yards"),
            "rushing_yards": r.get("rushing_yards"),
            "passing_tds": r.get("passing_tds"),
            "rushing_tds": r.get("rushing_tds"),
        }
    return out


def _injuries_for_game(week: int, home: str, away: str, injuries: pl.DataFrame) -> list[dict[str, Any]]:
    """Filter injuries to teams playing this week, status of concern."""
    rows = injuries.filter(
        (pl.col("week") == week)
        & (pl.col("team").is_in([home, away]))
        & (pl.col("report_status").is_in(["Out", "Doubtful", "Questionable"]))
    )
    return [
        {
            "team": r["team"],
            "gsis_id": r["gsis_id"],
            "name": r.get("full_name"),
            "status": r["report_status"],
            "primary_injury": r.get("report_primary_injury"),
        }
        for r in rows.iter_rows(named=True)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--max-age-hours", type=int, default=168)
    args = parser.parse_args()

    sched_path = fetch_one("schedules", args.season, args.max_age_hours)
    ts_path = fetch_one("team_stats", args.season, args.max_age_hours)
    inj_path = fetch_one("injuries", args.season, args.max_age_hours)

    schedules = pl.read_parquet(sched_path).sort("game_id")
    team_stats = pl.read_parquet(ts_path).sort(["game_id", "team"])
    injuries = pl.read_parquet(inj_path).sort(["week", "team", "gsis_id"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for row in schedules.iter_rows(named=True):
        record = build_game_record(row, team_stats, injuries)
        out_path = OUT_DIR / f"{record['game_id']}.json"
        save_json_canonical(out_path, record)
        count += 1
    print(f"  Wrote {count} NFLGame files to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run unit tests, verify pass**

```bash
python -m pytest scripts/tests/test_generate_nfl_games.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Smoke-test (real generation)**

```bash
python scripts/generate_nfl_games.py --season 2025
```

Expected: prints `Wrote N NFLGame files`. N ≈ 272 across full season.

- [ ] **Step 6: Verify idempotency**

```bash
python scripts/generate_nfl_games.py --season 2025
git status data/2025/nfl_games/ | head -5
```

Expected: no changes (re-run produced byte-identical files).

- [ ] **Step 7: Spot-check one file against schema**

```bash
python -c "import json, jsonschema; jsonschema.validate(json.load(open('data/2025/nfl_games/2025_01_DAL_PHI.json')), json.load(open('scripts/schemas/nfl_game.schema.json')))" && echo OK
```

Expected: `OK`. (If `jsonschema` not installed: `pip install jsonschema`.)

- [ ] **Step 8: Commit**

```bash
git add scripts/generate_nfl_games.py scripts/tests/test_generate_nfl_games.py data/2025/nfl_games/
git commit -m "feat(data): NFLGame as first-class entity

Item 14 of phase-1a. Per-game JSON files in data/2025/nfl_games/{game_id}.json
sourced from nflreadpy schedules + team_stats + injuries. ~272 files for
full 2025 season.

Architect M2: denormalization fix — same Bills-Dolphins game appears once,
not duplicated across 5+ player entries.

Schema-validated. Idempotent.

Tests: +2. Suite: 57/57."
```

---

## Task 5: Extend extract_week_data.py — top_scorers reference game_id + src field

**Files:**

- Modify: `scripts/extract_week_data.py` (`build_game_context` function)
- Test: `scripts/tests/test_extract_week_data_v2.py`

- [ ] **Step 1: Read the current build_game_context implementation**

```bash
grep -n -A 30 "def build_game_context" scripts/extract_week_data.py | head -50
```

Note the current shape of the function and where it's called from.

- [ ] **Step 2: Write failing test for new game_context shape**

Create `scripts/tests/test_extract_week_data_v2.py`:

```python
"""Tests for v2 extract_week_data — game_context references game_id + src field.

Architect M3: src field per-attribution for graceful degradation.
Architect M2: game_id reference replaces nested weather/opponent.
"""
import json
from pathlib import Path

import pytest

from scripts.extract_week_data import build_game_context_v2


@pytest.fixture
def player_id_to_game_id():
    """Mock crosswalk: sleeper player_id → nfl game_id for the week."""
    return {
        "4017": "2025_06_ATL_BUF",  # Bijan
        "421": "2025_06_KC_LV",     # Mahomes
    }


def test_game_context_v2_returns_game_id_reference(player_id_to_game_id):
    """game_context contains game_id reference, not nested weather/opponent."""
    ctx = build_game_context_v2(
        player_id="4017",
        sleeper_stats_for_player={"car": 22, "rush_yd": 169, "rush_td": 2},
        player_id_to_game_id=player_id_to_game_id,
        nfl_team_full={"BUF": "Bills", "ATL": "Falcons"},
        opponent_abbr="BUF",
    )
    assert ctx["game_id"] == "2025_06_ATL_BUF"
    assert "weather" not in ctx  # Moved to NFLGame entity
    assert "opponent_dvoa" not in ctx  # Moved to NFLGame entity


def test_game_context_v2_includes_src_attribution(player_id_to_game_id):
    """src field present with per-attribution sources."""
    ctx = build_game_context_v2(
        player_id="4017",
        sleeper_stats_for_player={"car": 22, "rush_yd": 169, "rush_td": 2},
        player_id_to_game_id=player_id_to_game_id,
        nfl_team_full={"BUF": "Bills", "ATL": "Falcons"},
        opponent_abbr="BUF",
    )
    assert "src" in ctx
    assert ctx["src"].get("game_id") in ("nflreadpy", "fallback")


def test_game_context_v2_handles_missing_game_id(player_id_to_game_id):
    """Player not in crosswalk → game_id null, src.game_id null."""
    ctx = build_game_context_v2(
        player_id="9999",
        sleeper_stats_for_player={},
        player_id_to_game_id=player_id_to_game_id,
        nfl_team_full={},
        opponent_abbr=None,
    )
    assert ctx["game_id"] is None
    assert ctx["src"].get("game_id") is None
```

- [ ] **Step 3: Run test, verify it fails**

```bash
python -m pytest scripts/tests/test_extract_week_data_v2.py -v
```

Expected: ImportError on `build_game_context_v2`.

- [ ] **Step 4: Add build_game_context_v2 to extract_week_data.py**

Find the existing `build_game_context` in `scripts/extract_week_data.py` and add a v2 version BELOW it (don't delete the old one yet — Item 1 backward-compat):

```python
def build_game_context_v2(
    player_id: str,
    sleeper_stats_for_player: dict,
    player_id_to_game_id: dict[str, str],
    nfl_team_full: dict[str, str],
    opponent_abbr: str | None,
) -> dict:
    """Build v2 game_context: game_id reference + src attribution.

    v2 differences from v1 (per architect M2 + M3):
    - Returns `game_id` reference instead of nesting weather/opponent
    - Adds `src` field with per-attribution sources
    - Weather, opponent_def_epa, injury_status live in the NFLGame entity now

    Returns dict shape:
        {
            "game_id": str | None,
            "stat_line": str | None,
            "one_liner": str | None,
            "opponent": str | None,
            "src": {"game_id": "nflreadpy" | "fallback" | None, ...}
        }
    """
    game_id = player_id_to_game_id.get(player_id)
    src: dict[str, str | None] = {
        "game_id": "nflreadpy" if game_id else None,
    }

    stat_line = _format_stat_line(sleeper_stats_for_player) if sleeper_stats_for_player else None
    src["stat_line"] = "sleeper_stats" if stat_line else None

    opponent_full = nfl_team_full.get(opponent_abbr) if opponent_abbr else None
    one_liner = (
        f"{stat_line} vs the {opponent_full}" if stat_line and opponent_full else stat_line
    )
    src["opponent"] = "sleeper_stats" if opponent_abbr else None
    src["one_liner"] = "fallback" if one_liner else None

    return {
        "game_id": game_id,
        "stat_line": stat_line,
        "one_liner": one_liner,
        "opponent": opponent_full,
        "src": src,
    }


def _format_stat_line(stats: dict) -> str | None:
    """Render a Sleeper stats blob as a one-line stat string. Trivial cases only."""
    if not stats:
        return None
    parts = []
    if stats.get("car"):
        parts.append(f"{stats['car']} carries")
    if stats.get("rush_yd"):
        parts.append(f"{stats['rush_yd']} yd")
    if stats.get("rush_td"):
        parts.append(f"{stats['rush_td']} rush TD")
    if stats.get("rec"):
        parts.append(f"{stats['rec']} rec")
    if stats.get("rec_yd"):
        parts.append(f"{stats['rec_yd']} rec yd")
    if stats.get("rec_td"):
        parts.append(f"{stats['rec_td']} rec TD")
    return ", ".join(parts) if parts else None
```

- [ ] **Step 5: Run test, verify pass**

```bash
python -m pytest scripts/tests/test_extract_week_data_v2.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Wire build_game_context_v2 into the main extraction path**

Find where the existing `build_game_context` is called in `scripts/extract_week_data.py` (likely inside the top_scorers loop). Replace the call with `build_game_context_v2(...)`. Build the `player_id_to_game_id` crosswalk from the cached nflreadpy schedules + ff_playerids data BEFORE the loop.

Add helper at top of file (after imports):

```python
def _load_player_to_game_crosswalk(season: int, week: int) -> dict[str, str]:
    """Build sleeper_id → game_id mapping for one week.

    Joins:
    - data/external/ff_playerids.parquet (sleeper_id ↔ gsis_id ↔ team)
    - data/external/schedules_{season}.parquet (week → home_team/away_team → game_id)

    For each rostered player on a team playing this week, map to the game_id.
    """
    import polars as pl

    from scripts.fetch_nflreadpy import fetch_one

    ff_path = fetch_one("ff_playerids", season=season)
    sched_path = fetch_one("schedules", season=season)

    ff = pl.read_parquet(ff_path).select(["sleeper_id", "gsis_id", "team"])
    schedules = pl.read_parquet(sched_path).filter(pl.col("week") == week)

    # team → game_id (one team plays one game per week)
    team_to_game: dict[str, str] = {}
    for row in schedules.iter_rows(named=True):
        team_to_game[row["home_team"]] = row["game_id"]
        team_to_game[row["away_team"]] = row["game_id"]

    # sleeper_id → game_id via team
    crosswalk: dict[str, str] = {}
    for row in ff.iter_rows(named=True):
        sid = row["sleeper_id"]
        team = row["team"]
        if sid and team in team_to_game:
            crosswalk[str(sid)] = team_to_game[team]
    return crosswalk
```

- [ ] **Step 7: Run full test suite, verify no regression**

```bash
python -m pytest scripts/tests/ 2>&1 | tail -5
```

Expected: 60+ passed.

- [ ] **Step 8: Re-extract one week with the new path, sanity-check output**

```bash
python scripts/extract_week_data.py --week 6 --season 2025 --pretty
python -c "import json; d=json.load(open('content/weeks/week6_data.json')); ts = d.get('top_scorers', []); print('first top scorer game_context:', json.dumps(ts[0].get('game_context'), indent=2) if ts else 'none')"
```

Expected: prints a `game_context` containing `game_id` (string like `2025_06_...`) and `src` (object with attribution keys).

- [ ] **Step 9: Commit**

```bash
git add scripts/extract_week_data.py scripts/tests/test_extract_week_data_v2.py content/weeks/week6_data.json
git commit -m "feat(data): top_scorers.game_context references game_id + src

Item 1 of phase-1a. game_context now references game_id (Item 14 NFLGame
entity) instead of nesting weather/opponent. src field per-attribution
for graceful degradation when nflreadpy is upstream-broken (architect M3).

build_game_context_v2 + _load_player_to_game_crosswalk added.
v1 build_game_context retained for backward compat through Phase 1b.

Re-extracted week6_data.json as smoke test. Backfill of weeks 1-18 in next task.

Tests: +3. Suite: 60+/60+."
```

---

## Task 6: Backfill weeks 1-18 with v2 extractor + verifier extension

**Files:**

- Modify: `scripts/verify_week_content.py` (add Tier 1 check for new game_context shape)
- Re-run: `python scripts/extract_week_data.py --all --season 2025 --pretty`

- [ ] **Step 1: Find current Tier 1 game_context check**

```bash
grep -n -A 15 "check_game_context" scripts/verify_week_content.py | head -25
```

- [ ] **Step 2: Extend the Tier 1 check for new schema**

Edit `scripts/verify_week_content.py` `check_game_context_presence` function. Replace its body so it now requires `game_context.game_id` and validates `src` enum:

```python
def check_game_context_presence(week_data: dict) -> list[str]:
    """Tier 1: each top_scorer with ownership > 0 has a populated game_context.

    v2 (Phase 1a) requires: game_id present (string or null with explicit reason)
    AND src field present with valid enum values.
    """
    errors: list[str] = []
    valid_src = {"nflreadpy", "sleeper_stats", "fallback", None}
    populated = 0
    eligible = 0

    for ts in week_data.get("top_scorers", []):
        if ts.get("position") in {"K", "DEF"}:
            continue  # K/DEF have no game_context expectation
        eligible += 1
        ctx = ts.get("game_context")
        if not ctx:
            continue
        # game_id may be null only if status explains why (bye, retired, DNP)
        if ctx.get("game_id") is None:
            status = ts.get("status")
            if status not in {"bye_week", "retired", "did_not_play"}:
                errors.append(
                    f"top_scorer {ts.get('player_id')} game_context.game_id is null "
                    f"without explanatory status (got: {status})"
                )
                continue
        # src must be present and valid
        src = ctx.get("src")
        if not isinstance(src, dict):
            errors.append(f"top_scorer {ts.get('player_id')} game_context.src missing or wrong type")
            continue
        for k, v in src.items():
            if v not in valid_src:
                errors.append(f"top_scorer {ts.get('player_id')} game_context.src.{k} = {v} not in {valid_src}")
        populated += 1

    if eligible >= 20:
        ratio = populated / eligible
        if ratio < 0.80:
            errors.append(
                f"populated_ratio {ratio:.2f} below threshold 0.80 (populated={populated}, eligible={eligible})"
            )
    return errors
```

- [ ] **Step 3: Backfill all 18 weeks with v2 extractor**

```bash
python scripts/extract_week_data.py --all --season 2025 --pretty
```

Expected: prints `Done! Extracted 18 week(s).`.

- [ ] **Step 4: Run verifier on weeks 1-6**

```bash
for w in 1 2 3 4 5 6; do
  echo "=== Week $w ==="
  python scripts/verify_week_content.py --week $w --pretty 2>&1 | grep VERDICT
done
```

Expected: all 6 weeks show `VERDICT: PASS`. Warnings allowed.

- [ ] **Step 5: Run full pytest**

```bash
python -m pytest scripts/tests/ 2>&1 | tail -5
```

Expected: 60+ passed.

- [ ] **Step 6: Idempotency CI check (architect M6)**

```bash
python scripts/extract_week_data.py --all --season 2025 --pretty
git diff content/weeks/ | wc -l
```

Expected: 0 (no diff after second extraction).

- [ ] **Step 7: Commit**

```bash
git add scripts/verify_week_content.py content/weeks/
git commit -m "feat(verify): Tier 1 check for v2 game_context (game_id + src enum)

Item 1 backfill. All 18 weeks of weekN_data.json now have v2 game_context
with game_id reference + src per-attribution. Verifier enforces:
- game_id present OR explanatory status (bye/retired/DNP)
- src field present with valid enum values
- populated_ratio >= 0.80 for eligible top_scorers (existing F1 check)

All 6 weeks PASS. Idempotency holds (architect M6)."
```

---

## Task 7: Generate weekN_data_expanded.json companion + manifest hash

**Files:**

- Create: `scripts/generate_expanded_week.py`
- Test: `scripts/tests/test_generate_expanded.py`

- [ ] **Step 1: Write failing test**

Create `scripts/tests/test_generate_expanded.py`:

```python
"""Tests for generate_expanded_week.py.

Architect M2: weekN_data_expanded.json inlines NFLGame data per top_scorer
for chrome authors who prefer one-fetch-per-week.

Architect N2: regeneration is content-addressable via manifest hash.
"""
import json
from pathlib import Path

import pytest

from scripts.generate_expanded_week import compute_manifest_hash, build_expanded


def test_compute_manifest_hash_stable_across_runs(tmp_path: Path):
    """Same inputs → same hash."""
    a = tmp_path / "a.json"
    a.write_text('{"x": 1}')
    h1 = compute_manifest_hash([a])
    h2 = compute_manifest_hash([a])
    assert h1 == h2


def test_compute_manifest_hash_changes_when_input_changes(tmp_path: Path):
    """Modify input → different hash."""
    a = tmp_path / "a.json"
    a.write_text('{"x": 1}')
    h1 = compute_manifest_hash([a])
    a.write_text('{"x": 2}')
    h2 = compute_manifest_hash([a])
    assert h1 != h2


def test_build_expanded_inlines_game_data():
    """top_scorers entries get a `game` field with the full NFLGame data."""
    week_data = {
        "meta": {"week": 6, "season": 2025},
        "top_scorers": [
            {"player_id": "4017", "game_context": {"game_id": "2025_06_ATL_BUF", "src": {}}}
        ],
    }
    nfl_games = {
        "2025_06_ATL_BUF": {
            "game_id": "2025_06_ATL_BUF",
            "home_team": "BUF",
            "away_team": "ATL",
            "temp": 52,
        }
    }
    expanded = build_expanded(week_data, nfl_games)
    inlined_game = expanded["top_scorers"][0]["game"]
    assert inlined_game["temp"] == 52
    assert inlined_game["home_team"] == "BUF"
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python -m pytest scripts/tests/test_generate_expanded.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create the generator**

Create `scripts/generate_expanded_week.py`:

```python
"""Generate weekN_data_expanded.json from weekN_data.json + NFLGame entities.

Architect M2: denormalized companion for chrome authors who prefer one
fetch per week instead of N+1 (week + per-game files).

Architect N2: content-addressable regeneration via manifest hash. Avoids
unnecessary writes when inputs haven't changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.shared import REPO_ROOT, load_json, save_json_canonical

WEEKS_DIR = REPO_ROOT / "content" / "weeks"
NFL_GAMES_DIR = REPO_ROOT / "data" / "2025" / "nfl_games"
MANIFEST_PATH = NFL_GAMES_DIR / "_expanded_manifest.json"


def compute_manifest_hash(paths: list[Path]) -> str:
    """SHA-256 over sorted (path, content) pairs. Stable across runs."""
    h = hashlib.sha256()
    for p in sorted(paths, key=str):
        h.update(str(p.name).encode("utf-8"))
        h.update(b"\x00")
        h.update(p.read_bytes())
        h.update(b"\x00")
    return h.hexdigest()


def build_expanded(week_data: dict, nfl_games: dict[str, dict]) -> dict:
    """Build the expanded week-data by inlining NFLGame data per top_scorer."""
    expanded = json.loads(json.dumps(week_data))  # deep copy
    for ts in expanded.get("top_scorers", []):
        ctx = ts.get("game_context") or {}
        game_id = ctx.get("game_id")
        if game_id and game_id in nfl_games:
            ts["game"] = nfl_games[game_id]
    return expanded


def regenerate_for_week(week: int, season: int = 2025) -> bool:
    """Regenerate the expanded file for one week. Returns True if written."""
    week_data_path = WEEKS_DIR / f"week{week}_data.json"
    week_data = load_json(week_data_path)

    # Collect referenced game_ids
    game_ids = {
        ts.get("game_context", {}).get("game_id")
        for ts in week_data.get("top_scorers", [])
        if ts.get("game_context", {}).get("game_id")
    }
    referenced_game_paths = sorted(NFL_GAMES_DIR / f"{gid}.json" for gid in game_ids if gid)
    inputs = [week_data_path] + [p for p in referenced_game_paths if p.exists()]

    new_hash = compute_manifest_hash(inputs)

    # Manifest check
    manifest = load_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}
    if manifest.get(str(week)) == new_hash:
        return False  # Already up-to-date

    # Build + write
    nfl_games = {
        p.stem: load_json(p) for p in referenced_game_paths if p.exists()
    }
    expanded = build_expanded(week_data, nfl_games)
    out_path = WEEKS_DIR / f"week{week}_data_expanded.json"
    save_json_canonical(out_path, expanded)

    # Update manifest
    manifest[str(week)] = new_hash
    save_json_canonical(MANIFEST_PATH, manifest)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", type=int, default=None, help="Single week (default: all 1-18)")
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()

    weeks = [args.week] if args.week else list(range(1, 19))
    written = 0
    for w in weeks:
        if regenerate_for_week(w, args.season):
            written += 1
            print(f"  Wrote week{w}_data_expanded.json")
        else:
            print(f"  week{w}: up-to-date (manifest hash unchanged)")
    print(f"  Total written: {written}/{len(weeks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest scripts/tests/test_generate_expanded.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Generate expanded files for all 18 weeks**

```bash
python scripts/generate_expanded_week.py --season 2025
```

Expected: writes 18 expanded files + manifest. Second run: all "up-to-date."

- [ ] **Step 6: Idempotency check**

```bash
python scripts/generate_expanded_week.py --season 2025
git diff content/weeks/*_expanded.json | wc -l
```

Expected: 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/generate_expanded_week.py scripts/tests/test_generate_expanded.py content/weeks/*_expanded.json data/2025/nfl_games/_expanded_manifest.json
git commit -m "feat(data): weekN_data_expanded.json companion + manifest hash

Architect M2: chrome authors who prefer one fetch per week consume the
expanded file (NFLGame data inlined per top_scorer) instead of week_data
+ N per-game files.

Architect N2: content-addressable regeneration via manifest hash at
data/2025/nfl_games/_expanded_manifest.json. Re-runs skip unchanged weeks.

18 expanded files generated. Idempotent.

Tests: +3. Suite: 65+/65+."
```

---

## Task 8: Weekly Fantasy Roster Snapshots — capture-from-now-on

**Files:**

- Modify: `fetch_sleeper.py` (add weekly snapshot capture step)
- Modify: `.gitignore` (add `data/*/fantasy_rosters/`)

- [ ] **Step 1: Read current fetch_sleeper.py structure**

```bash
grep -n -E "^def |^if __name__|step \[" fetch_sleeper.py | head -20
```

- [ ] **Step 2: Add roster-snapshot capture function**

Add to `fetch_sleeper.py` (after the existing fetch step that retrieves `rosters`):

```python
def capture_weekly_roster_snapshot(season: int, week: int, rosters: list[dict]) -> Path:
    """Snapshot all 12 rosters at fetch time.

    Item 13 of phase-1a. Future weeks captured live; weeks already played
    are derived in derive_historical_rosters.py (separate task).
    """
    from scripts.shared import REPO_ROOT, save_json_canonical
    from datetime import datetime, timezone

    snapshot = {
        "week": week,
        "captured": True,
        "derived": False,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "rosters": [
            {
                "roster_id": r["roster_id"],
                "owner_id": r["owner_id"],
                "players": r.get("players") or [],
                "starters": r.get("starters"),
                "reserve": r.get("reserve"),
            }
            for r in sorted(rosters, key=lambda r: r["roster_id"])
        ],
    }
    out_path = REPO_ROOT / "data" / str(season) / "fantasy_rosters" / f"week{week}.json"
    save_json_canonical(out_path, snapshot)
    return out_path
```

- [ ] **Step 3: Wire the capture into the main fetch flow**

In `fetch_sleeper.py`'s main `fetch_season` (or similar) function, after rosters are fetched and current week is determined, call:

```python
current_week = get_current_week(...)  # however the existing code determines week
snapshot_path = capture_weekly_roster_snapshot(season, current_week, rosters)
print(f"  Snapshot: {snapshot_path}")
```

- [ ] **Step 4: Add gitignore entry**

Edit `.gitignore`, add:

```
# Weekly fantasy roster snapshots — Item 13 (phase-1a)
data/*/fantasy_rosters/
```

- [ ] **Step 5: Smoke-test the capture (manual run)**

```bash
python fetch_sleeper.py --season 2025 2>&1 | tail -10
```

Expected: prints `Snapshot: <path>/data/2025/fantasy_rosters/week{N}.json`. File exists.

- [ ] **Step 6: Validate against schema**

```bash
python -c "import json, jsonschema; jsonschema.validate(json.load(open('data/2025/fantasy_rosters/week6.json')), json.load(open('scripts/schemas/fantasy_roster.schema.json')))" && echo OK
```

Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add fetch_sleeper.py .gitignore
git commit -m "feat(fetch): weekly fantasy roster snapshots captured live

Item 13 of phase-1a. Sleeper API only shows current state; without
snapshots, who-owned-which-player-in-week-N becomes unrecoverable
(research-synthesis red flag).

Captured live: week, captured=true, full starters/reserve. Derived
backfill for weeks 1-6 in next task (with starters/reserve null per
architect B2)."
```

---

## Task 9: Derive historical roster snapshots for weeks 1-6 (best-effort, derived=true)

**Files:**

- Create: `scripts/derive_historical_rosters.py`
- Test: `scripts/tests/test_derive_historical_rosters.py`

- [ ] **Step 1: Write failing test**

Create `scripts/tests/test_derive_historical_rosters.py`:

```python
"""Tests for derive_historical_rosters.py.

Architect B2: weeks 1-6 of 2025 are already played; we can recover
players[] from transactions + current state, but starters/reserve
are unrecoverable (per-week designation overwritten).

Schema mandates: derived=true → starters and reserve are null.
"""
import json
from pathlib import Path

import pytest

from scripts.derive_historical_rosters import derive_week


def test_derived_snapshot_has_null_starters():
    """Derived snapshots have null starters/reserve per architect B2."""
    transactions = []  # empty for trivial test
    current_rosters = [
        {"roster_id": 1, "owner_id": "U1", "players": ["p1", "p2"], "starters": ["p1"]},
        {"roster_id": 2, "owner_id": "U2", "players": ["p3"], "starters": ["p3"]},
    ]
    snapshot = derive_week(week=3, current_rosters=current_rosters, transactions=transactions)
    assert snapshot["captured"] is False
    assert snapshot["derived"] is True
    for r in snapshot["rosters"]:
        assert r["starters"] is None
        assert r["reserve"] is None


def test_derived_snapshot_reverses_recent_transactions():
    """Players added after week N are removed from week N's roster."""
    current_rosters = [
        {"roster_id": 1, "owner_id": "U1", "players": ["p_old", "p_new"], "starters": ["p_new"]},
    ]
    # Transaction: p_new added in week 5
    transactions = [
        {"type": "waiver", "week": 5, "adds": {"p_new": 1}, "drops": {}},
    ]
    snapshot = derive_week(week=3, current_rosters=current_rosters, transactions=transactions)
    roster_1 = snapshot["rosters"][0]
    assert "p_new" not in roster_1["players"]  # Wasn't on roster yet in week 3
    assert "p_old" in roster_1["players"]
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python -m pytest scripts/tests/test_derive_historical_rosters.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create the deriver**

Create `scripts/derive_historical_rosters.py`:

```python
"""Best-effort backfill of fantasy roster snapshots for weeks 1-6.

Architect B2: transactions provide adds/drops with timestamps, but
starters/reserve are weekly-set + overwritten — unrecoverable. Snapshot
shape: derived=true, starters=null, reserve=null. players[] IS recoverable
by reverse-applying transactions from current state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from scripts.shared import REPO_ROOT, load_json, save_json_canonical


def derive_week(week: int, current_rosters: list[dict], transactions: list[dict]) -> dict:
    """Derive a roster snapshot for `week` by reversing transactions newer than `week`."""
    # Start from current rosters, work backward
    rosters_by_id: dict[int, dict] = {
        r["roster_id"]: {
            "roster_id": r["roster_id"],
            "owner_id": r["owner_id"],
            "players": list(r.get("players") or []),
            "starters": None,  # Unrecoverable
            "reserve": None,
        }
        for r in current_rosters
    }

    # Sort transactions newest-first; reverse-apply those after `week`
    txns_after = [t for t in transactions if t.get("week", 0) > week]
    txns_after.sort(key=lambda t: -(t.get("week", 0)))

    for txn in txns_after:
        adds = txn.get("adds") or {}  # {player_id: roster_id}
        drops = txn.get("drops") or {}
        # Reverse: a player ADDED after week → remove from snapshot
        for player_id, rid in adds.items():
            if rid in rosters_by_id and player_id in rosters_by_id[rid]["players"]:
                rosters_by_id[rid]["players"].remove(player_id)
        # A player DROPPED after week → add back to snapshot
        for player_id, rid in drops.items():
            if rid in rosters_by_id and player_id not in rosters_by_id[rid]["players"]:
                rosters_by_id[rid]["players"].append(player_id)

    return {
        "week": week,
        "captured": False,
        "derived": True,
        "captured_at": None,
        "rosters": [rosters_by_id[rid] for rid in sorted(rosters_by_id.keys())],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--weeks", nargs="+", type=int, default=[1, 2, 3, 4, 5, 6])
    args = parser.parse_args()

    season_combined = load_json(REPO_ROOT / "data" / str(args.season) / "season_combined.json")
    current_rosters = season_combined.get("rosters") or []
    transactions = season_combined.get("transactions") or []

    out_dir = REPO_ROOT / "data" / str(args.season) / "fantasy_rosters"
    out_dir.mkdir(parents=True, exist_ok=True)

    for w in args.weeks:
        snapshot = derive_week(w, current_rosters, transactions)
        out_path = out_dir / f"week{w}.json"
        save_json_canonical(out_path, snapshot)
        print(f"  derived week{w}.json (rosters: {len(snapshot['rosters'])}, derived=true)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test, verify pass**

```bash
python -m pytest scripts/tests/test_derive_historical_rosters.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run derivation for weeks 1-6**

```bash
python scripts/derive_historical_rosters.py --season 2025 --weeks 1 2 3 4 5 6
```

Expected: prints `derived week{N}.json` for each. Files in `data/2025/fantasy_rosters/`.

- [ ] **Step 6: Validate one against schema**

```bash
python -c "import json, jsonschema; jsonschema.validate(json.load(open('data/2025/fantasy_rosters/week3.json')), json.load(open('scripts/schemas/fantasy_roster.schema.json')))" && echo OK
```

Expected: `OK`.

- [ ] **Step 7: Verify derived snapshots have null starters**

```bash
python -c "import json; d=json.load(open('data/2025/fantasy_rosters/week3.json')); assert d['derived'] is True; assert all(r['starters'] is None for r in d['rosters']); print('OK')"
```

Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add scripts/derive_historical_rosters.py scripts/tests/test_derive_historical_rosters.py
git commit -m "feat(data): derive historical fantasy roster snapshots for weeks 1-6

Item 13 backfill. Reverses transactions from current state. starters/
reserve are null per architect B2 (per-week designation overwritten,
unrecoverable). players[] IS recovered.

Snapshots: derived=true, captured=false. Schema-validated.

Tests: +2. Suite: 67+/67+."
```

---

## Task 10: End-of-Phase-1a verification — full pipeline + idempotency CI check

**Files:**

- No new files. Run full pipeline and verify everything.

- [ ] **Step 1: Run full pipeline once**

```bash
python scripts/fetch_nflreadpy.py --season 2025
python scripts/generate_nfl_games.py --season 2025
python scripts/extract_week_data.py --all --season 2025 --pretty
python scripts/generate_expanded_week.py --season 2025
python scripts/derive_historical_rosters.py --season 2025 --weeks 1 2 3 4 5 6
```

Expected: all four scripts complete without error.

- [ ] **Step 2: Run full pipeline a SECOND time (idempotency check)**

```bash
python scripts/fetch_nflreadpy.py --season 2025
python scripts/generate_nfl_games.py --season 2025
python scripts/extract_week_data.py --all --season 2025 --pretty
python scripts/generate_expanded_week.py --season 2025
python scripts/derive_historical_rosters.py --season 2025 --weeks 1 2 3 4 5 6
```

- [ ] **Step 3: Verify idempotency — git diff is empty (modulo data/external/)**

```bash
git status --porcelain | grep -v '^.. data/external/' | wc -l
```

Expected: `0` (no diffs except cached external data which is gitignored anyway).

- [ ] **Step 4: Run full pytest**

```bash
python -m pytest scripts/tests/ -v 2>&1 | tail -10
```

Expected: 67+ passed (48 baseline + new tests across tasks).

- [ ] **Step 5: Run verifier on all 6 published weeks**

```bash
for w in 1 2 3 4 5 6; do
  echo "=== Week $w ==="
  python scripts/verify_week_content.py --week $w --pretty 2>&1 | grep VERDICT
done
```

Expected: all show `VERDICT: PASS`.

- [ ] **Step 6: Spot-check a player's game_context references a real NFLGame**

```bash
python -c "
import json
d = json.load(open('content/weeks/week6_data.json'))
ts = d.get('top_scorers', [])
for p in ts[:3]:
    gid = p.get('game_context', {}).get('game_id')
    if gid:
        nfl = json.load(open(f'data/2025/nfl_games/{gid}.json'))
        print(f\"{p.get('player_name', '?')} -> {gid} ({nfl['away_team']} @ {nfl['home_team']}, temp={nfl.get('temp')})\")"
```

Expected: prints 3 lines like `Bijan Robinson -> 2025_06_ATL_BUF (ATL @ BUF, temp=52)`.

- [ ] **Step 7: Spot-check expanded file inlines NFLGame**

```bash
python -c "
import json
d = json.load(open('content/weeks/week6_data_expanded.json'))
ts = d['top_scorers'][0]
print('Has game inlined:', 'game' in ts)
print('Inlined keys:', list(ts.get('game', {}).keys())[:5] if 'game' in ts else 'n/a')"
```

Expected: `Has game inlined: True` and shows inlined keys.

- [ ] **Step 8: Final commit (phase 1a closeout)**

```bash
git add -u
git commit --allow-empty -m "chore(phase-1a): closeout — full pipeline + idempotency verified

All Phase 1a items shipped:
- Item 14 (NFLGame as first-class entity, ~272 files)
- Item 1 (game_context references game_id + src field, all 18 weeks)
- Item 13 (weekly fantasy roster snapshots: live + derived)
- Companion: weekN_data_expanded.json (manifest-hash idempotent)

Full pipeline runs cleanly. Idempotency CI check passes (git diff empty
modulo gitignored data/external/). 67+ tests passing. All 6 published
weeks PASS verifier.

Phase 1b next: cross-season Player Arcs + Franchise Wing.
Phase 1c next: writer prompt updates + CLAUDE.md updates."
```

---

## Phase 1a end-state checklist

- [ ] `data/external/` populated with nflreadpy parquet caches (gitignored)
- [ ] `data/2025/nfl_games/` contains ~272 per-game JSON files (each schema-valid)
- [ ] `data/2025/nfl_games/_expanded_manifest.json` exists with hash entries for weeks 1-18
- [ ] `data/2025/fantasy_rosters/` contains weeks 1-6 (derived) + current week (captured) [gitignored]
- [ ] `content/weeks/week{1-18}_data.json` re-extracted with v2 game_context (game_id ref + src)
- [ ] `content/weeks/week{1-18}_data_expanded.json` companion files committed
- [ ] `scripts/fetch_nflreadpy.py` + `scripts/generate_nfl_games.py` + `scripts/generate_expanded_week.py` + `scripts/derive_historical_rosters.py` exist and have tests
- [ ] `scripts/schemas/{nfl_game,game_context,fantasy_roster}.schema.json` exist
- [ ] `scripts/verify_week_content.py` extended Tier 1 check passes for all 6 published weeks
- [ ] `python -m pytest scripts/tests/` returns 67+ passed
- [ ] Idempotency check passes: full pipeline runs twice → `git diff` empty modulo `data/external/`

## What's deferred to Phase 1b

- Item 2 (Player Arcs cross-season) — depends on NFLGame entity (1a) + nflreadpy crosswalk; uses derived snapshots from 1a
- Item 3 (Franchise Wing roster_id-keyed) — depends on Player Arcs for roster_lineage joins

## What's deferred to Phase 1c

- Item 18 (Writer prompt updates for new fields) — references new game_context shape from 1a
- Item 19 (CLAUDE.md updates) — documents new file paths + idempotency convention

---

## Self-review notes

**Spec coverage:** Tasks 1-10 cover all Phase 1a items per spec lines 434-441 (Items 1, 13, 14) plus the implicit prerequisites (canonicalization helper from Task 1, schemas from Task 3, expanded companion from Task 7, derived backfill from Task 9). Item 18 and 19 deferred to Phase 1c per architect N1 fix.

**Placeholder scan:** No "TBD," no "implement later," no "similar to Task N." Each task has full code blocks for the files it creates.

**Type consistency:** `build_game_context_v2`, `_load_player_to_game_crosswalk`, `compute_manifest_hash`, `build_expanded`, `derive_week` are all defined where first used and referenced consistently. JSON schema files referenced by task numbers match their actual filenames.

**TDD pattern:** Each task that creates new code follows test-first: write failing test → run/verify FAIL → implement → run/verify PASS → commit.

**Commit cadence:** 10 commits across 10 tasks. Each commit is atomic, has tests passing, and documents what shipped + which architect finding it addresses.
