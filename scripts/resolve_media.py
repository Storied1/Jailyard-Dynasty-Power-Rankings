#!/usr/bin/env python
"""Resolve media slots in Jailyard content JSON via Giphy API.

Modes:
  --preview     Search Giphy for each slot, generate preview.html with 3 candidates
  --more ID     Fetch next 3 candidates for a specific slot
  --pick ID GID Write a Giphy pick to media_picks.json (never touches content JSON)
  --resolve     Produce final media_cache.json with resolved URLs

The content JSON is NEVER modified. Picks live in media_picks.json.
Resolved URLs live in media_cache.json. Both are gitignored.

Requires GIPHY_API_KEY in environment for --preview/--resolve/--more.
Falls back to existing media_cache.json for rendering if key is absent.

Dependencies: stdlib + requests
"""

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library required. Install with: pip install requests")
    sys.exit(2)

GIPHY_API_BASE = "https://api.giphy.com/v1/gifs"
CANDIDATES_PER_SLOT = 3
GIPHY_RATING = "pg-13"  # filter out explicit content


# ── Giphy API ────────────────────────────────────────────────────────

def get_api_key() -> str:
    """Read GIPHY_API_KEY from environment."""
    key = os.environ.get("GIPHY_API_KEY", "").strip()
    if not key:
        print("ERROR: GIPHY_API_KEY not set in environment.")
        print("  Set it with: $env:GIPHY_API_KEY='your_key_here'  (PowerShell)")
        print("  Or create a .env file and source it.")
        sys.exit(1)
    return key


def search_giphy(query: str, api_key: str, limit: int = 3, offset: int = 0) -> list[dict]:
    """Search Giphy and return simplified result list."""
    params = {
        "api_key": api_key,
        "q": query,
        "limit": limit,
        "offset": offset,
        "rating": GIPHY_RATING,
        "lang": "en",
    }
    url = f"{GIPHY_API_BASE}/search?{urlencode(params)}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for gif in data.get("data", []):
        images = gif.get("images", {})
        original = images.get("original", {})
        original_mp4 = images.get("original_mp4", {})
        still = images.get("original_still", {})
        fixed = images.get("fixed_width", {})

        # Prefer original_mp4, fall back to fixed_width mp4
        mp4_url = original_mp4.get("mp4", "") or fixed.get("mp4", "")

        results.append({
            "giphy_id": gif.get("id", ""),
            "title": gif.get("title", ""),
            "mp4_url": mp4_url,
            "gif_url": original.get("url", ""),
            "poster_url": still.get("url", ""),
            "width": int(original.get("width", 0) or 0),
            "height": int(original.get("height", 0) or 0),
            "rating": gif.get("rating", ""),
            "source_url": gif.get("url", ""),
        })

    return results


def fetch_giphy_by_id(giphy_id: str, api_key: str) -> dict:
    """Fetch a specific Giphy GIF by ID."""
    params = {"api_key": api_key}
    url = f"{GIPHY_API_BASE}/{giphy_id}?{urlencode(params)}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    gif = resp.json().get("data", {})

    images = gif.get("images", {})
    original = images.get("original", {})
    original_mp4 = images.get("original_mp4", {})
    still = images.get("original_still", {})
    fixed = images.get("fixed_width", {})

    mp4_url = original_mp4.get("mp4", "") or fixed.get("mp4", "")

    return {
        "giphy_id": gif.get("id", ""),
        "title": gif.get("title", ""),
        "mp4_url": mp4_url,
        "gif_url": original.get("url", ""),
        "poster_url": still.get("url", ""),
        "width": int(original.get("width", 0) or 0),
        "height": int(original.get("height", 0) or 0),
        "rating": gif.get("rating", ""),
        "source_url": gif.get("url", ""),
    }


