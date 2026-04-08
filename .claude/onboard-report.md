# Project Health Card: Jailyard Dynasty Power Rankings
*Generated: 2026-04-07*

## Structure
Static fantasy football dynasty league site (12 teams, est. 2022). Zero dependencies — pure inline HTML/CSS/JS with Python data pipeline (17 scripts). Data from Sleeper API (cached JSON + live fallback). Glassmorphic dark theme with light toggle. Content pipeline: AI-generated Bill Simmons-style weekly columns from Sleeper data + WhatsApp chat context. 13 HTML pages, 17 Python scripts, 1 shared JS config.

## Security & Quality
- **Critical issues:** 0 — No secrets in code, no external scripts, no XSS from user input
- **Warnings:** 2 — innerHTML used with API data (trusted but unescaped), empty catch blocks in 2 pages
- **Dependency vulnerabilities:** 0 (zero external dependencies)
- **Top concern:** Empty `catch(e){}` blocks in power-rankings.html and season.html swallow errors silently

## Tech Debt
- **High priority items:** 3
- **Top items:**
  1. `power-rankings.html:219-226` — Hardcodes SEASON and league IDs instead of reading from config.js (config drift risk)
  2. `scripts/*.py` (3-4 files) — Duplicate `load_json()`, `save_json()`, `parse_ts()` definitions that should import from `shared.py` (commit 08bd250 started this refactor but didn't finish)
  3. All HTML pages — Footer hardcoded instead of using `config.js:buildFooterNav()` (60+ lines of duplication across 8+ files)
  4. `config.js:508-572` — 4 dead utility functions (`processMediaTokens`, `spreadToProb`, `parseMovement`, `gradientFor`) never called by any page
  5. Error handling inconsistent — season.html has recovery hints, power-rankings.html shows bare error, history.html has no-data state. Should standardize.

## Blind Spots
1. **No automated tests.** Zero pytest, zero Jest, zero test files. `verify_week_content.py` acts as a content validator (1300 lines, 36 checks) but there's no test harness for the data pipeline itself. If Sleeper changes their API response schema, the pipeline silently produces garbage.
2. **config.js is a single point of failure with no null guard.** Every page calls `applyConfig()` unconditionally. If config.js fails to load (404, syntax error), all 13 pages break — nav gone, footer gone, no error message.
3. **Accessibility gaps.** No alt text, no keyboard navigation for selectors/buttons, muted-text-on-dark-background likely fails WCAG AA contrast. 20%+ of users may struggle.

## Architecture Assessment
| Area | Grade | Notes |
|------|-------|-------|
| Data pipeline | **B+** | Sleeper API → cached JSON → live fallback is well-designed. Schema validation missing. |
| Content pipeline | **A-** | Voice bible, editor quality gate, content validator are strong. Franchise history was a blind spot (now fixed). |
| Frontend code | **B-** | Inline everything works for zero-deps but creates duplication. CSS variables consistent. JS patterns vary by page. |
| Documentation | **A** | CLAUDE.md, voice-bible, README all excellent. Minor staleness in AGENTS.md model names. |
| Security | **A** | Zero deps, no secrets, no external scripts, no user input vectors. innerHTML with trusted data only. |
| Maintainability | **C+** | Silo'd development shows. Each page was built independently — inconsistent error handling, hardcoded values that should be centralized, duplicate code across scripts. |
| Testing | **D** | verify_week_content.py is strong for content, but no pipeline tests, no rendering tests, no regression suite. |

## What's Working Well
- Zero-dependency architecture is a genuine strength (no supply chain risk, no build step)
- Content pipeline (write → edit → verify → render → push) is well-designed with clear quality gates
- Config.js centralizes branding, nav, and league data (when pages actually use it)
- Voice bible + editor checklist is professional-grade content QA
- Data loading fallback pattern (cache → API → error) is consistent on 3/4 data pages
- GitHub Actions auto-fetch on NFL Sundays is smart automation
- CLAUDE.md is among the best project docs I've seen — comprehensive and actionable

## Recommendations

### Block Week 7 (fix before writing more content)
1. **Re-run `/edit-week` on weeks 1-6** — Fact-check written content against corrected data (franchise history changed)

### Fix Soon (next session)
2. **Centralize power-rankings.html** — Replace hardcoded SEASON/league IDs with config.js imports (~15 min)
3. **Finish shared.py refactor** — Remove duplicate functions from 3-4 scripts (~1 hour)
4. **Remove dead config.js functions** — Delete 4 unused utilities (~10 min)
5. **Standardize error handling** — Add try-catch to offline JSON loads, show recovery hints on all data pages (~30 min)

### Backlog
6. Add null guard for config.js loading (defensive, low probability)
7. Footer centralization (buildFooterNav exists but no page uses it)
8. Accessibility pass (contrast ratios, keyboard nav, alt text)
9. Basic pipeline tests (validate Sleeper API contract, data schema)
10. AGENTS.md model name cleanup

## CLAUDE.md Status
- **EXISTS** — Comprehensive and accurate (160 lines)
- **Gap:** Doesn't mention power-rankings.html's hardcoded values as a known issue
- **Gap:** AGENTS.md lists stale model names (qwen3 vs qwen3.5-abliterated) and outdated picks ledger status
