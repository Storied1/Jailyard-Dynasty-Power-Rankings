# Jailyard — P-only 2026 Preservation and Sealing: Acceptance Contract

**Status:** DRAFT — awaiting Blake's binary review. Not authorized for implementation.

**Design authority:** `docs/superpowers/specs/2026-08-01-jailyard-writer-foundation-design.md`
APPROVED at `9805426`, §6. That section requires this path to exist and states it "may run only
through a separately approved P-only implementation plan." Material deviation requires re-approval.

**Form:** acceptance contract — schemas, invariants, named tests, files, commands, gates. **No
implementation bodies.** Implementation is written TDD at execution time against the invariants.

**Sequencing:** two operational tranches. **A** delivers the deterministic prospective safeguard and
operates as soon as it passes. **B** adds the rich contrast. A never waits on B. This is what makes
R3 executable rather than descriptive: if projections, chat, or the model arms slip, the safeguard
has already sealed.

**Relationship to the kernel plan.** `2026-08-02-jailyard-temporal-kernel.md` is K1–K3 only; its
P1–P3 are superseded by this document. This plan neither unblocks nor depends on it.

---

## 1. Verified facts (checked against the repo, not assumed)

| Fact                                    | Value                                             | Evidence                                                                                                                |
| --------------------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 2026 league id                          | `1312884727480352768`                             | `fetch_sleeper.py:38`, `config.js`, `data/2026/league.json` — **not a Blake input**; verify against the fetched payload |
| First regular-season kickoff            | `2026-09-10T00:20:00Z`                            | **Official NFL schedule.** Fixture value only; production derives it from a verified `nfl_schedules` capture            |
| Preseason cutoff                        | `2026-09-03T00:20:00Z`                            | kickoff − 7d. **31 days from 2026-08-03**                                                                               |
| Preview cutoff                          | `2026-09-10T00:19:59Z`                            | strictly before kickoff                                                                                                 |
| 2025 `playoff_week_start`               | `15` ⇒ regular season = weeks 1–14                | `data/2025/league.json`, and carried in `data/2025/season_combined.json`                                                |
| 2026 schedule on disk                   | **absent**                                        | `data/external/` stops at 2025 — acquisition is real work                                                               |
| `private_captures/`, `private_bundles/` | **NOT currently gitignored**                      | `.gitignore` — must be added before any private write                                                                   |
| polars / nflreadpy                      | import cleanly **with** `POLARS_SKIP_CPU_CHECK=1` | verified in this shell                                                                                                  |

## 2. Rulings recorded (Blake, 2026-08-03)

**R1 — Cutoffs.** Preseason = 7 days before the qualified first regular-season kickoff. Preview =
strictly before that kickoff. Both derived from a **verified schedule capture** and bound through a
**cutoff-qualification receipt**. Never hard-coded in production.

**R2 — Arms.** Three arms, seven runs per edition:

| `arm_id`        | `runner_kind` | Trials | Evidence                                      |
| --------------- | ------------- | ------ | --------------------------------------------- |
| `record_points` | deterministic | 1      | qualified 2025 final regular-season standings |
| `minimal_legal` | model         | 3      | franchise identity, draft, roster facts       |
| `full_rich`     | model         | 3      | every family the frozen matrix assigns to it  |

Both model arms bind an **identical** runner configuration. Only the bundle differs. Baseline plus
one model arm is not an evidence experiment — it confounds runner kind with evidence richness.

**R3 — Degradation.** If the model contrast cannot complete before a cutoff, seal the deterministic
baseline as a **prospective record** and mark the experiment `unavailable`. Preseason and preview are
processed **independently**: a missing preseason does not contaminate preview.

**R4 — Capture groups.** Eight accounting groups, **twelve components**.

| #   | Group             | Components                                          | Bridge fact types                    |
| --- | ----------------- | --------------------------------------------------- | ------------------------------------ |
| 1   | `league_identity` | `sleeper_league`, `sleeper_users`                   | `franchise_identity`                 |
| 2   | `rosters`         | `sleeper_rosters`                                   | `roster_membership`                  |
| 3   | `draft`           | `draft_meta`, `draft_picks`                         | `draft_pick`                         |
| 4   | `transactions`    | `sleeper_transactions`                              | `transaction`                        |
| 5   | `league_matchups` | `sleeper_matchups`                                  | `schedule_pairing`, `matchup_result` |
| 6   | `projections`     | `sleeper_projections`                               | — (rich-bundle evidence)             |
| 7   | `nfl_context`     | `nfl_schedules`, `nfl_team_context`, `nfl_injuries` | `nfl_game`                           |
| 8   | `chat`            | `chat_export`                                       | `chat_message`                       |

