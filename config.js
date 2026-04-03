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
  name: "The Jailyard", // Displayed in nav, hero, footer
  tagline: "Dynasty League HQ", // Shown in the browser tab alongside the name
  established: 2022, // First season year
  teamCount: 12, // Number of franchises
  description:
    "A 12-team dynasty fantasy football league since 2022. Season recaps, all-time records, Elo ratings, power rankings, and full league history.",

  // ─── Sleeper Integration ───────────────────────────────────
  // Map each season year to its Sleeper league ID.
  // Find yours at: https://sleeper.com → your league → Settings → General → League ID
  sleeperLeagueIds: {
    2022: "792314138780090368",
    2023: "918335334096846848",
    2024: "1048889097223266304",
    2025: "1180228858937966592",
    2026: "1312884727480352768", // offseason / upcoming
  },

  // The current or most recent completed season
  currentSeason: 2025,

  // All seasons that should be selectable in the Season Hub dropdown
  availableSeasons: [2022, 2023, 2024, 2025],

  // ─── Theme Colours ─────────────────────────────────────────
  // Override the CSS custom properties in :root.
  // Set to null to use the defaults defined in each page's <style> block.
  colors: {
    accent: null, // default: #8b5cf6  (purple)
    accent2: null, // default: #ec4899  (pink)
    bg: null, // default: #0b0d10
    fg: null, // default: #e8ecf0
  },

  // ─── Navigation ────────────────────────────────────────────
  // Core pages appear in the top nav bar.
  // Weekly columns (group:'columns') appear in the Season Strip instead.
  totalWeeks: 18,
  pages: [
    { label: "League Bible", href: "history.html" },
    { label: "Season Hub", href: "season.html" },
    { label: "Rankings", href: "preseason.html" },
    { label: "Power Rankings", href: "power-rankings.html" },
    { label: "Draft", href: "draft.html" },
    { label: "Trades", href: "trades.html" },
    {
      label: "Week 1",
      href: "week1.html",
      group: "columns",
      subtitle: "Opening week chaos sets the tone",
    },
    {
      label: "Week 2",
      href: "week2.html",
      group: "columns",
      subtitle: "Early risers and first-week frauds",
    },
    {
      label: "Week 3",
      href: "week3.html",
      group: "columns",
      subtitle: "The cream separates from the chaos",
    },
    {
      label: "Week 4",
      href: "week4.html",
      group: "columns",
      subtitle: "Legion stands alone at 4-0",
    },
    {
      label: "Week 5",
      href: "week5.html",
      group: "columns",
      subtitle: "Five-way tie at 4-1 after the Legion falls",
    },
    {
      label: "Week 6",
      href: "week6.html",
      group: "columns",
      subtitle:
        "Kittler dethroned, trade bazaar erupts, Legion vs Ken-obi looms",
    },
    { label: "2026 Preview", href: "preseason-2026.html" },
  ],

  // ─── Fun facts (scrolling ticker on index.html) ────────────
  funFacts: [
    { emoji: "🏈", text: "4 seasons and counting since 2022" },
    { emoji: "🏆", text: "3 different champions in 4 years" },
    { emoji: "📊", text: "500+ players rostered across all teams" },
    {
      emoji: "🔥",
      text: "The longest win streak in league history spans multiple seasons",
    },
    { emoji: "💥", text: "The biggest blowout was over 80 points" },
    {
      emoji: "🎯",
      text: "Head-to-head rivalries tracked across every matchup",
    },
    {
      emoji: "📈",
      text: "Elo ratings update after every game with margin weighting",
    },
    { emoji: "🧠", text: "12 GMs battling for dynasty supremacy" },
    {
      emoji: "📋",
      text: "60 picks made in the 2025 rookie draft across 5 rounds",
    },
    {
      emoji: "🤝",
      text: "Seven first-round picks were traded on draft day alone",
    },
    { emoji: "⚡", text: "All data pulled live from the Sleeper API" },
    {
      emoji: "🎲",
      text: "Luck index measures who overperformed their expected wins",
    },
  ],

  // ─── Stats shown on index.html hero section ────────────────
  heroStats: [
    { target: 12, suffix: "", label: "Teams" },
    { target: 4, suffix: "", label: "Seasons" },
    { target: 3, suffix: "", label: "Champions" },
    { target: 60, suffix: "+", label: "Trades" },
    { target: 500, suffix: "+", label: "Rostered Players" },
  ],

  // ─── Copyright / Footer ────────────────────────────────────
  copyrightRange: "2022\u20132026", // en-dash between years
  copyrightEntity: "The Jailyard Dynasty League",
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
  if (c.accent) root.style.setProperty("--accent", c.accent);
  if (c.accent2) root.style.setProperty("--accent2", c.accent2);
  if (c.bg) root.style.setProperty("--bg", c.bg);
  if (c.fg) root.style.setProperty("--fg", c.fg);
}

