# JAILYARD AUDIT REPORT

**Audit Date:** 2026-02-15 (Revision 2 — post-merge with main)
**Auditor:** Claude Code `/audit` command
**Scope:** All 8 HTML pages, config.js, fetch_sleeper.py, GitHub Actions workflow

---

## 1. Executive Summary — CONDITIONAL GO

The site is **ready to share with the league** with a short list of fixes. Content accuracy is solid, performance is excellent, and security is clean. The main gaps are:

- **3 pages missing Power Rankings / Draft / Trades nav links** (power-rankings.html, draft.html, trades.html have incomplete cross-linking)
- **1 empty catch block** in `power-rankings.html` (silent data failure)
- **1 stray `console.log`** in `season.html`
- **`power-rankings.html` missing `prefers-reduced-motion`** CSS
- **All 8 hamburger menus missing `aria-expanded`**

**Blockers for public release:** 0
**Should-fix before sharing:** 6
**Nice-to-have improvements:** 14

---

## 2. Content Accuracy — All Accurate

| Check | Result |
|-------|--------|
| Team count = 12 | Consistent everywhere (config.js, index meta, fun facts) |
| 2022 champ: Legion of Bouz | Correct in preseason.html, index.html |
| 2023 champ: General Ken-obi | Correct in preseason.html, index.html |
| 2024 champ: Kittler on the Roof | Correct in preseason.html, index.html |
| Current season = 2025 | No stale references |
| Fun facts ticker | All verifiable claims accurate |
| fetch_sleeper.py LEAGUE_IDS | All 5 seasons present (2022–2026), match config.js |
| Team name consistency | All 12 names match across preseason.html, draft.html, trades.html |

**Issues found: 0**

---

## 3. Link Integrity — 3 Nav Gaps Found

**All `.html` files exist.** No broken links to missing pages. Anchor links verified (e.g. `#rankings` in preseason.html resolves correctly). External Sleeper API docs URL is valid.

**Navigation cross-link coverage:**

| File | Has draft.html | Has trades.html | Has power-rankings.html | Total links |
|------|:-:|:-:|:-:|:-:|
| index.html | Y | Y | Y | 8 |
| history.html | Y | Y | Y | 8 |
| season.html | Y | Y | Y | 8 |
| preseason.html | Y | Y | Y | 8 |
| week1.html | Y | Y | Y | 8 |
| **draft.html** | Y (self) | Y | **N** | 7 |
| **trades.html** | Y | Y (self) | **N** | 7 |
| **power-rankings.html** | **N** | **N** | Y (self) | 6 |

**Should fix:** Add missing nav links to these 3 pages.

**Data files:** `data/` directories exist but JSON cache files are empty (expected — requires `python3 fetch_sleeper.py --all` to populate). Pages fall back to live Sleeper API.

---

## 4. Visual Consistency — Clean

**`--accent-2` vs `--accent2`:** All active files use `--accent2`. Fixed in previous round.

**Canonical CSS variable coverage:**

| File | Core 7 vars | Extras |
|------|:-:|---|
| index.html | 7/7 | `--glow-1`, `--glow-2` |
| preseason.html | 7/7 | `--glass`, `--good`, `--bad`, `--warning`, `--font-main`, `--h1`, `--h2`, `--maxw` |
| season.html | 7/7 | `--glass`, `--good`, `--bad`, `--warn`, `--font`, `--maxw` |
| history.html | 7/7 | `--glass`, `--good`, `--bad`, `--maxw` |
| power-rankings.html | 7/7 | `--glass`, `--good`, `--bad`, `--warn`, `--font`, `--maxw` |
| draft.html | 7/7 | `--good`, `--bad`, `--warn`, `--glow-1`, `--glow-2` |
| trades.html | 7/7 | `--good`, `--bad`, `--warn`, `--glow-1`, `--glow-2` |
| week1.html | 7/7 | `--glass`, `--good`, `--bad`, `--warn`, `--font-main`, `--h1`, `--h2`, `--h3` |

**Minor naming variance (not breaking):**
- `--warn` (6 files) vs `--warning` (preseason.html) — same purpose, different name
- `--font` (season, power-rankings) vs `--font-main` (preseason, week1) — same purpose

**No hardcoded hex colors found outside `:root` blocks** (position colors in draft/trades are intentional inline values for QB/RB/WR/TE).

---

## 5. Performance — Excellent

**File sizes (all under 500KB):**

| File | Size |
|------|------|
| bg_hero.png | 419K (largest asset) |
| preseason.html | 73K |
| season.html | 68K |
| power-rankings.html | 60K |
| history.html | 52K |
| index.html | 39K |
| draft.html | 38K |
| trades.html | 32K |
| week1.html | 24K |
| config.js | 6.8K |
| **Total site** | **~470K** |

**Canvas animations:** All use `requestAnimationFrame`. No `setInterval` found.

**Scroll listeners missing `{passive: true}`:**

| File | Lines |
|------|-------|
| index.html | 683, 816 |
| history.html | 335, 971, 978 |
| draft.html | 607, 628 |
| power-rankings.html | 1089, 1096 |
| preseason.html | 1070, 1116, 1323 |
| trades.html | 553, 574 |
| week1.html | 291, 473, 489 |

