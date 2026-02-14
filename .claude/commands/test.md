# Test — Jailyard

Run validation checks on the codebase. No test framework exists — this command IS the test suite.

## Automated Checks

### 1. HTML Validation
For each .html file (excluding dontuse*):
- Verify `<!DOCTYPE html>` present
- Verify `<meta charset="utf-8">` present
- Verify `<meta name="viewport">` present
- Verify `<title>` is not empty
- Verify no unclosed tags (search for common issues)
- Verify all internal `href` links point to files that exist

### 2. CSS Variable Consistency
- Extract `:root` variables from each HTML file
- Flag any file using `--accent-2` (should be `--accent2`)
- Flag any hardcoded color values in new CSS (hex, rgb, hsl not inside `:root`)

### 3. Navigation Cross-Links
For each HTML file, extract all `href="*.html"` links.
Verify every page links to: `index.html`, `history.html`, `season.html`, `preseason.html`, `week1.html`
Report any missing links.

### 4. Data File Check
- Check if `data/` directory exists
- If yes: list JSON files and their sizes
- If no: warn that pages will fall back to live API

### 5. JavaScript Scan
For each HTML file:
- Count empty catch blocks: `catch(e) {}` or `catch(e){}` or similar
- Count `console.log` statements (should be 0 in production)
- Check for `var ` usage (should use const/let)
- Check for deprecated `keyCode` usage

### 6. Python Script Check
- Verify `fetch_sleeper.py` has valid Python syntax: `python3 -c "import ast; ast.parse(open('fetch_sleeper.py').read())"`
- Verify all LEAGUE_IDS years are sequential and reasonable

### 7. Git Status
- Check for untracked files that should be committed
- Check for large files (>1MB) that might need gitignoring
- Verify `.gitignore` includes `data/players.json`

## Output

```
JAILYARD TEST RESULTS
=====================
HTML Validation:  X/N pass
CSS Consistency:  X issues
Nav Cross-Links:  X/N complete
Data Files:       Present / Missing
JS Quality:       X warnings
Python Syntax:    Pass / Fail
Git Status:       Clean / X issues

OVERALL: PASS / FAIL (N issues)
```

If $ARGUMENTS contains "fix", also apply automatic fixes for:
- `--accent-2` → `--accent2` replacement
- Empty `catch(e) {}` → `catch(e) { console.error('Error:', e); }`
- `var ` → `let ` (where safe)
