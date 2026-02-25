#!/usr/bin/env python
"""Split parsed_messages.json into monthly chunk files for MAP phase processing.

Deterministic, stdlib only. No API calls.

Reads:  chat/parsed_messages.json
        content/chat/name-map.json
        content/chat/fingerprints.json
Writes: content/chat/.map_cache/YYYY-MM_raw.json (one per month)

Each chunk file contains:
  - identity_context: name-map for all 12 members
  - fingerprint_summary: behavioral stats per member
  - month: "YYYY-MM"
  - message_count: int
  - messages: list of message dicts (sender, text, timestamp_utc, media, etc.)
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PARSED_MESSAGES = REPO_ROOT / "chat" / "parsed_messages.json"
NAME_MAP_PATH = REPO_ROOT / "content" / "chat" / "name-map.json"
FINGERPRINTS_PATH = REPO_ROOT / "content" / "chat" / "fingerprints.json"
MAP_CACHE_DIR = REPO_ROOT / "content" / "chat" / ".map_cache"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    # Load parsed messages
    if not PARSED_MESSAGES.exists():
        print(f"ERROR: {PARSED_MESSAGES} not found. Run parse_whatsapp.py first.")
        sys.exit(1)

    raw = load_json(PARSED_MESSAGES)
    messages = raw.get("messages", raw) if isinstance(raw, dict) else raw
    print(f"Loaded {len(messages):,} messages")

    # Load identity context
    name_map = load_json(NAME_MAP_PATH) if NAME_MAP_PATH.exists() else {}
    print(f"Name map: {len(name_map)} members")

    # Load fingerprints (summarize for prompt inclusion)
    fingerprints = {}
    if FINGERPRINTS_PATH.exists():
        fp_data = load_json(FINGERPRINTS_PATH)
        members = fp_data.get("members", fp_data)
        # Create compact summary per member
        for member, stats in members.items():
            vol = stats.get("volume", {})
            timing = stats.get("timing", {})
            style = stats.get("style", {})
            fingerprints[member] = {
                "total_messages": vol.get("total_messages", 0),
                "avg_length_chars": vol.get("avg_length_chars", 0),
                "peak_hour": timing.get("peak_hour", None),
                "late_night_pct": timing.get("late_night_pct", 0),
                "top_emojis": [e["emoji"] for e in style.get("emoji_top_10", [])[:5]],
                "question_pct": style.get("question_pct", 0),
                "caps_pct": style.get("caps_pct", 0),
            }
        print(f"Fingerprints: {len(fingerprints)} members")

    # Group messages by month
    buckets = defaultdict(list)
    for msg in messages:
        ts = msg.get("timestamp_utc", "")
        if ts:
            month_key = ts[:7]  # YYYY-MM
            buckets[month_key].append(msg)

    sorted_months = sorted(buckets.keys())
    print(f"Found {len(sorted_months)} months: {sorted_months[0]} to {sorted_months[-1]}")

    # Write each month's chunk
    MAP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for month in sorted_months:
        msgs = buckets[month]
        chunk = {
            "identity_context": name_map,
            "fingerprint_summary": fingerprints,
            "month": month,
            "message_count": len(msgs),
            "messages": msgs,
        }
        out_path = MAP_CACHE_DIR / f"{month}_raw.json"
        save_json(out_path, chunk)
        print(f"  {month}: {len(msgs):,} messages -> {out_path.name}")

    print(f"\nDone. {len(sorted_months)} chunk files written to {MAP_CACHE_DIR.relative_to(REPO_ROOT)}")

    # Print volume tiers for planning
    print("\n-- Volume Tiers --")
    by_size = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)
    for month, msgs in by_size:
        tier = "HEAVY" if len(msgs) > 1400 else "MEDIUM" if len(msgs) > 600 else "LIGHT"
        print(f"  {month}: {len(msgs):>5,} messages  [{tier}]")


if __name__ == "__main__":
    main()
