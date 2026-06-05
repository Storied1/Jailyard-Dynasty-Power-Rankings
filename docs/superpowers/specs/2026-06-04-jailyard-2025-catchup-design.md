# Jailyard Dynasty — 2025 Season Catch-Up Program

**Date:** 2026-06-04
**Status:** Ratified (Blake, 2026-06-04). Stress-tested by a 4-reviewer round (architect: NEEDS REVISION → revised + re-approved; strategic-critic, blind-spot-detector, elite-advisor). Two BLOCKING data bugs found in review were independently verified and are fixed in this design.
**Vault decision:** `40-Decisions/2026-06-04-jailyard-content-before-redesign.md` (supersedes `2026-04-08-jailyard-v2-sequencing.md`).
**Parent roadmap:** `project_jailyard_roadmap.md` (CC memory, restructured + ratified 2026-06-04).

## Context

It's June 2026. The 2025 NFL and fantasy seasons are over — final games in week 17 (championship; 4 playoff matchups), week 18 had no matchups. The site is parked at week 6 of a finished season. This program catches the site up: the **full 2025 season written**, then the v2 redesign, then 2026 readiness.

Writing 2025 retroactively is **dual-purpose**: produce the content AND lock the repeatable process (committed writer commands, continuity ledger, calibrated editor gate) that covers the 2026 season live.

The site is a **running blog**: later weeks back-reference earlier ones. Production is chronological so every piece lands on the FINAL version of its predecessors — the production order itself is the continuity enforcement.

### Editorial law (as-if-realtime)

Every column body and week subtitle uses only knowledge/stats/chat available at that point in the season. Enforcement layers:

