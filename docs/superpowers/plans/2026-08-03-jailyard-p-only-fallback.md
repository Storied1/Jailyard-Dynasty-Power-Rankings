# Jailyard — P-only 2026 Preservation and Sealing: Acceptance Contract

**Status:** DRAFT — awaiting Blake's binary review. Not authorized for implementation.

**Design authority:** `docs/superpowers/specs/2026-08-01-jailyard-writer-foundation-design.md`
APPROVED at `9805426`, §6. That section requires this path to exist and states it "may run only
through a separately approved P-only implementation plan." Material deviation requires re-approval.

**Form:** acceptance contract — schemas, invariants, named tests, files, commands, gates. **No
implementation bodies.** The prior revision embedded ~1,200 lines of pseudocode; two review rounds
showed that form generates defects faster than it removes them. Implementation is written TDD at
execution time against the invariants below.

**Relationship to the kernel plan.** `2026-08-02-jailyard-temporal-kernel.md` is K1–K3 only; its
P1–P3 are superseded by this document. This plan neither unblocks nor depends on it.

---

## 1. Verified facts (checked against the repo, not assumed)

| Fact                         | Value                                             | Evidence                                                                                                                                              |
| ---------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026 league id               | `1312884727480352768`                             | `fetch_sleeper.py:38`, `config.js`, `data/2026/league.json` (season 2026, "The Jailyard") — **not a Blake input**; verify against the fetched payload |
| First regular-season kickoff | `2026-09-10T00:20:00Z`                            | Blake, 2026-08-03. **Test fixture only** — production derives it from the captured schedule                                                           |
| Preseason cutoff             | `2026-09-03T00:20:00Z`                            | kickoff − 7d. **31 days from 2026-08-03**                                                                                                             |
| Preview cutoff               | `2026-09-10T00:19:59Z`                            | strictly before kickoff                                                                                                                               |
| 2026 schedule on disk        | **absent**                                        | `data/external/` stops at 2025 — acquisition is real work, not a read                                                                                 |
| polars / nflreadpy           | import cleanly **with** `POLARS_SKIP_CPU_CHECK=1` | verified in this shell                                                                                                                                |

## 2. Rulings recorded (Blake, 2026-08-03)

**R1 — Cutoffs.** Preseason = 7 days before the qualified first regular-season kickoff. Preview =
strictly before that kickoff. Both derived from a **verified schedule capture** and bound through a
**cutoff-qualification receipt**. Never hard-coded in production.

**R2 — Arms.** The prospective evaluation is three arms:

| `arm_id`        | `runner_kind` | Trials | Evidence                                |
| --------------- | ------------- | ------ | --------------------------------------- |
| `record_points` | deterministic | 1      | prior-season final standings            |
| `minimal_legal` | model         | 3      | franchise identity, draft, roster facts |
| `full_rich`     | model         | 3      | all available families                  |

The two model arms bind **identical** provider, model, model_version, prompt hash, rule hashes, and
tool/browsing policy. Only the bundle differs. **Baseline + one model arm is not an evidence
experiment** — it confounds runner kind with evidence richness.

**R3 — Degradation.** If the model contrast cannot complete before a cutoff, seal the deterministic
baseline as a **prospective record** and mark the experiment `unavailable`. Preseason and preview
are processed **independently**: a missing preseason does not contaminate preview.

**R4 — Capture groups.** Eight accounting groups; components are provenance atoms.

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

**Every component has an executable producer.** Projections are automated via the Sleeper
projections endpoint — not classified permanently manual. `nfl_context` is ingested from nflreadpy.
`chat_export` is the sole manual component and **must be refreshed before each seal** (I14).

## 3. Files

