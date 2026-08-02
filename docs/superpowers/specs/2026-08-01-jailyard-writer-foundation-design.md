# Jailyard — Writer Foundation + Newsroom Design

**Date:** 2026-08-01
**Status:** **APPROVED** by Blake 2026-08-02 as written at `072f4ea`. This is the design
authority for the 2025 replay program; implementation plans are written against this document,
and material changes require re-approval.
**Relationship to prior work:** replaces the "weeks 1-6 next" sequencing in
`2026-06-04-jailyard-2025-catchup-design.md`. That document's data → content → design ordering
still holds; its claim that the data layer is complete does not.

## Context

The 2026-06-04 program said the next step was rewriting weeks 1-6. That is wrong, and this
session proved it against disk.

### The defect, stated at two levels

**Structural exposure: 98 of 98 H2H blocks are unsafe.** Every `matchups[].h2h` block in every
week packet is sourced from `league_history.json`'s season-end aggregate with no cutoff slice —
`wins`, `losses`, and `last_meeting` are all-time values. Blocks that read correctly today do so
by accident of scheduling, not by construction.

**Confirmed contamination: 46 entries currently carry future values.**

| Class                                      | Count  | Detail                                                   |
| ------------------------------------------ | ------ | -------------------------------------------------------- |
| H2H `last_meeting` postdating the packet   | 32     | Worst case: `week1_data.json` carries a week-17 score    |
| `historical_context.highest_combined`      | 13     | 2025 week 14 record, present in packets 1-13             |
| `historical_context.longest_losing_streak` | 1      | Undated aggregate; week 1 carries 10, correct value is 9 |
| **Total**                                  | **46** |                                                          |

This counts **week-packet fields only**. A separate source-level exposure — 239 of 1,205 media
catalog items postdating the week-1 cutoff, with no filtering in any media tool — is documented
under the projection compiler and is not included in the 46.

### Reproducing census

Two passes are required, and the second is the one that was originally missed.

**Pass 1 — dated entries.** Compare `season`/`week` against the edition cutoff:

```python
import json, glob, re
def wkof(p): return int(re.search(r'week(\d+)_', p).group(1))

h2h_struct = 0; h2h_future = []; hc_future = []
for fp in sorted(glob.glob('content/weeks/week*_data.json'), key=wkof):
    wk = wkof(fp); d = json.load(open(fp, encoding='utf-8'))
    for m in d.get('matchups', []):
        h = m.get('h2h') or {}
        if not h: continue
        h2h_struct += 1                      # sourced from the unsliced aggregate
        lm = h.get('last_meeting') or {}
        s, w = lm.get('season'), lm.get('week')
        if s is not None and (s > 2025 or (s == 2025 and w is not None and w > wk)):
            h2h_future.append((wk, s, w))    # recap semantics: week N's own meeting is legal
    for key, rec in (d.get('historical_context') or {}).items():
        if not isinstance(rec, dict): continue
        s, w = rec.get('season'), rec.get('week')
        if s is not None and (s > 2025 or (s == 2025 and w is not None and w > wk)):
            hc_future.append((wk, key, s, w))
```

Expected: `h2h_struct == 98`, `len(h2h_future) == 32`, `len(hc_future) == 13`.

The comparison is `w > wk`, not `w >= wk`. Using `>=` reports 98 H2H leaks, which conflates
structural exposure with actual contamination.

**Pass 2 — undated aggregates.** `longest_win_streak` and `longest_losing_streak` carry only
`count`, `team`, `owner_id`. **A missing `season`/`week` cannot mean safe, and cannot mean
skipped.** Undated aggregates are recomputed from temporal primitives and compared to the
committed value. For streaks: replay non-playoff games from `data/*/season_combined.json` in
order, truncated at each edition cutoff, tracking `best_l` per owner
(`fetch_sleeper.py:962-1002`). Verified results:

| Cutoff            | Correct `longest_losing_streak` | Committed value |
| ----------------- | ------------------------------- | --------------- |
| through 2024      | 8                               | 10              |
| through 2025 wk 1 | 9                               | 10              |
| through 2025 wk 2 | 10                              | 10              |

So exactly one packet (week 1) is contaminated on this field today. That the number is small is
irrelevant — the field was invisible to the detector entirely, which is the real defect.

**The sibling is accidentally safe, not structurally safe.** `longest_win_streak` was tested the
same way and leaks in **0 packets**: the 11-game streak completed before 2025 week 1, so the
committed value is correct at every cutoff. It is nonetheless produced by the same unsliced
computation from the same undated shape. It reads correctly by accident of when that streak
happened — exactly as the 66 currently-clean H2H blocks read correctly by accident of scheduling.
Both undated aggregates are structurally exposed; one is confirmed contaminated. Treating the
clean one as safe is what produced this class of defect in the first place.

### Root cause

`extract_week_data.py:559-567` reads `history_data["h2h"]` and takes `games[-1]` as
`last_meeting`. No cutoff filter. `compute_as_of_history` — the correct helper — already exists
in the same file and is already used by the standings path.

