# CLAUDE.md — The Jailyard Dynasty Power Rankings

## Quick Context

Static site + editorial system for a 12-team dynasty fantasy football league
(est. 2022). Pure HTML/CSS/JS, inline everything, zero dependencies. Data from
the Sleeper API (cached JSON + live fallback), enriched with real-NFL context
(nflreadpy). The written product is a season of long-form column editions;
`content/editorial-standard.md` defines the bar.

## Tech Stack

- HTML5 / CSS3 / Vanilla JS (no frameworks, no npm, no build)
- Canvas 2D API for charts (scatter, stacked bar, trend, Elo)
- Python 3 for the data pipeline (`fetch_sleeper.py`, `scripts/*.py`)
- GitHub Actions for automated weekly data fetches + the test suite
- Hosted as static files (GitHub Pages or direct)

## Pages

| File                  | Purpose                                                                      |
| --------------------- | ---------------------------------------------------------------------------- |
| `index.html`          | Landing — starfield canvas, stat counters, nav cards, Championship Vault     |
| `season.html`         | Season hub — weekly results, power rankings, trend charts (Sleeper API)      |
| `power-rankings.html` | Standalone power rankings page                                               |
| `history.html`        | League Bible — all-time records, H2H matrix, Elo ratings, franchise profiles |
| `draft.html`          | Draft recap — full draft board, grades, storylines                           |
| `trades.html`         | Trade tracker — timeline, season filter, activity chart                      |
| `config.js`           | Central league config — name, Sleeper IDs, colors, nav (edit to rebrand)     |

Edition pages (`preseason-2025.html`, `week{N}.html`) are produced by
`/render-preseason` and `/render-week N` as editions publish, and join the
`config.js` `pages` "columns" group.

## The Editorial System

Editions publish in chronological order: preseason first, then weeks 1→18.
Power rankings are the recurring spine; each edition develops its own form
from that week's material (`content/editorial-standard.md`).

**Writer inputs are a positive registry:** `content/writer-inputs.json`.
Every fact, quote, and storyline in an edition traces to a registered source
dated at or before the edition's cutoff. The classes: the week's data packet,
the sanitized chat context (quotes verbatim), franchise history data, the
team registry, accepted decisions (`content/rankings/`), published editions
of this run, and contemporaneous NFL coverage cited with its publication
date.

**Pipeline per edition:** `/write-week N` → `/canon-check N` →
`/edit-week N` (binary gate; APPROVE/REVISE/REJECT) → `/pick-media N` +
`/review-media N` (if the edition uses media) → `/render-week N` →
browser-verify → commit. Preseason uses the `-preseason` variants.

**Ranking judgment gate:** every published ranking order is backed by a
judgment record passing `python scripts/verify_ranking_judgment.py --record
<path>` — G0 structure (exactly 12 positions/ranks/rosters), G1
non-arithmetic ordering, G2 ≥3 reasoned fact-bound deviations from the
wins-then-points baseline, G3 contender sanity, G4 ≥2 evidence families per
position (≥1 beyond the box score), G5 every citation resolves in the
edition's frozen state. The record is declared as `meta.ranking_source`;
`verify_week_content.check_rankings_order` enforces the published order
against it (fail closed), or against the standings sort when no record is
declared.

## Data

- `config.js` — league branding, Sleeper IDs, nav links (loaded by all pages)
- `data/{year}/season_combined.json` — main season data file
- `data/league_history.json` — cross-season analytics (Elo, H2H, records)
- `content/weeks/week{N}_data.json` — per-week writer packet. **Cutoff-safe by
  construction:** every cutoff-sensitive field (h2h totals + `last_meeting`,
  `historical_context` records, Elo/all-time enrichment) is derived as-of week
  N by `extract_week_data.py` (`as_of_h2h`, `as_of_records`,
  `compute_as_of_history`); `python scripts/migration_census.py --all`
  enforces zero post-cutoff facts across every packet by exit code.
  `championships`/`best_win_streak` are intentionally absent in-season.
- `content/weeks/week{N}_data_expanded.json` — denormalized companion:
  top-level `games{}` map keyed by `game_id`; manifest-hash idempotent
  (`data/2025/nfl_games/_expanded_manifest.json`)
- `data/2025/nfl_games/{game_id}.json` — per-NFL-game entity (scores, EPA
  `team_stats`, `key_injuries`, `rest_days`, `div_game`, `spread_line`,
  roof/temp/wind). `game_context` references these by `game_id`
- `data/2025/fantasy_rosters/week{1..17}.json` — per-week roster snapshots
  with real starters
