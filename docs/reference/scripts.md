# Key scripts (Jailyard)

> Moved out of CLAUDE.md 2026-08-20 (size cap).

| Script                                 | Purpose                                                              |
| -------------------------------------- | -------------------------------------------------------------------- |
| `fetch_sleeper.py`                     | Fetch season data from Sleeper API                                   |
| `scripts/extract_week_data.py`         | `season_combined.json` → per-week writer packets (as-of-week slices) |
| `scripts/generate_expanded_week.py`    | `week{N}_data_expanded.json` companions (games map)                  |
| `scripts/generate_nfl_games.py`        | Per-game NFLGame entities (EPA, injuries) from `data/external/`      |
| `scripts/fetch_nflreadpy.py`           | nflreadpy caches → `data/external/*.parquet`                         |
| `scripts/fetch_league_settings.py`     | Sleeper league rules → `data/{season}/league_settings.json`          |
| `scripts/verify_week_content.py`       | Edition validator (structure, data accuracy, chat, ranking order)    |
| `scripts/verify_ranking_judgment.py`   | Ranking judgment gate (G0-G5)                                        |
| `scripts/migration_census.py`          | Zero-post-cutoff-facts census over packets + compiled states         |
| `scripts/canon_checks.py`              | Sanitizer-artifact pre-render gate                                   |
| `scripts/parse_whatsapp.py`            | Raw WhatsApp export → `chat/parsed_messages.json`                    |
| `scripts/map_chat_deterministic.py`    | Chat MAP stage (monthly chunks)                                      |
| `scripts/reduce_chat_deterministic.py` | Chat REDUCE stage → analytics                                        |
| `scripts/build_chat_context.py`        | Per-edition sanitized chat context (`--no-ai` deterministic)         |
| `scripts/generate_chat_provenance.py`  | Chat pipeline provenance (verify / receipt-bound rebuild)            |
| `scripts/generate_player_arcs.py`      | Cross-season player arcs (local only)                                |
| `scripts/generate_franchise_wings.py`  | Franchise data files keyed by roster_id                              |
| `scripts/fetch_draft_picks.py`         | Sleeper draft-pick backfill                                          |
| `scripts/derive_historical_rosters.py` | Per-week roster snapshots                                            |
| `scripts/claims_ledger.py`             | Scoreable claims with resolution rules fixed at claim time           |
| `scripts/resolve_media.py`             | Resolve media picks to CDN URLs                                      |
| `scripts/describe_media.py`            | Catalog league media via headless Claude (`--backend claude-cli`)    |
