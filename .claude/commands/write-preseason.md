# Write the Preseason Edition

Produce `content/preseason-2025/preseason_content.json`: the season-opening
edition. The product bar is `content/editorial-standard.md`; read it first.

This edition sets the season's table: twelve preseason power rankings argued
from rosters, draft classes, franchise trajectories, and the league's
offseason chat, plus whatever sections the offseason material earns. Positions
taken here are the receipts every later edition grades.

## Preflight (mandatory)

```bash
python scripts/build_preseason_evidence.py --verify
```

The writer bundle lives in gitignored private custody at
`private_bundles/preseason-2025/preseason_evidence.json`, verified against
the tracked public manifest
`content/preseason-2025/preseason_evidence.manifest.json` (edition, cutoff,
canonical hash, counts, lineage). An absent or hash-mismatched bundle is a
hard stop: regenerate with `python scripts/build_preseason_evidence.py`,
never write from memory or a stale copy.

## Sources

The preseason writer reads exactly these:

1. **`league_settings` inside the bundle** -- the league's own rules. The
   starting lineup is **QB, RB, RB, WR, WR, WR, TE, FLEX, K, DEF, DL, LB, DB**
   (13 starters), with 13 bench, 4 taxi and 2 IR, half-PPR receiving, and full
   IDP scoring (solo tackle 1.0, assist 0.5, pass defensed 2.0, interception
   3.0, sack 3.0). State the lineup where a reader needs it to follow an
   argument, and show the arithmetic on any roster or IDP claim rather than
   asserting it.

2. **`private_bundles/preseason-2025/preseason_evidence.json`** -- the
   complete league-data source for this edition: team identities, the 2025
   draft, the offseason transaction log, 2022-2024 results, complete cutoff
   rosters for all 12 teams, and exact chat quotes (author, timestamp, team,
   fact_id), every item admitted at or before the preseason cutoff
   (`cutoff_utc` in the file). It contains facts only.
3. **Contemporaneous coverage** published at or before the cutoff, cited
   with its publication date.

Do not open any other league store for this edition: the season-long data
files describe a season this edition has not seen. Chat quotes are verbatim
from the evidence bundle. Nothing dated after the cutoff is admissible.

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
deletion. That asymmetry has already cost this column real human, comic and
dramatic material once. Rewriting a beat in better language is the expected
repair; cutting it is the exception that has to be argued.

## Shape

Required: `meta` ({season, type: "preseason", `ranking_source`}) and
`rankings` (12 argued positions: rank, team_name, owner, blurb). The ranking
order is backed by a judgment record that passes
`python scripts/verify_ranking_judgment.py --record <path>` and is declared
as `meta.ranking_source`; a published ranking never falls back to an
arithmetic sort. Optional: `meta.threads` to open season-long storylines;
any sections the material earns.

## After writing

```bash
python scripts/canon_checks.py --preseason
python scripts/verify_week_content.py --preseason --pretty
```

The second command is the executable preseason ranking gate: authored
content exists, `meta.ranking_source` resolves to a gate-passed judgment
record, and the published order matches it. Fix until clean. Then
`/edit-preseason`.