- `data/{year}/draft_picks.json` — Sleeper draft picks per season
- `data/2025/player_arcs/{player_id}.json` + `_index.json` — cross-season
  player arcs 2022-2025; **regenerate locally only** (inputs include
  gitignored `players.json` + stats caches)
- `data/franchises/{roster_id}.json` + `_index.json` — franchise data:
  trophy case, h2h, roster lineage, season results, historical names
- `content/team-profiles.json` — team identity registry (roster_id, name,
  owner); schema `scripts/schemas/team_registry.schema.json`
- `content/rankings/` — accepted structured editorial decisions
- `content/weeks/week{N}_chat_context.json` (+
  `content/preseason-2025/preseason_chat_context.json`) — sanitized league
  chat per edition: verbatim quotes, storylines, league memory, every field
  admitted by exact timestamp at or before the cutoff. Arcs/jokes carry
  through-cutoff `count` + exact `first_seen_at`/`last_observed_at` bounds;
  no status fields; use `last_observed_at` for recency
- `content/chat/` — chat analytics + `name-map.json` (WhatsApp name → real
  name, team, roster_id); `chat/` raw exports and `.map_cache/` are
  gitignored
- `data/external/*.parquet` — gitignored nflreadpy caches
- `data/{year}/nfl_stats_week{N}.json` — gitignored Sleeper stats cache
- Sleeper API (`https://api.sleeper.app/v1`) as live fallback