**R5 — Baseline rule (fixed now, not at execution).** `record_points` orders franchises by the
**final regular-season standings**: regular season = weeks `1 .. playoff_week_start − 1`, read from
the same artifact the standings are computed from. Ordering is **wins descending, then points-for
descending, then `roster_id` ascending** as the deterministic final tie-break. Qualified source:
`data/2025/season_combined.json` (carries `weeks`, `roster_map`, `playoff_week_start`, `league_id`,
`season`). Its **locator and `sha256` are bound** into the bundle and the seal.

## 3. Tranche sequencing

**Tranche A — prospective safeguard (first vertical slice).** Operate as soon as it passes; do not
wait for projections, chat, or the model arms.

1. capture-envelope core and accounting receipt — which may **honestly show unfinished rich
   components** rather than blocking;
2. verified schedule acquisition and cutoff-qualification receipt;
3. exact qualified 2025 final-standings input (R5);
4. deterministic `record_points` ranking and scoreable claims;
5. bundle, closed run receipt, seal, reload verification, and rederivation;
6. **operate**: seal the preseason and preview baselines before their cutoffs.

**Tranche B — rich prospective contrast.**

1. remaining component producers (all twelve);
2. `minimal_legal` and `full_rich` bundles;
3. Blake-approved **frozen** runner, source-policy/arm-membership, transformation, and evaluation
   configurations;
4. three paired trials per model arm;
5. exact preseason and preview success-or-R3-fallback operation.

**A's accounting gate is scoped to A's components** (I16a). A rich component still `due` does not
block the safeguard — it is reported honestly and blocks only B.

## 4. Files

| Path                                                                                                                                                      | Responsibility                                              | Git            |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- | -------------- |
| `.gitignore`                                                                                                                                              | ignore private roots — **authorized surface for A1 and A5** | tracked        |
| `scripts/capture_2026.py`                                                                                                                                 | envelope write/verify, producers, accounting                | tracked        |
| `scripts/cutoff_2026.py`                                                                                                                                  | kickoff qualification, cutoff receipt                       | tracked        |
| `scripts/bundle_2026.py`                                                                                                                                  | payload projection, bundle compiler, capture manifest       | tracked        |
| `scripts/seal_2026.py`                                                                                                                                    | run receipts, claims, seals, reload verify, rederive        | tracked        |
| `scripts/tests/test_capture_2026.py`, `test_cutoff_2026.py`, `test_bundle_2026.py`, `test_seal_2026.py`, `test_privacy_boundary.py`, `test_p_only_e2e.py` | §7                                                          | tracked        |
| `content/governance/capture_table_2026.json`                                                                                                              | eight groups, twelve components                             | tracked        |
| `content/governance/source_policy_2026.json`                                                                                                              | **frozen** source-policy + arm-membership matrix (S3)       | tracked        |
| `content/governance/runner_config_2026.json`                                                                                                              | **frozen** shared model-arm binding (S7)                    | tracked        |
| `content/governance/evaluation_config_2026.json`                                                                                                          | **frozen** scoring + aggregation (S10)                      | tracked        |
| `data/captures/2026/public/`, `data/captures/2026/_receipts/`                                                                                             | public envelopes, accounting + cutoff receipts              | tracked        |
| `content/seals/2026/{edition_id}/{arm_id}/trial{n}/`                                                                                                      | seals, decisions, claims, run receipts                      | tracked        |
| `private_captures/2026/`, `private_bundles/2026/`                                                                                                         | private envelopes and private bundles                       | **gitignored** |
| `docs/superpowers/plans/capture-manual-ingest.md`                                                                                                         | chat ingestion procedure                                    | tracked        |

`CAPTURE_TABLE_PATH` **must be defined** as a module constant resolving to
`content/governance/capture_table_2026.json`. The prior revision referenced it without defining it.

## 5. Schemas

**S1 — Capture envelope** (`{root}/{source_id}/{captured_at_compact}.json`):
`source_id`; `request` `{endpoint_or_dataset, params}` (exact source request identity); `season`;
`league_id`; `locator` (repo-relative); `captured_at`; `known_at_basis`; `access_scope`
(`public` | `league_private`); `privacy` (`public` | `private`); `payload_sha256`;
`envelope_sha256` (over all fields except itself); `payload`.

