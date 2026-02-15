# JAILYARD AUDIT REPORT

**Audit Date:** 2026-02-15
**Auditor:** Claude Code `/audit` command
**Scope:** All 8 HTML pages, config.js, fetch_sleeper.py, GitHub Actions workflow

---

## 1. Executive Summary — CONDITIONAL GO

The site is **ready to share with the league** with a short list of fixes. Content accuracy is perfect, performance is excellent, and security is clean. The main gaps are accessibility polish (missing `aria-expanded` on hamburger menus, no alt text on chart canvases) and one empty catch block in `power-rankings.html`. Code duplication across files is the primary technical debt but doesn't affect the user experience.

**Blockers for public release:** 0
**Should-fix before sharing:** 3
**Nice-to-have improvements:** 12

---

## 2. Content Accuracy — All Accurate

| Check | Result |
|-------|--------|
| Team count (12) | Consistent across all pages |
| 2022 champ: Legion of Bouz | Correct everywhere |
| 2023 champ: General Ken-obi | Correct everywhere |
| 2024 champ: Kittler on the Roof | Correct everywhere |
| Current season = 2025 | No stale references found |
| Fun facts ticker | All claims verified accurate |
| fetch_sleeper.py LEAGUE_IDS | All 5 seasons present (2022-2026) |
| Team name consistency | All 12 names match across pages |

**Issues found: 0**

---

## 3. Link Integrity — All Valid

All internal `href="*.html"` links resolve to existing files. No broken links.

| Issue | Severity | Location |
|-------|----------|----------|
| `preseason.html` nav missing Power Rankings link | Minor | Nav only has 6 of 8 pages |
| `season.html` nav missing Preseason link | Minor | Nav only has 7 of 8 pages |
| Anchor `href="#rankings"` in preseason.html has no matching ID | Minor | ~line 196 |

External links: Sleeper API docs URL is valid.

---

## 4. Visual Consistency — Minor CSS Drift

**`--accent-2` vs `--accent2`:** FIXED — All active files now use `--accent2`. Legacy `dontuse*` files still have `--accent-2` (expected, not touched per rules).

**Variable coverage by file:**

| File | Missing from canonical set |
|------|--------------------------|
| index.html | `--glass`, `--good`, `--bad`, `--warn` |
| history.html | `--warn` |
| draft.html | `--glass` |
| trades.html | `--glass` |
| week1.html | `--maxw` |
| preseason.html | Uses `--warning` instead of `--warn` |

**Naming inconsistencies:**
- Font variable: `--font` (season, power-rankings) vs `--font-main` (preseason, week1)
- Warning variable: `--warn` (most files) vs `--warning` (preseason)

**Hardcoded colors outside `:root`:** Position colors (QB red, RB blue, WR green, TE yellow) are hardcoded in draft.html and trades.html rather than defined as CSS variables. Gradient extension colors (`#a78bfa`, `#f472b6`) also hardcoded in multiple files.

---

## 5. Performance — Excellent

**File sizes (all under 500KB threshold):**

| File | Size |
|------|------|
| preseason.html | 73K (largest) |
| season.html | 68K |
| power-rankings.html | 60K |
| history.html | 52K |
| index.html | 39K |
| draft.html | 38K |
| trades.html | 32K |
| week1.html | 24K |
| config.js | 6.8K |
| bg_hero.png | 419K |

**Canvas animations:** All use `requestAnimationFrame` — no `setInterval` found.

**Scroll listeners missing `{passive: true}`:**
- `index.html` line ~683 (nav scroll toggle)
- `history.html` lines ~335, ~971 (nav + back-to-top)
- `preseason.html` line ~1070 (parallax scroll)

These are non-blocking but could improve scroll performance on mobile.

---

## 6. Security — Clean

| Check | Result |
|-------|--------|
| API keys / tokens / passwords | None found |
| `.gitignore` covers `data/players.json` | Yes |
| GitHub Actions exposes secrets | No — uses bot credentials only |
| `fetch_sleeper.py` User-Agent header | Set to `JailyardDynasty/1.0` |
| Sleeper League IDs | Public identifiers, not secrets |

**No security issues found.**

---

## 7. Accessibility — Needs Improvement

**Total ARIA attributes across all pages: 17** (low for 8 pages)

