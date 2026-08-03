# Jailyard — Temporal League-Intelligence and Decision-Evaluation Design

**Date:** 2026-08-01, revised 2026-08-02
**Status:** **DRAFT — awaiting Blake review.** Not approved. Supersedes the APPROVED revision at
`072f4ea`, whose approval is preserved in git history and remains the authority until this
revision is approved.
**Why a new revision rather than a plan correction:** a clean-room review of the product
objective found that this document's own explicit exclusions — typed temporal evidence,
measurable ranking evaluation, and clean-room prospective testing — conflict with what is
actually being built. That is an architectural finding, not an implementation defect.
**Relationship to prior work:** replaces the "weeks 1-6 next" sequencing in
`2026-06-04-jailyard-2025-catchup-design.md`. The implementation plan at
`docs/superpowers/plans/2026-08-02-jailyard-writer-foundation-d1.md` (`df7c1ea`) stands
**unmodified as a requirements inventory** until this design is approved.

---

## What the system actually is

Not primarily a writing pipeline. A **temporally replayable league-intelligence and
decision-evaluation system**, of which prose is one downstream surface:

```
immutable captures
  → typed temporal facts
  → state_at(season, cutoff)
  → ranking and forecast decisions
  → prose and publication
  → later outcome grading
```

The prior revision optimized the last three stages and left the first two implicit. That is the
architectural gap this revision closes.

### The two disconnected paths in the approved design

1. 2026 captures are preserved under `data/captures/` and `private_captures/`.
2. The edition compiler reads **finished-state legacy JSON** through source-specific adapters.

Nothing bridges them. There is no shared temporal-fact contract and no single historical-state
authority. Temporal meaning is currently divided among at least seven competing carriers:
`results_through_week`, edition kind, roster-anchor `known_at`, transaction `status_updated`,
message timestamps, chat outcome switches, and media timestamps.

Giving weekly packets a season-qualified location (plan Task A6) fixes an authority collision. It
does **not** make a finished packet a canonical temporal fact — the packet is still a snapshot of
an ending, sliced after the fact.

---

## Verified defects — preserved, and now correctly diagnosed

These findings stand exactly as measured. What changes is the diagnosis: each is a symptom of
having no temporal kernel, not an isolated field bug.

### Structural exposure: 98 of 98 H2H blocks

Every `matchups[].h2h` block is sourced from `league_history.json`'s season-end aggregate with no
cutoff slice. Blocks that read correctly today do so by accident of scheduling.

### Confirmed contamination: 46 entries

| Class                                      | Count  | Detail                                                   |
| ------------------------------------------ | ------ | -------------------------------------------------------- |
| H2H `last_meeting` postdating the packet   | 32     | Worst case: `week1_data.json` carries a week-17 score    |
| `historical_context.highest_combined`      | 13     | 2025 week 14 record, present in packets 1-13             |
| `historical_context.longest_losing_streak` | 1      | Undated aggregate; week 1 carries 10, correct value is 9 |
| **Total**                                  | **46** |                                                          |

Week-packet fields only. A separate **source-level** exposure — 239 of 1,205 media catalog items
postdating the week-1 cutoff — is counted apart from the 46.

The reproducing census (two passes: dated comparison, then recomputation of undated aggregates)
is retained verbatim from the approved revision and is unchanged by this document. Verified
streak values: 8 through 2024, 9 through 2025 wk1, 10 through 2025 wk2, against a committed 10.

**The sibling is accidentally safe, not structurally safe.** `longest_win_streak` leaks in 0
packets because its 11-game streak completed before 2025 week 1 — the same unsliced computation,
correct by coincidence. Under a temporal kernel this distinction disappears: both are aggregates
recomputed from admitted facts, and neither can be accidentally anything.

### Root cause, restated

`extract_week_data.py:559-567` takes `games[-1]` as `last_meeting` with no cutoff filter, while
`compute_as_of_history` sits in the same file. `verify_h2h_claims`
(`verify_week_content.py:892-949`) validates prose _against_ the contaminated field and only
warns.

The deeper root cause is that **every one of these paths invents its own notion of "as of."**
There is no shared answer to "what was true, and knowable, at this instant," so each call site
improvises one and the improvisations disagree.

### What is NOT broken

`standings` are genuinely cutoff-correct (0 of 12 blocks identical between weeks 1 and 10). The
chat layer's temporal admissibility and provenance were hardened and pushed 2026-07-20
(`c751b22`, CI green).

