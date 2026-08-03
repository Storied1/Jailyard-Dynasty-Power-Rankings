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

| Field            | Meaning                                                                      |
| ---------------- | ---------------------------------------------------------------------------- |
| `fact_id`        | Stable identity for this observation                                         |
| `entity_ref`     | `{type, id}` — franchise, player, matchup, transaction, message, media, game |
| `source_ref`     | Which capture or legacy artifact produced it                                 |
| `fact_type`      | Governs which reducer applies                                                |
| `effective_at`   | When the thing was **true**                                                  |
| `known_at`       | When it was **publicly knowable**                                            |
| `known_at_basis` | How `known_at` was established, or the versioned inference policy id         |
| `captured_at`    | When **this repository** first held it                                       |
| `content_sha256` | Hash of the fact payload                                                     |
| `privacy`        | `public` \| `private`                                                        |
| `schema_version` | Fact schema version                                                          |
| `supersedes`     | `fact_id` this correction replaces, or null                                  |

**Never equate the three times.** A backfilled 2025 result has `effective_at` in September 2025,
`known_at` at the conclusion of that game, and `captured_at` in 2026. Collapsing them is precisely
how `rosters.json` — a February 2026 final state — came to be treated as a September 2025 anchor.

**Corrections are supersessions, not mutations.** A fact is never edited in place; a superseding
fact carries its own `known_at`, so a state built at an earlier cutoff still sees the original.

**Unknown historical availability fails closed**, or admits under an explicit, approved, versioned
inference policy recorded in `known_at_basis`. There is no silent default.

---

## 2. One temporal authority

A single interface replaces every ad-hoc slice:

```
state_at(season: int, cutoff: str) -> LeagueState
```

- **Admission is principally `known_at <= cutoff`.** One rule, one comparison, one place.
- **Fact-type reducers use `effective_at`** to fold admitted facts into current values.
- **Aggregates are recomputed from admitted facts** — never read from a stored season-end value.
  Records, streaks, H2H, standings, and Elo all become derivations, so the
  dated/undated distinction that produced the 46 stops existing as a category.
- **Schedule and result are separate facts.** A week-1 pairing is knowable in the preseason; its
  result is not. The approved design entangled them in one weekly packet, which is why the
  preview needed an "outcome-free" variant of a completed artifact.
- **Edition kind selects presentation components. It must not decide whether a fact existed.**
  The prior `allow_outcome_derivation` switch is a symptom: a projector reaching for outcomes and
  being told not to, rather than a state that does not contain them.
- **`results_through_week` is derived from — or mechanically checked against — the temporal
  state.** It stops being a competing clock.

**Storage is secondary.** Rebuildable SQLite, typed JSONL, or Parquet/Polars all work at this
scale. Explicitly excluded: Kafka, Feast, XTDB, OpenLineage, graph databases, or any new service.

---

## 3. Minimum normalization bridge

Normalize **only** what the three D1 editions need, plus the corresponding prospective 2026
captures. Nothing speculative.

| Fact type            | 2025 source                      | 2026 source   | Notes                             |
| -------------------- | -------------------------------- | ------------- | --------------------------------- |
| `franchise_identity` | `data/2025/users.json`           | capture       | durable `roster_id`/`owner_id`    |
| `schedule_pairing`   | weekly packet, outcomes stripped | capture       | separate from result              |
| `matchup_result`     | weekly packet                    | capture       | `known_at` = game conclusion      |
| `roster_membership`  | anchor + transactions            | capture       | forward from a qualified anchor   |
| `transaction`        | `transactions.json`              | capture       | `known_at` = effective completion |
| `draft_pick`         | `draft_picks.json`               | capture       | pick order preserved              |
| `chat_message`       | parsed corpus                    | manual export | private-class                     |
| `media_item`         | rebound catalog                  | manual export | private-class original            |
| `nfl_game`           | `nfl_games/` + schedules         | capture       | kickoff needs venue timezone      |

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

The ranking record from the approved revision grounds an ordering in evidence. It does not say
**what the ordering predicts**, so it cannot be scored — and an unscoreable judgment cannot
demonstrate a model becoming more informed.

Add a first-class **claims and forecast ledger**. Each claim carries:

| Field               | Meaning                                                        |
| ------------------- | -------------------------------------------------------------- |
| `claim_id`          | Stable identity                                                |
| `target`            | Entity the claim is about                                      |
| `horizon`           | `next_week` \| `rest_of_season` \| `championship` \| `dynasty` |
| `assertion`         | Rank, probability, or bounded quantity                         |
| `confidence`        | Stated, not implied                                            |
| `decisive_evidence` | Bundle pointers that drove it                                  |
| `contrary_evidence` | What argues against it                                         |
| `cutoff_utc`        | The state it was made from                                     |
| `resolution_rule`   | Fixed **before** the outcome — rule, source, and date          |
| `outcome`           | Filled by the resolver, later                                  |
| `score`             | Computed from the fixed rule                                   |

**The published ranking may synthesize horizons** — weekly strength, rest-of-season equity,
championship equity, dynasty value — but each underlying horizon stays explicit and separately
scoreable. A single blended number that cannot be graded is the thing this replaces.

The `resolution_rule` is fixed at claim time. A rule written after the outcome is known is not a
forecast.

---

## 5. Model-run and evaluation contract

Every intelligence run binds:

model and provider, version, reasoning setting, prompt and rule hashes, tools and browsing
policy, bundle and predecessor hashes, budget, retries or a recorded deterministic policy, start
and end timestamps, and the output decision hash.

Without this, two runs that differ are uninterpretable — you cannot tell whether the evidence, the
model, or the sampling changed.

### Matched arms

The approved single bake-off — desks versus one writer, both on the same rich bundle — cannot
isolate data-layer lift. It compares two prose pipelines over identical evidence. Replace with:

| Arm                           | Tests                                    |
| ----------------------------- | ---------------------------------------- |
| Prior ranking unchanged       | Does anything beat inertia?              |
| Simple record/points baseline | Does the model beat arithmetic?          |
| Minimal legal bundle          | How much does the floor deliver?         |
| Full rich bundle              | Marginal value of the enriched layer     |
| No-chat ablation              | Does culture evidence change decisions?  |
| No-history ablation           | Does the dynasty layer change decisions? |
| Full bundle + desks           | Marginal value of the newsroom           |

Use repeated trials or a recorded deterministic policy, and **randomized blind Blake review** —
arms unlabeled at review time.

This is the mechanism that answers the D1 product question with evidence instead of impression.

---

## 6. The 2025 versus 2026 claim boundary

**A cutoff-clean bundle does not stop a model running in 2026 from already knowing public 2025
NFL outcomes.** This is a limit of retrospective evaluation, not a bug to be engineered away, and
the approved design did not acknowledge it at all.

For the 2025 ranking-evaluation arm:

- Disable browsing and all non-bundle tools.
- Use opaque league and player identities where practical.
- **Lock the decision before names return** for prose generation.
- Expose outcomes only to the resolver, never to the decider.
- **Label 2025 as retrospective replay / backtest** in every artifact and every report.

The **prospective 2026 ledger** — decisions sealed before outcomes exist — is the first
definitive forecasting test. This is the strongest argument for Phase 0 capture continuing at
full priority: it is not archival housekeeping, it is the only clean experiment available.

---

## 7. Sequencing

**Prove the kernel before investing in surfaces.**

| Phase    | Content                                                                           | Gate                                                                                             |
| -------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **P**    | 2026 capture lane (unchanged, continues throughout)                               | Eight-row accounting receipt                                                                     |
| **K1**   | Temporal fact schema + `state_at` + minimum normalization for the three D1 states | Truncation, poison, season-isolation, preview-outcome, leaky-control all pass through `state_at` |
| **K2**   | Three D1 states compiled: preseason, week-1 pre-kickoff, week-1 recap             | Each state reproducible; no future fact admitted                                                 |
| **K3**   | Claims ledger + model-run contract + matched-arm evaluation                       | Arms run, blind review recorded, lift measured                                                   |
| **STOP** | **Judge whether richer evidence actually changed decisions**                      | Blake's call                                                                                     |
| **S1**   | Six desks, media rebind, full render and publication lifecycle                    | Only if K3 justified it                                                                          |

Everything after the STOP is contingent. If the rich bundle does not change decisions relative to
the minimal legal bundle, building six desks to enrich it further is investment against a
disproven hypothesis.

### Preserved without change

The capture lane, exact-instant cutoffs, bundle and manifest identity, provenance and staleness
binding, ranking-before-prose ordering, noninterference proof, approval lifecycle, media
admission and byte-level render verification, and publication records all carry forward. They
were hard-won and none of them is displaced by this revision — they move from being the whole
architecture to being the publication half of it.

---

## Out of scope

- Kafka, Feast, XTDB, OpenLineage, graph databases, any new service.
- D2 — the remaining archive beyond the three D1 editions.
- v2 redesign.
- 2026 authoring. Phase 0 preserves 2026 evidence and writes no 2026 prose.
- `feat/analytics-owner-edge` — parked, shadow-only.