| Path                                                                                                                          | Responsibility                                               | Git            |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | -------------- |
| `scripts/capture_2026.py`                                                                                                     | envelope write/verify, component producers, accounting       | tracked        |
| `scripts/cutoff_2026.py`                                                                                                      | kickoff qualification from captured schedule, cutoff receipt | tracked        |
| `scripts/bundle_2026.py`                                                                                                      | frozen bundle compiler, capture manifest                     | tracked        |
| `scripts/seal_2026.py`                                                                                                        | run receipts, claims, seals, reload verify, rederive         | tracked        |
| `scripts/tests/test_capture_2026.py`, `test_cutoff_2026.py`, `test_bundle_2026.py`, `test_seal_2026.py`, `test_p_only_e2e.py` | §6                                                           | tracked        |
| `content/governance/capture_table_2026.json`                                                                                  | the eight groups + components                                | tracked        |
| `content/governance/runner_config_2026.json`                                                                                  | shared model-arm binding (R2)                                | tracked        |
| `data/captures/2026/public/`                                                                                                  | public capture envelopes                                     | tracked        |
| `data/captures/2026/_receipts/`                                                                                               | accounting + cutoff receipts                                 | tracked        |
| `content/seals/2026/{edition_id}/{arm_id}/trial{n}/`                                                                          | seals, decisions, claims, run receipts                       | tracked        |
| `private_captures/2026/`                                                                                                      | private envelopes (chat)                                     | **gitignored** |
| `private_bundles/2026/`                                                                                                       | bundles containing private components                        | **gitignored** |
| `docs/superpowers/plans/capture-manual-ingest.md`                                                                             | chat ingestion procedure                                     | tracked        |

`CAPTURE_TABLE_PATH` **must be defined** as a module constant resolving to
`content/governance/capture_table_2026.json`. The prior revision referenced it without defining it.

## 4. Schemas

**S1 — Capture envelope** (`{root}/{source_id}/{captured_at_compact}.json`)

| Field                 | Meaning                                                                 |
| --------------------- | ----------------------------------------------------------------------- |
| `source_id`           | component identity                                                      |
| `request`             | `{endpoint_or_dataset, params}` — the **exact source request identity** |
| `season`, `league_id` | scope of the observation                                                |
| `locator`             | **repo-relative** path of this envelope                                 |
| `captured_at`         | exact UTC instant this repo first held it                               |
| `known_at_basis`      | how `known_at` is defensibly established for this source                |
| `access_scope`        | `public` \| `league_private`                                            |
| `privacy`             | `public` \| `private` (custody, independent of scope)                   |
| `payload_sha256`      | hash of `payload`                                                       |
| `envelope_sha256`     | hash of every field above **excluding itself**                          |
| `payload`             | the observation                                                         |

**S2 — Accounting receipt.** `{season, generated_at, groups[], unmet_required_groups[], ok}`. Each
group: `{group, required, status ∈ {captured, incomplete, error}, components[]}`. Each component
independently: `{source_id, required, mechanism, cadence, availability_window, status ∈ {captured,
due, not_due, error}, captured_at, payload_sha256, envelope_sha256, error, acquisition_trigger}`.

**S3 — Cutoff-qualification receipt.** `{season, kickoff_utc, kickoff_source_locator,
kickoff_source_envelope_sha256, derivation_version, preseason_cutoff_utc, preview_cutoff_utc,
qualified_at, receipt_sha256}`.

**S4 — Capture manifest** (inside the bundle). Ordered list of
`{source_id, locator, envelope_sha256, payload_sha256, captured_at}` — one entry per selected
envelope. This is what rederivation reconstructs from (I21).

**S5 — Frozen bundle.** `{edition_id, arm_id, cutoff_utc, capture_manifest[], transformations[],
transformations_version, contains_private, bundle_sha256}`. Each transformation:
`{step, version, source_ids[], description}`.