---

## 1. Canonical temporal facts

Every observation admitted to D1 is a typed fact carrying:

| Field                | Meaning                                                                                 |
| -------------------- | --------------------------------------------------------------------------------------- |
| `fact_id`            | Stable identity for this observation                                                    |
| `source_record_id`   | **Semantic identity of the underlying record** — the thing a repeat capture re-observes |
| `entity_ref`         | `{type, id}` — franchise, player, matchup, transaction, message, media, game            |
| `source_ref`         | Which capture or legacy artifact produced it                                            |
| `fact_type`          | Governs which reducer applies                                                           |
| `effective_at`       | When the thing was **true**                                                             |
| `known_at`           | When it became **defensibly available to `access_scope`**                               |
| `access_scope`       | `public` \| `league_private` — the epistemic scope `known_at` is asserted against       |
| `known_at_basis`     | How `known_at` was established, or the versioned inference policy id                    |
| `captured_at`        | When **this repository** first held it                                                  |
| `content_sha256`     | Hash of the fact payload                                                                |
| `privacy`            | `public` \| `private` — custody class, independent of `access_scope`                    |
| `normalizer_version` | Which normalizer produced this fact                                                     |
| `schema_version`     | Fact schema version                                                                     |
| `supersedes`         | `fact_id` this correction replaces, or null                                             |

**Never equate the three times.** A backfilled 2025 result has `effective_at` in September 2025,
`known_at` at that game's conclusion, and `captured_at` in 2026. Collapsing them is exactly how
`rosters.json` — a February 2026 final state — came to be treated as a September 2025 anchor.

### Idempotency and replay determinism

Daily captures are **complete snapshots**, so the same transaction, draft pick, or roster row
recurs in every capture. Without semantic identity the fact store grows a duplicate per day.

- **`source_record_id`** is the semantic identity of the underlying record (e.g. Sleeper
  `transaction_id`, `(draft_id, pick_no)`, `(roster_id, week)`).
- **Identical repeats coalesce.** A re-observation whose payload hash matches an existing fact
  for the same `source_record_id` updates nothing and creates no new fact. It may extend an
  observation log, which is not part of state.
- **Changed records supersede.** A re-observation with a different payload creates a new fact
  carrying `supersedes` and its own `known_at` — so a state built at an earlier cutoff still sees
  the original value.
- **`normalizer_version`** is bound into every fact, because a normalizer change is a change in
  meaning even when the capture bytes are identical.
- **Deterministic replay:** normalizing the same capture set twice must produce **byte-identical
  facts and byte-identical `state_at` output**. This is the fact-layer analogue of the bundle
  reproducibility already proven downstream.

### Knowledge scope

`known_at` cannot mean "publicly knowable" while chat and media are the richest evidence and are
private by construction. It means **defensibly available to a named epistemic scope**:

- `access_scope: public` — knowable to anyone (NFL results, published schedules).
- `access_scope: league_private` — knowable to the league (chat messages, shared media).

A league-private fact is legitimately admissible at a cutoff the public did not share. **Custody
and publication remain separate axes:** `privacy` governs where raw bytes may live and whether a
derived quotation may be published, and neither is decided by `access_scope`. A chat message can
be admissible evidence and unpublishable at the same time.

### Replay vantage

`state_at(season, cutoff)` as first drafted ignores `captured_at`, which silently conflates two
different questions:

- **Latest best-known reconstruction** — everything we now know was true and knowable by the
  cutoff, including facts captured afterward. Correct for a 2025 backtest.
- **As-recorded replay** — only facts this repository actually held at a stated vantage. Required
  for any prospective claim.

The interface therefore takes a vantage:

```
state_at(season, cutoff, access_scope, as_recorded_at=None) -> LeagueState
```

`as_recorded_at=None` yields the latest reconstruction. A prospective seal **must** pin
`as_recorded_at` (or an equivalent fact-set identity hash), so a 2026 decision can never
retroactively acquire a late-captured fact.

### Requested knowledge scope

`access_scope` is a **required parameter**, not an attribute the caller may ignore. "Admission is
evaluated against the fact's `access_scope`" does not say which facts _this caller_ may receive —
it leaves a later projection to improvise access control, which is the improvisation this kernel
exists to remove.

The lattice, in full:

| Requested `access_scope` | Receives                                |
| ------------------------ | --------------------------------------- |
| `public`                 | `public` facts only                     |
| `league_private`         | `public` **and** `league_private` facts |

