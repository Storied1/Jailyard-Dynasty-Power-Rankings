#!/usr/bin/env python
"""AI-powered map-reduce analysis of Jailyard Dynasty WhatsApp chat.

Takes parsed_messages.json (from Phase 1 parser) and produces deep analytics
about the league's WhatsApp group chat using Claude API calls.

Map-Reduce Strategy:
  MAP   — Process chat month-by-month (~29 chunks, Sept 2023 → Feb 2026).
           Each monthly chunk → partial persona/arcs/relationships/consensus data.
  REDUCE — Merge all partial outputs → final analytics files.

Outputs (all under content/chat/):
  league-memory.json          — culture, running jokes, greatest moments, lexicon
  personas/<slug>.md          — 12 member profiles
  arcs.json                   — narrative plotlines
  predictions.json            — receipts ledger with credibility index
  relationships.json          — social graph
  consensus.json              — group opinion tracker

Usage:
  python scripts/analyze_chat.py                    # full analysis
  python scripts/analyze_chat.py --month 2024-03    # single month (debug)
  python scripts/analyze_chat.py --map-only          # MAP phase only
  python scripts/analyze_chat.py --reduce-only       # REDUCE from cached map outputs
  python scripts/analyze_chat.py --skip-personas     # skip persona generation
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package required. Install with: pip install anthropic")
    sys.exit(1)

# ── Paths ───────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
CHAT_DIR = REPO_ROOT / "content" / "chat"
PARSED_MESSAGES = REPO_ROOT / "chat" / "parsed_messages.json"  # lives in chat/, not content/chat/
NAME_MAP_PATH = CHAT_DIR / "name-map.json"
MAP_CACHE_DIR = CHAT_DIR / ".map_cache"
PERSONAS_DIR = CHAT_DIR / "personas"

FINGERPRINTS_PATH = CHAT_DIR / "fingerprints.json"
MEDIA_CATALOG_PATH = CHAT_DIR / "media-catalog.json"

# Output files
OUT_LEAGUE_MEMORY = CHAT_DIR / "league-memory.json"
OUT_ARCS = CHAT_DIR / "arcs.json"
OUT_PREDICTIONS = CHAT_DIR / "predictions.json"
OUT_RELATIONSHIPS = CHAT_DIR / "relationships.json"
OUT_CONSENSUS = CHAT_DIR / "consensus.json"

# ── Constants ───────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_BASE_DELAY = 2.0  # seconds


# ── Helpers ─────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict | list:
    """Load a JSON file with UTF-8 encoding."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data, indent=2):
    """Save data as JSON with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    print(f"  Saved: {path.relative_to(REPO_ROOT)}")


def save_text(path: Path, text: str):
    """Save text to a file with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  Saved: {path.relative_to(REPO_ROOT)}")


def slugify(name: str) -> str:
    """Convert a WhatsApp display name to a filename-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[~@#]", "", s)        # strip common prefixes
    s = re.sub(r"[^\w\s-]", "", s)      # strip non-word chars
    s = re.sub(r"[\s_]+", "-", s)       # spaces/underscores → hyphens
    s = re.sub(r"-+", "-", s)           # collapse multiple hyphens
    return s.strip("-")


def month_key(timestamp: str) -> str:
    """Extract YYYY-MM from an ISO timestamp string."""
    return timestamp[:7]


def chunk_by_month(messages: list[dict]) -> dict[str, list[dict]]:
    """Group messages into monthly buckets keyed by YYYY-MM."""
    buckets = defaultdict(list)
    for msg in messages:
        ts = msg.get("timestamp_utc", "")
        if ts:
            buckets[month_key(ts)].append(msg)
    return dict(sorted(buckets.items()))


def get_name_map() -> dict:
    """Load the WhatsApp name → identity mapping."""
    if NAME_MAP_PATH.exists():
        return load_json(NAME_MAP_PATH)
    print(f"WARNING: {NAME_MAP_PATH} not found. Identity resolution disabled.")
    return {}


def build_identity_context(name_map: dict) -> str:
    """Build a text block describing all league members for AI prompts."""
    if not name_map:
        return "No identity mapping available."
    lines = ["League members (WhatsApp name → real name, team, handle):"]
    for wa_name, info in name_map.items():
        real = info.get("real_name", "Unknown")
        team = info.get("team_name", "Unknown")
        handle = info.get("sleeper_handle", "N/A")
        lines.append(f"  - {wa_name} → {real}, Team: {team}, @{handle}")
    return "\n".join(lines)


def load_media_catalog() -> dict:
    """Load media catalog if available. Returns {message_id: item} lookup."""
    if not MEDIA_CATALOG_PATH.exists():
        return {}
    catalog = load_json(MEDIA_CATALOG_PATH)
    items = catalog.get("items", [])
    return {item["message_id"]: item for item in items if "message_id" in item}


def format_messages_for_prompt(messages: list[dict], limit: int = 0,
                                media_lookup: dict | None = None) -> str:
    """Format messages as a readable chat log for AI consumption.

    When media_lookup is provided, inline media descriptions from the catalog
    instead of raw filenames.
    """
    lines = []
    for msg in (messages[:limit] if limit else messages):
        ts = msg.get("timestamp_utc", "????-??-??")[:10]  # date only for readability
        sender = msg.get("sender", "Unknown")
        text = msg.get("text", "")
        media = msg.get("media", "")
        msg_id = msg.get("id")

        if media:
            # Try to get rich description from catalog
            catalog_entry = media_lookup.get(msg_id) if media_lookup and msg_id else None
            if catalog_entry:
                desc = catalog_entry.get("description", media)
                media_type = catalog_entry.get("type", "media").upper()
                media_label = f"[{media_type}: {desc}]"
            else:
                media_label = f"[{media}]"

            if not text:
                text = media_label
            else:
                text = f"{text} {media_label}"

        lines.append(f"[{ts}] {sender}: {text}")
    return "\n".join(lines)


# ── AI Client ──────────────────────────────────────────────────────────

def create_client() -> anthropic.Anthropic:
    """Create an Anthropic client. Requires ANTHROPIC_API_KEY env var."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("ERROR: ANTHROPIC_API_KEY not set in environment.")
        print("  Set it with: $env:ANTHROPIC_API_KEY='your_key_here'  (PowerShell)")
        print("  Or:          export ANTHROPIC_API_KEY='your_key_here' (bash)")
        sys.exit(1)
    return anthropic.Anthropic(api_key=key)