`verify_h2h_claims` (`verify_week_content.py:892-949`) validates writer prose _against_ the
contaminated field, and only warns. A column faithfully reporting the leaked number is certified
correct.

### What is NOT broken

`standings` are genuinely cutoff-correct: between weeks 1 and 10, zero of twelve standings blocks
are identical (`record` 0-1 → 2-8, `current_elo` 1429.4 → 1351.7, `all_time_record` 19-24 →
21-31). The chat layer's temporal admissibility and provenance were hardened and pushed
2026-07-20 (`c751b22`, CI green).

The defect is not "the foundation is incomplete." One fix landed on one field family and silently
missed its siblings — the fourth documented instance of that pathology here. **Nothing walks the
writer-facing surface and asks every field whether it is cutoff-legal**, and nothing recomputes
the fields that carry no timestamp to ask with.

## Temporal semantics

**The cutoff is an exact UTC instant, declared per edition** — not a week number. Week numbers
cannot express "before the Thursday opener," which is exactly where the preview lives.

| Edition                    | Cutoff                            | Week N results | Week N H2H meeting |
| -------------------------- | --------------------------------- | -------------- | ------------------ |
| Preseason                  | before any 2025 game              | excluded       | excluded           |
| Week 1 pre-kickoff preview | **strictly before** first kickoff | excluded       | excluded           |
| Week N recap               | after week N games conclude       | included       | included           |
| Finale (week 18)           | after the week 17 championship    | n/a (no games) | included thru 17   |

**Every source class is qualified, not only markets.** For each source: what temporal primitive
establishes its `known_at`, how it is recomputed at a cutoff, what provenance is required, and
what happens when it cannot be established (the answer is "unavailable," never "assume safe").

Transaction reconstruction uses the **effective completion instant**, not `created` — some
transactions are created before a kickoff and complete after it.

**The preview cutoff is strictly before kickoff.** `shared.admissible` is inclusive (`ts <=
cutoff`), so a descriptor whose `cutoff_utc` _equals_ the qualified first-kickoff instant would
admit evidence at kickoff — which is not pre-kickoff. The week-1 preview descriptor sets
`cutoff_utc` to an instant strictly prior to the qualified first kickoff, so the inclusive
comparison still yields pre-kickoff semantics. The same descriptor cutoff governs rebound league
media.

## The ranking decision contract — the product proof

Power rankings are not one desk among six. They are the artifact this system exists to produce,
and the only one that can demonstrate the league model becoming more informed. Everything else —
temporal correctness, provenance, reproducibility — is subordinate infrastructure.

**This is not a statistical ranking model.** No formula, no weights, no validated predictor. It is
a _decision record_: the columnist's dated judgment, with its reasoning exposed for audit and
later grading.

Per team, per edition:

```json
{
  "team": "General Ken-obi",
  "prior_rank": 4,
  "proposed_rank": 2,
  "movement": "up_2",
  "decisive_evidence": ["<bundle evidence refs>"],
  "contrary_evidence": "<what argues against this, or the uncertainty accepted>",
  "coherence": "<why this order holds together -- addressing whoever was passed>"
}
```

**Preseason claims become receipts.** A ranking rationale is a dated claim; later editions grade
it rather than forget it. This generalizes the `picks_ledger` pattern from predictions to
judgments — and unlike picks, a ranking rationale can be wrong in an _interesting_ way, which is
what makes learning visible.

**Ranking quality is a first-class gate**, in the Phase C bake-off and in every edition's
acceptance:

- **Evidence-driven ordering** — every movement traces to evidence in that edition's bundle.
- **Explained movement** — no silent moves; a changed rank carries a rationale.
- **No unexplained inversions** — if A passes B, the rationale addresses B.
- **Continuity with prior judgment** — contradicting an earlier call requires acknowledging it,
  not quietly reversing.
- **Blake approves the ranking itself**, separately from the prose.

The design must be unable to pass with stylish columns and arbitrary rankings. An edition with
clean facts, strong voice, and unjustified ordering is a **failed** edition.

## Phase 0 — 2026 evidence preservation (parallel lane, starts immediately)

The point of rebuilding 2025 is to exercise the system that will write the 2026 preseason and
week-1 preview. That evidence is disappearing now:

- `data/2026` is still the 2026-04-04 snapshot.
- `.github/workflows/fetch-sleeper-data.yml` cron is `0 6 * 9-12 0` — nothing runs before
  September.
- `fetch_sleeper.py` overwrites current rosters and projections with no append-only capture
  identity.
- **The existing fetcher cannot capture the offseason at all.** `fetch_sleeper.py:172` iterates
  `range(1, len(all_matchups) + 1)`; before any scored matchup exists, that is `range(1, 1)` and
  **zero transactions are fetched**. Offseason preservation is not merely untested — it is
  structurally impossible with the current code. Phase 0 needs its own capture path.

