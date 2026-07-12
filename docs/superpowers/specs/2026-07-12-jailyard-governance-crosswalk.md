# Jailyard Governance Crosswalk + Temporal Contract (lean — no DB, no scoring, no confidence aggregation)

Status: **Committed DRAFT / NOT-APPROVED** (shipped in `a0587fb`; content updated by the temporal/provenance pass). Supersedes the dead v4.1 governance design's machinery; retains its five real _functions_. Every claim below is labeled **IMPLEMENTED** (with the code path + passing test that proves it) or **PROPOSED / NOT IMPLEMENTED**.

## Why this exists

The chat-repair proved that prompt-level as-if-realtime rules + verifier Tier-3 are **not** an equivalent replacement for machine-checkable knowability. The committed writer contexts leaked future knowledge three ways, all verified on disk:

- **Lexicon values:** wk1 kept 38 terms but 18 still carried post-cutoff months (46 refs) — e.g. `brent -> 2026-03`, `nate -> 2026-04/05`. Key-gating without value-sanitizing leaks.
- **Aggregate counts:** wk1 `tanking` running-joke `total_frequency: 312` was all-time, not through-cutoff.
- **Month-granular comparison** admitted same-month-after-day-cutoff evidence (wk18 January recurrence whose messages post-date the Jan-6 cutoff).

One uniform rule fixes the class; ad-hoc per-field sanitizers do not.

## The Temporal Contract (uniform, exact-cutoff) — IMPLEMENTED

1. **Admissibility:** a writer-facing datum is admissible iff its exact tz-aware instant `<=` the piece's exact knowledge cutoff. — `shared.admissible` (`scripts/shared.py:181`), the single admitter at every gate: message window (`build_chat_context.filter_messages_in_window`, `scripts/build_chat_context.py:105`), prediction resolution incl. nested evidence (`test_resolve_predictions_skips_predictions_made_after_cutoff`, `test_resolve_predictions_gates_nested_evidence_and_local`), callbacks (`test_callbacks_gate_nested_prediction_evidence`). Full form matrix: `test_recompute_projection.py::test_admissible_table`.
2. **Exact cutoff, not month:** month-granular comparison is banned; `_month_le` is deleted. Month keys themselves are strict-parsed (`shared.month_key_strict`, `scripts/shared.py:212`; `test_shared.py::test_month_key_strict_rejects_non_instant`).
3. **Counts/aggregates are through-cutoff:** every emitted `count` is computed over admissible evidence only — `scripts/recompute_projection.py` (jokes `:254-283`, arcs `:231-235`); `test_recompute_projection.py::test_joke_count_semantics`, `::test_senderless_trade_raises_count`.
4. **Fail-closed:** missing/malformed/naive/date-only/month-only timestamps are rejected (`test_recompute_projection.py::test_inadmissible_ts_dropped_e2e`); an arc/joke with through-cutoff `count == 0` is DROPPED (`scripts/build_chat_context.py:554`, `:998`; `test_build_chat_context.py::test_find_active_arcs_drops_count_zero`); a missing or coarse cutoff fails closed (`test_canon_checks.py::test_arc_joke_semantics_missing_cutoff_fails_closed`, `::test_arc_joke_semantics_coarse_cutoff_rejected`).
5. **Internal retention:** full raw/all-time analytics are preserved internally (`content/chat/*.json`); only the writer-facing projection is gated. Two distinct layers guard this: the **raw-read ban** ("writers/drafters read only per-week sanitized artifacts") is a writer/agent INSTRUCTION (CLAUDE.md critical rule + `/write-week` contract, prompt-enforced); the machine-tested property is **projection independence** — the noninterference gate below proves the sanitized artifacts themselves carry no post-cutoff influence, not that an agent obeys the read ban.

**Noninterference (the hard gate) — IMPLEMENTED:** two worlds differing only by post-cutoff evidence produce byte-identical writer-facing sections at the cutoff, and every surface is detector-active (the same evidence DOES change all-evidence output). In-memory: `test_build_chat_context_noninterference.py::test_noninterference_all_sections_byte_identical_at_cutoff`, `::test_each_message_surface_is_detector_active`, `::test_prediction_axis_noninterference_and_detector_active`. Full-corpus: `build_chat_context.py --verify-noninterference --season 2025` exits 0 across preseason + weeks 1-18 (run green at Gate 3).

## Five retained functions

