# Jailyard — Writer Foundation + Newsroom Design

**Date:** 2026-08-01
**Status:** DRAFT — awaiting Blake review. Not approved. Nothing here is authorized for
implementation.
**Relationship to prior work:** replaces the "weeks 1-6 next" sequencing in
`2026-06-04-jailyard-2025-catchup-design.md`. That document's data → content → design ordering
still holds; its claim that the data layer is complete does not.

## Context

The 2026-06-04 program said the next step was rewriting weeks 1-6. That is wrong, and this
session proved it against disk.

### The defect, stated at two levels

These are different claims and both matter.

**Structural exposure: 98 of 98 H2H blocks are unsafe.** Every `matchups[].h2h` block in every
week packet is sourced from `league_history.json`'s season-end aggregate with no cutoff slice
applied — `wins`, `losses`, and `last_meeting` are all-time values. The blocks that happen to
read correctly today do so by accident of scheduling, not by construction. Any re-extraction,
any schedule difference, any new season turns an accidentally-safe block into a leaking one.

**Confirmed contamination: 45 entries currently carry future values** — 32 H2H blocks whose
`last_meeting` postdates their packet's week, plus 13 `historical_context` entries. Only one
`historical_context` record leaks (`highest_combined`, 2025 week 14), appearing in packets 1
through 13.

The worst single case: `week1_data.json` tells a week-1 columnist the score of a game played in
week 17.

### Reproducing census

```python
import json, glob, re
def wkof(p): return int(re.search(r'week(\d+)_', p).group(1))
files = sorted(glob.glob('content/weeks/week*_data.json'), key=wkof)

h2h_struct = 0; h2h_future = []; hc_future = []
for fp in files:
    wk = wkof(fp); d = json.load(open(fp, encoding='utf-8'))
    for m in d.get('matchups', []):
        h = m.get('h2h') or {}
        if not h: continue
        h2h_struct += 1                      # sourced from the unsliced aggregate
        lm = h.get('last_meeting') or {}
        s, w = lm.get('season'), lm.get('week')
        if s is None: continue
        if s > 2025 or (s == 2025 and w is not None and w > wk):   # recap semantics
            h2h_future.append((wk, s, w))
    for key, rec in (d.get('historical_context') or {}).items():
        if not isinstance(rec, dict): continue
        s, w = rec.get('season'), rec.get('week')
        if s is None: continue
        if s > 2025 or (s == 2025 and w is not None and w > wk):
            hc_future.append((wk, key, s, w))
```

Expected: `h2h_struct == 98`, `len(h2h_future) == 32`, `len(hc_future) == 13`, total confirmed
`45`. Note the comparison is `w > wk`, not `w >= wk` — see temporal semantics below. Using `>=`
reports 98 confirmed leaks, which conflates structural exposure with actual contamination.

### Root cause

`extract_week_data.py:559-567` reads `history_data["h2h"]` and takes `games[-1]` as
`last_meeting`. No cutoff filter. The correct helper, `compute_as_of_history`, already exists in
the same file and is already used by the standings path.

`verify_h2h_claims` (`verify_week_content.py:892-949`) validates writer prose _against_ the
contaminated field, and only warns. A column faithfully reporting the leaked number is certified
correct.

### What is NOT broken

This bounds the work. `standings` are genuinely as-of-week: between weeks 1 and 10, zero of
twelve standings blocks are identical (`record` 0-1 → 2-8, `current_elo` 1429.4 → 1351.7,
`all_time_record` 19-24 → 21-31). The M1 `compute_as_of_history` fix works as claimed. The chat
layer's temporal admissibility and provenance were hardened and pushed 2026-07-20 (`c751b22`,
CI green).

The defect is not "the foundation is incomplete." One fix landed on one field family and
silently missed its siblings — the fourth documented instance of that pathology here, the first
three unnoticed for weeks or months each. **Nothing walks the writer-facing surface and asks
every field whether it is cutoff-legal.** That missing instrument, not the two leaking blocks,
is the finding.

