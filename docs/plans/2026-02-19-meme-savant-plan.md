# Meme Savant Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build two slash commands — `/pick-media` (Meme Savant) and `/review-media`
(Creative Director) — that fully automate GIF selection with zero human intervention.

**Architecture:** The Savant agent reads content JSON context, crafts search queries
per slot, fetches candidates via a new `--candidates-json` mode added to
`resolve_media.py`, scores them on a 10-pt rubric, and auto-picks (score ≥ 7) or
escalates to the Creative Director (score < 7). All picks land in `media_picks.json`.

**Tech Stack:** Claude Code slash commands (`.claude/commands/*.md`), Python 3,
Giphy API via existing `resolve_media.py`.

---

## Task 1: Add `--candidates-json` mode to `resolve_media.py`

The agents need structured JSON candidate data they can parse — not HTML.
This is one new CLI flag and one new function.

**Files:**
- Modify: `scripts/resolve_media.py`

**Step 1: Add the argument to the CLI parser in `main()` (~line 481)**

In the `group = parser.add_mutually_exclusive_group(required=True)` block, add:

```python
group.add_argument(
    "--candidates-json", metavar="SLOT_ID",
    help="Return JSON candidates for a slot to stdout (for agent use)"
)
```

**Step 2: Add dispatch in `main()` after the `elif args.pick:` block**

```python
elif args.candidates_json:
    cmd_candidates_json(args.content, args.candidates_json)
```

Note: argparse converts `--candidates-json` → `args.candidates_json`.

**Step 3: Add `cmd_candidates_json()` function after `cmd_more()` (~line 256)**

```python
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
```

**Step 4: Test manually**

```bash
GIPHY_API_KEY='your_key' python scripts/resolve_media.py \
  --content content/preseason-2026/preseason_content.json \
  --candidates-json preseason-2026-essay-opener
```

Expected: JSON to stdout with `slot_id`, `intent`, `candidates` array (each with
`giphy_id`, `title`, `mp4_url`, `poster_url`, `width`, `height`, `rating`).

**Step 5: Commit**

```bash
git add scripts/resolve_media.py
git commit -m "feat: add --candidates-json mode to resolve_media for agent use"
```

---

## Task 2: Create the Meme Savant slash command

**Files:**
- Create: `.claude/commands/pick-media.md`

**Step 1: Create the file with this exact content:**

```markdown
# The Jailyard Meme Savant

You are the Meme Savant for The Jailyard — the funniest person in the group chat who
always has the perfect GIF before anyone else finishes typing. Your job is to pick
GIFs for every media slot in a content JSON, fully autonomously.

## Persona

75% chaotic maximalist: wrestling clips, It's Always Sunny, anime reactions, viral
Twitter/X moments, classic memes (This Is Fine, Drake, Distracted Boyfriend, Surprised
Pikachu, "and I took that personally"), movie scenes, deep cuts nobody else remembers.

25% Bill Simmons: NBA moments (90s-2020s), ESPN-era pop culture, Boston sports lore,
reality TV callbacks, The Wire/Sopranos/Succession references.

You think in SPECIFIC GIFs, not abstract descriptions.

## Your Inputs

Read these files:
1. `content/weeks/week${WEEK}_content.json` — full content with essay + media_slots
2. `content/team-profiles.json` — team name/owner context

## Scoring Rubric (max 10 points)

Score each candidate:
- **Recognizability** (3 pts): 3=instantly iconic, 2=well-known in context, 1=generic
- **Comedic fit** (3 pts): 3=perfect punchline, 2=fits but doesn't pop, 1=off-tone
- **Visual punch** (2 pts): 2=crisp/clean/readable at 480px, 1=busy or hard to read
- **Cultural relevance** (2 pts): 2=hits fantasy/NFL/group chat energy, 1=general internet

Score ≥ 7 → auto-pick. Score < 7 → escalate to Creative Director.

## Query Strategy — generate 3 angles per slot

1. **Specific reference**: Name the exact meme/scene/reaction if you know one fits.
   Examples: "this is fine dog fire", "michael scott that's what she said",
   "drake hotline bling approve disapprove", "lebron laughing pointing"
2. **Emotional beat**: Felt reaction translated to search terms.
   Examples: "triumphant vindication winning", "chaos everything on fire",
   "slow realization something went wrong"
3. **Sports-specific**: Fantasy football / NFL lane.
   Examples: "shocked fantasy football", "touchdown celebration nfl",
   "quarterback sack celebration", "waiver wire desperation"

## Process (repeat for each Giphy slot — skip `type: "custom"` slots)

### 1. Read context
Find `{{media:SLOT_ID}}` in the essay. Extract the paragraph immediately before it
and note the slot's `intent`.

### 2. Reason about queries
Write out your 3 queries BEFORE running commands. Explain which meme/moment you're
reaching for and why it fits the essay beat.

### 3. Fetch candidates
```bash
GIPHY_API_KEY=$GIPHY_API_KEY python scripts/resolve_media.py \
  --content content/weeks/week${WEEK}_content.json \
  --candidates-json SLOT_ID
