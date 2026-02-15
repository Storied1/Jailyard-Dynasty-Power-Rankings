# JAILYARD DYNASTY POWER RANKINGS — PRE-PUBLISH AUDIT

**Date:** 2026-02-15
**Auditor:** Automated (Claude)
**Scope:** Full site audit across 8 HTML pages, config.js, fetch_sleeper.py, GitHub Actions

---

## 1. Executive Summary

### CONDITIONAL GO

The site is in strong shape for publishing. Content accuracy is solid, all internal links resolve, and the security posture is clean. Three areas need attention before going fully public:

1. **Accessibility gaps** — No `aria-expanded` on any hamburger menu; most canvas data charts lack text alternatives; no skip-to-content links
2. **Missing `overflow-x: hidden`** on `preseason.html` and `week1.html` — risk of horizontal scroll on mobile
3. **History page has no theme toggle button** — users have no way to switch themes on that page

None of these are blockers, but items 1 and 2 should be addressed before sharing widely.

---

## 2. Content Accuracy

### Team Names — CONSISTENT
All 12 teams are present and consistently named across every page:

| # | Team | Pages Found |
|---|------|-------------|
| 1 | General Ken‑obi | preseason, index, draft, trades, week1 |
| 2 | Noble FFT | preseason, draft, trades, week1 |
| 3 | MHJTIME | preseason, index, week1 |
| 4 | Ghastly Grayskull Gang | preseason |
| 5 | Rasheeing the Scene | preseason, draft, trades, week1 |
| 6 | Kittler on the Roof | preseason, index, draft, trades, week1, season |
| 7 | Chudders Football Team | preseason |
| 8 | Burden of Etienne‑y Woody | preseason |
| 9 | The Legion of Bouz | preseason, index, draft, trades, week1 |
| 10 | Father Time | preseason, trades, week1 |
| 11 | Sleeping Giants | preseason, index |
| 12 | The Boonist Monks | preseason, draft, trades, week1 |

**Team count:** 12 in `preseason.html` league.teams[], 12 in `config.js` (teamCount: 12). Consistent.

### Championship Data — ACCURATE
- **2022:** Legion of Bouz (confirmed in `index.html:825`, `preseason.html:310`)
- **2023:** General Ken‑obi (confirmed in `index.html:827`, `preseason.html:309`)
- **2024:** Kittler on the Roof (confirmed in `index.html:829`, `preseason.html:308`)

### Season References — CURRENT
- `config.js:33` → `currentSeason: 2025` ✅
- `fetch_sleeper.py:34` → `SEASON = 2025` (internal constant) ✅
- Index hero text references "2025 championship" ✅

### Fun Facts Ticker — ACCURATE
- `index.html:767-784`: 12 facts, all verifiable. "4 seasons and counting since 2022" ✅, "3 different champions" ✅, "60 picks in 2025 rookie draft" ✅, "MHJTIME went from last place in 2023 to top 3 in 2025" matches preseason data ✅
- `config.js:62-75`: Separate fun facts list (12 entries), consistent with index.html facts ✅

### fetch_sleeper.py LEAGUE_IDS — CORRECT
```python
2022: "792314138780090368"
2023: "918335334096846848"
2024: "1048889097223266304"
2025: "1180228858937966592"
2026: "1312884727480352768"   # offseason
```
Matches `config.js:24-30` exactly ✅

### Issues Found
- **None** — all content is accurate and consistent.

---

## 3. Link Integrity

### Internal Links — ALL VALID
Every `href="*.html"` across all 8 pages resolves to an existing file:

| Target | Referenced By |
|--------|---------------|
| `index.html` | All 8 pages (nav/footer) |
| `history.html` | All 8 pages |
| `season.html` | All 8 pages |
| `preseason.html` | All 8 pages |
| `power-rankings.html` | All 8 pages |
| `draft.html` | All 8 pages |
| `trades.html` | All 8 pages |
| `week1.html` | All 8 pages |