> **Project state (HEAD, phase status, what's next) lives in ONE place: the
> roadmap memory** (`project_jailyard_roadmap.md` under the auto-memory
> scope). This file carries rules and mechanics only.

## 2026 Prospective Pipeline (P-lane)

Contract: `docs/superpowers/plans/2026-08-03-jailyard-p-only-fallback.md`.
Modules: `scripts/{capture,capture_optional,cutoff,bundle,seal}_2026.py`.

```bash
export POLARS_SKIP_CPU_CHECK=1   # required for the nflreadpy path
python scripts/capture_2026.py --season 2026 --tranche A
python scripts/capture_2026.py --season 2026 --component <id>
python scripts/cutoff_2026.py --season 2026 --write-receipt
python scripts/bundle_2026.py --edition <ed> --arm record_points --policy content/governance/source_policy_2026.v1.json
python scripts/seal_2026.py --edition <ed> --arm record_points --trial 1
python scripts/seal_2026.py --verify-all     # and --rederive-all
```

- **Append-only store** — `data/captures/2026/`, `content/seals/2026/` are
  never edited, deleted, or re-sealed; exclusive-create enforces it.
- **`source_policy_2026.v1.json` is FROZEN** — supersede only via a new
  version; freezing requires `--expected-candidate-sha256`.
- **Prospective label** = ended AND sealed ≤ cutoff, read only from the
  hash-verified cutoff receipt; no reclassification mechanism exists.
- **Locators are repo-relative POSIX**; the seals tree is TRACKED;
  `private_captures/` + `private_bundles/` are gitignored — never `git add -f`.
- **Staging guard before committing captures/bundles:**
  `git diff --cached --name-only | grep -qE '^(private_captures|private_bundles)/'`
  must match nothing.
- **New scripts bootstrap BOTH paths** — `scripts/` AND the repo root.

## Critical Rules

- **Every fact traces to its source at its time.** Editions cite only
  registered sources (`content/writer-inputs.json`) dated at or before the
  edition's cutoff. Chat quotes verbatim; numbers from the packet; outside
  coverage carries its publication date.
- **No machine tells in prose** — zero em dashes, no "it's not X, it's Y"
  constructions, prose never discusses how the column gets made. Audience:
  sharp, college-educated league members.
- **Publication order is chronological** — preseason first, then weeks in
  order; a callback lands only on a published edition.
- **As-if-realtime** — edition bodies and week subtitles use only knowledge
  available at that point in the season. Site chrome (Vault, landing, meta)
  is present-day and exempt.
- **Quality gates are binary** — a gate that finds an error returns REVISE/
  FAIL. Never rationalize exceptions. Fix first, approve second.
- **Uniform temporal contract** — every knowledge-cutoff admission goes
  through `shared.admissible` (exact tz-aware instant ≤ cutoff; malformed/
  naive/date-only rejected). Full contract:
  `docs/superpowers/specs/2026-07-12-jailyard-governance-crosswalk.md`.
- **Chat provenance** — `python scripts/generate_chat_provenance.py`
  (`--verify` default) checks `content/chat/provenance.json` against disk;
  the manifest is rewritten ONLY via receipt-bound `--write --receipt <path>`
  after a green `--rebuild-check`. Never bless a manifest by hand.
- **KEEP everything inline; ZERO dependencies; glassmorphic dark theme; CSS
  variables (`--accent2`, not `--accent-2`); Canvas handles
  `devicePixelRatio`; no `animation-iteration-count: infinite` for
  shimmer/pulse/glow.**
- **Data changes update all consumers** — grep every reference when a schema
  moves.
- **Sleeper bracket data has 2 games at max round** — championship
  (`min(matchup_id)`) + 3rd-place; always filter to `min(m)`.
- **2025 season ended at week 17** — wk17 is the championship; week 18 has 0
  games (finale/awards edition, never a standard week).
- **Never trust AI-generated inline data arrays** — cross-reference against
  Sleeper API endpoints before publishing.
- **Content fixes require HTML re-render** — editing a content JSON does not
  update its page.

## Known Patterns

- Data loading: try cached JSON → catch → live Sleeper API → catch → error UI
- IIFEs for scope isolation; `idFromName()` for HTML-safe ids; View
  Transitions API; Speculation Rules; Intersection Observer `.visible`
- `scripts/shared.py` is canonical for `load_json`, `save_json_canonical`,
  `parse_ts`, `admissible`, path constants, Ollama config. Never define local
  copies.
- Theme has two toggle paths: nav button (config.js) + keyboard `t`/`T`
  (index.html only); keep in sync.
- `franchise_map` stores CURRENT team names; historical names live in
  `data/franchises/` per season.
- **Momentum label sets** — team: `opening | early | cooling | collapsing |
steady | hot | surging`; matchup: `too early | coin flip | slight edge |
heavy lean | upset brewing`. Defined in `shared.py`,
  `extract_week_data.py`, `verify_week_content.py`; adding a label updates
  all three in one commit.
- **Script import pattern:** scripts runnable under pytest AND directly
  insert `scripts/` into `sys.path[0]` before `from shared import ...` (see
  `scripts/fetch_nflreadpy.py`).
- **Idempotency convention:** generators write via `save_json_canonical`;
  re-extraction idempotency rides input-hash manifests, not byte-parity with
  prettier-formatted committed files. Data-layer spec:
  `docs/superpowers/specs/2026-05-02-jailyard-content-depth-design.md`.
- `shared.load_json(path)` returns `None` on a missing file; pass
  `required=True` for a loud error.
- `build_chat_context.py` has no `--all` mode — loop `--week N`.
- `list(set)` order is non-deterministic (`PYTHONHASHSEED` unpinned) — use
  `sorted()` before serializing set contents.
- `{{media:*}}` token validation is `essay_tokens.issubset(slot_ids)`, not
  equality — a `type:"custom"` hero slot renders separately.
- `verify_week_content.py` Tier 1 has a `warnings` channel beside `errors`
  — structural violations are errors; heuristic findings are warnings.
- `LeagueState.standings()` must be passed `season=` explicitly — an
  unqualified call folds every admitted game across seasons.

## Style Conventions

- CSS: kebab-case classes, `clamp()` for responsive type
- JS: camelCase, functional array methods
- Commits: descriptive, informal
- `:root` defines `--bg --fg --muted --accent --accent2 --card --border
--glass --good --bad --warn`

## Key Scripts

| Script                                 | Purpose                                                              |
| -------------------------------------- | -------------------------------------------------------------------- |
| `fetch_sleeper.py`                     | Fetch season data from Sleeper API                                   |
| `scripts/extract_week_data.py`         | `season_combined.json` → per-week writer packets (as-of-week slices) |
| `scripts/generate_expanded_week.py`    | `week{N}_data_expanded.json` companions (games map)                  |
| `scripts/generate_nfl_games.py`        | Per-game NFLGame entities (EPA, injuries) from `data/external/`      |
| `scripts/fetch_nflreadpy.py`           | nflreadpy caches → `data/external/*.parquet`                         |
| `scripts/verify_week_content.py`       | Edition validator (structure, data accuracy, chat, ranking order)    |
| `scripts/verify_ranking_judgment.py`   | Ranking judgment gate (G0-G5)                                        |
| `scripts/migration_census.py`          | Zero-post-cutoff-facts census over packets + compiled states         |
| `scripts/canon_checks.py`              | Sanitizer-artifact pre-render gate                                   |
| `scripts/parse_whatsapp.py`            | Raw WhatsApp export → `chat/parsed_messages.json`                    |
| `scripts/map_chat_deterministic.py`    | Chat MAP stage (monthly chunks)                                      |
| `scripts/reduce_chat_deterministic.py` | Chat REDUCE stage → analytics                                        |
| `scripts/build_chat_context.py`        | Per-edition sanitized chat context (`--no-ai` deterministic)         |
| `scripts/generate_chat_provenance.py`  | Chat pipeline provenance (verify / receipt-bound rebuild)            |
| `scripts/generate_player_arcs.py`      | Cross-season player arcs (local only)                                |
| `scripts/generate_franchise_wings.py`  | Franchise data files keyed by roster_id                              |
| `scripts/fetch_draft_picks.py`         | Sleeper draft-pick backfill                                          |
| `scripts/derive_historical_rosters.py` | Per-week roster snapshots                                            |
| `scripts/claims_ledger.py`             | Scoreable claims with resolution rules fixed at claim time           |
| `scripts/resolve_media.py`             | Resolve media picks to CDN URLs                                      |
| `scripts/describe_media.py`            | Catalog league media via headless Claude (`--backend claude-cli`)    |

## Common Tasks

- **Produce an edition:** `/write-week N` → `/canon-check N` → `/edit-week N`
  → media (if used) → `/render-week N` → browser-verify → commit
- **Validate content:** `python scripts/verify_week_content.py --week N --pretty`
- **Gate a ranking:** `python scripts/verify_ranking_judgment.py --record <path>`
- **Census:** `python scripts/migration_census.py --all`
- **Refresh data:** `python fetch_sleeper.py --all` then commit `data/`
- **Extract packets:** `python scripts/extract_week_data.py --all --pretty`
  (always `--pretty`)
- **Rebuild chat context:** `python scripts/build_chat_context.py --week N --season 2025 --no-ai`
- **Run tests:** `python -m pytest scripts/tests/ -v` (counts live in the
  roadmap memory)
- **Regenerate dynasty layer:** `generate_player_arcs.py` then
  `generate_franchise_wings.py` (local only)

## Slash Commands (`.claude/commands/`)

| Command             | Purpose                               |
| ------------------- | ------------------------------------- |
| `/write-week N`     | Write the week's edition              |
| `/edit-week N`      | Binary editorial gate                 |
| `/canon-check N`    | Artifact + continuity pre-render gate |
| `/render-week N`    | Render edition → HTML                 |
| `/write-preseason`  | Write the preseason edition           |
| `/edit-preseason`   | Binary editorial gate (preseason)     |
| `/render-preseason` | Render preseason edition              |
| `/pick-media N`     | Choose media for declared slots       |
| `/review-media N`   | Creative pass over media picks        |
| `/data-refresh`     | Refresh data from Sleeper API         |
| `/audit`            | Security and quality scan             |
| `/review`           | Code review                           |
| `/refactor`         | Behavior-preserving cleanup           |
| `/test`             | Run tests and validation              |

## Local LLM Integration (Ollama)

- **Ollama** at `localhost:11434`: `huihui_ai/qwen3.5-abliterated:9b` (fast),
  `huihui_ai/qwen3.5-abliterated:35b` (heavy), `huihui_ai/qwen3-coder-abliterated:30b`
  (agentic coding), `nomic-embed-text` (embeddings)
- **MCP server** (`scripts/ollama_mcp_server.py`) exposes
  `ollama_generate/chat/embed` via `.mcp.json`
- **Chat embeddings** (`scripts/embed_chat.py`) — semantic search over the
  chat corpus
- **Post-edit hook** (`scripts/local_review_hook.py`) — Qwen reviews diffs
- Qwen 3/3.5 `<think>` tokens consume `num_predict`; scripts double limits

## Environment

- Local dev: `python -m http.server 8000` or open HTML directly
- Python: use `python` not `python3` (Windows;
  `C:\Users\blake\AppData\Local\Programs\Python\Python312\python`)
- `pip install -r requirements.txt` on fresh clones; optional AI/media deps
  commented in the file
- GIPHY API key in `.claude/settings.local.json` (gitignored)
- `describe_media.py --backend claude-cli` runs headless Claude Code on the
  Max subscription; resumable; exits cleanly on usage-window limits
- GitHub Actions runs `fetch_sleeper.py` on NFL Sundays; test CI runs on
  every push/PR to `main`
- **After every push, watch CI keyed to HEAD's SHA:**
  `gh run watch $(gh run list --commit $(git rev-parse HEAD) --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status`
- **Pre-commit gotchas:** eslint skips when no config exists; the PostToolUse
  semgrep scan blocks dynamic `urllib.urlopen` (pattern that passes: constant
  Sleeper host + digits-only ID validation + justified `# nosemgrep`);
  committing generated JSON can leave phantom `M` files (if `git diff` is
  empty and values parse-identical, `git checkout -- <files>`)
- **HTML is prettier-excluded** (`.prettierignore` = `*.html`): hand-
  maintained compact HTML must not be reformatted; do not remove the ignore.