**Fail closed:** an omitted or unrecognized scope is an error, never a default. A fact carrying no
`access_scope` is inadmissible at every scope. Publication eligibility stays a separate axis — a
`league_private` fact admitted to a league-scope state may still be unpublishable.

The K1 private-scope test calls this shipped signature. It does not assert the rule against a
downstream projection.

### Schedule provenance

Stripping outcomes from a completed weekly packet does not prove the pairing was knowable before
kickoff — it proves only that we can hide what we already have. A `schedule_pairing` fact requires
either an **independently qualified schedule source** with its own `known_at`, or an **explicit
versioned availability policy** recorded in `known_at_basis`. Absent both, the schedule fact is
**unavailable** and the edition proceeds without it.

**Corrections are supersessions, not mutations.** Unknown availability fails closed, or admits
under an approved versioned inference policy named in `known_at_basis`. There is no silent
default.

---

## 2. One temporal authority, and one decision-history boundary

Two authorities, deliberately separate. Conflating them is what lets an arm read another arm's
judgments.

### League-world truth

```
state_at(season, cutoff, access_scope, as_recorded_at=None) -> LeagueState
```

- **Admission is principally `known_at <= cutoff`**, evaluated against the fact's `access_scope`.
  One rule, one comparison, one place.
- **Fact-type reducers use `effective_at`** to fold admitted facts into current values.
- **Aggregates are recomputed from admitted facts** — never read from a stored season-end value.
  Records, streaks, H2H, standings, and Elo become derivations, so the dated/undated distinction
  that produced the 46 stops existing as a category.
- **Schedule and result are separate facts.** A week-1 pairing may be knowable in the preseason;
  its result is not.
- **Edition kind selects presentation components. It must not decide whether a fact existed.**
  The `allow_outcome_derivation` switch was a symptom: a projector reaching for outcomes and being
  told not to, rather than a state that does not contain them.
- **`results_through_week` is derived from — or mechanically checked against — the temporal
  state.** It stops being a competing clock.

`state_at` contains **no decisions**. It is the world, not our judgments about the world.

### Decision history

Sealed prior judgments are a separate, canonically time-qualified boundary:

```
decision_history_at(season, cutoff, arm_id, trial_id) -> [SealedDecision]
```

- Returns only decisions **sealed by that same `arm_id` and `trial_id`** at a cutoff strictly
  before the requested one.
- **No consumer improvises continuity.** The preview does not glob prior editions; it asks this
  interface. (The plan's `prior_editions` adapter globbed published editions, which let a rebuild
  admit its own future — the same class of defect one level up.)
- A `SealedDecision` is immutable once sealed, carries its own `decision_hash`, and records the
  `state_hash` it was made from.

**No arm may consume another arm's decision history.** A no-chat arm's preview must build on the
no-chat arm's preseason seal, not on the full-bundle arm's. Otherwise every arm inherits the best
arm's continuity and the comparison measures nothing.

**Storage is secondary.** Rebuildable SQLite, typed JSONL, or Parquet/Polars all work at this
scale. Explicitly excluded: Kafka, Feast, XTDB, OpenLineage, graph databases, any new service.

---

## 3. Minimum normalization bridge

Normalize **only** what the three D1 editions need, plus the corresponding prospective 2026
captures. Nothing speculative.

| Fact type            | 2025 source                                                                               | 2026 source   | Notes                                                                                                                  |
| -------------------- | ----------------------------------------------------------------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `franchise_identity` | `data/2025/users.json`                                                                    | capture       | durable `roster_id`/`owner_id`                                                                                         |
| `schedule_pairing`   | **qualified schedule source, or a versioned availability policy — otherwise unavailable** | capture       | a completed packet with outcomes stripped is not a source (§1)                                                         |
| `matchup_result`     | weekly packet                                                                             | capture       | `known_at` = game conclusion                                                                                           |
| `roster_membership`  | anchor + transactions                                                                     | capture       | forward from a qualified anchor                                                                                        |
| `transaction`        | `transactions.json`                                                                       | capture       | `known_at` = effective completion                                                                                      |
| `draft_pick`         | `draft_picks.json`                                                                        | capture       | pick order preserved                                                                                                   |
| `chat_message`       | parsed corpus                                                                             | manual export | private-class                                                                                                          |
| `media_item`         | rebound catalog                                                                           | manual export | private-class original                                                                                                 |
| `historical_matchup` | `data/{2022,2023,2024}/season_combined.json`, `known_at` = each game's conclusion         | n/a           | required by the no-history arm and by contrast integrity; absent this row the arm is **unavailable**, not merely empty |
| `nfl_game`           | `nfl_games/` + schedules                                                                  | capture       | kickoff needs venue timezone                                                                                           |

