# Data layer (Jailyard)

> Full per-file detail moved out of CLAUDE.md 2026-08-20 (size cap). The one-line law
> for each file stays in CLAUDE.md; this file carries the elaboration.

- `config.js` — league branding, Sleeper IDs, nav links (loaded by all pages)
- `data/{year}/season_combined.json` — main season data file
- `data/league_history.json` — cross-season analytics (Elo, H2H, records)
- `content/weeks/week{N}_data.json` — per-week writer packet. **Cutoff-safe by
  construction:** every cutoff-sensitive field (h2h totals + `last_meeting`,
  `historical_context` records, Elo/all-time enrichment) is derived as-of week
  N by `extract_week_data.py` (`as_of_h2h`, `as_of_records`,
  `compute_as_of_history`); `python scripts/migration_census.py --all`
  enforces zero post-cutoff facts across every packet by exit code.
  `championships`/`best_win_streak` are intentionally absent in-season.
- `content/weeks/week{N}_data_expanded.json` — denormalized companion:
  top-level `games{}` map keyed by `game_id`; manifest-hash idempotent
  (`data/2025/nfl_games/_expanded_manifest.json`)
- `data/2025/nfl_games/{game_id}.json` — per-NFL-game entity (scores, EPA
  `team_stats`, `key_injuries`, `rest_days`, `div_game`, `spread_line`,
  roof/temp/wind). `game_context` references these by `game_id`
- `data/2025/fantasy_rosters/week{1..17}.json` — per-week roster snapshots
  with real starters
- `data/2025/league_settings.json` — the league's own rules from Sleeper:
  starting lineup **QB/RB/RB/WR/WR/WR/TE/FLEX/K/DEF/DL/LB/DB** (13), 13 bench,
  4 taxi, 2 IR, half PPR, full IDP scoring. Registered source class; projected
  into the preseason bundle as `league_settings`. Regenerate:
  `python scripts/fetch_league_settings.py --season 2025` (the ONLY network step;
  the bundle builder reads this file and never fetches). Without it the column
  asserts lineup math a reader cannot check
- `data/{year}/draft_picks.json` — Sleeper draft picks per season
- `data/2025/player_arcs/{player_id}.json` + `_index.json` — cross-season
  player arcs 2022-2025; **regenerate locally only** (inputs include
  gitignored `players.json` + stats caches)
- `data/franchises/{roster_id}.json` + `_index.json` — franchise data:
  trophy case, h2h, roster lineage, season results, historical names
- `content/team-profiles.json` — team identity registry (roster_id, name,
  owner); schema `scripts/schemas/team_registry.schema.json`
- `content/rankings/` — accepted structured editorial decisions
- `content/weeks/week{N}_chat_context.json` (+
  `content/preseason-2025/preseason_chat_context.json`) — sanitized league
  chat per edition: verbatim quotes, storylines, league memory, every field
  admitted by exact timestamp at or before the cutoff. Arcs/jokes carry
  through-cutoff `count` + exact `first_seen_at`/`last_observed_at` bounds;
  no status fields; use `last_observed_at` for recency
- `content/chat/` — chat analytics + `name-map.json` (WhatsApp name → real
  name, team, roster_id); `chat/` raw exports and `.map_cache/` are
  gitignored
- `data/external/*.parquet` — gitignored nflreadpy caches
- `data/{year}/nfl_stats_week{N}.json` — gitignored Sleeper stats cache
- Sleeper API (`https://api.sleeper.app/v1`) as live fallback
