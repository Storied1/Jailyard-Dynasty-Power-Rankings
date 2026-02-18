# Preseason Media & Data Verification Design

**Date:** 2026-02-17
**Status:** Approved for implementation

## Architecture

Two parallel tracks feeding into a polished, accurate, media-rich site:

1. **Media-Rich Content Pipeline** — Writer outputs `media_slots` in content JSON with `{{media:slot_id}}` anchor tokens in text. Python resolver calls Giphy API at build time. Renderer replaces anchors with `<video>` elements. Final HTML is fully static — no client-side API calls.

2. **Data Verification** — Draft board ordering fix (immediate), then generalized `/verify` system (deferred).

### Constraints

- Static site stays dependency-free at runtime: no client-side API calls, no external JS
- Giphy resolution happens only during local build step; final HTML has resolved CDN URLs
- Pages fetch media from Giphy CDN at view-time (lazy-loaded), but no API calls from browser
- API keys never committed; build reads from env vars, falls back to cached mappings

## Media Slots Schema

In content JSON (writer-owned, immutable):

```json
{
  "media_slots": [
    {
      "slot_id": "preseason-2026-essay-opener",
      "intent": "The offseason was pure chaos",
      "source": {
        "type": "giphy",
        "search_query": "this is fine everything chaos",
        "fallback_query": "dumpster fire"
      },
      "alt_text": "This is fine - dog in burning room"
    },
    {
      "slot_id": "preseason-2026-hero",
      "intent": "Cinematic league intro",
      "source": {
        "type": "custom",
        "local_path": "media/custom/preseason-2026-hero.mp4"
      },
      "alt_text": "The Jailyard 2026"
    }
  ]
}
```

Placement defined by `{{media:slot_id}}` tokens inline in essay/blurb text.

## Media Cache Schema

Output of `resolve_media.py` (`media_cache.json`, gitignored):

```json
{
  "resolved_at": "2026-02-17T12:00:00Z",
  "attribution": "Powered by GIPHY",
  "slots": {
    "preseason-2026-essay-opener": {
      "giphy_id": "QMHoU66sBXqqLqYvGO",
      "mp4_url": "https://media.giphy.com/media/.../giphy.mp4",
      "poster_url": "https://media.giphy.com/media/.../giphy_s.gif",
      "width": 480,
      "height": 360,
      "alt_text": "This is fine - dog in burning room",
      "rating": "g"
    }
  }
}
```

## File Plan

```
NEW:
  scripts/resolve_media.py
  scripts/verify_draft_order.py
  .env.example
  media/custom/
  docs/plans/

GENERATED (gitignored):
  .env
  **/media_cache.json
  **/media_picks.json
  **/preview.html
```

## Build Commands

```powershell
# Preview GIF candidates (3 per slot)
python scripts/resolve_media.py --content <path> --preview

# Pick a specific GIF for a slot
python scripts/resolve_media.py --content <path> --pick <slot_id> <giphy_id>

# Fetch more candidates for one slot
python scripts/resolve_media.py --content <path> --more <slot_id>

# Lock final selections into media_cache.json
python scripts/resolve_media.py --content <path> --resolve
```

## HTML Output

```html
<figure class="media-slot" id="gif-{slot_id}">
  <video loop muted playsinline
         width="{actual}" height="{actual}"
         poster="{poster_url}" preload="none">
    <source data-src="{mp4_url}" type="video/mp4">
  </video>
</figure>
```

- IntersectionObserver lazy-loads (copies `data-src` to `src`, calls `.load()`)
- `prefers-reduced-motion`: JS removes autoplay, shows poster, adds click-to-play overlay
- Mobile: `max-width: 100%; height: auto`
- Attribution: "Powered by GIPHY" in footer
- Theme: `border-radius: 12px; border: 1px solid var(--border)`

## Commit Plan

1. Draft board ordering fix + `verify_draft_order.py` regression script
2. Media resolver (`resolve_media.py`) — preview + cache + picks
3. Renderer embeds — reduced-motion + responsive video + attribution
4. Preseason-2026 longform page end-to-end

## Deferred

- Ranking blurb reaction GIFs (top 3 + bottom 3)
- Confessional GIFs
- Team-specific GIF library
- Section divider GIFs
- Generalized `/verify` slash command
- Veo3 custom content automation
- Candidate history in cache