Spending the summer rebuilding 2025 while volatile 2026 preseason evidence evaporates would
force us to reconstruct another pre-kickoff state after the fact — the exact failure class this
design exists to eliminate.

### Capture is not admission

Preservation is deliberately **broad**; edition admission stays **strict**. Capturing a
projection feed now does not make it admissible evidence later — admission still requires a
qualified `known_at` and an adapter. Capturing costs little and is irreversible if skipped;
admitting is a separate, revocable decision. Conflating them is what makes preservation
programs stall on qualification debates until the evidence is gone.

### Minimum capture table

Every row is captured append-only; existing snapshots are never overwritten.

| Source                          | Mechanism                       | Cadence / trigger                    | Known-at semantics                         | Privacy     |
| ------------------------------- | ------------------------------- | ------------------------------------ | ------------------------------------------ | ----------- |
| Sleeper league settings         | API                             | weekly + on change                   | capture instant                            | public      |
| Sleeper users / franchise names | API                             | weekly + on change                   | capture instant                            | public      |
| Rosters (prospective, pre-lock) | API                             | daily through preseason              | capture instant; roster state as-of        | public      |
| Draft (picks + order)           | API                             | on completion, then weekly           | pick timestamp where available             | public      |
| Transactions                    | API, **offseason-capable path** | daily; keyed on effective completion | effective completion instant               | public      |
| Projections / markets           | source-dependent                | weekly through preseason             | publication instant; unqualified if absent | public      |
| Injuries / availability         | source-dependent                | weekly through preseason             | publication instant; unqualified if absent | public      |
| Chat + media export             | manual export                   | on export                            | message timestamp                          | **private** |

Every captured artifact records: `source`, `captured_at`, `known_at` semantics, content hash,
and privacy boundary.

### The private-source boundary

Stated carelessly, "private artifacts never enter a public projection" would forbid the culture
layer — chat receipts and league media are among the richest intended inputs, and the week-1
preview explicitly consumes cutoff-projected chat. The boundary is about _wholesale copying_, not
about derivation:

- **Raw private captures** — chat exports, media originals — never leave their protected local
  boundary and are never copied wholesale into public artifacts.
- **Derived projections, quotations, and media selections may reach writer bundles and
  publication** when they are explicitly policy-approved and provenance-bound.
- **Publication eligibility remains separate from temporal admissibility.** A quote can be
  perfectly in-window and still be unpublishable; the 147 `personal`-tagged assets are the same
  case in media form.

**In scope for Phase 0:** prospective preseason roster and source capture, including the
offseason-capable transaction path.
**Out of scope:** 2026 authoring, and live in-season capture operations (roster capture _during_
the 2026 season, current-week detection). Phase 0 preserves the pre-kickoff window only.

## Phase A — Authority and read-path census

Not a file table. An audit of **every path by which prose reaches a writing decision**: prompts,
local drafts, generators, editors, media tools, renderers, and derived artifacts.

Confirmed contaminated read paths:

| Path                                      | Finding                                                                   |
| ----------------------------------------- | ------------------------------------------------------------------------- |
| `voice-bible.md` §1 patterns              | Excerpts at :16-20, :38-46, :64-70, :100-106, :122-126, :148-152          |
| `voice-bible.md` §5 exemplars             | Entirely excerpts from superseded prose                                   |
| `write-week.md:7-25`                      | Requires the whole voice bible, team-profile essays, optional local draft |
| `write-preseason.md:47-53`                | "use as inspiration" for team-profile prose                               |
| `write-preseason.md:72-75`                | 2026 prose as "shape, tone, and length precedent"                         |
| `weekN_data.json` `team_profiles_summary` | Carries `essay_snippet` and `roast`                                       |
| `generate_franchise_wings.py:294-301`     | Compiles `roast` into `voice_bible_callbacks` in franchise data           |

**Keep:** abstract voice grammar (pattern definitions), section templates, anti-patterns.
**Remove or block:** every current prose excerpt, wherever it appears — including inside
generated data.
**Preserve:** old prose as git fixtures that no active path can read.

**No replacement exemplar is required for the first edition.** The "no deletion before
replacement" rule applies to authoritative _instruction surfaces_, not to illustrative excerpts;
the voice grammar is fully operative without examples. The first approved edition becomes the
first canonical exemplar afterward.

The handle table in §2 is replaced by the chat-mined name repertoire (Phase C); `@kharlo_w` is
wrong — `data/2025/users.json` says `kharlow`. Roadmap SUPERSEDED blocks and the four `.bak`
copies are deleted; git and the daily ClaudeMemorySnapshot preserve history. `CLAUDE.md` stale
counts corrected in place (states 200 tests; suite is 343).

## Phase B — Repair, projection compiler, and audit

### Repair

Slice `h2h_entry["games"]` by the edition cutoff and recompute `wins`/`losses`/`last_meeting`.
Recompute `historical_context` — including undated aggregates — at each cutoff. Re-extract all
packets **and the `_expanded` companions in the same pass**; commit `c5b6b50` regenerated week
data without the companions and left 32 season-end Elo values leaking there.

