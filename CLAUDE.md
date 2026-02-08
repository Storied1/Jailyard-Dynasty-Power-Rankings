# CLAUDE.md

Guide for AI assistants working on The Jailyard Dynasty Power Rankings codebase.

## Project Overview

A static website for "The Jailyard" — a 12-team fantasy football dynasty league (2025 season). Provides preseason power rankings, team rosters, data visualizations, and weekly preview columns. Entirely client-side with no backend, no build process, and no external dependencies.

## Repository Structure

```
/
├── index.html          # Landing page — hero + nav cards linking to subpages
├── preseason.html      # Main rankings page (~950 lines) — data, charts, team cards
├── week1.html          # Week 1 preview column — essay, mailbag, game picks
├── bg_hero.png         # Hero background image
├── icon_preseason.png  # Card icon for preseason link
├── icon_week.png       # Card icon for week preview link
├── dontuse             # Archived/legacy HTML version (do not modify)
├── dontuse2            # Archived/legacy HTML version (do not modify)
├── dontusedraft3       # Archived/legacy HTML version (do not modify)
└── README.md           # Brief project description
```

**Note:** `index.html` references images via `assets/` path prefix (e.g., `assets/bg_hero.png`) but images are at the root. This is a known path discrepancy — the site may be deployed behind a server that resolves these, or this may need to be fixed.

## Technology Stack

- **HTML5 / CSS3 / Vanilla JavaScript** — no frameworks, no libraries, no npm
- **CSS custom properties** for theming (dark mode default, light mode toggle)
- **Canvas 2D API** for data visualization charts (scatter, stacked bar, schedule analysis, titles)
- **Intersection Observer API** for scroll-triggered animations and nav highlighting
- **CSS Grid / Flexbox** for responsive layouts
- **Glassmorphic design** with `backdrop-filter`, gradients, and subtle transparency

## Architecture

### Data Model

All league data lives in `preseason.html` as inline JavaScript objects:

```javascript
const league = {
  season: 2025,
  teams: [ /* 12 team objects with rosters, records, picks */ ],
  awards: [ /* superlative awards */ ]
};

const extras = {
  "Team Name": { weeklyPoints, scheduleRank, essay }
};
```

Each team object contains: `name`, `rank`, `tier`, `record`, `playoffHistory`, `roster` (array of player objects), `draftPicks`, `roast`, and `blurb`.

### Rendering Pattern

Data-driven DOM construction — JavaScript iterates over `league.teams` and builds HTML elements programmatically. No templating engine.

```javascript
league.teams.forEach(team => {
  // Create card element
  // Populate with team data
  // Add event listeners
  // Append to DOM
});
```

### Page Architecture

| Page | Role | Key Features |
|------|------|-------------|
| `index.html` | Entry point / hub | Parallax hero, CTA cards |
| `preseason.html` | Main application | Sortable table, expandable team cards, Canvas charts, scroll animations |
| `week1.html` | Weekly column | Embeds preseason as iframe, adds essay/mailbag/picks |

## Code Conventions

### CSS
- **kebab-case** class names (e.g., `.hero-content`, `.team-meta`)
- **BEM-like** naming for hero section (`.hero__bg`, `.hero__content`, `.hero__title`)
- CSS variables defined in `:root` for consistent theming
- Inline `<style>` blocks — no external stylesheets
- `clamp()` for responsive typography
- Mobile-first responsive design

### JavaScript
- **camelCase** for variables and functions
- All scripts are inline `<script>` blocks at the bottom of each HTML file
- Functional style with `forEach`, `map`, `sort` over arrays
- Helper functions like `idFromName()` for slug generation
- No module system — everything is in global scope

### Naming
- Team names use title case, some with special characters (en-dash: "Ken-obi")
- HTML IDs derived from team names via `idFromName()` helper (lowercase, hyphenated)

## Development Workflow

### Running Locally

No build step required. Open any HTML file directly in a browser:

```bash
# Using Python's built-in server
python3 -m http.server 8000

# Or just open the file directly
open index.html
```

### No Build Tools

- No `package.json`, no npm dependencies
- No TypeScript, no transpilation
- No bundler (webpack, vite, etc.)
- No linter or formatter configured
- No test framework

### Testing

No automated tests exist. Changes should be verified by:
1. Opening each modified page in a browser
2. Checking responsive behavior at different viewport widths
3. Verifying Canvas charts render correctly
4. Testing dark/light theme toggle
5. Confirming scroll animations and Intersection Observer behavior

## Key Considerations for AI Assistants

### Do
- Keep all CSS and JS inline within HTML files (this is the project convention)
- Maintain the existing glassmorphic dark-theme aesthetic
- Preserve the data structure format when adding teams or updating rosters
- Test that Canvas charts still render after data changes
- Keep the zero-dependency approach — don't introduce npm packages or frameworks

### Don't
- Modify files prefixed with `dontuse` — these are archived legacy versions
- Add external CSS/JS files unless explicitly requested
- Introduce a build system unless the project owner requests it
- Change the data schema without updating all rendering code that consumes it

### Common Tasks
- **Adding a new week's column:** Follow `week1.html` pattern — create `week2.html` with updated essays, picks, and game data
- **Updating rankings:** Modify the `league.teams` array in `preseason.html`, adjust `rank` values and re-sort
- **Adding a team's data:** Add entries to both `league.teams` and `extras` objects
- **Updating rosters:** Modify `roster` arrays within team objects in `preseason.html`
- **Adding new charts:** Use the Canvas 2D API pattern established in `preseason.html` with `devicePixelRatio` handling

## Git Conventions

- Repository hosted on GitHub as `Storied1/Jailyard-Dynasty-Power-Rankings`
- Default branch: `main`
- Commits have been informal / descriptive (e.g., "Add files via upload", "Updated site")
- No branch protection or CI/CD pipelines configured