## Temporal semantics by edition type

"Strictly before week N" cannot govern every edition. The cutoff is a property of the edition,
not of the field.

| Edition                    | Cutoff                      | Week N's own results | Week N's own H2H meeting |
| -------------------------- | --------------------------- | -------------------- | ------------------------ |
| Preseason                  | before any 2025 game        | excluded             | excluded                 |
| Week 1 pre-kickoff preview | before week 1 kickoff       | excluded             | excluded                 |
| Week N recap               | after week N games conclude | included             | included                 |
| Finale (week 18)           | after week 17 championship  | n/a (no games)       | included through 17      |

Every temporal check takes its boundary from the edition's declared cutoff. A preview and a
recap for the same week are different editions with different legal evidence, and the audit must
evaluate each against its own cutoff rather than a global rule.

## Phase A — Instruction census: keep / replace / delete

Not blanket deletion. The goal is removing stale material without destroying the operative
instruction system. **No authoritative surface is deleted until its replacement is identified
and exists.** History needs no tombstones: git covers repo files, and the daily
ClaudeMemorySnapshot covers the memory tree.

| Surface                                            | Verdict        | Replacement / rationale                                                                                                                                                        |
| -------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `voice-bible.md` §1 patterns, §4 anti-patterns     | **KEEP**       | Abstract voice rules; the operative charter. Review, don't discard.                                                                                                            |
| `voice-bible.md` §2 handle table                   | **REPLACE**    | Superseded by the chat-mined name repertoire (Phase C). `@kharlo_w` is wrong — `data/2025/users.json` says `kharlow`.                                                          |
| `voice-bible.md` §5 exemplars                      | **DELETE**     | Filler excerpts from prose now classified as non-authoritative. Repopulated from the first edition that passes the final system — the charter carries no exemplars until then. |
| `voice-bible.md` §3 templates                      | **KEEP**       | Section contracts still describe the stable sections.                                                                                                                          |
| `project_jailyard_roadmap.md` SUPERSEDED blocks    | **DELETE**     | Git + memory backup hold the history.                                                                                                                                          |
| `project_jailyard_roadmap.md` current-state claims | **REPLACE**    | "Data layer complete" and "weeks 1-6 next" are disproved. Replacement is this spec once approved.                                                                              |
| `project_jailyard_roadmap.md.bak.*` (4 files)      | **DELETE**     | Redundant with git and the snapshot backup.                                                                                                                                    |
| `CLAUDE.md` stale counts                           | **REPLACE**    | States 200 tests; suite is 343. Correct in place.                                                                                                                              |
| `CLAUDE.md` rules and patterns                     | **KEEP**       | Operative. Amend only where this design changes a rule.                                                                                                                        |
| `team-profiles.json` structured fields             | **RECLASSIFY** | Ranks, needs, values, projections beside prose become untrusted until independently sourced or regenerated. Not deleted.                                                       |
| Feedback memories, vault notes                     | **AUDIT**      | Per-file verdict; same rule — no deletion without an identified replacement.                                                                                                   |

The census is produced and reviewed before any file is modified.

## Phase B — Data integrity, the audit, and the writer-access boundary

**Repair.** Slice `h2h_entry["games"]` by the edition's cutoff (not a fixed "before week N") and
recompute `wins`/`losses`/`last_meeting` from that slice. Same for `historical_context`.
Re-extract all packets **and the `_expanded` companions in the same pass** — commit `c5b6b50`
regenerated week data without the companions and left 32 season-end Elo values leaking there.
Repeating that inside this fix would reproduce the bug being fixed.

**Audit.** Walk every leaf of every writer-facing artifact; every field must be classified.
Unknown fields fail closed.

- `static-legal` — cannot vary by cutoff and encodes nothing after it. Only valid where
  "identical across editions" is the _correct_ answer — precisely the test `historical_context`
  fails today.
