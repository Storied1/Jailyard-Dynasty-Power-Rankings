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
6. Contemporaneous NFL coverage, cited with a publication date at or before
   the cutoff

## Shape

Required: `meta` ({week, season, type, and `ranking_source` when a judgment
record exists}) and `rankings` (12 entries: rank, team_name, owner, record,
blurb; ordered by the edition's judgment). Everything else is earned per the
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
