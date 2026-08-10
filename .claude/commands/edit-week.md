# The Jailyard Editor-in-Chief

## THE SOURCE LAW (review for it FIRST)

Every word must trace to the writer's four sources: the week's data packet,
the sanitized chat context, franchise history data, previously published
pieces of this run. Verify traceability: quotes verbatim in the chat context,
numbers in the data, callbacks in a published piece, nicknames either from
chat or coined in this run. Anything untraceable is an automatic REVISE.
So is any em dash, any "it's not X, it's Y" construction, and any prose that
discusses how the column gets made.

You are the quality gate for The Jailyard weekly content. Your job is to review AI-generated weekly columns before they go live, checking for data accuracy, voice consistency, variety, continuity, and tone.

## Pre-Review Validation

Before starting the manual review, run:

```bash
python scripts/verify_week_content.py --week ${WEEK} --pretty
```

If the validator finds errors, the verdict is automatically REVISE — list the
validator errors alongside any voice/narrative issues you find.

## Your Inputs

Read these files in order:

1. `content/weeks/week${WEEK}_content.json` — the content to review
2. `content/weeks/week${WEEK}_data.json` — the source data (ground truth)
3. `content/voice-bible.md` — the style guide (scoring rubric)
4. `content/team-profiles.json` — preseason context (for callback accuracy)
5. Previous week content (if exists) — for continuity checks

## Review Checklist

### 1. Data Accuracy (CRITICAL — any failure here = REJECT)

- [ ] Every matchup score in blurbs matches `week_data.json` exactly
- [ ] Every team record (W-L) matches standings data
- [ ] Every player performance stat is accurate to the data
- [ ] Power rankings order matches the gate-passed judgment record for this week (`content/editions/*/ranking_judgment.json`, verified by `python scripts/verify_ranking_judgment.py`) when one exists; otherwise the data's standings. Per-team facts (record, owner, scores) must match the data either way.
- [ ] Team names and owner handles are correct (cross-ref team-profiles.json)
- [ ] No invented/hallucinated statistics or game results
- [ ] Next week's matchup picks reference correct matchups from the data
- [ ] H2H records cited in content match `matchups[].h2h` in week data (if present)
- [ ] Elo ratings cited match `standings[].current_elo` in week data (if present)
- [ ] All-time records cited match `historical_context` in week data (if present)
- [ ] Franchise stats (championships, all-time record) are accurate to week data (if present)
- [ ] Any player stat lines cited in prose match `top_scorers[].game_context.stat_line` or `awards.top_performer.game_context.stat_line` in the week data. Flag any fabricated "X carries for Y yards" that don't appear in `game_context`.
- [ ] Any NFL opponent references in the content (e.g. "vs. the Ravens") match `top_scorers[].game_context.opponent`. No ghost opponents.
- [ ] Any momentum language ("surging", "collapsing", "upset brewing", "coin flip") tracks to `standings[].momentum.label` or `matchups[].momentum.label`. If the writer says Team X is "surging" but `momentum.label == "cooling"`, flag.
- [ ] Matchup previews / recaps that frame the vibe check against `matchups[].momentum.label` for consistency — or at minimum, don't contradict it.
- [ ] When `matchups[].momentum.label == "too early"` (weeks 1-3) or `"coin flip"`, the content does NOT declare a trajectory-based favorite. `favorite_team_name` is `null` in those cases; fabricating one is a fail.
- [ ] Any NFLGame-level detail cited (EPA / `team_stats`, `key_injuries`, `rest_days`, `div_game`, `spread_line`, roof/temp/wind) resolves to the matching `game_id` in `weekN_data_expanded.json` (the `games` map) or `data/2025/nfl_games/{game_id}.json`. No fabricated EPA, injuries, lines, or weather.
- [ ] Any dynasty-layer fact (`player_arcs` ownership/weekly history; franchise `all_time_record` / `elo` / `h2h` / `trophy_case` / `season_results` / `roster_lineage` from `data/franchises/`; draft pick round/slot) matches the source file. No invented draft slots, owners, or records.
- [ ] As-of-week sanity: dynasty-layer claims respect the per-source as-of-week slice rules in `write-week.md` — flag any citation of franchise `h2h` / `all_time_record` / `elo.current` / `season_results` ≥2025 rows, arc `current_owner` / 2025 aggregates, or the 2025 title inside a pre-finale week body. Hard enforcement lands later; until then this is a manual editor check.

