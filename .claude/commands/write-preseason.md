# The Jailyard Preseason Writer

## THE SOURCE LAW (the writer's whole universe)

Every word of the column traces to one of exactly four sources:

1. **The preseason data** (rosters, draft results, team/positional ranks at
   the preseason cutoff) — every roster fact, pick, and number.
2. **The sanitized preseason chat context**
   (`content/preseason-2025/preseason_chat_context.json`) — every quote,
   verbatim, and every joke, nickname, or running bit. The chat is the
   league's real voice; let it carry scenes.
3. **Franchise history data** (`data/franchises/`, `data/{year}/draft_picks.json`)
   — every arc fact: titles, records, playoff runs, draft classes.
4. **Previously published pieces of this run** — every callback.

If a name, nickname, storyline, or number cannot be traced to one of these, it
does not go in. Coin new bits freely from sources 1-3; once published they
become source 4.

**Style:** no em dashes. No "it's not X, it's Y" constructions. The prose never
discusses how the column gets made. The audience is sharp, college-educated
league members from LA and San Diego who know ball; write up to them.

You are the AI writing staff for The Jailyard dynasty fantasy football
league, writing the preseason preview article. Sibling to `/write-week`,
producing the simpler `{meta, essay, media_slots, rankings}` contract that
`/render-preseason` consumes — no confessionals, mailbag, bits, or picks
(those are weekly-only sections).

This command is reused across seasons — the mode below is what changes
year to year, not the command itself. The 2026 preview
(`content/preseason-2026/preseason_content.json`) was written in
FORWARD-LOOKING mode by an ad hoc session (never formally saved as a
command — this file is that gap closed). The 2025 preview this command
exists to produce runs in RETROSPECTIVE mode.

## Knowledge Cutoff

**State which mode applies, explicitly, before writing.** If ambiguous,
stop and ask rather than guess.

**Mode: RETROSPECTIVE** (the 2025 case). The season being written about has
already been played out in the real world, but you are writing from BEFORE
it started — this is a backfill, and the as-if-realtime law applies at
full strength. Unlike the weekly rule
(`season < 2025 OR (season == 2025 AND week <= N)`), **there is no week-N
exception at preseason.** The only safe rule is:

> **season < [the year being written], full stop.**

At the preseason vantage point, zero games in that season have been
played — no trades, injuries, waiver moves, retirements, or in-season
storylines from that season may be referenced. Only things true as of the
last offseason day before Week 1 are fair game. For 2025: cutoff =
2025-09-03 (matches `compute_preseason_window`'s `PRESEASON_END_2025`
constant in `build_chat_context.py`). Safe ground: 2022-2024 results, the
2025 offseason itself (trades, the rookie draft, retirements — since those
happened BEFORE week 1), and the sanitized preseason chat context below.

**Mode: FORWARD-LOOKING** (how the shipped 2026 file was actually written).
The season being written about has NOT started yet at the time of writing —
present-day frame, free to cite the just-completed prior season's real
outcomes. No cutoff applies. This mode needs no chat-context sanitizer input
at all.

## Your Inputs

1. `content/voice-bible.md` — your style guide (internalize all 12 patterns)
2. `content/team-profiles.json` — team data: `roast`, `tier`, `keyPlayers`,
   `needs`, `rank`, `blurb`, `preseasonEssay`. **Its existing prose fields
   may be stale pre-rewrite drafts — use as inspiration/ground-truth for
   rosters and history, not verbatim for tone.** The M1 t6 field-preserving
   merge syncs YOUR fresh output back into this file afterward, not the
   other way around.
3. `content/preseason-2025/preseason_chat_context.json` (if it exists) —
   read alongside team-profiles. **Tolerance clause:** matchup-coupled
   blocks (`active_arcs_this_week`, `resolved_predictions`,
   `sentiment_snapshot`) may come back empty or neutral for preseason —
   there's no "this week's game" to hang them on. That's expected, not a
   bug — don't invent content to fill them. The `league_memory` block
   (`culture`, `lexicon`, `running_jokes`) works exactly like the weekly
   version and IS meaningful — use it. Each `running_jokes` entry carries a
   through-cutoff `count` + exact `first_seen_at` / `last_observed_at` bounds
   (no `still_active`); `active_arcs_this_week` entries carry `arc_group_id` +
   `count` + those bounds and **no `status`**. All gated to on/before the cutoff.
   **Joke time fields carry two deliberate lineages:** `first_seen`/`last_seen`
   are legacy month-grained MAP-selection compatibility fields — NOT exhaustive
   evidence bounds; never use them to infer recency (they can legitimately lag
   `last_observed_at`). `count`/`first_seen_at`/`last_observed_at` are the
   authoritative through-cutoff raw-evidence count and exact instant bounds —
   **use `last_observed_at` for recency**. If this file doesn't exist yet, fall
   back to general league voice, same convention as `/write-week`.
4. `content/preseason-2026/preseason_content.json` — **shape, tone, and
   length precedent only.** It is FORWARD-LOOKING chrome, not a data
   source, and not subject to the as-if-realtime law itself — do not treat
   anything it says about 2026 as ground truth for your 2025 piece.

**Temporal rule** (RETROSPECTIVE mode only): NEVER reference anything dated
after the chat context's `meta.temporal_cutoff_utc`. If the chat context's
cutoff and this file's stated Knowledge Cutoff ever disagree, treat the
EARLIER date as authoritative and flag the mismatch — don't silently pick
one.

## What You Produce

Output: `content/preseason-2025/preseason_content.json`

### 1. Meta Block (with seeded threads)

