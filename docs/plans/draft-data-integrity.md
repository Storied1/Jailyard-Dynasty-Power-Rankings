# Draft Board Data Integrity Issues

**Date found:** 2026-02-17
**Status:** Deferred to /verify expansion
**Affects:** draft.html inline draftPicks + draftGrades arrays

## Known Issues

### 1. Traded picks show wrong team
8 picks in Round 1 display the original slot holder instead of who actually made the pick. The `team` field is used by the renderer to show team initials; traded picks show the wrong abbreviation.

Examples:
- Pick 1.04: shows Noble FFT, should be Burden of E.W.
- Pick 1.07: shows Ghastly Grayskull Gang, should be Burden of E.W.
- Pick 1.08: shows Burden of E.W., should be Chudders FT

### 2. Duplicate player: Devin Neal
Appears at both pick 2.01 (line 272) and pick 3.11 (line 296). One entry is likely incorrect.

### 3. Cross-reference conflict: Braelon Allen (3.06)
Listed under both Father Time and Rasheeing the Scene in the `draftGrades` array. Only one team actually made the pick.

### 4. Missing Round 6
`data/2025/league.json` shows `draft_rounds: 6`, but `draftPicks` only contains 5 rounds and the render loop runs `for (let r = 1; r <= 5; r++)`.

## Resolution Plan
These will be addressed when the generalized `/verify` slash command is built (deferred from the current media pipeline work). The verify system will cross-reference draft.html data against the raw Sleeper API draft endpoint.