**Role change.** The repaired per-week packet stops being a direct writer input and becomes a
**component of its edition's bundle**, carrying the edition's `edition_id`, `cutoff_utc`, and
build identity — **not** the enclosing bundle's final hash, which cannot exist yet. This keeps the
existing verifier and renderer working against a familiar shape while still satisfying the
writer-access boundary — the packet a consumer reads is the one the projector compiled, not a
file it opened for itself. Its prose fields (`team_profiles_summary.essay_snippet`, `roast`) are
stripped per Phase A. Pages outside the writing path (`season.html`, `history.html`) may continue
reading published data directly; the boundary governs writing decisions, not site rendering.

### Projection compiler

Lightweight, file-backed, no database and no full typed evidence hierarchy — but a real contract,
not an ephemeral subset.

**Built to a minimum, not to completion.** Only the adapters the first three editions (D1)
require are implemented; every other source fails closed until an edition needs it. Adapter
coverage is driven by editions, not built speculatively ahead of them.

- **Edition descriptor:** `edition_id`, `season`, edition kind, `cutoff_utc`, results-through
  week, policy version.
- **One canonical, persisted writer-facing bundle per edition.** Persisted because the archive is
  definitive; an ephemeral slice cannot be re-audited.
- **Per-source adapters**, each naming its temporal primitive, recomputation rule, provenance
  requirement, and unavailable behavior. Final aggregates — streaks, player arcs, records —
  cannot be made safe by generic field filtering and require explicit recomputation rules.
- **The projector is the sole trusted reader** of raw and full-season stores.
- **Consumers** — writer, desks, editor, local drafter, media picker, content verifier — read
  only the edition bundle, approved prior editions, and editorial rules. Direct reads of
  full-season stores become test failures.
- **Two identities, not one** — a single hash binding both the inputs and its own output is
  circular:
  - **Bundle manifest** — binds the edition descriptor, raw-source hashes, projection code and
    policy version, and a **separately calculated bundle-payload hash**.
  - **Authoring manifest** — binds the bundle manifest, approved predecessor hashes,
    desk/writer/editor rule versions, the produced content hash, and the final ranking decision
    record. **Content and ranking only — no media.** Editorial approval binds this object, and
    approval happens before media exists.
  - **Publication record** — written after media and render; binds the approved authoring
    manifest, the media-manifest hash, the rendered-HTML hash, and the publication result.

  Components carry edition and build identity; only the manifests carry final hashes.

- **Editorial approval binds the authoring manifest and content**, not the evidence bundle alone.
  This distinguishes the two ways an approval goes stale — the evidence changed, or the rules
  that interpreted it changed — which one hash cannot express.
- **Season-parameterized from the start**, with at least one non-2025 canary edition, so 2025
  genuinely tests a reusable system rather than a 2025-shaped one.

### Media catalog — rebind before it can be a source

**Current state, stated precisely.** `content/chat/media-catalog.json` holds 1,205 items with
`timestamp_utc`, of which **239 postdate the week-1 kickoff, including 77 from 2026**. This is a
**source-level exposure**, counted separately from the 46 packet contaminations.

It is **not** a confirmed catalog-to-picker leak today: `pick-media.md` and `resolve_media.py`
contain no reference to `media-catalog.json`. An earlier revision of this document implied they
read it; they do not.

**Current committed writer contexts are NOT proven contaminated by the catalog.** An earlier
revision of this document asserted that they were, via `build_chat_context.py`. That claim was
wrong and is retracted. The live call graph, checked by AST across `scripts/`:

- `build_chat_context.py:38` declares `MEDIA_CATALOG_PATH` as an **assignment target only** —
  zero load references anywhere in the module. It never opens the catalog.
- `score_message_relevancy` (`:358`) takes `media_catalog=None` as its last parameter, and the
  conditional lookup at `:381-382` sits behind that default.
- Its **sole production caller (`:1228`) passes ten positional arguments and no keywords**, so
  the parameter is always `None` and the branch is unreachable. **Dead code, not a leak.**
- `generate_chat_provenance.py:102-103` classifies `media-catalog.json` as
  `KNOWN_NON_PIPELINE_CHAT_JSON`, and `CODE_FILES` (`:79-89`) excludes `analyze_chat.py` from the
  canonical set. `--verify` currently reports `OK ... matches recomputed (full)`.
- The canonical workflow is `map_chat_deterministic.py` → `reduce_chat_deterministic.py` →
  `build_chat_context.py`.

**The actual unsafe reader is `analyze_chat.py`**, which genuinely loads the stale catalog
(`load_json(MEDIA_CATALOG_PATH)` at `:145` and `:988`) and message-ID-joins it into legacy AI MAP
prompts and persona generation. Its risk is different in kind: it is a **noncanonical,
overwrite-capable legacy producer** that can rewrite the same analytics filenames the canonical
builder later consumes. That is a contamination _route_, not evidence of contamination _today_.

