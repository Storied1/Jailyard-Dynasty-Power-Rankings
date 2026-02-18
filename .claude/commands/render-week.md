# The Jailyard HTML Renderer

You are the renderer for The Jailyard weekly columns. Your job is to take approved content from `content/weeks/week${WEEK}_content.json` and produce a complete HTML page following the `week1.html` template pattern.

## Your Inputs

Read these files:
1. `content/weeks/week${WEEK}_content.json` — the approved content to render
2. `week1.html` — the template (copy the FULL HTML/CSS/JS structure)
3. `config.js` — for nav links and branding
4. `content/weeks/media_cache.json` — resolved media URLs (if exists, for `{{media:*}}` tokens)

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

### 7. Media Embeds (GIFs / Video)

Content JSON may contain `{{media:slot_id}}` tokens inline in essay, blurb, or other text fields. These are anchor points for embedded media (Giphy GIFs as MP4 video, or custom video clips).

**How it works:**
1. Read `media_cache.json` from the content directory (sibling to the content JSON)
2. For each `{{media:slot_id}}` token found in any text field, look up the slot in `media_cache.json.slots`
3. Replace the token with the appropriate `<figure>` HTML (see below)
4. If `media_cache.json` doesn't exist or a slot isn't found, **silently drop the token** — render nothing, no broken UI

**For Giphy slots** (slot has `giphy_id`):
```html
<figure class="media-slot" id="media-{slot_id}">
  <video loop muted playsinline
         width="{width}" height="{height}"
         poster="{poster_url}" preload="none"
         aria-label="{alt_text}">
    <source data-src="{mp4_url}" type="video/mp4">
  </video>
</figure>
```

**For custom video slots** (slot has `type: "custom"`):
```html
<figure class="media-slot media-slot--hero" id="media-{slot_id}">
  <video controls muted playsinline preload="none"
         poster=""
         aria-label="{alt_text}">
    <source data-src="{local_path}" type="video/mp4">
  </video>
</figure>
```

**Add this CSS** to the `<style>` block:
```css
/* ── Media Slots (GIF/video embeds) ── */
.media-slot {
  margin: 1.5rem auto;
  max-width: 480px;
  text-align: center;
}
.media-slot video {
  max-width: 100%;
  height: auto;
  border-radius: 12px;
  border: 1px solid var(--border);
  display: block;
  background: var(--card);
}
.media-slot--hero {
  max-width: 100%;
}
.media-slot--hero video {
  width: 100%;
  border-radius: 16px;
}
.media-slot .play-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  cursor: pointer;
  background: rgba(0,0,0,0.3);
  border-radius: 12px;
  opacity: 0;
  transition: opacity 0.2s;
}
.media-slot .play-overlay.active {
  opacity: 1;
}
.media-slot .play-overlay svg {
  width: 48px;
  height: 48px;
  fill: #fff;
  filter: drop-shadow(0 2px 8px rgba(0,0,0,0.5));
}
.media-slot figcaption {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 0.4rem;
}
```

**Add this JS** at the end of the main `<script>` block (after the existing IntersectionObserver code):
```javascript
// ── Media slot lazy loading + reduced-motion ──
(function(){
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const mediaSlots = document.querySelectorAll('.media-slot');
  if (!mediaSlots.length) return;

  const playSvg = '<svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>';

  function applyMotionPref(video, overlay) {
    if (prefersReducedMotion.matches) {
      video.removeAttribute('autoplay');
      video.pause();
      video.currentTime = 0;
      if (overlay) overlay.classList.add('active');
    } else {
      if (video.src || video.querySelector('source[src]')) {
        video.play().catch(function(){});
      }
      if (overlay) overlay.classList.remove('active');
    }
  }

  const mediaObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) {
      if (!e.isIntersecting) return;
      const video = e.target.querySelector('video');
      if (!video) return;
      const source = video.querySelector('source[data-src]');
      if (source && !source.src) {
        source.src = source.dataset.src;
        source.removeAttribute('data-src');
        video.load();
        video.addEventListener('loadeddata', function() {
          const overlay = e.target.querySelector('.play-overlay');
          if (!prefersReducedMotion.matches) {
            video.play().catch(function(){});
          } else if (overlay) {
            overlay.classList.add('active');
          }
        }, { once: true });
      }
      mediaObserver.unobserve(e.target);
    });
  }, { rootMargin: '200px' });

  mediaSlots.forEach(function(slot) {
    const video = slot.querySelector('video');
    if (!video) return;

    // Build click-to-play overlay for reduced-motion
    slot.style.position = 'relative';
    const overlay = document.createElement('div');
    overlay.className = 'play-overlay';
    overlay.innerHTML = playSvg;
    overlay.addEventListener('click', function() {
      video.play().catch(function(){});
      overlay.classList.remove('active');
    });
    slot.appendChild(overlay);

    mediaObserver.observe(slot);
  });

  // Listen for motion preference changes
  prefersReducedMotion.addEventListener('change', function() {
    mediaSlots.forEach(function(slot) {
      const video = slot.querySelector('video');
      const overlay = slot.querySelector('.play-overlay');
      if (video) applyMotionPref(video, overlay);
    });
  });
})();
```

**Add GIPHY attribution** in the footer, right before the copyright line:
```html
<div style="font-size:.7rem;color:var(--muted);margin-bottom:.4rem;">
  GIFs <a href="https://giphy.com" style="color:var(--muted);text-decoration:underline;">Powered by GIPHY</a>
</div>
```

Only include the attribution line if the page actually has Giphy media slots.

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
12. **Media tokens** — replace `{{media:*}}` with `<figure>` elements from `media_cache.json`; silently drop unresolved tokens
13. **No client-side API calls** — all media URLs must be resolved CDN URLs baked into the HTML
14. **GIPHY attribution** — if any Giphy media is embedded, include "Powered by GIPHY" in footer

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