/**
 * Inject the league name into any element with [data-league-name].
 */
function applyLeagueName() {
  document.querySelectorAll("[data-league-name]").forEach((el) => {
    el.textContent = LEAGUE_CONFIG.name;
  });
}

/**
 * Build a standard footer navigation block.
 * Returns an HTML string.
 */
function buildFooterNav() {
  const links = LEAGUE_CONFIG.pages
    .map(
      (p) =>
        `<a href="${p.href}" style="color:var(--muted);font-size:.85rem;">${p.label}</a>`,
    )
    .join("");
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
  const footer = document.querySelector("footer");
  if (footer) footer.innerHTML = buildFooterNav();
}

/**
 * Render the site-wide navigation: top nav bar + Season Strip + floating pill.
 * Populates <div id="site-nav"> on every page.
 * Note: innerHTML is used with trusted config data only (no user input).
 */
function renderNav() {
  var target = document.getElementById("site-nav");
  if (!target) return;

  var cfg = LEAGUE_CONFIG;
  var corePages = cfg.pages.filter(function (p) {
    return !p.group;
  });
  var columns = cfg.pages.filter(function (p) {
    return p.group === "columns";
  });
  var currentPath = window.location.pathname.split("/").pop() || "index.html";

  // Find the latest (highest-numbered) column
  var latestCol = columns.length ? columns[columns.length - 1] : null;
  var latestWeek = columns.length;
  var isOnLatest = latestCol && currentPath === latestCol.href;

  // ── Inject nav CSS into <head> ──
  if (!document.getElementById("nav-styles")) {
    var style = document.createElement("style");
    style.id = "nav-styles";
    style.textContent = [
      ".site-topnav{position:fixed;top:0;left:0;right:0;z-index:100;padding:.6rem 1.5rem;display:flex;align-items:center;justify-content:space-between;background:rgba(11,13,16,0.6);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border-bottom:1px solid transparent;transition:border-color .3s,background .3s;}",
      ".site-topnav.scrolled{border-bottom-color:var(--border);background:rgba(11,13,16,0.85);}",
      ".site-topnav .nav-brand{font-weight:700;letter-spacing:.04em;font-size:1rem;color:var(--fg);text-decoration:none;}",
      ".site-topnav .nav-pills{display:flex;gap:.4rem;align-items:center;}",
      ".site-topnav .nav-pills a{padding:.3rem .65rem;border-radius:999px;font-size:.82rem;color:var(--muted);transition:color .2s,background .2s;text-decoration:none;}",
      ".site-topnav .nav-pills a:hover,.site-topnav .nav-pills a.active{color:var(--fg);background:rgba(255,255,255,0.06);}",
      ".site-topnav .nav-right{display:flex;align-items:center;gap:.5rem;}",
      ".site-topnav .nav-theme{cursor:pointer;padding:.3rem .65rem;border:1px solid var(--border);border-radius:999px;background:rgba(255,255,255,0.05);font-size:.78rem;color:var(--muted);font-family:inherit;transition:color .2s,background .2s;}",
      ".site-topnav .nav-theme:hover{color:var(--fg);background:rgba(255,255,255,0.08);}",
      ".site-topnav .nav-hamburger{display:none;background:none;border:none;cursor:pointer;padding:.4rem;color:var(--muted);transition:color .2s;}",
      ".site-topnav .nav-hamburger:hover,.site-topnav .nav-hamburger:focus-visible{color:var(--fg);}",
      ".site-topnav .nav-hamburger svg{width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:2;}",
      ".season-strip{position:fixed;top:42px;left:0;right:0;z-index:99;display:flex;align-items:center;justify-content:center;padding:.4rem 1.5rem;background:rgba(11,13,16,0.5);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-bottom:1px solid var(--border);}",
      ".strip-track{display:flex;align-items:center;position:relative;width:100%;max-width:800px;}",
      ".strip-spacer{flex:1;min-width:0;}",
      ".strip-line{position:absolute;top:50%;left:0;right:0;height:2px;transform:translateY(-50%);background:var(--border);}",
      ".strip-line-fill{position:absolute;top:50%;left:0;height:2px;transform:translateY(-50%);background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .6s cubic-bezier(.17,.67,.24,1);}",
      ".strip-node{position:relative;z-index:1;width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-size:.7rem;font-weight:700;border:2px solid var(--accent);background:var(--bg);color:var(--fg);cursor:pointer;transition:all .2s ease;flex-shrink:0;text-decoration:none;}",
      ".strip-node:hover{transform:scale(1.2);border-color:var(--accent2);box-shadow:0 0 12px rgba(139,92,246,0.4);text-decoration:none;color:var(--fg);}",
      ".strip-node.active{background:var(--accent);color:#fff;border-color:var(--accent);}",
      ".strip-node.latest{width:32px;height:32px;animation:node-pulse 2s ease-in-out infinite;}",
      '.strip-node.latest::after{content:"";position:absolute;top:-3px;right:-3px;width:8px;height:8px;border-radius:50%;background:var(--accent2);box-shadow:0 0 6px var(--accent2);}',
      ".strip-node.ghost{width:12px;height:12px;border:1.5px solid rgba(122,129,148,0.3);background:transparent;cursor:default;font-size:0;}",
      ".strip-node.ghost:hover{transform:none;box-shadow:none;border-color:rgba(122,129,148,0.3);}",
      "@keyframes node-pulse{0%,100%{box-shadow:0 0 0 0 rgba(139,92,246,0.4);}50%{box-shadow:0 0 0 8px rgba(139,92,246,0);}}",
      ".strip-tooltip{position:absolute;bottom:calc(100% + 12px);left:50%;transform:translateX(-50%) translateY(8px);opacity:0;pointer-events:none;transition:opacity .2s,transform .2s;z-index:100;min-width:220px;padding:.8rem 1rem;background:rgba(15,17,22,0.92);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid var(--border);border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.4);text-align:left;}",
      ".strip-tooltip.visible{opacity:1;transform:translateX(-50%) translateY(0);pointer-events:auto;}",
      '.strip-tooltip::after{content:"";position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:rgba(15,17,22,0.92);}',
      ".strip-tooltip .tt-week{font-size:.7rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);margin-bottom:.3rem;}",
      ".strip-tooltip .tt-subtitle{font-size:.85rem;color:var(--fg);line-height:1.4;margin-bottom:.5rem;}",
      ".strip-tooltip .tt-link{font-size:.8rem;color:var(--accent2);font-weight:600;text-decoration:none;}",
      ".strip-tooltip .tt-link:hover{text-decoration:underline;}",
      ".latest-pill{position:fixed;bottom:1.5rem;right:1.5rem;z-index:90;display:inline-flex;align-items:center;gap:.5rem;padding:.6rem 1.2rem;background:rgba(15,17,22,0.85);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid var(--border);border-radius:999px;color:var(--fg);font-weight:600;font-size:.85rem;text-decoration:none;box-shadow:0 4px 20px rgba(0,0,0,0.3);animation:pill-enter .5s cubic-bezier(.17,.67,.24,1) .5s both;transition:transform .2s,box-shadow .2s;}",
      ".latest-pill:hover{transform:translateY(-3px);box-shadow:0 8px 30px rgba(139,92,246,0.3);text-decoration:none;color:var(--fg);}",
      ".latest-pill .pill-dot{width:8px;height:8px;border-radius:50%;background:var(--accent2);animation:pulse 2s ease-in-out infinite;}",
      "@keyframes pill-enter{from{opacity:0;transform:translateY(20px);}to{opacity:1;transform:translateY(0);}}",
      ".nav-body-pad{padding-top:80px;}",
      "@media(max-width:768px){",
      "  .site-topnav .nav-pills{display:none;position:absolute;top:100%;left:0;right:0;flex-direction:column;padding:.5rem 1rem 1rem;background:rgba(11,13,16,0.95);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);gap:0;}",
      "  .site-topnav .nav-pills.open{display:flex;}",
      "  .site-topnav .nav-pills a{padding:.65rem .75rem;}",
      "  .site-topnav .nav-hamburger{display:block;}",
      "  .season-strip{overflow-x:auto;justify-content:flex-start;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;scrollbar-width:none;}",
      "  .season-strip::-webkit-scrollbar{display:none;}",
      "  .strip-node{scroll-snap-align:center;}",
      "  .strip-tooltip{position:fixed;bottom:0;left:0;right:0;top:auto;transform:none;border-radius:16px 16px 0 0;min-width:auto;}",
      "  .strip-tooltip.visible{transform:none;}",
      "  .strip-tooltip::after{display:none;}",
      "  .latest-pill{right:auto;left:50%;transform:translateX(-50%);bottom:1rem;}",
      "  .latest-pill:hover{transform:translateX(-50%) translateY(-3px);}",
      "}",
      ".light .site-topnav{background:rgba(247,249,252,0.6);}",
      ".light .site-topnav.scrolled{background:rgba(247,249,252,0.85);}",
      ".light .season-strip{background:rgba(247,249,252,0.5);}",
      ".light .strip-node{background:var(--bg);}",
      ".light .strip-node.active{background:var(--accent);color:#fff;}",
      ".light .strip-tooltip{background:rgba(247,249,252,0.95);}",
      ".light .latest-pill{background:rgba(247,249,252,0.9);}",
    ].join("\n");
    document.head.appendChild(style);
  }

  // ── Build top nav HTML ──
  var pillsHtml = corePages
    .map(function (p) {
      var cls = currentPath === p.href ? ' class="active"' : "";
      return '<a href="' + p.href + '"' + cls + ">" + p.label + "</a>";
    })
    .join("");

  // ── Build Season Strip nodes ──
  var nodesHtml = "";
  for (var w = 1; w <= cfg.totalWeeks; w++) {
    var col = null;
    for (var ci = 0; ci < columns.length; ci++) {
      if (columns[ci].label === "Week " + w) {
        col = columns[ci];
        break;
      }
    }
    if (col) {
      var isActive = currentPath === col.href;
      var isLatest = col === latestCol;
      var cls = "strip-node";
      if (isActive) cls += " active";
      if (isLatest) cls += " latest";
      nodesHtml +=
        '<a href="' +
        col.href +
        '" class="' +
        cls +
        '" data-week="' +
        w +
        '" data-subtitle="' +
        (col.subtitle || "") +
        '">' +
        w +
        "</a>";
    } else {
      nodesHtml +=
        '<span class="strip-node ghost" data-week="' + w + '"></span>';
    }
    if (w < cfg.totalWeeks) nodesHtml += '<span class="strip-spacer"></span>';
  }
  var fillPct =
    cfg.totalWeeks > 1 ? ((latestWeek - 1) / (cfg.totalWeeks - 1)) * 100 : 0;

  // ── Build floating pill ──
  var pillHtml = "";
  if (latestCol && !isOnLatest) {
    pillHtml =
      '<a href="' +
      latestCol.href +
      '" class="latest-pill"><span class="pill-dot"></span>' +
      latestCol.label +
      "</a>";
  }

  // ── Assemble (trusted config data only) ──
  target.insertAdjacentHTML(
    "beforeend",
    '<nav class="site-topnav" id="siteTopnav">' +
      '  <a href="index.html" class="nav-brand">' +
      cfg.name +
      "</a>" +
      '  <div class="nav-pills" id="navPills">' +
      pillsHtml +
      "</div>" +
      '  <div class="nav-right">' +
      '    <button class="nav-theme" id="navThemeToggle">Theme</button>' +
      '    <button class="nav-hamburger" id="navHamburger" aria-label="Toggle navigation menu" aria-expanded="false">' +
      '      <svg viewBox="0 0 24 24"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>' +
      "    </button>" +
      "  </div>" +
      "</nav>" +
      '<div class="season-strip" id="seasonStrip">' +
      '  <div class="strip-track">' +
      '    <div class="strip-line"></div>' +
      '    <div class="strip-line-fill" style="width:' +
      fillPct +
      '%"></div>' +
      nodesHtml +
      "  </div>" +
      "</div>" +
      pillHtml,
  );

  // Add body padding for fixed nav + strip
  document.body.classList.add("nav-body-pad");

  // ── Tooltip ──
  var tooltip = document.createElement("div");
  tooltip.className = "strip-tooltip";
  tooltip.insertAdjacentHTML(
    "beforeend",
    '<div class="tt-week"></div><div class="tt-subtitle"></div><a class="tt-link" href="#">Read &rarr;</a>',
  );
  document.body.appendChild(tooltip);

  var activeTooltipNode = null;
  function showTooltip(node) {
    var week = node.dataset.week;
    var sub = node.dataset.subtitle;
    if (!sub) return;
    tooltip.querySelector(".tt-week").textContent = "Week " + week;
    tooltip.querySelector(".tt-subtitle").textContent = sub;
    tooltip.querySelector(".tt-link").href = node.href;
    var isMobile = window.innerWidth <= 768;
    if (!isMobile) {
      var rect = node.getBoundingClientRect();
      tooltip.style.position = "absolute";
      tooltip.style.left = rect.left + rect.width / 2 + "px";
      tooltip.style.bottom = "";
      tooltip.style.top = rect.top - 12 + window.scrollY + "px";
      tooltip.style.transform = "translateX(-50%) translateY(-100%)";
    }
    tooltip.classList.add("visible");
    activeTooltipNode = node;
  }
  function hideTooltip() {
    tooltip.classList.remove("visible");
    activeTooltipNode = null;
  }

  // Desktop: hover
  document.querySelectorAll(".strip-node:not(.ghost)").forEach(function (node) {
    node.addEventListener("mouseenter", function () {
      showTooltip(node);
    });
    node.addEventListener("mouseleave", hideTooltip);
  });

  // Mobile: tap to show tooltip, second tap navigates
  if ("ontouchstart" in window) {
    document
      .querySelectorAll(".strip-node:not(.ghost)")
      .forEach(function (node) {
        node.addEventListener("click", function (e) {
          if (activeTooltipNode !== node) {
            e.preventDefault();
            showTooltip(node);
          }
        });
      });
  }

  // Dismiss tooltip on outside click or Escape
  document.addEventListener("click", function (e) {
    if (!e.target.closest(".strip-node") && !e.target.closest(".strip-tooltip"))
      hideTooltip();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") hideTooltip();
  });

  // ── Scroll handler ──
  var topnav = document.getElementById("siteTopnav");
  window.addEventListener(
    "scroll",
    function () {
      topnav.classList.toggle("scrolled", window.scrollY > 40);
    },
    { passive: true },
  );

  // ── Theme toggle ──
  document
    .getElementById("navThemeToggle")
    .addEventListener("click", function () {
      document.documentElement.classList.toggle("light");
      window.dispatchEvent(new Event("themechange"));
    });

  // ── Hamburger ──
  document
    .getElementById("navHamburger")
    .addEventListener("click", function () {
      var pills = document.getElementById("navPills");
      pills.classList.toggle("open");
      this.setAttribute("aria-expanded", pills.classList.contains("open"));
    });

  // ── Mobile: auto-scroll strip to latest week ──
  if (window.innerWidth <= 768 && latestCol) {
    var strip = document.getElementById("seasonStrip");
    var latestNode =
      strip.querySelector(".strip-node.latest") ||
      strip.querySelector(".strip-node.active");
    if (latestNode) {
      requestAnimationFrame(function () {
        latestNode.scrollIntoView({ inline: "center", block: "nearest" });
      });
    }
  }
}