**S2 — Accounting receipt.** `{season, generated_at, tranche, groups[], unmet_required[], ok}`.
Group: `{group, required_for[], status ∈ {captured, incomplete, error}, components[]}`. Component,
independently: `{source_id, required_for[], mechanism, cadence, availability_window, empty_valid,
status ∈ {captured, due, not_due, error}, captured_at, payload_sha256, envelope_sha256, error,
acquisition_trigger}`.

**S3 — Source-policy and arm-membership matrix** (`source_policy_2026.json`) — **frozen and hashed
before any run.** One row per source, covering all twelve capture components **plus** the
non-capture qualified sources:

| Row field                         | Meaning                                                                                             |
| --------------------------------- | --------------------------------------------------------------------------------------------------- |
| `source_id`                       | the twelve components, plus `standings_2025`, `league_history_{2022,2023,2024}`, `player_crosswalk` |
| `kind`                            | `capture` \| `qualified_artifact`                                                                   |
| `locator_or_endpoint`             | exact path or endpoint                                                                              |
| `arms`                            | subset of `{record_points, minimal_legal, full_rich}` — **exact** membership                        |
| `editions`                        | subset of `{2026-preseason, 2026-wk01-preview}`                                                     |
| `required_for`                    | arms for which absence is fatal                                                                     |
| `availability_window`             | `{opens_at_rule, closes_at_rule}`                                                                   |
| `freshness`                       | max age for `captured`; `null` = existence suffices                                                 |
| `empty_valid`                     | whether a legitimately empty payload counts as `captured`                                           |
| `known_at_basis`                  | how `known_at` is defensibly established                                                            |
| `chat_refresh`                    | `initial` and `subsequent` rules (chat row only)                                                    |
| `policy_version`, `matrix_sha256` | freeze identity                                                                                     |

`player_crosswalk` is the **shared player-identity source used identically by both model arms** —
same locator, same hash, in both bundles. `standings_2025` is R5's source.
`league_history_{2022,2023,2024}` are `full_rich`-only. **"All available" and "required rich family"
are not admissible descriptions**; membership is whatever this matrix says and nothing else.

**S4 — Cutoff-qualification receipt.** `{season, kickoff_utc, kickoff_game_id,
kickoff_source_locator, kickoff_source_envelope_sha256, derivation_version, preseason_cutoff_utc,
preview_cutoff_utc, qualified_at, receipt_sha256}`.

**S5 — Frozen bundle.** Binds the **actual canonical decision-input payload as the decider saw it**,
not only capture identities:

| Field                                             | Meaning                                                                                             |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `edition_id`, `arm_id`, `cutoff_utc`              | scope                                                                                               |
| `cutoff_receipt_locator`, `cutoff_receipt_sha256` | the cutoff this bundle was cut at                                                                   |
| `capture_manifest[]`                              | S6 — the selected envelopes                                                                         |
| `decision_input_payload`                          | the **canonical rendered payload** handed to the runner                                             |
| `decision_input_sha256`                           | hash of that payload                                                                                |
| `projection`                                      | `{ordering_version, redaction_version, projection_version, code_sha256, config_sha256, parameters}` |
| `matrix_sha256`                                   | the frozen source policy in force                                                                   |
| `contains_private`                                | true ⇒ written under `private_bundles/`                                                             |
| `bundle_sha256`                                   | computed from content; **never caller-supplied**                                                    |

Projection rules are **deterministic**: a stated total ordering of entities and fields, a stated
redaction set, and a stated field projection — each versioned and hashed. Rederivation regenerates
`decision_input_payload` and must reproduce `decision_input_sha256` **and** `bundle_sha256`.

**S6 — Capture manifest.** Ordered list of
`{source_id, locator, envelope_sha256, payload_sha256, captured_at}` — one entry per selected
envelope. This is what rederivation reads from.

**S7 — Runner config** (`runner_config_2026.json`, frozen). `provider, model, model_version,
reasoning, tools_policy, browsing, budget, retries, sampling_policy, prompt_locator, prompt_sha256,
rule_locators, rule_sha256s, runner_config_sha256`. **One immutable `runner_config_sha256` appears in
every model receipt**, identical across `minimal_legal` and `full_rich`.

**S8 — Decision-run receipt.** `decision_run_id, edition_id, arm_id, trial_id, runner_kind,
bundle_sha256, decision_input_sha256, capture_manifest_sha256, cutoff_receipt_locator,
cutoff_receipt_sha256, matrix_sha256, predecessor_decision_hash, predecessor_null_reason,
started_at, ended_at, output_decision_sha256`. `state_hash` is **null with a recorded reason** — no
`state_at` exists pre-kernel. Deterministic adds `code_sha256, config_sha256, input_hashes`. Model
adds `runner_config_sha256` (S7).