### External Links — VALID
- Sleeper API (`https://api.sleeper.app/v1`) — standard public API, no auth required ✅

### Anchor Links
- No broken `#section` anchors detected.

### Navigation Consistency
- **Minor inconsistency:** `power-rankings.html` nav is missing links to `draft.html` and `trades.html` in the main nav (only has League Bible, Season Hub, Preseason, Power Rankings, Week 1). Footer nav is also slimmer. Not a broken link but a navigation gap.

### Issues Found
- **LOW:** `power-rankings.html` main nav omits Draft and Trades links (lines 211-215)

---

## 4. Visual Consistency

### CSS Variable Comparison

| Variable | index | preseason | season | history | draft | trades | week1 | power-rankings |
|----------|:-----:|:---------:|:------:|:-------:|:-----:|:------:|:-----:|:--------------:|
| `--bg` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--fg` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--muted` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--accent` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--accent2` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--card` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--border` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--glass` | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| `--good` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--bad` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `--warn` | ❌ | ❌* | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |

*preseason.html uses `--warning` instead of `--warn` (line 23). This is a naming drift.

### `--accent-2` Usage — CLEAN
No active HTML files use `--accent-2`. Only the archived `dontuse`, `dontuse2`, `dontusedraft3` files contain it. ✅

### Unique/Non-Standard Variables
| Page | Unique Variables | Notes |
|------|-----------------|-------|
| `index.html` | `--glow-1`, `--glow-2` | Used for hero glow effects |
| `draft.html` | `--glow-1`, `--glow-2` | Same pattern as index |
| `trades.html` | `--glow-1`, `--glow-2` | Same pattern as index |
| `preseason.html` | `--warning`, `--h1`, `--h2`, `--maxw`, `--font-main` | `--warning` deviates from `--warn` |
| `week1.html` | `--h1`, `--h2`, `--h3`, `--font-main` | Typography scale variables |
| `season.html` | `--font`, `--maxw` | Layout variables |
| `power-rankings.html` | `--font`, `--maxw` | Layout variables |
| `history.html` | `--maxw` | Layout variable |

### Theme Toggle
| Page | Has Toggle Button | Method |
|------|:-----------------:|--------|
| `index.html` | Keyboard only (T) | `classList.toggle('light')` |
| `preseason.html` | ✅ | `#toggleDark` button |
| `season.html` | ✅ | Inline onclick |
| `history.html` | ❌ | **Missing** — no button, no keyboard shortcut |
| `draft.html` | ✅ | `#toggleTheme` button |
| `trades.html` | ✅ | `#toggleTheme` button |
| `week1.html` | ✅ | `#toggleTheme` button |
| `power-rankings.html` | ✅ | `#themeToggle` button |

### Issues Found
- **MEDIUM:** `preseason.html` uses `--warning` instead of `--warn` (line 23) — naming drift
- **LOW:** `history.html` has no theme toggle button
- **LOW:** `index.html` theme toggle is keyboard-only (press T) — no visible button

---

## 5. Performance

### File Sizes

| File | Size | Status |
|------|------|--------|
| `preseason.html` | 73 KB | ✅ |
| `season.html` | 68 KB | ✅ |
| `power-rankings.html` | 60 KB | ✅ |
| `history.html` | 52 KB | ✅ |
| `index.html` | 39 KB | ✅ |
| `draft.html` | 38 KB | ✅ |
| `fetch_sleeper.py` | 37 KB | ✅ |
| `trades.html` | 32 KB | ✅ |
| `week1.html` | 24 KB | ✅ |
| `config.js` | 6.8 KB | ✅ |
| `bg_hero.png` | 419 KB | ✅ (under 500 KB) |
| `icon_preseason.png` | 676 B | ✅ |
| `icon_week.png` | 611 B | ✅ |

**Total site weight:** ~850 KB (excluding `dontuse*` legacy files and `data/` directory)
**No files exceed 500 KB** ✅