**S6 — Decision-run receipt.** Design §5 field set: `decision_run_id, edition_id, arm_id, trial_id,
bundle_sha256, predecessor_decision_hash, started_at, ended_at, output_decision_sha256,
runner_kind`. `state_hash` is **null with a recorded reason** — no `state_at` exists pre-kernel;
`capture_manifest_sha256` is bound in its place. Deterministic adds `code_hash, config_hash,
input_hashes`. Model adds `provider, model, model_version, reasoning, prompt_hash, rule_hashes,
tools_policy, browsing, budget, retries, sampling_policy`.

**S7 — Claim.** Design §4 field set: `claim_id, target, claim_type ∈ {ordinal_rank,
binary_probability, bounded_quantity}, horizon, assertion, confidence, bound (bounded_quantity),
decisive_evidence, contrary_evidence, cutoff_utc, edition_id, arm_id, trial_id, decision_run_id,
resolution_rule {rule, source, resolve_on}, outcome, score, resolution_failed`. `outcome`/`score`
start null.

**S8 — Seal.** `{edition_id, kind, season, arm_id, trial_id, cutoff_utc, ended_at, sealed_at,
label ∈ {prospective, retrospective}, bundle_sha256, bundle_locator, capture_manifest_sha256,
decision_sha256, decision_locator, claims_sha256, claims_locator, receipt_sha256, receipt_locator,
predecessor_decision_hash, runner_kind, decision_hash}`. `decision_hash` covers every other field.
Nothing binds `decision_hash` — the chain is acyclic.

**S9 — Experiment status.** `{edition_id, arms_completed[], experiment_status ∈ {complete,
unavailable}, reason}` per edition, written independently per R3.

## 5. Invariants

Each is testable and named in §6.

**Capture**

- **I1** A failed fetch is never an envelope. `fetch_sleeper.fetch_json` returns `None` on exhausted
  retries (`fetch_sleeper.py:69`); `None`, non-object, and empty payloads are refused.
- **I2** `capture()` validates its own arguments — instant shape, privacy, scope, basis — because
  manual ingestion never passes through `main()`.
- **I3** Append-only: an existing envelope path is never overwritten.
- **I4** A **future-dated** capture (`captured_at` > trusted now) is refused.
- **I5** Verification checks **payload and metadata**: `payload_sha256` over `payload`, and
  `envelope_sha256` over all other fields. Either mismatch ⇒ the envelope is **not coverage**.
- **I6** Private components land only under `private_captures/`; nothing private is ever written
  under a tracked root.
- **I7** Per-leg/per-week sources record `*_requested` and raise on any unreadable leg. An outage is
  never byte-identical to a quiet week.
- **I8** `draft_picks` resolves `draft_id` then fetches `/draft/{id}/picks`; the row fails unless
  `pick_count > 0` **and** pick order is preserved.
- **I9** The league id used is read from `data/2026/league.json` and **verified equal** to the
  `league_id` in the fetched league payload.

**Accounting**

- **I10** Exactly eight groups; every component reported independently with its own status and
  hashes.
- **I11** A group passes only when every **required** component passes.
- **I12** Status is availability-aware: `not_due` before a component's availability window opens,
  `due` when open and absent or stale, `captured` when a verified envelope exists inside its
  freshness window, `error` when a producer failed this run.
- **I13** A component reaching `captured` after ingestion clears the lane — no component is
  permanently `unavailable`.
- **I14** `chat_export` must have been captured **after the previous seal and before the next**; a
  stale chat export blocks sealing.
- **I15** Receipts carry hashes and metadata only. **No payload, and never raw chat.**
- **I16** The CLI exits non-zero when any required group is not `captured`; the receipt is still
  written.

**Cutoff**

- **I17** Kickoff is derived from a **verified** `nfl_schedules` envelope, with venue-timezone
  conversion — never by appending `Z` to a local time, never hard-coded in production.
- **I18** The cutoff receipt binds the source locator, its `envelope_sha256`, and a
  `derivation_version`. Cutoffs are read from this receipt everywhere downstream.

**Bundle**

- **I19** The compiler selects, per component, the latest **verified** envelope with
  `captured_at <= cutoff_utc`. A post-cutoff envelope is never selected.
