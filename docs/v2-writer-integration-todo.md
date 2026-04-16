# Writer Integration TODO — v2 data enrichment

> **Status (2026-04-16, post-Phase-17):** Superseded by Phases 11-17. Writer (`write-week.md`), editor (`edit-week.md`), voice-bible, and local_draft prompts are all wired. The `momentum.label` enumeration below is incomplete — Phase 11 added `early` (weeks 1-3 with partial rolling window). Canonical set: `opening | early | collapsing | cooling | steady | hot | surging`.

Generated during Phase 9 of `C:\Users\blake\.claude\plans\purrfect-bouncing-fox.md` (2026-04-14). This catalogs where the writer / editor / chat-context / local-draft consumers should reference the new enrichment fields in `content/weeks/weekN_data.json`:

- `top_scorers[].player_id` — Sleeper player ID (string)
- `top_scorers[].game_context` — `{opponent, stat_line, one_liner}` (or `null`)
- `awards.top_performer.player_id` and `.game_context` — same shape
- `standings[].roster_id` — int (for stable joining)
- `standings[].margin_this_week` — float (points over opponent, signed)
- `standings[].momentum` — `{score: float[-3,+3], label: opening|collapsing|cooling|steady|hot|surging}`
- `matchups[].momentum` — `{edge: float, label: coin flip|slight edge|heavy lean|upset brewing, favorite_team_name: str}`

These fields are NOT yet referenced by writer prompts or editor checklists. Updating them is out of scope for the v2 data enrichment plan — this file catalogs the specific places for a follow-up session.

---

## `.claude/commands/write-week.md`

Where the writer agent learns what fields exist in `week_data.json`.

**Lines to update:**

- Line 10 — current: `content/weeks/week${WEEK}_data.json — this week's data (matchups, standings, awards)`
  - After: extend the one-liner to mention the enrichment: `matchups (now with momentum), standings (now with momentum + margin_this_week), awards (top_performer now has game_context), top_scorers (now have player_id + game_context.one_liner for narrative framing)`.
- Line 34 — currently lists `matchups[].h2h` fields
  - After: add a new bullet before it: `matchups[].momentum.label — "coin flip" / "slight edge" / "heavy lean" / "upset brewing". Use to frame matchup preview/recap vibe.`
  - And: `matchups[].momentum.favorite_team_name — who's favored by trajectory, distinct from rank.`
- Line 35 — lists `standings[].current_elo, peak_elo, elo_change`
  - After: add bullet: `standings[].momentum.label — per-team trajectory (opening/cooling/steady/hot/surging/collapsing). Cite sparingly; don't say the label, describe the trajectory.`
  - And: `standings[].margin_this_week — the emotional story of this week. Use it when recapping.`
- **Per-player bullets (MISSING entirely from current prompt)** — add a new section after the `standings[].` fields listing `top_scorers[].game_context`:
  - `top_scorers[].game_context.one_liner — pre-rendered real-game stat line, e.g. "22 carries, 169 yd, 2 TDs vs. the Bills." Cite this directly when writing about a top scorer; it saves the writer from inventing stat lines that might be wrong.`
  - `top_scorers[].game_context.opponent — NFL opponent abbreviation; useful when narrating "your top player got his numbers against a good/bad defense."`
  - `top_scorers[].player_id — Sleeper player ID; join key for future cross-week player arcs. Don't cite in prose.`
- Line 173 — "Use next week's matchups from the data" — could extend to mention using `matchups[].momentum` for next-week preview vibe.

**Voice bible companion update (out of scope, cross-reference):**

- `content/voice-bible.md` has 12 Simmons-DNA patterns. A new pattern entry for "Real-game anchor" should be added: "Every fantasy number should trace to a real NFL moment. Use `game_context.one_liner` to anchor fantasy scores in actual Sunday action — 'Bijan went for 195 and a TD in a blowout of the Rams' reads better than 'Bijan put up 37.4.'"