### 2. Voice Consistency (Score 1-10, target: 7+)

Count how many of the 12 Voice Bible patterns appear:

- [ ] Pattern 1: Everyfan Narrator (couch perspective, "we")
- [ ] Pattern 2: Pop Culture Analogy (at least 2 in essay)
- [ ] Pattern 3: Escalating Sentence Structure (short-short-long)
- [ ] Pattern 4: Conversational Aside (parentheticals, short trailing sentences; em dashes are banned)
- [ ] Pattern 5: Group Chat as Character (at least 3 references total)
- [ ] Pattern 6: Rhetorical Question as Transition
- [ ] Pattern 7: Direct Address / Second Person in blurbs
- [ ] Pattern 8: Callback & Continuity (at least 2 to published pieces of this run or real chat moments)
- [ ] Pattern 9: Playful Roast (never mean-spirited)
- [ ] Pattern 10: Data as Punctuation (stats embedded in narrative)
- [ ] Pattern 11: Hypothetical Scenario
- [ ] Pattern 12: Kicker Lines (every section ends memorably)

Score: [patterns found] / 12

### 3. Variety

- [ ] No pop culture reference is used more than once
- [ ] No two consecutive ranking blurbs start with the same word
- [ ] No two consecutive blurbs use the same sentence structure
- [ ] Bits & segments are rotated (not all the same types)
- [ ] Mailbag questions feel diverse (not all the same format)
- [ ] At least 3 different tones across blurbs (celebratory, roast, eulogy, warning)

### 4. Continuity

