# Jailyard — P-only 2026 Preservation and Sealing: Acceptance Contract

**Status:** APPROVED for Tranche-A implementation (A1–A6/E2E-A only) — Blake delegated the technical
approval 2026-08-04; exercised after the I50a/I50b correction, a five-finding architect repair pass,
and an architect PASS with a mechanically verified census (62/62 gate tokens, 0 violations). Tranche
B, the production `v1` freeze, and production A7 sealing remain Blake-gated. Nothing here authorizes
push, publication, or scheduler activation.

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

| Fact                                    | Value                                                                                                                            | Evidence                                                                                                                |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 2026 league id                          | `1312884727480352768`                                                                                                            | `fetch_sleeper.py:38`, `config.js`, `data/2026/league.json` — **not a Blake input**; verify against the fetched payload |
| First regular-season kickoff            | `2026-09-10T00:20:00Z`                                                                                                           | **Official NFL schedule.** Fixture value only; production derives it from a verified `nfl_schedules` capture            |
| Preseason cutoff                        | `2026-09-03T00:20:00Z`                                                                                                           | kickoff − 7d. **31 days from 2026-08-03**                                                                               |
| Preview cutoff                          | `2026-09-10T00:19:59Z`                                                                                                           | strictly before kickoff                                                                                                 |
| 2025 `playoff_week_start`               | `15` ⇒ regular season = weeks 1–14                                                                                               | `data/2025/league.json`, and carried in `data/2025/season_combined.json`                                                |
| 2026 schedule on disk                   | **absent**                                                                                                                       | `data/external/` stops at 2025 — acquisition is real work                                                               |
| `private_captures/`, `private_bundles/` | **NOT currently gitignored**                                                                                                     | `.gitignore` — must be added before any private write                                                                   |
| polars / nflreadpy                      | import cleanly **with** `POLARS_SKIP_CPU_CHECK=1`                                                                                | verified in this shell                                                                                                  |
| 2025 regular-season standings           | **recomputable** — `weeks[13].standings` carries cumulative `wins`/`pf` per `roster_id`; `is_playoff` false wks 1–14, true 15–18 | `data/2025/season_combined.json`                                                                                        |
| 2025→2026 franchise join key            | **`owner_id`** — `roster_map` carries `{roster_id, owner_id, final_record{wins, fpts}}`; 2026 rosters carry `owner_id`           | both artifacts inspected                                                                                                |
| Owner overlap 2025↔2026                 | **12 of 12**, 0 unmatched                                                                                                        | `data/2026/rosters.json` (2026-04-04 snapshot — evidence, not a guarantee at capture time)                              |

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

1. capture-envelope core and **its own frozen baseline policy `v1`** (A1b) — A never depends on a
   policy that a later tranche creates;
2. accounting receipt — which may **honestly show unfinished non-baseline components** rather than
   blocking;
3. verified schedule acquisition and cutoff-qualification receipt;
4. exact qualified 2025 final-standings input (R5);
5. deterministic `record_points` ranking and scoreable claims;
6. bundle, closed run receipt, seal, reload verification, and rederivation;
7. **operate**: seal the preseason and preview baselines before their cutoffs.

**Tranche B — rich prospective contrast.**

1. remaining component producers (all twelve);
2. Blake-approved **frozen** model-arm policy `v2`, runner, transformation and evaluation
   configurations — `v2` is a **new version alongside** `v1`, never an edit to it;
3. `minimal_legal` and `full_rich` bundles;
4. three paired trials per model arm;
5. exact preseason and preview success-or-R3-fallback operation.

**Policy lifecycle — the correction that makes A independent.** The prior revision had B2 create and
freeze the single `source_policy_2026.json`, while A3's accounting, A5's bundles and A7's seals all
required a frozen matrix. A could not run without an artifact only B produced. Resolved by **two
separately versioned, immutable policy files**:

| Version                      | Scope        | Frozen in                | Governs                      |
| ---------------------------- | ------------ | ------------------------ | ---------------------------- |
| `source_policy_2026.v1.json` | `baseline`   | **A1b**, before A2/A3/A5 | `record_points`              |
| `source_policy_2026.v2.json` | `model_arms` | B2                       | `minimal_legal`, `full_rich` |

Each run binds the **locator and hash of the version in force for its arm**. `v2` may set different
values for a source it shares with `v1` — those govern only B's arms — but it **must not modify
`v1`'s bytes and must not change the verification result of any seal already bound to `v1`**
(I47–I49). A's seals cite `v1` permanently.

**A's accounting gate is scoped to A's components** (I16a). A non-baseline component still `due` does
not block the safeguard — it is reported honestly and blocks only B.

## 4. Files

| Path                                                                                                                                                      | Responsibility                                                       | Git            |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | -------------- |
| `.gitignore`                                                                                                                                              | ignore private roots — **authorized surface for A1 and A5**          | tracked        |
| `scripts/capture_2026.py`                                                                                                                                 | envelope write/verify, producers, accounting, **policy freeze (S3)** | tracked        |
| `scripts/cutoff_2026.py`                                                                                                                                  | kickoff qualification, cutoff receipt                                | tracked        |
| `scripts/bundle_2026.py`                                                                                                                                  | payload projection, bundle compiler, source manifest                 | tracked        |
| `scripts/seal_2026.py`                                                                                                                                    | run receipts, claims, seals, reload verify, rederive                 | tracked        |
| `scripts/tests/test_capture_2026.py`, `test_cutoff_2026.py`, `test_bundle_2026.py`, `test_seal_2026.py`, `test_privacy_boundary.py`, `test_p_only_e2e.py` | §7                                                                   | tracked        |
| `content/governance/capture_table_2026.json`                                                                                                              | eight groups, twelve components                                      | tracked        |
| `content/governance/source_policy_2026.v1.json`                                                                                                           | **frozen in A1b** — baseline policy, governs `record_points` (S3)    | tracked        |
| `content/governance/source_policy_2026.v2.json`                                                                                                           | **frozen in B2** — model-arm policy; never edits `v1` (S3)           | tracked        |
| `content/governance/runner_config_2026.json`                                                                                                              | **frozen** shared model-arm binding (S7)                             | tracked        |
| `content/governance/evaluation_config_2026.json`                                                                                                          | **frozen** scoring + aggregation (S10)                               | tracked        |
| `data/captures/2026/public/`, `data/captures/2026/_receipts/`                                                                                             | public envelopes, accounting + cutoff receipts                       | tracked        |
| `content/seals/2026/{edition_id}/{arm_id}/trial{n}/`                                                                                                      | seals, decisions, claims, run receipts                               | tracked        |
| `private_captures/2026/`, `private_bundles/2026/`                                                                                                         | private envelopes and private bundles                                | **gitignored** |
| `docs/superpowers/plans/capture-manual-ingest.md`                                                                                                         | chat ingestion procedure — **authored at B1**                        | tracked        |

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

