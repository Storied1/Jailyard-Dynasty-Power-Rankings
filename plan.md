# Data Audit & Fixes Plan
## Jailyard Dynasty Power Rankings — March 2026

### Phase 1: Fix Critical Championship Data (NOW)

**1.1 Fix `index.html` Championship Vault (CRITICAL)**
- Lines 768-777: CHAMPS array has wrong winners AND runners-up for all years
- Correct data from `data/{year}/brackets.json`:
  - 2022: Winner = Sleeping Giants, Runner-up = Father Time
  - 2023: Winner = The Boonist Monks, Runner-up = The Legion of Bouz
  - 2024: Winner = MHJTIME, Runner-up = General Ken-obi
  - 2025: Winner = The Legion of Bouz, Runner-up = MHJTIME (MISSING — needs to be added)

**1.2 Fix `preseason.html` Playoff History (CRITICAL)**
- Lines 274-278: Same incorrect championship data
- Rewrite all playoff history text with correct winners/runners-up
- Add 2025 championship results

**1.3 Fix `config.js` Hardcoded Stats (HIGH)**
- Line 77: "3 different champions in 4 years" — verify actual unique champion count from bracket data
- Line 94: `{ target: 3, suffix: '', label: 'Champions' }` — update target to correct number
- Line 721: Clarify "championship appearances" vs "finals appearances" for Kittler

**1.4 Fix Owner Data (MEDIUM)**
- `preseason.html` line 471: "kharlo w" → "kharlow"
- Verify all other owner usernames against `league_history.json`

**1.5 Fix Data Cleanup (LOW)**
- `league_history.json`: Remove trailing space from "Father Time " team name
- Verify fun facts claims (500+ players, 60 picks, 7 first-round trades)

---

### Phase 2: Cross-Site Data Verification

**2.1 Run existing audit infrastructure**
- Run `/audit` skill across all pages
- Run `/test` skill to check HTML/CSS/nav/data/JS
- Run `verify_week_content.py` on weeks 1-5 to catch any data errors in published columns

**2.2 Cross-reference all hardcoded data against source JSON**
- Grep for team names, win counts, records across all HTML files
- Compare against `league_history.json` and `season_combined.json`
- Check Elo ratings, H2H records, all-time stats in `history.html`

**2.3 Validate `league_history.json` internal consistency**
- Check H2H symmetry (A's wins vs B = B's losses vs A)
- Check Elo bounds (reasonable range)
- Check franchise stats sum correctly across seasons
- Verify championship counts match bracket files

---

### Phase 3: Build Automated Render Script (WORKFLOW)
- Create `scripts/render_week.py` — deterministic HTML templating
- Takes `weekN_content.json` + template → `weekN.html`
- No AI needed for rendering, saves tokens and time
- Test with existing weeks 1-5 to verify output matches

---

### Phase 4: Retroactive Week 1-5 Updates (PENDING)
- Awaiting clarification on what "new elements" week 6 introduces
- Once defined, apply those elements retroactively to weeks 1-5
- Re-render all weeks through the new automated pipeline

---

### Phase 5: Ongoing Workflow Optimization (FUTURE)
- Add schema validation to `fetch_sleeper.py`
- Add data drift detection between fetches
- Build prerequisite checker for `/write-week`
- Consider making championship/stats data dynamic instead of hardcoded
