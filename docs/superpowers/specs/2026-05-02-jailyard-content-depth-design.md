---
title: Jailyard Dynasty — Content-Depth Workstream Design (REVISED)
date: 2026-05-02 (created) · 2026-05-03 (revised post-/critique + spike)
status: REVISED — pending architect review
type: design-spec
workstream: content-depth (chrome-agnostic core + distribution layer)
sequencing-position: 1 of 3 (content-depth → chrome/redesign → weeks 7-18)
parent-decision: 40-Decisions/2026-04-08-jailyard-v2-sequencing.md
related: docs/v2-research-synthesis.md · docs/v2-concept-01-the-clubhouse.md · docs/v2-potentials.md
revision-summary: |
  v2 (2026-05-03): /critique 3-agent gate found scope drift + 5 silent dependencies.
  Data-source spike empirically confirmed: Satori-Python doesn't exist (PyPI search
  returned "No matching distribution"); OpenWeatherMap historical is paid-only;
  ESPN scoreboard injury feed misclaimed in v1 spec. Replaced 3 fragile sources
  with single nflreadpy library (MIT, free, 12,435-row sleeper_id↔gsis_id crosswalk
  via load_ff_playerids). Promoted cross-season Player Arcs + Weekly Roster Snapshots
  + NFLGame as first-class entity to MUST. Added Distribution Layer (L5). Added
  Sunday Drop ritual + Discord webhook + TTS Field Notes per elite advisor. Demoted
  Items 8/11/12 (My Team standalone, Container Queries standalone, Web Share standalone).
  Editorial typography stays MUST with chrome-flexible token sets.
---

# Jailyard Dynasty — Content-Depth Workstream

## Context

Jailyard Dynasty Power Rankings is a static fantasy football site for a 12-person dynasty league with 4 years of history (2022-2025). Following the April 8, 2026 v2-sequencing decision, the next workstream is **content depth first**, before redesign (handoff_jailyard-v2-vision) and before writing weeks 7-18.

The April-2026 v2 data-enrichment remediation already shipped per-player `game_context` (one*liner / opponent / stat_line) and per-team momentum trajectories. That was \_narrative* depth infrastructure for prose. This workstream is **substance** depth — the 21K-message chat, 4 years of cross-season data, and external NFL reality are rich, but the surfaces are dumb. We're building the data layer + generators + universal patterns + 2026 web primitives + distribution layer that any future chrome (Clubhouse, Yard, Playfield, JailyardOS, or a not-yet-imagined v9-v11 mockup) can consume identically.