1. **Source/field qualification** — a persisted, field-level qualification VERDICT, **distinct from provenance** (provenance = lineage/hashing of inputs/code/outputs; qualification = per-field capability + temporal class). Provenance half: **IMPLEMENTED** (`scripts/generate_chat_provenance.py` — role-separated manifest, `--verify` default, receipt-bound `--write`; see Provenance below). Qualification half (per-field capability/temporal-class verdicts, persisted): **PROPOSED / NOT IMPLEMENTED** — see the matrix + dimensions below, which document the retained function without building the old DB/registry.
2. **Temporal admissibility** — **IMPLEMENTED** per the contract above. `_lexicon_as_of` was a first, partial instance; the uniform admitter replaced it.
3. **Governed-field coverage + editor review** — writer-context artifact gates are **IMPLEMENTED** (canon_checks semantic validation: exact-instant bounds, `first_seen_at <= last_observed_at <= meta.temporal_cutoff_utc`, positive non-boolean `count`, in-snapshot `arc_group_id` uniqueness — `scripts/canon_checks.py`; `test_canon_checks.py::test_arc_joke_semantics_pass`, `::test_arc_joke_semantics_count_bool_rejected`, `::test_arc_joke_semantics_count_zero_rejected`, `::test_arc_joke_semantics_past_cutoff_last_observed_is_leak`, `::test_arc_joke_semantics_coarse_bound_rejected`, `::test_arc_joke_semantics_bounds_out_of_order`, `::test_arc_joke_semantics_arc_group_id_not_unique`). The complete FIELD-level governed inventory with unknown-field fail-closed across every writer-facing artifact: **PROPOSED / NOT IMPLEMENTED** (today's fail-closed inventory guards are file-granular — provenance's unclassified-extra-file error and canon_checks' shape checks — not per-field classification).
4. **Missing-evidence fail-closed** — **IMPLEMENTED** for the deterministic artifact-layer behaviors real code + tests support: through-cutoff `count == 0` items dropped (`build_chat_context.py:554`/`:998`; `test_build_chat_context.py::test_find_active_arcs_drops_count_zero`), inadmissible evidence rejected (`test_recompute_projection.py::test_inadmissible_ts_dropped_e2e`), lexicon emitted empty (see Containment). The "empty blocks are expected, don't invent content" preseason tolerance is a WRITER INSTRUCTION (`.claude/commands/write-preseason.md`), not artifact-layer code. The four-outcome editorial taxonomy below is **PROPOSED** as an editor-facing classification.
5. **Approval → content/evidence/policy/render binding** — **PROPOSED / NOT IMPLEMENTED** as machine enforcement. What an approval must bind to: the exact chat-context canonical hashes (already computed by the provenance manifest), the week data file, the voice-bible + writer-command versions (code-role hashes), and the `content/review-log.jsonl` entry. The enforcement point would be the renderer refusing to render `weekN_content.json` whose bound input hashes no longer match. Today the ONLY protections are the "content fixes require HTML re-render" discipline rule and the review log — there is **no machine refusal of a stale render**, so this stays PROPOSED until an enforcement path is cited.

The dead design's machinery (claim registry, lens matrices, cryptographic review-binding, temporal-policy _engine_, graph DB) stays cut. Nothing here needs a database, a scoring system, or confidence aggregation.

## Provenance + external rebuild (function 1's lineage half) — IMPLEMENTED

- Two-layer manifest: portable payload (repo-relative keys, roles: `inputs_private` / `inputs_source` / `derived_intermediates` / `inputs_data` / `code` / `outputs_derived` + private-derived `counts`) vs receipt-only authorization (`normalized_source_root`, never persisted). `test_generate_chat_provenance.py::test_public_projection_is_symmetric`, `::test_public_projection_exact_role_set`.
- `--verify` is the DEFAULT mode (`::test_cli_default_is_verify_not_write`); `--verify-public` passes with private `chat/*` absent (`::test_verify_public_baseline_passes`).
- `--rebuild-check` = external full-DAG rebuild (reparse `_chat.txt` → fingerprint → split → MAP → REDUCE → 19 contexts) into a disjoint OUTPUT_ROOT; whole-root freshness + complete type-aware inventory + repo-nonmutation proof (non-following kind+hash snapshot over DAG+code surfaces AND exact git HEAD/index/tracked-worktree/untracked-bytes binding — `test_provenance_topology.py`, incl. link-substitution and worktree-byte detectors); receipt published atomically ONLY after the proof, unique temp + cleanup on failure.
- `--write` is receipt-bound: it recomputes the complete binding from on-disk bytes and refuses on any mismatch across the ENTIRE six-role portable payload — `inputs_private`, `inputs_source`, `derived_intermediates`, `inputs_data`, `code`, `outputs_derived` — plus the private-derived `counts`; `normalized_source_root` is the separate receipt-only authorization layer (gates `--write`, never persisted) (`::test_receipt_bound_write_happy_path`, `::test_receipt_rejections_leave_manifest_byte_identical`, `::test_write_requires_receipt`). Mixed-lineage poisoning is rejected (two-root poison-diff in `test_chat_rebuild.py`, local-only).

## Source-capability × temporal-orientation matrix — PROPOSED (documentation of the retained function)

Each governed source×field pair gets a capability class crossed with a temporal orientation; a claim is only expressible through a lens the pair qualifies for:

| Capability \ Temporal                           | Realized outcome      | Forecast              | Value snapshot        | Static    |
| ----------------------------------------------- | --------------------- | --------------------- | --------------------- | --------- |
| **Event record** (Sleeper matchups, brackets)   | qualified             | —                     | —                     | —         |
| **Human utterance** (WhatsApp corpus)           | quoted-as-said        | quoted-as-predicted   | —                     | —         |
| **Derived aggregate** (recompute counts/bounds) | through-cutoff only   | —                     | as-of-cutoff only     | —         |
| **External metric** (nflverse EPA etc.)         | pending qualification | pending qualification | pending qualification | —         |
| **League config** (name-map, rosters)           | —                     | —                     | —                     | qualified |

## Qualification dimensions (what a source must be assessed on) — PROPOSED

temporal semantics · historical reach · league fit · identifier/join behavior · coverage · reproducibility · attribution/usage rights · rate limits · source-specific failure behavior.

## Four missing-evidence outcomes — PROPOSED (editorial taxonomy)

1. **Qualified evidence available** — write the claim, cite the lens.
2. **Asserted claim lacks a qualified lens** — the claim must be dropped or reframed; never shipped raw.
3. **Unrelated coverage absence** — a gap that touches no asserted claim; note internally, no writer action.
4. **Unresolved identity join affecting only dependent claims** — quarantine the dependent claims; independent claims unaffected.

## Governed-field inventory + unknown-field behavior

**IMPLEMENTED (file/shape granularity):** provenance fails closed on any unclassified `content/chat/*.json` (`generate_chat_provenance._guard_content_chat_dir`; proven by a PLANTED real unexpected file — `test_generate_chat_provenance.py::test_guard_content_chat_dir_rejects_planted_unclassified_json`, with `::test_guard_content_chat_dir_happy_path` as the not-always-reject control); canon_checks fails closed on missing `league_memory` layers, missing/malformed cutoffs, and malformed arc/joke records (`test_canon_checks.py::test_arc_joke_semantics_malformed_cutoff_catches_future_bound`, `::test_arc_joke_semantics_empty_or_null_gid_rejected`). **PROPOSED:** the complete per-field inventory over every writer-facing artifact with unknown-field fail-closed at field granularity.

## Containment status (updated by the temporal/provenance pass)

- **Lexicon — two separate statuses:** the fail-closed EMPTY writer-facing emit is **IMPLEMENTED** (`scripts/build_chat_context.py:1012`; `test_build_chat_context.py::test_sanitize_league_memory_culture_and_recompute_jokes` asserts `lexicon == {}`). The structured per-term extractor that would replace it (`first_seen_at` + through-cutoff counts per term) is **PROPOSED / NOT IMPLEMENTED**.
- **Running-jokes:** containment SUPERSEDED — structured through-cutoff `count` + exact `first_seen_at`/`last_observed_at` bounds are live (see Temporal Contract #3/#4).
- **Culture aggregates:** still gated from the writer view (timeless `culture` only).

## Standing notes (deliberate decisions, recorded)

- **nflverse — split status.** The existing nflreadpy-backed pipeline IS production: `fetch_nflreadpy.py` (direct `import nflreadpy`, `:18`) caches schedules/injuries/team_stats parquets that `generate_nfl_games.py` + `extract_week_data.py` consume (via `fetch_one`) to build NFLGame entities and `game_context` — data the shipped weekly columns already use. What is provisional and **OUT OF PRODUCTION** is the PROPOSED advanced-metrics/source-qualification layer (EPA-grade claims through a qualified lens): it integrates only if a bounded, read-only qualification spike passes on the dimensions above. The CHAT/writer-context DAG reads none of it (its read-set is closed by the provenance manifest).
- **`rivalry_heat`: deliberate behavior contraction.** The dormant scoring branch was removed (`scripts/build_chat_context.py:483` comment marks the site). It was dormant, not dead — a `relationships["rivalries"]` payload would have fired the +3 branch; today only `pairs` exists. Removal is intentional; reinstating requires a new decision.
- **`arc_group_id` is NOT durable identity.** It is a collision-free key over the full `(type, sorted participants)` group — unique in-snapshot, stable across cutoffs for the same complete crew, and it CHANGES the moment a crew gains a member. No consumer may treat it as durable thread continuity; none is built. (`test_recompute_projection.py::test_arc_group_id_unique_in_snapshot`, `::test_arc_group_id_stable_across_cutoffs`, `::test_arc_group_id_changes_on_growth`, `::test_arc_group_id_no_collision`.)
- **Joke time fields carry two deliberate lineages.** `first_seen`/`last_seen` are legacy month-grained MAP-selection compatibility fields (parity-preserved; NOT evidence bounds; never used to infer recency — they can legitimately lag). `count`/`first_seen_at`/`last_observed_at` are the authoritative through-cutoff raw-evidence count + exact bounds; recency comes from `last_observed_at`. `last_seen` is never rewritten or derived from `last_observed_at` (`test_recompute_projection.py::test_joke_discriminator` proves legitimate divergence). Writer-facing wording lives in `.claude/commands/write-week.md` + `write-preseason.md`.