def call_claude(client: anthropic.Anthropic, system: str, user: str) -> str:
    """Call Claude with retries for rate limits. Returns the text response."""
    for attempt in range(RATE_LIMIT_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            delay = RATE_LIMIT_BASE_DELAY * (2 ** attempt)
            print(f"    Rate limited. Retrying in {delay:.0f}s...")
            time.sleep(delay)
        except anthropic.APIError as e:
            print(f"    API error: {e}")
            if attempt < RATE_LIMIT_RETRIES - 1:
                time.sleep(RATE_LIMIT_BASE_DELAY)
            else:
                raise
    raise RuntimeError("Exceeded max retries for Claude API call")


def call_claude_json(client: anthropic.Anthropic, system: str, user: str) -> dict:
    """Call Claude and parse the response as JSON."""
    raw = call_claude(client, system, user)
    # Strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"    WARNING: Failed to parse JSON response: {e}")
        print(f"    Raw response (first 500 chars): {raw[:500]}")
        # Try to extract JSON from the response
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"_raw": raw, "_parse_error": str(e)}


# ── MAP Phase ──────────────────────────────────────────────────────────

MAP_SYSTEM_PROMPT = """You are analyzing a WhatsApp group chat for a fantasy football dynasty league called "The Jailyard Dynasty" (12 teams, est. 2022). Your job is to extract structured analytical data from one month of chat messages.

{identity_context}

IMPORTANT RULES:
- Extract VERBATIM quotes — never paraphrase or invent text
- Every quote must include the exact sender name and timestamp from the chat log
- When extracting notable moments or predictions, include CONVERSATIONAL BLOCKS: the target message PLUS 1-2 messages before and 0-1 after for context
- If a setup line is from a different sender, include it — that's where the comedy lives
- If messages in a block are separated by >2 hours, truncate the block (different conversation)
- Focus on fantasy football discussion, trash talk, predictions, bets, reactions to games/trades/draft
- Flag running jokes, recurring phrases, and callback humor
- Track who talks to whom and in what tone

Respond with ONLY valid JSON matching this schema (no markdown, no commentary):
{{
  "month": "YYYY-MM",
  "message_count": <int>,
  "persona_observations": [
    {{
      "member": "<WhatsApp name>",
      "observations": ["<specific behavioral note with evidence>"],
      "notable_quotes": [
        {{
          "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
          "target_message_index": <int>,
          "context": "<why this is notable>"
        }}
      ],
      "posting_stats": {{
        "message_count": <int>,
        "avg_length_chars": <int>,
        "peak_hour": <int or null>,
        "emoji_heavy": <bool>,
        "media_count": <int>
      }}
    }}
  ],
  "candidate_arcs": [
    {{
      "title": "<descriptive arc name>",
      "type": "rivalry | trade_saga | prediction_saga | redemption | villain_arc | underdog | running_bit",
      "participants": ["<name>", ...],
      "key_moments": [
        {{
          "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
          "target_message_index": <int>,
          "significance": "<why this matters>"
        }}
      ],
      "status": "emerging | building | climax | cooling"
    }}
  ],
  "relationship_interactions": [
    {{
      "pair": ["<name1>", "<name2>"],
      "interaction_count": <int>,
      "tone": "friendly | hostile | competitive | comedic | neutral",
      "notable_exchanges": [
        {{
          "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
          "target_message_index": <int>,
          "label": "<short description>"
        }}
      ]
    }}
  ],
  "consensus_snapshots": [
    {{
      "topic": "<what the group is debating>",
      "group_lean": "<majority opinion summary>",
      "dissenters": ["<name>"],
      "key_quotes": [
        {{
          "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
          "target_message_index": <int>
        }}
      ]
    }}
  ],
  "predictions_and_bets": [
    {{
      "author": "<WhatsApp name>",
      "type": "prediction | bet | hot_take | guarantee",
      "quote_block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
      "target_message_index": <int>,
      "subject": "<what was predicted/bet on>",
      "made_at": "<ISO timestamp>"
    }}
  ],
  "running_jokes": [
    {{
      "name": "<joke/meme name>",
      "instances": [
        {{
          "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
          "target_message_index": <int>
        }}
      ],
      "frequency_this_month": <int>
    }}
  ],
  "greatest_moments": [
    {{
      "title": "<moment name>",
      "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
      "target_message_index": <int>,
      "why_great": "<why this is a hall-of-fame moment>"
    }}
  ],
  "lexicon_candidates": {{
    "<term>": "<definition with context>"
  }}
}}"""