**Diagnosis (Blake's words):** "Data is rich but surfaces are dumb." The fix is a five-layer fabric, not a single feature.

**Brainstorm reframing acknowledgment:** The April 8 v2-sequencing decision used "content depth" with two readings. The brainstorming pass with Blake (2026-05-02) ratified the scope as "data/pipeline enrichment for new content forms" (not prose rewriting). This spec executes the brainstorm-ratified scope.

**Audience priority** (from preferences ratified in brainstorm):

1. League members (12 friends, Sunday-Wednesday cycle, casual phone read) — primary
2. Blake-as-archivist (look-back, cross-season coherence) — secondary
3. Portfolio outsider (sample-season showcase) — tertiary

**Ethos:** Top-tier output, no time pressure, bleeding edge where it serves the league. Football season starts August 2026, giving 4 months of focused runway.

## Out of scope (explicitly deferred)

- Chrome / redesign decision (handoff_jailyard-v2-vision; v9-v11 mockups still being explored)
- Writing weeks 7-18 (handoff to come after redesign)
- 11ty migration (separate handoff)
- Three-Reaction System (Clubhouse-coupled)
- Polygraph / Grudge Ledger / Reputation Archetypes (Yard-coupled, conflicts with "social fabric not load-bearing" caveat)
- The Field / Bloom / Threads / Rail (Playfield-coupled)
- JailyardOS window manager (chrome itself)
- Drama timeline UI / chat-derived awards (Blake caveat: not load-bearing, not awards)
- Cmd-K palette (chrome-coupled polish; defer)
- WebGPU + Whisper voice search (fun easter egg, not load-bearing)
- CSS Houdini Paint API generative backgrounds (interesting, not Phase 1)
- OPFS for owner annotations (requires user research first)
- Email digest (chrome-coupled UI for opt-in flow; defer to chrome handoff)

Each is real future work; none belongs here.

## Architecture — the 5-layer fabric

```
┌──────────────────────────────────────────────────────────────┐
│ L1: DATA (JSON)                                              │
│   Pure data files any chrome reads. Build-time generated.    │
│   ─ weekN_data.json (extended top_scorers[].game_context)    │
│   ─ data/2025/nfl_games/{game_id}.json (NEW first-class)     │
│   ─ data/2025/player_arcs.json (cross-season MUST)           │
│   ─ data/2025/fantasy_rosters/week{N}.json (snapshots MUST)  │
│   ─ data/franchises/{roster_id}.json                         │
│   ─ data/2025/receipts.json                                  │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ L2: GENERATORS (Python build-time)                           │
│   Take L1 data + templates → produce binary/SVG/audio.       │
│   ─ scripts/generate_verdict_cards.py → 1200x630 PNGs        │
│   ─ scripts/charts/*.py → standalone SVG files               │
│   ─ scripts/generate_field_notes_audio.py → .mp3 (TTS)       │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ L3: PATTERNS (CSS/JS modules)                                │
│   Drop-in primitives any chrome composes.                    │
│   ─ content/editorial.css (typography, drop caps, grain)     │
│     · with chrome-flexible token sets (default + mono alt)   │
│   ─ content/components/receipt.js (Web Component)            │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ L4: 2026 INTERACTION PRIMITIVES (native CSS/HTML/JS)         │
│   No libraries. Just patterns to apply.                      │
│   ─ Popover API + Anchor Positioning                         │
│   ─ View Transitions API named regions                       │
│   ─ Container queries (BAKED into L3, not standalone)        │
│   ─ Web Share API (BAKED into Verdict Card consumer code)    │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│ L5: DISTRIBUTION (NEW)                                       │
│   How content reaches the league outside the URL.            │
│   ─ scripts/release_week.py (Sunday Drop ritual)             │
│   ─ scripts/post_to_discord.py (webhook auto-post)           │
│   ─ OG meta tags on every Verdict Card URL                   │
└──────────────────────────────────────────────────────────────┘
```

**Per-phase usability requirement:** Each phase must produce demonstrably usable artifacts that stand on their own (not "infrastructure waiting for chrome"). Phase 1 outputs are queryable JSON. Phase 2 outputs are shareable PNGs and renderable SVGs. Phase 3 outputs go live on the existing site via additive integration.

## The 15 items — full specification

> **Item-numbering note:** Numbering reflects revision history (NEW items added at the end). Layer order in the architecture diagram differs from numerical order. See category tags (MUST / SHOULD / NEW-2026 / DEMOTED).

### Layer 1: DATA

#### 1. Real Game Context expansion (MUST) — REVISED post-spike

**Spike findings consolidated source:** Originally proposed 3 sources (ESPN scoreboard + ESPN injury feed + OpenWeatherMap). Empirically: ESPN scoreboard provides `homeAway` ✓ but NOT injury or weather; OpenWeatherMap historical is paid-only. Replaced with **single source: nflreadpy** (MIT-licensed, free, no auth):

- `home_away` — `"home" | "away" | null`. Source: `nflreadpy.load_schedules(2025).home_team / away_team`.
- `weather` — `{temp, wind_mph, roof, surface}` or null for indoor. Source: `nflreadpy.load_schedules` columns `temp`, `wind`, `roof`, `surface`.
- `opponent_def_epa` — number, opponent's defensive EPA-allowed (lower = better defense). Replaces the spec-v1's "opponent_dvoa" claim (DVOA is proprietary Football Outsiders, not in nflreadpy). Derived from `nflreadpy.load_team_stats` columns `passing_epa`, `rushing_epa`, `receiving_epa` aggregated per opponent per week.
- `injury_status` — string enum or null. Source: `nflreadpy.load_injuries(2025)` columns `report_status`, `practice_status`, `report_primary_injury`. Player linkage via `gsis_id` ↔ `sleeper_id` crosswalk.
- **`src` (NEW — architect M3)** — string indicating which source populated each above field. Enum: `"nflreadpy" | "sleeper_stats" | "fallback" | null`. Used so downstream consumers can degrade gracefully when nflreadpy is upstream-broken (e.g., missing → fall back to Sleeper undocumented stats endpoint, then null). Schema: `game_context.src = {"home_away": "nflreadpy", "weather": "nflreadpy", "opponent_def_epa": "fallback", "injury_status": null}`.
  - **Default consumer policy (architect N4):** render fields regardless of `src`; surface `src=null` (data unavailable) by omitting the field entirely. Consumer-side logging when `src="fallback"` is optional and chrome-author's choice.

**Player-id crosswalk (NEW data dependency):** `nflreadpy.load_ff_playerids()` provides 12,435-row crosswalk including both `sleeper_id` (our existing data key) and `gsis_id` (nflreadpy's stats key). Cache to `data/external/ff_playerids.json` on first build; refresh weekly during NFL season.

**File:** `scripts/extract_week_data.py` (extend `build_game_context`) + new `scripts/fetch_nflreadpy.py` (fetch + cache nflreadpy outputs).
**Output:** Same `weekN_data.json` schema. Each `top_scorers[].game_context` now references parent `game_id` (per Item 14) instead of nesting weather/opponent inline.
**Backfill:** All 18 weeks of 2025 season.
**Verification:** `verify_week_content.py` Tier 1 check — each top_scorer with ownership > 0% has either a populated game_context OR an explicit reason ("bye_week" | "did_not_play" | "no_game_data"). Falls back gracefully.

#### 2. Player Arcs — cross-season MUST (REVISED)

Cross-week + cross-season per-player timeline. The substrate for "click any player anywhere → modal with full timeline" interaction in any future chrome.

**Cross-season is MUST (was deferred in v1).** A dynasty league with redraft-only arcs is missing the dynasty. Transactions data exists in `season_combined.json` for 2022-2025 already.

**Output:** `data/2025/player_arcs.json` — keyed by Sleeper `player_id`, structured as:

```json
{
  "4017": {
    "player_id": "4017",
    "gsis_id": "00-0039004",
    "name": "Bijan Robinson",
    "position": "RB",
    "current_owner": {"roster_id": 3, "team_name": "Legion of Bouz"},
    "ownership_history": [
      {"event": "draft", "season": 2024, "round": 1, "pick": 5, "roster_id": 3, "date": "2024-08-15"},
      {"event": "rostered", "from": "2024-08-15", "to": "2024-12-08", "roster_id": 3},
      {"event": "trade", "date": "2024-12-08", "from_roster_id": 3, "to_roster_id": 7, "in_return": [...]},
      {"event": "rostered", "from": "2024-12-08", "to": "present", "roster_id": 7}
    ],
    "weekly": [
      {"week": 1, "season": 2025, "fantasy_points": 27.4, "game_id": "2025_01_ATL_PIT", "owner_roster_id": 7, "status": "played"},
      {"week": 2, "season": 2025, "fantasy_points": null, "game_id": null, "owner_roster_id": 7, "status": "bye_week"},
      ...
    ],
    "season_aggregates": {"2025": {"total_fantasy_pts": 178.3, "weeks_played": 5, "weeks_on_bye": 1, "best_week": {...}, "worst_week": {...}}, "2024": {...}, "2023": {...}, "2022": {...}}
  }
}
```

**Edge-case schemas (NEW, per blind-spot + architect critics):**

- **Bye week:** `{week, fantasy_points: null, game_id: null, status: "bye_week"}`
- **Played but 0 fantasy points:** `{week, fantasy_points: 0.0, game_id: "...", status: "played"}`
- **Inactive (DNP):** `{week, fantasy_points: null, game_id: "...", status: "did_not_play"}`
- **Retired mid-season (architect Mi3):** `{week, fantasy_points: null, game_id: null, status: "retired", retired_date: "YYYY-MM-DD"}` — applied to all weeks ≥ retirement date. Source: nflreadpy.load_players or roster-presence delta.
- **Mid-season trade:** ownership_history includes `event: "trade"` entries with `from_roster_id`, `to_roster_id`, `in_return` (other-side players exchanged)
- **Same-name players:** keyed by `player_id` always; display logic uses `f"{name} ({position}, {nfl_team})"` to disambiguate
- **Null starters in derived snapshots (architect B2):** weeks 1-6 of 2025 use derived roster snapshots from Item 13, which lack starters/reserve designation. Player Arc consumer treats `weekly[].owner_roster_id` as authoritative (still derivable) but does NOT depend on starters/reserve for those weeks; downstream UI can render "no starter info available" if needed.

**File:** `scripts/generate_player_arcs.py` (new). Reads `data/league_history.json`, `data/2025/season_combined.json`, all 4 seasons of transaction history, `weekN_data.json` files for 2025, nflreadpy data per Item 1.
**Scope:** All players who appeared in any roster across ANY of 2022-2025 seasons. This is the dynasty layer; non-negotiable.
**Verification:** Spot check 5 high-traffic players (Mahomes, Bijan, Henry, Allen, Chase). Each has continuous weekly entries from W1 to W6 with correct owner attribution. Trade events link both sides correctly.

#### 3. Franchise Wing (MUST) — REVISED

Per-team permanent biography that builds across season + cross-season.

**Primary key change:** `roster_id` (stable across team renames) instead of `team_slug`. CLAUDE.md notes "franchise_map stores CURRENT team names, not historical" — using roster_id sidesteps the rename problem.

**Output:** `data/franchises/{roster_id}.json` — 12 files, one per roster_id. Schema otherwise unchanged from v1 (trophy_case, all_time_record, h2h, milestones, roster_lineage, voice_bible_callbacks). Rename map (current_team_name vs historical names) lives in a separate `data/franchises/_index.json`.

**File:** `scripts/generate_franchise_wings.py` (new).
**Verification:** Each of 12 files exists keyed by roster_id. Trophy case matches championship vault on `index.html`. Roster_id remains stable across seasons (verify by joining transactions across years).

#### 13. Weekly Fantasy Roster Snapshots (NEW · MUST · per elite advisor)

**Why:** Sleeper API only shows CURRENT roster state. Without weekly snapshots, who-owned-which-fantasy-player-in-week-3 becomes permanently unknowable. Research synthesis flagged this in red letters; spec-v1 missed it.

**File:** `fetch_sleeper.py` (extend with weekly snapshot capture, ~3 lines) + new gitignored cache directory.
**Output:** `data/2025/fantasy_rosters/week{N}.json` — 12 entries, each `{roster_id, owner_id, players: [player_ids], starters: [player_ids] | null, reserve: [player_ids] | null, captured: bool, derived: bool}`. Captured at the time of each weekly fetch. Gitignored per Phase 14 cache pattern (`.gitignore` extends to cover `data/*/fantasy_rosters/`).
**Backfill (architect B2 correction):** Cannot fully backfill historical weeks. Sleeper transactions provide adds/drops with timestamps but **NOT starter/reserve weekly designation** (that's set per-week and overwritten — unrecoverable). For weeks 1-6 of 2025 already played:

- `players[]` IS recoverable (transactions + current state)
- `starters[]` is `null` with `derived: true` flag
- `reserve[]` is `null` with `derived: true` flag
- New weeks captured from now on get `captured: true` and full `starters[]`/`reserve[]`
  Item 2 (Player Arcs) consumer handles the null case; downstream UI shows "no starter info available" for derived weeks.
  **Verification:** Run `fetch_sleeper.py` once → confirm `week{current}.json` exists. Confirm content matches Sleeper API at fetch time.

#### 14. NFLGame as first-class entity (NEW · MUST · per elite advisor)

**Why:** v1 spec nested game_context per-player, denormalizing the same NFL game across 5+ player entries. Promoting NFLGame to its own file unlocks Rivalry Cards, slate-at-a-glance views, opponent context popovers — all from one extra fetch step.

**Output:** `data/2025/nfl_games/{game_id}.json` — keyed by nflreadpy's `game_id` (e.g., `"2025_06_BUF_NYJ"`).

```json
{
  "game_id": "2025_06_BUF_NYJ",
  "season": 2025,
  "week": 6,
  "home_team": "BUF",
  "away_team": "NYJ",
  "home_score": 28,
  "away_score": 14,
  "result": 14,
  "kickoff": "2025-10-12T13:00-04:00",
  "stadium": "Highmark Stadium",
  "stadium_id": "BUF",
  "roof": "outdoors",
  "surface": "grass",
  "temp": 52,
  "wind": 12,
  "spread_line": -7.5,
  "total_line": 47,
  "starting_qbs": {"home": "00-0034796", "away": "00-0036442"},
  "rest_days": {"home": 7, "away": 7},
  "div_game": true,
  "team_stats": {"BUF": {"passing_epa": 8.4, "rushing_epa": 3.2, ...}, "NYJ": {...}},
  "key_injuries": [{"team": "NYJ", "gsis_id": "...", "name": "...", "status": "Out", "primary_injury": "ankle"}, ...]
}
```

**File:** `scripts/generate_nfl_games.py` (new). Reads from cached nflreadpy schedules + team_stats + injuries; writes per-game files.
**Player-game linkage:** `top_scorers[].game_context` in `weekN_data.json` references `game_id` instead of nesting weather/opponent. UI consumers fetch the game file once per game; no per-player duplication.
**Companion file (NEW — architect M2):** `weekN_data_expanded.json` — same shape as `weekN_data.json` but with NFLGame data inlined per top_scorer. Build-time generated from `weekN_data.json` + the corresponding `nfl_games/{game_id}.json` files. Chrome authors who prefer denormalized week-views can fetch `_expanded.json` (1 request per week) instead of `_data.json` + per-game fetches (1 + N requests). The denormalization-cost trade-off is now explicit; chrome picks.
**Verification:** All 18 weeks × ~16 games ≈ 272 files exist (actual count varies week-to-week due to bye weeks; total ≈ 272 across the season per architect F4). Opening any one shows valid schema. Each `game_id` is referenced at least once from a top_scorer entry. `weekN_data_expanded.json` for week 6 contains all referenced game_id data inlined.

### Layer 2: GENERATORS

#### 5. Verdict Card generator (MUST) — REVISED post-spike

**Spike correction:** Satori-Python doesn't exist on PyPI. v1 spec said "Satori (or Playwright fallback)" — confirmed empirically that BOTH `satori-html` and `python-satori` return "No matching distribution found." Switching primary to **Playwright** (already installed on this Windows box, sync_api importable).

**Why Playwright over Pillow:** Playwright renders HTML/CSS templates via headless Chromium → PNG. Pillow alone forces pixel-by-pixel construction (drop caps, serif typography, grain texture all become painful). Playwright lets the same HTML/CSS we use for editorial typography drive PNG output. Browser binaries via `playwright install chromium` (~150MB one-time download).

**Optional optimization:** `Resvg` (Python bindings for resvg, Rust-based SVG-to-PNG renderer) — if Verdict Card template can be expressed as SVG, Resvg is faster and lighter than Playwright. Test during implementation.

**File:** `scripts/generate_verdict_cards.py` + `scripts/templates/verdict_card.html` + (optional) `scripts/templates/verdict_card.svg`
**Output:** `content/cards/2025/week{N}/verdict-{roster_id}.png` — 12 cards × 18 weeks = 216 cards full season. **Edge cases:** playoff weeks 15-17 generate cards only for the 4-6 teams playing; eliminated teams get a "season recap" variant or no card. Championship week 18 generates 2 game cards (home/away verdicts) + 1 season recap card per non-finalist team.

**Variants:**

- #1 = "BRAG CARD" (gold accents)
- #12 = "SELF-ROAST CARD" (muted, charcoal)
- ELIMINATED = "season recap" treatment (post-elimination weeks)

**Web Share integration (folds in former Item 12):** Each card surface gets a "Share" button that uses `navigator.share({files: [card], title, text})` on supported platforms; falls back to right-click-save otherwise.

**Verification:** Generate week 6 cards. Manually inspect 3 cards (rank #1, #6, #12). Confirm: typography crisp, accent color matches team, momentum sparkline drawn, no text overflow, share button triggers native share sheet on iOS Safari.

#### 6. SVG Chart library (SHOULD)

Hand-rolled SVG via Python — unchanged from v1. Standalone `.svg` files at `content/charts/{type}/{identifier}.svg`. matplotlib SVG export as fallback for complex plots; hand-templated SVG for sparklines and small multiples.

**File:** `scripts/charts/sparkline.py`, `scripts/charts/elo_small_multiples.py`, `scripts/charts/momentum_trajectory.py`, `scripts/charts/rivalry_strength.py` (NEW for Rivalry Cards integration).
**Verification:** Render one sparkline per team. Open in browser. Confirm: scales correctly, breathes with `prefers-reduced-motion`, accessible via `<title>` and `<desc>` tags.

#### 17. TTS Field Notes (NEW · SHOULD · per elite advisor)

**Why:** Highest league-additive ROI per session per the elite review. ~30-90s weekly recap per team in voice-bible voice. Owner taps the play button on their Verdict Card → hears their week summarized in a sportscaster voice. The "wait, did you HEAR this week's column?" moment.

**Tooling:** Coqui XTTS (local Aegis Ollama stack) or Edge TTS (free Microsoft endpoint). XTTS preferred for voice consistency across weeks (can clone a reference voice; consistent timbre). Edge TTS as fallback if XTTS install issues.
**File:** `scripts/generate_field_notes_audio.py` (new). Reads team-specific recap text (derived from `weekN_content.json` rankings blurb for the team) + voice-bible style guidance, generates `.mp3` AND companion `.json` sidecar.
**Output (paired files):**

- `content/audio/2025/week{N}/field_notes-{roster_id}.mp3` — the audio
- `content/audio/2025/week{N}/field_notes-{roster_id}.json` — sidecar metadata (NEW per architect Mi1): `{transcript, duration_sec, voice_id, source_blurb_hash, generated_at}`. Lets a chrome render transcript-with-audio (JailyardOS) or audio-with-transcript-secondary (Clubhouse) without re-deriving anything.
  12 audio files × 18 weeks = 216 audio + 216 sidecar files (~5-10 MB per .mp3, gitignored if needed for size; sidecars committed).
  **Edge cases:** playoff weeks generate audio only for active teams; eliminated teams get optional "season eulogy" audio variant.
  **Verification:** Generate week 6 audio for 1-2 teams. Listen. Confirm: voice consistent with chosen reference, prose matches the ranking blurb, no awkward TTS artifacts on player names (validate pronunciation dictionary if needed). Sidecar JSON validates against schema and `transcript` field equals input text.

### Layer 3: PATTERNS

#### 4. Editorial Typography pattern library (MUST) — REVISED chrome-flexible

Drop-in CSS module any chrome consumes. **Chrome-flexible token sets** — provides a default magazine palette AND a system-mono alternative; chrome decision picks which to activate.

**File:** `content/editorial.css` + `content/editorial-mono.css` (alternative palette)
**Default palette tokens (Clubhouse-aligned):**

- Newsreader (variable serif) for headlines + body
- Inter for UI
- Drop caps via `::first-letter` + `initial-letter` fallback
- Pull quotes
- Hairline rules via `border-image: linear-gradient`
- Subtle grain texture as data-URI background

**Alternative palette tokens (JailyardOS-aligned):**

- IBM Plex Mono / Geist Mono for headlines + body
- System sans for UI
- ASCII rules instead of hairline borders
- No grain texture (clean monospace surfaces)

**Shared 2026 primitives across both palettes:**

- Cascade layers (`@layer base, components, utilities`)
- `oklch()` color tokens for theme (`--ink`, `--paper`, `--accent`, `--muted`, `--rule`, `--good`, `--bad`)
- `light-dark()` function for theme-mode tokens
- `text-wrap: balance` on `h1, h2, h3`
- `text-wrap: pretty` on `p, blockquote`
- `font-display: swap` for variable fonts
- Container query units (`cqw`, `cqi`)
- `@property` declarations for animatable custom properties
- `@scope` blocks for component-local styling
- `@starting-style` for entry animations on popovers

**Container Queries integration (folds in former Item 11):** Every L3 component sets `container-type: inline-size` on its root and uses `@container (min-width: ...)` instead of `@media`. Not a standalone item; baked into typography + Receipt + any future component.

**Verification:** Apply default to a sample HTML page (`docs/sample-editorial.html`) and alternative to (`docs/sample-mono.html`). Confirm: typography crisp, drop cap renders (default), monospace renders cleanly (alt), theme tokens light + dark via `light-dark()`, container queries reflow at component-local breakpoints.

#### 7. The Receipt (predictions ledger) (SHOULD)

Per-season ledger of every prediction made in weekly columns + outcomes. Lightweight UI component any chrome can drop in. Schema unchanged from v1.

**Output:** `data/2025/receipts.json`
**Component:** `content/components/receipt.js` — vanilla Web Component (`<jy-receipt>`) reading from `receipts.json`.
**Initial scope:** Prospective tracking only (predictions added to `receipts.json` when each new column is generated). Retroactive extraction from weeks 1-6 prose deferred.
**Verification:** Drop `<jy-receipt season="2025"></jy-receipt>` into a sample HTML page. Renders cleanly with sample data.

### Layer 4: 2026 INTERACTION PRIMITIVES

#### 9. Popover API + Anchor Positioning (NEW-2026)

Native zero-JS popovers and tooltips. Schema and pattern unchanged from v1. Falls back to centered popover on Safari iOS where Anchor Positioning still pending.

**Browser-support honesty:** Anchor Positioning was Chrome 125+ in 2025; Safari shipping in 2026; Firefox 137 in late 2025. iOS Safari users (significant share of league members) will hit the centered fallback for several months. Centered fallback is acceptable.

#### 10. View Transitions named regions (NEW-2026)

Pattern unchanged from v1. `view-transition-name` set on Verdict Cards, player arc cards, momentum sparklines.

**Collision guard:** Names must be page-unique (e.g., `card-{game_id}-{roster_id}`). Build-time linter check ensures no duplicates.

### DEMOTED items (folded or deferred)

#### 8. "My Team" localStorage (DEFERRED)

Originally SHOULD. Removed from this workstream's scope — solving a problem nobody has yet. If a future chrome wants personalization, the implementation is trivial (~30 min) and can be added then. Keeping it on the deferred list for visibility.

#### 11. Container Queries as standalone (FOLDED)

Folded into Item 4 (Editorial Typography) and any future L3 component. Container queries are a discipline applied to all components, not a deliverable item.

#### 12. Web Share API as standalone (FOLDED)

Folded into Item 5 (Verdict Card generator) — the share button is part of the card consumer code, not a separate item.

### Layer 5: DISTRIBUTION (NEW)

#### 15. Sunday Drop ritual (NEW · MUST · per elite advisor)

**Why:** Cheapest league-additive feature available. Creates a recurring league moment owners coordinate around. Cards/columns embargo until 9pm Tuesday; release script flips a flag at scheduled time, group chat lights up at 9:01.

**File:** `scripts/release_week.py` (new).
**Mechanism:** Source files live in `content/embargo/week{N}/`; release script `mv`s them to `content/cards/2025/week{N}/` (and triggers Discord webhook per Item 16) at scheduled time. Can be triggered manually or scheduled via Windows Task Scheduler / GitHub Actions cron.
**Verification:** Stage week-7 content in embargo dir. Run release script. Files move atomically; Discord webhook fires; live URL serves the new cards.

#### 16. Discord webhook (NEW · MUST) — REVISED scope per architect Mi2

**Discord webhook:** When Sunday Drop fires, post Verdict Cards to the league's Discord channel via webhook. Cards as image attachments + brief text intro derived from week's headline.
**File:** `scripts/post_to_discord.py` (new). Discord webhook URL stored in `.claude/settings.local.json` (gitignored).
**OG meta tags — DEFERRED:** v2 spec originally bundled OG meta with Discord webhook. Architect Mi2 surfaced that OG meta requires a per-card URL pattern decision the chrome handoff hasn't made yet. Defer OG meta to chrome handoff. Discord webhook ships in this workstream as the file-attachment path; rich-link previews via OG come later.
**Verification:** Post one card via webhook → confirm appears in Discord channel as inline image. WhatsApp share via Web Share API still works (file attachment, not URL preview).

### Phase 1 Voice Coordination

#### 18. Writer prompt updates for new fields (NEW · MUST · Phase 1)

**Why:** Voice workstream is "deferred" but writers will attempt weeks 7-18 BEFORE the voice workstream ships. If `write-week.md` and `local_draft.py` don't know about `opponent_def_epa`, `injury_status`, `weather`, `home_away`, `game_id`, the new data goes unused.

**File:** `.claude/commands/write-week.md` + `scripts/local_draft.py` (extend prompts).
**Scope:** Add references to new fields in the writer's "Enriched Fields in Week Data" section. Add corresponding Tier 1 checks in `.claude/commands/edit-week.md` (already updated in Phase 15.5 for previous fields; extend for new ones).
**Verification:** Run `/write-week 7` (when ready) → confirm output cites new fields naturally. `/edit-week 7` → confirm new Tier 1 checks pass.

## Data flow

```
External APIs              Build-time scripts            Static outputs
──────────────             ──────────────────            ──────────────
Sleeper API ─────┐
                 ├─► fetch_sleeper.py ─► season_combined.json
                 │   (also writes weekly snapshots → fantasy_rosters/week{N}.json)
                 │
nflreadpy ───────┼─► fetch_nflreadpy.py ─► data/external/{ff_playerids,schedules,team_stats,injuries}.{parquet,json}
                 │
                 ├─► generate_nfl_games.py ─► data/2025/nfl_games/{game_id}.json
                 ├─► extract_week_data.py ─► weekN_data.json (top_scorers reference game_id)
                 ├─► generate_player_arcs.py ─► data/2025/player_arcs.json
                 └─► generate_franchise_wings.py ─► data/franchises/{roster_id}.json

L1 outputs ─────► generate_verdict_cards.py (Playwright) ─► content/cards/*.png
              ├─► scripts/charts/*.py ─► content/charts/*.svg
              └─► generate_field_notes_audio.py (XTTS) ─► content/audio/*.mp3

L1+L2 outputs ─► release_week.py (Sunday Drop) ─► moves files from embargo/ → live
                 │
                 └─► post_to_discord.py ─► Discord webhook attachment

CSS/JS modules
──────────────
content/editorial.css           (default magazine palette)
content/editorial-mono.css      (alternative monospace palette)
content/components/receipt.js   (Web Component, container-queried)
```

All Python scripts are idempotent — running them twice produces byte-identical output (modulo Sleeper API freshness or NFL game results).

## Sequencing — 4 phases (revised post-architect)

**Architect finding:** v2 originally bundled 6 items into Phase 1 / 2-3 sessions. Honest re-budget — Item 14 alone (refactoring `extract_week_data.py` + 2 new generators + 272+ outputs) is a session; Item 2 (cross-season player arcs across 4 seasons of transactions) is a session. Splitting Phase 1 into two sub-phases.

### Phase 1a: Data foundation, primary entities (~3 sessions)

- Item 1 (Real Game Context expansion via nflreadpy + `src` field)
- Item 13 (Weekly Fantasy Roster Snapshots — capture-from-now-on first; backfill in 1b)
- Item 14 (NFLGame first-class entity + `weekN_data_expanded.json` companion)

End state: per-game JSON files for 2025 weeks 1-6 exist; weekN_data.json references game_id; companion expanded files generated. Per-phase usability: ad-hoc queries against `data/2025/nfl_games/` yield insights.

### Phase 1b: Cross-season aggregates (~2-3 sessions)

- Item 2 (Player Arcs, cross-season — depends on 1a's NFLGame entity + nflreadpy crosswalk)
- Item 3 (Franchise Wing, roster_id-keyed — depends on 1b's player_arcs for roster_lineage joins)

End state: cross-season dynasty layer exists. `player_arcs.json` (or per-player files if size demands) includes 2022-2025 weekly entries with full ownership history; franchise files include 4-year trophy case + h2h matrix.

### Phase 1c: Documentation + writer-coordination tail (~0.5-1 session) — NEW per architect N1

- Item 18 (Writer prompt updates for new fields)
- Item 19 (CLAUDE.md updates — new file paths + new generators + idempotency convention)

**Honest re-budget:** Architect first-pass flagged Phase 1 overscoping. v3 spec recreated the bug by bundling Items 18+19 into Phase 1a. Splitting Items 18+19 into Phase 1c (documentation tail) keeps Phase 1a focused on data work. End state: writer prompts know the new fields; CLAUDE.md reflects the new structure.

### Phase 2: Generators + Distribution (~2-3 sessions)

- Item 5 (Verdict Card generator via Playwright; Web Share folded in)
- Item 6 (SVG Chart library)
- Item 17 (TTS Field Notes via XTTS, with `.json` sidecar)
- Item 15 (Sunday Drop ritual)
- Item 16 (Discord webhook only — OG meta deferred to chrome handoff per architect M2)

End state: 216 PNG cards (excluding playoff-week non-participants) + ~50 SVG charts + ~216 MP3 audio files + Sunday Drop ritual functional + Discord webhook posting. Per-phase usability: cards shareable via Web Share + posted to Discord at next Sunday Drop. League members start seeing the new artifacts in their Discord channel.

### Phase 3: Patterns + Primitives + Falsifiable Validation (~1-2 sessions)

- Item 4 (Editorial Typography with chrome-flexible token sets)
- Item 7 (The Receipt component)
- Item 9 (Popover + Anchor)
- Item 10 (View Transitions named)
- **League-member validation gate (FALSIFIABLE — revised per architect M5):**
  - Build a one-off prototype URL combining all artifacts.
  - Post URL to league Discord channel + WhatsApp.
  - **Pass** = within 7 days, AT LEAST 4 of 12 league members open the URL (Discord webhook log + URL access log) AND AT LEAST 2 of those 4 unprompted-share at least one Verdict Card to the league chat.
  - **Fail** = below either threshold. Capture as data for chrome handoff (which surface didn't engage? what did members say?).
  - The gate is observable, not vibes-based. "I'd share this" cheap-talk is not accepted as pass criterion.

End state: Full pattern library + interaction primitives ready. Sample integration HTML demonstrates each in isolation. Falsifiable league-member feedback captured for chrome workstream input.

**Total scope:** 8-12 focused sessions across the 4-month runway. No rush.

**Phase 2 pre-check (architect F3):** Day 1 of Phase 2 — install XTTS on Aegis and generate one test audio file. If install fails, switch to Edge TTS immediately and update Item 17 voice-consistency claim from "XTTS clone" to "Edge TTS named voice." Don't discover this 3 sessions into Phase 2.

## Idempotency canonicalization (NEW — architect M6)

**Architect finding:** v1 spec claimed "All Python scripts are idempotent" but Phase 17 (commit `2e75a96`) was a whitespace-refresh proving the existing pipeline already had drift bugs. Adding 5 new generators without addressing root cause re-litigates the bug.

**Canonicalization discipline (mandatory for ALL new generators):**

- All `save_json(...)` calls use `sort_keys=True` and `ensure_ascii=False`
- pandas/polars DataFrame iteration uses explicit sort before serialization (`.sort_values(...)`)
- Pre-commit hook continues running prettier on JSON outputs (existing); generators must produce prettier-compatible whitespace OR run prettier as final step
- `data/external/*` cache files use deterministic timestamps (e.g., embed nflreadpy version + fetch date in filename, not in file body)

**Companion-file idempotency (architect N2):** `weekN_data_expanded.json` joins `weekN_data.json` + N+1 `nfl_games/{game_id}.json` files. Regeneration is content-addressable: pipeline computes a stable hash of all referenced inputs; expanded file is regenerated only if hash differs from a manifest entry at `data/2025/nfl_games/_expanded_manifest.json`. Expanded files are committed (not gitignored) so the CI idempotency check sees them. Pipeline order: NFLGame files → manifest hash → expanded files → downstream consumers.

**Cache invalidation cadence (architect F1):** `fetch_nflreadpy.py` accepts `--max-age-hours N` (default 168 = 7 days during NFL season). Compares file mtime; refreshes if older. Phase 2 wires the GitHub Actions cron (existing `.github/workflows/fetch-sleeper-data.yml`) to run `fetch_nflreadpy.py --max-age-hours 168` weekly during NFL season.

**CI verification (added to Verification section):** "Run full pipeline twice. `git diff data/ content/` returns empty (modulo cached external fetches whose timestamps differ — those are scoped to `data/external/` and excluded from the diff check)."

## Scope expansion acknowledgment (NEW — architect M1)

**Architect finding:** v2 grew 12 → 15 items + new Layer 5. Items 13-18 are author-promoted post-brainstorm. Brainstorm-ratification only covers v1's 12 items.

**Honest acknowledgment:**

- **Item 13 (Roster Snapshots):** Elite advisor's MUST recommendation. Blake greenlit the synthesis containing it.
- **Item 14 (NFLGame entity):** Elite advisor's top leverage point. Blake greenlit the synthesis containing it.
- **Item 15 (Sunday Drop):** Elite advisor recommendation, Blake greenlit.
- **Item 16 (Discord webhook):** Elite advisor recommendation, Blake greenlit (OG meta now deferred per architect).
- **Item 17 (TTS Field Notes):** Elite advisor recommendation, Blake greenlit.
- **Item 18 (Writer prompt updates):** Architect-relevant Phase 1 task; surfaces in v2 as a result of Phase 1 voice-coordination concern.
- **Item 19 (CLAUDE.md update):** Architect-suggested addition.

These are Blake-sanctioned via the elite-advisor synthesis approval ("ok thanks for double checking. if you're confident to move forward, let's do it"), not opaque scope-creep. Documenting here for traceability. If any individual item should be cut, we cut at this gate, not at architect or implementation.

## Chrome-agnosticism guarantee

Every item passes this test: **"If a chrome we haven't picked yet wants to use this primitive, can it consume the output without modification?"**

- Items 1, 2, 3, 13, 14: pure JSON. Trivially consumable.
- Item 5: PNG file path + share button helper. Trivially consumable.
- Item 6: SVG file path. Trivially consumable.
- Item 17: MP3 file path. Trivially consumable.
- Items 15, 16: distribution scripts; chrome-independent.
- Item 18: writer prompt; producer-side, not chrome-side.
- Item 4: CSS module with TWO palettes; chrome picks which.
- Item 7: Web Component drop-in tag.
- Items 9, 10: native browser APIs; standard patterns.

If any item fails this test during Phase 2-3 implementation, surface and re-scope.

## Risks

| Risk                                                   | Severity | Mitigation                                                                                                                                                                                                              |
| ------------------------------------------------------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| nflreadpy data freshness during NFL season             | M        | Cache Parquet files to `data/external/`; refresh weekly during season; document the refresh cadence in CLAUDE.md.                                                                                                       |
| Playwright Chromium binary install on Windows          | L        | `playwright install chromium` is well-documented; ~150MB one-time.                                                                                                                                                      |
| XTTS install pain on Aegis                             | M        | Test early. If XTTS fails, fall back to Edge TTS (Microsoft, free, requires no install — HTTP API).                                                                                                                     |
| Discord webhook secret leakage                         | L        | Webhook URL in `.claude/settings.local.json` (already gitignored).                                                                                                                                                      |
| Cross-season Player Arcs file size                     | M        | Deterministic threshold (architect F2): if `player_arcs.json` exceeds **3MB** at end of Phase 1b generation, split immediately into per-player files at `data/2025/player_arcs/{player_id}.json`. No operator judgment. |
| Build-time growth from added generators                | M        | Profile during Phase 2. Parallelize generators if exceeding 5min total. Cache aggressively.                                                                                                                             |
| Data drift between L1 generators and consumers         | L        | Pydantic-style schema validation extended to new data files. `verify_week_content.py` covers all new schemas.                                                                                                           |
| 2026 CSS primitives Safari-iOS lag                     | L        | Each pattern has a documented fallback (Anchor Positioning → centered popover; `text-wrap: pretty` → `text-wrap: balance`).                                                                                             |
| Voice integration timing (Item 18 vs voice workstream) | L        | Item 18 is in Phase 1 specifically to prevent the gap. Voice workstream can refine prompts later.                                                                                                                       |
| Roster snapshots can't backfill historical weeks       | M        | Item 13 acknowledges this; flag derived snapshots as `derived: true`; null starters/reserve for derived. Future weeks captured fresh.                                                                                   |
| nflreadpy SPOF (architect M3)                          | M        | Single library, single maintainer, 3-link upstream chain. Item 1 `src` field allows graceful degradation. Cache last-good Parquet.                                                                                      |
| Idempotency drift (architect M6)                       | M        | Phase 17 already had whitespace bug. Mandate `sort_keys=True, ensure_ascii=False` + explicit DataFrame sorts. CI runs pipeline 2x.                                                                                      |
| Item 14 query fan-out (architect M2)                   | L        | Companion `weekN_data_expanded.json` provides denormalized view for chrome authors who prefer one fetch per week.                                                                                                       |
| Player retired mid-season (architect Mi3)              | L        | Item 2 status enum includes `"retired"` with `retired_date`. Source: nflreadpy.load_players + roster-presence delta.                                                                                                    |
| Sleeper API breaking change (architect Mi3)            | M        | Cache last-good fetch; pipeline degrades to cached data with `stale: true` flag. Don't crash.                                                                                                                           |
| 2026 league restructure (architect Mi3)                | L        | `roster_id` keying mitigates partially; if team count changes, `data/franchises/_index.json` rebuilt.                                                                                                                   |

### 19. CLAUDE.md update (NEW · MUST · architect-suggested)

**Why:** Project CLAUDE.md declares file paths and pipeline conventions (e.g., the "label drift risk" note from Phase 17). Adding 5 new generators + 7 new directories without updating CLAUDE.md leaves future sessions blind to the new structure.

**File:** `CLAUDE.md` (project root).
**Updates required:**

- New file paths in the "Data" section: `data/2025/nfl_games/`, `data/2025/fantasy_rosters/`, `data/2025/player_arcs.json`, `data/franchises/`, `content/cards/`, `content/charts/`, `content/audio/`, `content/embargo/`, `data/external/`
- New scripts in "Key Scripts" section: `fetch_nflreadpy.py`, `generate_nfl_games.py`, `generate_player_arcs.py`, `generate_franchise_wings.py`, `generate_verdict_cards.py`, `generate_field_notes_audio.py`, `release_week.py`, `post_to_discord.py`
- Idempotency convention note (architect M6): "All new generators must use `save_json(..., sort_keys=True, ensure_ascii=False)` and explicit DataFrame sort before serialization."
- Reference to this spec as the canonical source.

**Verification:** Grep `CLAUDE.md` for each new file path → all return ≥ 1 match.

## Verification (end-to-end)

1. **Data layer test:** All 18 `weekN_data.json` files validate against extended schema. `data/2025/player_arcs.json` exists with at least 200 player entries spanning 2022-2025. `data/franchises/*.json` has 12 files keyed by roster_id. `data/2025/nfl_games/*.json` has 272+ files (18 weeks × ~16 games). `data/2025/fantasy_rosters/week{N}.json` captured for current week.

2. **Generator test:** `scripts/generate_verdict_cards.py` produces 216 PNGs (excluding playoff-week non-participants) that visually render correctly (manual spot-check of 6 cards across 3 weeks). `scripts/charts/sparkline.py` produces sparklines per team. `scripts/generate_field_notes_audio.py` produces audio for 1-2 teams as POC.

3. **Distribution test:** `scripts/release_week.py` moves files from embargo correctly. `scripts/post_to_discord.py` fires webhook (test channel) and Card appears as inline image in Discord. WhatsApp share via Web Share API works as file-attachment (OG meta deferred per architect Mi2; rich-link previews wait for chrome handoff).

4. **Pattern test:** `docs/sample-editorial.html` (default palette) and `docs/sample-mono.html` (alternative palette) demonstrate CSS patterns rendering correctly across Chrome / Safari / Firefox. `<jy-receipt>` Web Component renders cleanly. Container queries reflow at component-local breakpoints.

5. **Primitive test:** Click a popover trigger — popover opens anchored (or centered fallback on iOS Safari). View Transitions morph correctly between two surfaces with matching `view-transition-name`. Web Share API works on iOS Safari + Chrome Android.

6. **Chrome-agnosticism stress test:** Build a single `docs/sample-chrome.html` page that uses all items in a flat layout — no JailyardOS / Clubhouse / Playfield framing. Each item renders correctly without chrome opinions.

7. **Tests pass:** `python -m pytest scripts/tests/` — current 48 + new tests for L1/L2 generators (target: 65+ passing).

8. **Machine-checkable assertions per MUST item (NEW — architect M4):**
   - Item 1: `python -c "import json; d=json.load(open('content/weeks/week6_data.json')); assert all('src' in s.get('game_context', {}) for s in d['top_scorers'] if s.get('game_context'))"` returns 0
   - Item 2: JSON schema at `scripts/schemas/player_arc.schema.json` validates against all entries in `player_arcs.json`
   - Item 3: `python -c "import json,os; assert all(os.path.exists(f'data/franchises/{r}.json') for r in range(1,13))"` returns 0
   - Item 13: `python -c "import json; d=json.load(open('data/2025/fantasy_rosters/week1.json')); assert d[0].get('derived') is True"` (for derived weeks); `derived is False` for captured weeks
   - Item 14: `find data/2025/nfl_games -name '*.json' | wc -l` returns ≥ 272 for full season; `weekN_data_expanded.json` exists for week 6
   - Item 18: `grep -E 'opponent_def_epa|injury_status|home_away|game_id' .claude/commands/write-week.md` returns ≥ 4 matches; same grep on `scripts/local_draft.py` returns ≥ 4 matches
   - Item 19: `grep -E 'fetch_nflreadpy|generate_nfl_games|generate_player_arcs' CLAUDE.md` returns ≥ 3 matches

9. **Idempotency CI check (NEW — architect M6):** Run full pipeline twice. `git diff data/ content/` returns empty (modulo cached external fetches whose timestamps differ). Add to `.github/workflows/` as a CI job.

10. **League-member validation (Phase 3 gate, FALSIFIABLE — architect M5):**
    - Post prototype URL to league Discord + WhatsApp.
    - **Pass within 7 days:** ≥4 of 12 members open the URL (Discord webhook log + URL access log) AND (≥2 of those 4 unprompted-share at least one Verdict Card to the league chat OR ≥3 unprompted text mentions of a Card or its data in chat). Broader share signal per architect N3 — engagement-without-image-share still counts if the data shows up in conversation.
    - **Fail with high opens (≥6 of 12) but no share/mention signal:** trigger re-evaluation rather than chrome-handoff signal-recording. The data was reached but didn't activate — that's a different problem than "nobody cared."
    - **Fail with low opens:** capture as data for chrome handoff (which surface didn't engage? what did members say?).
    - The gate is observable, not vibes. Cheap-talk ("I'd share this") rejected.

## Glossary / Reference

- **Chrome** — the visual / interaction shell that frames content. Clubhouse / Yard / Playfield / JailyardOS / TBD-v9-v11 are all candidate chromes.
- **Chrome-agnostic** — works in any chrome without modification.
- **Verdict Card** — 1200×630 PNG per team per week; share-friendly. From Clubhouse concept.
- **Franchise Wing** — per-team biography page concept. From Clubhouse concept.
- **Receipt** — predictions ledger across the season. From Clubhouse concept.
- **Sunday Drop** — Tuesday 9pm synced reveal moment. From Yard concept (used here without the surveillance framing).
- **NFLGame entity** — first-class data file per NFL game. NEW in v2 spec.
- **Field Notes audio** — TTS-generated weekly recap per team. NEW in v2 spec.
- **L1-L5** — the five-layer fabric in this spec (Data → Generators → Patterns → Primitives → Distribution).
- **nflreadpy** — Python port of nflfastR; MIT-licensed; 12,435-row sleeper_id↔gsis_id crosswalk; replaces ESPN scoreboard + injury feed + OpenWeatherMap.
- **Playwright** — headless Chromium for HTML/CSS → PNG (Verdict Cards). Replaces Satori (which doesn't exist for Python).
- **Coqui XTTS** — local TTS for Field Notes audio. Edge TTS fallback if install issues.
- **2026 native primitives** — Popover API, Anchor Positioning, View Transitions, Container Queries, Web Share, `text-wrap`, `:has()`, `oklch()`, `light-dark()`, `@scope`, `@starting-style`, cascade layers.

## Next step

After architect agent reviews this revised spec and verdict is APPROVED (or APPROVED WITH NITS that get fixed), transition to `superpowers:writing-plans` to produce the concrete implementation plan with file edits, sequencing, verification commands, and commit boundaries. That implementation plan goes into a fresh plan-mode session for execution approval, then `superpowers:executing-plans` consumes it phase-by-phase.