- **I20** The bundle binds locators, hashes, timestamps, and **versioned transformations**. There is
  **no caller-supplied factset hash**; `bundle_sha256` is computed from content.
- **I21** Rederivation **reconstructs** the bundle from the sealed capture manifest by re-reading
  and re-verifying each envelope, then compares to `bundle_sha256`. Re-hashing the already-frozen
  bundle is not a test and is explicitly forbidden.
- **I22** A bundle whose manifest includes any private component sets `contains_private: true` and
  is written under `private_bundles/`. Only its hashes may be committed.
- **I23** `full_rich` fails to build if any required rich family is **absent or empty**;
  `minimal_legal` is a strict subset of `full_rich`.

**Decision, seal, evaluation**

- **I24** `started_at`, `ended_at`, `sealed_at` come from a **trusted clock** in production; clock
  injection exists for tests only.
- **I25** `started_at <= ended_at <= sealed_at`, enforced.
- **I26** `label` is `prospective` only when **both** `ended_at` and `sealed_at` are `<= cutoff_utc`.
  Otherwise `retrospective`. There is no mechanism to reclassify, and none may be added.
- **I27** A run is closed before sealing; the seal binds the **closed** receipt's hash, not a path.
- **I28** Every artifact is keyed by `(edition_id, arm_id, trial_id)`.
- **I29** Predecessor lookup returns seals from the **same** `arm_id` and `trial_id` at a strictly
  earlier cutoff. A foreign predecessor raises.
- **I30** Seals are immutable; seal files use a distinct suffix so decision, claims and receipt
  bodies are never deserialized as seals.
- **I31** Load-time verification recomputes and cross-checks **every** hash: seal metadata, decision,
  claims, receipt, bundle, capture manifest, and receipt↔decision agreement.
- **I32** Every ranking position carries at least one claim with a `resolution_rule` fixed before the
  outcome.
- **I33** Both model arms bind identical `provider`, `model`, `model_version`, `prompt_hash`,
  `rule_hashes`, `tools_policy`, `browsing`. A mismatch fails the run.
- **I34** Model arms require 3 trials; a deterministic arm requires 1. Under-sampling fails.
- **I35** Per R3, an incomplete model contrast writes `experiment_status: unavailable` with a reason
  and still seals the baseline as a prospective record. Preseason and preview are independent.

## 6. Named tests

Every test must be **observed failing** with its rule removed before the task is complete. A green
suite alone is not acceptance.