**The projector shapes bundles only from `state_at` output.** It stops being a collection of
source-specific adapters that each improvise a slice. Its remaining job is presentation selection
per edition kind.

**Reuse the existing hard-won tests through this path** — physical truncation, poisoned-root
season isolation, preview outcome-freedom, and the leaky-adapter comparator control all apply
unchanged to `state_at`, and are stronger there because a single admission rule is the only thing
they need to falsify.

**The source census and leaf registry become migration checks** rather than the primary
guarantee: they answer "did every legacy field find a fact type," not "is this field safe."

---

## 4. Measurable decisions

The ranking record grounds an ordering in evidence. It does not say **what the ordering
predicts**, so it cannot be scored — and an unscoreable judgment cannot demonstrate a model
becoming more informed.

Add a first-class **claims and forecast ledger**. Each claim carries:

| Field                                     | Meaning                                                        |
| ----------------------------------------- | -------------------------------------------------------------- |
| `claim_id`                                | Stable identity                                                |
| `target`                                  | Entity the claim is about                                      |
| `claim_type`                              | `ordinal_rank` \| `binary_probability` \| `bounded_quantity`   |
| `horizon`                                 | `next_week` \| `rest_of_season` \| `championship` \| `dynasty` |
| `assertion`                               | Rank, probability, or quantity                                 |
| `confidence`                              | Stated, not implied                                            |
| `decisive_evidence` / `contrary_evidence` | Bundle pointers                                                |
| `cutoff_utc`, `state_hash`                | The state it was made from                                     |
| `arm_id`, `trial_id`, `decision_run_id`   | Which run produced it                                          |
| `resolution_rule`                         | Fixed **before** the outcome — rule, source, and date          |
| `outcome`, `score`                        | Filled by the resolver, later                                  |

The published ranking may synthesize horizons — weekly strength, rest-of-season equity,
championship equity, dynasty value — but each stays explicit and separately scoreable.

### Precommitted scoring

Defined before any arm runs, so no metric is chosen after seeing results.

| `claim_type`         | Scoring rule                                            | Aggregation                    |
| -------------------- | ------------------------------------------------------- | ------------------------------ |
| `ordinal_rank`       | Spearman footrule against realized end-of-horizon order | Mean per edition, then per arm |
| `binary_probability` | Brier score                                             | Mean per edition, then per arm |
| `bounded_quantity`   | Absolute error normalized by the claim's stated bound   | Mean per edition, then per arm |

- **Unresolved claims** (horizon not yet reached) are excluded from scoring and **counted
  separately**; an arm producing fewer resolvable claims is not thereby better.
- **Missing outcomes** (resolution source unavailable) mark the claim `unresolvable` and are
  reported, never silently dropped.
- **Aggregation order is fixed:** claim → team → edition → trial → arm. Reporting a different
  order after the fact is a post-hoc metric choice.
- **Randomized blind review is a separate, non-substitutable signal.** Blake ranks unlabeled arm
  outputs on prose and judgment quality. It never overwrites the computed scores; where the two
  disagree, both are reported and the disagreement is the finding.
- **Repeated trials:** any arm whose runner is not deterministic requires **at least three
  trials**, and its reported score is the median with the range shown. A single sample from a
  stochastic runner is not a measurement.

---

## 5. Decision-run contract and evaluation arms

### Decision-run, not model-run

Two arms are deterministic baselines and cannot satisfy a receipt demanding a provider and model.
The contract generalizes:

```
runner_kind: deterministic | model
```

**Both kinds bind:** `decision_run_id`, `edition_id`, `arm_id`, `trial_id`, `state_hash`,
`bundle_hash`, `predecessor_decision_hash`, start and end timestamps, and `output_decision_hash`.

**Deterministic arms additionally bind:** code hash, configuration hash, and input hashes. Given
identical inputs they must reproduce an identical `output_decision_hash`.

**Model arms additionally bind:** provider, model, version, reasoning setting, prompt and rule
hashes, tools and browsing policy, budget, retries, and sampling policy.

`predecessor_decision_hash` is what makes cross-arm contamination detectable: it must resolve to
a seal from the **same** `arm_id` and `trial_id`.