**Phase A obligations:** quarantine or retire `analyze_chat.py` as an active producer, or require
it to use the rebound catalog and enter the provenance contract before it may run
authoritatively. The dormant `build_chat_context` enrichment is either removed or intentionally
activated — and only after rebind.

What the catalog _becomes_ under this design is a selectable-media corpus. Rebinding remains
required before that corpus is authorized, and the 239 stays a **source-corpus exposure**,
separate from the 46 packet contaminations.

**But the catalog cannot simply be filtered on that timestamp.** It was committed at `9ae72e3`
(2026-07-10) and never touched since; the parser repair landed at `c751b22` (2026-07-20). Its
provenance does not survive that repair. Measured against the repaired corpus:

| Check                                            | Result          |
| ------------------------------------------------ | --------------- |
| `message_id` differs from the live message       | **1205 / 1205** |
| `timestamp_utc` differs                          | **1202**        |
| `sender` differs                                 | **742**         |
| Live attachments absent from the catalog         | **255**         |
| `message_id` joins resolving to the correct file | **0 of 1205**   |

The 742 sender mismatches are the known unicode-space bug (Harlow and Patrick, 742+ messages
never resolved before the repair).

Filtering on `timestamp_utc` would therefore gate on a field that is wrong 1,202 times out of
1,205 — promoting a stale catalog into authority rather than containing it.

**Rebind first:**

- Join on **asset content hash plus filename/source provenance**. `message_id` is not a valid
  join key — every one of its 1,205 joins resolves to the wrong file.
- Preserve existing descriptions where the asset rebinds cleanly; regenerate only entries that
  are missing or whose asset changed. The descriptions are expensive and mostly still valid;
  it is the _provenance_ that is broken, not the prose.
- Treat the **255 uncatalogued assets as unavailable** until classified.
- **No `message_id` join is trusted without a verified source binding.**
- Only after rebinding does the catalog become a per-edition bundle source, projected on the
  repaired timestamp.

### Publication eligibility is not temporal admissibility

These are independent properties and both must hold. A cutoff-safe attachment is not thereby
publishable: **147 catalog entries are tagged `personal`.** A photo of someone's kid from 2023 is
perfectly admissible at any 2025 cutoff and must never be embedded in a public column.

- Rebound league-media items default to **unreviewed**. Only explicitly approved items may be
  embedded.
- Kept lean: review D1 candidates and selections as they arise rather than classifying all 1,205
  assets up front. Classification is demand-driven.

**No blanket GIPHY exemption.** GIPHY and custom media may carry an explicit
`non_evidentiary_decoration` policy **only** when they communicate no post-cutoff Jailyard or NFL
fact. A generic reaction GIF qualifies; a GIF captioned with a week-14 result does not, and a
screenshot of a later standings page never does. Anything else requires ordinary temporal
qualification. The prior revision's blanket exemption is withdrawn — "third-party" describes
where an asset came from, not what it discloses.

### Media enforcement through the rendered artifact

Bundle admission proves what media was _available_. It proves nothing about what was _selected_
or what the HTML _embeds_. Those are three different facts and only the last one ships.

**Per-edition media manifest — tracked, and the sole authority.** Bound to the edition ID, the
approved authoring-manifest/content hash, and the media-policy version. Each selected slot
records:

| Field                | league_media                                     | giphy                                            | custom                        |
| -------------------- | ------------------------------------------------ | ------------------------------------------------ | ----------------------------- |
| source class         | `league_media`                                   | `giphy`                                          | `custom`                      |
| source identity      | protected source locator + **source SHA-256**    | exact GIPHY ID                                   | asset SHA-256                 |
| selection provenance | why this slot, from what query                   | same                                             | same                          |
| temporal             | rebound `timestamp_utc`                          | cutoff-qualified or `non_evidentiary_decoration` | same                          |
| transformation       | redaction / crop / none — the decision, recorded | n/a                                              | n/a                           |
| publication decision | approved / unreviewed / barred                   | policy applied                                   | policy applied                |
| **publish identity** | **derivative SHA-256**                           | persisted resolved-result metadata               | asset SHA-256                 |
| **publish location** | **authorized repo-relative path or URL**         | persisted resolved URL                           | authorized repo-relative path |

**League media binds both sides of the endpoint.** A source SHA identifies the _protected
original_; it tells the renderer nothing about what it may embed. Each league-media entry
therefore carries a second, separate identity: the **approved publication derivative** — its own
SHA-256 and its authorized publication location — plus the transformation or redaction decision
that produced it.

**The renderer consumes only the approved publication derivative.** The final-HTML verifier
checks **both its location and its bytes** against the manifest.

Where publication approval permits the original unchanged, the source and publish hashes may be
equal — but the manifest must still name an **authorized publication location**, never exposing
or depending on the protected raw-source path. Equal hashes are a permitted outcome; a missing
publish location is not.

