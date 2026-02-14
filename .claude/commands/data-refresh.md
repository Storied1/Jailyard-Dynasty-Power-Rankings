# Data Refresh — Jailyard

Refresh the Sleeper API data. Use when season data needs updating.

## Steps

### 1. Pre-check
- Verify `fetch_sleeper.py` exists and has valid Python syntax
- Check current state of `data/` directory

### 2. Fetch Data
If $ARGUMENTS contains a specific season (e.g., "2025"):
```bash
python3 fetch_sleeper.py --season $YEAR
```

If $ARGUMENTS contains "all" or no arguments:
```bash
python3 fetch_sleeper.py --all
```

### 3. Verify Output
- Check `data/` directory was created/updated
- List all JSON files and their sizes
- Verify `season_combined.json` exists for each fetched season
- If `--all` was used, verify `data/league_history.json` exists

### 4. Quick Validation
- Check that `season_combined.json` has the expected structure:
  - `season` field matches year
  - `roster_map` has 12 entries
  - `weeks` array has at least 1 entry
- Report total matchups, teams, and weeks found

### 5. Git Status
- Show which files changed
- Suggest commit message: `Update Sleeper data (YYYY-MM-DD)`
- Remind: do NOT commit `data/players.json` (gitignored, ~5MB)

## Output

```
DATA REFRESH RESULTS
====================
Seasons fetched: [list]
Files updated:   [list]
Total size:      X MB
Validation:      PASS / FAIL

Suggested commit:
  git add data/
  git commit -m "Update Sleeper data (YYYY-MM-DD)"
  git push
```
