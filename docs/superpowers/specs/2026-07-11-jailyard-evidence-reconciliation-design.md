# Jailyard Evidence-Reconciliation — Design Spec (v4.1, effective)

> Effective spec. The v4 baseline below (historical, sha256 `FE03786A…737B11`, byte-exact, unmodified) is preserved for provenance; the **v4.1 corrections** that follow **govern on any conflict**. This consolidated v4.1 carries its own hash (reported at persistence checkpoint).

## Baseline (v4 — historical, DO NOT EDIT)

# The Evidence-Reconciliation Layer — Executable Plan (v4)

> Direction approved through v3. v4's bounded revision makes enforcement **general** (not Ken-obi-shaped): a claim-type registry, canonical claim-context bundles, an honest completeness split, full review-input binding, lineage-not-coexistence provenance, a real entry-point map, and league-wide acceptance. Ken-obi is one fixture, not the acceptance test.

## Context (verified)

Root cause = unreconciled contradictory authorities with **prose treated as evidence**: `team-profiles.json` held `needs:["QB"]`, `ranks.qb:11`, KTC-derived `overallValue/starterValue`, **and** "four startable QBs / All-Pro" in one record; `week{N}_data.json` propagated the prose. League = 1-QB, 0 SF, **13 BN**, deep dynasty. Roster 10 started **3** QBs (Maye ×15, Lawrence wk14, McCarthy wk15; Richardson never). `projections.json` `updated_at`≈Oct-6-2025 (post-wk1) → not as-of safe. Corrected note: structured `ranks/needs/values` are **not automatically evidence** (§5).

---

## 1. General claim contract (registry, not a fixed short list)

**`claim_registry` artifact** (`scripts/schemas/claim_registry.json`) — every governed claim type → `{admissible_lens_ids[], predicate_schema, allowed_temporal_orientations[]}`. Initial registered types: `ex_ante_startability`, `ex_post_starter_result`, `lineup_eligibility`, `room_depth`, `roster_efficiency`, `dynasty_value`, `weekly_performance`, `comparative`, `health_availability`, `idp_context`, `forward_pick`, `attributed_opinion`, `other_evaluative`.

Rules:

- **No lens shopping:** a claim adjudicates only via its registered `admissible_lens_ids`. Wrong-lens → deterministic FAIL.
- **`other_evaluative` is not an escape hatch:** it must carry a `subtype` + `lens_id` + `predicate`. An **unknown** subtype is recorded for discovery but **REVISE** until its lens is registered.
- **Authorial hedge ≠ exemption.** "I think X is elite" is a truth-bearing evaluative claim needing support. Only a **named, provenance-backed third-party opinion** is admissible — and only as `attributed_opinion` evidence that _person P expressed O at T_, never that O is true.
- **`starter_level_result` definition is a concrete Milestone-A artifact + test** (`scripts/schemas/starter_level_result.json`): this league's scoring, positional universe, threshold (weekly finish baseline per 1-QB/12-team; per-position for IDP), tie handling, bye/DNP treatment, offensive/IDP slot. Test computes it reproducibly for known weeks.

## 2. Canonical claim context = the bundle key (no writer curation)

Bundle key is a **canonical claim context**, persisted per claim (not derived from file/rewrite time):
`{subject_refs[] (typed canonical ids), claim_type, lens_id/metric/predicate, knowledge_cutoff, target_period, temporal_orientation, position_or_slot, comparison_universe?, league_config_id}`.
`bundle(claim_context)` = deterministic exhaustive query over the evidence store returning **every** qualified authority for that context. The writer supplies only the context key; verifier + editor see the **recomputed** bundle. The writer cannot add, drop, narrow, or relabel members. (Fields optional per type; the invariant is the key fully determines the bundle.)

**Locator:** each ledger entry uses `content_path` + JSON Pointer + `offset`/`span_hash` → resolves to exactly one occurrence (a phrase can appear in both essay and a blurb).

## 3. Completeness — the honest split (editor owns semantic discovery)

Deterministic code **cannot discover omitted claims** in free-form prose; it validates what's declared. So:

- **Governed-field registry** (`content/governance/governed_fields.json`) enumerates every governed published prose field and classifies each: `authorial_prose | quotation | control_metadata | other`.
- **Deterministic verifier** validates _declared_ ledger entries: unique locators, recomputed bundles, lens admissibility, resolved joins, provenance completeness, coverage records.
- **Editor** independently inventories material claims across every registered field; any **material unledgered claim → REVISE**.
- **Phrase/model detection = advisory** assistance to the editor scan.
  (Preserves current voice. If deterministic semantic completeness is ever required, prose must go claim-first/marked — deferred, not now.)

