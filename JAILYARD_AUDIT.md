# JAILYARD DYNASTY POWER RANKINGS — PRE-PUBLISH AUDIT

**Date:** 2026-02-15
**Auditor:** Automated (Claude)
**Scope:** Full site audit across 8 HTML pages, config.js, fetch_sleeper.py, GitHub Actions

---

## 1. Executive Summary

### CONDITIONAL GO

The site is in strong shape for publishing. Content accuracy is solid, all internal links resolve, and the security posture is clean. Three areas need attention before going fully public:

1. **`power-rankings.html` doesn't load `config.js`** — the only page that doesn't; duplicates LEAGUE_IDS inline, misses `applyConfig()`, nav is missing Draft/Trades links, footer has no nav
2. **Accessibility gaps** — No `aria-expanded` on any hamburger menu; most canvas data charts lack text alternatives; no skip-to-content links
3. **Missing `overflow-x: hidden`** on `preseason.html` and `week1.html` — risk of horizontal scroll on mobile
4. **History page has no theme toggle button** — users have no way to switch themes on that page

None of these are blockers, but items 1-3 should be addressed before sharing widely.

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
- `config.js:62-75`: Separate fun facts list (12 entries) with **different content** — see "Dead Code" note below

### fetch_sleeper.py LEAGUE_IDS — CORRECT
```python
2022: "792314138780090368"
2023: "918335334096846848"
2024: "1048889097223266304"
2025: "1180228858937966592"
2026: "1312884727480352768"   # offseason
```
Matches `config.js:24-30` exactly ✅

### config.js `funFacts` — DEAD CODE
`config.js:62-75` defines a `funFacts` array (12 entries), but `index.html` builds its ticker from its own hardcoded inline array at lines 767-783 and **never reads** `LEAGUE_CONFIG.funFacts`. The two arrays contain different facts. This is dead code — editing `config.js` fun facts has no effect.

### Issues Found
- **LOW:** `config.js` `funFacts` array is unused dead code — `index.html` defines its own inline ticker facts
- **LOW:** `power-rankings.html` inline `LEAGUE_IDS` is missing the 2026 entry (present in `config.js` and `fetch_sleeper.py`)

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
Nav bar gaps (missing `power-rankings.html` link):
- `draft.html` nav (lines 164-170) — missing `power-rankings.html`
- `trades.html` nav (lines 157-163) — missing `power-rankings.html`
- `power-rankings.html` nav (lines 210-215) — missing `draft.html` and `trades.html`