---

## `.claude/commands/edit-week.md`

The editor's Tier 1/2 checklist.

**Lines to update:**

- Line 27 — "Every team record (W-L) matches standings data"
- Line 29 — "Power rankings order matches the data's standings"
- Line 32 — "Next week's matchup picks reference correct matchups from the data"
- Line 33 — "H2H records cited in content match `matchups[].h2h` in week data (if present)"
- Line 34 — "Elo ratings cited match `standings[].current_elo` in week data (if present)"

**New checklist items to add after line 34:**

- [ ] Any player stat lines cited in prose match `top_scorers[].game_context.stat_line` or `awards.top_performer.game_context.stat_line` in the week data. Flag any fabricated "X carries for Y yards" that don't appear in `game_context`.
- [ ] Any NFL opponent references cited in the content (e.g. "vs. the Ravens") match `top_scorers[].game_context.opponent`. No ghost opponents.
- [ ] Any momentum language ("surging," "collapsing," "upset brewing," "coin flip") tracks to `standings[].momentum.label` or `matchups[].momentum.label`. If the writer says Team X is "surging" but `momentum.label == "cooling"`, flag.
- [ ] Matchup previews / recaps that frame the vibe (e.g. "should be a coin flip") check against `matchups[].momentum.label` for consistency — or at minimum, don't contradict it.

---

## `scripts/local_draft.py`

Where local Qwen drafts are primed with week data. No code change strictly required — the JSON serialization at lines 187-190, 199-207, 240-244, 247-250, 282-299 already includes the new fields by default. But the prompts don't call them out.

**Prompt-level enhancements (optional, high leverage):**

- **Essay prompt (around `build_essay_prompt` near line 186):** add instruction text after the serialization block, e.g.:
  - `"Each top_scorer now has a 'game_context.one_liner' — cite it directly for narrative depth instead of inventing stat lines. Each standings entry has 'momentum.label' and 'margin_this_week' — use these to frame team trajectories."`
- **Rankings prompt (around `build_rankings_prompt` near line 236-244):** add similar instruction:
  - `"Each standings entry has 'momentum' — prefer describing trajectory over just rank change. Ignore if label is 'opening' (week 1)."`
- **Confessionals/mailbag/bits (around line 278-299):** the abridged data doesn't currently include momentum. Update line 299 (`for s in week_data["standings"]`) to include `momentum.label` and `margin_this_week` in the condensed standings summary so the LLM sees them.

---

## `scripts/build_chat_context.py`

Chat relevancy engine. Iterates matchups + top_scorers to score chat messages. **No code changes required** — new fields don't change relevancy scoring. Referenced locations for reference only:

- Lines 163-176 — matchup roster_id iteration
- Lines 190-194 — player name extraction from `top_scorers`
- Lines 200-202, 503, 530, 580-592, 740 — various matchup iterations

**Potential future enhancement (optional):** use `player_id` at line 192-194 instead of name matching for more reliable player attribution across weeks. Today name matching works but can miss edge cases (suffix like "Jr.").

---

## Suggested follow-up session scope

**Option A — minimum writer-integration update:**

1. Update `write-week.md` lines 10, 34, 35 + new per-player section (under 30 min of editing).
2. Update `edit-week.md` with 4 new checklist items.
3. Regenerate a single week (e.g. week 7 or rewrite week 6) to validate the writer uses the new fields naturally.

**Option B — full integration + voice bible:**

1. Everything in A.
2. Update `local_draft.py` prompts for essay + rankings + confessionals.
3. Add "Real-game anchor" pattern to `content/voice-bible.md`.
4. Regenerate weeks 1-6 to upgrade their narrative depth.

**Option C — wait for natural use:**
Leave prompts as-is. Data is there, the LLM will organically find it in serialization. Revisit if writer quality doesn't improve noticeably on next-generated week.
