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

**Structural exposure: 98 of 98 H2H blocks are unsafe.** Every `matchups[].h2h` block in every
week packet is sourced from `league_history.json`'s season-end aggregate with no cutoff slice —
`wins`, `losses`, and `last_meeting` are all-time values. Blocks that read correctly today do so
by accident of scheduling, not by construction.

**Confirmed contamination: 46 entries currently carry future values.**

| Class                                      | Count  | Detail                                                   |
| ------------------------------------------ | ------ | -------------------------------------------------------- |
| H2H `last_meeting` postdating the packet   | 32     | Worst case: `week1_data.json` carries a week-17 score    |
| `historical_context.highest_combined`      | 13     | 2025 week 14 record, present in packets 1-13             |
| `historical_context.longest_losing_streak` | 1      | Undated aggregate; week 1 carries 10, correct value is 9 |
| **Total**                                  | **46** |                                                          |

### Reproducing census

Two passes are required, and the second is the one that was originally missed.

**Pass 1 — dated entries.** Compare `season`/`week` against the edition cutoff:

```python
import json, glob, re
def wkof(p): return int(re.search(r'week(\d+)_', p).group(1))

h2h_struct = 0; h2h_future = []; hc_future = []
for fp in sorted(glob.glob('content/weeks/week*_data.json'), key=wkof):
    wk = wkof(fp); d = json.load(open(fp, encoding='utf-8'))
    for m in d.get('matchups', []):
        h = m.get('h2h') or {}
        if not h: continue
        h2h_struct += 1                      # sourced from the unsliced aggregate
        lm = h.get('last_meeting') or {}
        s, w = lm.get('season'), lm.get('week')
        if s is not None and (s > 2025 or (s == 2025 and w is not None and w > wk)):
            h2h_future.append((wk, s, w))    # recap semantics: week N's own meeting is legal
    for key, rec in (d.get('historical_context') or {}).items():
        if not isinstance(rec, dict): continue
        s, w = rec.get('season'), rec.get('week')
        if s is not None and (s > 2025 or (s == 2025 and w is not None and w > wk)):
            hc_future.append((wk, key, s, w))
```

Expected: `h2h_struct == 98`, `len(h2h_future) == 32`, `len(hc_future) == 13`.

The comparison is `w > wk`, not `w >= wk`. Using `>=` reports 98 H2H leaks, which conflates
structural exposure with actual contamination.

**Pass 2 — undated aggregates.** `longest_win_streak` and `longest_losing_streak` carry only
`count`, `team`, `owner_id`. **A missing `season`/`week` cannot mean safe, and cannot mean
skipped.** Undated aggregates are recomputed from temporal primitives and compared to the
committed value. For streaks: replay non-playoff games from `data/*/season_combined.json` in
order, truncated at each edition cutoff, tracking `best_l` per owner
(`fetch_sleeper.py:962-1002`). Verified results:

| Cutoff            | Correct `longest_losing_streak` | Committed value |
| ----------------- | ------------------------------- | --------------- |
| through 2024      | 8                               | 10              |
| through 2025 wk 1 | 9                               | 10              |
| through 2025 wk 2 | 10                              | 10              |

So exactly one packet (week 1) is contaminated on this field today. That the number is small is
irrelevant — the field was invisible to the detector entirely, which is the real defect.

### Root cause

`extract_week_data.py:559-567` reads `history_data["h2h"]` and takes `games[-1]` as
`last_meeting`. No cutoff filter. `compute_as_of_history` — the correct helper — already exists
in the same file and is already used by the standings path.

`verify_h2h_claims` (`verify_week_content.py:892-949`) validates writer prose _against_ the
contaminated field, and only warns. A column faithfully reporting the leaked number is certified
correct.

### What is NOT broken

`standings` are genuinely cutoff-correct: between weeks 1 and 10, zero of twelve standings blocks
are identical (`record` 0-1 → 2-8, `current_elo` 1429.4 → 1351.7, `all_time_record` 19-24 →
21-31). The chat layer's temporal admissibility and provenance were hardened and pushed
2026-07-20 (`c751b22`, CI green).

The defect is not "the foundation is incomplete." One fix landed on one field family and silently
missed its siblings — the fourth documented instance of that pathology here. **Nothing walks the
writer-facing surface and asks every field whether it is cutoff-legal**, and nothing recomputes
the fields that carry no timestamp to ask with.

## Temporal semantics