MAP_USER_TEMPLATE = """Analyze this month of WhatsApp chat messages from The Jailyard Dynasty league.

Month: {month_label}
Message count: {msg_count}

--- CHAT LOG ---
{chat_log}
--- END CHAT LOG ---

Extract all analytical data as specified. Be thorough — capture every prediction, hot take, notable exchange, and running joke. Include full conversational blocks for context."""


def run_map_phase(
    client: anthropic.Anthropic,
    monthly_chunks: dict[str, list[dict]],
    name_map: dict,
    single_month: str | None = None,
) -> dict[str, dict]:
    """Run the MAP phase: process each monthly chunk through Claude."""
    MAP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    identity_context = build_identity_context(name_map)
    system = MAP_SYSTEM_PROMPT.format(identity_context=identity_context)

    # Load media catalog for rich inline descriptions
    media_lookup = load_media_catalog()
    if media_lookup:
        print(f"  Media catalog loaded: {len(media_lookup)} entries")

    months_to_process = (
        {single_month: monthly_chunks[single_month]}
        if single_month
        else monthly_chunks
    )
    total = len(months_to_process)
    results = {}

    for i, (month, messages) in enumerate(months_to_process.items(), 1):
        cache_path = MAP_CACHE_DIR / f"{month}.json"

        # Use cache if available
        if cache_path.exists():
            print(f"  [{i}/{total}] {month} — cached ({len(messages)} messages)")
            results[month] = load_json(cache_path)
            continue

        print(f"  [{i}/{total}] {month} — processing {len(messages)} messages...")
        chat_log = format_messages_for_prompt(messages, media_lookup=media_lookup)
        user_prompt = MAP_USER_TEMPLATE.format(
            month_label=month,
            msg_count=len(messages),
            chat_log=chat_log,
        )

        result = call_claude_json(client, system, user_prompt)
        results[month] = result
        save_json(cache_path, result)

        # Gentle pacing between API calls
        if i < total:
            time.sleep(1.0)

    return results


# ── REDUCE Phase ───────────────────────────────────────────────────────

def load_cached_map_outputs() -> dict[str, dict]:
    """Load all cached MAP phase outputs."""
    if not MAP_CACHE_DIR.exists():
        print(f"ERROR: No map cache found at {MAP_CACHE_DIR}")
        print("  Run the MAP phase first: python scripts/analyze_chat.py --map-only")
        sys.exit(1)

    results = {}
    for path in sorted(MAP_CACHE_DIR.glob("*.json")):
        month = path.stem  # e.g. "2024-03"
        results[month] = load_json(path)
    if not results:
        print("ERROR: Map cache directory is empty.")
        sys.exit(1)

    print(f"  Loaded {len(results)} cached monthly analyses")
    return results


# ── REDUCE: League Memory ─────────────────────────────────────────────

REDUCE_MEMORY_SYSTEM = """You are producing the definitive "League Bible" for The Jailyard Dynasty fantasy football league. You will receive summaries from monthly chat analyses spanning Sept 2023 → Feb 2026 (~23K messages).

Your job is to synthesize these into a single authoritative document about the league's culture, humor, and collective memory.

{identity_context}

RULES:
- Every quote block must be VERBATIM from the source data — never invent text
- Running jokes must have origin stories traced to specific messages
- Greatest moments must be ranked by genuine comedic/dramatic impact
- Lexicon terms must have real origins
- Culture summary should capture what makes THIS group chat unique

Respond with ONLY valid JSON (no markdown fences, no commentary)."""