### The five K3 data-layer arms

| Arm                    | Runner        | Tests                                    | Preseason meaning                                                                                 |
| ---------------------- | ------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Record/points baseline | deterministic | Does the model beat arithmetic?          | No 2025 results exist; ranks by **prior-season final standings**, stated as the preseason variant |
| Minimal legal bundle   | model         | What does the floor deliver?             | Franchise identity, draft, roster facts only                                                      |
| Full rich bundle       | model         | Marginal value of enrichment             | All available evidence families                                                                   |
| No-chat ablation       | model         | Does culture evidence change decisions?  | Full minus `chat_message` facts                                                                   |
| No-history ablation    | model         | Does the dynasty layer change decisions? | Full minus pre-2025 facts                                                                         |

### Inertia is a comparator, not an arm

The previous revision made "prior unchanged" an arm that was N/A at preseason yet entered at
preview "carrying the preseason seal of its own arm" — a seal an arm that never ran preseason
cannot have. Inertia has no independent lineage to carry.

It is therefore a **deterministic transition comparator** evaluated inside each eligible arm:

- an arm's **preview** decision is scored against an unchanged copy of **that same arm's**
  preseason seal;
- its **recap** decision is scored against an unchanged copy of **that same arm's** preview seal;
- **no comparator exists where no qualified predecessor exists** — so there is nothing to compute
  at preseason, and nothing is invented to fill the gap.

The comparator carries the arm's own `arm_id` and `trial_id`, so it cannot borrow another arm's
continuity. "Does anything beat inertia?" is answered five times, once per arm, rather than by a
sixth arm with no origin.

**"Full bundle + desks" is not a K3 arm.** It compares two prose pipelines over identical
evidence and cannot isolate data-layer lift. It moves to S1a, after the desks exist — correcting
a sequencing contradiction where §5 required desks that §7 did not build until after the STOP.

### Longitudinal execution

K2 may compile the immutable league states in advance. **K3 must execute each arm's chain
chronologically**, and each arm's chain is closed:

```
preseason state → seal THIS arm's decision + claims
  → preview consumes THIS arm's preseason seal → seal preview
  → recap resolves and grades THIS arm's prior claims
```

An arm never sees another arm's judgments. A **cross-arm predecessor poison test** deliberately
feeds arm B's seal into arm A's preview and requires the run to fail on the
`predecessor_decision_hash` check.

### Contrast integrity

A null result is only interpretable if the arms genuinely differed.

**The evidence-family manifest is frozen before any arm runs.** No source may be added after
seeing output; changing the manifest invalidates every completed arm and restarts the comparison.
Otherwise a disappointing result invites one more source, and the experiment becomes a search for
a configuration that produces the desired answer.

**Required families for the K1/K3 data-layer contrast:**

| Family               | Required          | Rationale                                                                                                                                                                                                                                                                                                                      |
| -------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `roster_membership`  | yes               | Directly informs strength judgments                                                                                                                                                                                                                                                                                            |
| `historical_matchup` | yes               | The no-history arm ablates exactly this                                                                                                                                                                                                                                                                                        |
| `chat_message`       | yes               | The no-chat arm ablates exactly this                                                                                                                                                                                                                                                                                           |
| `nfl_game` context   | yes               | Distinguishes rich from minimal                                                                                                                                                                                                                                                                                                |
| `media_item`         | **no — excluded** | Media is deferred to S1b and classified non-evidentiary decoration. It cannot be decoration and also load-bearing for a ranking decision. Its absence must not degrade the data-layer experiment. If league media is ever argued to change a ranking decision, that exact decision path must be shown before it moves earlier. |

- The full rich bundle must meet the coverage above, all present and non-empty.
- It must **demonstrably differ** from the minimal bundle: a computed diff over admitted fact
  types, recorded per edition.
- If a required family is unavailable — no qualified roster anchor, no qualified historical
  source, no admissible schedule source — the comparison is **degraded**.

**Degraded contrast is bounded, not open-ended.** A degraded result permits **one** explicitly
approved remediation cycle to qualify the missing family. If it remains degraded after that
cycle, the outcome is **STOP — NO DECISION, NO EXPANSION**: no data-layer verdict is recorded,
S1a does not begin, and prospective 2026 capture and sealing continue regardless.

"Inconclusive" is not an unlimited infrastructure license. A degraded contrast is never evidence
that richer data failed to add value — and equally, it is never a reason to keep building until
the contrast becomes measurable.

