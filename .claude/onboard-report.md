# Project Health Card: Jailyard Dynasty Power Rankings

_Generated: 2026-06-03 — supersedes the 2026-04-07 card, which predated all of Phase 1a and is stale (it graded Testing "D/zero tests"; there are now 76)._

## Structure

Static fantasy-football dynasty site (12 teams, est. 2022) **+** a Python data/content pipeline. Zero frontend deps — 14 inline HTML pages, Canvas 2D charts, glassmorphic theme. Pipeline: 21 scripts, 9 pytest files (**76 tests**), 3 JSON schemas, **286 NFLGame entity files**. Two pipelines: (1) data (Sleeper API + nflreadpy → cached JSON → site), (2) AI content (Bill Simmons-style weekly columns from data + WhatsApp chat). Mid-rebuild: **Phase 1a (data foundation) at 7/10**, en route to a planned v2 design/content overhaul.

## Security & Quality — A

- **Critical: 0.** No secrets tracked (`git ls-files` clean), `.claude/settings.local.json` gitignored, zero frontend deps (no supply chain), gitleaks in pre-commit.
- **Warnings: 2.** (1) Empty `catch(){}` in 5 pages (`week3-6.html`, `preseason-2026.html`) swallow errors silently. (2) `innerHTML` with API data (trusted, unescaped).
- **Dependency vulns: 0** frontend. Python deps undocumented (no `requirements.txt`).
- **Top concern:** nothing security-critical. Biggest quality gap is the shared.py-dedup self-contradiction (Tech Debt #1).

## Tech Debt

**High:**

1. **shared.py dedup incomplete** — 4 scripts still define local `load_json`/`save_json` (`build_chat_context.py:46`, `analyze_chat.py:82`, `resolve_media.py:135`, `verify_week_content.py:92`), directly contradicting `CLAUDE.md:66` ("never define local copies — import from shared"). Phase 1a's new scripts comply; legacy ones never migrated.
2. **No `requirements.txt` / `pyproject.toml`** — `jsonschema`, `nflreadpy`, `polars`, `playwright` must be hand-installed on a fresh clone.

**Medium:**

3. **Momentum label-set drift** (`remediation_nits` #2, still open) — 3 truth sources (`extract_week_data.py:398` `EARLY_MOMENTUM_LABELS`, `verify_week_content.py:330` `VALID_MOMENTUM_LABELS`, `shared.py:312` `MOMENTUM_LABELS`) **+ a dead `MOMENTUM_LABELS` tuple** at `shared.py:312` missing `opening`/`early` (silent import trap).
4. **save_json↔prettier divergence** (`remediation_nits` #5) — `json.dump` expands arrays, prettier collapses them → diff noise on re-extract. New wrinkle this session: CRLF/LF manifest-byte-hash skew → latent Task-10 CI idempotency trap (fixed in `generate_expanded_week.py`; vault Pattern #22).

**Low:** matchup tie-order latent bug (`nits` #3), cosmetic stat-line minors (#6), early-sentinel docstring (#7), F20 home/away one-liner (#1 — now _unblocked_ by NFLGame `home_team`/`away_team`).

**Resolved since 2026-04-07:** dead config.js functions (now used 5–11×), `power-rankings.html` hardcoded IDs (now reads `LEAGUE_CONFIG`), zero tests (→76), missing schema validation (→3 schemas).

## Blind Spots

1. **No test CI.** The 76 tests run only locally (pre-commit). `.github/workflows/fetch-sleeper-data.yml` automates the data fetch but **not** the suite — nothing gates the remote on green. (Phase 1a Task 10 would add this.)
2. **Frontend is untested.** All 76 tests are data-pipeline. HTML rendering, `config.js`, theme toggle, Canvas charts: zero coverage. `config.js` is still a single point of failure for all 14 pages.
3. **Engineering health ≠ product health.** By Blake's own review (`feedback_v2_site_review`), the live product is still v1 "AI slop." Phase 1a builds the _data_ for v2; the design/content overhaul (`handoff_jailyard-v2-vision`, high/in-progress) is unstarted.

## Architecture Assessment

| Area             | Grade  | Δ vs 2026-04-07 | Notes                                                                |
| ---------------- | ------ | --------------- | -------------------------------------------------------------------- |
| Data pipeline    | **A-** | ↑ from B+       | nflreadpy single-source, NFLGame entity, schemas, canonical save     |
| Testing          | **B+** | ↑↑ from D       | 76 tests (was 0). Gaps: no CI, no frontend tests                     |
| Content pipeline | **A-** | =               | Voice bible, editor gate, verifier (Tier 1–3). Mature                |
| Documentation    | **A**  | =               | CLAUDE.md excellent (freshly fixed this session); minor stale counts |
| Security         | **A**  | =               | Zero deps, no secrets, gitleaks pre-commit                           |
| Frontend code    | **B-** | =               | Inline-by-design; per-page duplication, empty catches, untested      |
| Maintainability  | **B-** | ↑ from C+       | shared.py canonical for new code; legacy dedup + label drift remain  |

## Recommendations

1. **Finish Phase 1a** (Tasks 8–10) — the active, planned work; Task 10 adds the idempotency CI check.
2. **Add test CI** — run `pytest` in GitHub Actions (infra already exists). Makes 76 tests a real merge gate. ~20 min.
3. **Add `requirements.txt`** — trivial; fixes fresh-clone friction. ~5 min.
4. **Close `remediation_nits` #2 + dedup** — consolidate momentum labels into `shared.py`, delete the dead tuple, migrate the 4 legacy scripts to import shared's helpers (closes the CLAUDE.md contradiction).
5. **Then the v2 overhaul** (`handoff_jailyard-v2-vision`) — the data foundation is nearly ready to support it.

## CLAUDE.md Status

- **EXISTS** — among the best project docs; freshly corrected this session (nested `top_scorers` + expanded companion).
- **Stale counts:** line 11 "18 scripts" (now 21); line 173 "48 tests" (now 76).
- **Self-contradiction:** line 66 "never define local copies" vs the 4 scripts that still do (Tech Debt #1).

---

## Appendix: Jailyard vs blakebook (requested comparison)

**Different archetypes — not the same axis.** blakebook is Blake's process/tooling _lab_ (CLAUDE.md, hooks, bootstrap, skills, the architectural-patterns doc) — it has no end-users or UI; its "health" is process hygiene. Jailyard is a _product_ with a frontend, readers, and content.

| Dimension              | Jailyard (today)                            | blakebook                                                                        | Read                                       |
| ---------------------- | ------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------ |
| Docs                   | A (excellent CLAUDE.md)                     | A (the _source_ of the convention + vault decisions)                             | ~even                                      |
| Testing                | 76 data-pipeline tests, no CI               | RED/GREEN proofs of hooks/skills                                                 | even, different surface                    |
| Security/secrets       | A (zero deps, gitleaks)                     | Manages real secrets (`.env.shared`, gitleaks-action)                            | even; blakebook bigger surface             |
| **Process automation** | global hooks + a roadmap (new this session) | bootstrap `--check` drift, retirement protocol, journal pipeline, 22-pattern doc | **blakebook well ahead**                   |
| **CI rigor**           | data-fetch only, no test gate               | gitleaks-action + squash-merge scanner discipline (Pattern #10)                  | **blakebook ahead**                        |
| Roadmap maturity       | created this session (nascent)              | grew into a longform shipped-log                                                 | blakebook ahead                            |
| Product/app debt       | frontend dup, label drift, empty catches    | (no app surface)                                                                 | Jailyard carries debt blakebook can't have |

**Synthesis:** blakebook _should_ lead on process/tooling/CI/roadmap maturity — it's the project where Blake builds the process itself. Post-Phase-1a, Jailyard is comparable on **docs, security, and engineering discipline**, but trails on **process automation, CI rigor, and roadmap maturity**, and carries **product-level debt** blakebook structurally lacks. The gap is narrowing on exactly the axes Phase 1a targets.

**Highest-leverage blakebook practices to port to Jailyard:** (1) **test CI** (blakebook gates on green; Jailyard doesn't), (2) **dep hygiene** (`requirements.txt`), (3) the **roadmap** (done this session). Jailyard does _not_ need blakebook's full machinery — it's a smaller-surface product; importing those three closes most of the meaningful gap.

_Note: this comparison is grounded in cross-project context (global CLAUDE.md, the patterns doc, memories), not a fresh `/onboard` run on blakebook. A true side-by-side would run `/onboard` in the blakebook repo and diff the two cards._