## 4. Review-input binding (binds everything that justified approval)

Approval record stores a canonical **review-input hash** over: reviewed content bytes · exact ledger bytes · **sorted consumed bundle hashes** (evidence manifest) · qualification + temporal/query-policy versions · `league_config`. Stored append-only alongside `content/review-log.jsonl` (extends the existing `{piece, pass_number, verdict, ...}` schema; contaminated approvals are **kept**, new pass appended).

- Renderer recomputes the input hash and **refuses stale approval**. Unrelated evidence-store changes do **not** invalidate while every consumed bundle stays byte-identical.
- **HTML binding (pushed-back mechanism):** since render is agent-driven, bind the HTML by its own hash **and** run a deterministic **prose-faithfulness** check — governed prose spans extracted from `weekN.html`/`preseason-*.html` must be byte-equal to the approved ledgered content. Closes agent-render drift without a deterministic renderer.
- **Invalidation tests:** content, ledger, consumed-bundle, policy, and league-config mutation each invalidate.

## 5. Provenance = lineage, not coexistence

- **PASS-gate covers every raw authority** under the on-disk substrate. Derived files need no independent rights review but must carry **lineage to PASS-qualified upstreams + input hashes + transform/code versions**. Existing files are not trustworthy for saving ingestion work.
- **`team-profiles.json` `ranks/needs/values`:** either (a) receive real provenance, (b) be **regenerated from qualified evidence**, or (c) be classified **contextual/non-evidence**. They are not evidence by coexisting with prose.
- **`preseason.html` is a live linked page with contaminated prose** — not renderer-reference-only. Give it an explicit **edit / regenerate / retire** operation and resolve the authority direction between it and `team-profiles.json` (which is source of truth).

## 6. Integration map — real entry points + stable contract locations

**Enforcement lands on these live paths (a publish path must not exist beside the gate):**
| Stage | Entry point | Gate role |
| --- | --- | --- |
| Data | `scripts/extract_week_data.py`, `generate_expanded_week.py` | emit provenanced week data; carry lineage |
| Write | `.claude/commands/write-week.md`, `write-preseason.md` | emit prose + populate claims ledger (context keys, locators) |
| Verify (code) | **`scripts/verify_week_content.py`** (extend) + new `scripts/verify_evidence.py` | deterministic hard-fail: declared-entry validation, locator uniqueness, bundle recompute, lens admissibility, joins, provenance, coverage |
| Canon | `.claude/commands/canon-check.md`, `scripts/canon_checks.py` | continuity + governance preconditions |
| Edit | `.claude/commands/edit-week.md`, `edit-preseason.md` | semantic completeness inventory + APPROVE/REVISE → `content/review-log.jsonl` + review binding |
| Render | `.claude/commands/render-week.md`, `render-preseason.md` | recompute review-input hash; prose-faithfulness; refuse stale |
| Public | `week1..6.html`, `preseason-2025.html`, `preseason.html` | governed outputs (in boundary) |

**New persistent contracts (stable paths):** qualification verdicts `data/governance/qualification/{source}.json`; evidence store `data/2025/evidence/**` (+ `_bundles/` manifests); schemas `scripts/schemas/{claim_registry,starter_level_result,evidence,claim_context,ledger,review_binding}.json`; claims ledgers `content/ledgers/{piece}.json`; review bindings appended to `content/review-log.jsonl`. Internal helper-module names remain implementation judgment.

**Gate order:** qualify → produce+lineage evidence → draft+log claims → deterministic verify → canon → editor semantic → bind → render(+faithfulness) → production-path scan.

## 7. Governed boundary + league-wide acceptance

**Boundary (explicit):** `preseason-2025` + every governed published prose field in **Weeks 1–6**, all **12 teams**. Draft/trades/history/season/power-rankings pages are **out of Milestone-A scope** (named deferral, not silent exclusion).

**Acceptance:**

