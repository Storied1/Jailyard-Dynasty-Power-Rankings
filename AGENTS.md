# AGENTS.md — The Jailyard Dynasty Power Rankings

Operating guide for coding agents. `CLAUDE.md` is the full reference; this
file carries the invariants that must never be violated.

## What this is

Static site + editorial system for a 12-team Sleeper dynasty league. Pure
HTML/CSS/JS, everything inline, zero dependencies. Python data pipeline.
The written product: one long-form column edition per week of the season
(preseason first), power rankings as the recurring spine, bar defined in
`content/editorial-standard.md`.

## Invariants

- **Zero dependencies, everything inline.** No npm, no CDN, no frameworks.
  `config.js` is the only external file a page loads.
- **Glassmorphic dark theme with light toggle.** All colors via `:root` CSS
  variables (`--accent2`, not `--accent-2`). Canvas handles
  `devicePixelRatio`. No infinite shimmer/pulse/glow animations.
- **HTML is prettier-excluded** (`.prettierignore` = `*.html`). Never
  reformat the compact hand-maintained pages.
- **Editions cite only registered sources** (`content/writer-inputs.json`),
  each dated at or before the edition's cutoff. Chat quotes verbatim;
  numbers from the data packets; outside coverage cited with publication
  date. Edition bodies use only knowledge available at that point in the
  season (site chrome is present-day and exempt).
- **No machine tells in prose**: zero em dashes, no "it's not X, it's Y"
  constructions, prose never discusses how the column gets made.
- **Quality gates are binary.** `verify_week_content.py`,
  `verify_ranking_judgment.py`, `migration_census.py --all`, `/edit-week`,
  `/canon-check`: an error means REVISE/FAIL. Fix first, approve second.
- **Ranking orders are judgment, gated.** Published order matches a record
  passing `python scripts/verify_ranking_judgment.py --record <path>`
  (12 complete positions, non-arithmetic order, reasoned deviations,
  contender sanity, evidence breadth, resolving citations).
- **Temporal admission is exact-instant** via `shared.admissible`
  (tz-aware ≤ cutoff; malformed/naive/date-only rejected).
- **Append-only stores stay append-only**: `data/captures/2026/`,
  `content/seals/2026/`, `content/review-log.jsonl`. The frozen
  `source_policy_2026.v1.json` changes only by issuing a new version,
  never by editing.
- **Never `git add -f`** `private_captures/`, `private_bundles/`, or any
  gitignored path. Staging guard:
  `git diff --cached --name-only | grep -qE '^(private_captures|private_bundles)/'`
  must match nothing.
- **Chat provenance manifests are receipt-bound**: rewrite
  `content/chat/provenance.json` only via
  `generate_chat_provenance.py --write --receipt` after a green
  `--rebuild-check`.
- **Content fixes require HTML re-render**; a content JSON edit does not
  update its page.
- **After every push, watch CI keyed to HEAD's SHA** (see CLAUDE.md for the
  exact command). A push is not done until its run is green.

## Pipeline per edition

`/write-week N` → `/canon-check N` → `/edit-week N` → media commands if the
edition uses media → `/render-week N` → browser-verify (zero console errors)
→ commit. Preseason uses the `-preseason` variants and publishes first.

## Environment

Windows. Use `python`, not `python3`. `pip install -r requirements.txt` on
fresh clones. Tests: `python -m pytest scripts/tests/`. Local server:
`python -m http.server 8000`.