---

## 6. The 2025 / 2026 claim boundary, and prospective sealing

### 2025 is a backtest

**A cutoff-clean bundle does not stop a model running in 2026 from already knowing public 2025
NFL outcomes.** This is a limit of retrospective evaluation, not a bug to engineer away.

For the 2025 evaluation arms: browsing and non-bundle tools disabled; opaque league and player
identities where practical; **the decision locked before names return** for prose; outcomes
exposed only to the resolver; and every artifact labeled **retrospective replay / backtest**.

### 2026 prospective sealing is in scope — capture alone is not the experiment

Verified 2026-08-02: there is **no capture script, no capture table, no capture directory, and no
capture workflow**. `data/2026` is the 2026-04-04 snapshot, four months stale. The only scheduled
job is `fetch-sleeper-data.yml` (`cron: '0 6 * 9-12 0'`) — September onward, weekly, overwriting.
**Phase P is not running.** Everything describing it lives in the frozen implementation plan.

And capture alone would not be enough. If a decision is generated after the outcome exists, the
model may already know 2026 exactly as it may know 2025. **The seal, not the capture, is what
makes the experiment prospective.** A minimum sealing lane is therefore in scope:

1. **Start the capture and accounting lane** — eight-row receipt, append-only, public/private
   root split.
2. **Before the applicable real-world cutoff, seal the 2026 preseason and week-1 preview ranking
   and claims.** Prose is out of scope; the sealed decision is not.
3. **Each seal binds:** its contemporaneous fact set (`as_recorded_at` or fact-set identity
   hash), the bundle hash, the decision-run receipt, and the cutoff.
4. **Late writes are rejected**, or admitted and **labeled retrospective** — never silently
   accepted as prospective.

### Deadline mechanism and fallback

| Deadline              | Governs        | Mechanism                                                                                                                |
| --------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 2026 preseason cutoff | preseason seal | `qualify_cutoff` derives it from the qualified first-kickoff instant; a seal attempted after it is rejected or relabeled |
| 2026 week-1 kickoff   | preview seal   | Strictly-before the qualified kickoff, same derivation                                                                   |

**Fallback if the kernel is not ready in time — a required design option, not an authorization.**
The definitive test must not expire while the backtest is perfected. If K1-K2 will not complete
before a cutoff, this design **requires** a minimal preservation-and-sealing path to exist as an
option. It **may run only through a separately approved P-only implementation plan.**

That plan must bind:

- the eight capture rows with full receipts;
- **the exact frozen decision-input bundle** the seal was made from, and the permitted
  transformations from captures to that bundle — not merely the hashes of raw captures. A hash of
  inputs does not pin what the decider actually saw;
- a decision-run receipt of the correct `runner_kind`;
- deferred normalization: when the kernel exists, **re-derive** the state from the same frozen
  captures and verify the seal still resolves.

**A missed deadline is never backdated.** A seal attempted after its cutoff is labeled
**retrospective**, and prospective work moves to the next uncontaminated cutoff. There is no
mechanism to reclassify a late seal as prospective, and none may be added.

---

## 7. Sequencing

**Prove the kernel before investing in surfaces.**

| Phase    | Content                                                                                                                              | Gate                                                                                                                      |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| **P**    | 2026 capture + prospective sealing lane. **Starts first; runs throughout.**                                                          | Eight-row accounting receipt; preseason and week-1 seals bound to fact-set identity before their cutoffs                  |
| **K1**   | Temporal fact schema + `state_at` + `decision_history_at` + minimum normalization for the three D1 states                            | The seven discriminating tests below all pass                                                                             |
| **K2**   | Three D1 states compiled: preseason, week-1 pre-kickoff, week-1 recap                                                                | Each state reproducible; no future fact admitted; deterministic replay byte-identical                                     |
| **K3**   | Claims ledger + decision-run contract + **five data-layer arms**, executed chronologically per arm, each with its inertia comparator | All five arms complete with their inertia comparators; contrast integrity satisfied; blind review recorded; lift measured |
| **STOP** | **Judge data-layer lift**                                                                                                            | Blake's call                                                                                                              |
| **S1a**  | Build the six desks; run **full bundle + one writer vs. full bundle + desks**                                                        | Newsroom lift measured on identical evidence                                                                              |
| **S1b**  | Media rebind, render, publication lifecycle                                                                                          | Only if S1a justified it                                                                                                  |

