# Low-Priority Audit Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the remaining 5 low-priority items (#11-15) from `JAILYARD_AUDIT.md` to bring the site to full polish.

**Architecture:** 4 tasks covering ARIA tab roles (2 files), gitignore hardening (1 file), CSS variable standardization (7 files), and legacy directory cleanup. Each task is a single commit.

**Tech Stack:** Pure HTML/CSS/JS (inline, zero dependencies)

---

### Task 1: Add ARIA tab roles to tab components

**Files:**
- Modify: `history.html` (lines 234-238 HTML, lines 250-253 panels, lines 363-367 handler)
- Modify: `season.html` (lines 832-837 handler, line 846 panel)

> preseason.html has no tab components (only hamburger + sort headers) — skip.

**Step 1: Edit history.html — tab bar container**

Find the `<div>` wrapping the 4 tab buttons (around line 233). Add `role="tablist"`:

```html
<!-- old -->
<div class="tabs">

<!-- new -->
<div class="tabs" role="tablist">
```

**Step 2: Edit history.html — 4 tab buttons**

Each button gets `role="tab"`, `aria-selected`, and `aria-controls`:

```html
<!-- old -->
<button class="tab active" data-tab="records">Records Book</button>
<button class="tab" data-tab="franchises">Franchises</button>
<button class="tab" data-tab="h2h">Head to Head</button>
<button class="tab" data-tab="elo">Elo Ratings</button>

<!-- new -->
<button class="tab active" data-tab="records" role="tab" aria-selected="true" aria-controls="p-records">Records Book</button>
<button class="tab" data-tab="franchises" role="tab" aria-selected="false" aria-controls="p-franchises">Franchises</button>
<button class="tab" data-tab="h2h" role="tab" aria-selected="false" aria-controls="p-h2h">Head to Head</button>
<button class="tab" data-tab="elo" role="tab" aria-selected="false" aria-controls="p-elo">Elo Ratings</button>
```

**Step 3: Edit history.html — 4 panel sections**

Each panel gets `role="tabpanel"`:

```html
<!-- old -->
<section id="p-records" class="panel" hidden></section>
<section id="p-franchises" class="panel" hidden></section>
<section id="p-h2h" class="panel" hidden></section>
<section id="p-elo" class="panel" hidden></section>

<!-- new -->
<section id="p-records" class="panel" role="tabpanel" hidden></section>
<section id="p-franchises" class="panel" role="tabpanel" hidden></section>
<section id="p-h2h" class="panel" role="tabpanel" hidden></section>
<section id="p-elo" class="panel" role="tabpanel" hidden></section>
```

**Step 4: Edit history.html — click handler ARIA toggle**

In the tab click handler (~line 363-367), after `btn.classList.add('active')`, add aria-selected toggling:

```javascript
// old
document.querySelector('.tab.active').classList.remove('active');
btn.classList.add('active');

// new
const prev = document.querySelector('.tab.active');
prev.classList.remove('active');
prev.setAttribute('aria-selected','false');
btn.classList.add('active');
btn.setAttribute('aria-selected','true');
```

**Step 5: Edit season.html — tab buttons**

Find the `.vtab` buttons (~line 832-837). The tabs container needs `role="tablist"`, each button needs `role="tab"`, `aria-selected`, and `aria-controls="viewContent"`.

First, find the wrapper `<div>` that contains the `.vtab` buttons and add `role="tablist"`. Then for each button:

```html
<!-- Each .vtab button needs: -->
role="tab" aria-selected="false"
<!-- The initially active one needs: -->
role="tab" aria-selected="true"
```

**Step 6: Edit season.html — click handler ARIA toggle**

In the `.vtab` click handler, add aria-selected toggling:

```javascript
// old
document.querySelector('.vtab.active').classList.remove('active');
btn.classList.add('active');

// new
const prev = document.querySelector('.vtab.active');
prev.classList.remove('active');
prev.setAttribute('aria-selected','false');
btn.classList.add('active');
btn.setAttribute('aria-selected','true');
```

**Step 7: Add `role="tabpanel"` to `#viewContent`**

Find `<div id="viewContent">` in season.html and add `role="tabpanel"`.

**Step 8: Verify**

- Open history.html, click each tab — content switches, inspect buttons to confirm `aria-selected` flips
- Open season.html, pick a week, click view tabs — same check
- No console errors

**Step 9: Commit**

```bash
git add history.html season.html
git commit -m "a11y: add ARIA tab roles to history and season tab components"
```

---

### Task 2: Add prophylactic .gitignore entries

**Files:**
- Modify: `.gitignore`

**Step 1: Edit .gitignore**

Add these entries at the end of the file:

```gitignore
# OS system files
.DS_Store
Thumbs.db

# Security — never commit
*.key
*.pem
*.ppk
*.env.local
```

> `.env` is already in `.gitignore`. Don't add `dist/`, `.cache/`, or other build-tool entries — this project has no build step and adding them is speculative.

**Step 2: Verify**

```bash
git status
```

