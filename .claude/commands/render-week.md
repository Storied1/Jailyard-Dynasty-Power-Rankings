# Render an Edition (week ${WEEK})

Turn approved `content/weeks/week${WEEK}_content.json` into
`week${WEEK}.html`, a self-contained page in the site's design system.

## Rules

1. Match the site chrome: glassmorphic dark theme with light toggle, `:root`
   CSS variables (`--bg --fg --muted --accent --accent2 --card --border
--glass --good --bad --warn`), sticky nav from `config.js`, scroll
   animations (IntersectionObserver + `.visible`), View Transitions meta,
   back-to-top button, scroll progress bar. `season.html` is a live example of the chrome.
2. Everything inline: all CSS in a `<style>` block, all JS inline (config.js
   is the only external file), all content baked into inline JS objects. No
   CDN, no frameworks, no client-side API calls.
3. Render what the content JSON contains: rankings always; every other
   section the edition earned, in the order the JSON gives them. Design each
   section's layout within the design system.
4. No repeating animations (no infinite shimmer/pulse/glow; spinners and
   tickers are fine); Canvas handles `devicePixelRatio`; mobile responsive.
5. Media: replace `{{media:slot_id}}` tokens from `media_cache.json` slots
   (lazy-loaded muted video figures, reduced-motion click-to-play, GIPHY
   attribution in the footer when Giphy media is present); drop unresolved
   tokens silently.
6. Add the page to `config.js` `pages` (group "columns") and verify the nav.

## After rendering

Load the page in a browser: zero console errors, all sections render, theme
toggle works. HTML is prettier-ignored; keep it compact.