| Check | Status | Details |
|-------|--------|---------|
| `prefers-reduced-motion` | 7/8 pages | Present in all production pages |
| Hamburger `aria-label` | 8/8 | All have labels |
| Hamburger `aria-expanded` | 0/8 | **Missing on all pages** |
| Chart canvas alt text | 0/7 charts | **No alternatives for screen readers** |
| Decorative canvas `aria-hidden` | 2/4 | index.html has it, history.html missing |
| Focus-visible styles | Good | Defined on buttons and links |
| Color contrast | Acceptable | `--muted` on `--bg` passes WCAG AA |
| Tab buttons ARIA roles | Missing | No `role="tab"` or `aria-selected` |

**Key recommendations:**
1. Add `aria-expanded="false"` to hamburger buttons, toggle in JS
2. Add `aria-label` to chart `<canvas>` elements describing what data they show
3. Add `aria-hidden="true"` to decorative canvas in history.html

---

## 8. Mobile — Responsive

| Check | Status |
|-------|--------|
| Breakpoints defined | 5 breakpoints (480px–800px) across all pages |
| Hamburger menu exists | All 8 pages |
| Hamburger JS toggle works | All pages have click handler |
| `overflow-x: hidden` | Present on all pages |
| `clamp()` typography | 24 instances across all pages |
| Fixed-width issues | Data tables use `min-width` + scroll container (intentional) |

**No mobile responsiveness issues found.**

---

## 9. Technical Debt — Moderate

### JavaScript volume
| File | JS Lines | Status |
|------|----------|--------|
| season.html | 1,188 | Exceeds 1000-line threshold |
| preseason.html | 976 | Approaching threshold |
| power-rankings.html | 863 | Large |
| history.html | 713 | OK |
| draft.html | 407 | OK |
| trades.html | 358 | OK |
| index.html | 336 | OK |
| week1.html | 214 | OK |

### Code quality
| Check | Count | Status |
|-------|-------|--------|
| Empty catch blocks | 1 | `power-rankings.html:297` |
| `console.log` statements | 1 | `season.html:344` |
| `var` usage | 0 | All modern `const`/`let` |
| Deprecated `keyCode` | 0 | All use `e.key` |
| TODO/FIXME/HACK | 0 | Clean |

### Duplication hotspots
| Pattern | Duplicated across |
|---------|-------------------|
| Nav HTML markup | 4 different implementations |
| Footer HTML | 8 different implementations (config.js provides `renderConfigFooter()` but not all pages use it consistently) |
| Scroll progress bar (CSS + JS) | 7 pages |
| Theme toggle | 3 different button IDs, 2 binding patterns |
| Hamburger menu toggle JS | 6 pages |

### Recommendations
1. Fix the empty catch block in `power-rankings.html:297`
2. Remove `console.log` from `season.html:344`
3. Standardize theme toggle button ID to `themeToggle` across all pages
4. Consider extracting shared scroll-progress and hamburger JS into config.js helpers

---

## 10. Priority Fix List

| # | Fix | Impact | Severity |
|---|-----|--------|----------|
| 1 | Add `console.error` to empty catch in `power-rankings.html:297` | Silent data failures | Should fix |
| 2 | Remove `console.log` from `season.html:344` | Debug noise in production | Should fix |
| 3 | Add `aria-expanded` to all hamburger buttons | Screen reader navigation | Should fix |
| 4 | Add `{passive: true}` to 4 scroll listeners | Mobile scroll perf | Nice to have |
| 5 | Add `aria-label` to chart canvas elements | Screen reader data access | Nice to have |
| 6 | Add `aria-hidden="true"` to decorative canvas in history.html | Screen reader noise | Nice to have |
| 7 | Standardize `--warn` / `--warning` variable name | CSS consistency | Nice to have |
| 8 | Standardize `--font` / `--font-main` variable name | CSS consistency | Nice to have |
| 9 | Add missing nav links (Power Rankings in preseason, Preseason in season) | Navigation gaps | Nice to have |
| 10 | Add `role="tab"` and `aria-selected` to tab buttons | Accessibility | Nice to have |
| 11 | Define position colors as CSS variables | Theming consistency | Nice to have |
| 12 | Standardize theme toggle button ID across all pages | Code consistency | Nice to have |

---

**Bottom line:** Content is bulletproof, performance is great, security is clean. Fix the 3 "should fix" items and this is ready to share with confidence. The technical debt (duplication) is manageable at the current scale and doesn't affect the end-user experience.
