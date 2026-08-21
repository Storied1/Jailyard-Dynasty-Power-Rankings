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

**Writer inputs are a positive registry:** `content/writer-inputs.json`. Every fact,
quote, and storyline traces to a registered source dated ≤ the edition's cutoff.
`build_preseason_evidence.py`'s `CHAT_WINDOW_START` (`2023-09-01`, exposing 19,284
admitted chat facts) is a PROJECTION filter, not an admissibility filter — widening it
cannot leak a post-cutoff fact; its old narrowness (1,955 quotes) was what made six
drafts read like an outsider.

**`league_exemplars` is the one class read as FORM, not facts** (`read_as:"form"`,
schema-enforced): the eight power-ranking editions the league wrote for itself in
2023-24 (Karim, Ben, Zach, Patrick, Oscar, Matt, and Blake's own 2023-11-26 Thanksgiving
edition — the bundle `form:` label misattributes that one to Nate; `author_display` is
correct). Projected by fact_id allowlist, fail-closed. The column INHERITS this form.

**Pipeline per edition:** `/write-week N` → `/canon-check N` →
`/edit-week N` (binary gate; APPROVE/REVISE/REJECT) → `/pick-media N` +
`/review-media N` (if the edition uses media) → `/render-week N` →
browser-verify → commit. Preseason uses the `-preseason` variants.

**Blake review loop:** cleared editions export as numbered reading copies to
`Obsidian Vault/MindPalace/10-Projects/` (never overwrite). His notes return SHA-bound;
rebind and verify every checkable claim against live evidence before acting, and push
back with exact evidence where an instruction fails. Craft laws + the battery live in
the auto-memory tree.

**Ranking judgment gate:** every published order is backed by a record passing
`python scripts/verify_ranking_judgment.py --record <path>` (G0 structure, G1
non-arithmetic, G2 ≥3 reasoned fact-bound deviations, G3 contender sanity, G4 ≥2
evidence families per position with ≥1 beyond the box score, G5 citations resolve in the
frozen state). Declared as `meta.ranking_source`; `verify_week_content` enforces the
published order against it, fail closed.

## Data

Full per-file detail: `docs/reference/data-layer.md`. The laws, inline:

- `content/weeks/week{N}_data.json` — per-week writer packet, **cutoff-safe by
  construction** (as-of-week derivations); `_data_expanded.json` companion carries the
  `games{}` map; `python scripts/migration_census.py --all` enforces zero post-cutoff
  facts by exit code. `championships`/`best_win_streak` intentionally absent in-season.
- `content/weeks/week{N}_chat_context.json` (+ preseason variant) — sanitized chat,
  verbatim quotes, every field admitted by exact timestamp ≤ cutoff; arcs carry
  through-cutoff `count` + `first_seen_at`/`last_observed_at`; use `last_observed_at`
  for recency; no status fields.
- `data/2025/league_settings.json` — lineup **QB/RB/RB/WR/WR/WR/TE/FLEX/K/DEF/DL/LB/DB**,
  13 bench / 4 taxi / 2 IR, half PPR, full IDP. Regenerate:
  `python scripts/fetch_league_settings.py --season 2025` (the ONLY network step).
- `data/2025/nfl_games/{game_id}.json` — per-NFL-game entities (EPA, injuries, Vegas,
  weather); `data/2025/fantasy_rosters/week{1..17}.json` — real weekly starters.
- `data/2025/player_arcs/` — cross-season arcs 2022-2025, **regenerate locally only**;
  `data/franchises/` — trophy case, h2h, lineage, historical names.
- `content/team-profiles.json` — team identity registry; `content/rankings/` — accepted
  editorial decisions; `content/chat/` — analytics + `name-map.json` (raw exports and
  `.map_cache/` gitignored); `data/external/*.parquet` + stats caches gitignored.
- Sleeper API (`https://api.sleeper.app/v1`) as live fallback.

> **Project state (HEAD, phase status, what's next) lives in ONE place: the
> roadmap memory** (`project_jailyard_roadmap.md` under the auto-memory
> scope). This file carries rules and mechanics only.

## 2026 Prospective Pipeline (P-lane)

Background lane, append-only stores, frozen policy. **Read
`docs/reference/2026-p-lane.md` before ANY P-lane work** (capture/cutoff/bundle/seal
commands, custody rules, staging guard). Blake-gated: push, scheduler, Tranche B.

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

**Read `docs/reference/known-patterns.md` before pipeline or renderer work.** The
non-negotiables inline: `scripts/shared.py` is canonical for `load_json` /
`save_json_canonical` / `parse_ts` / `admissible` (never define local copies);
`load_json` returns `None` unless `required=True`; `LeagueState.standings()` needs
`season=` explicitly; momentum label sets live in three files and change in one commit;
`sorted()` before serializing any set; scripts bootstrap BOTH import paths.

## Style Conventions

- CSS: kebab-case classes, `clamp()` for responsive type
- JS: camelCase, functional array methods
- Commits: descriptive, informal
- `:root` defines `--bg --fg --muted --accent --accent2 --card --border
--glass --good --bad --warn`

## Key Scripts

Full table: `docs/reference/scripts.md`. Most-used: `fetch_sleeper.py` (season data),
`scripts/extract_week_data.py` (packets, always `--pretty`), `scripts/value_rosters.py`
(the valuation desk), `scripts/verify_week_content.py` / `verify_ranking_judgment.py` /
`canon_checks.py` / `migration_census.py` (gates), `scripts/build_chat_context.py`
(`--no-ai`, no `--all` mode — loop `--week N`), `scripts/build_preseason_evidence.py`
(`--verify` preflight), `scripts/generate_chat_provenance.py` (verify default; rewrite
only receipt-bound).

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

Editions: `/write-week N`, `/edit-week N`, `/canon-check N`, `/render-week N`,
`/pick-media N`, `/review-media N`, plus `-preseason` variants of write/edit/render.
Data + quality: `/data-refresh`, `/audit`, `/review`, `/refactor`, `/test`.

## Local LLM Integration (Ollama)

Ollama at `localhost:11434` (Qwen 3.5 9b/35b, qwen3-coder 30b, nomic-embed); MCP server
`scripts/ollama_mcp_server.py`; details + quirks: `docs/reference/ollama.md` and the
`reference_ollama_integration` memory.

## Environment

- Local dev: `python -m http.server 8000`; Python is `python` (Windows, 3.12);
  `pip install -r requirements.txt` on fresh clones (optional AI/media deps commented).
- GIPHY key in `.claude/settings.local.json` (gitignored); `describe_media.py
--backend claude-cli` runs headless Claude on the Max sub, resumable.
- GitHub Actions: `fetch_sleeper.py` on NFL Sundays; test CI on every push/PR to `main`.
  **After every push, watch CI keyed to HEAD's SHA:**
  `gh run watch $(gh run list --commit $(git rev-parse HEAD) --limit 1 --json databaseId --jq '.[0].databaseId') --exit-status`
- **Pre-commit gotchas:** eslint skips without a config; the PostToolUse semgrep scan
  blocks dynamic `urllib.urlopen` (pass with constant Sleeper host + digits-only ID +
  justified `# nosemgrep`); phantom `M` files after committing generated JSON get
  `git checkout --` only if `git diff` is empty and values parse-identical.
- **HTML is prettier-excluded** (`.prettierignore` = `*.html`): hand-maintained compact
  HTML must not be reformatted; do not remove the ignore.
