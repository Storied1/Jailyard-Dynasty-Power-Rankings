# Write an Edition (week ${WEEK})

Produce `content/weeks/week${WEEK}_content.json`: this week's edition of The
Jailyard column. The product bar is `content/editorial-standard.md`; read it
first, every time.

## Sources

`content/writer-inputs.json` is the complete registry of admissible sources.
Every fact, quote, and storyline traces to a registered source dated at or
before this edition's cutoff (`meta.temporal_cutoff_utc` in the chat context).
Chat quotes are verbatim. Numbers come from the data packet; player stat lines
use the packet's pre-rendered `game_context` lines. If it cannot be traced, it
does not go in.

For week ${WEEK}, load:

1. `content/weeks/week${WEEK}_data.json` (+ `_data_expanded.json` for per-game
   NFL depth: scores, Vegas lines, injuries, weather, EPA)
2. `content/weeks/week${WEEK}_chat_context.json`
3. Franchise history as needed: `data/franchises/{roster_id}.json`, draft
   picks, player arcs (cite nothing from later in the season than week ${WEEK})
4. Published editions of this run (the callback surface)
5. Any accepted decisions in `content/rankings/`
6. Contemporaneous coverage, cited with a publication date at or before the
   cutoff. Primarily NFL, and not limited to it: the wider sports world and
   recognizable news or cultural events are admissible on the same terms
   whenever they bear on the column

The source rule binds facts, quotes and storylines. It does not bind the
writing: original metaphor, parody, coinage, humor and ordinary allusion are
authored expression and need no registered source. A checkable outside factual
predicate asserted inside one still needs admissible pre-cutoff support.

## Interpretive warrant

The subject is twelve people, not twelve rosters, and the reach of a reading
is bounded by its evidence. The ladder is in `content/editorial-standard.md`:
words plus a decision support an attributed belief; repeated conduct supports
a qualified characterization; a roster alone supports "bets as if" and never
private motive; thin evidence gets an open question and never a fabricated
arc. No gate can catch a violation here, which is exactly why it is the
writer's job.

## Revising

When a revision removes a passage, name the editorial function it was doing:
factual grounding, causal explanation, character, tension, comedy, surprise,
comparison, wider meaning, or a receipt a later edition can settle. **A
function that was working survives somewhere in the rebuilt module**, unless
it is explicitly ruled unsupported, redundant, unsuccessful or unearned.
Wording, location, length, evidence selection and structure may all change.
This protects function at the beat and module level, never sentence count, and
never freezes an existing shape.

Deletion is cheaper than successful replacement and the gates only ever score
deletion. Rewriting a beat in better language is the expected repair; cutting
it is the exception that has to be argued.

## Shape

Required: `meta` ({week, season, type, `ranking_source`}) and `rankings`
(12 entries: rank, team_name, owner, record, blurb; ordered by the edition's
judgment). Publishing rankings without a gate-passed `meta.ranking_source`
fails `verify_week_content`; there is no fallback ordering. Everything else is earned per the
standard: sections exist because this week's material demands them, under
whatever keys fit; the renderer renders what exists. Optional continuity:
`meta.threads` (id, status opened|continued|paid_off|dropped, summary,
last_touched).

## Rankings judgment

The ordering is a set of argued positions, backed by a judgment record that
passes `python scripts/verify_ranking_judgment.py --record <path>` (structure,
non-arithmetic ordering, reasoned deviations, contender sanity, evidence
breadth, citation resolution). Declare it as `meta.ranking_source`.

## After writing

```bash
python scripts/verify_week_content.py --week ${WEEK} --pretty
```

Fix until clean. Then `/edit-week ${WEEK}`.