### Canvas Animations — GOOD
All canvas animations use `requestAnimationFrame`:
- `index.html`: Starfield (line 672), counter animation (line 723), vault particles (line 929)
- `preseason.html`: Bar chart animation (line 1051)
- `season.html`: Trend chart (lines 858, 1362)
- `history.html`: Constellation (line 324), Elo chart (line 378), tab animation (line 395)
- `week1.html`: Reveal animation (line 449)

**No `setInterval` used for animations** ✅

### Scroll Listeners — MOSTLY PASSIVE
- 13 out of ~20 scroll listeners use `{passive: true}` ✅
- Remaining ~7 scroll listeners lack `{passive: true}` — these are primarily for reveal/intersection-style effects. Since they don't call `preventDefault()`, the browser can optimize them, but explicitly marking them passive is better practice.

### Issues Found
- **LOW:** ~7 scroll event listeners across files don't specify `{passive: true}` (e.g., `index.html:683`, `preseason.html:1070`, `history.html:335`, `week1.html:291`)

---

## 6. Security

### API Keys / Tokens / Passwords — CLEAN
Searched entire repository for: `token`, `secret`, `password`, `api_key`, `apikey`, `API_KEY`, `Bearer`, `Authorization`
- **No matches in any source files** ✅
- Only matches were in `CLAUDE.md` and `.claude/commands/` (documentation about the audit itself)

### .gitignore — ADEQUATE
```
data/players.json    # Large temp file excluded
__pycache__/         # Python bytecode excluded
```
- No `.env`, credentials, or sensitive files present in repo ✅
- The Sleeper API is public and requires no authentication ✅

### GitHub Actions — SECURE
- `fetch-sleeper-data.yml` uses no secrets or tokens ✅
- `permissions: contents: write` is appropriately scoped ✅
- No environment variables exposed ✅
- Uses pinned action versions (`actions/checkout@v4`, `actions/setup-python@v5`) ✅

### fetch_sleeper.py — POLITE
- User-Agent header set: `"JailyardDynasty/1.0"` (lines 50, 183) ✅
- No API keys or auth tokens used ✅

### Issues Found
- **None** — security posture is clean.

---

## 7. Accessibility

### ARIA Attributes Per Page

| Page | `aria-*` Count | Details |
|------|:--------------:|---------|
| `index.html` | 5 | `aria-hidden="true"` on starfield canvas, fun ticker, vault particles; `aria-label` on hamburger, vault close |
| `preseason.html` | 2 | `aria-label` on hamburger, back-to-top |
| `season.html` | 1 | `aria-label` on hamburger |
| `history.html` | 1 | `aria-label` on hamburger |
| `draft.html` | 2 | `aria-label` on hamburger, back-to-top |
| `trades.html` | 2 | `aria-label` on hamburger, back-to-top |
| `week1.html` | 2 | `aria-label` on hamburger, back-to-top |
| `power-rankings.html` | 2 | `aria-label` on hamburger, back-to-top |

**Total: 17 aria attributes across 8 pages**

### Buttons — MOSTLY ACCESSIBLE
- All hamburger buttons have `aria-label` ✅
- Back-to-top buttons have `aria-label` ✅
- Tab/filter buttons have visible text content ✅
- Theme toggle buttons have visible text ✅
- `preseason.html` compare close button uses SVG icon — has no `aria-label` ⚠️

### Hamburger Menus — MISSING `aria-expanded`
- **No page uses `aria-expanded`** on the hamburger button. This is a screen reader gap — users can't tell if the menu is open or closed.

### Canvas Elements

| Page | Canvas | `aria-hidden` | Text Alternative |
|------|--------|:------------:|:----------------:|
| `index.html` | Starfield | ✅ | N/A (decorative) |
| `index.html` | Vault particles | ✅ | N/A (decorative) |
| `preseason.html` | 4 data charts | ❌ | ❌ |
| `season.html` | Trend chart | ❌ | ❌ |
| `trades.html` | Activity chart | ❌ | ❌ |
| `history.html` | Constellation (decorative) | ❌ | N/A |
| `history.html` | Elo chart (data) | ❌ | ❌ |
| `draft.html` | Draft chart | ❌ | ❌ |