**S9 — Claim.** Design §4 field set plus binding: `claim_id, target, claim_type ∈ {ordinal_rank,
binary_probability, bounded_quantity}, horizon, assertion, confidence, bound, decisive_evidence,
contrary_evidence, cutoff_utc, edition_id, arm_id, trial_id, decision_run_id, bundle_sha256,
capture_manifest_sha256, resolution_rule {rule, source, resolve_on}, outcome, score,
resolution_failed`. `outcome`/`score` start null.

**S10 — Evaluation config** (`evaluation_config_2026.json`, frozen). The **already-approved** design
§4 rules, hashed: Spearman footrule for `ordinal_rank`, Brier for `binary_probability`, bound-
normalized absolute error for `bounded_quantity`; aggregation order `claim → team → edition → trial
→ arm`; unresolved excluded and counted; unresolvable reported; median-with-range for
non-deterministic runners; `evaluation_config_sha256`.

**S11 — Seal.** `{edition_id, kind, season, arm_id, trial_id, cutoff_utc, cutoff_receipt_locator,
cutoff_receipt_sha256, ended_at, sealed_at, label ∈ {prospective, retrospective}, bundle_sha256,
bundle_locator, decision_input_sha256, capture_manifest_sha256, matrix_sha256, decision_sha256,
decision_locator, claims_sha256, claims_locator, receipt_sha256, receipt_locator,
predecessor_decision_hash, runner_kind, decision_hash}`. `decision_hash` covers every other field;
nothing binds `decision_hash` — the chain is acyclic.

**S12 — Experiment status.** Per edition: `{edition_id, expected_runs, verified_prospective_seals[],
experiment_status ∈ {complete, unavailable}, reason, computed_at}`. `experiment_status` is
**derived**: `complete` iff all **seven** verified prospective seals exist for that edition
(`record_points` ×1, `minimal_legal` ×3, `full_rich` ×3). Never manually asserted.

## 6. Invariants

**Capture**

- **I1** A failed fetch is never an envelope. `fetch_sleeper.fetch_json` returns `None` on exhausted
  retries (`fetch_sleeper.py:69`); `None`, non-object, and payloads empty where `empty_valid` is
  false are refused.
- **I2** `capture()` validates its own arguments — instant shape, privacy, scope, basis — because
  manual ingestion never passes through `main()`.
- **I3** Append-only: an existing envelope path is never overwritten.
- **I4** A future-dated capture (`captured_at` > trusted now) is refused.
- **I5** Verification checks **payload and metadata**: `payload_sha256` over `payload`,
  `envelope_sha256` over all other fields. Either mismatch ⇒ **not coverage**.
- **I7** Per-leg/per-week sources record `*_requested` and raise on any unreadable leg. An outage is
  never byte-identical to a quiet week.
- **I8** `draft_picks` resolves `draft_id` then fetches `/draft/{id}/picks`; the component fails
  unless `pick_count > 0` **and** pick order is preserved.
- **I9** The league id is read from `data/2026/league.json` and **verified equal** to the
  `league_id` in the fetched league payload.
- **I36** **All twelve components have an executable producer.** A test enumerates the capture table
  and asserts a producer exists for each; a component with no producer fails the suite.

**Privacy boundary — enforced before any private write**

- **I6** Private components are written only under `private_captures/`; private bundles only under
  `private_bundles/`.
- **I37** `.gitignore` ignores both private roots, proven by `git check-ignore -q` on a
  representative path — not by reading the file.
- **I38** `git ls-files` reports **zero** tracked paths under either private root.
- **I39** The resolved absolute write path is **contained** within the intended private root
  (`Path.resolve()` containment check), so `..` traversal cannot escape it.
- **I40** Paths containing traversal segments, or resolving through a symlink/junction/reparse point
  out of the private root, are **rejected** rather than followed.
- **I41** The index staging guard (`git diff --cached --name-only`) fails on any staged private path.
  Checking `git status` cannot work — an ignored path never appears there.
- **I15** Receipts, manifests and seals carry hashes and metadata only. **No payload, never raw
  chat.**

**Accounting**

- **I10** Eight groups; every one of the twelve components reported independently with its own
  status and hashes.
- **I11** A group passes only when every component **required for the tranche in scope** passes.
- **I12** Status is availability-aware per the frozen matrix: `not_due` before the window opens,
  `due` when open and absent or stale, `captured` when a verified envelope exists inside its
  freshness window, `error` when a producer failed this run.
