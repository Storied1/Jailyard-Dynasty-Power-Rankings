# Known Patterns (Jailyard)

> Moved out of CLAUDE.md 2026-08-20 (size cap). Read before data-pipeline or renderer work.

- Data loading: try cached JSON → catch → live Sleeper API → catch → error UI
- IIFEs for scope isolation; `idFromName()` for HTML-safe ids; View
  Transitions API; Speculation Rules; Intersection Observer `.visible`
- `scripts/shared.py` is canonical for `load_json`, `save_json_canonical`,
  `parse_ts`, `admissible`, path constants, Ollama config. Never define local
  copies.
- Theme has two toggle paths: nav button (config.js) + keyboard `t`/`T`
  (index.html only); keep in sync.
- `franchise_map` stores CURRENT team names; historical names live in
  `data/franchises/` per season.
- **Momentum label sets** — team: `opening | early | cooling | collapsing |
steady | hot | surging`; matchup: `too early | coin flip | slight edge |
heavy lean | upset brewing`. Defined in `shared.py`,
  `extract_week_data.py`, `verify_week_content.py`; adding a label updates
  all three in one commit.
- **Script import pattern:** scripts runnable under pytest AND directly
  insert `scripts/` into `sys.path[0]` before `from shared import ...` (see
  `scripts/fetch_nflreadpy.py`).
- **Idempotency convention:** generators write via `save_json_canonical`;
  re-extraction idempotency rides input-hash manifests, not byte-parity with
  prettier-formatted committed files. Data-layer spec:
  `docs/superpowers/specs/2026-05-02-jailyard-content-depth-design.md`.
- `shared.load_json(path)` returns `None` on a missing file; pass
  `required=True` for a loud error.
- `build_chat_context.py` has no `--all` mode — loop `--week N`.
- `list(set)` order is non-deterministic (`PYTHONHASHSEED` unpinned) — use
  `sorted()` before serializing set contents.
- `{{media:*}}` token validation is `essay_tokens.issubset(slot_ids)`, not
  equality — a `type:"custom"` hero slot renders separately.
- `verify_week_content.py` Tier 1 has a `warnings` channel beside `errors`
  — structural violations are errors; heuristic findings are warnings.
- `LeagueState.standings()` must be passed `season=` explicitly — an
  unqualified call folds every admitted game across seasons.
