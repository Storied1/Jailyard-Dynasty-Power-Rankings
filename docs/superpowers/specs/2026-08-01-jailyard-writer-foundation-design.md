# Jailyard — Writer Foundation + Newsroom Design

**Date:** 2026-08-01
**Status:** Design approved by Blake in session. Supersedes the "weeks 1-6 next" sequencing in
`2026-06-04-jailyard-2025-catchup-design.md` (that document's data → content → design ordering
still holds; only its claim that the data layer is complete does not).

## Context

The 2026-06-04 program said the next step was rewriting weeks 1-6. That is wrong, and this
session proved it against disk.

`content/weeks/week1_data.json` — the writer's primary input — tells a week-1 columnist the
score of a game played in week 17. Every matchup carries an `h2h` block whose `wins`, `losses`,
and `last_meeting` are all-time totals taken from the season-end aggregate, with no as-of-week
filter. **98 of 98 matchup h2h entries across all 18 week packets leak future results.** A
second block, `historical_context`, is byte-identical in every packet and cites a 2025 week-14
record inside week 1.

Root cause: `extract_week_data.py:559-567` reads `history_data["h2h"]` from
`league_history.json` and takes `games[-1]` as `last_meeting`. The correct as-of-week helper,
`compute_as_of_history`, already exists in the same file and is already used by the standings
path.

The verifier makes it worse rather than catching it: `verify_h2h_claims`
(`verify_week_content.py:892-949`) validates the writer's prose _against_ the contaminated
field, and only warns. A column that faithfully reports the leaked number is certified correct.

### What is NOT broken

This bounds the work. `standings` are genuinely as-of-week: across weeks 1 and 10, zero of
twelve standings blocks are identical (`record` 0-1 → 2-8, `current_elo` 1429.4 → 1351.7,
`all_time_record` 19-24 → 21-31). The M1 `compute_as_of_history` fix works exactly as the
roadmap claims. The chat layer's temporal admissibility and provenance were hardened and pushed
on 2026-07-20 (`c751b22`, CI green).

So the defect is not "the foundation is incomplete." It is that **one fix landed on one field
family and silently missed its siblings** — the fourth documented instance of that pathology in
this repo, and the first three went unnoticed for weeks or months each. Nothing walks the
writer-facing surface and asks every field whether it is as-of-week legal. That missing
instrument, not the two leaking blocks, is the real finding.

## Phase A — Delete the stale instruction surface

Delete outright. Git and the daily ClaudeMemorySnapshot backup already preserve history; no
`SUPERSEDED` markers, no tombstones, no archive files.

- `content/voice-bible.md` — §5 exemplars quote the preseason that was replaced on 2026-07-10.
  `@kharlo_w` is wrong; `data/2025/users.json` says `kharlow`. Re-verify all twelve handles
  against that file, **not** `content/team-profiles.json`, which carries its own `"kharlo w"`
  drift.
- `project_jailyard_roadmap.md` — three nested "SUPERSEDED / preserved as audit trail" blocks,
  plus the now-disproved claims that the data layer is complete and that weeks 1-6 are next.
  Delete the four `.bak` copies in the memory directory.
- `CLAUDE.md` — stale counts (states 200 tests; suite is 343).
- Feedback memories and vault notes — audit, cut what no longer holds.

## Phase B — Data integrity, and the instrument that proves it

**Repair.** Filter `h2h_entry["games"]` to meetings strictly before (2025, week N) and recompute
`wins`/`losses`/`last_meeting` from that slice. Apply the same treatment to
`historical_context`. Re-extract all 18 packets with `--pretty` **and the `_expanded`
companions in the same pass** — commit `c5b6b50` regenerated week data without the companions
and left 32 season-end Elo values leaking there; repeating that inside this fix would reproduce
the exact bug being fixed.

**Instrument.** An audit that walks every leaf of every writer-facing artifact and requires each
field to be classified. Unknown fields fail closed. The three classes:

- `static-legal` — the value cannot vary by week and cannot encode anything after the cutoff.
  Preseason team profiles and pre-2025 league records qualify; a field is only static-legal if
  identical across packets is the _correct_ answer, which is precisely the test
  `historical_context` fails today.
- `as-of-filtered` — the value varies by week and must be derived through
  `compute_as_of_history` or an equivalent cutoff filter. `standings` and (after repair) `h2h`.
- `forbidden` — must not reach a writer-facing artifact at all. Scope is every writer-facing artifact, not only week packets: `weekN_data.json`,
  `weekN_data_expanded.json`, `weekN_chat_context.json`, `data/franchises/*`,
  `data/2025/player_arcs/*`, `content/team-profiles.json`.

Reuse the coverage pattern already specified in
`docs/superpowers/plans/2026-07-11-governance-foundation.md` Task 5 — `_leaf_pointers()`,
`coverage_check()`, equal-specificity conflicts failing closed, tests globbing real files rather
than fixtures. It was written for content governance; the mechanism transfers to data unchanged.

**Prove it fires.** Plant leaks of each class and confirm the audit reports them before trusting
any green result. A check that has never failed has not been tested.

**Gate.** Promote `verify_h2h_claims` from warning to error, checked against corrected values.

## Phase C — The writing room