1. **Generator** — `build_chat_context.py` hard UTC windows (`compute_week_cutoff`: Tue 06:59:59 UTC after that week's MNF; `compute_preseason_window`: 2025-02-10 → 2025-09-03); `filter_messages_in_window()` physically excludes out-of-window messages.
2. **Writer prompt** — `write-week.md:73,240` temporal rule (never reference past `meta.temporal_cutoff_utc`).
3. **Validator** — `verify_week_content.py` Tier-3 `check_chat_temporal_cutoff()` errors on content timestamps past cutoff.
4. **Data** — `extract_week_data.py` standings are cumulative through week N only.

**Known gap (fixed in M1):** derived chat analytics (`arcs.json`, `predictions.json`, `league-memory.json`) carry season-end knowledge (`resolution`, `status`, `span`, `key_moments`) that message-windowing does not sanitize; `find_active_arcs` _skips_ resolved arcs, so a then-live arc vanishes from early weeks (wrong in both directions). An as-of-week sanitizer is M1's first task, before any writing.

**Chrome exemption (ruled 2026-06-04):** the site wrapper — Championship Vault, landing page, meta description — is the present-day frame and may know the ending. Column bodies + week subtitles stay sacred.

## Locked decisions (execution order)

1. **Full data workstream first:** finish 1a, then 1b (cross-season aggregates) and 1c (writer-facing docs + writer-prompt wiring, incl. deferred Items 18/19) before any content.
2. **Chronological sweep:** preseason-2025 redo → weeks 1→18 in order.
3. **Rewrite depth:** preseason + weeks 1-6 = full rewrites (existing text reference-only; they were the process-discovery drafts); weeks 7-18 fresh.
4. **Render per week:** approved pieces ship live on the current design; the redesign re-renders everything once (explicit, accepted cost — knowingly reverses the April rationale).
5. **Chrome exempt, columns sacred** (above).
6. **Redesign AFTER all 2025 content**, then 2026 readiness.

## Out of scope (explicitly deferred)

- **v2 Redesign** (roadmap Phase 7) — after all content; gets its own spec. Reader-profile question (April decision Open Item #3) carries to its brief.
- **Old phases 2/3** (generators/distribution automation; falsifiable validation primitives) — absorbed into roadmap Phase 8 (2026-live concerns, not retro-writing prerequisites).
- **T8 live roster capture** — deferred to Phase 8; `fetch_sleeper.py` has no current-week detection and offseason "current week" is meaningless. Wire at 2026 kickoff.

## Program sequencing

| Step | Roadmap phase | Content                                                                    | Plan                                                   |
| ---- | ------------- | -------------------------------------------------------------------------- | ------------------------------------------------------ |
| M0   | 1a close      | Persist direction; T9 redesigned, T8 deferred, T10 corrected; CI gate live | `~/.claude/plans/you-dont-have-that-jaunty-volcano.md` |
| 1b   | 1b            | Cross-season aggregates                                                    | own plan, per data spec (2026-05-02)                   |
| 1c   | 1c            | Writer-prompt wiring (prerequisite to all writing)                         | own plan, per data spec                                |
| M1   | 4             | Preseason-2025 redo + pipeline hardening                                   | own plan                                               |
| M2   | 5             | Weeks 1-6 full rewrite + calibration instrumentation                       | own plan                                               |
| M3   | 6             | Weeks 7-18 (playoff template; wk18 finale)                                 | own plan                                               |

**Global content gate (every shipped piece):** verifier PASS (0 errors) AND `/edit-week` APPROVE AND renders clean AND as-if-realtime checklist clean.

## M0 — Phase 1a close (key corrections from review)

- **T9 redesigned.** The original deriver read `season_combined.get("rosters"/"transactions")` — neither key exists; real sources are `data/2025/rosters.json` (April-2026 snapshot) + `data/2025/transactions.json` (week-keyed dict; txns use **`leg`** not `week`; 97/717 are `status:"failed"` and must be filtered). Reversal from the April snapshot inherits the unrecorded 2025→2026 offseason gap (transactions stop at leg 17), so: **primary = live Sleeper re-fetch** of per-week matchups (players/starters arrays) for weeks 1-17 → authoritative snapshots; **fallback** = reversal-derived snapshots stamped `derived_confidence:"approximate"`, advisory-only for editorial checks. Tests must use real field shapes (synthetic `week` keys masked all three bugs).
- **T10 corrected.** Spot-checks updated to the shipped T7 games-map shape (no top-level `top_scorers[]`, no per-scorer `game` inlining); idempotency via the manifest-skip path.
- **CI gate.** `requirements.txt` + `.github/workflows/test.yml` committed `181d464`; first ubuntu run observed green (26s) — cross-platform proof for the CRLF/LF-sensitive manifest-hash test.

## M1 — Preseason-2025 redo + pipeline hardening

1. **Analytics as-of sanitizer** (before ANY writing): surface arcs as-of week N (active if started ≤N and not yet resolved at N); strip `resolution`/`status`/`key_moments` from everything injected into context; `/write-week` stops reading `league-memory.json` raw.
2. **Preseason context patch:** `--preseason` writes `content/preseason-2025/preseason_chat_context.json` (today it would overwrite `week{W}_chat_context.json` — `build_chat_context.py:1277`); `week_data` optional with null-guards on ~5 downstream call sites. Honest estimate: a second assembly path, not 6 LOC. Requires local gitignored `chat/parsed_messages.json` (privacy by design; single-machine constraint).
3. **Author `.claude/commands/write-preseason.md`** (the 2026 "write-preseason agent" prompt was never saved). Output contract mirrors `content/preseason-2026/preseason_content.json`: `{meta, essay ({{media:slot}} tokens), media_slots[], rankings[12: {rank, team_name, owner, tier, blurb}]}`. Knowledge cutoff stated (nothing after 2025-09-03). Draft board is API-rebuilt (`ca3d698`); grade text is editorial.
4. **Threads ledger:** `meta.threads` schema `{id, status: opened|continued|paid_off|dropped, opened, summary, last_touched}` — generalizes the proven `picks_ledger` pattern. Preseason promises seed it; weekly writers read predecessors' threads + emit their own. `check_threads_continuity()` Tier-1 warnings (~40 LOC mirroring `check_picks_ledger`).
5. **Ship `preseason-2025.html`:** `/render-preseason 2025`; nav = **core page, no group** (`{ label: "2025 Preview", href: "preseason-2025.html" }` before the 2026 Preview entry) — a `group:"columns"` non-"Week N" entry renders nowhere.
6. **`team-profiles.json` field-preserving merge:** update prose fields (rank, tier, roast, blurb, preseasonEssay); preserve structured fields (initials, ranks{}, keyPlayers, draftPicks, weeklyPoints, scheduleRank, needs, championshipHistory, owner spellings — incl. fixing the `kharlo w`/`kharlow` mismatch). Then re-run `extract_week_data.py --all` (temporally safe: preseason precedes all weeks) + re-verify weeks 1-6.
7. **`/edit-week` as-if-realtime checklist:** no week numbers >N; no prophecy idioms; no player-team pairs that became true later (roster snapshots advisory where `derived_confidence:"approximate"`); no post-cutoff knowledge; scope = column bodies + week subtitles. Editor emits one `review-log.jsonl` line per pass.
8. **Close-out:** strongest new-bar excerpts → voice-bible exemplars; media caches added to backup (gitignored; redesign re-render depends on them).

## M2 — Weeks 1-6 full rewrite

Loop 1→6: `git tag v1-content-frozen` once → `/write-week N` overwrites (writer pointed at REWRITTEN predecessors + merged team-profiles; reads predecessors' `meta.threads`) → verifier PASS → `/edit-week` APPROVE (+ review-log) → media: keep picks for surviving slot-ids, re-pick changed beats, prune stale keys → render + commit. No archive dir (git history + tag). Chat/data not regenerated beyond M1's re-extraction; Tier-3 re-run at start as drift guard.

- **Picks-ledger lockstep:** each rewritten week emits fresh picks; week N+1 re-grades them; `check_picks_ledger` recomputes the whole chain. Ledger chain 1→6 green before M3 (week-6 cumulative freezes M3's baseline).
- **`check_narrative_anachronisms()`** Tier-3 warnings: prophecy-idiom regex + week-number-overshoot heuristic. Promote idiom check to ERROR after weeks 1-2 FP calibration (warnings rationalize away under binary-gate culture).
- Optional: one `batch_drafts.py` run on weeks 1-6 measuring per-section Qwen keep-rates → calibrates the M3 lane.
- `index.html`/`season.html` "latest column" hardcodes → config-driven or per-week checklist item.

**M2→M3 calibration gate:** synthesize review-log — top recurring finding categories become standing writer-prompt rules; lock threads schema; set the Qwen lane; promote/demote anachronism checks per FP data.

## M3 — Weeks 7-18

Same loop minus archive/tag. Cadence: 1 week/session through the gate (2/session allowed weeks 13-18 if 7-12 ran clean). Local Qwen pre-drafts per the calibrated lane.

- **Playoff template (before week 15):** weeks 15-17 are bracket weeks (wk17 = championship; `min(matchup_id)` = title game); verifier assumes 12-team round-robin shapes — playoff content contract + verifier accommodation required. **Week 18 = season finale/awards format** (no games; the championship result is known at week-18 vantage — legal under as-if-realtime).
- **Rework protocol:** material change to an approved week → threads ledger identifies forward-referencing weeks → re-gate only those.

## 2026 live-season delta (which scaffolding is 2025-only)

| Artifact                                                 | 2025 retro role                      | 2026 live role                                                                                                 |
| -------------------------------------------------------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| Chat UTC windows                                         | Hard as-if-realtime enforcement      | Become "everything up to now" — still used, trivially satisfied                                                |
| Anachronism checks (idioms, week-overshoot, player-team) | Load-bearing                         | Idle — you cannot reference a future you don't have. Keep wired but expect zero hits                           |
| Analytics as-of sanitizer                                | Required (analytics know the ending) | Mostly idle (analytics can't know the future) — keep: it also normalizes arc shape                             |
| `meta.threads` ledger                                    | Continuity + rework index            | **More** valuable — live arc-tracking with no ability to peek ahead; the continuity spine                      |
| review-log + standing writer rules                       | Calibration during M2                | The live-season writer's standing instructions — first-pass quality when there's no time for 1.5 editor rounds |
| `/write-preseason`                                       | 2025 redo                            | Reused verbatim for preseason-2027; preseason-2026 refresh at Phase 8                                          |
| `compute_preseason_window` constants                     | 2025-specific dates                  | Needs 2026 constants (one-liner) at Phase 8                                                                    |
| T8 live roster capture                                   | Deferred                             | Activated at kickoff (with current-week detection, which must be built)                                        |

## Verification (end-to-end)

- **M0:** suite ≥76/76 local + first GitHub Actions Linux run passes (observed ✅ `181d464`, 26s); T10 idempotency in CI; roadmap diff approved (✅ 2026-06-04); T9 artifacts weeks 1-17 with source/confidence fields.
- **Per piece (M1-M3):** the global content gate.
- **Per milestone:** all pieces pass; config.js/nav current; suite green.
- **Program:** after M3 — 19 pieces live (preseason-2025 + weeks 1-17 + wk-18 finale); process locked as the 2026 SOP; THEN redesign re-renders once.

## Critical interfaces

- `scripts/build_chat_context.py` — analytics sanitizer + preseason output path (M1)
- `scripts/derive_historical_rosters.py` (new, T9) — `data/2025/rosters.json` + `transactions.json`, `leg`, `status=="complete"`; live-fetch primary
- `.claude/commands/write-preseason.md` (new), `write-week.md`, `edit-week.md` — writer/editor contracts, threads + checklist + review-log
- `content/team-profiles.json` — field-preserving merge contract (M1); `team_profiles_summary` is baked into every `weekN_data.json`
- `scripts/verify_week_content.py` — `check_narrative_anachronisms`, `check_threads_continuity`
- `config.js` — core-page nav entry (M1); per-week entries (M2/M3); season-strip matches only "Week N" labels

## Next step

Execute M0 Task 4 (T9 redesign under TDD, T10 corrected) → then author the 1b plan.
