# The Jailyard Continuity/Canon Keeper

A standing pre-render adversarial gate. Complements `/edit-week`'s voice/quality
gate — it doesn't replace it. Where `/edit-week` asks "is this good writing,"
`canon-check` asks "is the underlying data even in the right shape, and does
this week stay consistent with everything published before it." Run it after
`/write-week ${WEEK}`, before `/pick-media ${WEEK}` / render — and it's safe to
run even before `/write-week` has been called at all, since its first check
only needs the sanitizer's source artifacts, not written content.

## Step 1: Artifact Check (always runs)

```bash
python scripts/canon_checks.py --week ${WEEK}
```

This validates the _source artifacts_ the as-of-week sanitizer produces —
`week${WEEK}_chat_context.json` has a `league_memory` block shaped
`{culture, lexicon, running_jokes}`, and `week${WEEK}_data.json`'s standings
entries have `current_elo`/`peak_elo`/`all_time_record` present and
`championships`/`best_win_streak` absent (the in-season-omission rule). This
is exactly the check that would have caught the weeks 7-18 league-culture gap
before anyone ran `/write-week` against them.

If this step reports FAIL, stop here — don't proceed to Step 2. The data isn't
sanitized correctly; that has to be fixed at the source (`build_chat_context.py`
/ `extract_week_data.py`), not papered over in the content review.

## Step 2: Content/Continuity Check (only if content exists)

Check whether `content/weeks/week${WEEK}_content.json` exists.

**If it doesn't exist yet:** report "artifact checks only — content not yet
written" and stop. This is the expected state for any week that hasn't gone
through `/write-week` yet — not a gap, not an error.

**If it exists**, run:

```bash
python scripts/verify_week_content.py --week ${WEEK} --pretty
```

Then do a continuity pass: read `content/weeks/week${WEEK}_content.json`'s
callbacks/references against the `meta.threads` ledger (and previous weeks'
published content) and flag anything inconsistent with what earlier weeks
actually said — a callback to a joke, storyline, or prediction that doesn't
match what was actually published.

## Output

```
## Canon Check: Week ${WEEK}

### Artifact Check: PASS / FAIL
[List any issues, with file:line or field-path citations — no vague "looks off"]

### Content/Continuity Check: PASS / FAIL / SKIPPED (content not yet written)
[List any inconsistent callbacks, with the exact prior-week text being contradicted]

### Verdict: PASS / FAIL
```

**No "PASS with notes."** Same standard as `/edit-week`: if anything is wrong,
it's FAIL. Fix at the source, re-run, then re-check for PASS.

## Usage

```
/canon-check 7
```

The argument is the week number to check.
