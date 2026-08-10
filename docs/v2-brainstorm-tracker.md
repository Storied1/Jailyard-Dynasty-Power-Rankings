# Jailyard Dynasty v2 — Brainstorm Tracker

> Living document. Tracks every topic that needs creative/strategic exploration before implementation.
> Updated as research completes and decisions are made.

## Sequencing Decision (LOCKED)

**Decision:** Content Depth + Voice → Redesign → Write All 18 Weeks
**Recorded:** 2026-04-08 in Obsidian vault (`40-Decisions/2026-04-08-jailyard-v2-sequencing.md`)
**Key constraint:** No rush. Football season starts Aug/Sep 2026. Build for quality and licensing potential.

---

## Research Swarm Status

| #   | Agent                      | Status | Key Findings                                                                                                                                        |
| --- | -------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Competitive Intelligence   | DONE   | Market gap real. Competitors exist but none produce editorial columns. Commissioner burnout = pain point. $200K-$700K ARR ceiling.                  |
| 2   | NFL Data & Game Context    | DONE   | nflreadpy (MIT) + Sleeper undocumented stats endpoint. Player ID mapping solved. Engineering task, not research.                                    |
| 3   | Content & Media Innovation | DONE   | Kill GIFs. Serif typography = #1 premium signal. Jon Bois "boss chart" concept. CSS scroll-driven animations. Progressive formats = differentiator. |
| 4   | Tech Stack & Platform      | DONE   | 11ty wins. 2-3 session migration. config.js 80% licensable. Observable Plot for new charts.                                                         |
| 5   | Sleeper Ecosystem          | DONE   | Undocumented stats endpoint (real NFL data!). No write API/webhooks. traded_picks + previous_league_id untapped. Sleeper Minis possible.            |
| 6   | User & Product             | DONE   | The editorial voice is genuine IP. $200K-$700K ARR. Biggest risks: quality at scale, distribution, Sleeper building natively.                       |
| S   | Synthesis Director         | DONE   | See `docs/v2-research-synthesis.md`. 5 resolved questions, 7 open questions, ranked opportunities.                                                  |

---

## Brainstorm Topics

### 1. Product Vision & Licensing

- **Status:** NOT STARTED
- **Core question:** Is this a premium fan site for one league, or a licensable platform for any fantasy league?
- **Research needed:** Competitive landscape, existing products, market size
- **Findings:** —
- **Decision:** —

### 2. Design Identity

- **Status:** NOT STARTED
- **Core question:** What does "not AI slop" look like? Editorial magazine? Sports media? Something new?
- **Research needed:** Competitive design references, editorial design patterns, premium sports content sites
- **Findings:** —
- **Decision:** —

### 3. Content Format (Progressive/Adaptive)

- **Status:** NOT STARTED
- **Core question:** Should the weekly format evolve with the season instead of being the same every week?
- **Ideas surfaced:** Week 1 = introductions, mid-season = analytical, rivalry weeks = spotlight, playoffs = intense
- **Research needed:** What formats do the best sports content sites use? Interactive? Personalized?
- **Findings:** —
- **Decision:** —

### 4. Real-World NFL Context (game_context)

- **Status:** NOT STARTED
- **Core question:** What data source provides real-game narratives to bridge fantasy scores to NFL moments?
- **Research needed:** Available APIs (nfl-data-py, ESPN, PFF, Sportradar), free vs paid, programmatic access
- **Findings:** —
- **Decision:** —

### 5. Voice Evolution

- **Status:** NOT STARTED
- **Core question:** How does the voice keep sharpening its own identity?
- **Current state:** editorial standard has 12 strong DNA patterns, 18 anti-patterns. Foundation is excellent.
- **Known gaps:** Owner bias, explicit naming, tone-per-section, pattern weighting, arcs.json integration
- **Research needed:** What makes AI-generated sports writing not feel like AI? Adaptive voice?
- **Findings:** —
- **Decision:** —

### 6. Media Experience

- **Status:** NOT STARTED
- **Core question:** What's beyond GIPHY? What media makes a sports content site feel premium?
- **Research needed:** What do The Ringer, Secret Base, SB Nation use? Interactive embeds? Custom video? AI visuals?
- **Findings:** —
- **Decision:** —

### 7. Tech Stack & Build System

- **Status:** NOT STARTED
- **Core question:** What stack serves a licensable editorial content platform?
- **Current state:** Zero-dependency inline HTML/CSS/JS. 158 KB CSS, 87x duplication. No templating.
- **Research needed:** Astro, 11ty, Next.js SSG, design systems, multi-tenant architecture
- **Findings:** —
- **Decision:** —

### 8. Sleeper Ecosystem

- **Status:** NOT STARTED
- **Core question:** Are we leaving Sleeper API features on the table?
- **Research needed:** Full API surface, webhooks, game-day data, community features, developer ecosystem
- **Findings:** —
- **Decision:** —

### 9. Preseason Ranking Methodology

- **Status:** NOT STARTED (blocked on research)
- **Core question:** How should preseason rankings be built from real dynasty sources?
- **Known:** Current data is AI-fabricated. "Five sources" were never named. Full rebuild needed.
- **Research needed:** Which dynasty ranking sources are best (KTC, FantasyCalc, DynastyProcess)? API access?
- **Findings:** —
- **Decision:** —

### 10. User Experience & Personalization

- **Status:** NOT STARTED
- **Core question:** What makes league members come back every week? "My Team" feature? Narrative arcs as navigation?
- **Ideas surfaced:** "My Team" localStorage, narrative arc navigation, Elo sparklines, "Jailyard Rewind" play-by-play
- **Research needed:** What do fantasy league consumers actually engage with?
- **Findings:** —
- **Decision:** —

---

## Completed Investigations

| Investigation                 | Date       | Outcome                                                                                                  |
| ----------------------------- | ---------- | -------------------------------------------------------------------------------------------------------- |
| Preseason data provenance     | 2026-04-08 | AI-fabricated. Full rebuild needed.                                                                      |
| Weeks 1-6 preseason callbacks | 2026-04-08 | 11-14 callbacks per week. Full rewrites needed, not patches.                                             |
| Python scripts quality audit  | 2026-04-08 | Architecture sound (B+ avg). shared.py centralization working. Zero tests.                               |
| Slash commands audit          | 2026-04-08 | Strong foundation (esp. write-week, edit-week). Needs modernization for teams/tasks.                     |
| editorial standard audit      | 2026-04-08 | Excellent core. Gaps: owner bias, naming, tone calibration, arcs.json integration.                       |
| Frontend architecture audit   | 2026-04-08 | 87x CSS duplication. No templating. Zero-dep constraint is fine for output, build process needs tooling. |
| CLAUDE.md cleanup             | 2026-04-08 | 5 fixes applied and committed (ca78d33).                                                                 |

---

## Key Principles (from Blake)

- **No rushing.** 4-5 months of runway. Do it right.
- **Nothing is set in stone.** Weekly format can be progressive, adaptive, living.
- **Build for the vision, not the current audience.** Could be licensed to other leagues.
- **Question everything.** The whole site was a rough draft. Now we're coming through for real.
- **Quality gates are binary.** Fix first, approve second.