REDUCE_MEMORY_USER = """Synthesize these monthly chat analyses into the League Bible.

Source months: {month_list}

Combined data follows. For each month you'll see running jokes, greatest moments, and lexicon candidates. Merge, deduplicate, rank, and produce the final league memory.

{monthly_summaries}

Produce JSON matching this schema:
{{
  "meta": {{
    "generated": "{timestamp}",
    "message_count": {total_messages},
    "analysis_version": "1.0",
    "months_analyzed": {month_count}
  }},
  "culture": {{
    "summary": "<2-3 paragraph description of this group chat's unique character>",
    "communication_patterns": {{
      "peak_activity_days": ["<day of week>"],
      "peak_hours": ["<hour range>"],
      "avg_daily_messages": <float>,
      "media_vs_text_ratio": "<rough ratio>"
    }},
    "activity_triggers": ["<what causes message spikes — e.g. trade announcements, TNF>"]
  }},
  "running_jokes": [
    {{
      "name": "<joke/meme name>",
      "origin_story": "<how it started>",
      "origin_quote": {{
        "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
        "target_message_index": 0
      }},
      "frequency": "daily | weekly | situational | seasonal",
      "peak_period": "<YYYY-MM when it was hottest>",
      "still_active": true
    }}
  ],
  "greatest_moments": [
    {{
      "rank": <int>,
      "title": "<memorable label>",
      "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
      "target_message_index": <int>,
      "why_great": "<what makes this hall-of-fame worthy>",
      "month": "<YYYY-MM>"
    }}
  ],
  "lexicon": {{
    "<term>": "<definition with origin>"
  }}
}}"""


def reduce_league_memory(
    client: anthropic.Anthropic,
    map_outputs: dict[str, dict],
    name_map: dict,
    total_messages: int,
) -> dict:
    """REDUCE: Merge monthly analyses into league-memory.json."""
    print("\n  Reducing: league-memory.json...")
    identity_context = build_identity_context(name_map)

    # Build compressed summaries of each month's cultural data
    summaries = []
    for month, data in map_outputs.items():
        if "_parse_error" in data:
            continue
        section = {
            "month": month,
            "message_count": data.get("message_count", 0),
            "running_jokes": data.get("running_jokes", []),
            "greatest_moments": data.get("greatest_moments", []),
            "lexicon_candidates": data.get("lexicon_candidates", {}),
        }
        summaries.append(json.dumps(section, ensure_ascii=False))

    system = REDUCE_MEMORY_SYSTEM.format(identity_context=identity_context)
    user = REDUCE_MEMORY_USER.format(
        month_list=", ".join(map_outputs.keys()),
        monthly_summaries="\n\n---\n\n".join(summaries),
        timestamp=datetime.utcnow().isoformat() + "Z",
        total_messages=total_messages,
        month_count=len(map_outputs),
    )

    result = call_claude_json(client, system, user)
    save_json(OUT_LEAGUE_MEMORY, result)
    return result


# ── REDUCE: Arcs ──────────────────────────────────────────────────────

REDUCE_ARCS_SYSTEM = """You are a narrative analyst for The Jailyard Dynasty fantasy football league. You will receive candidate narrative arcs extracted from monthly chat analyses spanning Sept 2023 → Feb 2026.

Your job: merge candidate arcs that span multiple months into coherent storylines. Some arcs appear in one month, others thread across many.

{identity_context}

RULES:
- Link arcs that share participants AND themes across months
- Track status: rising_tension → climax → resolved (or dormant/recurring)
- Rate narrative_potential 1-10 based on drama, humor, stakes
- Every key_moment block must use VERBATIM quotes from source data
- Include arc_id as a slug (e.g., "sacko-villain-arc-2024")

Respond with ONLY valid JSON array (no markdown, no commentary)."""

REDUCE_ARCS_USER = """Merge these candidate arcs into coherent cross-month narratives.

{monthly_arcs}

Produce a JSON array matching this schema:
[
  {{
    "arc_id": "<slug>",
    "title": "<descriptive name>",
    "type": "rivalry | trade_saga | prediction_saga | redemption | villain_arc | underdog | running_bit",
    "status": "rising_tension | climax | resolved | dormant | recurring",
    "span": {{"start": "YYYY-MM", "end": "YYYY-MM"}},
    "participants": ["<name>", ...],
    "key_moments": [
      {{
        "date": "<ISO date or YYYY-MM>",
        "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
        "target_message_index": <int>,
        "significance": "<why this moment matters to the arc>"
      }}
    ],
    "resolution_trigger": "<what resolved it, or null>",
    "narrative_potential": <float 1-10>
  }}
]"""


def reduce_arcs(
    client: anthropic.Anthropic,
    map_outputs: dict[str, dict],
    name_map: dict,
) -> list:
    """REDUCE: Merge candidate arcs into arcs.json."""
    print("\n  Reducing: arcs.json...")
    identity_context = build_identity_context(name_map)

    arc_summaries = []
    for month, data in map_outputs.items():
        if "_parse_error" in data:
            continue
        arcs = data.get("candidate_arcs", [])
        if arcs:
            arc_summaries.append(json.dumps(
                {"month": month, "arcs": arcs}, ensure_ascii=False
            ))

    system = REDUCE_ARCS_SYSTEM.format(identity_context=identity_context)
    user = REDUCE_ARCS_USER.format(
        monthly_arcs="\n\n---\n\n".join(arc_summaries)
    )

    result = call_claude_json(client, system, user)
    if isinstance(result, dict) and not isinstance(result, list):
        # AI might wrap array in an object
        result = result.get("arcs", result.get("data", [result]))
    save_json(OUT_ARCS, result)
    return result