- **I13** A component reaching `captured` after ingestion clears the lane — no component is
  permanently `unavailable`.
- **I14** Chat refresh follows the matrix's `initial`/`subsequent` rules; a stale chat export blocks
  **B** sealing.
- **I16a** The accounting gate is **tranche-scoped**: `--tranche A` fails only on A's required
  components and reports rich components honestly as `due`/`not_due`. A rich gap never blocks the
  safeguard.
- **I16b** The CLI exits non-zero when any component required for the requested tranche is not
  `captured`; the receipt is still written.

**Cutoff**

- **I17** Kickoff is derived from a **verified** `nfl_schedules` envelope with venue-timezone
  conversion — never by appending `Z` to a local time, never hard-coded in production.
- **I18** The cutoff receipt binds `kickoff_game_id`, the source locator, its `envelope_sha256`, and
  a `derivation_version`.
- **I42** Cutoffs are read **only** from the cutoff receipt downstream; bundle, receipt and seal each
  carry `cutoff_receipt_locator` + `cutoff_receipt_sha256`, and reload verifies that the selected
  schedule game, derivation version, cutoff value, run receipt and seal all agree.

**Bundle and payload**

- **I19** The compiler selects, per source, the latest **verified** envelope with
  `captured_at <= cutoff_utc`. A post-cutoff envelope is never selected.
- **I20** `bundle_sha256` and `decision_input_sha256` are computed from content. There is **no
  caller-supplied factset or bundle hash**.
- **I43** The bundle binds the **canonical decision-input payload** the runner received, plus the
  versioned ordering, redaction and projection rules with their code and config hashes and
  parameters.
- **I21** Rederivation **regenerates** the decision-input payload from the sealed capture manifest by
  re-reading and re-verifying each envelope and re-applying the recorded projection, then reproduces
  `decision_input_sha256` and `bundle_sha256`. Re-hashing an already-frozen bundle is not a test and
  is forbidden.
- **I22** A bundle containing any private component sets `contains_private: true` and is written
  under `private_bundles/`. Only its hashes may be committed.
- **I23** Arm membership comes from the frozen matrix: `full_rich` fails if any source the matrix
  marks `required_for: full_rich` is absent or empty-where-not-`empty_valid`; `minimal_legal` is a
  strict subset of `full_rich`; `player_crosswalk` appears in **both** with identical locator and
  hash.

**Decision, seal, evaluation**

- **I24** `started_at`, `ended_at`, `sealed_at` come from a **trusted clock** in production; clock
  injection is test-only.
- **I25** `started_at <= ended_at <= sealed_at`, enforced.
- **I26** `label` is `prospective` only when **both** `ended_at` and `sealed_at` are `<= cutoff_utc`.
  Otherwise `retrospective`. No mechanism reclassifies, and none may be added.
- **I27** A run is closed before sealing; the seal binds the **closed** receipt's hash, not a path.
- **I28** Every artifact is keyed by `(edition_id, arm_id, trial_id)`.
- **I29** Predecessor lookup returns the **latest qualified** seal from the **same** `arm_id` and
  `trial_id` at a strictly earlier cutoff. A foreign predecessor raises.
- **I44** `predecessor_decision_hash` is **required** whenever a qualified predecessor exists; null
  is permitted only with a recorded `predecessor_null_reason`.
- **I30** Seals are immutable; seal files use a distinct suffix so decision, claims and receipt
  bodies are never deserialized as seals.
- **I31** Load-time verification recomputes and cross-checks **every** hash: seal metadata, decision,
  claims, receipt, bundle, decision-input payload, capture manifest, cutoff receipt, matrix, and
  receipt↔decision agreement.
- **I32** Every ranking position carries at least one claim with a `resolution_rule` fixed before the
  outcome; every claim binds `bundle_sha256` and `capture_manifest_sha256`.
- **I33** Both model arms bind an identical `runner_config_sha256` — provider, model, model_version,
  reasoning, budget, retries, sampling policy, prompt, rules, tools policy and browsing all equal. A
  mismatch fails the run.
- **I34** Model arms require 3 trials; deterministic requires 1. Under-sampling fails.
- **I45** Scoring and aggregation come from the frozen `evaluation_config_sha256`; no metric may be
  selected after results are seen.
- **I35** `experiment_status` is **derived** from the seven verified prospective seals per edition
  (S12), never manually asserted. Preseason and preview are computed independently.
