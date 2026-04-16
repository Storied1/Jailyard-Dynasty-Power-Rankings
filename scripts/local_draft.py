#!/usr/bin/env python
"""
Local Draft Generator v2 — section-by-section column drafts via Ollama.

V2 fixes from v1 critique:
  - Section-by-section generation (not one monolithic shot)
  - Smart context budgeting per section (essay gets arcs, rankings gets stats)
  - Chat context cascade (high → medium → arcs, not just high)
  - Voice bible: extracts relevant patterns per section (not blind truncation)
  - JSON extraction with retry (up to 2 retries per section)
  - Continuity injection (loads previous week's content for callbacks)
  - Adaptive model selection (30B for essay/rankings, 8B for lighter sections)

Usage:
    python scripts/local_draft.py --week 7
    python scripts/local_draft.py --week 7 --section essay
    python scripts/local_draft.py --week 7 --fast          # use 8B for everything
    python scripts/local_draft.py --week 7 --resume         # skip already-drafted sections
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from shared import (
    WEEKS_DIR,
    VOICE_BIBLE_PATH as VOICE_BIBLE,
    TEAM_PROFILES_PATH as TEAM_PROFILES,
    OLLAMA_BASE,
    MODEL_HEAVY,
    MODEL_LIGHT,
    SECTION_TOKEN_BUDGETS,
    load_json,
)

# Section generation order and model assignment
SECTIONS = [
    ("essay", MODEL_HEAVY, SECTION_TOKEN_BUDGETS["essay"]),
    ("rankings", MODEL_HEAVY, SECTION_TOKEN_BUDGETS["rankings"]),
    ("confessionals", MODEL_LIGHT, SECTION_TOKEN_BUDGETS["confessionals"]),
    ("mailbag", MODEL_LIGHT, SECTION_TOKEN_BUDGETS["mailbag"]),
    ("bits", MODEL_LIGHT, SECTION_TOKEN_BUDGETS["bits"]),
]

MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Ollama API
# ---------------------------------------------------------------------------


def ollama_generate(model, prompt, system=None, temperature=0.7, max_tokens=4096):
    """Call Ollama /api/generate with streaming off.

    Doubles num_predict for Qwen 3 thinking mode overhead.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens * 2},
    }
    if system:
        payload["system"] = system

    url = f"{OLLAMA_BASE}/api/generate"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("response", "")
    except urllib.error.URLError as e:
        print(f"Error: Ollama unreachable at {OLLAMA_BASE}: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# File loaders
# ---------------------------------------------------------------------------


def load_text(path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Voice Bible — section-relevant extraction
# ---------------------------------------------------------------------------

# Which voice bible sections matter most per content section.
# We extract paragraphs containing these keywords instead of blind truncation.
VOICE_KEYWORDS = {
    "essay": [
        "hook",
        "cold open",
        "kicker",
        "pop culture",
        "callback",
        "narrative",
        "dramatic",
        "conversational",
        "group chat",
    ],
    "rankings": [
        "second person",
        "you",
        "blurb",
        "data as punctuation",
        "stat",
        "roast",
        "tone",
        "vary",
    ],
    "confessionals": ["first person", "camera", "reality TV", "dramatic", "confess"],
    "mailbag": ["mailbag", "Q&A", "question", "punchy", "humor", "dear commish"],
    "bits": [
        "bits",
        "segment",
        "Great Call",
        "Ewing Theory",
        "Parent Corner",
        "Overheard",
        "kicker",
    ],
}


def extract_voice_guidance(section, max_chars=4000):
    """Extract voice bible paragraphs most relevant to this section."""
    full_text = load_text(VOICE_BIBLE)
    if not full_text:
        return ""

    keywords = VOICE_KEYWORDS.get(section, VOICE_KEYWORDS["essay"])
    paragraphs = full_text.split("\n\n")

    # Score each paragraph by keyword hits
    scored = []
    for para in paragraphs:
        lower = para.lower()
        score = sum(1 for kw in keywords if kw.lower() in lower)
        # Boost headings and pattern definitions
        if para.strip().startswith("#"):
            score += 1
        scored.append((score, para))

    # Always include high-scoring paragraphs, fill remaining budget with others
    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    chars = 0
    for score, para in scored:
        if score == 0 and chars > max_chars * 0.6:
            break  # stop adding zero-relevance paragraphs once we have enough
        if chars + len(para) > max_chars:
            break
        result.append(para)
        chars += len(para)

    return "\n\n".join(result)


# ---------------------------------------------------------------------------
# Context builders — each section gets tailored data
# ---------------------------------------------------------------------------


def build_essay_context(week_data, chat_context, prev_content):
    """Essay needs: matchup highlights, arcs, chat drama, previous week callbacks."""
    parts = []

    if week_data:
        # Full matchups (essay references specific games)
        if "matchups" in week_data:
            parts.append(
                "MATCHUP RESULTS:\n"
                + json.dumps(week_data["matchups"], indent=None, separators=(",", ":"))
            )
        # Awards for narrative hooks
        if "awards" in week_data:
            parts.append(
                "AWARDS:\n"
                + json.dumps(week_data["awards"], indent=None, separators=(",", ":"))
            )
        # Standings for context
        if "standings" in week_data:
            compact = [
                {
                    "team": s.get("team_name"),
                    "record": s.get("record"),
                    "rank": s.get("rank"),
                    "pf": s.get("points_for"),
                    "momentum": (s.get("momentum") or {}).get("label"),
                    "margin": s.get("margin_this_week"),
                }
                for s in week_data["standings"]
            ]
            parts.append("STANDINGS:\n" + json.dumps(compact, separators=(",", ":")))

    # Chat context — cascade: high → medium → arcs → highlights
    parts.extend(_chat_section(chat_context, max_quotes=6))

    # Previous week callback material
    if prev_content and "essay" in prev_content:
        # Give a brief summary of last week's essay for callbacks
        prev_essay = (
            prev_content["essay"][:500] + "..."
            if len(prev_content.get("essay", "")) > 500
            else prev_content.get("essay", "")
        )
        parts.append(f"LAST WEEK'S ESSAY (for callbacks):\n{prev_essay}")

    if week_data and "previous_weeks_summary" in week_data:
        parts.append(
            "PREVIOUS WEEKS SUMMARY:\n"
            + json.dumps(
                week_data["previous_weeks_summary"], indent=None, separators=(",", ":")
            )
        )

    return "\n\n".join(parts)


def build_rankings_context(week_data, chat_context):
    """Rankings need: full standings with stats, matchup scores, team profiles."""
    parts = []

    if week_data:
        # Full standings (rankings need every stat)
        if "standings" in week_data:
            parts.append(
                "FULL STANDINGS:\n"
                + json.dumps(week_data["standings"], indent=None, separators=(",", ":"))
            )
        # Matchups with scores
        if "matchups" in week_data:
            parts.append(
                "MATCHUP RESULTS:\n"
                + json.dumps(week_data["matchups"], indent=None, separators=(",", ":"))
            )
        # Historical context for record references
        if "historical_context" in week_data:
            parts.append(
                "HISTORICAL RECORDS:\n"
                + json.dumps(
                    week_data["historical_context"], indent=None, separators=(",", ":")
                )
            )
        # Team profile summaries for roster/rank data
        if "team_profiles_summary" in week_data:
            parts.append(
                "TEAM PROFILES:\n"
                + json.dumps(
                    week_data["team_profiles_summary"],
                    indent=None,
                    separators=(",", ":"),
                )
            )

    # Light chat context for rankings flavor
    parts.extend(_chat_section(chat_context, max_quotes=3))

    return "\n\n".join(parts)


def build_light_context(week_data, chat_context):
    """Confessionals, mailbag, bits need: matchup highlights + chat + standings summary."""
    parts = []

    if week_data:
        if "matchups" in week_data:
            parts.append(
                "MATCHUP RESULTS:\n"
                + json.dumps(week_data["matchups"], indent=None, separators=(",", ":"))
            )
        if "awards" in week_data:
            parts.append(
                "AWARDS:\n"
                + json.dumps(week_data["awards"], indent=None, separators=(",", ":"))
            )
        if "standings" in week_data:
            compact = [
                {
                    "team": s.get("team_name"),
                    "record": s.get("record"),
                    "rank": s.get("rank"),
                    "momentum": (s.get("momentum") or {}).get("label"),
                    "margin": s.get("margin_this_week"),
                }
                for s in week_data["standings"]
            ]
            parts.append("STANDINGS:\n" + json.dumps(compact, separators=(",", ":")))

    parts.extend(_chat_section(chat_context, max_quotes=4))

    return "\n\n".join(parts)


def _chat_section(chat_context, max_quotes=5):
    """Build chat context parts with cascade: high → medium → arcs → highlights."""
    if not chat_context:
        return []

    parts = []
    quotes = []

    # Cascade: high relevancy first, then medium if we need more
    high = chat_context.get("high_relevancy", [])
    medium = chat_context.get("medium_relevancy", [])
    quotes.extend(high[:max_quotes])
    remaining = max_quotes - len(quotes)
    if remaining > 0 and medium:
        quotes.extend(medium[:remaining])

    if quotes:
        parts.append(
            "CHAT QUOTES:\n" + json.dumps(quotes, indent=None, separators=(",", ":"))
        )

    arcs = chat_context.get("active_arcs_this_week", [])
    if arcs:
        parts.append(
            "ACTIVE STORYLINES:\n" + json.dumps(arcs[:5], separators=(",", ":"))
        )

    highlights = chat_context.get("this_weeks_chat_highlights", [])
    if highlights:
        parts.append(
            "CHAT HIGHLIGHTS:\n" + json.dumps(highlights[:5], separators=(",", ":"))
        )

    resolved = chat_context.get("resolved_predictions", [])
    if resolved:
        parts.append(
            "RESOLVED PREDICTIONS:\n" + json.dumps(resolved[:3], separators=(",", ":"))
        )

    sentiment = chat_context.get("sentiment_snapshot", {})
    if sentiment:
        parts.append("SENTIMENT:\n" + json.dumps(sentiment, separators=(",", ":")))

    return parts


# ---------------------------------------------------------------------------
# Section prompts (v2 — more specific, with schema examples)
# ---------------------------------------------------------------------------

SECTION_PROMPTS = {
    "essay": (
        "Write a 400-700 word cold open essay for Week {week} of The Jailyard dynasty "
        "fantasy football league.\n\n"
        "REQUIREMENTS:\n"
        "- Start with a dramatic, specific hook (NOT 'Welcome back' or 'Another week')\n"
        "- Reference 2-3 teams whose stories are most compelling this week\n"
        "- Weave in at least 1 callback to previous weeks\n"
        "- Reference the group chat at least once (use quotes from CHAT QUOTES if available)\n"
        "- Embed specific stats naturally in narrative (never standalone stat lines)\n"
        "- When citing player performances, use `top_scorers[].game_context.one_liner` "
        "verbatim -- do NOT invent yards / TDs / targets. Fabricated stat lines are a fail mode.\n"
        "- Frame team trajectories using `standings[].momentum.label` and "
        "`standings[].margin_this_week`. Ignore 'opening' and 'early' labels "
        "(weeks 1-3, not enough data).\n"
        "- End with a quotable kicker line\n\n"
        'Output ONLY valid JSON: {{"essay": "the full essay text..."}}'
    ),
    "rankings": (
        "Write power ranking blurbs for all 12 teams for Week {week}.\n\n"
        "REQUIREMENTS:\n"
        "- Each blurb: 100-200 words, written in SECOND PERSON ('you')\n"
        "- Reference at least one specific player performance with actual stats from the data\n"
        "- Each standings entry has `momentum.score` (-3 to +3) and `momentum.label`. "
        "Prefer describing trajectory (e.g. 'surging', 'cooling') over just citing rank change. "
        "Skip the label if it's 'opening' or 'early'.\n"
        "- NO two consecutive blurbs should start with the same word or structure\n"
        "- Vary the tone: some celebratory, some eulogies, some roasts\n"
        "- When H2H data exists, consider citing the series record\n"
        "- End each blurb with a kicker line\n\n"
        "Order teams from rank 1 (best) to rank 12 (worst) based on standings.\n\n"
        "Output ONLY valid JSON:\n"
        '{{"rankings": [\n'
        '  {{"rank": 1, "prev_rank": null, "movement": "none", '
        '"team_name": "...", "owner": "...", "record": "W-L", '
        '"blurb": "..."}},\n'
        "  ...\n"
        "]}}"
    ),
    "confessionals": (
        "Write 3-4 confessionals for Week {week}.\n\n"
        "REQUIREMENTS:\n"
        "- First person, 50-100 words each\n"
        "- Written as if the owner is talking to a reality TV camera\n"
        "- Pick the most dramatic stories: big winners, heartbreaking losers, surprises\n\n"
        "Output ONLY valid JSON:\n"
        '{{"confessionals": [{{"team_name": "...", "text": "..."}}]}}'
    ),
    "mailbag": (
        "Write 3-5 mailbag Q&As for Week {week}.\n\n"
        "REQUIREMENTS:\n"
        "- Questions start with 'Dear Commish:' and reference real situations from this week\n"
        "- Mix serious analysis with humor\n"
        "- At least one question references a preseason prediction\n"
        "- Answers should be punchy (shorter than the question if possible)\n\n"
        "Output ONLY valid JSON:\n"
        '{{"mailbag": [{{"question": "Dear Commish: ...", "answer": "..."}}]}}'
    ),
    "bits": (
        "Write 3-5 bits/segments for Week {week}.\n\n"
        "REQUIREMENTS:\n"
        "- Rotate from: Great Call, Parent Corner, Nobody Believes in Us, "
        "Overheard in the Chat, Ewing Theory Alert, Is X the New Y?, "
        "Things I Believe But Can't Prove, IDP Monster of the Week, "
        "Preseason Prediction Tracker, Luck Index\n"
        "- 1-3 sentences each\n"
        "- Reference actual data from this week\n\n"
        "Output ONLY valid JSON:\n"
        '{{"bits": [{{"title": "...", "text": "..."}}]}}'
    ),
}

CONTEXT_BUILDERS = {
    "essay": build_essay_context,
    "rankings": build_rankings_context,
    "confessionals": build_light_context,
    "mailbag": build_light_context,
    "bits": build_light_context,
}


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def extract_json(response):
    """Try to extract valid JSON from model output. Handles markdown fences."""
    cleaned = response.strip()

    # Strip markdown code fences
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try to find JSON starting from first {
    idx = cleaned.find("{")
    if idx >= 0:
        # Find matching closing brace
        depth = 0
        for i in range(idx, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[idx : i + 1])
                    except json.JSONDecodeError:
                        break

    return None


def validate_section(section, data):
    """Basic structural validation for a draft section."""
    if not isinstance(data, dict):
        return False, "Not a dict"

    if section == "essay":
        if "essay" not in data or not isinstance(data["essay"], str):
            return False, "Missing or invalid 'essay' key"
        if len(data["essay"]) < 200:
            return False, f"Essay too short ({len(data['essay'])} chars)"
        return True, "OK"

    elif section == "rankings":
        rankings = data.get("rankings", [])
        if not isinstance(rankings, list) or len(rankings) < 6:
            return (
                False,
                f"Rankings has {len(rankings) if isinstance(rankings, list) else 0} items (need 12)",
            )
        return True, f"{len(rankings)} teams"

    elif section == "confessionals":
        items = data.get("confessionals", [])
        if not isinstance(items, list) or len(items) < 2:
            return (
                False,
                f"Only {len(items) if isinstance(items, list) else 0} confessionals",
            )
        return True, f"{len(items)} items"

    elif section == "mailbag":
        items = data.get("mailbag", [])
        if not isinstance(items, list) or len(items) < 2:
            return False, f"Only {len(items) if isinstance(items, list) else 0} Q&As"
        return True, f"{len(items)} items"

    elif section == "bits":
        items = data.get("bits", [])
        if not isinstance(items, list) or len(items) < 2:
            return False, f"Only {len(items) if isinstance(items, list) else 0} bits"
        return True, f"{len(items)} items"

    return True, "OK"


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------


def generate_section(
    section,
    week,
    model,
    max_tokens,
    temperature,
    week_data,
    chat_context,
    prev_content,
    team_profiles,
):
    """Generate a single section with retry logic."""
    voice_guidance = extract_voice_guidance(section)
    system_prompt = (
        "You are the AI writing staff for The Jailyard dynasty fantasy football league. "
        "Your voice is Bill Simmons -- conversational, pop-culture-laden, data-grounded.\n\n"
        "VOICE GUIDE:\n"
        f"{voice_guidance}\n\n"
        "CRITICAL: Output ONLY valid JSON. No explanation, no preamble, no markdown."
    )

    # Build section-specific context
    context_builder = CONTEXT_BUILDERS.get(section, build_light_context)
    if section == "essay":
        context = context_builder(week_data, chat_context, prev_content)
    else:
        context = context_builder(week_data, chat_context)

    # Team names for reference
    team_list = ""
    if team_profiles:
        profiles = (
            team_profiles
            if isinstance(team_profiles, list)
            else team_profiles.get("teams", [])
        )
        names = [
            f"{t.get('team_name', '?')} ({t.get('owner', '?')})"
            for t in profiles
            if isinstance(t, dict)
        ]
        if names:
            team_list = f"\n\nTEAMS: {', '.join(names)}"

    prompt_template = SECTION_PROMPTS.get(section, SECTION_PROMPTS["essay"])
    prompt = prompt_template.format(week=week) + "\n\n" + context + team_list

    for attempt in range(1, MAX_RETRIES + 2):
        start = time.time()
        response = ollama_generate(
            model,
            prompt,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed = time.time() - start

        parsed = extract_json(response)
        if parsed:
            valid, detail = validate_section(section, parsed)
            if valid:
                print(f"    [{section}] OK in {elapsed:.0f}s ({detail})")
                return parsed

            if attempt <= MAX_RETRIES:
                print(
                    f"    [{section}] Validation failed ({detail}), retry {attempt}/{MAX_RETRIES}..."
                )
                # Add feedback to prompt for retry
                prompt += f"\n\nYour previous output was invalid: {detail}. Fix and output valid JSON only."
                continue
            else:
                print(
                    f"    [{section}] Validation failed after retries ({detail}), using best effort"
                )
                return parsed
        else:
            if attempt <= MAX_RETRIES:
                print(f"    [{section}] Invalid JSON, retry {attempt}/{MAX_RETRIES}...")
                prompt += "\n\nYour previous output was not valid JSON. Output ONLY a JSON object, no other text."
                continue
            else:
                print(
                    f"    [{section}] Failed to get valid JSON after {MAX_RETRIES} retries"
                )
                # Save raw text for manual extraction
                raw_path = WEEKS_DIR / f"week{week}_draft_{section}.txt"
                with open(raw_path, "w", encoding="utf-8") as f:
                    f.write(response)
                print(f"    Saved raw text to {raw_path}")
                return None

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate weekly column draft via local Ollama (v2)"
    )
    parser.add_argument("--week", type=int, required=True, help="Week number")
    parser.add_argument(
        "--section",
        default=None,
        choices=["essay", "rankings", "confessionals", "mailbag", "bits"],
        help="Generate a single section (default: all sections)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help=f"Use {MODEL_LIGHT} for all sections (faster, lower quality)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.7, help="Sampling temperature"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip sections that already exist in the draft file",
    )
    parser.add_argument("--output", help="Output file path (default: weekN_draft.json)")
    args = parser.parse_args()

    week = args.week
    output_path = (
        Path(args.output) if args.output else WEEKS_DIR / f"week{week}_draft.json"
    )

    # Load inputs
    week_data = load_json(WEEKS_DIR / f"week{week}_data.json")
    chat_context = load_json(WEEKS_DIR / f"week{week}_chat_context.json")
    team_profiles = load_json(TEAM_PROFILES)

    # Load previous week content for continuity
    prev_content = None
    if week > 1:
        prev_content = load_json(WEEKS_DIR / f"week{week-1}_content.json")
        if not prev_content and week > 2:
            prev_content = load_json(WEEKS_DIR / f"week{week-2}_content.json")

    if not week_data:
        print(
            f"Warning: No week data at {WEEKS_DIR / f'week{week}_data.json'}",
            file=sys.stderr,
        )

    # Load existing draft for resume mode
    existing = {}
    if args.resume and output_path.exists():
        existing = load_json(output_path) or {}
        print(f"Resuming — existing sections: {', '.join(existing.keys())}")

    # Determine sections to generate
    if args.section:
        sections_to_run = [
            (
                args.section,
                (
                    MODEL_LIGHT
                    if args.fast
                    else (
                        dict(SECTIONS).get(args.section, (MODEL_HEAVY,))[0]
                        if isinstance(dict(SECTIONS).get(args.section), tuple)
                        else MODEL_HEAVY
                    )
                ),
                dict((s[0], s[2]) for s in SECTIONS).get(args.section, 4096),
            )
        ]
    else:
        sections_to_run = [
            (name, MODEL_LIGHT if args.fast else model, tokens)
            for name, model, tokens in SECTIONS
        ]

    # Filter out already-done sections in resume mode
    if args.resume:
        sections_to_run = [
            (n, m, t) for n, m, t in sections_to_run if n not in existing
        ]
        if not sections_to_run:
            print("All sections already drafted. Nothing to do.")
            return

    print(f"Week {week} — generating {len(sections_to_run)} sections")
    for name, model, tokens in sections_to_run:
        short_model = model.split(":")[0] if ":" in model else model
        print(f"  {name}: {short_model} ({tokens} tokens)")

    # Generate each section
    draft = dict(existing)  # preserve existing sections in resume mode
    total_start = time.time()

    for section_name, model, max_tokens in sections_to_run:
        result = generate_section(
            section=section_name,
            week=week,
            model=model,
            max_tokens=max_tokens,
            temperature=args.temperature,
            week_data=week_data,
            chat_context=chat_context,
            prev_content=prev_content,
            team_profiles=team_profiles,
        )
        if result:
            draft.update(result)
            # Save after each section (crash recovery)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(draft, f, indent=2, ensure_ascii=False)

    total_elapsed = time.time() - total_start

    # Summary
    print(f"\nDraft complete in {total_elapsed:.0f}s")
    print(f"Sections: {', '.join(draft.keys())}")
    if "essay" in draft:
        print(f"Essay: {len(draft['essay'])} chars")
    if "rankings" in draft:
        print(f"Rankings: {len(draft['rankings'])} teams")
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
