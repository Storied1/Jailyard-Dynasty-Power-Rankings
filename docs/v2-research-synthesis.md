# Jailyard Dynasty v2 — Research Synthesis

> Produced 2026-04-09 by 6 parallel research agents + Synthesis Director.
> This document captures the unified findings from competitive intelligence, NFL data sources,
> content/media innovation, tech stack evaluation, Sleeper ecosystem, and product/market research.

## Unified Findings

**The market thesis is validated.** League-specific editorial narrative content has zero quality competition. Competitors (League Legacy $36/yr, League Rewind $5, SmackScript, FantasySmack) produce tools or templates, not columns. Commissioner burnout by Week 6 is a documented pain point.

**Dynasty is the right market.** Year-round engagement, deeper emotional investment, longer histories. Market: 400K-650K dynasty leagues, 1-3% conversion = 4,000-20,000 paying leagues, $200K-$700K ARR at $50/season.

**The voice bible is genuine IP.** 12 codified DNA patterns with anti-patterns and exemplars. No competitor has attempted this. The moat is voice, not tech.

**game_context is solved.** nfl_data_py/nflverse (MIT-licensed) + Sleeper's undocumented `stats/nfl/{season}/{week}` endpoint both provide real NFL stats. Player ID mapping via gsis_id is already solved.

**GIFs are dead.** GIPHY: $9K/yr commercial. Tenor: shutting down June 2026. KLIPY is the free replacement, but the better move is to shift to editorial design (typography, data viz, illustrations).

**11ty is the SSG.** Zero JS output, Nunjucks (Jinja2-like), data cascade eats JSON files. Migration: 2-3 sessions.

**Sleeper has untapped endpoints.** Undocumented `stats/nfl/{season}/{week}`, `traded_picks`, `previous_league_id` chain. But NO write API, NO webhooks, NO bot posting.

**Distribution is the unsolved problem.** No Sleeper bot. Discord webhook is best channel. Email digest is simplest. Sleeper Minis (iframe extensions) are a potential novel channel.

## "We Didn't Know This" List

1. **Sleeper has undocumented NFL stats endpoints** — real game stats without needing a third-party API
2. **nfl_data_py was archived Sept 2025** — successor is nflreadpy
3. **GIPHY charges $9K/yr commercial; Tenor shutting down June 2026**
4. **Sleeper Minis** — iframe extensions inside the Sleeper mobile app (potential distribution)
5. **CSS scroll-driven animations are now native** — zero JS, GPU-accelerated
6. **Progressive/adaptive content formats are a genuine differentiator** — nobody does this
7. **"Your Team" personalization is trivially implementable** — one localStorage question transforms the experience
8. **Observable Plot (30KB, SVG)** — right charting upgrade over Canvas 2D for new charts
9. **config.js is 80% white-labelable already** — licensing path is shorter than expected
10. **Sleeper only shows current roster state** — must snapshot weekly or lose historical data

## Ranked Opportunities

### Tier 1: Do First (high impact, high feasibility)
1. Add `game_context` via Sleeper stats endpoint (~1 session)
2. Editorial typography overhaul: serif headlines, drop caps, pull quotes (~1-2 sessions)
3. Migrate to 11ty: extract duplicated CSS, set up data cascade (~2-3 sessions)
4. "My Team" localStorage personalization (trivial implementation)

### Tier 2: Do Next (high impact, moderate feasibility)
5. Progressive content format (4-5 season phases with distinct structures)
6. Narrative arc navigation (arcs.json already exists)
7. Weekly roster snapshots in pipeline
8. Elo small multiples (replace spaghetti chart)

### Tier 3: Build Toward (requires decisions first)
9. Licensing Phase 1 (GitHub template repo)
10. Sleeper Mini exploration
11. Discord webhook distribution

## Resolved Questions

| Topic | Answer |
|-------|--------|
| NFL game context source | Sleeper undocumented stats + nflreadpy as backup. No paid API. |
| What's beyond GIPHY? | Kill GIFs. Editorial typography, data viz, CSS animations. |
| Tech stack | 11ty. Not Astro, not Next.js, not Tailwind. |
| Sleeper features on the table? | Stats endpoint, traded_picks, previous_league_id. No write API. |
| Premium site vs licensable? | Both, sequentially. Premium first, licensing is a natural byproduct. |

## Open Questions (Need Brainstorming)

1. Voice evolution — own identity or lean harder into Simmons?
2. Content quality at scale — cold start problem for new leagues
3. Distribution strategy — Discord vs email vs Sleeper Mini
4. Owner bias handling — should Ken-obi get roasted harder?
5. Preseason ranking sources — which dynasty sites? API access?
6. Reader device profile — mobile or desktop?
7. Picks section role — marquee feature or filler?

## Recommended Brainstorm Agenda

### Session 1: Design Identity + Editorial Voice (creative decisions)
- Define "not AI slop" — review reference sites, pick a direction
- Progressive content format — define season phases and structure shifts
- Owner bias policy
- Voice evolution — Simmons foundation + Jailyard's own identity

### Session 2: Product Scope + Licensing Vision (strategic decisions)
- "My Team" personalization scope
- Distribution channel selection
- Narrative arc navigation design
- Licensing timeline and tiers
- Cold start problem for new leagues

### Engineering Tasks (just build, no brainstorm needed)
- game_context pipeline (Sleeper stats endpoint)
- 11ty migration
- Typography overhaul (after Session 1 design direction)
- Weekly roster snapshots
- Elo small multiples
- nflreadpy integration as backup
- Traded picks enrichment