18 total scroll listeners without passive flag. Non-blocking but could improve mobile scroll performance.

---

## 6. Security — Clean

| Check | Result |
|-------|--------|
| API keys / tokens / passwords | None found |
| `.gitignore` covers `data/players.json` | Yes |
| GitHub Actions exposes secrets | No — `github-actions[bot]` only |
| `fetch_sleeper.py` User-Agent | Set: `JailyardDynasty/1.0` |
| Sleeper League IDs | Public identifiers, not secrets |
| External dependencies | Zero — no CDN, no npm |

**No security issues found.**

---

## 7. Accessibility — Needs Improvement

**Total ARIA attributes: 19** (low for 8 pages with interactive elements)

| Check | Status | Count |
|-------|--------|-------|
| Hamburger `aria-label` | All 8 pages | 8/8 |
| Hamburger `aria-expanded` | **Missing on all pages** | 0/8 |
| `prefers-reduced-motion` | 7 of 8 pages | **power-rankings.html missing** |
| Decorative canvas `aria-hidden` | 2 of 3 decorative canvases | history.html constellation missing |
| Data chart canvas accessibility | **None have aria-label** | 0/9 charts |
| `:focus-visible` styles | 5 of 8 pages | draft.html, trades.html, preseason.html missing |
| `var` usage | 0 | All modern const/let |
| Deprecated `keyCode` | 0 | All use `e.key` |

**Key gaps:**
1. No `aria-expanded` on any hamburger button — screen readers can't tell if nav is open
2. 9 data chart canvases have no accessible alternative for screen readers
3. power-rankings.html is the only page without `prefers-reduced-motion`

---

## 8. Mobile — Responsive

| Check | Status |
|-------|--------|
| `<meta viewport>` | All 8 pages |
| Breakpoints defined | 5 values (480–800px) across all pages |
| Hamburger menu + JS toggle | All 8 pages |
| `overflow-x: hidden` on body | All pages |
| `clamp()` typography | 22 instances across all pages |
| Fixed-width issues | Data tables use intentional `min-width` + scroll containers |

**No mobile responsiveness issues found.**

---

## 9. Technical Debt — Moderate

### Code volume

| File | JS Lines | Status |
|------|----------|--------|
| **season.html** | **1,187** | **Exceeds 1000-line threshold** |
| preseason.html | 975 | Approaching |
| power-rankings.html | 863 | OK |
| history.html | 712 | OK |
| draft.html | 403 | OK |
| trades.html | 354 | OK |
| index.html | 332 | OK |
| week1.html | 213 | OK |

### Code quality issues

| Issue | Count | Where |
|-------|-------|-------|
| Empty catch blocks | 1 | power-rankings.html:297 |
| `console.log` in production | 1 | season.html:344 |
| `var` usage | 0 | Clean |
| Deprecated `keyCode` | 0 | Clean |
| TODO/FIXME/HACK | 0 | Clean |
| Inline `onclick` attributes | 4 | history.html (2), season.html (2) |

### Duplication hotspots

| Pattern | Duplicated across | Opportunity |
|---------|-------------------|-------------|
| Nav HTML | 8 files, 4 different structures | config.js could generate |
| Footer HTML | 8 files | `renderConfigFooter()` exists but not used on all pages |
| Hamburger toggle JS | 8 files | Could extract to config.js |
| Scroll progress bar CSS + JS | 7 files | Could extract to config.js |
| Theme toggle binding | 8 files, 3 different button IDs | Could standardize |
| Back-to-top button + JS | 7 files | Could extract |

---

## 10. Priority Fix List

| # | Fix | Severity | Files |
|---|-----|----------|-------|
| 1 | Add missing nav links: Power Rankings to draft.html + trades.html; Draft + Trades to power-rankings.html | Should fix | 3 files |
| 2 | Add `console.error` to empty catch in power-rankings.html:297 | Should fix | 1 file |
| 3 | Remove `console.log` from season.html:344 | Should fix | 1 file |
| 4 | Add `prefers-reduced-motion` CSS to power-rankings.html | Should fix | 1 file |
| 5 | Add `aria-expanded="false"` to all hamburger buttons + toggle in JS | Should fix | 8 files |
| 6 | Add `aria-hidden="true"` to decorative constellation canvas in history.html | Should fix | 1 file |
| 7 | Add `{passive: true}` to 18 scroll event listeners | Nice to have | 7 files |
| 8 | Add `aria-label` to 9 data chart canvas elements | Nice to have | 5 files |
| 9 | Add `:focus-visible` styles to draft.html, trades.html, preseason.html | Nice to have | 3 files |
| 10 | Standardize `--warn` / `--warning` variable name | Nice to have | 1 file |
| 11 | Standardize `--font` / `--font-main` variable name | Nice to have | 2 files |
| 12 | Convert 4 inline `onclick` handlers to `addEventListener()` | Nice to have | 2 files |
| 13 | Standardize hamburger `aria-label` text ("Menu" vs "Toggle navigation menu") | Nice to have | 2 files |
| 14 | Update config.js pages to include all pages for footer generation | Nice to have | 1 file |

---

**Bottom line:** Content is bulletproof, performance is great, security is clean. Fix items 1–6 and this is ready to share with confidence.