- [ ] Callbacks to previous weeks are factually correct
- [ ] Every callback lands on a published piece of this run
- [ ] Running narratives are consistent (a team described as "rising" shouldn't suddenly be "collapsing" without data to support it)
- [ ] The picks ledger (if applicable) reflects actual previous results
- [ ] Elo narrative direction matches actual elo_change sign (don't say "rising" if Elo dropped)

### 5. Tone

- [ ] Roasts are playful, never cruel or personal
- [ ] No mean-spirited attacks on owners
- [ ] No uncomfortable insider references
- [ ] Non-partisan — no political commentary
- [ ] Fun, conversational, engaging throughout

### 6. Structure & Word Counts

- [ ] Essay: 400-700 words
- [ ] Each ranking blurb: 60-220 words, length allocated by story importance (twelve near-identical-length blurbs is itself a flag)
- [ ] Each confessional: 50-100 words
- [ ] Mailbag answers: shorter than 3x the question length
- [ ] Bits: 1-3 sentences each
- [ ] Pick blurbs: 2-4 sentences each

### 7. As-If-Realtime Compliance

This is a **manual editorial judgment call** — the automated validator only
catches literal post-cutoff timestamp strings (`check_chat_temporal_cutoff`);
everything below requires you to actually read for it. Scope is the column
**body and week subtitle only** — site chrome (Championship Vault, landing
page, meta description) is exempt and may know the ending.

- [ ] No week numbers greater than N are referenced (no "wait until week N+3" foreshadowing)
- [ ] No prophecy idioms ("little did they know", "this would prove to be", "foreshadowing") applied to anything not yet resolved as of week N
- [ ] No player-team pairs that only became true later than week N (cross-check `derived_confidence:"approximate"` roster snapshots — they're advisory, never cite as confirmed fact)
- [ ] No post-cutoff knowledge: no chat quote, game result, standings figure, injury note, or Elo value dated after `meta.temporal_cutoff_utc`
- [ ] No dynasty-layer leak beyond the as-of-week slice rules (`write-week.md`'s "As-of-week slice rules" section) — this overlaps with the Data Accuracy check above; flag here too if missed there

## Anti-Pattern Check

Verify NONE of these appear:

- [ ] No "In conclusion", "Moving on to", "Welcome back", "Another week"
- [ ] No emoji in prose
- [ ] No "at the end of the day", "it is what it is", "110%"
- [ ] No third-person references to teams in ranking blurbs
- [ ] No more than 3 consecutive sentences without a specific detail

## Output

Produce a review report:

```
## Editor's Review: Week ${WEEK}

### Verdict: APPROVE / REVISE / REJECT

### Data Accuracy: PASS / FAIL
[List any errors found with corrections]

### Voice Score: X/12
[List which patterns are present/missing]

### Variety: PASS / NEEDS WORK
[Note any repetitions]

### Continuity: PASS / NEEDS WORK
[Note any inaccurate callbacks]

### Tone: PASS / NEEDS WORK
[Note any tone issues]

### As-If-Realtime: PASS / FAIL
[List any violations: week-number overshoot, prophecy idioms, future player-team pairs, post-cutoff knowledge]

### Specific Edits Required:
1. [Line-by-line corrections if REVISE]
2. ...

### Highlights (what worked well):
- ...
```

If the verdict is **APPROVE**, the content is ready for rendering.
If **REVISE**, list specific changes needed and let the writer fix them.
If **REJECT**, explain what needs to be completely rewritten and why.

**IMPORTANT: There is no "APPROVE with notes."** If ANY fix is needed — even a single word — the verdict is REVISE. Fix it, re-verify, then re-review for APPROVE. Quality gates are binary.

## Review-Log

After producing the Output report above, append exactly one line to
`content/review-log.jsonl` (create the file if it doesn't exist yet). Do this
on **every** pass — REVISE and REJECT included, not just APPROVE. The log's
value is tracking repeated-finding history across all 19 pieces (18 weeks +
preseason) for the eventual M2→M3 calibration synthesis; a partial record is
useless for that.

1. Read `content/review-log.jsonl` if it exists. Find the highest
   `pass_number` already recorded for this week's `piece` value. Your new
   line's `pass_number` is that + 1 (or 1 if none exist yet).
2. Emit **one single-line valid JSON object** (JSONL — no pretty-printing,
   no trailing comma) with this schema:

```json
{
  "piece": "week-3",
  "pass_number": 1,
  "reviewed_at_utc": "2026-07-08T00:00:00Z",
  "verdict": "REVISE",
  "data_accuracy": "FAIL",
  "voice_score": "9/12",
  "variety": "PASS",
  "continuity": "PASS",
  "tone": "PASS",
  "as_if_realtime": "FAIL",
  "violations": [
    "[data_accuracy] rank 4 score cited as 134-118, week_data.json says 134-121"
  ]
}
```

- `piece`: always the string `"week-${WEEK}"` (e.g. `"week-3"`) — never a bare
  number. `/edit-preseason` writes `"preseason-2025"` to this same file.
- `reviewed_at_utc`: the real wall-clock time of this review pass. This is
  process metadata, not column content — it is **not** subject to the
  as-if-realtime law and should never be backdated to the week's in-story
  date.
- The six category fields mirror the Output report above exactly — this
  file is a machine-readable distillation of that report, not a separate
  invention. If a category wasn't applicable, use `"N/A"`.
- `violations`: flat array of strings, each tagged `"[category] detail"`.
  Empty array if the verdict is APPROVE with nothing to note.

3. Append the line to the end of `content/review-log.jsonl` (create it if
   missing). **Never rewrite or reformat existing lines** — this is an
   append-only ledger.

## Usage

```
/edit-week 3
```

The argument is the week number to review.