Confirm only `.gitignore` is modified, nothing new got untracked.

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add prophylactic .gitignore entries for keys and OS files"
```

---

### Task 3: Standardize `--maxw`, `--glass`, and `--font` CSS variables

**Files:**
- Modify: `index.html` (lines 23-35 `:root`, line 37 `.light`)
- Modify: `draft.html` (~line 20-25 `:root`)
- Modify: `trades.html` (~line 20-25 `:root`)
- Modify: `history.html` (~line 13-17 `:root`)
- Modify: `preseason.html` (line 21 `--glass`, line 26 `--font-main`, line 29 `--maxw`)
- Modify: `week1.html` (line 19 `--glass`, line 24 `--font-main`)

> Goal: every page defines `--glass`, `--font`, `--maxw` in `:root`. Standardize naming to `--font` (not `--font-main`). Pick one `--maxw` value or keep page-appropriate values — see note below.

**`--maxw` strategy:** Each page legitimately needs different widths (power-rankings is narrow column, preseason has wide tables). Do NOT force a single value. Instead, add `--maxw` only to pages that lack it, using the value closest to their existing inline `max-width`:

| Page | Current inline max-width | Add `--maxw` |
|------|-------------------------|--------------|
| `index.html` | 900px (hero), 1200px (container) | `1200px` |
| `draft.html` | 1200px (.container) | `1200px` |
| `trades.html` | 1100px (.container) | `1100px` |
| `week1.html` | varies | `900px` |

**Standard values:**
- `--glass: rgba(255,255,255,0.05);`
- `--font: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;`

**Step 1: Edit index.html `:root`**

Add `--glass`, `--font`, `--maxw` after `--border`:

```css
/* old */
    --border: rgba(255,255,255,0.07);
    --good: #16a34a;

/* new */
    --border: rgba(255,255,255,0.07);
    --glass: rgba(255,255,255,0.05);
    --font: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    --maxw: 1200px;
    --good: #16a34a;
```

Also add `--glass` to the `.light` block:

```css
/* old */
    --card:rgba(0,0,0,0.03); --glow-1:rgba(139,92,246,0.08);

/* new */
    --card:rgba(0,0,0,0.03); --glass:rgba(0,0,0,0.04); --glow-1:rgba(139,92,246,0.08);
```

And update `font-family` in `:root` to reference `--font`:

```css
/* old */
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;

/* new */
    font-family: var(--font);
```

**Step 2: Edit draft.html `:root`**

Add `--glass`, `--font`, `--maxw` to the `:root` block:

```css
/* old */
    --card:rgba(255,255,255,0.03); --border:rgba(255,255,255,0.07);

/* new */
    --card:rgba(255,255,255,0.03); --border:rgba(255,255,255,0.07);
    --glass:rgba(255,255,255,0.05); --font:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif; --maxw:1200px;
```

Replace inline `font-family:system-ui...` with `font-family:var(--font)` in `body` rule.

**Step 3: Edit trades.html `:root`**

Same pattern as draft.html, but `--maxw:1100px`.

Replace inline `font-family:system-ui...` with `font-family:var(--font)` in `body` rule.

**Step 4: Edit history.html `:root`**

Add `--font` (already has `--glass`):

```css
/* old */
  --border:rgba(255,255,255,0.07);

/* new */
  --border:rgba(255,255,255,0.07);
  --font:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
```

Replace inline `font-family:` with `font-family:var(--font)` in `body` rule.

**Step 5: Edit preseason.html — rename `--font-main` to `--font`**

```css
/* old */
  --font-main: system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;

/* new */
  --font: system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
```

Then find all references to `var(--font-main)` and replace with `var(--font)`.

**Step 6: Edit week1.html — rename `--font-main` to `--font`, add `--maxw`**

```css
/* old */
    --font-main: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;

/* new */
    --font: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    --maxw: 900px;
```

Then find all references to `var(--font-main)` and replace with `var(--font)`.

**Step 7: Verify**

- `grep -rn "\-\-glass" *.html` — should appear in all 8 pages (7 listed + power-rankings already has it)
- `grep -rn "\-\-font:" *.html` — should appear in all 8 pages
- `grep -rn "\-\-maxw" *.html` — should appear in all pages that define it
- `grep -rn "\-\-font-main" *.html` — should return 0 results (fully renamed)
- Open each page in browser — no visual regressions, fonts render correctly

**Step 8: Commit**

```bash
git add index.html draft.html trades.html history.html preseason.html week1.html
git commit -m "style: standardize --glass, --font, --maxw CSS variables across all pages"
```

---

### Task 4: Delete legacy nested directory

**Files:**
- Delete: `Jailyard-Dynasty-Power-Rankings-main/` (already in `.gitignore`, ~1 MB on disk)

**Step 1: Delete the directory**

```bash
rm -rf "Jailyard-Dynasty-Power-Rankings-main/"
```

**Step 2: Verify**

```bash
ls Jailyard-Dynasty-Power-Rankings-main/ 2>&1
# Expected: "No such file or directory"
git status
# Expected: clean (directory was gitignored, so no git change)
```

> No commit needed — directory was already gitignored and never tracked.

---

## Verification (after all 4 tasks)

1. Open each of the 8 pages in browser — no console errors, no visual regressions
2. history.html: click all 4 tabs, inspect `aria-selected` flipping, `role="tabpanel"` present
3. season.html: pick a week, click view tabs, same ARIA check
4. Run verification greps:
   - `grep -rn "role=\"tab\"" *.html` — should show history + season
   - `grep -rn "\-\-font-main" *.html` — should return 0 (fully migrated)
   - `grep -rn "\-\-glass" *.html` — should show all 8 pages
   - `grep -rn "\.key" .gitignore` — should show `*.key`
5. Confirm `Jailyard-Dynasty-Power-Rankings-main/` directory no longer exists

**Total: ~35 edits, 3 commits + 1 deletion, 8 files**

## Final Audit Scorecard (after all tasks)

After these 4 tasks, ALL 15 audit items will be resolved:
- High Priority #1-4: Done (previous session)
- Medium Priority #5-10: Done (previous session)
- Low Priority #11-15: Done (this plan)