`media_picks.json` and `media_cache.json` are gitignored (`.gitignore:29-30`) and **may remain
derivative caches, but neither can authorize publication**. The verifier never consults them. No
raw-catalog reference, free-form custom path, or shared ignored cache authorizes anything.

**GIPHY results are persisted, not re-resolved.** Live search is dynamic — the same query returns
different assets on different days, and this project has already recorded GIPHY serving an
identical canned junk set across unrelated queries. The resolved result is captured in the
manifest so the artifact is reproducible.

**Custom assets** must live inside an authorized media root and hash-match the manifest.

**Both render paths** — weekly and preseason — and the resolver consume the per-edition manifest.
A referenced but unresolved slot **fails**; it does not silently disappear.

**Render verifier:** extract every media URL and path from the final HTML and prove a
**one-to-one match** with the manifest. No missing nodes, no extra nodes. This is the only check
that speaks to what actually shipped.

### Approval lifecycle — content first, publication last

The previous revision put the media manifest inside the authoring manifest. That is wrong:
**editorial approval happens before media exists**, so binding media into the approved object
would make every approval stale the instant art was added.

- **Authoring manifest** stays **content and ranking only**. Editorial approval binds this.
- **Publication record** is created after media selection and render, binding: the approved
  authoring manifest, the media-manifest hash, the rendered-HTML hash, and the final publication
  result.

This preserves the existing content-first workflow while still making publication provable.

**On whether a smaller mechanism would do:** I looked for one and don't believe it exists. The
manifest and the publication record sit at different times in the pipeline — the renderer
_consumes_ the manifest, and the publication record can only be written once the HTML it hashes
exists — so they cannot collapse into a single artifact. Promoting the existing
`media_picks.json` instead of adding a manifest saves nothing real: it would need edition
binding, hashes, and policy version added, which is the manifest, and it would fuse cache
semantics with authority semantics, which is the failure being prevented. Dropping the render
verifier would leave every other control unable to speak about the artifact that actually
publishes.

### Week 1 pre-kickoff preview inputs

`data/2025/fantasy_rosters/week1.json` is **not** a legal preview source. Proof: transaction
`1269785739084701696` added player `6949` to roster 6 at `2025-09-05T20:10:20.977Z`, after the
September 4 opener; that player appears in both `players` and `starters` in the backfilled week-1
file. The file records what week 1 became, not what was knowable before it.

The preview roster is **reconstructed to the exact cutoff instant** from transactions (using
effective completion instants) plus an admissible anchor — or marked unavailable.

**Unavailable unless separately proven:** final starters (inherently later knowledge), injuries,
availability, betting lines, market projections. No historical injury or availability artifact
currently proves a pre-kickoff `known_at`.

The preview is not thereby empty. It builds original forecasts from: the reconstructed roster,
the completed draft, 2022-2024 history and H2H, week-1 pairings stripped of outcomes,
cutoff-projected chat, and the newly approved preseason edition's rankings, predictions, and
opened threads. External forecasts are optional evidence, not what makes it a preview.

### Audit — two distinct questions

**Leaf census:** did we classify every field? Every leaf of every writer-facing artifact must be
`static-legal`, `cutoff-filtered`, or `forbidden`. Unknown fails closed. Undated aggregates
cannot be classified `static-legal` by default — absence of a timestamp triggers recomputation,
not exemption. Reuse the coverage pattern in
`docs/superpowers/plans/2026-07-11-governance-foundation.md` Task 5 — the mechanism only
(`_leaf_pointers`, `coverage_check`, equal-specificity conflicts failing closed, tests globbing
real files). That plan remains DRAFT and NOT APPROVED; borrowing its pattern does not ratify its
governance program.

**Noninterference:** did future evidence actually influence a classified field? Full-input versus
cutoff-truncated runs must produce byte-identical bundles, with detector-active positive controls
proving the comparison can fail. The existing chat-context noninterference and provenance code is
the local pattern.

Both are required; neither substitutes for the other. A clean rebuild must reproduce the same
bundle.

**Gate:** promote `verify_h2h_claims` from warning to error, evaluated against the edition cutoff.

## Phase C — The writing room

**Name repertoires.** Mine the chat corpus for how each of the twelve owners is actually referred
to. Twelve rows — first name, surname, handle, team, shorthand, earned nicknames — with usage
notes on register. Blake approves once; ships as committed data the Culture desk serves.

"Brent Boone" in every sentence is what happens when the writer holds a database row instead of a
relationship. A person you know has a name that moves with context.

**Desks**, as committed commands so 2026 reuses them: Power Rankings, Game/NFL, History, Culture,
Continuity, plus a Data/Copy Editor. Desks return structured evidence and candidate angles, never
prose. Desks read the edition bundle only.

**Continuity desk carries voice memory** — reads approved prior editions and reports what has
been spent: jokes, comparisons, openers, name-forms per owner. The only mechanism that catches
semantic repeats, which a string-matching ledger cannot.