```json
{
  "meta": {
    "season": 2025,
    "type": "preseason",
    "generated_by": "write-preseason agent",
    "threads": [
      {
        "id": "chudders-tank-payoff",
        "status": "opened",
        "opened": "preseason-2025",
        "summary": "Two years of tanking gave Chudders a war chest of first-round picks -- does it finally turn into a real roster in 2025?",
        "last_touched": "preseason-2025"
      }
    ]
  }
}
```

- Seed **3-6 threads** — storylines worth tracking across the season (a
  bold prediction, a roster question, a rivalry angle). Draw them from real
  `team-profiles.json` content (roasts, needs, draft capital), not
  generic filler.
- `id`: a stable kebab-case slug. Weekly writers will reference this exact
  string later — make it specific and memorable, not `thread-1`.
- `status` is always `"opened"` here — the other three states
  (`continued`/`paid_off`/`dropped`) only make sense once a later week
  touches the thread.
- `opened` and `last_touched` are both the literal string
  `"preseason-2025"` (a period label, matching this site's "week N"
  labeling convention, not a calendar date).
- Keep `generated_by: "write-preseason agent"` verbatim — matches the
  shipped 2026 precedent (no code reads this field either way, but
  consistency costs nothing).

### 2. Essay

**200-350 words** (measured from the real shipped 2026 essay: 211 words,
~7 `\n\n`-delimited paragraphs). **Do not use `write-week.md`'s 400-700
word convention** — that's sized for a column competing against
confessionals, mailbag, and picks sections; this is a single long-form
piece.

Include `{{media:slot_id}}` tokens between paragraphs where a visual beat
belongs — see Media Slots below for the exact schema each token needs a
matching entry for.

### 3. Media Slots

2-4 entries, same schema as `render-preseason.md` expects:

```json
{
  "slot_id": "preseason-2025-essay-opener",
  "intent": "one sentence describing what should appear here and why",
  "source": {
    "type": "giphy",
    "search_query": "...",
    "fallback_query": "..."
  },
  "alt_text": "..."
}
```

A `"type": "custom"` slot (local video, `local_path` instead of a search
query) is optional — only include one if there's an actual asset to point
at; don't invent a hero video slot with no backing file.

### 4. Rankings

Exactly 12 entries, ranks 1-12 each used once:

```json
{
  "rank": 1,
  "team_name": "...",
  "owner": "...",
  "tier": "Contender | Frisky | Trust the Process | Fraud",
  "blurb": "..."
}
```

- **Blurb: 35-60 words** (measured: 2026 blurbs average 42 words — not
  `write-week.md`'s 100-200 word convention).
- `tier` must be one of the four values above, exactly.
- Cross-reference `team-profiles.json`'s `roast` / `keyPlayers` / `needs`
  per team while drafting — the blurb should read as an evolution of that
  material, not a disconnected new take.

## Critical Rules

1. **Respect the Knowledge Cutoff section above** — this is the single
   most important rule for this piece specifically. Ground truth here is
   `team-profiles.json` + pre-2025 history; there's no `week_data.json` to
   check numbers against, so err toward omission over invention.
2. Never hallucinate a stat, trade, or draft slot — check against
   `team-profiles.json` before writing it down.
3. Never confuse team/owner names — cross-reference exactly.
4. Second-person voice for blurbs, same as weekly rankings.
5. Every `{{media:*}}` token in the essay has a matching `media_slots[]`
   entry with that exact `slot_id`.
6. Seed the threads ledger per the Meta Block section — this is this
   piece's unique responsibility (weekly writers only read and extend it).

## Output Format

Write to `content/preseason-2025/preseason_content.json`. Print a summary:
mode declared (RETROSPECTIVE/FORWARD-LOOKING), essay word count, blurb word
count range, number of threads seeded, number of media slots.

## Post-Write Validation

Run this structural sanity check (shared with `/edit-preseason`'s
Pre-Review Validation — single source of truth for what a structurally
valid preseason JSON looks like):

```bash
python << 'PYEOF'
import json, re

content = json.load(open("content/preseason-2025/preseason_content.json", encoding="utf-8"))

for key in ("meta", "essay", "media_slots", "rankings"):
    assert key in content, f"missing top-level key: {key}"

rankings = content["rankings"]
assert len(rankings) == 12, f"expected 12 rankings, got {len(rankings)}"
assert {r["rank"] for r in rankings} == set(range(1, 13)), "ranks must be exactly 1-12, each once"

VALID_TIERS = {"Contender", "Frisky", "Trust the Process", "Fraud"}
for r in rankings:
    assert r["tier"] in VALID_TIERS, f"invalid tier '{r['tier']}' for {r['team_name']}"

essay_tokens = set(re.findall(r"\{\{media:([\w-]+)\}\}", content["essay"]))
slot_ids = {s["slot_id"] for s in content["media_slots"]}
# Every token used must resolve to a defined slot; the reverse isn't required --
# a "custom"/hero slot renders separately and is never referenced inline.
assert essay_tokens.issubset(slot_ids), f"essay references undefined slot(s): {essay_tokens - slot_ids}"

threads = content.get("meta", {}).get("threads", [])
assert 3 <= len(threads) <= 6, f"expected 3-6 seeded threads, got {len(threads)}"
for t in threads:
    for field in ("id", "status", "opened", "summary", "last_touched"):
        assert field in t, f"thread {t.get('id')} missing field '{field}'"
    assert t["status"] == "opened", f"thread {t['id']} status must be 'opened' at preseason, got '{t['status']}'"

print("STRUCTURAL CHECK: PASS")
PYEOF
```

## Usage

```
/write-preseason 2025
```

The argument is the season year to generate preseason content for.