**Name repertoires.** Mine the chat corpus for how each of the twelve owners is actually
referred to in practice. Produce twelve rows — first name, surname, Sleeper handle, team,
shorthand, earned nicknames — with usage notes on which form fits which register. Blake approves
once; it ships as committed data the Culture desk serves to every column.

Rationale: "Brent Boone" in every sentence is not a style failure, it is what happens when the
writer holds a database row instead of a relationship. A person you know has a name that moves
with context.

**Desks**, built as committed commands so the 2026 season reuses them: Power Rankings, Game/NFL,
History, Culture, Continuity, plus a Data/Copy Editor. Desks return structured evidence and
candidate angles — never prose. One columnist owns voice, pacing, and argument.

The **Continuity desk carries voice memory**: it reads what has already been published and
reports what has been spent — which jokes, comparisons, openers, and name-forms per owner. This
is the only mechanism that catches semantic repeats ("same joke, different words"), which a
string-matching ledger cannot.

Rationale for the desks generally: columns go stale because each week is written cold —
eighteen independent draws from one distribution, every draw reaching for the most probable
phrasing. `picks_ledger` and `meta.threads` already make week N conditional on its predecessors
for _facts_. Nothing does so for _voice_.

**Bake-off.** Write week 1 both ways — desks and the existing single-writer pipeline — and
compare under the editor rubric: factual corrections required, unique evidence used, phrase
repetition, owner specificity, how much prose survives Blake's edit. Keep the winner, delete the
loser. This is the gate the newsroom proposal itself asked for, and it distinguishes two
confounded causes: v1's staleness may have been architecture, or may have been the far poorer
February evidence layer that no longer exists.

## Phase D — Write the season

**20 canonical editions:** preseason-2025, a standalone week-1 pre-kickoff preview, week 1-17
recaps, and a week-18 finale (no week-18 fantasy games were played).

Phase D covers all 20, produced in order. Weeks 1-6 are a checkpoint, not a separate phase: after
week 6, synthesize `review-log.jsonl` into standing writer rules before continuing to week 7.
preseason-2025 already shipped and is re-gated against the corrected data rather than rewritten,
unless the audit shows its inputs were contaminated.

The week-1 preview is added because it is the strictest as-of-week case in the corpus — it makes
picks with zero 2025 results in evidence — and it gives predict-then-grade a clean start.

**Shape: story-first within stable sections.** The six sections remain available and the
renderer and verifier stay simple, but each week leads with its strongest story and sections
flex in weight. A thin section may be two lines or absent. Playoff weeks (15-17) and the finale
get their own contracts, as the 2026-06-04 spec already requires.

**Order is strictly sequential and this is a hard dependency, not a preference.** Week N-1's
writer _invents_ the six picks, their spreads, and their Lock / Upset Watch / Stay Away tags;
that data exists in no generated file. Week N's
`meta.picks_ledger.week{N-1}_picks_results` cannot be authored before the pick exists. Threads
must be opened before they can be advanced. Callbacks quote prose that must exist. Six
concurrent writers produce six week 1s.

**Per-edition loop:** desks brief → columnist writes → `verify_week_content.py` exits 0 →
`/edit-week` APPROVE (one `review-log.jsonl` line per pass) → media → render → commit.

**Serial, owned by the lead context, never delegated:** `check_picks_ledger` (transitive over
all prior content), `verify_prev_rank_claims`, and appends to `content/review-log.jsonl` — one
shared unlocked ledger across all editions with a read-modify-write on `pass_number`.

## Out of scope

- Sol's full six-phase program: new contract layers (EditionSpec, SeasonSnapshot,
  EvidenceBundle, RankingSnapshot), quarantining all existing prose as untrusted, a validated
  ranking model with a selection gate, disposable benchmark editions, and a clean-room 2026
  rehearsal. The confirmed defect does not justify that scope. Revisit if the widened audit
  finds leak classes that the targeted repair cannot address.
- v2 redesign (deferred to in-season 2026).
- 2026 readiness: live roster capture, preseason-2026, `compute_preseason_window` constants.
- `feat/analytics-owner-edge` — remains parked and unmerged.

## Acceptance

- Phase A: no `SUPERSEDED` block remains in memory or repo docs; all twelve voice-bible handles
  match `data/2025/users.json`; `.bak` files gone.
- Phase B: zero leaking `h2h` entries across 18 packets (currently 98); `historical_context`
  as-of-week per packet; the audit reports zero uncovered fields across all writer-facing
  artifacts AND is demonstrated to fire on planted leaks of each class; `verify_h2h_claims`
  errors; full suite green (baseline 343 passed / 2 skipped at `c751b22`); CI green on HEAD's
  own SHA.
- Phase C: twelve name repertoires committed and Blake-approved; desks exist as committed
  commands; bake-off run and the outcome recorded in `review-log.jsonl`.
- Phase D: each edition passes the global content gate — verifier 0 errors AND `/edit-week`
  APPROVE AND renders clean AND as-if-realtime checklist clean. Binary; no "APPROVE with notes."

## Open items

- Whether the widened audit surfaces leak classes beyond `h2h` and `historical_context`. If it
  does, repair scope grows before Phase C starts.
- Playoff (weeks 15-17) and finale content contracts — needed before week 15, not before week 1.