**The cutoff is an exact UTC instant, declared per edition** — not a week number. Week numbers
cannot express "before the Thursday opener," which is exactly where the preview lives.

| Edition                    | Cutoff                         | Week N results | Week N H2H meeting |
| -------------------------- | ------------------------------ | -------------- | ------------------ |
| Preseason                  | before any 2025 game           | excluded       | excluded           |
| Week 1 pre-kickoff preview | first 2025 kickoff instant     | excluded       | excluded           |
| Week N recap               | after week N games conclude    | included       | included           |
| Finale (week 18)           | after the week 17 championship | n/a (no games) | included thru 17   |

**Every source class is qualified, not only markets.** For each source: what temporal primitive
establishes its `known_at`, how it is recomputed at a cutoff, what provenance is required, and
what happens when it cannot be established (the answer is "unavailable," never "assume safe").

Transaction reconstruction uses the **effective completion instant**, not `created` — some
transactions are created before a kickoff and complete after it.

## Phase 0 — 2026 evidence preservation (parallel lane, starts immediately)

The point of rebuilding 2025 is to exercise the system that will write the 2026 preseason and
week-1 preview. That evidence is disappearing now:

- `data/2026` is still the 2026-04-04 snapshot.
- `.github/workflows/fetch-sleeper-data.yml` cron is `0 6 * 9-12 0` — nothing runs before
  September.
- `fetch_sleeper.py` overwrites current rosters and projections with no append-only capture
  identity.

Spending the summer rebuilding 2025 while volatile 2026 preseason evidence evaporates would
force us to reconstruct another pre-kickoff state after the fact — the exact failure class this
design exists to eliminate.

**Scope:** timestamped, append-only snapshots of the 2026 sources we qualify, each with a content
hash and explicit capture-time and `known_at` semantics. Existing snapshots are never overwritten.

This is evidence preservation, not 2026 authoring. No 2026 prose is written.

## Phase A — Authority and read-path census

Not a file table. An audit of **every path by which prose reaches a writing decision**: prompts,
local drafts, generators, editors, media tools, renderers, and derived artifacts.

Confirmed contaminated read paths:

| Path                                      | Finding                                                                   |
| ----------------------------------------- | ------------------------------------------------------------------------- |
| `voice-bible.md` §1 patterns              | Excerpts at :16-20, :38-46, :64-70, :100-106, :122-126, :148-152          |
| `voice-bible.md` §5 exemplars             | Entirely excerpts from superseded prose                                   |
| `write-week.md:7-25`                      | Requires the whole voice bible, team-profile essays, optional local draft |
| `write-preseason.md:47-53`                | "use as inspiration" for team-profile prose                               |
| `write-preseason.md:72-75`                | 2026 prose as "shape, tone, and length precedent"                         |
| `weekN_data.json` `team_profiles_summary` | Carries `essay_snippet` and `roast`                                       |
| `generate_franchise_wings.py:294-301`     | Compiles `roast` into `voice_bible_callbacks` in franchise data           |

**Keep:** abstract voice grammar (pattern definitions), section templates, anti-patterns.
**Remove or block:** every current prose excerpt, wherever it appears — including inside
generated data.
**Preserve:** old prose as git fixtures that no active path can read.

**No replacement exemplar is required for the first edition.** The "no deletion before
replacement" rule applies to authoritative _instruction surfaces_, not to illustrative excerpts;
the voice grammar is fully operative without examples. The first approved edition becomes the
first canonical exemplar afterward.

The handle table in §2 is replaced by the chat-mined name repertoire (Phase C); `@kharlo_w` is
wrong — `data/2025/users.json` says `kharlow`. Roadmap SUPERSEDED blocks and the four `.bak`
copies are deleted; git and the daily ClaudeMemorySnapshot preserve history. `CLAUDE.md` stale
counts corrected in place (states 200 tests; suite is 343).

## Phase B — Repair, projection compiler, and audit

### Repair

Slice `h2h_entry["games"]` by the edition cutoff and recompute `wins`/`losses`/`last_meeting`.
Recompute `historical_context` — including undated aggregates — at each cutoff. Re-extract all
packets **and the `_expanded` companions in the same pass**; commit `c5b6b50` regenerated week
data without the companions and left 32 season-end Elo values leaking there.