**S3 — Source-policy and arm-membership matrix** — **a versioned family**, each version frozen and
hashed before any run that cites it. `v1` (scope `baseline`) is frozen in **A1b**; `v2` (scope
`model_arms`) in **B2**. A version is written once and never edited. One row per source, covering
the twelve capture components **plus** the non-capture qualified sources. Header fields:
`policy_version`, `scope ∈ {baseline, model_arms}`, `frozen_at`, `policy_sha256`. Rows:

| Row field                                  | Meaning                                                                                             |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| `source_id`                                | the twelve components, plus `standings_2025`, `league_history_{2022,2023,2024}`, `player_crosswalk` |
| `kind`                                     | `capture` \| `qualified_artifact`                                                                   |
| `locator_or_endpoint`                      | exact path or endpoint                                                                              |
| `arms`                                     | subset of `{record_points, minimal_legal, full_rich}` — **exact** membership                        |
| `editions`                                 | subset of `{2026-preseason, 2026-wk01-preview}`                                                     |
| `required_for`                             | arms for which absence is fatal                                                                     |
| `availability_window`                      | `{opens_at_rule, closes_at_rule}`                                                                   |
| `freshness`                                | max age for `captured`; `null` = existence suffices                                                 |
| `empty_valid`                              | whether a legitimately empty payload counts as `captured`                                           |
| `known_at_basis`                           | how `known_at` is defensibly established                                                            |
| `chat_refresh`                             | `initial` and `subsequent` rules (chat row only)                                                    |
| `policy_version`, `scope`, `policy_sha256` | freeze identity                                                                                     |

`player_crosswalk` is the **shared player-identity source used identically by both model arms** —
same locator, same hash, in both bundles. `standings_2025` is R5's source.
`league_history_{2022,2023,2024}` are `full_rich`-only. **"All available" and "required rich family"
are not admissible descriptions**; membership is whatever the cited policy version says.

**Version scope.** `v1` rows carry `arms ⊆ {record_points}` and are sufficient on their own for
baseline accounting, bundle construction, sealing and rederivation — that sufficiency is A1b's gate.
`v2` rows carry `arms ⊆ {minimal_legal, full_rich}`. Where a source appears in both, each version
governs only its own arms; the versions need not agree, and a `v2` value never reaches a `v1`-bound
seal.

**S4 — Cutoff-qualification receipt.** `{season, kickoff_utc, kickoff_game_id,
kickoff_source_locator, kickoff_source_envelope_sha256, derivation_version, preseason_cutoff_utc,
preview_cutoff_utc, qualified_at, receipt_sha256}`.

**S5 — Frozen bundle.** Binds the **actual canonical decision-input payload as the decider saw it**,
not only capture identities:

| Field                                             | Meaning                                                                                             |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `edition_id`, `arm_id`, `cutoff_utc`              | scope                                                                                               |
| `cutoff_receipt_locator`, `cutoff_receipt_sha256` | the cutoff this bundle was cut at                                                                   |
| `source_manifest[]`                               | S6 — every selected source, capture and qualified alike                                             |
| `source_manifest_sha256`                          | hash over the canonical manifest; bound downstream by S8, S9 and S11                                |
| `decision_input_payload`                          | the **canonical rendered payload** handed to the runner                                             |
| `decision_input_sha256`                           | hash of that payload                                                                                |
| `projection`                                      | `{ordering_version, redaction_version, projection_version, code_sha256, config_sha256, parameters}` |
| `policy_locator`, `matrix_sha256`                 | the **exact policy version** in force for this arm                                                  |
| `contains_private`                                | true ⇒ written under `private_bundles/`                                                             |
| `bundle_sha256`                                   | computed from content; **never caller-supplied**                                                    |

Projection rules are **deterministic**: a stated total ordering of entities and fields, a stated
redaction set, and a stated field projection — each versioned and hashed. Rederivation regenerates
`decision_input_payload` and must reproduce `decision_input_sha256` **and** `bundle_sha256`.

**S6 — Source manifest.** Ordered list, one entry per selected source. Two kinds, one chain — an
envelope-only manifest could not carry `standings_2025`, leaving one of A7's four required sources
outside the verified chain entirely.

| Field                                                                                                           | Kind               | Gating?                                  |
| --------------------------------------------------------------------------------------------------------------- | ------------------ | ---------------------------------------- |
| `kind ∈ {capture, qualified_artifact}`, `source_id`, `locator`                                                  | both               | **gate** — identity                      |
| `content_sha256` (canonical, per S13), `canonicalizer_id`, `canonicalizer_version`, `canonicalizer_code_sha256` | both               | **gate** — authoritative source identity |
| `envelope_sha256`, `payload_sha256`, `captured_at`                                                              | capture            | **gate**                                 |
| `commit_sha`, `path`, `git_blob_oid`, `blob_bytes_sha256`                                                       | qualified_artifact | **gate** — the frozen historical bytes   |
| `observed_worktree_bytes_sha256`, `byte_count`, `eol_profile`                                                   | qualified_artifact | **non-gating diagnostics only**          |