# ── File I/O helpers ─────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    """Load JSON file, return empty dict if missing."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, data: dict) -> None:
    """Write JSON with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def content_dir(content_path: Path) -> Path:
    """Return the directory containing the content JSON."""
    return content_path.parent


# ── Core operations ──────────────────────────────────────────────────

def load_content_slots(content_path: Path) -> list[dict]:
    """Load media_slots from content JSON (read-only)."""
    content = load_json(content_path)
    slots = content.get("media_slots", [])
    if not slots:
        print("WARNING: No media_slots found in content JSON.")
    return slots


def cmd_preview(content_path: Path) -> None:
    """Search Giphy for each slot, generate preview.html with 3 candidates."""
    api_key = get_api_key()
    slots = load_content_slots(content_path)
    out_dir = content_dir(content_path)
    picks_path = out_dir / "media_picks.json"
    picks = load_json(picks_path)

    # State file for tracking offsets (for --more)
    state_path = out_dir / ".resolve_state.json"
    state = load_json(state_path)

    giphy_slots = [s for s in slots if s.get("source", {}).get("type") != "custom"]
    custom_slots = [s for s in slots if s.get("source", {}).get("type") == "custom"]

    if not giphy_slots and not custom_slots:
        print("No media slots to preview.")
        return

    all_candidates = {}

    for slot in giphy_slots:
        slot_id = slot["slot_id"]
        source = slot["source"]
        query = source.get("search_query", "")
        fallback = source.get("fallback_query", "")
        offset = state.get(slot_id, {}).get("offset", 0)

        print(f"  Searching Giphy for [{slot_id}]: \"{query}\" (offset={offset})")
        results = search_giphy(query, api_key, limit=CANDIDATES_PER_SLOT, offset=offset)

        # Use fallback if primary returned < 3 results
        if len(results) < CANDIDATES_PER_SLOT and fallback:
            print(f"    < {CANDIDATES_PER_SLOT} results, trying fallback: \"{fallback}\"")
            extra = search_giphy(fallback, api_key, limit=CANDIDATES_PER_SLOT - len(results))
            # Deduplicate by giphy_id
            seen = {r["giphy_id"] for r in results}
            for r in extra:
                if r["giphy_id"] not in seen:
                    results.append(r)
                    seen.add(r["giphy_id"])

        all_candidates[slot_id] = results[:CANDIDATES_PER_SLOT]

        # Save offset state for --more
        state.setdefault(slot_id, {})["offset"] = offset + len(results)

    save_json(state_path, state)

    # Generate preview.html
    preview_path = out_dir / "preview.html"
    html = _build_preview_html(slots, all_candidates, picks)
    preview_path.write_text(html, encoding="utf-8")

    print(f"\nPreview generated: {preview_path}")
    print(f"Slots: {len(giphy_slots)} Giphy + {len(custom_slots)} custom")

    # Open in browser
    try:
        webbrowser.open(preview_path.as_uri())
    except Exception:
        print(f"  Open manually: {preview_path}")


def cmd_more(content_path: Path, slot_id: str) -> None:
    """Fetch next 3 candidates for a specific slot."""
    api_key = get_api_key()
    slots = load_content_slots(content_path)
    out_dir = content_dir(content_path)

    slot = next((s for s in slots if s["slot_id"] == slot_id), None)
    if not slot:
        print(f"ERROR: Slot '{slot_id}' not found in content JSON.")
        sys.exit(1)

    if slot.get("source", {}).get("type") == "custom":
        print(f"ERROR: Slot '{slot_id}' is a custom slot, not Giphy.")
        sys.exit(1)

    state_path = out_dir / ".resolve_state.json"
    state = load_json(state_path)
    offset = state.get(slot_id, {}).get("offset", 0)

    source = slot["source"]
    query = source.get("search_query", "")

    print(f"Fetching more for [{slot_id}]: \"{query}\" (offset={offset})")
    results = search_giphy(query, api_key, limit=CANDIDATES_PER_SLOT, offset=offset)

    if not results:
        print("  No more results available.")
        return

    state.setdefault(slot_id, {})["offset"] = offset + len(results)
    save_json(state_path, state)

    print(f"  Found {len(results)} more candidates:")
    for i, r in enumerate(results, 1):
        print(f"    {i}. {r['giphy_id']}  {r['title']}")
        print(f"       Preview: {r['gif_url']}")

    # Regenerate preview with updated candidates
    print("\nRe-run --preview to update preview.html with these new candidates.")


def cmd_candidates_json(content_path: Path, slot_id: str) -> None:
    """Return JSON candidates for a slot to stdout. For agent/script use."""
    api_key = get_api_key()
    slots = load_content_slots(content_path)

    slot = next((s for s in slots if s["slot_id"] == slot_id), None)
    if not slot:
        print(json.dumps({"error": f"Slot '{slot_id}' not found"}))
        sys.exit(1)

    if slot.get("source", {}).get("type") == "custom":
        print(json.dumps({"error": f"Slot '{slot_id}' is custom, no Giphy candidates"}))
        sys.exit(1)

    source = slot["source"]
    primary_query = source.get("search_query", "")
    fallback_query = source.get("fallback_query", "")

    results = search_giphy(primary_query, api_key, limit=CANDIDATES_PER_SLOT)
    if len(results) < CANDIDATES_PER_SLOT and fallback_query:
        seen = {r["giphy_id"] for r in results}
        extra = search_giphy(fallback_query, api_key, limit=CANDIDATES_PER_SLOT)
        for r in extra:
            if r["giphy_id"] not in seen:
                results.append(r)
                seen.add(r["giphy_id"])

    output = {
        "slot_id": slot_id,
        "intent": slot.get("intent", ""),
        "alt_text": slot.get("alt_text", ""),
        "primary_query": primary_query,
        "fallback_query": fallback_query,
        "candidates": results[:CANDIDATES_PER_SLOT],
    }
    print(json.dumps(output, indent=2))


def cmd_pick(content_path: Path, slot_id: str, giphy_id: str) -> None:
    """Write a pick to media_picks.json. Never touches content JSON."""
    slots = load_content_slots(content_path)
    out_dir = content_dir(content_path)

    slot = next((s for s in slots if s["slot_id"] == slot_id), None)
    if not slot:
        print(f"ERROR: Slot '{slot_id}' not found in content JSON.")
        sys.exit(1)

    if slot.get("source", {}).get("type") == "custom":
        print(f"ERROR: Slot '{slot_id}' is a custom slot. No Giphy pick needed.")
        sys.exit(1)

    picks_path = out_dir / "media_picks.json"
    picks = load_json(picks_path)
    picks[slot_id] = giphy_id
    save_json(picks_path, picks)

    print(f"Picked {giphy_id} for slot [{slot_id}]")
    print(f"  Saved to: {picks_path}")


def cmd_resolve(content_path: Path) -> None:
    """Produce final media_cache.json with resolved URLs."""
    slots = load_content_slots(content_path)
    out_dir = content_dir(content_path)
    picks_path = out_dir / "media_picks.json"
    picks = load_json(picks_path)
    cache_path = out_dir / "media_cache.json"

    # Check if we need the API key (any unresolved giphy slots?)
    giphy_slots = [s for s in slots if s.get("source", {}).get("type") != "custom"]
    needs_api = False
    for slot in giphy_slots:
        sid = slot["slot_id"]
        if sid not in picks:
            needs_api = True  # need to auto-pick via search
            break
        # Even with a pick, we need to fetch its metadata
        needs_api = True

    api_key = None
    if needs_api:
        api_key = get_api_key()

    resolved_slots = {}

    for slot in slots:
        sid = slot["slot_id"]
        source = slot.get("source", {})
        stype = source.get("type", "giphy")

        if stype == "custom":
            resolved_slots[sid] = {
                "type": "custom",
                "local_path": source.get("local_path", ""),
                "alt_text": slot.get("alt_text", ""),
            }
            print(f"  [{sid}] custom -> {source.get('local_path', '?')}")
            continue

        # Giphy slot
        giphy_id = picks.get(sid)

        if giphy_id:
            # Fetch specific GIF metadata
            print(f"  [{sid}] resolving picked ID: {giphy_id}")
            result = fetch_giphy_by_id(giphy_id, api_key)
        else:
            # Auto-pick: search and take top result
            query = source.get("search_query", "")
            fallback = source.get("fallback_query", "")
            print(f"  [{sid}] no pick — auto-selecting from: \"{query}\"")

            results = search_giphy(query, api_key, limit=1)
            if not results and fallback:
                print(f"    Trying fallback: \"{fallback}\"")
                results = search_giphy(fallback, api_key, limit=1)

            if not results:
                print(f"    WARNING: No Giphy results for [{sid}]. Skipping.")
                continue

            result = results[0]
            print(f"    Auto-picked: {result['giphy_id']} — {result['title']}")

        resolved_slots[sid] = {
            "giphy_id": result["giphy_id"],
            "mp4_url": result["mp4_url"],
            "poster_url": result["poster_url"],
            "width": result["width"],
            "height": result["height"],
            "alt_text": slot.get("alt_text", ""),
            "rating": result["rating"],
            "source_url": result.get("source_url", ""),
        }

    cache = {
        "resolved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": "Powered by GIPHY",
        "slots": resolved_slots,
    }

    save_json(cache_path, cache)
    print(f"\nCache written: {cache_path}")
    print(f"  {len(resolved_slots)} slots resolved ({len([s for s in resolved_slots.values() if s.get('type') != 'custom'])} Giphy, {len([s for s in resolved_slots.values() if s.get('type') == 'custom'])} custom)")


# ── Preview HTML generator ───────────────────────────────────────────

def _build_preview_html(slots: list[dict], candidates: dict, picks: dict) -> str:
    """Generate a self-contained preview HTML page."""
    giphy_slots = [s for s in slots if s.get("source", {}).get("type") != "custom"]
    custom_slots = [s for s in slots if s.get("source", {}).get("type") == "custom"]

    slot_sections = []

    for slot in giphy_slots:
        sid = slot["slot_id"]
        intent = slot.get("intent", "")
        alt = slot.get("alt_text", "")
        source = slot.get("source", {})
        query = source.get("search_query", "")
        picked_id = picks.get(sid, "")
        cands = candidates.get(sid, [])

        cards = []
        for i, c in enumerate(cands, 1):
            is_picked = c["giphy_id"] == picked_id
            border = "3px solid #a855f7" if is_picked else "1px solid #333"
            badge = '<span style="color:#a855f7;font-weight:700;">PICKED</span>' if is_picked else ""
            cards.append(f"""
            <div style="flex:1;min-width:200px;max-width:300px;border:{border};border-radius:12px;padding:8px;background:#1a1a2e;">
              <video autoplay loop muted playsinline style="width:100%;border-radius:8px;"
                     poster="{c.get('poster_url', '')}">
                <source src="{c['mp4_url']}" type="video/mp4">
              </video>
              <div style="margin-top:6px;font-size:13px;">
                <div style="color:#ccc;">{i}. {c.get('title', 'Untitled')[:50]}</div>
                <div style="color:#888;font-family:monospace;font-size:11px;">{c['giphy_id']}</div>
                <div style="color:#888;font-size:11px;">{c['width']}x{c['height']} &middot; {c['rating']}</div>
                {badge}
              </div>
            </div>""")

        no_results = "" if cands else '<p style="color:#f87171;">No candidates found. Try --more or different search terms.</p>'

        slot_sections.append(f"""
        <div style="margin-bottom:2rem;padding:1.5rem;background:#0f0f23;border-radius:16px;border:1px solid #333;">
          <div style="margin-bottom:1rem;">
            <span style="font-size:1.1rem;font-weight:700;color:#a855f7;">{sid}</span>
            <span style="color:#888;margin-left:1rem;">Giphy</span>
          </div>
          <div style="color:#ccc;margin-bottom:0.5rem;font-style:italic;">"{intent}"</div>
          <div style="color:#666;font-size:0.85rem;margin-bottom:1rem;">Query: {query}</div>
          <div style="display:flex;gap:12px;flex-wrap:wrap;">
            {''.join(cards)}
          </div>
          {no_results}
          <div style="margin-top:1rem;font-size:12px;color:#555;">
            Pick command: <code style="color:#a855f7;">python scripts/resolve_media.py --content {'{content_path}'} --pick {sid} &lt;GIPHY_ID&gt;</code>
          </div>
        </div>""")

    for slot in custom_slots:
        sid = slot["slot_id"]
        intent = slot.get("intent", "")
        local_path = slot.get("source", {}).get("local_path", "")
        slot_sections.append(f"""
        <div style="margin-bottom:2rem;padding:1.5rem;background:#0f0f23;border-radius:16px;border:1px solid #555;">
          <div style="margin-bottom:1rem;">
            <span style="font-size:1.1rem;font-weight:700;color:#ec4899;">{sid}</span>
            <span style="color:#888;margin-left:1rem;">Custom (Veo3/local)</span>
          </div>
          <div style="color:#ccc;margin-bottom:0.5rem;font-style:italic;">"{intent}"</div>
          <div style="color:#666;font-size:0.85rem;">Source: {local_path}</div>
          <div style="margin-top:0.5rem;color:#555;font-size:0.85rem;">No Giphy candidates — uses local file directly.</div>
        </div>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Media Slot Preview — The Jailyard</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0a0a1a; color: #e0e0e0; padding: 2rem; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
    .subtitle {{ color: #888; margin-bottom: 2rem; font-size: 0.9rem; }}
    code {{ background: #1a1a2e; padding: 2px 6px; border-radius: 4px; }}
    footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #333;
              color: #555; font-size: 0.8rem; text-align: center; }}
  </style>
</head>
<body>
  <h1>Media Slot Preview</h1>
  <div class="subtitle">{len(giphy_slots)} Giphy slots &middot; {len(custom_slots)} custom slots &middot; {CANDIDATES_PER_SLOT} candidates each</div>
  {''.join(slot_sections)}
  <footer>
    Powered by GIPHY &middot; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}
  </footer>
</body>
</html>
"""


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Resolve media slots in Jailyard content JSON via Giphy API."
    )
    parser.add_argument(
        "--content", required=True, type=Path,
        help="Path to content JSON (e.g. content/preseason-2026/preseason_content.json)"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview", action="store_true", help="Generate preview.html with 3 candidates per slot")
    group.add_argument("--more", metavar="SLOT_ID", help="Fetch next 3 candidates for a specific slot")
    group.add_argument("--pick", nargs=2, metavar=("SLOT_ID", "GIPHY_ID"), help="Set a Giphy pick for a slot")
    group.add_argument("--resolve", action="store_true", help="Produce final media_cache.json")
    group.add_argument(
        "--candidates-json", metavar="SLOT_ID",
        help="Return JSON candidates for a slot to stdout (for agent use)"
    )

    args = parser.parse_args()

    if not args.content.exists():
        print(f"ERROR: Content file not found: {args.content}")
        sys.exit(2)

    if args.preview:
        cmd_preview(args.content)
    elif args.more:
        cmd_more(args.content, args.more)
    elif args.pick:
        cmd_pick(args.content, args.pick[0], args.pick[1])
    elif args.resolve:
        cmd_resolve(args.content)
    elif args.candidates_json:
        cmd_candidates_json(args.content, args.candidates_json)


if __name__ == "__main__":
    main()
