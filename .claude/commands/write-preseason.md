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

The preseason writer reads exactly two things:

1. **`private_bundles/preseason-2025/preseason_evidence.json`** -- the
   complete league-data source for this edition: team identities, the 2025
   draft, the offseason transaction log, 2022-2024 results, complete cutoff
   rosters for all 12 teams, and exact chat quotes (author, timestamp, team,
   fact_id), every item admitted at or before the preseason cutoff
   (`cutoff_utc` in the file). It contains facts only.
2. **Contemporaneous NFL coverage** published at or before the cutoff, cited
   with its publication date.

Do not open any other league store for this edition: the season-long data
files describe a season this edition has not seen. Chat quotes are verbatim
from the evidence bundle. Nothing dated after the cutoff is admissible.

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