# ── REDUCE: Predictions ──────────────────────────────────────────────

REDUCE_PREDICTIONS_SYSTEM = """You are the Receipts Keeper for The Jailyard Dynasty fantasy football league. You will receive predictions, bets, hot takes, and guarantees extracted from monthly chat analyses spanning Sept 2023 → Feb 2026.

Your job: compile the definitive predictions ledger and calculate credibility scores.

{identity_context}

RULES:
- Deduplicate predictions that appear in multiple monthly extractions
- Assess resolution status: pending, correct, wrong, partially_correct
- Use your knowledge of NFL/fantasy outcomes to resolve where possible
- credibility_impact: +1 for correct, -1 for wrong, 0 for pending/partial
- Every quote_block must be VERBATIM from source data
- Build credibility_index: per-member total correct, wrong, pending, accuracy%

Respond with ONLY valid JSON (no markdown, no commentary)."""

REDUCE_PREDICTIONS_USER = """Compile the definitive predictions ledger from these monthly extractions.

{monthly_predictions}

Produce JSON matching this schema:
{{
  "predictions": [
    {{
      "id": "pred-NNN",
      "author_whatsapp": "<WhatsApp name>",
      "type": "prediction | bet | hot_take | guarantee",
      "quote_block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
      "target_message_index": <int>,
      "subject": "<what was predicted>",
      "made_at": "<ISO timestamp>",
      "resolution": "pending | correct | wrong | partially_correct",
      "resolution_context": "<evidence for resolution, or null>",
      "credibility_impact": <-1 | 0 | 1>
    }}
  ],
  "credibility_index": {{
    "<WhatsApp name>": {{
      "total": <int>,
      "correct": <int>,
      "wrong": <int>,
      "pending": <int>,
      "accuracy_pct": <float or null>
    }}
  }}
}}"""


def reduce_predictions(
    client: anthropic.Anthropic,
    map_outputs: dict[str, dict],
    name_map: dict,
) -> dict:
    """REDUCE: Compile predictions.json from monthly extractions."""
    print("\n  Reducing: predictions.json...")
    identity_context = build_identity_context(name_map)

    pred_summaries = []
    for month, data in map_outputs.items():
        if "_parse_error" in data:
            continue
        preds = data.get("predictions_and_bets", [])
        if preds:
            pred_summaries.append(json.dumps(
                {"month": month, "predictions": preds}, ensure_ascii=False
            ))

    system = REDUCE_PREDICTIONS_SYSTEM.format(identity_context=identity_context)
    user = REDUCE_PREDICTIONS_USER.format(
        monthly_predictions="\n\n---\n\n".join(pred_summaries)
    )

    result = call_claude_json(client, system, user)
    save_json(OUT_PREDICTIONS, result)
    return result


# ── REDUCE: Relationships ────────────────────────────────────────────

REDUCE_RELATIONSHIPS_SYSTEM = """You are mapping the social dynamics of The Jailyard Dynasty fantasy football league. You will receive relationship interaction data from monthly chat analyses spanning Sept 2023 → Feb 2026.

Your job: aggregate pairwise interactions into a comprehensive social graph.

{identity_context}

RULES:
- Merge interactions for the same pair across months
- Determine overall dynamic: rivalry, alliance, trade_partners, comedic_duo, mentor_mentee
- Track sentiment_trajectory over time: warming, cooling, stable, volatile
- Signature moments must use VERBATIM quote blocks from source data
- Include interaction_count as sum across all months

Respond with ONLY valid JSON (no markdown, no commentary)."""

REDUCE_RELATIONSHIPS_USER = """Build the social graph from these monthly interaction records.

{monthly_relationships}

Produce JSON matching this schema:
{{
  "pairs": [
    {{
      "members": ["<name1>", "<name2>"],
      "interaction_count": <int>,
      "dynamic": "rivalry | alliance | trade_partners | comedic_duo | mentor_mentee | frenemies",
      "sentiment_trajectory": "warming | cooling | stable | volatile",
      "peak_month": "<YYYY-MM when they interacted most>",
      "signature_moments": [
        {{
          "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
          "target_message_index": <int>,
          "label": "<short description of this exchange>"
        }}
      ]
    }}
  ]
}}"""


def reduce_relationships(
    client: anthropic.Anthropic,
    map_outputs: dict[str, dict],
    name_map: dict,
) -> dict:
    """REDUCE: Aggregate relationships.json from monthly interactions."""
    print("\n  Reducing: relationships.json...")
    identity_context = build_identity_context(name_map)

    rel_summaries = []
    for month, data in map_outputs.items():
        if "_parse_error" in data:
            continue
        rels = data.get("relationship_interactions", [])
        if rels:
            rel_summaries.append(json.dumps(
                {"month": month, "interactions": rels}, ensure_ascii=False
            ))

    system = REDUCE_RELATIONSHIPS_SYSTEM.format(identity_context=identity_context)
    user = REDUCE_RELATIONSHIPS_USER.format(
        monthly_relationships="\n\n---\n\n".join(rel_summaries)
    )

    result = call_claude_json(client, system, user)
    save_json(OUT_RELATIONSHIPS, result)
    return result


