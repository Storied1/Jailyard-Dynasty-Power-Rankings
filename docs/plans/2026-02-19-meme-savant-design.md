# Meme Savant Agent Design

**Date:** 2026-02-19
**Status:** Approved for implementation

## Overview

Two new slash commands that replace manual GIF selection with a fully autonomous,
LLM-driven media curation pipeline. Zero human intervention required for GIF picks.

## Agents

### `/pick-media` — The Meme Savant

**Persona:** 75% chaotic maximalist group-chat friend, 25% Bill Simmons. Thinks in
wrestling clips, It's Always Sunny references, anime reactions, viral Twitter moments,
classic memes, NBA highlights, movie scenes, and deep cuts. The friend who always has
the perfect GIF before anyone else finishes typing.

**Input:** `content/weeks/weekN_content.json` (or any content JSON with `media_slots`)

**Output:** `media_picks.json` alongside the content file, all slots resolved

**Process for each slot:**
1. Read the `intent` field + surrounding essay paragraph for full context
2. Run 3 search passes in priority order (see Query Strategy below)
3. Score all candidates on the rubric (max 10)
4. If top score ≥ 7 → auto-pick, write to `media_picks.json`
5. If top score < 7 → escalate to Creative Director with scored candidate list + reasoning
6. Hard rule: never pick the same GIF twice in one piece of content

### `/review-media` — The Creative Director

**Persona:** Visual curator. Less personality, more curation expertise. Thinks about
pacing (are two GIFs too close?), visual tone consistency across sections, whether a GIF
is too busy or too subtle for the surrounding text.

**Input:** Escalated slots from the savant — each with ranked candidates and savant
scoring reasoning

**Process:**
1. Review savant's scored candidates for each escalated slot
2. Either pick one OR reject all and tell savant to retry with different search terms
3. Savant gets one retry per slot — if still < 7 after retry, director makes final call
   from available candidates regardless of score

**Output:** Remaining picks written to `media_picks.json`

## Scoring Rubric (1–10)

| Criterion | Points | What it measures |
|-----------|--------|-----------------|
| Recognizability | 3 | Iconic/well-known vs. generic filler |
| Comedic fit | 3 | Humor matches essay tone at that exact moment |
| Visual punch | 2 | Clean loop, good quality, reads well at 480px |
| Cultural relevance | 2 | Connects to sports/fantasy/group chat culture |

Score ≥ 7 = savant auto-picks. Score < 7 = escalates to Creative Director.

## Query Strategy

For each slot the savant generates **3 search passes** in priority order:

1. **Specific reference** — if the moment calls for a known meme/scene, search it
   directly ("michael scott that's what she said", "ron swanson explosion")
2. **Emotional beat** — translate intent into felt reaction
   ("triumphant vindication", "slow realization everything is wrong")
3. **Sports-specific** — if moment is football/fantasy related, try that lane
   ("touchdown celebration", "shocked fantasy football manager")

Each pass fetches 3 candidates via `resolve_media.py --preview`. Savant scores all 9,
picks the highest scoring one.

## Files

### New
```
.claude/commands/pick-media.md      — Meme Savant slash command
.claude/commands/review-media.md    — Creative Director slash command
```

### Unchanged
```
scripts/resolve_media.py            — Giphy API plumbing (no changes)
```

The agents call `resolve_media.py` as a subprocess. No new Python code.

## Updated Pipeline

```
/write-week N           → weekN_content.json  (with media_slots + {{media:*}} tokens)
/pick-media N           → media_picks.json    (fully autonomous: savant + director)
resolve_media --resolve  → media_cache.json
/render-week N          → weekN.html          (GIFs embedded)
```

`/pick-media` replaces the manual `--preview` → human eyeball → `--pick` steps entirely.

## Cultural Knowledge Profile

The savant draws from (non-exhaustive):
- **Sports/fantasy:** ESPN reaction moments, draft day chaos, injury reports, waiver wire
  desperation, touchdown celebrations, sideline meltdowns
- **Classic memes:** This Is Fine, Drake approve/disapprove, Distracted Boyfriend,
  Surprised Pikachu, That's What She Said, and I took that personally
- **TV:** The Office, It's Always Sunny, Succession, The Wire, Breaking Bad, Parks & Rec,
  Real Housewives, Survivor, WWE/AEW highlights
- **Bill Simmons lane:** NBA moments (90s-2020s), pop culture callbacks, ESPN The Magazine
  era references, Boston sports lore
- **Viral internet:** Twitter/X moments, Reddit classics, TikTok crossovers that hit
  mainstream

## Deferred

- Team-specific GIF library (per-team recurring reactions)
- Section divider GIFs
- Confessional GIFs
- Ranking blurb GIFs (top 3 / bottom 3)
- Giphy candidate history tracking in cache