### K1's discriminating tests — exercised, not asserted

Acceptance prose is not a gate. K1 ships with tests that **fail when the rule is absent**:

1. **Duplicate capture** — the same record captured twice produces one fact, not two.
2. **Revised duplicate** — a changed record supersedes rather than mutating; the earlier state is
   unchanged.
3. **Late capture** — a fact captured after a stated `as_recorded_at` is excluded from the
   as-recorded replay and included in the latest reconstruction.
4. **Private-scope exclusion** — a `league_private` fact is admissible to a league-scope state and
   excluded from a public-scope projection; custody and publication remain separately governed.
5. **Schedule-provenance failure** — a pairing derived only from a completed packet, with no
   independent source and no versioned policy, is **unavailable**.
6. **Correction chains** — a three-step supersession resolves to the correct value at each of the
   three cutoffs.
7. **Cross-arm predecessor poisoning** — feeding arm B's seal into arm A's preview fails the
   `predecessor_decision_hash` check.

Plus **deterministic replay:** normalizing the same captures twice yields byte-identical facts
and byte-identical `state_at` output.

### Preserved without change

Exact-instant cutoffs, bundle and manifest identity, provenance and staleness binding,
ranking-before-prose ordering, noninterference proof, approval lifecycle, media admission and
byte-level render verification, and publication records all carry forward. They move from being
the whole architecture to being the publication half of it. The source census and leaf registry
become **migration checks** — "did every legacy field find a fact type" — rather than the primary
temporal guarantee.

---

## What approving this design does NOT do

Stated plainly so approval cannot be read as a start signal:

- It **does not start Phase P.** Capture and sealing begin only under an approved P-only
  implementation plan.
- It **does not approve the frozen `df7c1ea` implementation plan**, which remains a requirements
  inventory pending its own revision and review.
- It **does not authorize any repository change** — no implementation, no push, no deletion.

Approval of this document authorizes exactly one thing: writing implementation plans against it.

---

## Out of scope

- Kafka, Feast, XTDB, OpenLineage, graph databases, any new service.
- D2 — the remaining archive beyond the three D1 editions.
- v2 redesign.
- 2026 authoring. Phase 0 preserves 2026 evidence and writes no 2026 prose.
- `feat/analytics-owner-edge` — parked, shadow-only.

---

## Acceptance

- **Facts:** every D1 observation carries the full field set including `source_record_id`,
  `access_scope`, `normalizer_version`, and `captured_at`; no fact conflates `effective_at`,
  `known_at`, and `captured_at`; corrections supersede rather than mutate; unknown availability
  fails closed or cites a versioned inference policy.
- **Idempotency:** normalizing the same capture set twice produces byte-identical facts and
  byte-identical `state_at` output; identical repeats coalesce; changed records supersede.
- **Authority:** exactly one `state_at`; exactly one `decision_history_at`; `state_at` contains no
  decisions; no consumer slices its own history or globs prior editions; schedule and result are
  separate fact types; `results_through_week` is derived or mechanically checked; every aggregate
  is recomputed from admitted facts.
- **Vantage:** a prospective seal pins `as_recorded_at` (or a fact-set identity hash) and cannot
  retroactively acquire a late-captured fact.
- **Schedule provenance:** every admitted `schedule_pairing` cites an independent qualified source
  or a versioned availability policy; otherwise it is unavailable.
- **K1 tests:** all seven discriminating tests pass, each demonstrated to fail when its rule is
  removed.
- **Decisions:** every published ranking position carries at least one scoreable claim with a
  resolution rule fixed before the outcome; horizons are explicit; scoring rules, aggregation
  order, and trial counts are precommitted.
- **Evaluation:** all **five** K3 data-layer arms run under decision-run receipts, each with its inertia comparator where a qualified predecessor exists of the correct
  `runner_kind`; every arm's chain is chronological and closed; the cross-arm poison test fails as
  designed; contrast integrity is satisfied or the result is reported degraded/inconclusive; blind
  review recorded separately from computed scores.
- **Boundary:** the 2025 arms ran with browsing disabled and decisions locked before names
  returned; every 2025 artifact is labeled retrospective replay; the 2026 preseason and week-1
  seals exist, bound to their fact sets, before their cutoffs.
- **Newsroom (S1a, after the STOP):** full-bundle-one-writer versus full-bundle-desks measured on
  identical evidence.
- **Census carried:** 46 confirmed future entries → 0; 98 structurally unsliced H2H blocks → 0,
  by construction rather than by patch.

