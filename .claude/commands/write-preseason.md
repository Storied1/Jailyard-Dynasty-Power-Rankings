# Write the Preseason Edition

Produce `content/preseason-2025/preseason_content.json`: the season-opening
edition. The product bar is `content/editorial-standard.md`; read it first.

This edition sets the season's table: twelve preseason power rankings argued
from rosters, draft classes, franchise trajectories, and the league's
offseason chat, plus whatever sections the offseason material earns. Positions
taken here are the receipts every later edition grades.

## Sources

`content/writer-inputs.json` governs. For the preseason, load:

1. `content/preseason-2025/preseason_chat_context.json` (cutoff in
   `meta.temporal_cutoff_utc`; quotes verbatim)
2. `content/team-profiles.json` (team identity registry)
3. Franchise history: `data/franchises/{roster_id}.json`,
   `data/2025/draft_picks.json`, the season-opening roster snapshot
   (`data/2025/fantasy_rosters/week1.json`), player arcs for multi-season
   trajectories
4. Contemporaneous NFL coverage published at or before the cutoff, cited with
   its date

Nothing dated after the cutoff is admissible; from this edition's vantage the
season has not been played.

## Shape

Required: `meta` ({season, type: "preseason"}) and `rankings` (12 argued
positions: rank, team_name, owner, blurb). Optional: `meta.threads` to open
season-long storylines; any sections the material earns.

## After writing

```bash
python scripts/canon_checks.py --preseason
```

Then `/edit-preseason`.