### Images — NO `alt` ATTRIBUTES
- `<img>` tag search returned **zero results**. The site uses no `<img>` tags — images are CSS backgrounds or canvas. Not an issue.

### `prefers-reduced-motion` — GOOD
Present on 7 of 8 pages ✅
- **Missing:** `power-rankings.html` ⚠️

### Skip-to-Content Links — MISSING
No skip navigation links on any page.

### Heading Hierarchy
Not fully audited, but pages generally follow `h1` > `h2` > `h3` patterns based on section structure.

### Issues Found
- **HIGH:** No `aria-expanded` on any hamburger menu (8 pages)
- **MEDIUM:** 7 data canvas charts lack text alternatives (preseason: 4, season: 1, trades: 1, history: 1, draft: 1)
- **MEDIUM:** `history.html` decorative constellation canvas missing `aria-hidden="true"`
- **LOW:** No skip-to-content links (all 8 pages)
- **LOW:** `power-rankings.html` missing `prefers-reduced-motion` media query
- **LOW:** `preseason.html` compare close button missing `aria-label`

---

## 8. Mobile Responsiveness

### `@media` Breakpoints Per Page

| Page | Breakpoint Count | Notable Breakpoints |
|------|:----------------:|---------------------|
| `index.html` | 3 | Responsive grid, hero, nav |
| `preseason.html` | 3 | Table scroll, card layout, nav |
| `season.html` | 3 | Week selector, matchup cards |
| `history.html` | 2 | Card layout, nav |
| `draft.html` | 2 | Draft board, nav |
| `trades.html` | 2 | Timeline, nav |
| `week1.html` | 2 | Article layout, nav |
| `power-rankings.html` | 1 | Minimal responsive rules |

### Hamburger Menu — PRESENT ON ALL PAGES ✅
All 8 pages have a hamburger button with open/close JavaScript logic.

### `overflow-x: hidden` on Body

| Page | Has `overflow-x: hidden` |
|------|:------------------------:|
| `index.html` | ✅ |
| `season.html` | ✅ |
| `history.html` | ✅ |
| `draft.html` | ✅ |
| `trades.html` | ✅ |
| `power-rankings.html` | ✅ |
| `preseason.html` | ❌ |
| `week1.html` | ❌ |

### `clamp()` Usage

| Page | `clamp()` Count | Usage |
|------|:---------------:|-------|
| `index.html` | 5 | Typography |
| `preseason.html` | 4 | Typography (`--h1`, `--h2`) |
| `week1.html` | 3 | Typography (`--h1`, `--h2`, `--h3`) |
| `history.html` | 4 | Typography |
| `draft.html` | 3 | Typography |
| `trades.html` | 4 | Typography |
| `season.html` | 1 | Limited |
| `power-rankings.html` | 2 | Limited |

### Viewport Meta Tag — ALL PAGES ✅
All 8 pages have `<meta name="viewport" content="width=device-width, initial-scale=1">` ✅

### Issues Found
- **MEDIUM:** `preseason.html` missing `overflow-x: hidden` on body — may cause horizontal scroll on mobile
- **MEDIUM:** `week1.html` missing `overflow-x: hidden` on body
- **LOW:** `power-rankings.html` has minimal responsive breakpoints (only 1 `@media` query)

---

## 9. Technical Debt

### Lines of Code Per File