**Role change.** The repaired per-week packet stops being a direct writer input and becomes a
**component of its edition's bundle**, carrying the bundle's cutoff and hash. This keeps the
existing verifier and renderer working against a familiar shape while still satisfying the
writer-access boundary — the packet a consumer reads is the one the projector compiled, not a
file it opened for itself. Its prose fields (`team_profiles_summary.essay_snippet`, `roast`) are
stripped per Phase A. Pages outside the writing path (`season.html`, `history.html`) may continue
reading published data directly; the boundary governs writing decisions, not site rendering.

### Projection compiler

Lightweight, file-backed, no database and no full typed evidence hierarchy — but a real contract,
not an ephemeral subset.

- **Edition descriptor:** `edition_id`, `season`, edition kind, `cutoff_utc`, results-through
  week, policy version.
- **One canonical, persisted writer-facing bundle per edition.** Persisted because the archive is
  definitive; an ephemeral slice cannot be re-audited.
- **Per-source adapters**, each naming its temporal primitive, recomputation rule, provenance
  requirement, and unavailable behavior. Final aggregates — streaks, player arcs, records —
  cannot be made safe by generic field filtering and require explicit recomputation rules.
- **The projector is the sole trusted reader** of raw and full-season stores.
- **Consumers** — writer, desks, editor, local drafter, media picker, content verifier — read
  only the edition bundle, approved prior editions, and editorial rules. Direct reads of
  full-season stores become test failures.
- **Bundle identity** binds descriptor, source hashes, projection code, policy, and output hash.
- **The review record binds the exact bundle hash** it was approved against; a changed bundle
  makes the approval stale.
- **Season-parameterized from the start**, with at least one non-2025 canary edition, so 2025
  genuinely tests a reusable system rather than a 2025-shaped one.

### Week 1 pre-kickoff preview inputs

`data/2025/fantasy_rosters/week1.json` is **not** a legal preview source. Proof: transaction
`1269785739084701696` added player `6949` to roster 6 at `2025-09-05T20:10:20.977Z`, after the
September 4 opener; that player appears in both `players` and `starters` in the backfilled week-1
file. The file records what week 1 became, not what was knowable before it.

The preview roster is **reconstructed to the exact cutoff instant** from transactions (using
effective completion instants) plus an admissible anchor — or marked unavailable.

**Unavailable unless separately proven:** final starters (inherently later knowledge), injuries,
availability, betting lines, market projections. No historical injury or availability artifact
currently proves a pre-kickoff `known_at`.

The preview is not thereby empty. It builds original forecasts from: the reconstructed roster,
the completed draft, 2022-2024 history and H2H, week-1 pairings stripped of outcomes,
cutoff-projected chat, and the newly approved preseason edition's rankings, predictions, and
opened threads. External forecasts are optional evidence, not what makes it a preview.

### Audit — two distinct questions

**Leaf census:** did we classify every field? Every leaf of every writer-facing artifact must be
`static-legal`, `cutoff-filtered`, or `forbidden`. Unknown fails closed. Undated aggregates
cannot be classified `static-legal` by default — absence of a timestamp triggers recomputation,
not exemption. Reuse the coverage pattern in
`docs/superpowers/plans/2026-07-11-governance-foundation.md` Task 5.

**Noninterference:** did future evidence actually influence a classified field? Full-input versus
cutoff-truncated runs must produce byte-identical bundles, with detector-active positive controls
proving the comparison can fail. The existing chat-context noninterference and provenance code is
the local pattern.

Both are required; neither substitutes for the other. A clean rebuild must reproduce the same
bundle.

**Gate:** promote `verify_h2h_claims` from warning to error, evaluated against the edition cutoff.

## Phase C — The writing room

**Name repertoires.** Mine the chat corpus for how each of the twelve owners is actually referred
to. Twelve rows — first name, surname, handle, team, shorthand, earned nicknames — with usage
notes on register. Blake approves once; ships as committed data the Culture desk serves.

"Brent Boone" in every sentence is what happens when the writer holds a database row instead of a
relationship. A person you know has a name that moves with context.

**Desks**, as committed commands so 2026 reuses them: Power Rankings, Game/NFL, History, Culture,
Continuity, plus a Data/Copy Editor. Desks return structured evidence and candidate angles, never
prose. Desks read the edition bundle only.

**Continuity desk carries voice memory** — reads approved prior editions and reports what has
been spent: jokes, comparisons, openers, name-forms per owner. The only mechanism that catches
semantic repeats, which a string-matching ledger cannot.

Columns go stale because each edition is written cold — independent draws from one distribution,
each reaching for the most probable phrasing. `picks_ledger` and `meta.threads` make an edition
conditional on predecessors for _facts_. Nothing does so for _voice_.