# ── REDUCE: Consensus ────────────────────────────────────────────────

REDUCE_CONSENSUS_SYSTEM = """You are tracking the collective wisdom (and foolishness) of The Jailyard Dynasty fantasy football league group chat. You will receive consensus snapshots from monthly chat analyses spanning Sept 2023 → Feb 2026.

Your job: stitch these into an opinion-shift timeline, identify the group's biggest collective mistakes, and find the lone wolves who were right when everyone else was wrong.

{identity_context}

RULES:
- Track how group opinion on topics SHIFTS over time
- Identify collective_wrongs: times the group was confidently wrong
- Identify lone_wolves: members who held correct minority positions
- Every quote must be VERBATIM from source data
- Resolution assessments should use actual NFL/fantasy outcomes

Respond with ONLY valid JSON (no markdown, no commentary)."""

REDUCE_CONSENSUS_USER = """Build the group opinion timeline from these monthly consensus snapshots.

{monthly_consensus}

Produce JSON matching this schema:
{{
  "snapshots": [
    {{
      "topic": "<debate topic>",
      "period": "<YYYY-MM>",
      "group_opinion": "<majority view>",
      "dissenters": ["<name>"],
      "key_quotes": [
        {{
          "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
          "target_message_index": <int>
        }}
      ],
      "resolution": "<what actually happened, or pending>"
    }}
  ],
  "collective_wrongs": [
    {{
      "topic": "<what the group got wrong>",
      "group_prediction": "<what they thought>",
      "reality": "<what actually happened>",
      "peak_confidence_month": "<YYYY-MM>",
      "key_quote": {{
        "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
        "target_message_index": <int>
      }}
    }}
  ],
  "lone_wolves": [
    {{
      "member": "<name>",
      "position": "<their minority take>",
      "group_opposition": "<what everyone else said>",
      "vindication": "<how they were proven right>",
      "key_quote": {{
        "block": [{{"sender": "...", "text": "...", "timestamp": "..."}}],
        "target_message_index": <int>
      }}
    }}
  ]
}}"""


def reduce_consensus(
    client: anthropic.Anthropic,
    map_outputs: dict[str, dict],
    name_map: dict,
) -> dict:
    """REDUCE: Build consensus.json from monthly snapshots."""
    print("\n  Reducing: consensus.json...")
    identity_context = build_identity_context(name_map)

    con_summaries = []
    for month, data in map_outputs.items():
        if "_parse_error" in data:
            continue
        snaps = data.get("consensus_snapshots", [])
        if snaps:
            con_summaries.append(json.dumps(
                {"month": month, "snapshots": snaps}, ensure_ascii=False
            ))

    system = REDUCE_CONSENSUS_SYSTEM.format(identity_context=identity_context)
    user = REDUCE_CONSENSUS_USER.format(
        monthly_consensus="\n\n---\n\n".join(con_summaries)
    )

    result = call_claude_json(client, system, user)
    save_json(OUT_CONSENSUS, result)
    return result


# ── REDUCE: Personas ─────────────────────────────────────────────────

REDUCE_PERSONA_SYSTEM = """You are writing the definitive deep-dive character profile for a member of The Jailyard Dynasty fantasy football league, based on 2+ years of WhatsApp group chat behavior, quantitative fingerprinting, and media analysis.

{identity_context}

Target member: {target_member}
{member_identity}

RULES:
- Write in engaging, specific, DEEP prose — not generic filler. This is a psychological profile, not a Wikipedia entry.
- Every quote and catchphrase must be VERBATIM from source data with timestamps
- Reference quantitative fingerprint data naturally (don't just list stats — weave them into observations)
- Use media/GIF descriptions to characterize humor style and meme taste
- Include specific rivalries, alliances, and signature interactions with FULL conversational blocks
- Greatest hits and worst misses need full conversational blocks showing the setup and payoff
- Be honest but playful — this is a roast, not a resume
- When citing fingerprint stats, make them vivid: "Posts 0.24 emojis per message — nearly one in four messages gets the treatment" rather than just listing numbers

Respond with ONLY the markdown content (no code fences wrapping it)."""