---

## Acceptance

- **Facts:** every D1 observation carries the full temporal-fact field set; no fact conflates
  `effective_at`, `known_at`, and `captured_at`; corrections supersede rather than mutate;
  unknown availability fails closed or cites a versioned inference policy.
- **Authority:** exactly one `state_at` implementation; no consumer slices its own history;
  schedule and result are separate fact types; `results_through_week` is derived or mechanically
  checked, never an independent clock; every aggregate is recomputed from admitted facts.
- **Bridge:** only the D1-required fact types are normalized; the projector reads solely from
  `state_at`; the existing truncation, poison, season-isolation, preview-outcome, and
  leaky-control tests pass through that path.
- **Decisions:** every published ranking position has at least one scoreable claim with a
  resolution rule fixed before the outcome; horizons are explicit.
- **Evaluation:** all seven arms run under a recorded model-run contract; blind review completed;
  measured lift reported per arm.
- **Boundary:** the 2025 arm ran with browsing disabled and decisions locked before names
  returned; every 2025 artifact is labeled retrospective replay.
- **Census carried:** 46 confirmed future entries → 0; 98 structurally unsliced H2H blocks → 0,
  by construction rather than by patch.

---

## Corrections the implementation plan must absorb

Recorded here so the plan's revision has a source. **The plan itself is unmodified** pending
approval of this design.

1. **`bundle["source_identities"]` KeyError.** Plan `:2671` (Task B11 test) reads
   `bundle["source_identities"]`, but `project()` returns identities _alongside_ the semantic
   payload (`:2500`) and `compile_edition()` writes only the payload to `bundle.json` (`:2755`).
   Identities must stay outside the semantic bundle — that separation is what makes the
   noninterference comparison valid — so the test inspects `source_hashes.json` or the manifest.
2. Task A6's season-qualified authority becomes a **migration step** toward fact normalization
   rather than the temporal fix itself.
3. Task A7's `allow_outcome_derivation` switch is **replaced** by state composition: a preview
   state contains no result facts, so there is nothing to switch off.

---

## Open items

- **`data/roster_anchors.json` has no producer.** Without a qualified pre-kickoff roster
  snapshot, preview and preseason roster facts are unavailable and those states carry no roster
  component. Fail-closed and correct, but a real reduction in preview evidence.
- **`protected_source_root` is null.** League media stays unavailable; D1 runs the degraded route
  (GIPHY and custom only, approved as non-evidentiary decoration) and the league-media rebind
  branch is recorded NOT VALIDATED.
- **Storage substrate for facts** — SQLite, JSONL, or Parquet. Deliberately deferred; all three
  satisfy the contract at this scale and the choice does not gate design approval.
- **`known_at` inference policies** for legacy 2025 sources that carry no publication instant.
  Each needs an explicit versioned policy or a fail-closed decision, per fact type.

---

## Self-review — the capture → fact → state → decision → publication path

**Capture → fact.** Every fact type in §3 names both a 2025 legacy source and a 2026 capture
source, so the bridge is defined in both directions and the 2026 lane is not orphaned. Private
classes (`chat_message`, `media_item`) carry the privacy flag from §1 through to publication
eligibility, which remains independent of temporal admissibility.

**Fact → state.** Admission is one rule (`known_at <= cutoff`), applied in one place. Reducers
key on `effective_at`. Aggregates are recomputed, which is what dissolves the dated/undated
distinction that produced the 46 rather than patching each field.

**State → decision.** The ranking record binds to a state hash; each position yields at least one
claim with a pre-fixed resolution rule. The ranking-before-prose ordering is preserved, and it
now has a stronger justification: a claim made after prose is written is a description, not a
forecast.

**Decision → publication.** Unchanged from the approved revision — authoring manifest binds
content and ranking, publication record binds authoring manifest plus media manifest plus
rendered HTML, and the render verifier compares multiplicity, location, and bytes.

**Publication → grading.** New, and the reason the ledger exists. The resolver reads outcomes the
decider never saw and scores each claim against its fixed rule. For 2025 this is a backtest; for
2026 it is a genuine prospective test.

**Gap I could not close in this revision:** the 2025 arm's contamination boundary is mitigated,
not eliminated. Browsing disabled, opaque identities, and locked decisions reduce leakage through
the model's pretrained knowledge of public 2025 NFL outcomes — they cannot prove it absent. That
is why 2025 is labeled replay and 2026 is labeled the definitive test, and why nothing in the
acceptance criteria claims otherwise.