- `cutoff-filtered` — varies by edition cutoff; must be derived through `compute_as_of_history`
  or an equivalent slice.
- `forbidden` — must not reach a writer-facing artifact.

Scope is every consumer, not only week packets: `weekN_data.json`, `weekN_data_expanded.json`,
`weekN_chat_context.json`, `data/franchises/*`, `data/2025/player_arcs/*`,
`content/team-profiles.json`.

Reuse the coverage pattern in `docs/superpowers/plans/2026-07-11-governance-foundation.md`
Task 5 — `_leaf_pointers()`, `coverage_check()`, equal-specificity conflicts failing closed,
tests globbing real files. Written for content governance; the mechanism transfers to data
unchanged.

**Prove it fires.** Plant leaks of each class and confirm the audit reports them before trusting
any green result. A check that has never failed has not been tested.

**Writer-access boundary.** Full-season artifacts — franchise wings, player arcs, team profiles,
chat analytics — cannot remain direct writer or desk inputs governed by prose instructions to
"slice carefully." A rule a human must remember is not a boundary. Writers and desks consume
**cutoff-safe projections** of these stores; direct reads of full-season aggregates become test
failures.

The projection is the minimum needed to serve an edition: the subset of each store legally
knowable at that edition's cutoff, with unavailable data represented explicitly rather than
omitted silently. This is a slicing contract, not a new storage layer or database.

**Week 1 pre-kickoff preview input contract.** `week1_data.json` contains week 1 outcomes and is
therefore not a legal preview input. The preview requires its own packet, which is the strictest
instance of the projection contract above:

- Standings at 0-0; no week 1 results, scores, margins, or awards.
- H2H sliced to meetings before week 1 of 2025 — 2022-2024 only.
- Week 1 matchup pairings (schedule is known pre-kickoff).
- Rosters and availability as of lock, from `fantasy_rosters/week1.json` and pre-kickoff injury
  data.
- Preseason receipts: the predictions and threads that edition opened.
- Forward-looking evidence must be a genuine pre-kickoff projection, not a back-derived one.
  Any projection or market snapshot admitted must carry a `known_at` no later than kickoff.

The projection mechanism is adopted because the preview cannot exist without it, independent of
the larger proposal it also appeared in.

**Gate.** Promote `verify_h2h_claims` from warning to error, evaluated against the edition's
cutoff.

## Phase C — The writing room

**Name repertoires.** Mine the chat corpus for how each of the twelve owners is actually
referred to. Produce twelve rows — first name, surname, Sleeper handle, team, shorthand, earned
nicknames — with usage notes on which form fits which register. Blake approves once; ships as
committed data the Culture desk serves.

"Brent Boone" in every sentence is not a style failure — it is what happens when the writer holds
a database row instead of a relationship. A person you know has a name that moves with context.

**Desks**, as committed commands so 2026 reuses them: Power Rankings, Game/NFL, History, Culture,
Continuity, plus a Data/Copy Editor. Desks return structured evidence and candidate angles, never
prose. One columnist owns voice, pacing, and argument. Desks consume projections, not full-season
stores.

**Continuity desk carries voice memory** — reads what has been published and reports what has
been spent: jokes, comparisons, openers, name-forms per owner. The only mechanism that catches
semantic repeats, which a string-matching ledger cannot.

Columns go stale because each edition is written cold — independent draws from one distribution,
each reaching for the most probable phrasing. `picks_ledger` and `meta.threads` already make an
edition conditional on its predecessors for _facts_. Nothing does so for _voice_.

**Bake-off.** Write the first edition both ways — desks and the existing single-writer pipeline
— and compare under the editor rubric: factual corrections required, unique evidence used, phrase
repetition, owner specificity, how much prose survives Blake's edit. Keep the winner, delete the
loser.

## Phase D — Twenty fresh canonical editions

