# K3.8 Proposed Verdict — 2026-08-06

## Question

**Did richer evidence measurably change and improve the decisions?**

## Answer

**NO DECISION — CONTRAST DEGRADED.** The comparison was never run, and that is
the finding, not a failure of the machinery.

The frozen evidence manifest (sha256:98f0ee71f963894c14427b98f5db1a5bfef1a394d567b0926561f6b0f40d90a1,
frozen 2026-08-06T16:32:36Z) requires four families: roster_membership,
historical_matchup, chat_message, nfl_game. Three are sourced and populated in
the 2025 fact store (historical_matchup 294, chat_message 22884, nfl_game 285
facts). But roster_membership — and schedule_pairing inside the full_rich
bundle — are frozen with **empty source_ids**: "no qualified pre-kickoff roster
anchor (open dependency 3)". Every model-arm bundle therefore fails closed
(`ArmUnavailable`) at every edition, the contrast lane records all required
families at zero, and preflight returned DEGRADED (exit 1) before any model
arm ran.

The one approved remediation cycle is limited to re-capture or
re-normalization under already-frozen source_ids. An unsourced family has
nothing to re-run; adding a source is a manifest change the freeze forbids by
design. The cycle was recorded as a documented no-op
(remediation_record.json), and the second assessment returned
STOP — NO DECISION (exit 3) through the persisted cycle counter.

**Zero of the 36 authorized model invocations were spent.** No arm chains, no
seals, no scores, no blind review exist — all recorded NOT PRODUCED. The
machinery itself is fully built and proven: 664 tests pass, including the
39-cell zero-spend dry-run rehearsal, masking/crash/lineage mutation controls,
and the executable degraded→stop path this run just exercised for real.

## Comparison form (precommitted, unused)

full_rich vs minimal_legal, and each ablation vs full_rich, on median claim
score with inter-trial ranges — NOT PRODUCED (no complete arm grid exists).

## What the verdict does and does not govern

- **S1a does not begin.** No expansion. This branch proposes no lift and no
  no-lift — the experiment is unrun, not failed.
- **The 2025 archive mission is untouched** — it was never contingent on
  measured lift.
- **Prospective Phase-P capture and sealing continue** (store verified intact:
  2 seals checked, 0 failures, verify + rederive).

## The single decision now required (Blake only)

Whether to qualify a roster anchor: admitting a pre-kickoff roster_membership
(and schedule_pairing) source is **open dependency 3** — it requires a NEW
manifest version, which by design discards every completed arm (there are
none) and restarts the comparison. Until that source exists, K3's five-arm
experiment is structurally unrunnable, and re-running it without one will
reproduce this exact STOP.
