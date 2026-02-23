# Handoff — Week 4 Column Pipeline

## Current State
- `content/weeks/week4_content.json` — DRAFT generated, validator PASS (6 warnings, all benign)
- No HTML rendered yet for Week 4

## What's Done
1. Week 4 content written via `/write-week 4`
2. Validator run: `python scripts/verify_week_content.py --week 4 --pretty` → PASS

## Next Steps (in order)
1. **Edit** — Run `/edit-week 4` for quality gate review (voice score, data accuracy, variety, continuity)
2. **Media** — Tell Claude your GIPHY API key, then run `/pick-media 4` to select GIFs for the 3 media slots
3. **Render** — Tell Claude "resolve and render week 4" to produce `week4.html` with embedded GIFs + config.js nav update
4. **Push** — "push it" to commit and push the rendered HTML

## Key Context
- Picks ledger: cumulative 11-7 (Week 3 picks went 3-3, Lock busted)
- Week 4 storylines: Rasheeing upset Ken-obi by 1.64, Legion 4-0, Ghastly 176.42 explosion, Jeanty 32.5 on 0-4 Chudders
- 3 media slots: `week4-essay-opener`, `week4-lock-bust`, `week4-jeanty-irony`

## Pipeline Reference
```
/edit-week 4        → quality gate
/pick-media 4       → GIF selection (needs GIPHY API key)
"resolve and render week 4" → week4.html
"push it"           → commit + push
```

## Files That Matter
- `content/voice-bible.md` — style guide
- `content/team-profiles.json` — team context
- `content/weeks/week4_data.json` — source data
- `content/weeks/week4_content.json` — the draft (this session's output)
- `scripts/verify_week_content.py` — validator

## Delete This File
This handoff is temporary. Delete `HANDOFF.md` once work resumes.