- Every **material published claim about all 12 teams** within the boundary is ledgered + editor-adjudicated.
- **Coverage report** by artifact × field × team × claim_type × position.
- No requirement to manufacture every claim type for every team.
- **Fixture set beyond Ken-obi** collectively covers `comparative`, `dynasty_value`, `health_availability`, `idp_context`/multi-position, and `forward_pick`.
- Unsupported lenses, unknown claim types, missing coverage, and unresolved joins remain **explicit in the report**, never dropped from the denominator.
- **Ken-obi = one hashed regression fixture**, not the organizing test.

## 8. Containment (audit snapshot + zero-unauthorized scan)

Keep the exact initial contamination list + count as an **audit snapshot** (currently ~49 non-archive hits). Every current hit gets a manifest operation typed as: **edit** authoritative prose (`team-profiles.json`, `voice-bible.md` — retire Exemplar A + Coachella/All-Pro; qualify "go big with superlatives"; generalize anti-sycophancy to source/name deference; "prose is never evidence"); **re-extract** `week{N}_data.json`; **regenerate** `week{N}_data_expanded.json`; **rewrite** preseason + weekly content JSON; **re-render** HTML; **edit/regenerate/retire** `preseason.html`. Never touch `dontuse*`.
**Sequence:** preserve hashed Ken-obi fixture → fix authorities/derived/preseason before M2 → Weeks 1–3 authored rewrites are the **first M2 ops** (not rewritten twice; surgical hotfix if pages can't stay public meanwhile). **Completion gates on a fresh production-path scan yielding zero unauthorized hits** (only explicitly named fixture/archive paths allowed; `dontuse*` excluded) — not equality to a frozen count.

## 9. Milestones + falsifiable deferrals

- **Milestone A (before M2):** registry + starter-level artifact · claim-context bundles · provenance/temporal-class + qualification (PASS-gated) · split gate + review binding · containment on authorities/derived/preseason. Core sources: DynastyProcess dynasty ECR _(pending PASS)_ + on-disk substrate + week-N actuals + `fantasy_rosters`. **No optional sources** (manual KTC/FantasyCalc are earn-ins).
- **M2 (Weeks 1–6) = calibration corpus** (wks 1–3 rewrites first). Optional lenses earn inclusion by changing adjudications/coverage.
- **File-backed but rigorous:** canonical schemas, deterministic queries, unique keys, content hashes, atomic writes, append-only review history.
- **Falsifiable deferrals (triggers, not prohibitions):** add a **DB** if measured query cost / transactional integrity / concurrent writers break the file design; add **evidence scoring** only after the calibration corpus shows recurring authority conflicts _and_ a validated score improves adjudication; add **confidence aggregation** only once calibratable _and_ source-dependence is handled (no double-counting).

## 10. Focused verification set (must prove — general, not Ken-obi-only)

Deterministic FAIL: wrong lens for claim type · future-informed evidence · missing required bundle · unresolved dependent join. **REVISE:** unsupported ex-ante assertion (Ken-obi preseason fixture) · a **material claim omitted** from the ledger · unknown `other_evaluative` subtype. **Cannot pass:** omission of a qualified authority from a bundle (bundle recomputed) · authorial-hedge exemption attempt. **APPROVE:** a genuinely supported evaluative claim. **Binding invalidation:** content, ledger, consumed-bundle, policy, league-config mutation each invalidate. **Coverage:** all 12 teams across the boundary reported; non-Ken-obi fixtures span comparative/dynasty/health/IDP/forward-pick. Plus full suite green; CI on HEAD SHA.

---

## PART A′ — v4.1 corrections (explicit delta; Phase 0 consolidates into authoritative v4.1 w/ new hash)

- **R1 Temporal policy (versioned).** Dual-time: `effective_at`=period; `first_known_at`=knowability, admissibility uniformly `first_known_at ≤ knowledge_cutoff`. Backfills keep `effective_at`, take capture as `first_known_at`. Per-class _derivation_ documented; enforced at P2. Approval binds to policy canonical-JSON hash.
- **R2 Lens/provider split.** Registry names abstract lenses; `lens_providers.json` (P2, PASS-gated) maps providers→lenses, validated vs `value_shape`.
- **R3 `forward_pick`=`disclosed_forecast`.** Every material truth-bearing premise (factual OR evaluative, incl. metaphor) decomposes to its own ledgered claim; external projection = context only; resolution never validates a defective premise.
- **R4 Phase seams.** Writer (P4) inert until P5; P6 splits P6a containment-readiness / P6b Weeks-1–6 coverage.
- **R5 Bidirectional render binding** on canonical decoded nodes both directions; unmapped → FAIL.