**A qualified artifact is pinned to a commit, not to the working tree.** The commit/path/blob
linkage and `blob_bytes_sha256` are verified; only the three worktree observations are diagnostic.
This is what lets the file be legitimately edited later without invalidating an old seal.

**S13 — Strict load and canonicalization.** Two versioned pure functions. Strictness operates on
**raw bytes**, because an already-parsed object has lost the information the check needs:

- **`load_json_strict(raw_json: bytes) -> object`** — rejects **duplicate keys at every nesting
  level** and rejects `NaN`, `Infinity` and `-Infinity`, **before** parsing discards them. In Python
  this means an `object_pairs_hook` that raises on a repeated key (it fires per object, so nesting is
  covered) and a `parse_constant` that raises; the stdlib default silently keeps the last duplicate
  and happily produces non-finite floats.
- **`canonical_json_v1(validated_obj) -> bytes`** — serializes **in memory** with
  `sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False`, appends **exactly one** LF, and
  encodes UTF-8 explicitly.

**Object-only canonicalization cannot qualify a source artifact** — it would accept a file whose
duplicate keys or non-finite values were already silently resolved. `content_sha256` is SHA-256 over
`canonical_json_v1(load_json_strict(raw_bytes))`. It is **not** derived from
`scripts/shared.py::save_json_canonical`'s on-disk output, and **this plan does not modify that
helper**.

**S7 — Runner config** (`runner_config_2026.json`, frozen). `provider, model, model_version,
reasoning, tools_policy, browsing, budget, retries, sampling_policy, prompt_locator, prompt_sha256,
rule_locators, rule_sha256s, runner_config_sha256`. **One immutable `runner_config_sha256` appears in
every model receipt**, identical across `minimal_legal` and `full_rich`.

**S8 — Decision-run receipt.** `decision_run_id, edition_id, arm_id, trial_id, runner_kind,
bundle_sha256, decision_input_sha256, source_manifest_sha256, cutoff_receipt_locator,
cutoff_receipt_sha256, policy_locator, matrix_sha256, predecessor_decision_hash,
predecessor_null_reason,
started_at, ended_at, output_decision_sha256`. `state_hash` is **null with a recorded reason** — no
`state_at` exists pre-kernel. Deterministic adds `code_sha256, config_sha256, input_hashes`. Model
adds `runner_config_sha256` (S7).

**S9 — Claim.** Design §4 field set plus binding: `claim_id, target, claim_type ∈ {ordinal_rank,
binary_probability, bounded_quantity}, horizon, assertion, confidence, bound, decisive_evidence,
contrary_evidence, cutoff_utc, edition_id, arm_id, trial_id, decision_run_id, bundle_sha256,
source_manifest_sha256, resolution_rule {rule, source, resolve_on}, outcome, score,
resolution_failed`. `outcome`/`score` start null.

**S10 — Evaluation config** (`evaluation_config_2026.json`, frozen). The **already-approved** design
§4 rules, hashed: Spearman footrule for `ordinal_rank`, Brier for `binary_probability`, bound-
normalized absolute error for `bounded_quantity`; aggregation order `claim → team → edition → trial
→ arm`; unresolved excluded and counted; unresolvable reported; median-with-range for
non-deterministic runners; `evaluation_config_sha256`.

**S11 — Seal.** `{edition_id, kind, season, arm_id, trial_id, cutoff_utc, cutoff_receipt_locator,
cutoff_receipt_sha256, ended_at, sealed_at, label ∈ {prospective, retrospective}, bundle_sha256,
bundle_locator, decision_input_sha256, source_manifest_sha256, policy_locator, matrix_sha256,
decision_sha256,
decision_locator, claims_sha256, claims_locator, receipt_sha256, receipt_locator,
predecessor_decision_hash, runner_kind, decision_hash}`. `decision_hash` covers every other field;
nothing binds `decision_hash` — the chain is acyclic.

**S12 — Experiment status.** Per edition: `{edition_id, expected_runs, verified_prospective_seals[],
experiment_status ∈ {complete, unavailable}, reason, computed_at}`. `experiment_status` is
**derived**: `complete` iff all **seven** verified prospective seals exist for that edition
(`record_points` ×1, `minimal_legal` ×3, `full_rich` ×3). Never manually asserted.

**S14 — Capture table** (`capture_table_2026.json`, resolved by `CAPTURE_TABLE_PATH`).
`{season, groups[]}`; group: `{group, components[]}` — exactly R4's eight groups and twelve
components, no additional fields. Grouping for S2 receipts comes from here; per-source policy
(windows, freshness, requiredness, `empty_valid`) comes **only** from S3.
`test_eight_groups_twelve_components_independent` pins it against R4.

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

- **I19** Selection is per source and per kind. **Captures:** the latest **verified** envelope with
  `captured_at <= cutoff_utc`; a post-cutoff envelope is never selected. **Qualified artifacts:** the
  content at the bound `commit_sha`/`path`, frozen per I54.
- **I20** `bundle_sha256` and `decision_input_sha256` are computed from content. There is **no
  caller-supplied factset or bundle hash**.
- **I43** The bundle binds the **canonical decision-input payload** the runner received, plus the
  versioned ordering, redaction and projection rules with their code and config hashes and
  parameters.
- **I21** Rederivation **regenerates** the decision-input payload from the sealed source manifest,
  re-verifying **every entry by kind** — captures via envelope and payload hashes, qualified
  artifacts via I55 — then re-applies the recorded projection and reproduces `decision_input_sha256`
  and `bundle_sha256`. It must cover **all four** A7 required sources, `data/2025/season_combined.json`
  included. Re-hashing an already-frozen bundle is not a test and is forbidden.
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
  claims, receipt, bundle, decision-input payload, source manifest, **every qualified artifact's
  bound commit/path/blob linkage**, cutoff receipt, matrix, and receipt↔decision agreement.
