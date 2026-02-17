# The Jailyard HTML Renderer

You are the renderer for The Jailyard weekly columns. Your job is to take approved content from `content/weeks/week${WEEK}_content.json` and produce a complete HTML page following the `week1.html` template pattern.

## Your Inputs

Read these files:
1. `content/weeks/week${WEEK}_content.json` — the approved content to render
2. `week1.html` — the template (copy the FULL HTML/CSS/JS structure)
3. `config.js` — for nav links and branding

## What You Produce

### 1. The Week Page: `week${WEEK}.html`

Create a complete, self-contained HTML file that:

**Matches the week1.html template exactly for:**
- All CSS (`:root` variables, glassmorphic theme, responsive breakpoints)
- Hero section with parallax layers
- Sticky navigation with hamburger menu
- Section layout (essay → mailbag → bits → picks)
- Matchup cards with win probability bars
- Special picks strip
- Sidebar with picks ledger
- Footer with config-driven nav
- Scroll animations (Intersection Observer)
- View Transitions API
- Back-to-top button
- Scroll progress bar
- Theme toggle (light/dark)

**Updates from the content JSON:**
- Hero title: "The Jailyard Week ${WEEK} Column"
- Hero subtitle: specific to this week's narrative
- `week${WEEK}Essay` — the cold open essay
- `week${WEEK}Mailbag` — array of {q, a} objects
- `week${WEEK}Bits` — the bits text
- `week${WEEK}Matches` — array of matchup pick objects
- `underdogLock`, `stayAway`, `teaser` — special picks

**Adds NEW sections not in week1.html:**
- Power Rankings section (after essay, before mailbag)
- Confessionals section (after power rankings)

### 2. Power Rankings Section

Add a new section between the essay and mailbag:

```html
<article class="card" id="week${WEEK}-rankings">
  <h3>Power Rankings</h3>
  <!-- 12 team cards, each with rank, movement arrow, blurb -->
</article>
```

Each ranking entry should render as:
```html
<div class="ranking-entry" style="...">
  <div class="rank-badge">#${rank}</div>
  <div class="rank-movement ${up|down|steady}">↑2 / ↓1 / —</div>
  <div>
    <h4>${team_name} <span class="rank-record">(${record})</span></h4>
    <p>${blurb}</p>
  </div>
</div>
```

Add these CSS rules to the `<style>` block:
```css
.ranking-entry {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  padding: 1rem 0;
  border-bottom: 1px solid var(--border);
}
.ranking-entry:last-child { border-bottom: none; }
.rank-badge {
  background: var(--accent);
  color: #fff;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: .85rem;
  flex-shrink: 0;
}
.rank-movement {
  font-size: .8rem;
  font-weight: 600;
  min-width: 30px;
  text-align: center;
  flex-shrink: 0;
}
.rank-movement.up { color: var(--good); }
.rank-movement.down { color: var(--bad); }
.rank-movement.steady { color: var(--muted); }
.rank-record { color: var(--muted); font-weight: 400; font-size: .9rem; }
```

### 3. Confessionals Section

Add after power rankings:
```html
<article class="card" id="week${WEEK}-confessionals">
  <h3>Confessionals</h3>
  <!-- Each confessional as a blockquote-style card -->
</article>
```

Style confessionals as:
```css
.confessional {
  background: rgba(139, 92, 246, 0.06);
  border-left: 3px solid var(--accent);
  padding: .8rem 1.2rem;
  margin-bottom: 1rem;
  border-radius: 0 8px 8px 0;
}
.confessional h4 { margin: 0 0 .4rem; font-size: .95rem; }
.confessional p { margin: 0; color: var(--muted); font-style: italic; }
```

### 4. Update Sidebar Ledger

Update the sidebar to show cumulative picks record:
- If this is Week 1: "Overall record: 0-0" (fresh start)
- If later weeks: compute from previous weeks' pick results

### 5. Update Navigation

Add a nav link for this week in:
- The sticky nav bar
- The footer nav

### 6. Update `config.js`

Add the new week page to the `pages` array in `config.js`:
```javascript
{ label: 'Week ${WEEK}', href: 'week${WEEK}.html' },
```

## Critical Rules

1. **ALL CSS must be inline** in a `<style>` block — no external stylesheets
2. **ALL JS must be inline** in `<script>` blocks (except config.js)
3. **ALL data must be in JS objects** — no external JSON loading
4. **Match the exact color scheme** — use the CSS variables from `:root`
5. **Handle devicePixelRatio** for any Canvas elements
6. **Support light/dark theme toggle**
7. **Mobile responsive** — hamburger menu, responsive matchup cards
8. **View Transitions API** — include the meta tag and CSS
9. **Scroll animations** — Intersection Observer on `.fade-in` and `.matchup-card`
10. **Back-to-top button** — show after 500px scroll
11. **Scroll progress bar** — at top of page

## Render the Rankings Data

Convert the `rankings` array from the content JSON into inline JS objects:
```javascript
const week${WEEK}Rankings = [
  { rank: 1, prevRank: 3, movement: 2, teamName: '...', record: '...', blurb: '...' },
  // ... 12 entries
];
```

Then render with a function similar to `renderWeek1()` in week1.html.

## After Rendering

1. Verify the HTML file is valid (no unclosed tags)
2. Confirm config.js has been updated with the new page
3. Print a summary: file size, sections rendered, config updated

## Usage
```
/render-week 3
```
The argument is the week number to render.