- **I46** R5's baseline is reproducible: regular season = weeks `1 .. playoff_week_start − 1`;
  ordering wins ↓, points-for ↓, `roster_id` ↑; source locator and hash bound into bundle and seal.

## 7. Named tests

Every test must be **observed failing** with its rule removed. A green suite alone is not acceptance.

| Test                                                                                                                                                                                                | Proves |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `test_failed_fetch_is_never_written` / `test_empty_payload_respects_empty_valid`                                                                                                                    | I1     |
| `test_capture_validates_its_own_arguments`                                                                                                                                                          | I2     |
| `test_append_only_refuses_overwrite`                                                                                                                                                                | I3     |
| `test_future_dated_capture_refused`                                                                                                                                                                 | I4     |
| `test_tampered_payload_is_not_coverage` / `test_tampered_metadata_is_not_coverage`                                                                                                                  | I5     |
| `test_partial_leg_failure_is_not_an_empty_week` / `test_all_legs_read_and_empty_is_valid`                                                                                                           | I7     |
| `test_draft_reaches_picks_and_fails_on_metadata_only`                                                                                                                                               | I8     |
| `test_league_id_verified_against_fetched_payload`                                                                                                                                                   | I9     |
| `test_all_twelve_components_have_producers`                                                                                                                                                         | I36    |
| `test_private_component_stays_outside_tracked_roots`                                                                                                                                                | I6     |
| `test_git_check_ignore_covers_both_private_roots`                                                                                                                                                   | I37    |
| `test_git_ls_files_reports_no_tracked_private_paths`                                                                                                                                                | I38    |
| `test_resolved_path_containment_blocks_traversal`                                                                                                                                                   | I39    |
| `test_symlink_or_reparse_point_escape_rejected`                                                                                                                                                     | I40    |
| `test_index_staging_guard_fails_on_staged_private_path`                                                                                                                                             | I41    |
| `test_receipt_carries_no_payload_or_chat`                                                                                                                                                           | I15    |
| `test_eight_groups_twelve_components_independent`                                                                                                                                                   | I10    |
| `test_group_passes_only_when_required_components_pass`                                                                                                                                              | I11    |
| `test_not_due_before_window_due_after` / `test_stale_component_returns_to_due`                                                                                                                      | I12    |
| `test_component_clears_after_ingestion`                                                                                                                                                             | I13    |
| `test_chat_refresh_initial_and_subsequent_rules` / `test_stale_chat_blocks_tranche_b_sealing`                                                                                                       | I14    |
| `test_tranche_a_gate_ignores_unfinished_rich_components`                                                                                                                                            | I16a   |
| `test_cli_exits_nonzero_on_unmet_required_component`                                                                                                                                                | I16b   |
| `test_kickoff_derived_with_venue_timezone` / `test_kickoff_never_hardcoded_in_production_path`                                                                                                      | I17    |
| `test_cutoff_receipt_binds_game_source_and_version`                                                                                                                                                 | I18    |
| `test_cutoff_receipt_bound_and_cross_verified_everywhere`                                                                                                                                           | I42    |
| `test_preseason_cutoff_is_seven_days_before_kickoff` / `test_preview_cutoff_is_strictly_before_kickoff`                                                                                             | R1     |
| `test_compiler_excludes_post_cutoff_envelopes`                                                                                                                                                      | I19    |
| `test_no_caller_supplied_bundle_or_factset_hash`                                                                                                                                                    | I20    |
| `test_bundle_binds_canonical_decision_input_and_projection_versions`                                                                                                                                | I43    |
| `test_rederive_regenerates_decision_input_payload` / `test_rederive_fails_when_an_envelope_changed`                                                                                                 | I21    |
| `test_private_bundle_stays_untracked`                                                                                                                                                               | I22    |
| `test_arm_membership_comes_from_frozen_matrix` / `test_full_rich_fails_on_missing_required_source` / `test_minimal_is_strict_subset_of_full` / `test_player_crosswalk_identical_in_both_model_arms` | I23    |
| `test_production_clock_is_not_injectable`                                                                                                                                                           | I24    |
| `test_timestamp_ordering_enforced`                                                                                                                                                                  | I25    |
| `test_prospective_requires_both_completion_and_sealing_before_cutoff` / `test_late_completion_early_seal_is_retrospective` / `test_backdating_is_impossible`                                        | I26    |
| `test_sealing_an_open_run_refused`                                                                                                                                                                  | I27    |
| `test_artifacts_keyed_by_edition_arm_trial`                                                                                                                                                         | I28    |
| `test_latest_qualified_same_arm_trial_predecessor` / `test_cross_arm_predecessor_poison_rejected` / `test_cross_trial_predecessor_poison_rejected`                                                  | I29    |
| `test_null_predecessor_requires_a_reason`                                                                                                                                                           | I44    |
| `test_seal_immutable_and_bodies_not_seals`                                                                                                                                                          | I30    |
| `test_reload_cross_checks_every_hash` / `test_tampered_bundle_decision_claims_receipt_detected`                                                                                                     | I31    |
| `test_every_position_carries_a_bound_claim`                                                                                                                                                         | I32    |
| `test_model_arms_share_one_runner_config_hash`                                                                                                                                                      | I33    |
| `test_trial_counts_enforced`                                                                                                                                                                        | I34    |
| `test_scoring_comes_from_frozen_evaluation_config`                                                                                                                                                  | I45    |
| `test_experiment_status_derived_from_seven_seals` / `test_manual_status_assertion_rejected` / `test_preseason_failure_does_not_contaminate_preview`                                                 | I35    |
| `test_baseline_uses_playoff_week_start_and_tiebreaks` / `test_baseline_source_locator_and_hash_bound`                                                                                               | I46    |
| `test_matrix_frozen_before_any_run` / `test_matrix_drift_invalidates_runs`                                                                                                                          | S3     |