REDUCE_PERSONA_USER = """Build the definitive V2 deep-dive profile for {target_member} from these monthly observations.

{persona_data}

=== QUANTITATIVE FINGERPRINT ===
{fingerprint_data}

=== MEDIA/GIF ANALYSIS ===
{media_data}

=== KEY RELATIONSHIPS ===
{relationship_data}

=== PREDICTIONS TRACK RECORD ===
{prediction_data}

Write the profile as markdown matching this V2 structure:

# {display_name} ({real_name})
**Team:** {team_name} | **Handle:** @{handle}

## 1. Identity
- Display name, team, role in the league, tenure
- One-sentence character summary (the "elevator pitch" for this person's league persona)

## 2. Communication DNA
- Writing style (essay writer? One-liner? GIF-first?)
- Vocabulary fingerprint: distinctive words from fingerprint data, what they reveal
- Emoji/GIF language: top emojis, what types of GIFs they send, media taste
- Timing patterns: peak hours, late-night percentage, day-of-week tendencies
- Message volume trends over time

## 3. Psychological Profile
- Confidence calibration: How often are they right vs. how confident they sound?
- Win/loss behavioral signatures: How does posting behavior change after wins vs. losses?
- Under-pressure tells: What happens when their team is struggling?
- Personality archetype in group context: The Troll? The Analyst? The Lurker? The Instigator?

## 4. Fantasy Brain
- Draft philosophy (from chat evidence)
- Trade approach: aggressive? passive? shark? marks?
- Hot take accuracy (cite predictions track record)
- Strategic strengths and blind spots

## 5. Social Position
- Key rivalries with VERBATIM quote evidence (full conversational blocks)
- Alliances and who they ride for
- Role in group dynamics: Who do they reply to most? Who replies to them?
- Conversation-starter vs. reactor ratio

## 6. Humor Profile
- Comedy style: dry wit? absurdist? trash talk king? meme lord?
- GIF/meme taste (cite specific media descriptions from catalog)
- Top 5 funniest moments as FULL conversational blocks (setup + payoff)
- Worst misses: jokes that bombed or takes that aged terribly (with receipts)

## 7. Narrative Hooks
- Active storylines heading into next season
- Unresolved tensions or bets
- Callback opportunities for the column writer
- "Watch for..." notes for future content"""