Columns go stale because each edition is written cold — independent draws from one distribution,
each reaching for the most probable phrasing. `picks_ledger` and `meta.threads` make an edition
conditional on predecessors for _facts_. Nothing does so for _voice_.

**Bake-off.** Write the first edition both ways — desks and single-writer — and compare under the
editor rubric: factual corrections required, unique evidence used, phrase repetition, owner
specificity, how much survives Blake's edit. Keep the winner, delete the loser.

## Phase D — Twenty fresh canonical editions

**All existing prose is filler with zero editorial authority** — preseason-2025, weeks 1-6,
current rankings, threads, media choices, 2026 prose. Preserved as inaccessible git fixtures;
never inspiration, exemplars, continuity, rankings, or factual evidence. Preseason-2025 is
written fresh through the final system, not re-gated.

**The corpus:** preseason-2025, a standalone week-1 pre-kickoff preview, week 1-17 recaps, and a
week-18 finale (no week-18 fantasy games were played).

**Shape: story-first within stable sections.** Sections remain available and the renderer and
verifier stay simple; each edition leads with its strongest story and sections flex in weight.
Playoff weeks (15-17) and the finale get their own contracts.

**Order is strictly sequential — a hard dependency.** The prior edition's writer _invents_ the
picks, spreads, and tags; that data exists in no generated file. An edition's `meta.picks_ledger`
cannot be authored before the picks exist. Threads must be opened before being advanced.
Callbacks quote prose that must exist.

**Per-edition loop:**

```
descriptor declared → bundle compiled → desks brief
  → RANKING DECISION RECORD produced
  → columnist writes FROM that judgment
  → verify_week_content.py exits 0
  → /edit-week APPROVE  (review-log line bound to the authoring manifest)
  → media manifest → render → render verifier → publication record → commit
```

**The ranking record precedes the prose, and this ordering is load-bearing.** Writing first and
recording the rationale afterward permits an arbitrary order followed by a plausible
justification — which would read exactly like judgment while containing none. The record is the
deliberative input to the ranking prose, not retrospective paperwork.

The record and the ordering may be revised _together_ during editing — judgment is allowed to
change when the writing exposes a weak call. What is not allowed is manufacturing the reasoning
after the order is already fixed. The final record binds with the authoring manifest.

**Serial, owned by the lead context, never delegated:** `check_picks_ledger`,
`verify_prev_rank_claims`, and appends to `content/review-log.jsonl`.

### D1 — First three editions, then STOP for review

**Do not build every adapter, every desk, and the rest of the infrastructure before finding out
whether the intelligence improves the work.**

Once the source census and a _minimum safe projector_ exist, run three editions through the
complete loop:

**preseason → week-1 pre-kickoff preview → week-1 recap.**

That sequence is the smallest slice that exercises everything that matters: predictions made,
pre-kickoff exclusion enforced, first results absorbed, first ranking movement justified,
continuity carried, editing, media, rendering — and whether the league model visibly becomes more
informed across three consecutive editions.

**Build only the adapters those three editions require. Everything else fails closed.**

These become the first canonical editions if they pass. This is a vertical slice, not a
disposable benchmark.

**Then stop for review.** If the slice is not materially richer than what the old pipeline
produced, revise the source and desk contracts _before_ building the rest. This is the mechanism
that keeps temporal correctness subordinate to the product instead of becoming the project.

### D2 — Remaining archive

Weeks 2-17 recaps and the week-18 finale, sequentially, on the contracts D1 validated. Adapters
beyond the D1 set are built as the editions that need them arrive.

**Checkpoint after week 6:** synthesize `review-log.jsonl` into standing writer rules.

## Out of scope

- **2026 authoring.** Phase 0 preserves 2026 evidence; it writes no 2026 prose.
- Formal typed evidence hierarchies beyond the descriptor/bundle/adapter contract above, a
  validated ranking model with a selection gate, disposable benchmark editions, and a clean-room
  2026 rehearsal. Revisit if the audit finds classes the adopted contract cannot address.
- v2 redesign (deferred to in-season 2026).
- 2026 **in-season** readiness: live roster capture during the season and current-week detection
  (Phase 0 covers the pre-kickoff window only), preseason-2026 authoring,
  `compute_preseason_window` constants.
- `feat/analytics-owner-edge` — parked, unmerged, shadow-only.

## Acceptance

- **Phase 0:** every row of the minimum capture table has a working capture path — including an
  **offseason-capable transaction path**, which `fetch_sleeper.py:172` cannot provide; each
  artifact records `source`, `captured_at`, `known_at` semantics, content hash, and privacy
  boundary; re-running capture never overwrites a prior snapshot; raw private captures never
  leave their protected local boundary and are never copied wholesale into public artifacts,
  while policy-approved provenance-bound derivations may. A single snapshot of one source does
  **not** satisfy this phase.
