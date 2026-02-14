# Audit — Jailyard

Comprehensive pre-publish audit. Run this before sharing the site with league members or making public.

## Full Audit Scope

### 1. Content Accuracy
Open each HTML file and verify:
- Team names are consistent across all pages
- Team count matches (should be 12 everywhere)
- Championship data is accurate (2022: Legion of Bouz, 2023: General Ken-obi, 2024: Kittler on the Roof)
- Season references say 2025 (not stale from earlier versions)
- Fun facts ticker in `index.html` has no outdated claims
- `fetch_sleeper.py` LEAGUE_IDS dictionary has correct IDs

### 2. Link Integrity
- Every internal link (`href="*.html"`) resolves to an existing file
- External links (Sleeper API docs) are valid
- No broken anchor links (`href="#section"` pointing to nonexistent IDs)

### 3. Visual Consistency
For each page, verify the CSS variable block matches the canonical set:
```
--bg, --fg, --muted, --accent, --accent2, --card, --border
```
Optional extras: `--glass, --good, --bad, --warn, --maxw, --font`

Flag any page with unique variables not used elsewhere.

### 4. Performance
- Measure total file sizes (all HTML + images + data JSON)
- Flag any single file >500KB
- Check if Canvas animations have frame limiting (requestAnimationFrame, not setInterval)
- Check if scroll event listeners use `{passive: true}`

### 5. Security (Lightweight)
- `grep -rn` for anything resembling API keys, tokens, or passwords
- Verify `.gitignore` excludes sensitive files
- Verify GitHub Actions workflow doesn't expose secrets
- Check that `fetch_sleeper.py` User-Agent header is set (API politeness)

### 6. Accessibility
- Count `aria-*` attributes per page
- Check all `<button>` elements have accessible labels
- Check hamburger menus have `aria-label` and `aria-expanded`
- Check Canvas elements: decorative ones have `aria-hidden="true"`, data ones have text alternatives
- Check for `prefers-reduced-motion` media query

### 7. Mobile Responsiveness
- Check each file for `@media` breakpoints
- Verify hamburger menu exists and has open/close logic
- Check for `overflow-x: hidden` on body (prevents horizontal scroll)
- Check `clamp()` usage on typography

### 8. Technical Debt
- Count total lines of JS per page (flag any >1000)
- Count empty catch blocks
- Count `console.log` statements
- Identify duplicated code blocks across files (shared nav, shared CSS)
- Check for TODO/FIXME/HACK comments

## Output

Write `JAILYARD_AUDIT.md` in the project root with:

1. **Executive Summary** — GO / CONDITIONAL GO / NO-GO
2. **Content Accuracy** — Issues found or "All accurate"
3. **Link Integrity** — Broken links or "All valid"
4. **Visual Consistency** — CSS drift issues
5. **Performance** — File sizes, animation concerns
6. **Security** — Clean or findings
7. **Accessibility** — Score and improvements
8. **Mobile** — Issues or "Responsive"
9. **Technical Debt** — Hotspots and recommendations
10. **Priority Fix List** — Ordered by impact, with estimated time