/**
 * Apply all config-driven changes to the current page.
 * Call once from each page's <script> block.
 */
function applyConfig() {
  renderNav();
  applyConfigColors();
  applyLeagueName();
  renderConfigFooter();
}

// ═══════════════════════════════════════════════════════════════
// SHARED UTILITIES — used across multiple pages
// ═══════════════════════════════════════════════════════════════

/**
 * Replace {{media:slotId}} tokens with video elements from a media cache.
 * @param {string} text - Text containing media tokens.
 * @param {Object} cache - Map of slotId → {width, height, poster_url, mp4_url, alt_text}.
 * @returns {string} Text with tokens replaced by <figure>/<video> HTML.
 */
function processMediaTokens(text, cache) {
  return text.replace(/\{\{media:([^}]+)\}\}/g, function (_, slotId) {
    var slot = cache[slotId];
    if (!slot) return "";
    return (
      '<figure class="media-slot" id="media-' +
      slotId +
      '">' +
      "<video loop muted playsinline" +
      ' width="' +
      slot.width +
      '" height="' +
      slot.height +
      '"' +
      ' poster="' +
      slot.poster_url +
      '" preload="none"' +
      ' aria-label="' +
      slot.alt_text.replace(/"/g, "&quot;") +
      '">' +
      '<source data-src="' +
      slot.mp4_url +
      '" type="video/mp4">' +
      "</video></figure>"
    );
  });
}