**Bake-off.** Write the first edition both ways — desks and single-writer — and compare under the
editor rubric: factual corrections required, unique evidence used, phrase repetition, owner
specificity, how much survives Blake's edit. Keep the winner, delete the loser.

## Phase D — Twenty fresh canonical editions

**All existing prose is filler with zero editorial authority** — preseason-2025, weeks 1-6,
current rankings, threads, media choices, 2026 prose. Preserved as inaccessible git fixtures;
never inspiration, exemplars, continuity, rankings, or factual evidence. Preseason-2025 is
written fresh through the final system, not re-gated.

**The corpus:** preseason-2025, a standalone week-1 pre-kickoff preview, week 1-17 recaps, and a
week-18 finale (no week-18 fantasy games were played).

**Shape: story-first within stable sections.** Sections remain available and the renderer and
verifier stay simple; each edition leads with its strongest story and sections flex in weight.
Playoff weeks (15-17) and the finale get their own contracts.

**Order is strictly sequential — a hard dependency.** The prior edition's writer _invents_ the
picks, spreads, and tags; that data exists in no generated file. An edition's `meta.picks_ledger`
cannot be authored before the picks exist. Threads must be opened before being advanced.
Callbacks quote prose that must exist.

**Per-edition loop:** descriptor declared → bundle compiled → desks brief → columnist writes →
`verify_week_content.py` exits 0 → `/edit-week` APPROVE (review-log line bound to the bundle
hash) → media → render → commit.

**Checkpoint after week 6:** synthesize `review-log.jsonl` into standing writer rules.

**Serial, owned by the lead context, never delegated:** `check_picks_ledger`,
`verify_prev_rank_claims`, and appends to `content/review-log.jsonl`.

## Out of scope

- **2026 authoring.** Phase 0 preserves 2026 evidence; it writes no 2026 prose.
- Formal typed evidence hierarchies beyond the descriptor/bundle/adapter contract above, a
  validated ranking model with a selection gate, disposable benchmark editions, and a clean-room
  2026 rehearsal. Revisit if the audit finds classes the adopted contract cannot address.
- v2 redesign (deferred to in-season 2026).
- 2026 live-season readiness: live roster capture, preseason-2026 authoring,
  `compute_preseason_window` constants.
- `feat/analytics-owner-edge` — parked, unmerged, shadow-only.

## Acceptance

- **Phase 0:** append-only 2026 snapshots exist with hashes and explicit capture/`known_at`
  semantics; re-running capture never overwrites a prior snapshot.
- **Phase A:** the read-path census is reviewed and approved before any file changes; no active
  writing path can reach barred prose, proven by test — including generated artifacts
  (`team_profiles_summary`, `voice_bible_callbacks`); abstract grammar, templates, and
  anti-patterns intact; twelve handles match `data/2025/users.json`.
- **Phase B:** census reports 0 confirmed future entries (from 46) across both passes, and 0
  structurally unsliced H2H blocks (from 98); the leaf census reports zero unclassified fields
  and fires on planted leaks of each class including an undated aggregate; noninterference is
  byte-identical with detector-active positive controls; a clean rebuild reproduces every bundle;
  no consumer reads a full-season store directly; a legal week-1 preview bundle exists containing
  no week-1 outcomes and no final starters; at least one non-2025 canary edition compiles;
  `verify_h2h_claims` errors; suite green (baseline 343 passed / 2 skipped at `c751b22`); CI green
  on HEAD's own SHA.
- **Phase C:** twelve repertoires committed and Blake-approved; desks exist as committed commands
  reading only bundles; bake-off run and outcome recorded.
- **Phase D:** each edition passes the global content gate — verifier 0 errors AND `/edit-week`
  APPROVE AND renders clean AND as-if-realtime checklist clean, with the approval bound to a
  bundle hash. Binary; no "APPROVE with notes."

## Open items

- Whether the audit surfaces leak classes beyond H2H, `historical_context`, and undated
  aggregates. If so, repair scope grows before Phase C.
- Which 2026 sources qualify for Phase 0 capture, and their `known_at` semantics.
- Whether any pre-kickoff forward-looking source has a defensible `known_at`. If none does, the
  week-1 preview runs on reconstructed roster, draft, 2022-2024 history, pairings, chat, and
  preseason receipts only.
- Playoff (weeks 15-17) and finale contracts — needed before week 15, not before the first
  edition.