| File | Total Lines | Est. JS Lines | Status |
|------|:-----------:|:-------------:|--------|
| `season.html` | 1,480 | ~1,200 | ⚠️ >1000 JS |
| `preseason.html` | 1,331 | ~1,000 | ⚠️ Borderline |
| `power-rankings.html` | 1,107 | ~900 | ✅ |
| `history.html` | 987 | ~750 | ✅ |
| `index.html` | 960 | ~500 | ✅ |
| `fetch_sleeper.py` | 928 | N/A (Python) | ✅ |
| `draft.html` | 642 | ~400 | ✅ |
| `trades.html` | 588 | ~350 | ✅ |
| `week1.html` | 497 | ~200 | ✅ |
| `config.js` | 153 | 153 | ✅ |

### Empty Catch Blocks — 1
- `power-rankings.html:297` → `catch(e){}` — silently swallows errors

### Console.log Statements — 1
- `season.html` — 1 occurrence (likely debug leftover)

### TODO / FIXME / HACK Comments — NONE ✅

### Duplicated Code Blocks

| Pattern | Occurrences | Files |
|---------|:-----------:|-------|
| Navigation HTML (hamburger + links) | 8 | All pages — each has its own nav HTML |
| CSS `:root` variable block | 8 | All pages — each defines its own theme vars |
| Light theme overrides | 7 | All except history (inline) |
| Footer HTML | 8 | All pages (partially centralized via `config.js:buildFooterNav()`) |
| Intersection Observer reveal pattern | 6 | preseason, season, history, draft, trades, week1 |
| Back-to-top button + logic | 6 | preseason, power-rankings, draft, trades, week1, history |
| Theme toggle logic | 7 | All except history |

**Note:** The `config.js` file provides `applyConfig()`, `buildFooterNav()`, and `applyLeagueName()` to centralize some patterns. Nav HTML remains duplicated because each page has slightly different active states and link sets.

### Hardcoded Values
- Team names, owners, and roster data are hardcoded in `preseason.html` (lines 360-600) — by design for a static site
- Sleeper league IDs duplicated in both `config.js:24-30` and `fetch_sleeper.py:31-37` — intentional (Python can't import JS)
- Trade data hardcoded in `trades.html` — by design

### Issues Found
- **LOW:** `season.html` has ~1,200 lines of JS (largest page)
- **LOW:** 1 empty catch block in `power-rankings.html:297`
- **LOW:** 1 console.log statement in `season.html`
- **INFO:** Nav HTML duplicated across all 8 pages (architectural choice, not a bug)
- **INFO:** CSS variable blocks duplicated across all 8 pages (inline-everything design)

---

## 10. Priority Fix List

### HIGH Priority
| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | Add `aria-expanded` to all hamburger buttons | All 8 pages | Screen readers can't determine menu state |

### MEDIUM Priority
| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 2 | Add `overflow-x: hidden` to body | `preseason.html`, `week1.html` | Horizontal scroll on mobile |
| 3 | Add text alternatives for data canvas charts | preseason (4), season (1), trades (1), history (1), draft (1) | Data inaccessible to screen readers |
| 4 | Add `aria-hidden="true"` to decorative constellation canvas | `history.html:217` | Screen reader noise |
| 5 | Rename `--warning` to `--warn` | `preseason.html:23` | CSS variable naming drift |
| 6 | Add theme toggle button | `history.html` | Users can't switch themes |

### LOW Priority
| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 7 | Add `prefers-reduced-motion` | `power-rankings.html` | Motion sensitivity |
| 8 | Add `{passive: true}` to remaining scroll listeners | ~7 across multiple pages | Minor scroll perf |
| 9 | Add missing nav links (Draft, Trades) | `power-rankings.html` nav | Navigation gap |
| 10 | Add visible theme toggle to index.html | `index.html` | Discoverability (currently keyboard-only) |
| 11 | Remove empty catch block | `power-rankings.html:297` | Silent error swallowing |
| 12 | Remove console.log | `season.html` | Debug artifact |
| 13 | Add skip-to-content links | All 8 pages | Keyboard navigation |
| 14 | Add `aria-label` to compare close button | `preseason.html:330` | Screen reader label |

---

*Audit complete. Overall the site is well-built, consistent, and publication-ready with the above accessibility and mobile fixes applied.*