/**
 * Convert a point spread to an implied win probability.
 * @param {number} spread - Point spread (positive = favored).
 * @returns {number} Win probability between 0 and 1.
 */
function spreadToProb(spread) {
  return 1 / (1 + Math.pow(10, -spread / 7));
}

/**
 * Parse a movement string like "up_3" into display format.
 * @param {string} movement - One of "steady", "up_N", "down_N".
 * @returns {{cls: string, text: string}} CSS class and display text.
 */
function parseMovement(movement) {
  if (movement === "steady") return { cls: "steady", text: "\u2014" };
  var parts = movement.split("_");
  var dir = parts[0];
  var n = parts[1] || "1";
  if (dir === "up") return { cls: "up", text: "\u2191" + n };
  return { cls: "down", text: "\u2193" + n };
}

/**
 * Generate a deterministic gradient from initials (for avatars).
 * @param {string} initials - Two-character string.
 * @returns {string} CSS linear-gradient value.
 */
function gradientFor(initials) {
  var seed = initials.charCodeAt(0) + initials.charCodeAt(1);
  var h1 = seed % 360;
  var h2 = (h1 + 60) % 360;
  return (
    "linear-gradient(135deg, hsl(" + h1 + ",80%,55%), hsl(" + h2 + ",80%,55%))"
  );
}