**All existing prose is filler.** Preseason-2025, weeks 1-6, current rankings, threads, media
choices, and 2026 prose carry zero editorial authority. They are preserved through git as
fixtures and are **not** used as inspiration, exemplars, continuity, rankings, or factual
evidence. Preseason-2025 is written fresh through the final system, not re-gated.

**The corpus:** preseason-2025, a standalone week-1 pre-kickoff preview, week 1-17 recaps, and a
week-18 finale (no week-18 fantasy games were played). Twenty editions, all produced from a blank
editorial page.

**Shape: story-first within stable sections.** Sections remain available and the renderer and
verifier stay simple, but each edition leads with its strongest story and sections flex in
weight. A thin section may be two lines or absent. Playoff weeks (15-17) and the finale get their
own contracts.

**Order is strictly sequential — a hard dependency, not a preference.** The prior edition's
writer _invents_ the picks, spreads, and Lock / Upset Watch / Stay Away tags; that data exists in
no generated file. An edition's `meta.picks_ledger` cannot be authored before the picks exist.
Threads must be opened before being advanced. Callbacks quote prose that must exist. Concurrent
writers produce N copies of edition one.

**Per-edition loop:** cutoff declared → projection built → desks brief → columnist writes →
`verify_week_content.py` exits 0 → `/edit-week` APPROVE (one `review-log.jsonl` line per pass) →
media → render → commit.

**Checkpoint after week 6:** synthesize `review-log.jsonl` into standing writer rules before
continuing.

**Serial, owned by the lead context, never delegated:** `check_picks_ledger` (transitive over all
prior content), `verify_prev_rank_claims`, and appends to `content/review-log.jsonl` — one shared
unlocked ledger with a read-modify-write on `pass_number`.

## Out of scope

- The remainder of the larger evidence-reconciliation proposal beyond the projection contract
  adopted above: EditionSpec/SeasonSnapshot/EvidenceBundle/RankingSnapshot as formal typed
  layers, a validated ranking model with a selection gate, disposable benchmark editions, and a
  clean-room 2026 rehearsal. Revisit if the widened audit finds classes the targeted repair
  cannot address.
- v2 redesign (deferred to in-season 2026).
- 2026 readiness: live roster capture, preseason-2026, `compute_preseason_window` constants.
- `feat/analytics-owner-edge` — parked, unmerged, shadow-only.

## Acceptance

- **Phase A:** the keep/replace/delete census is reviewed and approved before any file changes;
  every DELETE verdict names an existing replacement or an explicit "no replacement needed";
  all twelve handles match `data/2025/users.json`.
- **Phase B:** the census script reports 0 confirmed future entries (from 45) and 0 structurally
  unsliced H2H blocks (from 98); the audit reports zero unclassified fields across all consumers
  **and** is demonstrated to fire on planted leaks of each class; no consumer reads a full-season
  store directly; a legal week-1 preview packet exists and contains no week 1 outcomes;
  `verify_h2h_claims` errors; suite green (baseline 343 passed / 2 skipped at `c751b22`); CI
  green on HEAD's own SHA.
- **Phase C:** twelve name repertoires committed and Blake-approved; desks exist as committed
  commands; bake-off run and outcome recorded in `review-log.jsonl`.
- **Phase D:** each edition passes the global content gate — verifier 0 errors AND `/edit-week`
  APPROVE AND renders clean AND as-if-realtime checklist clean. Binary; no "APPROVE with notes."

## Open items

- Whether the widened audit surfaces leak classes beyond `h2h` and `historical_context`. If so,
  repair scope grows before Phase C.
- Playoff (weeks 15-17) and finale content contracts — needed before week 15, not before the
  first edition.
- Which pre-kickoff forward-looking evidence is admissible for the week-1 preview, and whether a
  qualifying source with a defensible `known_at` exists at all. If none does, the preview relies
  on roster, schedule, and preseason receipts only.
