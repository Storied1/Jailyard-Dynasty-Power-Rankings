# Jailyard Dynasty Power Rankings

Twelve managers enter, one champion leaves. We sorted the chaos with numbers, instinct and a healthy dose of locker-room humour.

A fully static website for **The Jailyard** — a 12-team dynasty fantasy football league. Preseason power rankings, weekly preview columns, a season hub with live Sleeper API data, an all-time league history bible, a rookie draft recap, and a trade tracker. Zero dependencies, no build step, no backend.

---

## Use This for Your Own League

This site is designed to be forked and rebranded for any Sleeper dynasty league. One config file controls everything.

### Quick Start

1. **Fork this repo** (or click "Use this template" on GitHub)
2. **Edit `config.js`** — this is the only file you *need* to change:
   - `name` — your league name
   - `sleeperLeagueIds` — your Sleeper league IDs (one per season)
   - `currentSeason` — the current or most recent season year
   - `availableSeasons` — which seasons to show in the Season Hub
   - `colors` — optional custom accent colours
   - `funFacts`, `heroStats` — customise the landing page content
3. **Fetch your data:**
   ```bash
   python3 fetch_sleeper.py --all
   ```
4. **Open `index.html`** in a browser. Done.

### Finding Your Sleeper League ID

1. Open [sleeper.com](https://sleeper.com) and go to your league
2. Click **Settings → General**
3. Your League ID is the long number at the top

If your league has carried over across seasons (dynasty), each season has a different League ID. You'll need one per season.

### Customising Content

| What | Where |
|------|-------|
| League name, colours, Sleeper IDs | `config.js` |
| Preseason rankings, rosters, essays | `preseason.html` (inline JS data) |
| Weekly preview columns | `week1.html` (duplicate for more weeks) |
| Rookie draft board and grades | `draft.html` (inline JS data) |
| Trade history and analysis | `trades.html` (inline JS data) |
| Season results, standings, charts | Auto-generated from Sleeper API via `season.html` |
| All-time records, Elo, H2H | Auto-generated from Sleeper API via `history.html` |

Pages that say "Auto-generated" pull data from `data/` (cached JSON) or fall back to live Sleeper API calls. The others use inline JavaScript data objects that you edit directly.

---

## Fetching Sleeper Data

```bash
# Fetch current season only
python3 fetch_sleeper.py

# Fetch a specific season
python3 fetch_sleeper.py --season 2024

# Fetch all seasons (skips already-cached past seasons)
python3 fetch_sleeper.py --all

# Force re-fetch everything, even cached seasons
python3 fetch_sleeper.py --all --force
```

Past seasons are immutable — once cached locally, `--all` skips them automatically to save API calls. Use `--force` when you need a clean refresh.

A GitHub Action (`.github/workflows/fetch-sleeper-data.yml`) can run this automatically every Sunday during the NFL season.

---

## Running Locally

No build tools, no npm, no dependencies. Just open the files:

```bash
# Option 1: Python's built-in server
python3 -m http.server 8000

# Option 2: Just open index.html directly
open index.html
```

---

## Pages

| Page | Description |
|------|-------------|
| `index.html` | Landing page with animated starfield, stats, and navigation cards |
| `preseason.html` | Preseason power rankings with sortable table, team cards, and Canvas charts |
| `season.html` | Season hub with weekly results, standings, and power rankings (Sleeper API) |
| `history.html` | League Bible with all-time records, franchise profiles, H2H matrix, and Elo chart |
| `draft.html` | Rookie draft recap with full draft board, grades, and storylines |
| `trades.html` | Trade tracker with timeline, season filter, and activity chart |
| `week1.html` | Week 1 preview column with essay, mailbag, and matchup predictions |

---

## Tech Stack

- HTML5 / CSS3 / Vanilla JavaScript — no frameworks, no libraries
- Canvas 2D API for data visualisation
- CSS custom properties for dark/light theming
- Intersection Observer for scroll animations
- View Transitions API for page navigation
- Glassmorphic design with backdrop-filter and gradients

---

## License

MIT — fork it, rebrand it, use it for your league.