**End-to-end** — `test_p_only_e2e.py`, two tests:

> **A:** envelopes (A's components only) → tranche-A accounting → cutoff qualification → baseline
> bundle → deterministic run → claims → seal → reload verify → rederive from the capture manifest.
>
> **B:** full envelopes → tranche-B accounting → minimal + full bundles → 7 runs across 3 arms →
> claims → 7 seals → reload verify → rederive → derived `experiment_status`.

Controls in the same module: **missing component**, **post-cutoff envelope**, **private leak**,
**cross-arm predecessor**, **backdating**, **tamper** (envelope, bundle, decision-input payload,
claims, receipt, cutoff receipt, seal), and **retry** (a crash between run-close and seal leaves no
valid seal; re-running is safe and does not double-seal).

## 8. Tasks and gates

Each task: write named tests → observe them fail → implement → green → **observe each control fail
with its rule removed** → commit. Binary gates.

### Tranche A — prospective safeguard

| Task   | Delivers                                                                                                                                                            | Gate                                                  |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| **A1** | `.gitignore` private roots, envelope schema, write/verify, `CAPTURE_TABLE_PATH`, capture table                                                                      | I1–I5, I9, I37–I41 green **before any private write** |
| **A2** | A-scoped producers (`sleeper_league`, `sleeper_users`, `sleeper_rosters`, `draft_meta`, `draft_picks`, `sleeper_transactions`, `sleeper_matchups`, `nfl_schedules`) | I7, I8 green                                          |
| **A3** | tranche-scoped accounting receipt + CLI                                                                                                                             | I10–I13, I16a, I16b green                             |
| **A4** | cutoff qualification + receipt                                                                                                                                      | I17, I18, I42, R1 green                               |
| **A5** | projection rules, bundle compiler, capture manifest, R5 baseline input                                                                                              | I19–I23, I43, I46 green                               |
| **A6** | deterministic run receipt, claims, seal, reload verify, rederive                                                                                                    | I24–I32, I44 green; E2E-A green                       |
| **A7** | **operate**: seal preseason + preview baselines before their cutoffs                                                                                                | seals verify `prospective`                            |

### Tranche B — rich prospective contrast

| Task   | Delivers                                                                                       | Gate                                          |
| ------ | ---------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **B1** | remaining producers (`sleeper_projections`, `nfl_team_context`, `nfl_injuries`, `chat_export`) | I36 green — all twelve                        |
| **B2** | frozen `source_policy_2026.json`, `runner_config_2026.json`, `evaluation_config_2026.json`     | Blake-approved, hashed, frozen before any run |
| **B3** | `minimal_legal` + `full_rich` bundles                                                          | I23 green                                     |
| **B4** | 3 paired trials per model arm                                                                  | I33, I34, I45 green                           |
| **B5** | derived experiment status + R3 fallback                                                        | I35 green; E2E-B green                        |

### Commands

```bash
export PY="/c/Users/blake/AppData/Local/Programs/Python/Python312/python"
export POLARS_SKIP_CPU_CHECK=1                 # required for the nflreadpy path in this shell

$PY -m pytest scripts/tests/ -q                                    # >= 343 passed / 2 skipped + new
$PY scripts/capture_2026.py --help                                 # exit 0 WITH output
$PY scripts/capture_2026.py --season 2026 --tranche A              # league id read + verified
$PY scripts/cutoff_2026.py --season 2026 --write-receipt
$PY scripts/seal_2026.py --verify-all
$PY scripts/seal_2026.py --rederive-all                            # regenerates decision-input payloads
$PY scripts/seal_2026.py --experiment-status --edition 2026-preseason
```

Every CLI ends `raise SystemExit(main())` and is proven to execute via `--help` before any gate
depends on its exit code — a `main()` that is never called exits 0 while doing nothing.

### A7 / B5 edition-run matrix (literal)

```bash
# A7 -- safeguard. Runs as soon as A6 passes; does NOT wait for tranche B.
for ed in 2026-preseason 2026-wk01-preview; do
  $PY scripts/bundle_2026.py --edition "$ed" --arm record_points || exit 1
  $PY scripts/seal_2026.py   --edition "$ed" --arm record_points --trial 1 || exit 1
done

# B5 -- full experiment: 7 runs per edition (1 + 3 + 3).
for ed in 2026-preseason 2026-wk01-preview; do
  for arm in minimal_legal full_rich; do
    for t in 1 2 3; do
      $PY scripts/bundle_2026.py --edition "$ed" --arm "$arm" || exit 1
      $PY scripts/seal_2026.py   --edition "$ed" --arm "$arm" --trial "$t" || exit 1
    done
  done
  # R3: status is DERIVED from verified prospective seals, never asserted.
  $PY scripts/seal_2026.py --experiment-status --edition "$ed"
  # exit 0 = complete (7/7); exit 1 = unavailable, reason recorded, baseline stands
done
```

**Staging guard**, run before any commit that touches captures or bundles:

```bash
git diff --cached --name-only | grep -qE '^(private_captures|private_bundles)/' \
  && { echo "STOP: private artifact staged"; exit 1; }
```

**A7 and B5 stop after sealing.** Scheduler activation and any workflow push require Blake's
explicit approval of that exact action and are **not** authorized by approving this contract.

## 9. Open items

1. **B2 configurations require Blake's approval before freezing** — runner, source policy,
   transformations, evaluation. B cannot start without them; A is unaffected.
2. **Sleeper projections endpoint shape** for 2026 is unverified against a live response (B1).
3. **Preseason cutoff is 31 days out** (`2026-09-03T00:20:00Z`). Tranche A exists so this date is met
   by the safeguard regardless of B's progress.

## 10. Self-review

**Sequencing corrected.** The prior revision made every seal wait on F2's full producer set, so a
projections or `nfl_context` delay would have removed the very safeguard R3 promises. A now depends
only on the eight components it needs, its accounting gate is tranche-scoped (I16a), and A7 operates
without B. R3 is executable.

**Bounded corrections applied.** Twelve components, not eleven, with I36 and a producer-enumeration
test. `.gitignore` added to A1/A5's authorized surface with five privacy-boundary invariants
(I37–I41) proven by `git check-ignore`, `git ls-files`, resolved-path containment, traversal/reparse
rejection, and the index guard — all required **before** any private write. Frozen source-policy and
arm-membership matrix (S3) naming all twelve components plus `standings_2025`,
`league_history_{2022,2023,2024}` and the shared `player_crosswalk`, with requiredness, windows,
freshness, empty-valid, known-at basis and chat-refresh rules. S5 now binds the canonical
decision-input payload with versioned ordering/redaction/projection and their code/config hashes,
and I21 requires rederivation to regenerate it. Cutoff receipt bound through S5/S8/S11 with
cross-verification on reload (I42); kickoff attributed to the **official NFL schedule**. Run and
experiment binding completed: one immutable `runner_config_sha256` in every model receipt (I33),
bundle and manifest identity in every claim (I32), frozen evaluation config (I45), latest-qualified
predecessor with a reasoned null (I44), and derived experiment status (I35, S12). F8 replaced by a
literal edition-run matrix covering all seven runs per edition and the R3 fallback.

**Length.** ~500 lines, still code-free: 0 `def`/`class`, no implementation bodies. The overage is
governing matrices and invariants, which is what the guardrail was protecting, not pseudocode.

**Known gap.** The 2026 projections endpoint shape is unverified (open item 2) — a B1 risk only, and
A is designed so it cannot become an A risk.

**What would make this contract wrong.** If A7 has not sealed by `2026-09-03T00:20:00Z`, the
preseason baseline is `retrospective` by construction and that edition's prospective record is lost.
Per I26 nothing backdates it. That date is the reason tranche A exists.