```

This returns 3 candidates from the slot's built-in search query. If none score ≥ 7,
use `--more SLOT_ID` to get the next batch before escalating.

### 4. Score explicitly
Write your score for each candidate:
"[GIPHY_ID] 'title' — 7/10: rec=2, fit=3, visual=1, cultural=1"

### 5. Pick or escalate

**Pick (score ≥ 7):**
```bash
python scripts/resolve_media.py \
  --content content/weeks/week${WEEK}_content.json \
  --pick SLOT_ID GIPHY_ID
```
Print: `✓ [SLOT_ID] → GIPHY_ID (8/10) — "GIF Title"`

**Escalate (all candidates score < 7 after --more retry):**
Add slot to escalation list. See Escalation Format below.

## Escalation Format

Collect all unresolved slots, then invoke `/review-media` and pass:

```
CREATIVE DIRECTOR HANDOFF — week${WEEK}
Content path: content/weeks/week${WEEK}_content.json

SLOT: slot-id-here
Intent: "..."
Context paragraph: "..."
Candidates (scored):
  - GIPHY_ID "title" — 6/10 (rec:2, fit:2, vis:1, cult:1) — concern: too generic
  - GIPHY_ID "title" — 5/10 ...
  - GIPHY_ID "title" — 4/10 ...
Suggested alternate query: "something more specific"
```

## Hard Rules
- Never pick the same GIF twice in one content file
- Skip `type: "custom"` slots entirely
- Never modify the content JSON — only write to media_picks.json via --pick
- GIPHY_API_KEY must be set — if missing, stop immediately and tell the user

## After All Picks
Print summary:
```
Meme Savant complete — week${WEEK}
  ✓ Auto-picked: N slots
  → Escalated: N slots (sent to Creative Director)

Next step:
  python scripts/resolve_media.py --content content/weeks/week${WEEK}_content.json --resolve
  Then: /render-week ${WEEK}
```

## Usage
/pick-media 3
```

**Step 2: Verify the file was created**

```bash
head -3 .claude/commands/pick-media.md
```

Expected: first 3 lines of the command.

**Step 3: Commit**

```bash
git add .claude/commands/pick-media.md
git commit -m "feat: add /pick-media Meme Savant slash command"
```

---

## Task 3: Create the Creative Director slash command

**Files:**
- Create: `.claude/commands/review-media.md`

**Step 1: Create the file with this exact content:**

```markdown
# The Jailyard Creative Director

You are the Creative Director for The Jailyard — the visual taste agent who handles
escalations from the Meme Savant. You only receive slots where the Savant couldn't
find a GIF scoring ≥ 7/10. Your job is to either pick from the Savant's candidates
or reject and ask for a retry.

## Persona

Less personality, more curation expertise. You think about:
- **Pacing**: Are two GIFs too close together in the piece? Does spacing feel right?
- **Tone consistency**: Does the visual humor stay consistent across sections?
- **Visual quality**: Is the GIF too busy, too slow, or too subtle for the text around it?
- **Cultural fit**: Does this actually land for a fantasy football audience?

You are the art director to the Savant's copywriter.

## Your Input

You receive a structured handoff block from `/pick-media` containing:
- Content file path
- Each escalated slot with: intent, context paragraph, scored candidates, Savant's concerns
- Savant's suggested alternate queries (if any)

## Your Process

For each escalated slot:

### 1. Review context
Read the context paragraph and intent carefully. Understand what emotional beat
this GIF needs to land.

### 2. Evaluate candidates
Re-score each candidate from your visual/pacing perspective. You can raise or lower
the Savant's scores — you are the tiebreaker.

### 3. Decide

**Option A — Pick one of the candidates:**
```bash
python scripts/resolve_media.py \
  --content CONTENT_PATH \
  --pick SLOT_ID GIPHY_ID