Footer gaps — most pages have hardcoded footers missing `power-rankings.html` in the HTML source, but since those 7 pages load `config.js`, the `renderConfigFooter()` function overwrites the static footer at runtime and injects the correct links including Power Rankings. So this is a **source-code-only** issue, not user-facing, for all pages except `power-rankings.html` (which doesn't load `config.js` and has no footer nav at all).

### `power-rankings.html` — NOT LOADING `config.js`
This is the only page that does **not** include `<script src="config.js"></script>`. As a result:
- The brand name "The Jailyard" is hardcoded (no `data-league-name` attribute)
- The footer is hardcoded with no navigation links (lines 238-241)
- `LEAGUE_IDS` are duplicated inline (lines 247-252) instead of using `LEAGUE_CONFIG.sleeperLeagueIds`
- `applyConfig()` is never called
- If someone forks the repo and edits `config.js` to rebrand, this page won't pick up the changes

### Issues Found
- **MEDIUM:** `power-rankings.html` does not load `config.js` — the only page that doesn't
- **MEDIUM:** `power-rankings.html` main nav omits Draft and Trades links (lines 211-215)
- **MEDIUM:** `power-rankings.html` footer has no navigation links (all other pages include them)

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
| `preseason.html` | `--warning`, `--h1`, `--h2`, `--maxw`, `--font-main` | `--warning` deviates from `--warn`; `--font-main` vs `--font` |
| `week1.html` | `--h1`, `--h2`, `--h3`, `--font-main` | Uses `--font-main` (matches preseason) |
| `season.html` | `--font`, `--maxw` | Uses `--font` (differs from `--font-main`) |
| `power-rankings.html` | `--font`, `--maxw` | Uses `--font` (differs from `--font-main`) |
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
- **MEDIUM:** `preseason.html` uses `--warning:#ffb703` instead of `--warn:#ca8a04` (line 23) — both naming drift AND different color value
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
- 13 of 22 scroll listeners use `{passive: true}` ✅
- **11 scroll listeners lack `{passive: true}`** — primarily nav-scrolled-class toggles and parallax effects. None call `preventDefault()`, so all can safely be made passive.
  - `index.html:683`, `preseason.html:1070`, `history.html:335,971`, `trades.html:553`, `draft.html:607`, `week1.html:291`

### Canvas `devicePixelRatio` — GOOD
All 11 canvas implementations properly handle `devicePixelRatio` for Retina displays ✅

### Issues Found
- **LOW:** 11 scroll event listeners missing `{passive: true}`

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
- Rate limiting: `time.sleep(0.1)` between API calls (lines 140, 161) ✅
- No API keys or auth tokens used ✅

### innerHTML with External API Data — LOW RISK
Multiple pages fetch data from the Sleeper API and inject it via `innerHTML` without sanitization:
- `season.html` (lines 829, 957, 995)
- `power-rankings.html` (line 1038)
- `trades.html` (lines 385, 417)
- `index.html` (lines 783, 866)

The Sleeper API is a trusted source returning JSON, so the real-world risk is low. No `eval()` or `new Function()` is used anywhere.

### Issues Found
- **LOW:** `innerHTML` used with external API data in 6+ locations — low risk given Sleeper is trusted, but `textContent` would be safer for user-supplied strings
- **INFO:** `.gitignore` could add defensive entries (`.env`, `*.key`, `.DS_Store`) to prevent accidental future commits
- **INFO:** No Content Security Policy `<meta>` tag — defense-in-depth measure for static sites

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
- Most back-to-top buttons have `aria-label` ✅
- Tab/filter buttons have visible text content ✅
- Theme toggle buttons have visible text ✅
- `preseason.html` compare close button uses SVG icon — has no `aria-label` ⚠️
- `history.html:271` back-to-top button uses `&#8593;` with no `aria-label` ⚠️

### Form Inputs — MISSING LABEL
- `preseason.html:292` search input has `placeholder` but no `<label>` or `aria-label` ⚠️

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
- `trades.html`: Skips from `h2` to `h4` (no `h3`) inside trade cards — heading level gap
- `season.html`: No static `h1` element — relies entirely on JavaScript to render headings
- All other pages follow `h1` > `h2` > `h3` correctly

### Color Contrast Notes
- `--muted: #7a8194` on `--bg: #0b0d10` gives ~4.2:1 contrast — borderline for WCAG AA at small sizes (`.68rem`, `.72rem`)
- Gradient text via `background-clip: text` may be unreadable in Windows High Contrast Mode

### Issues Found
- **HIGH:** No `aria-expanded` on any hamburger menu (8 pages)
- **MEDIUM:** 7 data canvas charts lack text alternatives (preseason: 4, season: 1, trades: 1, history: 1, draft: 1)
- **MEDIUM:** `history.html` decorative constellation canvas missing `aria-hidden="true"`
- **MEDIUM:** `preseason.html:292` search input missing `<label>` or `aria-label`
- **LOW:** No skip-to-content links (all 8 pages)
- **LOW:** `power-rankings.html` missing `prefers-reduced-motion` media query
- **LOW:** `preseason.html:330` compare close button missing `aria-label`
- **LOW:** `history.html:271` back-to-top button missing `aria-label`
- **LOW:** `trades.html` heading hierarchy skips h3
- **LOW:** Touch targets on nav links (~37px) below recommended 44px minimum

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

### Breakpoint Consistency
Breakpoint values vary across files: `600px`, `700px`, `768px`, `800px`. This means some pages switch to mobile layout at different widths — a tablet-sized screen may see mobile on one page and desktop on another.

### Touch Targets
- Nav links: padding `.35rem .75rem` (~37px tall) — below 44px recommended minimum
- Hamburger buttons: ~37px total with SVG — slightly under 44px
- Back-to-top buttons: `44x44px` ✅
- `preseason.html` compare checkboxes: `20x20px` — well below 44px

### Issues Found
- **MEDIUM:** `preseason.html` missing `overflow-x: hidden` on body — may cause horizontal scroll on mobile
- **MEDIUM:** `week1.html` missing `overflow-x: hidden` on body
- **LOW:** `power-rankings.html` has minimal responsive breakpoints (only 1 `@media` query)
- **LOW:** Inconsistent breakpoints across files (600–800px range)
- **LOW:** Nav link and hamburger touch targets below 44px minimum

---

## 9. Technical Debt

### Lines of Code Per File

| File | Total Lines | JS Lines | Status |
|------|:-----------:|:--------:|--------|
| `season.html` | 1,480 | 1,058 | ⚠️ **>1000 JS** (33 functions) |
| `preseason.html` | 1,331 | 938 | ✅ |
| `power-rankings.html` | 1,107 | 780 | ✅ |
| `history.html` | 987 | 682 | ✅ |
| `index.html` | 960 | 308 | ✅ |
| `fetch_sleeper.py` | 928 | N/A | ✅ |
| `draft.html` | 642 | 369 | ✅ |
| `trades.html` | 588 | 319 | ✅ |
| `week1.html` | 497 | 193 | ✅ |
| `config.js` | 153 | 153 | ✅ |

### Empty/Silent Catch Blocks — 4
- `power-rankings.html:297` → `catch(e){}` — silently swallows errors
- `power-rankings.html:338` → `catch(e){ break; }` — breaks without logging
- `season.html:408` → `catch(e) { break; }` — breaks without logging
- `history.html:405` → `catch(e){ return null; }` — returns null silently

### Console Statements — 7
- `console.log`: 1 (`season.html:344` — debug leftover: `'Loaded offline data for'`)
- `console.error`: 6 (`season.html:327,348,416,421`; `history.html:413,417`) — these are appropriate error logging

### TODO / FIXME / HACK Comments — NONE ✅

### Duplicated Code Blocks

| Pattern | Occurrences | Notes |
|---------|:-----------:|-------|
| CSS `:root` variable block | 8 | Each page defines its own theme vars (inconsistent sets) |
| Light theme `.light{}` overrides | 8 | Repeated in every file |
| View Transitions CSS + keyframes | 8 | index.html uses different keyframe names (`fade-out`/`fade-in` vs `vt-out`/`vt-in`) |
| Navigation HTML (hamburger + links) | 8 | Hardcoded in each file; `config.js` only handles footer |
| Scroll progress bar (CSS + HTML + JS) | 8 | Identical pattern in every file |
| IntersectionObserver for `.reveal` | 7 | Slightly different configs per file |
| Back-to-top button (CSS + HTML + JS) | 7 | Inconsistent: class `.back-to-top` vs `.btt`, thresholds 400/500/600 |
| Theme toggle logic | 7 | 4 different ID conventions: `toggleDark`, `toggleTheme`, `themeToggle`, inline onclick |
| `gradientFor()` helper function | 2 | Identical in `preseason.html:684` and `draft.html:451` |

**Note:** The `config.js` file centralizes `applyConfig()`, `buildFooterNav()`, and `applyLeagueName()`. Main nav HTML remains duplicated because each page has different active states.

### Hardcoded Values
- Team names, owners, and roster data in `preseason.html` (lines 360-600) — by design
- Sleeper league IDs in 3 places: `config.js:24-30`, `power-rankings.html:247-252`, `fetch_sleeper.py:31-37`
- Sleeper API base URL hardcoded in 3 HTML files + Python (`SLEEPER = 'https://api.sleeper.app/v1'`)
- 27 occurrences of `rgba(11,13,16,...)` (the `--bg` color) hardcoded in CSS across all files — should reference a variable
- `config.js:62-75` `funFacts` and `config.js:78-84` `heroStats` are defined but `index.html` uses its own hardcoded versions
- Speculation rules (`<script type="speculationrules">`) only in 3 of 8 pages (index, draft, trades)

### Issues Found
- **LOW:** `season.html` has 1,058 lines of inline JS (only page over 1,000)
- **LOW:** 4 silent catch blocks across 3 files
- **LOW:** 1 debug `console.log` in `season.html:344`
- **INFO:** Nav HTML duplicated across all 8 pages (architectural choice)
- **INFO:** CSS variable blocks duplicated 8 times with inconsistent variable sets
- **INFO:** Speculation rules missing from 5 pages (won't break anything, just missed optimization)

---

## 10. Priority Fix List

### HIGH Priority
| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | Load `config.js` and call `applyConfig()` | `power-rankings.html` | Only page not using config; nav incomplete, footer empty, brand hardcoded |
| 2 | Add `aria-expanded` to all hamburger buttons | All 8 pages | Screen readers can't determine menu state |

### MEDIUM Priority
| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 3 | Add `overflow-x: hidden` to body | `preseason.html`, `week1.html` | Horizontal scroll on mobile |
| 4 | Add missing nav links: Draft/Trades on `power-rankings.html`; Power Rankings on `draft.html`/`trades.html` | 3 pages | Navigation gaps in static nav bars |
| 5 | Add text alternatives for data canvas charts | preseason (4), season (1), trades (1), history (1), draft (1) | Data inaccessible to screen readers |
| 6 | Add `aria-hidden="true"` to decorative constellation canvas | `history.html:217` | Screen reader noise |
| 7 | Rename `--warning` to `--warn` | `preseason.html:23` | CSS variable naming drift |
| 8 | Add theme toggle button | `history.html` | Users can't switch themes |

### LOW Priority
| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 9 | Add `prefers-reduced-motion` | `power-rankings.html` | Motion sensitivity |
| 10 | Add `{passive: true}` to remaining scroll listeners | 11 across 6 pages | Minor scroll perf |
| 11 | Add visible theme toggle to index.html | `index.html` | Discoverability (currently keyboard-only) |
| 12 | Remove empty catch block | `power-rankings.html:297` | Silent error swallowing |
| 13 | Remove console.log | `season.html` | Debug artifact |
| 14 | Add skip-to-content links | All 8 pages | Keyboard navigation |
| 15 | Add `aria-label` to compare close button and history back-to-top | `preseason.html:330`, `history.html:271` | Screen reader labels |
| 16 | Add `<label>` or `aria-label` to search input | `preseason.html:292` | Inaccessible form input |
| 17 | Remove/sync dead `funFacts` array in `config.js` | `config.js:62-75` | Dead code — `index.html` ignores it |
| 18 | Add 2026 to inline `LEAGUE_IDS` | `power-rankings.html:247-252` | Missing entry vs. config.js/fetch_sleeper.py |
| 19 | Fix heading hierarchy skip (h2 → h4) | `trades.html` | Accessibility — heading level gap |

---

*Audit complete. Overall the site is well-built, consistent, and publication-ready with the above accessibility and mobile fixes applied.*
