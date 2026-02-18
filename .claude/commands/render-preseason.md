# The Jailyard Preseason Renderer

You are the renderer for The Jailyard preseason preview articles. Your job is to take approved content from `content/preseason-${YEAR}/preseason_content.json` and produce a complete long-form HTML page.

## Your Inputs

Read these files:
1. `content/preseason-${YEAR}/preseason_content.json` — the approved content (essay, media_slots, rankings)
2. `content/preseason-${YEAR}/media_cache.json` — resolved media URLs (GIF/video CDN links)
3. `week1.html` — template reference for CSS variables, theme toggle, nav patterns, scroll animations
4. `preseason.html` — reference for preseason-specific styling and team card patterns
5. `config.js` — for nav links and branding
6. `content/team-profiles.json` — team data for ranking cards

## What You Produce

### 1. The Preseason Page: `preseason-${YEAR}.html`

A complete, self-contained long-form article page. This is NOT the data-heavy rankings page (that's `preseason.html`). This is a narrative magazine-style preview.

**Page structure:**
```
Hero (full-width, cinematic — may include custom video)
└─ Essay (long-form narrative with embedded media)
└─ Power Rankings (12 team cards with blurbs)
└─ Footer (nav + GIPHY attribution if applicable)
```

### 2. Essay Section

Render the `essay` field from the content JSON. The essay text contains `{{media:slot_id}}` anchor tokens that must be replaced with media embeds.

**Token replacement rules:**
1. Read `media_cache.json` from `content/preseason-${YEAR}/`
2. For each `{{media:slot_id}}` token in the essay text, look up the slot in `media_cache.json.slots`
3. Replace with the appropriate `<figure>` element (see Media Embed Patterns below)
4. If `media_cache.json` doesn't exist or a slot isn't found, silently drop the token

**Split the essay into paragraphs** at `\n\n` boundaries. Wrap each paragraph in `<p>` tags. The `{{media:*}}` tokens appear between paragraphs — render them as standalone `<figure>` elements between `<p>` blocks.

### 3. Hero Section

If the content JSON has a media slot with `"type": "custom"` (e.g., a Veo3 hero clip), render it as a full-width hero video:

```html
<header class="hero">
  <div class="hero__layer layer-stars" data-speed="0.2"></div>
  <div class="hero__layer layer-grid" data-speed="0.05"></div>
  <div class="hero__content">
    <h1>The Jailyard ${YEAR} Preview</h1>
    <p class="hero__sub">{subtitle from content}</p>
  </div>
</header>
```

If there's a hero video slot, add the video inside `hero__content` with class `media-slot media-slot--hero`.

### 4. Rankings Section

Render each team from the `rankings` array as a card:

```html
<article class="card" id="preseason-${YEAR}-rankings">
  <h3>${YEAR} Preseason Power Rankings</h3>
  <div class="ranking-entry" ...>
    <div class="rank-badge">#${rank}</div>
    <div>
      <h4>${team_name}</h4>
      <p>${blurb}</p>
    </div>
  </div>
  <!-- ... 12 entries -->
</article>
```

Use the same `.ranking-entry` CSS from render-week.md.

## Media Embed Patterns

These are identical to the patterns in `render-week.md` Section 7. Include them exactly.

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
         aria-label="{alt_text}">
    <source data-src="{local_path}" type="video/mp4">
  </video>
</figure>
```

**Required CSS** (add to `<style>` block):
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

**Required JS** (add at end of main `<script>` block):
```javascript
// ── Media slot lazy loading + reduced-motion ──
(function(){
  var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var mediaSlots = document.querySelectorAll('.media-slot');
  if (!mediaSlots.length) return;

  var playSvg = '<svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>';

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

  var mediaObserver = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) {
      if (!e.isIntersecting) return;
      var video = e.target.querySelector('video');
      if (!video) return;
      var source = video.querySelector('source[data-src]');
      if (source && !source.src) {
        source.src = source.dataset.src;
        source.removeAttribute('data-src');
        video.load();
        video.addEventListener('loadeddata', function() {
          var overlay = e.target.querySelector('.play-overlay');
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
    var video = slot.querySelector('video');
    if (!video) return;

    // Build click-to-play overlay for reduced-motion
    slot.style.position = 'relative';
    var overlay = document.createElement('div');
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
      var video = slot.querySelector('video');
      var overlay = slot.querySelector('.play-overlay');
      if (video) applyMotionPref(video, overlay);
    });
  });
})();
```

## GIPHY Attribution

If any Giphy media slots are embedded, add this in the footer before the copyright line:
```html
<div style="font-size:.7rem;color:var(--muted);margin-bottom:.4rem;">
  GIFs <a href="https://giphy.com" style="color:var(--muted);text-decoration:underline;">Powered by GIPHY</a>
</div>
```

## Critical Rules

1. **ALL CSS must be inline** in a `<style>` block — no external stylesheets
2. **ALL JS must be inline** in `<script>` blocks (except config.js)
3. **Match the exact color scheme** — use `:root` CSS variables from week1.html
4. **Support light/dark theme toggle**
5. **Mobile responsive** — `@media (max-width:768px)` breakpoints
6. **Scroll animations** — IntersectionObserver on `.fade-in` elements
7. **Media tokens** — replace `{{media:*}}` with `<figure>` elements from `media_cache.json`; silently drop unresolved tokens
8. **No client-side API calls** — all media URLs must be resolved CDN URLs baked into the HTML
9. **GIPHY attribution** — include "Powered by GIPHY" in footer if any Giphy media is used
10. **View Transitions API** — include the meta tag and CSS
11. **Back-to-top button + scroll progress bar**

## After Rendering

1. Verify the HTML file is valid (no unclosed tags)
2. Confirm config.js has the new page in its `pages` array
3. Confirm all `{{media:*}}` tokens have been replaced (none remain in output HTML)
4. Print a summary: file size, media slots embedded, config updated

## Usage
```
/render-preseason 2026
```
The argument is the season year to render.