- **I32** Every ranking position carries at least one claim with a `resolution_rule` fixed before the
  outcome; every claim binds `bundle_sha256` and `source_manifest_sha256`.
- **I33** Both model arms bind an identical `runner_config_sha256` — provider, model, model_version,
  reasoning, budget, retries, sampling policy, prompt, rules, tools policy and browsing all equal. A
  mismatch fails the run.
- **I34** Model arms require 3 trials; deterministic requires 1. Under-sampling fails.
- **I45** Scoring and aggregation come from the frozen `evaluation_config_sha256`; no metric may be
  selected after results are seen.
- **I35** `experiment_status` is **derived** from the seven verified prospective seals per edition
  (S12), never manually asserted. Preseason and preview are computed independently.
- **I46** R5's baseline is reproducible: regular season = weeks `1 .. playoff_week_start − 1`;
  wins and points-for are **recomputed** from `weeks[playoff_week_start − 2].standings` and
  **cross-checked** against `roster_map[*].final_record`, failing closed on disagreement — a stored
  season-end aggregate is corroboration, never the input; ordering wins ↓, points-for ↓,
  `roster_id` ↑; source locator and hash bound into bundle and seal.

**Policy lifecycle**

- **I47** A policy version is **immutable once frozen**. `freeze` writes exactly one version file,
  refuses an already-frozen version, and never writes or modifies another version's file.
- **I48** Every bundle, run receipt and seal binds `policy_locator` + `matrix_sha256` of the version
  in force **for that arm**; reload re-reads that locator and verifies it still hashes to the bound
  value.
- **I49** Freezing `v2` leaves `v1`'s bytes unchanged **and** leaves the verification result of every
  `v1`-bound seal unchanged. A `v2` value never reaches a `v1`-bound seal.
- **I52** `v1` alone is **sufficient** for baseline accounting, bundle construction, sealing and
  rederivation: with only `v1` present and no `v2` on disk, the A3–A7 code path completes. **Gated at
  A6/E2E-A**, exercised with an isolated pre-cutoff **fixture clock** — it proves the path, and does
  not require production A7 operation to have happened first.

**Tranche A independence**

- **I50a** A7's required-source set is **exactly** the four sources enumerated in §8, read from the
  frozen `v1` policy's `required_for` rows.
- **I50b** The status of any component outside that set — `due`, `not_due` or `error` — cannot block
  A7. Non-baseline producers may run, fail, and be reported during A without affecting the safeguard.
- **I51** Baseline franchise continuity joins 2025 → 2026 by **`owner_id`**, not by `roster_id`
  (the two seasons are different Sleeper leagues, so `roster_id` is not durable across them). A 2026
  franchise whose owner has no 2025 record sorts **last** under R5's stated ordering — 0 wins, 0
  points-for, `roster_id` ascending — which is a consequence of R5, not an additional rule.

**Qualified-artifact identity (gate: A5, end-to-end at A6/E2E-A)**

- **I53** `load_json_strict` rejects duplicate keys **at every nesting level** and rejects `NaN`,
  `Infinity`, `-Infinity`, operating on **raw bytes** before parsing discards them.
  `canonical_json_v1` serializes in memory with `sort_keys=True, ensure_ascii=False, indent=2,
allow_nan=False`, appends exactly one LF, and encodes UTF-8. Both are versioned; neither derives
  from `save_json_canonical`'s on-disk output, which this plan leaves unmodified.
- **I54** At freeze, a qualified artifact binds `commit_sha`, `path`, `git_blob_oid`,
  `blob_bytes_sha256`, canonicalizer identity and canonical `content_sha256`. The **current worktree
  must canonically equal that blob** or the freeze fails. Worktree bytes, byte count and EOL profile
  are recorded as diagnostics only.
- **I55** Rederivation reads and verifies the **bound commit/path/blob — never the current
  worktree**: the blob must resolve at that commit/path, its bytes must hash to `blob_bytes_sha256`,
  and `canonical_json_v1(load_json_strict(blob))` must hash to `content_sha256`. **Missing or
  mismatched bound Git evidence fails closed.** A later legitimate worktree edit must not invalidate
  an old seal; a worktree difference is reported as `same_content_different_materialization` and is
  **diagnostic only**.
- **I56** All four A7 required sources appear in the source manifest with verified identity; a
  manifest missing any of them fails the bundle.

**Governance reachability (gate: A1b)**

- **I57** `v1` conforms to the S3 schema and contains **exactly** the seventeen declared rows — all
  twelve capture components plus `standings_2025`, `league_history_{2022,2023,2024}` and
  `player_crosswalk` — with `arms`/`required_for` nonempty **only** on the four A7-required rows.
- **I58** **No task's gate may require code or artifacts first delivered by a later task.** Enforced
  by the §8 gate-reachability census, which maps every gate invariant to the task delivering what it
  needs and must report zero violations.

**Optional-lane isolation (gate: A6/E2E-A)**