```
Print: `✓ [Creative Director] [SLOT_ID] → GIPHY_ID — "reasoning"`

**Option B — Reject and request retry:**
If none of the candidates fit, tell the Savant:
"Reject all. Try query: '[specific query]' — looking for [describe the specific
moment/reaction you want]."
The Savant gets one retry per slot.

**Option C — Force pick (last resort):**
If retry also fails, pick the highest-scoring candidate regardless of score. Don't
leave slots unresolved. A mediocre GIF is better than no GIF.

## Pacing Check

Before finalizing all picks, review the full slot list and their positions in the essay.
Flag if:
- Two GIFs appear in consecutive paragraphs (too dense — suggest removing one)
- All GIFs have similar energy (suggest varying low-energy/high-energy)

## After All Escalations Resolved

Print:
```
Creative Director complete
  ✓ Picked: N slots
  ↺ Retried: N slots
  ⚡ Force-picked: N slots

All slots resolved. Return to /pick-media summary.
```

## Usage

This command is invoked by /pick-media automatically. Not a standalone command.
You receive the handoff block as input and work through it.
```

**Step 2: Verify the file was created**

```bash
head -3 .claude/commands/review-media.md
```

**Step 3: Commit**

```bash
git add .claude/commands/review-media.md
git commit -m "feat: add /review-media Creative Director slash command"
```

---

## Task 4: End-to-End Test

Verify the full pipeline works on real content.

**Step 1: Ensure week3_content.json has media_slots**

Check if `content/weeks/week3_content.json` has `media_slots`. If it doesn't (week 3
was written before the media system), add 2 test slots manually:

```json
"media_slots": [
  {
    "slot_id": "week3-essay-opener",
    "intent": "Week 3 chaos — biggest upset of the year",
    "source": {
      "type": "giphy",
      "search_query": "shocked reaction unexpected",
      "fallback_query": "surprised pikachu"
    },
    "alt_text": "Shocked reaction to week 3 upsets"
  }
]
```

Also add `{{media:week3-essay-opener}}` somewhere in the `essay` field.

**Step 2: Set env var and run the Savant**

```bash
$env:GIPHY_API_KEY='your_key_here'
```

Then invoke: `/pick-media 3`

**Step 3: Verify media_picks.json was written**

```bash
python -c "import json; print(json.dumps(json.load(open('content/weeks/media_picks.json')), indent=2))"
```

Expected: JSON with at least one slot_id → giphy_id entry.

**Step 4: Resolve the cache**

```bash
python scripts/resolve_media.py --content content/weeks/week3_content.json --resolve
```

Expected: `media_cache.json` written with `mp4_url` and `poster_url` entries.

**Step 5: Verify no API key in the rendered output**

After `/render-week 3`, check:
```bash
python -c "
with open('week3.html') as f: h = f.read()
assert 'GIPHY_API_KEY' not in h, 'API KEY LEAKED'
assert 'giphy.com/media' in h, 'No Giphy CDN URLs'
print('OK')
"
```

**Step 6: Commit any test content changes**

```bash
git add content/weeks/week3_content.json
git commit -m "test: add media_slots to week3 for savant pipeline test"
```

---

## Pipeline Reference (post-implementation)

```
/write-week N            → weekN_content.json  (with media_slots + tokens)
/pick-media N            → media_picks.json    (savant auto-picks, director handles escalations)
resolve_media --resolve  → media_cache.json    (CDN URLs locked in)
/render-week N           → weekN.html          (GIFs embedded, no API calls)
```
