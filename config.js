/**
 * League Configuration — The Jailyard Dynasty League
 * ===================================================
 *
 * This is the ONLY file you need to edit to rebrand this site for your own
 * dynasty league.  Every page reads from this config at runtime to populate
 * the league name, accent colours, Sleeper IDs, navigation links, and more.
 *
 * Fork the repo → edit this file → deploy.  That's it.
 */

const LEAGUE_CONFIG = {

  // ─── Branding ──────────────────────────────────────────────
  name: 'The Jailyard',                       // Displayed in nav, hero, footer
  tagline: 'Dynasty League HQ',               // Shown in the browser tab alongside the name
  established: 2022,                           // First season year
  teamCount: 12,                               // Number of franchises
  description: 'A 12-team dynasty fantasy football league since 2022. Season recaps, all-time records, Elo ratings, power rankings, and full league history.',

  // ─── Sleeper Integration ───────────────────────────────────
  // Map each season year to its Sleeper league ID.
  // Find yours at: https://sleeper.com → your league → Settings → General → League ID
  sleeperLeagueIds: {
    2022: '792314138780090368',
    2023: '918335334096846848',
    2024: '1048889097223266304',
    2025: '1180228858937966592',
    2026: '1312884727480352768',   // offseason / upcoming
  },

  // The current or most recent completed season
  currentSeason: 2025,

  // All seasons that should be selectable in the Season Hub dropdown
  availableSeasons: [2022, 2023, 2024, 2025],

  // ─── Theme Colours ─────────────────────────────────────────
  // Override the CSS custom properties in :root.
  // Set to null to use the defaults defined in each page's <style> block.
  colors: {
    accent:  null,   // default: #8b5cf6  (purple)
    accent2: null,   // default: #ec4899  (pink)
    bg:      null,   // default: #0b0d10
    fg:      null,   // default: #e8ecf0
  },

  // ─── Navigation ────────────────────────────────────────────
  // Define which pages appear in the navbar and footer.
  // Each entry: { label, href, icon (optional SVG for index cards) }
  pages: [
    { label: 'League Bible',  href: 'history.html'   },
    { label: 'Season Hub',    href: 'season.html'     },
    { label: 'Rankings',      href: 'preseason.html'  },
    { label: 'Power Rankings', href: 'power-rankings.html' },
    { label: 'Draft',         href: 'draft.html'      },
    { label: 'Trades',        href: 'trades.html'     },
    { label: 'Week 1',        href: 'week1.html'      },
    { label: 'Week 2',        href: 'week2.html'      },
    { label: 'Week 3',        href: 'week3.html'      },
    { label: '2026 Preview',  href: 'preseason-2026.html' },
  ],

  // ─── Fun facts (scrolling ticker on index.html) ────────────
  funFacts: [
    { emoji: '🏈', text: '4 seasons and counting since 2022' },
    { emoji: '🏆', text: '3 different champions in 4 years' },
    { emoji: '📊', text: '500+ players rostered across all teams' },
    { emoji: '🔥', text: 'The longest win streak in league history spans multiple seasons' },
    { emoji: '💥', text: 'The biggest blowout was over 80 points' },
    { emoji: '🎯', text: 'Head-to-head rivalries tracked across every matchup' },
    { emoji: '📈', text: 'Elo ratings update after every game with margin weighting' },
    { emoji: '🧠', text: '12 GMs battling for dynasty supremacy' },
    { emoji: '📋', text: '60 picks made in the 2025 rookie draft across 5 rounds' },
    { emoji: '🤝', text: 'Seven first-round picks were traded on draft day alone' },
    { emoji: '⚡', text: 'All data pulled live from the Sleeper API' },
    { emoji: '🎲', text: 'Luck index measures who overperformed their expected wins' },
  ],

  // ─── Stats shown on index.html hero section ────────────────
  heroStats: [
    { target: 12,  suffix: '',  label: 'Teams' },
    { target: 4,   suffix: '',  label: 'Seasons' },
    { target: 3,   suffix: '',  label: 'Champions' },
    { target: 60,  suffix: '+', label: 'Trades' },
    { target: 500, suffix: '+', label: 'Rostered Players' },
  ],

  // ─── Copyright / Footer ────────────────────────────────────
  copyrightRange: '2022\u20132026',            // en-dash between years
  copyrightEntity: 'The Jailyard Dynasty League',
};


// ═══════════════════════════════════════════════════════════════
// HELPERS — used by all pages that load this script
// ═══════════════════════════════════════════════════════════════

/**
 * Apply custom theme colours from config to the document root.
 */
function applyConfigColors() {
  const c = LEAGUE_CONFIG.colors;
  if (!c) return;
  const root = document.documentElement;
  if (c.accent)  root.style.setProperty('--accent', c.accent);
  if (c.accent2) root.style.setProperty('--accent2', c.accent2);
  if (c.bg)      root.style.setProperty('--bg', c.bg);
  if (c.fg)      root.style.setProperty('--fg', c.fg);
}

/**
 * Inject the league name into any element with [data-league-name].
 */
function applyLeagueName() {
  document.querySelectorAll('[data-league-name]').forEach(el => {
    el.textContent = LEAGUE_CONFIG.name;
  });
}

/**
 * Build a standard footer navigation block.
 * Returns an HTML string.
 */
function buildFooterNav() {
  const links = LEAGUE_CONFIG.pages.map(p =>
    `<a href="${p.href}" style="color:var(--muted);font-size:.85rem;">${p.label}</a>`
  ).join('');
  return `
    <div style="font-weight:700;font-size:1rem;color:var(--fg);margin-bottom:.4rem;" data-league-name>${LEAGUE_CONFIG.name}</div>
    <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:.8rem;margin-bottom:1rem;">
      <a href="index.html" style="color:var(--muted);font-size:.85rem;">Home</a>
      ${links}
    </div>
    &copy; ${LEAGUE_CONFIG.copyrightRange} ${LEAGUE_CONFIG.copyrightEntity}. All rights reserved.
  `;
}

/**
 * Auto-populate the first <footer> on the page with the standard nav.
 * Call this at the end of any page script.
 */
function renderConfigFooter() {
  const footer = document.querySelector('footer');
  if (footer) footer.innerHTML = buildFooterNav();
}

/**
 * Apply all config-driven changes to the current page.
 * Call once from each page's <script> block.
 */
function applyConfig() {
  applyConfigColors();
  applyLeagueName();
  renderConfigFooter();
}