| Test                                                                  | Proves |
| --------------------------------------------------------------------- | ------ |
| `test_failed_fetch_is_never_written`                                  | I1     |
| `test_capture_validates_its_own_arguments`                            | I2     |
| `test_append_only_refuses_overwrite`                                  | I3     |
| `test_future_dated_capture_refused`                                   | I4     |
| `test_tampered_payload_is_not_coverage`                               | I5     |
| `test_tampered_metadata_is_not_coverage`                              | I5     |
| `test_private_component_stays_outside_tracked_roots`                  | I6     |
| `test_partial_leg_failure_is_not_an_empty_week`                       | I7     |
| `test_all_legs_read_and_empty_is_valid`                               | I7     |
| `test_draft_reaches_picks_and_fails_on_metadata_only`                 | I8     |
| `test_league_id_verified_against_fetched_payload`                     | I9     |
| `test_eight_groups_every_component_independent`                       | I10    |
| `test_group_passes_only_when_every_required_component_passes`         | I11    |
| `test_not_due_before_window_due_after`                                | I12    |
| `test_stale_component_returns_to_due`                                 | I12    |
| `test_component_clears_after_ingestion`                               | I13    |
| `test_stale_chat_blocks_sealing`                                      | I14    |
| `test_receipt_carries_no_payload_or_chat`                             | I15    |
| `test_cli_exits_nonzero_on_unmet_required_group`                      | I16    |
| `test_kickoff_derived_with_venue_timezone`                            | I17    |
| `test_kickoff_never_hardcoded_in_production_path`                     | I17    |
| `test_cutoff_receipt_binds_source_and_version`                        | I18    |
| `test_preseason_cutoff_is_seven_days_before_kickoff`                  | R1     |
| `test_preview_cutoff_is_strictly_before_kickoff`                      | R1     |
| `test_compiler_excludes_post_cutoff_envelopes`                        | I19    |
| `test_bundle_binds_versioned_transformations`                         | I20    |
| `test_no_caller_supplied_factset_hash`                                | I20    |
| `test_rederive_reconstructs_from_capture_manifest`                    | I21    |
| `test_rederive_fails_when_an_envelope_changed`                        | I21    |
| `test_private_bundle_stays_untracked`                                 | I22    |
| `test_full_rich_fails_on_empty_required_family`                       | I23    |
| `test_minimal_is_strict_subset_of_full`                               | I23    |
| `test_production_clock_is_not_injectable`                             | I24    |
| `test_timestamp_ordering_enforced`                                    | I25    |
| `test_prospective_requires_both_completion_and_sealing_before_cutoff` | I26    |
| `test_late_completion_early_seal_is_retrospective`                    | I26    |
| `test_backdating_is_impossible`                                       | I26    |
| `test_sealing_an_open_run_refused`                                    | I27    |
| `test_artifacts_keyed_by_edition_arm_trial`                           | I28    |
| `test_same_arm_same_trial_predecessor_lookup`                         | I29    |
| `test_cross_arm_predecessor_poison_rejected`                          | I29    |
| `test_cross_trial_predecessor_poison_rejected`                        | I29    |
| `test_seal_immutable_and_bodies_not_seals`                            | I30    |
| `test_reload_cross_checks_every_hash`                                 | I31    |
| `test_tampered_bundle_decision_claims_receipt_detected`               | I31    |
| `test_every_position_carries_a_claim`                                 | I32    |
| `test_model_arms_share_identical_runner_binding`                      | I33    |
| `test_trial_counts_enforced`                                          | I34    |
| `test_incomplete_contrast_marks_experiment_unavailable`               | I35    |
| `test_preseason_failure_does_not_contaminate_preview`                 | I35    |

**End-to-end** — `test_p_only_e2e.py`, one test over the whole chain:

> capture envelopes → accounting → cutoff qualification → minimal + full bundles → runs (3 arms,
> correct trial counts) → claims → seals → reload and verify → rederive from the capture manifest.

with controls in the same module: **missing component**, **post-cutoff envelope**, **private leak**,
**cross-arm predecessor**, **backdating**, **tamper** (each of envelope, bundle, decision, claims,
receipt, seal), and **retry** (a crash between run-close and seal leaves no valid seal; re-running is
safe and does not double-seal).

## 7. Tasks and gates

Each task: write named tests → observe them fail → implement → green → **observe each control fail
with its rule removed** → commit. Binary gates; no "approve with notes".

| Task   | Delivers                                                                    | Gate                                                       |
| ------ | --------------------------------------------------------------------------- | ---------------------------------------------------------- |
| **F1** | envelope schema, write/verify, `CAPTURE_TABLE_PATH`, capture table          | I1–I6, I9 green + controls fired                           |
| **F2** | producers for all 11 components incl. automated projections and nfl_context | I7, I8 green; every component has a producer               |
| **F3** | accounting receipt + CLI                                                    | I10–I16 green; `--help` exits 0 with output                |
| **F4** | cutoff qualification + receipt                                              | I17, I18, R1 green                                         |
| **F5** | bundle compiler + capture manifest                                          | I19–I23 green                                              |
| **F6** | run receipts, claims, seals, reload verify, rederive                        | I24–I35 green                                              |
| **F7** | end-to-end + all controls                                                   | `test_p_only_e2e.py` green, every control observed failing |
| **F8** | operate: baseline capture, cutoff qualification, seals                      | receipts green; seals verify `prospective`                 |

