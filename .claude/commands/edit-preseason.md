# The Jailyard Preseason Editor

## THE COPY LAW (review for it FIRST)

Any of these is an automatic REVISE, no exceptions: a reference to legacy copy
(pre-2026-08-10 columns, old preseason essays, team-profiles roasts, retired
lexicon nicknames); an em dash anywhere in prose; an "it's not X, it's Y"
construction; prose that narrates the column's own methodology. Chat quotes
must be verbatim-verified against the sanitized chat context.

You are the quality gate for The Jailyard's preseason-2025 content — the
retrospective preview written under the as-if-realtime law (nothing past
2025-09-03). Sibling to `/edit-week`, scoped to the simpler
`{meta, essay, media_slots, rankings}` preseason contract instead of a
weekly column's confessionals/mailbag/bits/picks.

## Pre-Review Validation

Before starting the manual review, run this structural sanity check (no
persisted validator exists yet for the preseason contract — see
`write-week.md`'s note on this same script for why):

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
# a "custom"/hero slot renders separately (see render-preseason.md's Hero Section)
# and is never referenced via an inline {{media:*}} token.
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

If this fails, the verdict is automatically REVISE — fix the structural
issue before doing the manual review below.

## Your Inputs

Read these files in order:

1. `content/preseason-2025/preseason_content.json` — the content to review
2. `content/voice-bible.md` — the style guide (scoring rubric)
3. `content/team-profiles.json` — ground truth for names, tiers, rosters
4. `content/preseason-2026/preseason_content.json` — tonal/length reference (NOT a data source — it's forward-looking chrome, not subject to the as-if-realtime law)

There is no "previous week" input — preseason is the first piece in the
running-blog chain.

## Review Checklist

### 1. Data Accuracy (CRITICAL — any failure here = REJECT)

- [ ] Team names and owner handles are correct (cross-ref `team-profiles.json`)
- [ ] Every `tier` value is one of `Contender` / `Frisky` / `Trust the Process` / `Fraud`
- [ ] Rankings 1-12 are each used exactly once
- [ ] No invented draft picks, trades, or roster facts — cross-ref `team-profiles.json`'s `draftPicks`/`keyPlayers`
- [ ] No fabricated 2025-season results of any kind (see As-If-Realtime below — this is the sharpest edge of that law for this piece specifically)

### 2. Voice Consistency (Score 1-10, target: 7+)

Same 12 Voice Bible patterns as `/edit-week` — see `content/voice-bible.md`.
Score: [patterns found] / 12

### 3. Variety

- [ ] No two consecutive ranking blurbs start with the same word
- [ ] No two consecutive blurbs use the same sentence structure
- [ ] At least 3 different tones across the 12 blurbs (hype, skepticism, roast, cautious optimism)

### 4. Continuity

No predecessor content to check callbacks against. Instead:

- [ ] The seeded `meta.threads` entries (3-6) are genuinely distinct storylines, not restatements of the same idea
- [ ] Each thread's `summary` is specific enough that a week-6 writer could pick it up without re-reading the whole essay
- [ ] Thread `id`s are stable kebab-case slugs (future weeks will reference them by this exact string)

### 5. Tone

- [ ] Roasts are playful, never cruel or personal
- [ ] No mean-spirited attacks on owners
- [ ] Non-partisan — no political commentary
- [ ] Fun, conversational, engaging throughout

### 6. Structure & Word Counts

Calibrated against the real shipped 2026 preview, not `write-week.md`'s
weekly convention (that's sized for a column competing with confessionals/
mailbag/picks — this piece is a single long-form essay + rankings).

- [ ] Essay: 200-350 words
- [ ] Each ranking blurb: 35-60 words

### 7. As-If-Realtime Compliance

**This is the strictest version of this check anywhere in the pipeline.**
At the preseason vantage point, zero games in the 2025 season have been
played — there is no week-N exception the way a mid-season column gets one.

- [ ] Rule: `season < 2025`, full stop. No 2025 game result, trade, injury, waiver move, or in-season storyline appears anywhere — only things true as of the last offseason day before Week 1
- [ ] No prophecy idioms framed as foreshadowing ("this pick would prove...", "nobody knew yet...")
- [ ] No player-team pairs that only became true after the season started (a trade that happened in-season, a name that changed via a later move)
- [ ] Scope: essay + rankings blurbs. (There's no "week subtitle" for this piece — chrome/nav labeling is exempt as always.)

## Anti-Pattern Check

Verify NONE of these appear:

- [ ] No "In conclusion", "Moving on to", "Welcome back"
- [ ] No emoji in prose
- [ ] No "at the end of the day", "it is what it is", "110%"
- [ ] No third-person references to teams in ranking blurbs
- [ ] No more than 3 consecutive sentences without a specific detail

## Output

Produce a review report:

```
## Editor's Review: Preseason 2025

### Verdict: APPROVE / REVISE / REJECT

### Data Accuracy: PASS / FAIL
[List any errors found with corrections]

### Voice Score: X/12
[List which patterns are present/missing]

### Variety: PASS / NEEDS WORK
[Note any repetitions]

### Continuity: PASS / NEEDS WORK
[Note any weak or redundant seeded threads]

### Tone: PASS / NEEDS WORK
[Note any tone issues]

### As-If-Realtime: PASS / FAIL
[List any violations — this is the highest-stakes check for this piece]

### Specific Edits Required:
1. [Line-by-line corrections if REVISE]
2. ...

### Highlights (what worked well):
- ...
```

**IMPORTANT: There is no "APPROVE with notes."** If ANY fix is needed — even
a single word — the verdict is REVISE. Fix it, re-verify, then re-review for
APPROVE. Quality gates are binary.

## Review-Log

Same mechanism as `/edit-week` — append exactly one line to
`content/review-log.jsonl` after producing the Output report above, on
every pass (REVISE and REJECT included):

```json
{
  "piece": "preseason-2025",
  "pass_number": 1,
  "reviewed_at_utc": "2026-07-08T00:00:00Z",
  "verdict": "APPROVE",
  "data_accuracy": "PASS",
  "voice_score": "10/12",
  "variety": "PASS",
  "continuity": "PASS",
  "tone": "PASS",
  "as_if_realtime": "PASS",
  "violations": []
}
```

`pass_number` = 1 + the highest existing `pass_number` already recorded for
`"piece": "preseason-2025"` in that file (or 1 if none exist yet).
`reviewed_at_utc` is real wall-clock metadata — not subject to the
as-if-realtime law. Append-only; never rewrite existing lines.

## Usage

```
/edit-preseason 2025
```

The argument is the season year to review.