def reduce_personas(
    client: anthropic.Anthropic,
    map_outputs: dict[str, dict],
    name_map: dict,
    relationships: dict | None = None,
    predictions: dict | None = None,
):
    """REDUCE: Generate V2 persona markdown files from monthly observations + fingerprints + media."""
    print("\n  Reducing: persona profiles (V2)...")
    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
    identity_context = build_identity_context(name_map)

    # Load fingerprints
    fingerprints = {}
    if FINGERPRINTS_PATH.exists():
        fp_data = load_json(FINGERPRINTS_PATH)
        fingerprints = fp_data.get("members", {})
        print(f"    Fingerprints loaded: {len(fingerprints)} members")
    else:
        print("    WARNING: fingerprints.json not found — profiles will lack quantitative data")

    # Load media catalog indexed by sender
    media_by_sender = defaultdict(list)
    if MEDIA_CATALOG_PATH.exists():
        catalog = load_json(MEDIA_CATALOG_PATH)
        for item in catalog.get("items", []):
            sender = item.get("sender", "")
            if sender:
                media_by_sender[sender].append(item)
        print(f"    Media catalog loaded: {sum(len(v) for v in media_by_sender.values())} items")
    else:
        print("    WARNING: media-catalog.json not found — profiles will lack media analysis")

    # Collect all persona observations by member
    member_data = defaultdict(list)
    for month, data in map_outputs.items():
        if "_parse_error" in data:
            continue
        for obs in data.get("persona_observations", []):
            member = obs.get("member", "Unknown")
            member_data[member].append({"month": month, **obs})

    # Build per-member relationship and prediction context
    rel_by_member = defaultdict(list)
    if relationships and "pairs" in relationships:
        for pair in relationships["pairs"]:
            for m in pair.get("members", []):
                rel_by_member[m].append(pair)

    pred_by_member = defaultdict(list)
    if predictions and "predictions" in predictions:
        for pred in predictions["predictions"]:
            author = pred.get("author_whatsapp", "")
            pred_by_member[author].append(pred)

    total = len(member_data)
    for i, (member, observations) in enumerate(sorted(member_data.items()), 1):
        print(f"    [{i}/{total}] Generating V2 profile: {member}")

        # Resolve identity
        identity = name_map.get(member, {})
        real_name = identity.get("real_name", "Unknown")
        team_name = identity.get("team_name", "Unknown")
        handle = identity.get("sleeper_handle", "N/A")
        display_name = identity.get("display_name", member)

        member_identity = (
            f"Real name: {real_name}\n"
            f"Display name (for columns): {display_name}\n"
            f"Team: {team_name}\n"
            f"Sleeper handle: @{handle}"
        )

        # Prepare fingerprint context
        fp = fingerprints.get(member, {})
        fp_text = json.dumps(fp, ensure_ascii=False, indent=2) if fp else "No fingerprint data available."

        # Prepare media context — sample top items (limit to 50 to fit in prompt)
        member_media = media_by_sender.get(member, [])
        # Filter to items with actual descriptions
        described_media = [m for m in member_media if m.get("description") and m["description"] != "Unable to read file"]
        media_sample = described_media[:50]
        media_summary = {
            "total_media_sent": len(member_media),
            "described": len(described_media),
            "sample_items": media_sample,
        }
        media_text = json.dumps(media_summary, ensure_ascii=False, indent=2) if member_media else "No media data available."

        system = REDUCE_PERSONA_SYSTEM.format(
            identity_context=identity_context,
            target_member=member,
            member_identity=member_identity,
        )

        user = REDUCE_PERSONA_USER.format(
            target_member=member,
            persona_data=json.dumps(observations, ensure_ascii=False, indent=2),
            fingerprint_data=fp_text,
            media_data=media_text,
            relationship_data=json.dumps(
                rel_by_member.get(member, []), ensure_ascii=False, indent=2
            ),
            prediction_data=json.dumps(
                pred_by_member.get(member, []), ensure_ascii=False, indent=2
            ),
            display_name=display_name,
            real_name=real_name,
            team_name=team_name,
            handle=handle,
        )

        profile_md = call_claude(client, system, user)
        slug = slugify(member)
        save_text(PERSONAS_DIR / f"{slug}.md", profile_md)

        # Pacing
        if i < total:
            time.sleep(1.0)


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI-powered map-reduce analysis of Jailyard Dynasty WhatsApp chat"
    )
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="Process a single month (YYYY-MM format, for debugging)",
    )
    parser.add_argument(
        "--map-only",
        action="store_true",
        help="Run MAP phase only (cache monthly analyses)",
    )
    parser.add_argument(
        "--reduce-only",
        action="store_true",
        help="Run REDUCE phase only (from cached MAP outputs)",
    )
    parser.add_argument(
        "--skip-personas",
        action="store_true",
        help="Skip persona profile generation in REDUCE phase",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Jailyard Dynasty — WhatsApp Chat Analyzer")
    print("=" * 60)

    # ── Load data ──────────────────────────────────────────────────
    name_map = get_name_map()

    if not args.reduce_only:
        if not PARSED_MESSAGES.exists():
            print(f"\nERROR: {PARSED_MESSAGES} not found.")
            print("  Run the Phase 1 parser first to generate parsed_messages.json")
            sys.exit(1)

        print(f"\nLoading: {PARSED_MESSAGES.relative_to(REPO_ROOT)}")
        raw = load_json(PARSED_MESSAGES)
        messages = raw.get("messages", raw) if isinstance(raw, dict) else raw
        total_messages = len(messages)
        print(f"  {total_messages:,} messages loaded")

        monthly_chunks = chunk_by_month(messages)
        print(f"  {len(monthly_chunks)} monthly chunks: {list(monthly_chunks.keys())[0]} → {list(monthly_chunks.keys())[-1]}")

        # Validate single-month arg
        if args.month:
            if args.month not in monthly_chunks:
                print(f"\nERROR: Month {args.month} not found in chat data.")
                print(f"  Available months: {', '.join(monthly_chunks.keys())}")
                sys.exit(1)
    else:
        messages = None
        total_messages = 0

    # ── Create client ──────────────────────────────────────────────
    client = create_client()

    # ── MAP Phase ──────────────────────────────────────────────────
    if not args.reduce_only:
        print(f"\n{'─' * 40}")
        print("  MAP PHASE")
        print(f"{'─' * 40}")

        map_outputs = run_map_phase(
            client, monthly_chunks, name_map, single_month=args.month
        )

        if args.map_only:
            print(f"\n  MAP phase complete. {len(map_outputs)} months cached.")
            print(f"  Cache: {MAP_CACHE_DIR.relative_to(REPO_ROOT)}/")
            print("  Run --reduce-only to merge results.")
            return
    else:
        map_outputs = load_cached_map_outputs()

    # Count total messages from map outputs for metadata
    if total_messages == 0:
        for data in map_outputs.values():
            total_messages += data.get("message_count", 0)

    # ── REDUCE Phase ───────────────────────────────────────────────
    print(f"\n{'─' * 40}")
    print("  REDUCE PHASE")
    print(f"{'─' * 40}")

    # 1. League Memory
    league_memory = reduce_league_memory(client, map_outputs, name_map, total_messages)

    # 2. Arcs
    arcs = reduce_arcs(client, map_outputs, name_map)

    # 3. Predictions
    predictions = reduce_predictions(client, map_outputs, name_map)

    # 4. Relationships
    relationships = reduce_relationships(client, map_outputs, name_map)

    # 5. Consensus
    consensus = reduce_consensus(client, map_outputs, name_map)

    # 6. Personas (optional)
    if not args.skip_personas:
        reduce_personas(client, map_outputs, name_map, relationships, predictions)
    else:
        print("\n  Skipping persona generation (--skip-personas)")

    # ── Summary ────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  ANALYSIS COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Messages analyzed: {total_messages:,}")
    print(f"  Months covered:    {len(map_outputs)}")
    print(f"\n  Outputs:")
    for p in [OUT_LEAGUE_MEMORY, OUT_ARCS, OUT_PREDICTIONS, OUT_RELATIONSHIPS, OUT_CONSENSUS]:
        if p.exists():
            size_kb = p.stat().st_size / 1024
            print(f"    {p.relative_to(REPO_ROOT)} ({size_kb:.1f} KB)")
    if PERSONAS_DIR.exists():
        persona_files = list(PERSONAS_DIR.glob("*.md"))
        print(f"    {PERSONAS_DIR.relative_to(REPO_ROOT)}/ ({len(persona_files)} profiles)")
    print()


if __name__ == "__main__":
    main()