---

## Corrections the implementation plan must absorb

Recorded here so the plan's future revision has a source. **The plan at `df7c1ea` is unmodified.**

1. **`bundle["source_identities"]` KeyError.** Plan `:2671` reads `bundle["source_identities"]`,
   but `project()` returns identities _alongside_ the payload (`:2500`) and `compile_edition()`
   writes only the payload to `bundle.json` (`:2755`). Identities stay outside the semantic
   bundle — that separation is what makes the noninterference comparison valid — so the test must
   read `source_hashes.json` or the manifest.
2. Task A6's season-qualified authority becomes a **migration step** toward fact normalization,
   not the temporal fix itself.
3. Task A7's `allow_outcome_derivation` switch is **replaced** by state composition: a preview
   state contains no result facts, so there is nothing to switch off.
4. The plan's `prior_editions` adapter is replaced by `decision_history_at`, scoped to
   `arm_id`/`trial_id`.

---

## Open items

- **`data/roster_anchors.json` has no producer.** Without a qualified pre-kickoff roster snapshot,
  roster facts are unavailable for preview and preseason states. Fail-closed and correct — but it
  removes an evidence family, so the **contrast-integrity gate applies** and a full-bundle arm
  missing rosters yields a degraded comparison, not a finding.
- **`protected_source_root` is null.** League media unavailable. This **does not** degrade the
  K1/K3 contrast — `media_item` is excluded from the required evidence families, because media is
  deferred to S1b and classified non-evidentiary decoration.
- **Storage substrate** — SQLite, JSONL, or Parquet. Deferred; all three satisfy the contract and
  the choice does not gate approval.
- **`known_at` inference policies** for legacy 2025 sources carrying no publication instant. Each
  needs an explicit versioned policy or a fail-closed decision, per fact type.
- **2026 league id and cutoff dates** are needed before the prospective sealing lane can run.

---

## Self-review — fact → state → decision-history → evaluation → prospective seal

**Fact.** The contract now carries semantic identity (`source_record_id`) alongside observation
identity (`fact_id`), which is what makes complete daily snapshots idempotent instead of
duplicative. `access_scope` resolves the contradiction between "publicly knowable" and private
chat being the richest evidence, and it is deliberately orthogonal to `privacy`: a message can be
admissible at a league-scope cutoff and still unpublishable. `normalizer_version` is bound because
a normalizer change alters meaning even when capture bytes do not.

**State.** `state_at` gained a vantage parameter, closing a gap I had not seen: without
`as_recorded_at` the interface cannot express "what we actually held then," which is the only
form a prospective claim can be made from. Schedule provenance is now a precondition rather than
an assumption — stripping outcomes from a finished packet proves concealment, not availability.

**Decision history.** Split from `state_at` entirely. `state_at` is the world; `decision_history_at`
is our judgments about it, scoped to `arm_id` and `trial_id`. This is what makes the five arms
independent: without it, every arm's preview would inherit whichever preseason seal happened to be
on disk, and the comparison would measure nothing. The plan's globbing `prior_editions` adapter is
the same defect one level up and is superseded.

**Evaluation.** `runner_kind` resolves a real contradiction — two arms are deterministic and
cannot bind a provider. Arm applicability is now stated per edition, including the two genuinely
awkward cases: "prior unchanged" has no preseason meaning and enters at preview, and
"record/points" uses prior-season standings at preseason because no 2025 results exist. Scoring
rules, aggregation order, unresolved handling, and trial counts are precommitted so no metric can
be selected after seeing results. The desks arm moved to S1a, resolving the contradiction where
§5 required desks that §7 built only after the STOP.

**Prospective seal.** The correction I would have missed: capture is necessary and not sufficient.
A decision generated after the outcome exists is retrospective regardless of how clean the bundle
is, so the _seal_ is the experiment. Deadlines derive from the same qualified-kickoff machinery as
the 2025 preview cutoff, and the fallback path exists because the definitive test can expire while
the backtest is perfected.

**Gap I could not close.** The 2025 contamination boundary remains mitigated, not eliminated —
disabled browsing, opaque identities, and locked-before-names decisions reduce leakage through
pretrained knowledge of public 2025 outcomes; they cannot prove it absent. That asymmetry is why
2025 is labeled replay, why 2026 is the definitive test, and why Phase P now starts first rather
than running "throughout" — verification showed nothing was running at all.