**Commands** (interpreter and env pinned):

```bash
export PY="/c/Users/blake/AppData/Local/Programs/Python/Python312/python"
export POLARS_SKIP_CPU_CHECK=1                 # required for the nflreadpy path in this shell

$PY -m pytest scripts/tests/ -q                                    # >= 343 passed / 2 skipped + new
$PY scripts/capture_2026.py --help                                 # exit 0 WITH output
$PY scripts/capture_2026.py --season 2026                          # league id read + verified, not passed
$PY scripts/cutoff_2026.py --season 2026 --write-receipt
$PY scripts/bundle_2026.py --edition 2026-preseason --arm full_rich
$PY scripts/seal_2026.py --edition 2026-preseason --arm full_rich --trial 1
$PY scripts/seal_2026.py --verify-all
$PY scripts/seal_2026.py --rederive-all                            # reconstructs from capture manifests
```

Every CLI ends `raise SystemExit(main())` and is proven to execute via `--help` before any gate
depends on its exit code — a `main()` that is never called exits 0 while doing nothing.

**Staging guard** (F8): check the **index**, not `git status` — `private_captures/` and
`private_bundles/` are gitignored and can only reach the index via `git add -f`.

```bash
git diff --cached --name-only | grep -qE '^(private_captures|private_bundles)/' \
  && { echo "STOP: private artifact staged"; exit 1; }
```

**F8 stops** after sealing. Scheduler activation and any workflow push require Blake's explicit
approval of that exact action and are **not** authorized by approving this contract.

## 8. Open items

1. **Model-arm runner binding** — provider/model/version/prompt/rules must be fixed in
   `runner_config_2026.json` **before** the first model run, and identical across both arms (I33).
2. **Sleeper projections endpoint shape** for 2026 is unverified against a live response; F2 must
   confirm it before relying on the automated producer.
3. **Preseason cutoff is 31 days out** (2026-09-03T00:20:00Z). If F1–F7 will not complete in time,
   R3 applies: seal the baseline, mark the experiment `unavailable`, and preview remains available
   independently.

## 9. Self-review

**Form.** Acceptance contract within the 300–400 line boundary, no implementation bodies. Every
section is something an implementer tests against rather than transcribes.

**Corrections incorporated.** League id verified in-repo and no longer a Blake input (I9); kickoff
`2026-09-10T00:20:00Z` recorded as a fixture with production deriving it from the captured schedule
(I17); `CAPTURE_TABLE_PATH` given a definition requirement; `POLARS_SKIP_CPU_CHECK=1` pinned;
executable producers required for all eleven components with projections automated; availability-
aware `due`/`not_due`/freshness and pre-seal chat refresh (I12–I14); full envelope binding with
metadata verification and future-date rejection (S1, I4, I5); per-component accounting and rich-
family emptiness gate (I10, I23); compiler-selected verified envelopes with versioned
transformations and no caller-supplied factset hash (I19, I20); private captures and private bundles
out of Git (I6, I22); trusted clock with ordering and dual-condition prospectivity (I24–I26);
artifacts keyed by edition/arm/trial with same-arm predecessor lookup and poison tests (I28, I29);
full receipt and claims schemas with load-time cross-checks (S6, S7, I31); end-to-end plus all named
controls (§6).

**Rederivation replaced.** The prior test re-hashed the already-frozen bundle, so it could not fail.
I21 requires reconstruction from the sealed capture manifest by re-reading and re-verifying each
envelope.

**Known gap.** The 2026 projections endpoint shape is unverified (open item 2). Stated, not assumed.

**What would make this contract wrong.** If sealing begins after 2026-09-03T00:20:00Z, every
preseason seal is `retrospective` by construction and that edition's prospective test is lost. The
contract reports that honestly; per I26 nothing backdates it.