- **I59** The baseline path neither imports nor requires any optional producer module; accounting
  derives optional-component status from the store and the frozen policy without invoking them. The
  full A path runs with optional producer modules absent.

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
| `test_baseline_recomputes_wins_and_pf_and_crosschecks_final_record`                                                                                                                                 | I46    |
| `test_policy_version_immutable_and_freeze_refuses_overwrite`                                                                                                                                        | I47    |
| `test_freeze_never_writes_another_version_file`                                                                                                                                                     | I47    |
| `test_bundle_receipt_seal_bind_policy_locator_and_hash`                                                                                                                                             | I48    |
| `test_freezing_v2_leaves_v1_bytes_and_v1_bound_seals_unchanged`                                                                                                                                     | I49    |
| `test_v1_alone_completes_accounting_bundle_seal_and_rederive`                                                                                                                                       | I52    |
| `test_a7_required_set_is_exactly_the_four_named_sources`                                                                                                                                            | I50a   |
| `test_nonbaseline_component_due_or_error_cannot_block_a7`                                                                                                                                           | I50b   |
| `test_baseline_joins_2025_to_2026_by_owner_id`                                                                                                                                                      | I51    |
| `test_strict_loader_rejects_nested_duplicate_keys` / `test_strict_loader_rejects_nan_inf_neginf`                                                                                                    | I53    |
| `test_strict_loader_operates_on_raw_bytes_not_parsed_objects`                                                                                                                                       | I53    |
| `test_canonical_json_v1_params_and_single_trailing_lf`                                                                                                                                              | I53    |
| `test_freeze_requires_worktree_canonically_equal_to_bound_blob`                                                                                                                                     | I54    |
| `test_freeze_binds_commit_path_blob_oid_and_blob_bytes_sha256`                                                                                                                                      | I54    |
| `test_rederive_reads_bound_blob_not_current_worktree`                                                                                                                                               | I55    |
| `test_later_worktree_edit_does_not_invalidate_an_old_seal`                                                                                                                                          | I55    |
| `test_missing_or_mismatched_bound_git_evidence_fails_closed`                                                                                                                                        | I55    |
| `test_worktree_difference_reported_as_same_content_different_materialization`                                                                                                                       | I55    |
| `test_source_manifest_carries_capture_and_qualified_entries`                                                                                                                                        | I56    |
| `test_all_four_a7_sources_present_and_verified` / `test_manifest_missing_a_required_source_fails_bundle`                                                                                            | I56    |
| `test_v1_matches_schema_and_contains_exactly_the_declared_rows`                                                                                                                                     | I57    |
| `test_gate_reachability_census_reports_zero_violations`                                                                                                                                             | I58    |
| `test_baseline_path_runs_with_optional_producer_modules_absent`                                                                                                                                     | I59    |
| `test_accounting_reports_optional_status_without_invoking_producers`                                                                                                                                | I59    |
| `test_unmatched_2026_franchise_sorts_last_deterministically`                                                                                                                                        | I51    |

**End-to-end** — `test_p_only_e2e.py`, two tests:

> **A:** envelopes (A's components only) → tranche-A accounting → cutoff qualification → baseline
> bundle → deterministic run → claims → seal → reload verify → rederive from the source manifest.
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

| Task    | Delivers                                                                                                                                                                                                                                                                                                                                                                                                        | Gate (reachable at this task)                                                                                                           |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **A1**  | `.gitignore` private roots, envelope schema, write/verify, `CAPTURE_TABLE_PATH`, capture table                                                                                                                                                                                                                                                                                                                  | I1–I6, I37–I41 green **before any private write**                                                                                       |
| **A1b** | **freeze baseline policy `v1`** — all seventeen S3 rows (twelve components + `standings_2025`, `league_history_{2022,2023,2024}`, `player_crosswalk`), scope `baseline`: `arms`/`required_for` nonempty **only** on the four A7-required rows; every row carries window/freshness/`empty_valid` so A3 can report all twelve honestly. Freeze fn lives in `capture_2026.py`; its tests in `test_capture_2026.py` | **I47** (write-once, re-freeze refused), **I57** (schema + exactly the declared rows), **I58** (gate-reachability census, 0 violations) |
| **A2**  | **the three A7-required capture producers only** — `sleeper_rosters`, `sleeper_league`, `nfl_schedules`. The fourth required source, `standings_2025`, is a qualified artifact and needs no producer. **This is the sole producer predecessor of A3–A7.**                                                                                                                                                       | I9, I50a green                                                                                                                          |
| **A3**  | tranche-scoped accounting receipt + CLI                                                                                                                                                                                                                                                                                                                                                                         | I10–I13, I15, I16a, I16b, I50b green                                                                                                    |
| **A4**  | cutoff qualification + receipt                                                                                                                                                                                                                                                                                                                                                                                  | I17, I18, I42 (unit), R1 green                                                                                                          |
| **A5**  | **S13 strict load + canonicalizer**, projection rules, bundle compiler, source manifest, R5 baseline input                                                                                                                                                                                                                                                                                                      | I19, I20, I22, I43, I46, I51 green; **I53, I54, I55 (unit), I56** green                                                                 |
| **A6**  | deterministic run receipt, claims, seal, reload verify, rederive                                                                                                                                                                                                                                                                                                                                                | I24–I32, I44 green; **I21, I42 (end-to-end), I48, I52, I55, I59** green; **E2E-A** green                                                |
| **A7**  | **operate**: seal preseason + preview baselines before their cutoffs                                                                                                                                                                                                                                                                                                                                            | seals verify `prospective`                                                                                                              |

**I52 at A6 uses an isolated pre-cutoff fixture clock.** It proves the A3–A7 code path completes
with only `v1` on disk; it does **not** require production A7 operation to have happened first.
Nothing in A6's gate waits on A7.

### A-opt — parallel preservation lane (starts after A1; never gates A3–A7)

The 2026 evidence for these components is perishable, so the lane is real work with real deadlines —
it simply is not on the safeguard's critical path. Every component below has an owner, a command, a
cadence, a window, a capture deadline, a `v1` policy row, a receipt, and a downstream B gate.

| Component              | Command                                                   | Cadence | Availability window           | Capture deadline | `v1` row                    | Consumed by                     |
| ---------------------- | --------------------------------------------------------- | ------- | ----------------------------- | ---------------- | --------------------------- | ------------------------------- |
| `sleeper_users`        | `capture_2026.py --season 2026 --component sleeper_users` | daily   | open now                      | preseason cutoff | present, `required_for: []` | B3 `minimal_legal`, `full_rich` |
| `draft_meta`           | `… --component draft_meta`                                | daily   | opens at draft scheduling     | preseason cutoff | present, `required_for: []` | B3 both model arms              |
| `draft_picks`          | `… --component draft_picks`                               | daily   | opens at draft start          | preseason cutoff | present, `required_for: []` | B3 both model arms              |
| `sleeper_transactions` | `… --component sleeper_transactions`                      | daily   | open now                      | preview cutoff   | present, `required_for: []` | B3 `full_rich`                  |
| `sleeper_matchups`     | `… --component sleeper_matchups`                          | daily   | opens at schedule publication | preview cutoff   | present, `required_for: []` | B3 `full_rich`                  |

**Ownership:** the sole writer named at implementation kickoff owns the lane; it is not delegated
away from the A path's owner without an explicit hand-off.

**Deferral rule.** A-opt work may follow A7 **only when** a qualifying pre-cutoff capture already
exists for that component, **or** the next applicable cutoff is still open. Deferring past a closed
cutoff with no qualifying capture loses that evidence permanently and is not a scheduling choice.

**Receipts.** A-opt captures appear in the same accounting receipt as every other component, with
their own status. They are reported at `--tranche A` and **gate** at `--tranche B`.

**Lane gate.** I7 and I8 go green when the lane's producers land — written with the lane, exercised
with fixtures — and **B1 re-verifies both**. They never gate A3–A7 (I59): the safeguard path neither
imports nor requires the optional producer module they live in.

### A7 required-source set — exhaustive

Derived from what the `record_points` decision payload actually consumes, not from group membership.
**These four, and nothing else, can block A7** (I50a, I50b):

| Source                                              | Why fatal                                                                                                                                                                                                           | In the decision payload?      |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| `standings_2025` (`data/2025/season_combined.json`) | the ordering input: `weeks[..playoff_week_start−2].standings` for recomputed wins/points-for, `roster_map` for `roster_id → owner_id` and the `final_record` cross-check, and `playoff_week_start` for the boundary | **yes**                       |
| `sleeper_rosters` (2026)                            | defines which franchises exist to rank and carries the `owner_id` join key                                                                                                                                          | **yes**                       |
| `sleeper_league` (2026)                             | league-identity verification (I9); the seal must bind the league it is about                                                                                                                                        | no — verification and binding |
| `nfl_schedules` (2026)                              | cutoff qualification (A4), which A7 depends on                                                                                                                                                                      | no — determines the cutoff    |

**Explicitly not fatal to A** — attempted and reported, blocking only B: `sleeper_users`,
`draft_meta`, `draft_picks`, `sleeper_transactions`, `sleeper_matchups`, `sleeper_projections`,
`nfl_team_context`, `nfl_injuries`, `chat_export`.

`sleeper_users` is the instructive one. It sits in the same `league_identity` group as
`sleeper_league`, but the 2025→2026 join is by `owner_id`, which `sleeper_rosters` already carries;
`sleeper_users` adds display names, which are presentation, not decision. Group membership is
therefore not a proxy for requiredness — which is why S3 carries `required_for` **per component**
and I11 evaluates the tranche in scope.

### Tranche B — rich prospective contrast

| Task   | Delivers                                                                                                                                                       | Gate                                                                                                                                                                                         |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **B1** | remaining producers (`sleeper_projections`, `nfl_team_context`, `nfl_injuries`, `chat_export`) plus confirmation that **A-opt**'s five components are captured | I7, I8, I36 green — all twelve                                                                                                                                                               |
| **B2** | frozen **model-arm policy `v2`**, `runner_config_2026.json`, `evaluation_config_2026.json`                                                                     | Blake-approved, hashed, frozen before any B run; **I49 run against a NONEMPTY expected `v1`-seal set** — `v1`'s bytes and every existing `v1`-bound seal verify identically after the freeze |
| **B3** | `minimal_legal` + `full_rich` bundles                                                                                                                          | I23 green                                                                                                                                                                                    |
| **B4** | 3 paired trials per model arm                                                                                                                                  | I33, I34, I45 green                                                                                                                                                                          |
| **B5** | derived experiment status + R3 fallback                                                                                                                        | I14, I35 green; E2E-B green                                                                                                                                                                  |

### Gate reachability — a standing rule

**No task's gate may require code or artifacts first delivered by a later task** (I58). Every gate
above is satisfiable with what exists at or before its own task. The census below is part of §10 and
must report zero violations before implementation kickoff.

Three corrections this rule already forced: A1b previously demanded I48 (needs bundles, receipts and
seals from A5/A6), I49 (needs `v2` from B2) and I52 (needs the whole A3–A7 path) — none of which can
be green when A1b runs. And I52's own text named A1b as its gate, which is why the contradiction
survived earlier reads. Third: I50 sat in A2's gate while its cannot-block-A7 half needs A3's
accounting to be testable — split into I50a (required set, gated A2) and I50b (cannot-block, gated
A3), each keeping its existing named test. Fourth (architect pass, 2026-08-04): the census mapped 14
invariants while §8's cells name ~50, concealing five more placement defects — I9 sat at A1 needing
A2's `sleeper_league` producer (moved to A2); I7/I8 sat at A2 while their subjects are lane
producers (moved to the lane gate + B1); I23 sat at A5 with no `v1` rows to bind against (B3 alone);
I42's everywhere-check sat wholly at A4 (split unit A4 / end-to-end A6, the I55 convention); and I21
sat inside A5's range shorthand while §4 puts rederivation in `seal_2026.py` (A6). §10.B now
enumerates the full gate surface, and `v1` widened to all seventeen S3 rows so A3's
twelve-component reporting is derivable from the frozen matrix.

### Commands

```bash
export PY="/c/Users/blake/AppData/Local/Programs/Python/Python312/python"
export POLARS_SKIP_CPU_CHECK=1                 # required for the nflreadpy path in this shell

$PY -m pytest scripts/tests/ -q                                    # >= 343 passed / 2 skipped + new
$PY scripts/capture_2026.py --help                                 # exit 0 WITH output
$PY scripts/capture_2026.py --freeze-policy <candidate.json> --version v1 --expected-candidate-sha256 <approved-sha256>   # A1b: verifies the APPROVED candidate hash, stamps frozen_at + policy_sha256, writes content/governance/source_policy_2026.v1.json exactly once; refuses re-freeze or an unapproved candidate
$PY scripts/capture_2026.py --season 2026 --tranche A              # league id read + verified
$PY scripts/cutoff_2026.py --season 2026 --write-receipt
$PY scripts/bundle_2026.py --edition 2026-preseason --arm record_points \
    --policy content/governance/source_policy_2026.v1.json   # policy version is explicit
$PY scripts/seal_2026.py --verify-all
$PY scripts/seal_2026.py --rederive-all                            # regenerates decision-input payloads
$PY scripts/seal_2026.py --experiment-status --edition 2026-preseason
```

Every CLI ends `raise SystemExit(main())` and is proven to execute via `--help` before any gate
depends on its exit code — a `main()` that is never called exits 0 while doing nothing.

### A7 / B5 edition-run matrix (literal)

```bash
# A7 -- safeguard. Runs as soon as A6 passes; does NOT wait for tranche B.
# Gate on the FOUR required sources only. Any other component may be due or error.
$PY scripts/capture_2026.py --season 2026 --tranche A || exit 1
for ed in 2026-preseason 2026-wk01-preview; do
  $PY scripts/bundle_2026.py --edition "$ed" --arm record_points \
      --policy content/governance/source_policy_2026.v1.json || exit 1
  $PY scripts/seal_2026.py   --edition "$ed" --arm record_points --trial 1 || exit 1
done
# Independence check: A must complete with NO v2 on disk (I52).
test ! -f content/governance/source_policy_2026.v2.json \
  || echo "note: v2 exists; A still cites v1 and its seals are unaffected (I49)"

# B5 -- full experiment: 7 runs per edition (1 + 3 + 3).
for ed in 2026-preseason 2026-wk01-preview; do
  for arm in minimal_legal full_rich; do
    for t in 1 2 3; do
      $PY scripts/bundle_2026.py --edition "$ed" --arm "$arm" \
          --policy content/governance/source_policy_2026.v2.json || exit 1
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

1. **B2 configurations require Blake's approval before freezing** — model-arm policy `v2`, runner,
   transformations, evaluation. B cannot start without them; **A is unaffected**, because A freezes
   its own `v1` at A1b.
   1b. **`v1`'s contents require Blake's approval at A1b** — it is immutable once frozen and every A
   seal cites it permanently. Its seventeen rows cover every source, but only the four A7-required
   rows carry nonempty `arms`/`required_for`; a mistake in it cannot be corrected in place, only
   superseded by a `v3` that A's existing seals will not cite.
2. **Sleeper projections endpoint shape** for 2026 is unverified against a live response (B1).
3. **Preseason cutoff is 31 days out** (`2026-09-03T00:20:00Z`). Tranche A exists so this date is met
   by the safeguard regardless of B's progress.

## 10. Self-review

Three censuses. No other section reopened.

### A. Source-chain verification

| Stage               | Carries                                                                                                           | Verified against                                                                            |
| ------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| S6 source manifest  | one entry per source; `kind`, `locator`, canonical `content_sha256`, canonicalizer identity                       | —                                                                                           |
| … capture entries   | `envelope_sha256`, `payload_sha256`, `captured_at`                                                                | re-read envelope, both hashes (I5, I21)                                                     |
| … qualified entries | `commit_sha`, `path`, `git_blob_oid`, `blob_bytes_sha256`                                                         | blob resolves at commit/path; bytes hash; `canonical_json_v1(load_json_strict(blob))` (I55) |
| S5 bundle           | `source_manifest[]`, `source_manifest_sha256`, `decision_input_payload`, `decision_input_sha256`, `bundle_sha256` | I20, I43                                                                                    |
| S8 run receipt      | `source_manifest_sha256`, `bundle_sha256`, `decision_input_sha256`                                                | I31                                                                                         |
| S9 claim            | `bundle_sha256`, `source_manifest_sha256`                                                                         | I32                                                                                         |
| S11 seal            | `source_manifest_sha256` + every hash above                                                                       | I31                                                                                         |
| Reload / rederive   | regenerates the payload from the **manifest**, per kind                                                           | I21, I55 — all four A7 sources                                                              |

All four A7 required sources are inside the chain: `sleeper_rosters`, `sleeper_league`,
`nfl_schedules` as `capture`; `standings_2025` as `qualified_artifact`. The envelope-only manifest
could not represent the fourth at all — that was the break.

**Strictness is at the byte boundary.** `load_json_strict` takes raw bytes and rejects nested
duplicate keys and `NaN`/`Infinity`/`-Infinity` **before** parsing discards them; canonicalizing an
already-parsed object would silently accept a file whose duplicates were resolved last-wins.
Measured on `data/2025/season_combined.json`: strict parse passes, and canonical worktree equals
canonical committed blob at `29203e49…`, so I54's freeze equality holds today.

**Rederivation reads the frozen blob, not the worktree.** Bound commit/path/blob linkage and
`blob_bytes_sha256` are gates; `observed_worktree_bytes_sha256`, `byte_count` and `eol_profile` are
diagnostics. That distinction is load-bearing: the worktree copy is CRLF (`a50e041c…`, 392,064
bytes) while the committed blob is LF (`9e5ac6b0…`, 377,620) — a 14,444-byte difference on identical
content. Gating on the worktree would break every seal on a fresh clone; gating on the blob also
means a **later legitimate edit to the file cannot invalidate an old seal**. Missing or mismatched
Git evidence fails closed.

### B. Gate-reachability census

Task order for reachability: A1 < A1b < A2 < A3 < A4 < A5 < A6 < A7; the A-opt lane opens after A1
and must land by B1; A7 ≤ B1 < B2 < B3 < B4 < B5. A row is reachable iff every Delivered-by task is
at or before its Gate task. `test_gate_reachability_census_reports_zero_violations` parses §8's gate
cells and this table **from the contract file** and asserts mechanically: every invariant token
(`I\d+a?b?` or `R1`) in a §8 gate cell has exactly one row here, every row satisfies the ordering,
and no row is marked unreachable.

| Invariant          | Gate                             | Needs                                                   | Delivered by       | Reachable |
| ------------------ | -------------------------------- | ------------------------------------------------------- | ------------------ | --------- |
| I1–I5              | A1                               | envelope write/verify + `fetch_sleeper.fetch_json`      | A1                 | ✅        |
| I6                 | A1                               | private write path, fixture private component           | A1                 | ✅        |
| I37–I41            | A1                               | `.gitignore`, git guards, containment checks            | A1                 | ✅        |
| I47, I57, I58      | A1b                              | freeze fn (`capture_2026.py`) + `v1` + this contract    | A1b                | ✅        |
| I9                 | A2                               | `sleeper_league` producer + `data/2026/league.json`     | A2                 | ✅        |
| I50a               | A2                               | frozen `v1` required-source rows                        | A1b                | ✅        |
| I10–I13            | A3                               | producers + accounting + all-seventeen-row `v1` windows | A1b, A2, A3        | ✅        |
| I15                | A3                               | receipt writer (unit; E2E-A private-leak control at A6) | A3                 | ✅        |
| I16a, I16b         | A3                               | tranche-scoped gate + CLI                               | A3                 | ✅        |
| I50b               | A3                               | required producers + tranche-scoped accounting          | A2, A3             | ✅        |
| I17, I18, R1       | A4                               | verified `nfl_schedules` envelope + qualification       | A2, A4             | ✅        |
| I42                | A4 (unit), A6/E2E-A (everywhere) | receipt binding; then bundle + seal + reload            | A4; A5, A6         | ✅        |
| I19, I20, I22      | A5                               | selection + bundle compiler                             | A5                 | ✅        |
| I43, I46, I51      | A5                               | projection, R5 input, owner-id join                     | A1b, A5            | ✅        |
| I53, I54, I56      | A5                               | strict loader, canonicalizer, bundle compiler, manifest | A5                 | ✅        |
| I55                | A5 (unit), A6/E2E-A (end-to-end) | manifest + rederive path                                | A5, A6             | ✅        |
| I24–I32, I44       | A6                               | receipt, claims, seal layer                             | A5, A6             | ✅        |
| S3 freeze/drift    | A6                               | frozen policy + runs for drift to invalidate            | A1b, A5, A6        | ✅        |
| I21, I48, I52, I59 | A6 / E2E-A                       | bundle, receipt, seal, full A path                      | A5, A6             | ✅        |
| I7, I8             | B1 (lane landing is non-gating)  | optional-lane producers                                 | lane (post-A1), B1 | ✅        |
| I36                | B1                               | all twelve producers                                    | lane, B1           | ✅        |
| I49                | B2                               | `v2` **and a nonempty `v1`-bound seal set**             | B2 (after A7)      | ✅        |
| I23                | B3                               | frozen `v2` rows + model-arm bundles                    | B2, B3             | ✅        |
| I33, I34, I45      | B4                               | runner + evaluation configs, paired trials              | B2, B4             | ✅        |
| I14                | B5                               | `v2` chat row + B sealing gate                          | B2, B5             | ✅        |
| I35                | B5                               | seven-seal derivation                                   | B5                 | ✅        |

**Violations: 0 across the full gate surface** — every invariant token in a §8 gate cell is mapped.
History: the first pass found 3 (A1b demanding I48/I49/I52 — I52 now runs at A6 against an isolated
pre-cutoff **fixture clock**, proving the path without production A7; I49 at B2 against a
**nonempty** expected `v1`-seal set, so it cannot pass vacuously). The I50 correction found a 4th —
I50 at A2 while its cannot-block-A7 half needs A3's accounting; split into I50a/I50b, the two
existing named tests mapping one-to-one. The 2026-08-04 architect pass found the census itself
under-enumerated — 14 rows against ~50 gate tokens — concealing five more placement defects, fixed
in §8: I9 → A2, I7/I8 → lane + B1, I23 → B3 alone, I42 split A4/A6, I21 out of A5's range.
Under-enumeration is how each survived: a census that lists only the invariants already under
suspicion measures scope, not correctness.

### C. Optional-lane orphan census

| Component              | Owner | Command | Cadence | Window | Deadline | `v1` row | Receipt | B gate |
| ---------------------- | ----- | ------- | ------- | ------ | -------- | -------- | ------- | ------ |
| `sleeper_users`        | ✅    | ✅      | ✅      | ✅     | ✅       | ✅       | ✅      | ✅ B3  |
| `draft_meta`           | ✅    | ✅      | ✅      | ✅     | ✅       | ✅       | ✅      | ✅ B3  |
| `draft_picks`          | ✅    | ✅      | ✅      | ✅     | ✅       | ✅       | ✅      | ✅ B3  |
| `sleeper_transactions` | ✅    | ✅      | ✅      | ✅     | ✅       | ✅       | ✅      | ✅ B3  |
| `sleeper_matchups`     | ✅    | ✅      | ✅      | ✅     | ✅       | ✅       | ✅      | ✅ B3  |

**Orphans: 0.** A-opt starts after A1 and runs alongside the critical path; it is a predecessor to
nothing in Tranche A. Deferral past A7 is permitted **only** with a qualifying pre-cutoff capture in
hand or the next applicable cutoff still open — so "optional" bounds the _ordering_, never the
_obligation_, and perishable evidence is not quietly lost to sequencing.

**The critical path is now three producers.** A2 delivers `sleeper_rosters`, `sleeper_league` and
`nfl_schedules`; `standings_2025` needs none. I59 proves the baseline neither imports nor requires
optional producer modules, tested with those modules absent — so optional _implementation_, not just
optional runtime status, is off the safeguard's path.