- **Phase A:** the read-path census is reviewed and approved before any file changes; no active
  writing path can reach barred prose, proven by test — including generated artifacts
  (`team_profiles_summary`, `voice_bible_callbacks`); abstract grammar, templates, and
  anti-patterns intact; twelve handles match `data/2025/users.json`; **`analyze_chat.py` cannot
  run authoritatively** — quarantined or retired as a producer, or else using the rebound catalog
  and inside the provenance contract, so it can no longer overwrite analytics filenames the
  canonical builder consumes; the dormant `build_chat_context` media enrichment is removed or
  deliberately activated post-rebind, not left latent.
- **Phase B:** census reports 0 confirmed future entries (from 46) across both passes, and 0
  structurally unsliced H2H blocks (from 98); the leaf census reports zero unclassified fields
  and fires on planted leaks of each class including an undated aggregate; noninterference is
  byte-identical with detector-active positive controls; a clean rebuild reproduces every bundle;
  no consumer reads a full-season store directly; a legal week-1 preview bundle exists containing
  no week-1 outcomes and no final starters, on a descriptor cutoff **strictly before** the
  qualified first kickoff; **no bundle offers league media postdating its cutoff** — the
  invariant is "zero items whose _rebound_ `timestamp_utc` postdates the edition cutoff,"
  whatever count that yields (the pre-rebind figure of 966 of 1,205 is computed from a field
  wrong 1,202 times and is **not** a valid target); at least one non-2025
  canary edition compiles; `verify_h2h_claims` errors; suite green against the measured baseline
  of **343 passed / 2 skipped** (run at `c751b22` on 2026-08-01, 167s — verified, not inherited
  from memory); CI green on HEAD's own SHA.
- **Phase C:** twelve repertoires committed and Blake-approved; desks exist as committed commands
  reading only bundles; bake-off run and outcome recorded — scored on **ranking quality as well
  as prose**, and a candidate with better prose but weaker ranking judgment loses.
- **Media, end to end:** every rendered media node maps **one-to-one** to an approved
  per-edition manifest entry — no missing nodes, no extra nodes — matching on **both location
  and bytes**; every league-media entry binds **both** a protected source locator plus source
  SHA-256 **and** an approved publication derivative SHA-256 plus authorized publication location,
  with its transformation/redaction decision recorded; the renderer embeds only the publication
  derivative and no protected raw-source path appears in any rendered artifact (equal source and
  publish hashes are permitted where approval allows the original unchanged; a missing publish
  location is not); league assets are cutoff-safe and publication-approved; GIPHY and custom
  entries either satisfy the edition cutoff or carry an explicit `non_evidentiary_decoration`
  policy; GIPHY resolved results are persisted rather than re-resolved; custom assets hash-match
  and sit inside the authorized media root; a referenced but unresolved slot **fails**; no
  gitignored cache authorizes publication; and final publication binds the approved content, the
  media manifest, and the rendered artifact.
- **Media rebind (precondition to the above):** the catalog joins the repaired corpus on asset
  content hash plus filename/source provenance, with `message_id` unused as a join key; preserved
  descriptions rebind cleanly; the 255 uncatalogued assets are marked unavailable; rebound league
  media defaults to unreviewed with only approved items embeddable; only then is the catalog
  admitted as a bundle source.
- **Phase D — every edition:** passes the global content gate — verifier 0 errors AND
  `/edit-week` APPROVE AND renders clean AND as-if-realtime checklist clean, with approval bound
  to the **authoring manifest** (not the evidence bundle alone). Binary; no "APPROVE with notes."
- **Phase D — ranking gate, every edition:** a decision record exists for all twelve teams; every
  movement traces to evidence in that edition's bundle; no unexplained inversions; contradictions
  of prior judgment are acknowledged rather than silent; prior-edition ranking claims are graded
  rather than dropped; **Blake approves the ranking itself, separately from the prose.** An
  edition with clean facts and strong voice but unjustified ordering fails.
- **D1 product gate:** the three editions are produced end-to-end and reviewed **before** any
  further adapters, desks, or editions are built. If the slice is not materially richer than the
  old pipeline produced, source and desk contracts are revised before D2 begins. Passing D1 on
  temporal correctness alone is not passing.

## Open items

- Whether the audit surfaces leak classes beyond H2H, `historical_context`, and undated
  aggregates. If so, repair scope grows before Phase C.
- Which media-policy decisions the D1 editions actually force. Classification is demand-driven by
  design, so the first real answer arrives during D1 rather than before it.
- Beyond the minimum capture table, which _additional_ 2026 sources are worth preserving, and
  their `known_at` semantics. Capture is broad by policy; this question is about reach, not
  admission.
- Whether any pre-kickoff forward-looking source has a defensible `known_at`. If none does, the
  week-1 preview runs on reconstructed roster, draft, 2022-2024 history, pairings, chat, and
  preseason receipts only.
- Playoff (weeks 15-17) and finale contracts — needed before week 15, not before the first
  edition.
