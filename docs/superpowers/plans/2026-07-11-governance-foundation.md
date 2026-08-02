# Governance Foundation (Phase 1) — Implementation Plan

> Executed inline via superpowers:executing-plans (single-context). Effective spec: the v4.1 design doc alongside this plan.

## PART B — Phase 1 (Governance Foundation) — complete, verified, no placeholders

> **Executor:** `superpowers:executing-plans` (inline). Import `shared` via sys.path bootstrap; `save_json_canonical`; schemas **2020-12**; `python` 3.12; hermetic tests; commit per task.

### Task 1 — points / positive pool / ordinal cutoff

Files: create `scripts/starter_levels.py`, `scripts/tests/test_starter_levels.py`.

- [ ] **1.1** Test:

```python
from scripts.starter_levels import compute_fantasy_points, positive_pool, scores_of, ordinal_cutoff
def test_points_half_ppr():
    assert compute_fantasy_points({"pass_yd":300,"pass_td":2,"pass_int":1},{"pass_yd":0.04,"pass_td":4,"pass_int":-1})==19.0
def test_positive_pool_and_bridge():
    pool=positive_pool({"a":10.0,"b":0.0,"c":-3.0,"d":5.0})
    assert pool==[("a",10.0),("d",5.0)] and scores_of(pool)==[10.0,5.0]
def test_ordinal_cutoff():
    assert ordinal_cutoff([30.0,20.0,20.0,10.0],3)==20.0
    assert ordinal_cutoff([30.0,20.0],3)==20.0
    assert ordinal_cutoff([],3) is None
```

- [ ] **1.2** `python -m pytest scripts/tests/test_starter_levels.py -v` → FAIL. **1.3** Implement:

```python
"""Ex-post per-position starter-level benchmark (1-QB/12-team/0.5 PPR)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
def compute_fantasy_points(stats: dict, scoring: dict) -> float:
    return round(sum(float(v)*float(scoring.get(k,0.0)) for k,v in stats.items()), 2)
def positive_pool(points_by_player: dict):
    return sorted(((p,s) for p,s in points_by_player.items() if s is not None and s>0), key=lambda kv: kv[1], reverse=True)
def scores_of(pool): return [s for _,s in pool]
def ordinal_cutoff(sorted_scores, n):
    if not sorted_scores: return None
    return sorted_scores[n-1] if len(sorted_scores)>=n else sorted_scores[-1]
```

- [ ] **1.4** → PASS. **1.5** Commit `feat(governance): points/pool/cutoff (P1 T1)`.

### Task 2 — structured `classify_week` + artifact (config-hash) + literal fixture

Files: modify `scripts/starter_levels.py`; create `content/governance/starter_level_result.json`, `scripts/tests/fixtures/starter_levels_algofix.json`; extend tests. Result shape: `{tier, qualifying_slots, eligible_slots, applicable_cutoffs, flex_cutoff, score, reason}`.

- [ ] **2.1 Artifact** `content/governance/starter_level_result.json`:

```json
{
  "version": 1,
  "lens_id": "starter_level_result",
  "temporal_class": "realized-outcome",
  "semantics": "position_relative_finish_benchmark",
  "represents_unique_league_slots": false,
  "allocation_rule": "per_position_benchmark_no_refill",
  "method": "nth_ordinal_positive_score_cutoff_boundary_ties_inclusive",
  "league_config_id": "COMPUTED_IN_2.2",
  "candidate_universe_rule": "week-specific eligibility snapshot joined to qualified actual scoring for every NFL player eligible for a Jailyard starting slot; excludes metadata, ownership, started-lineups",
  "eligibility_timing": "as_of_week_lock",
  "participation_precedence": [
    "missing",
    "bye",
    "dnp",
    "zero",
    "negative",
    "scored"
  ],
  "dedicated_thresholds": {
    "QB": 12,
    "RB": 24,
    "WR": 36,
    "TE": 12,
    "K": 12,
    "DEF": 12,
    "DL": 12,
    "LB": 12,
    "DB": 12
  },
  "flex": { "positions": ["RB", "WR", "TE"], "band": 12 },
  "none_reasons": ["missing", "bye", "dnp", "zero", "negative", "below_cutoff"]
}
```

- [ ] **2.2** Compute immutable `league_config_id` (in `scripts/governance.py`, reused Task 3):

```python
import json, hashlib
def compute_league_config_id(league: dict) -> str:
    core = {"roster_positions": league["roster_positions"], "scoring_settings": league["scoring_settings"]}
    return "sha256:" + hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",",":")).encode()).hexdigest()
```

Set the artifact's `league_config_id = compute_league_config_id(load_json("data/2025/league.json"))`; test asserts equality.

- [ ] **2.3 Implement `classify_week`** (verified):

```python
from shared import load_json  # noqa: E402
_DEF = Path(__file__).resolve().parents[1]/"content"/"governance"/"starter_level_result.json"
_PART_NONE = ("missing","bye","dnp")
def load_definition(path: Path = _DEF) -> dict: return load_json(path, required=True)
def classify_week(universe: dict, defn: dict) -> dict:
    ded = defn["dedicated_thresholds"]; flexpos = set(defn["flex"]["positions"]); flexband = defn["flex"]["band"]
    cut = {}
    for pos, thr in ded.items():
        pts = {pid: u["points"] for pid, u in universe.items() if pos in u["positions"]}
        cut[pos] = ordinal_cutoff(scores_of(positive_pool(pts)), thr)
    res = {}
    for pid, u in universe.items():
        s = u["points"]; part = u.get("participation","scored"); elig = sorted(u["positions"])
        base = {"eligible_slots": elig, "applicable_cutoffs": {p: cut[p] for p in elig if cut.get(p) is not None},
                "score": s, "flex_cutoff": None, "qualifying_slots": []}
        if part in _PART_NONE: res[pid] = {**base, "tier":"none", "reason":part}; continue
        if s is None: res[pid] = {**base, "tier":"none", "reason":"missing"}; continue
        if s == 0: res[pid] = {**base, "tier":"none", "reason":"zero"}; continue
        if s < 0: res[pid] = {**base, "tier":"none", "reason":"negative"}; continue
        qual = [p for p in elig if cut.get(p) is not None and s >= cut[p]]
        if qual: res[pid] = {**base, "tier":"dedicated", "qualifying_slots": sorted(qual), "reason":"meets_position_cutoff"}
    fc = {pid: universe[pid]["points"] for pid, u in universe.items()
          if pid not in res and universe[pid]["points"] is not None and universe[pid]["points"] > 0
          and (set(universe[pid]["positions"]) & flexpos) and universe[pid].get("participation","scored") not in _PART_NONE}
    fcut = ordinal_cutoff(scores_of(positive_pool(fc)), flexband)
    flexids = {pid for pid, s in positive_pool(fc) if fcut is not None and s >= fcut}
    for pid in fc:
        u = universe[pid]; s = u["points"]; elig = sorted(u["positions"])
        base = {"eligible_slots": elig, "applicable_cutoffs": {p: cut[p] for p in elig if cut.get(p) is not None},
                "score": s, "flex_cutoff": fcut}
        res[pid] = ({**base, "tier":"flex", "qualifying_slots":["FLEX"], "reason":"meets_flex_cutoff"} if pid in flexids
                    else {**base, "tier":"none", "qualifying_slots":[], "reason":"below_cutoff"})
    for pid, u in universe.items():
        if pid in res: continue
        s = u["points"]; elig = sorted(u["positions"])
        res[pid] = {"eligible_slots": elig, "applicable_cutoffs": {p: cut[p] for p in elig if cut.get(p) is not None},
                    "score": s, "flex_cutoff": None, "tier":"none", "qualifying_slots":[], "reason":"below_cutoff"}
    return res
```

- [ ] **2.4 Tests** (verified green):

```python
from scripts.starter_levels import classify_week, load_definition, compute_league_config_id
DEF=load_definition()
def Uv(p,pos,part="scored"): return {"points":p,"positions":pos,"participation":part}
def test_dual_eligible_clears_both_no_refill():
    uni={"hunter":Uv(200.0,["DB","WR"])}; uni.update({f"wr{i}":Uv(65.0+i,["WR"]) for i in range(36)}); uni.update({f"db{i}":Uv(10.0+i,["DB"]) for i in range(12)})
    r=classify_week(uni,DEF); assert r["hunter"]["tier"]=="dedicated" and r["hunter"]["qualifying_slots"]==["DB","WR"]
def test_dual_eligible_clears_db_only():
    uni={"hunter":Uv(40.0,["DB","WR"])}; uni.update({f"wr{i}":Uv(65.0+i,["WR"]) for i in range(36)}); uni.update({f"db{i}":Uv(1.0+i,["DB"]) for i in range(12)})
    assert classify_week(uni,DEF)["hunter"]["qualifying_slots"]==["DB"]
def test_flex_is_deterministic_flex():
    uni={f"wr{i}":Uv(100.0-i,["WR"]) for i in range(36)}; uni.update({f"lw{i}":Uv(50.0-i,["WR"]) for i in range(20)})
    r=classify_week(uni,DEF); assert r["lw0"]["tier"]=="flex" and r["lw0"]["flex_cutoff"]==39.0
def test_participation_precedence_and_audit_retained():
    uni={"a":Uv(0.0,["QB"],"bye"),"b":Uv(0.0,["QB"],"dnp"),"c":Uv(0.0,["QB"]),"d":Uv(-2.0,["QB"]),"e":Uv(None,["QB"],"missing")}
    uni.update({f"q{i}":Uv(30.0-i,["QB"]) for i in range(12)})
    r=classify_week(uni,DEF); assert [r[k]["reason"] for k in "abcde"]==["bye","dnp","zero","negative","missing"] and r["c"]["applicable_cutoffs"]
def test_short_pool_all_positive_qualify():
    r=classify_week({"x":Uv(10.0,["QB"]),"y":Uv(5.0,["QB"])},DEF); assert r["x"]["tier"]=="dedicated" and r["y"]["tier"]=="dedicated"
def test_config_id_immutable_identity():
    assert DEF["league_config_id"]==compute_league_config_id(load_json("data/2025/league.json"))
```

- [ ] **2.5 Literal fixture** `scripts/tests/fixtures/starter_levels_algofix.json` (independently-authored `expected`; runs unconditionally; algorithm-only):

```json
{
  "version": 1,
  "generator": "scripts/starter_levels.py::classify_week",
  "input_manifest_sha256": "sha256:0f534042a533b6de7a9ac026c265a00440f13ef68301474440fe6580a270a312",
  "input": {
    "a": { "points": 20.0, "positions": ["QB"], "participation": "scored" },
    "b": { "points": 10.0, "positions": ["QB"], "participation": "scored" },
    "c": { "points": 0.0, "positions": ["QB"], "participation": "bye" },
    "d": { "points": -3.0, "positions": ["QB"], "participation": "scored" },
    "e": { "points": 0.0, "positions": ["QB"], "participation": "scored" },
    "f": { "points": null, "positions": ["QB"], "participation": "missing" },
    "db": { "points": 5.0, "positions": ["DB"], "participation": "scored" },
    "hunter": {
      "points": 50.0,
      "positions": ["DB", "WR"],
      "participation": "scored"
    }
  },
  "expected": {
    "a": {
      "eligible_slots": ["QB"],
      "applicable_cutoffs": { "QB": 10.0 },
      "score": 20.0,
      "flex_cutoff": null,
      "qualifying_slots": ["QB"],
      "tier": "dedicated",
      "reason": "meets_position_cutoff"
    },
    "b": {
      "eligible_slots": ["QB"],
      "applicable_cutoffs": { "QB": 10.0 },
      "score": 10.0,
      "flex_cutoff": null,
      "qualifying_slots": ["QB"],
      "tier": "dedicated",
      "reason": "meets_position_cutoff"
    },
    "c": {
      "eligible_slots": ["QB"],
      "applicable_cutoffs": { "QB": 10.0 },
      "score": 0.0,
      "flex_cutoff": null,
      "qualifying_slots": [],
      "tier": "none",
      "reason": "bye"
    },
    "d": {
      "eligible_slots": ["QB"],
      "applicable_cutoffs": { "QB": 10.0 },
      "score": -3.0,
      "flex_cutoff": null,
      "qualifying_slots": [],
      "tier": "none",
      "reason": "negative"
    },
    "e": {
      "eligible_slots": ["QB"],
      "applicable_cutoffs": { "QB": 10.0 },
      "score": 0.0,
      "flex_cutoff": null,
      "qualifying_slots": [],
      "tier": "none",
      "reason": "zero"
    },
    "f": {
      "eligible_slots": ["QB"],
      "applicable_cutoffs": { "QB": 10.0 },
      "score": null,
      "flex_cutoff": null,
      "qualifying_slots": [],
      "tier": "none",
      "reason": "missing"
    },
    "db": {
      "eligible_slots": ["DB"],
      "applicable_cutoffs": { "DB": 5.0 },
      "score": 5.0,
      "flex_cutoff": null,
      "qualifying_slots": ["DB"],
      "tier": "dedicated",
      "reason": "meets_position_cutoff"
    },
    "hunter": {
      "eligible_slots": ["DB", "WR"],
      "applicable_cutoffs": { "DB": 5.0, "WR": 50.0 },
      "score": 50.0,
      "flex_cutoff": null,
      "qualifying_slots": ["DB", "WR"],
      "tier": "dedicated",
      "reason": "meets_position_cutoff"
    }
  }
}
```

Fixture test:

```python
import json, hashlib
def test_algofix_manifest_and_expected():
    fix=load_json("scripts/tests/fixtures/starter_levels_algofix.json")
    canon=json.dumps(fix["input"],sort_keys=True,separators=(",",":"))
    assert "sha256:"+hashlib.sha256(canon.encode()).hexdigest()==fix["input_manifest_sha256"]
    assert classify_week(fix["input"],DEF)==fix["expected"]
```

- [ ] **2.6 Schema** `scripts/schemas/starter_level_result.schema.json` (body in **§Schemas**) + validation test. **2.7** Commit (P1 T2).

### Task 3 — complete registry + fail-closed validators (verified 11-case matrix) + schema

Files: create `content/governance/claim_registry.json`; extend `scripts/governance.py`, `scripts/tests/test_governance.py`. Predicates encode the **asserted proposition**; subject via `subject_refs`, cutoff via context (not duplicated).

- [ ] **3.1 Artifact** `content/governance/claim_registry.json`:

```json
{
  "version": 1,
  "lens_catalog": {
    "starter_level_result": {
      "temporal_class": "realized-outcome",
      "value_shape": "classification{dedicated|flex|none}"
    },
    "nfl_actuals": {
      "temporal_class": "realized-outcome",
      "value_shape": "per-player weekly stat/points"
    },
    "injury_status": {
      "temporal_class": "realized-outcome",
      "value_shape": "weekly active/inactive designation"
    },
    "dynasty_1qb_value_snapshot": {
      "temporal_class": "value-snapshot",
      "value_shape": "per-player 1QB value+rank"
    },
    "named_source_utterance": {
      "temporal_class": "realized-outcome",
      "value_shape": "quote+source+timestamp"
    },
    "roster_composition": {
      "temporal_class": "static-roster",
      "value_shape": "per-week roster/slots"
    },
    "realized_usage": {
      "temporal_class": "realized-outcome",
      "value_shape": "per-week started/among"
    },
    "disclosed_forecast": {
      "temporal_class": "forecast",
      "value_shape": "bounded resolvable prediction"
    }
  },
  "claim_types": {
    "ex_post_starter_result": {
      "admissible_lens_ids": ["starter_level_result"],
      "allowed_temporal_orientations": ["realized-outcome"],
      "predicate_schema": {
        "type": "object",
        "required": ["week", "asserted_tier"],
        "properties": {
          "week": { "type": "integer" },
          "asserted_tier": { "enum": ["dedicated", "flex", "none"] }
        },
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "position_or_slot",
        "predicate",
        "league_config_id"
      ],
      "no_provider_behavior": "REVISE"
    },
    "weekly_performance": {
      "admissible_lens_ids": ["nfl_actuals"],
      "allowed_temporal_orientations": ["realized-outcome"],
      "predicate_schema": {
        "type": "object",
        "required": ["week", "metric", "asserted_operator", "asserted_value"],
        "properties": {
          "asserted_operator": { "enum": ["gt", "lt", "eq", "gte", "lte"] },
          "asserted_value": { "type": "number" }
        },
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "predicate"
      ],
      "no_provider_behavior": "REVISE"
    },
    "idp_context": {
      "admissible_lens_ids": ["nfl_actuals"],
      "allowed_temporal_orientations": ["realized-outcome"],
      "predicate_schema": {
        "type": "object",
        "required": [
          "week",
          "position",
          "metric",
          "asserted_operator",
          "asserted_value"
        ],
        "properties": {
          "asserted_operator": { "enum": ["gt", "lt", "eq", "gte", "lte"] }
        },
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "position_or_slot",
        "predicate"
      ],
      "no_provider_behavior": "REVISE"
    },
    "health_availability": {
      "admissible_lens_ids": ["injury_status"],
      "allowed_temporal_orientations": ["realized-outcome"],
      "predicate_schema": {
        "type": "object",
        "required": ["week", "asserted_status"],
        "properties": {
          "asserted_status": {
            "enum": ["active", "inactive", "questionable", "out", "ir", "dnp"]
          }
        },
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "predicate"
      ],
      "no_provider_behavior": "REVISE",
      "note": "ex-post only in P1; pregame/preseason as-of snapshots deferred to P2"
    },
    "dynasty_value": {
      "admissible_lens_ids": ["dynasty_1qb_value_snapshot"],
      "allowed_temporal_orientations": ["value-snapshot"],
      "predicate_schema": {
        "type": "object",
        "required": ["asserted_operator", "asserted_value"],
        "properties": {
          "asserted_operator": { "enum": ["gt", "lt", "eq", "gte", "lte"] }
        },
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "predicate"
      ],
      "no_provider_behavior": "REVISE"
    },
    "lineup_eligibility": {
      "admissible_lens_ids": ["roster_composition"],
      "allowed_temporal_orientations": ["static-roster"],
      "predicate_schema": {
        "type": "object",
        "required": ["week", "asserted_slot", "asserted_eligible"],
        "properties": { "asserted_eligible": { "type": "boolean" } },
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "predicate"
      ],
      "no_provider_behavior": "REVISE"
    },
    "room_depth": {
      "requires_decomposition": true,
      "admissible_lens_ids": ["roster_composition", "realized_usage"],
      "allowed_temporal_orientations": ["static-roster", "realized-outcome"],
      "predicate_schema": { "type": "object" },
      "required_context_fields": [
        "subject_refs",
        "position_or_slot",
        "knowledge_cutoff"
      ],
      "no_provider_behavior": "REVISE"
    },
    "roster_efficiency": {
      "requires_decomposition": true,
      "admissible_lens_ids": ["dynasty_1qb_value_snapshot", "realized_usage"],
      "allowed_temporal_orientations": ["realized-outcome"],
      "predicate_schema": { "type": "object" },
      "required_context_fields": ["subject_refs", "knowledge_cutoff"],
      "no_provider_behavior": "REVISE"
    },
    "comparative": {
      "admissible_lens_ids": [
        "starter_level_result",
        "nfl_actuals",
        "dynasty_1qb_value_snapshot"
      ],
      "allowed_temporal_orientations": ["realized-outcome", "value-snapshot"],
      "predicate_schema": {
        "type": "object",
        "required": [
          "operator",
          "base_lens_id",
          "comparison_universe",
          "asserted_relation"
        ],
        "properties": {
          "operator": { "enum": ["gt", "lt", "eq", "rank_within"] },
          "comparison_universe": { "type": "array", "minItems": 2 }
        },
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "comparison_universe",
        "knowledge_cutoff",
        "predicate"
      ],
      "no_provider_behavior": "REVISE"
    },
    "attributed_opinion": {
      "admissible_lens_ids": ["named_source_utterance"],
      "allowed_temporal_orientations": ["realized-outcome"],
      "predicate_schema": {
        "type": "object",
        "required": ["source", "utterance", "said_at"],
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "predicate"
      ],
      "no_provider_behavior": "REVISE"
    },
    "forward_pick": {
      "admissible_lens_ids": ["disclosed_forecast"],
      "allowed_temporal_orientations": ["forecast"],
      "predicate_schema": {
        "type": "object",
        "required": ["target_event", "selection"],
        "additionalProperties": false
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "predicate"
      ],
      "no_provider_behavior": "admit_as_forecast"
    },
    "ex_ante_startability": {
      "admissible_lens_ids": [],
      "allowed_temporal_orientations": ["forecast"],
      "predicate_schema": {
        "type": "object",
        "required": ["asserted_relation"]
      },
      "required_context_fields": ["subject_refs", "knowledge_cutoff"],
      "no_provider_behavior": "REVISE_or_attribute"
    },
    "other_evaluative": {
      "admissible_lens_ids": [],
      "allowed_temporal_orientations": [
        "realized-outcome",
        "value-snapshot",
        "forecast"
      ],
      "registered_subtypes": {
        "unit_strength_claim": {
          "lens_id": "starter_level_result",
          "predicate_required": ["position", "asserted_relation"]
        }
      },
      "predicate_schema": {
        "type": "object",
        "required": ["subtype", "lens_id", "predicate"]
      },
      "required_context_fields": [
        "subject_refs",
        "knowledge_cutoff",
        "subtype",
        "predicate"
      ],
      "no_provider_behavior": "REVISE"
    }
  }
}
```

- [ ] **3.2 Validators** (verified 11-case matrix) in `scripts/governance.py`:

```python
_GOV = Path(__file__).resolve().parents[1]/"content"/"governance"
_SCH = Path(__file__).resolve().parent/"schemas"
def load_registry(path: Path = _GOV/"claim_registry.json") -> dict: return load_json(path, required=True)
def admissible_lenses(registry, claim_type):
    e = registry["claim_types"].get(claim_type); return list(e["admissible_lens_ids"]) if e else []
def validate_claim_lens(registry, claim_type, lens_id, temporal_orientation, subtype=None, predicate=None):
    types, cat = registry["claim_types"], registry["lens_catalog"]
    e = types.get(claim_type)
    if e is None: return False, f"unregistered claim_type: {claim_type}"
    if temporal_orientation not in e["allowed_temporal_orientations"]: return False, f"orientation {temporal_orientation} not allowed"
    if e.get("requires_decomposition"): return False, "requires_decomposition into atomic single-lens premises"
    if claim_type == "comparative":
        base = (predicate or {}).get("base_lens_id")
        if base not in cat: return False, "comparative base_lens_id not in catalog"
        if base != lens_id: return False, "comparative base_lens_id must equal selected lens"
        if cat[base]["temporal_class"] != temporal_orientation: return False, "comparative base temporal_class incompatible with orientation"
        return True, "ok"
    if claim_type == "other_evaluative":
        sub = e["registered_subtypes"].get(subtype)
        if not sub: return False, f"other_evaluative subtype not registered: {subtype}"
        if sub["lens_id"] != lens_id: return False, "subtype lens mismatch"
        missing = [f for f in sub.get("predicate_required",[]) if f not in (predicate or {})]
        if missing: return False, f"subtype predicate missing {missing}"
        return True, "ok"
    if not e["admissible_lens_ids"]: return False, f"no admissible lens; {e['no_provider_behavior']}"
    if lens_id not in e["admissible_lens_ids"]: return False, f"lens {lens_id} not admissible"
    return True, "ok"
```

- [ ] **3.3 Tests** (verified) `scripts/tests/test_governance.py`:

```python
from scripts.governance import load_registry, admissible_lenses, validate_claim_lens
R=load_registry()
def ok(*a,**k): return validate_claim_lens(R,*a,**k)[0]
def test_ex_post_admits_starter_level(): assert "starter_level_result" in admissible_lenses(R,"ex_post_starter_result")
def test_unregistered_type(): assert not ok("made_up","x","realized-outcome")
def test_wrong_lens(): assert not ok("ex_post_starter_result","nfl_actuals","realized-outcome")
def test_disallowed_orientation(): assert not ok("ex_post_starter_result","starter_level_result","forecast")
def test_requires_decomposition(): assert not ok("roster_efficiency","dynasty_1qb_value_snapshot","realized-outcome")
def test_comparative_base_rules():
    assert ok("comparative","nfl_actuals","realized-outcome",predicate={"base_lens_id":"nfl_actuals"})
    assert not ok("comparative","nfl_actuals","realized-outcome",predicate={"base_lens_id":"dynasty_1qb_value_snapshot"})
    assert not ok("comparative","dynasty_1qb_value_snapshot","realized-outcome",predicate={"base_lens_id":"dynasty_1qb_value_snapshot"})
def test_other_evaluative_subtype():
    assert not ok("other_evaluative","starter_level_result","realized-outcome",subtype="mystery")
    assert ok("other_evaluative","starter_level_result","realized-outcome",subtype="unit_strength_claim",predicate={"position":"QB","asserted_relation":"weak"})
    assert not ok("other_evaluative","starter_level_result","realized-outcome",subtype="unit_strength_claim",predicate={"position":"QB"})
def test_forward_pick_admits_forecast(): assert ok("forward_pick","disclosed_forecast","forecast")
```

- [ ] **3.4 Schema** `scripts/schemas/claim_registry.schema.json` (body in **§Schemas**) + validation test. **3.5** Commit (P1 T3).

### Task 4 — claim-context: strict UTC + normalized hash + predicate application + config-id validation

Files: modify `scripts/governance.py`; extend tests.

- [ ] **4.1 Implement** (verified):

```python
import re  # noqa: E402
from datetime import datetime  # noqa: E402
import jsonschema  # noqa: E402
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_LCID = re.compile(r"^sha256:[0-9a-f]{64}$")
_CANON_SETS = ("subject_refs","comparison_universe")
def parse_utc(s: str) -> str:
    if not isinstance(s,str) or not _TS.match(s): raise ValueError("must be YYYY-MM-DDTHH:MM:SSZ (UTC whole-seconds)")
    datetime.strptime(s,"%Y-%m-%dT%H:%M:%SZ"); return s
def _canon(ctx: dict) -> dict:
    out={}
    for k,v in ctx.items():
        if k=="knowledge_cutoff" and isinstance(v,str): out[k]=parse_utc(v)
        elif k in _CANON_SETS and isinstance(v,list): out[k]=sorted(v,key=lambda x: json.dumps(x,sort_keys=True))
        else: out[k]=v
    return out
def canonicalize_context(ctx: dict) -> str:
    return json.dumps(_canon(ctx), sort_keys=True, separators=(",",":"), ensure_ascii=False)
def context_hash(ctx: dict) -> str:
    return "sha256:"+hashlib.sha256(canonicalize_context(ctx).encode()).hexdigest()
def validate_claim_context(ctx: dict):
    errs=[]; reg=load_registry()
    schema=load_json(_SCH/"claim_context.schema.json", required=True)
    for e in jsonschema.Draft202012Validator(schema).iter_errors(ctx):
        errs.append((".".join(str(p) for p in e.absolute_path) or "(root)")+": "+e.message)
    ct=ctx.get("claim_type"); entry=reg["claim_types"].get(ct) if ct else None
    if ct is not None and entry is None: return False, errs+[f"unregistered claim_type: {ct}"]
    if entry:
        for f in entry["required_context_fields"]:
            if f not in ctx: errs.append(f"{f}: required for {ct}")
        if "knowledge_cutoff" in ctx:
            try: parse_utc(ctx["knowledge_cutoff"])
            except ValueError as ex: errs.append(f"knowledge_cutoff: {ex}")
        if "league_config_id" in ctx and not _LCID.match(str(ctx["league_config_id"])):
            errs.append("league_config_id: must be sha256:<64hex>")
        for e in jsonschema.Draft202012Validator(entry["predicate_schema"]).iter_errors(ctx.get("predicate") or {}):
            errs.append("predicate: "+e.message)
        ok,why=validate_claim_lens(reg,ct,ctx.get("lens_id"),ctx.get("temporal_orientation"),ctx.get("subtype"),ctx.get("predicate"))
        if not ok: errs.append(why)
    return (len(errs)==0), errs
```

- [ ] **4.2 Tests** (verified):

```python
import pytest
from scripts.governance import parse_utc, context_hash, validate_claim_context
def Cx(**k):
    b={"subject_refs":[{"type":"player","id":"4984"}],"claim_type":"ex_post_starter_result","lens_id":"starter_level_result",
       "temporal_orientation":"realized-outcome","knowledge_cutoff":"2025-09-08T17:00:00Z","position_or_slot":"QB",
       "predicate":{"week":1,"asserted_tier":"dedicated"},"league_config_id":"sha256:"+"a"*64}
    b.update(k); return b
def test_parse_utc_strict():
    assert parse_utc("2025-09-08T17:00:00Z")=="2025-09-08T17:00:00Z"
    for bad in ["2025-09-08T17:00:00.500Z","2025-09-08T17:00:00+00:00","not-a-date","2025-13-99T99:99:99Z"]:
        with pytest.raises(ValueError): parse_utc(bad)
def test_hash_order_invariant():
    assert context_hash(Cx(subject_refs=[{"type":"player","id":"1"},{"type":"player","id":"2"}]))==\
           context_hash(Cx(subject_refs=[{"type":"player","id":"2"},{"type":"player","id":"1"}]))
def test_valid_and_failures():
    assert validate_claim_context(Cx())[0]
    bad=Cx(); del bad["knowledge_cutoff"]; assert not validate_claim_context(bad)[0]
    assert not validate_claim_context(Cx(predicate={"week":1}))[0]              # missing asserted_tier
    assert not validate_claim_context(Cx(league_config_id="sha256:deadbeef"))[0]  # bad config-id
```

- [ ] **4.3 Schema** `scripts/schemas/claim_context.schema.json` (body in **§Schemas**) + test. **4.4** Commit (P1 T4).

### Task 5 — complete fail-closed coverage over real files; `/picks/*/spread`→forecast; conflict fail-closed

Files: create `content/governance/governed_fields.json`, `scripts/tests/test_governed_coverage.py`; modify `scripts/governance.py`, `scripts/tests/conftest.py`.

- [ ] **5.1 Artifact** `content/governance/governed_fields.json`:

```json
{
  "version": 1,
  "week": {
    "authorial_prose": [
      "/essay",
      "/rankings/*/blurb",
      "/confessionals/*/text",
      "/mailbag/*/question",
      "/mailbag/*/answer",
      "/bits/*/title",
      "/bits/*/text",
      "/picks/*/blurb",
      "/media_slots/*/alt_text"
    ],
    "forward_pick": [
      "/picks/*/pick",
      "/picks/*/spread",
      "/special_picks/underdog_lock",
      "/special_picks/stay_away",
      "/special_picks/teaser"
    ],
    "structured_fact": [
      "/rankings/*/team_name",
      "/rankings/*/owner",
      "/rankings/*/record",
      "/rankings/*/rank",
      "/rankings/*/prev_rank",
      "/rankings/*/movement",
      "/confessionals/*/team_name",
      "/picks/*/home",
      "/picks/*/away",
      "/meta/picks_ledger/*/cumulative_record",
      "/meta/picks_ledger/*/lock",
      "/meta/picks_ledger/*/stay_away",
      "/meta/picks_ledger/*/straight_up",
      "/meta/picks_ledger/*/upset_watch"
    ],
    "control_metadata": [
      "/picks/*/tag",
      "/meta/generated_by",
      "/meta/season",
      "/meta/type",
      "/meta/week",
      "/media_slots/*/intent",
      "/media_slots/*/slot_id",
      "/media_slots/*/source/type",
      "/media_slots/*/source/search_query",
      "/media_slots/*/source/fallback_query"
    ]
  },
  "preseason": {
    "authorial_prose": [
      "/essay",
      "/rankings/*/blurb",
      "/media_slots/*/alt_text"
    ],
    "evaluative_label": ["/rankings/*/tier"],
    "structured_fact": [
      "/rankings/*/team_name",
      "/rankings/*/owner",
      "/rankings/*/rank"
    ],
    "control_metadata": [
      "/media_slots/*/intent",
      "/media_slots/*/slot_id",
      "/media_slots/*/source/type",
      "/media_slots/*/source/search_query",
      "/media_slots/*/source/fallback_query",
      "/meta/generated_by",
      "/meta/season",
      "/meta/type",
      "/meta/threads/*/id",
      "/meta/threads/*/opened",
      "/meta/threads/*/status",
      "/meta/threads/*/last_touched",
      "/meta/threads/*/summary"
    ]
  }
}
```

- [ ] **5.2 Implement** (verified; conflict fail-closed):

```python
def load_governed_fields(path: Path = _GOV/"governed_fields.json") -> dict: return load_json(path, required=True)
def _match(pattern: str, pointer: str) -> bool:
    p, q = pattern.strip("/").split("/"), pointer.strip("/").split("/")
    return len(p)==len(q) and all(a=="*" or a==b for a,b in zip(p,q))
def field_class(reg: dict, piece_kind: str, pointer: str):
    ms = [(sum(1 for s in pat.split("/") if s!="*"), cls)
          for cls, pats in reg.get(piece_kind,{}).items() if isinstance(pats,list)
          for pat in pats if _match(pat,pointer)]
    if not ms: return None
    best = max(s for s,_ in ms); top = {c for s,c in ms if s==best}
    if len(top)>1: raise ValueError(f"ambiguous classification for {pointer}: {sorted(top)}")
    return next(c for s,c in ms if s==best)
def _leaf_pointers(o, p=""):
    if isinstance(o,dict):
        for k,v in o.items(): yield from _leaf_pointers(v,p+"/"+k)
    elif isinstance(o,list):
        for v in o: yield from _leaf_pointers(v,p+"/*")
    else: yield p
def coverage_check(reg: dict, piece_kind: str, content_obj: dict):
    unc=[]
    for ptr in set(_leaf_pointers(content_obj)):
        try:
            if field_class(reg,piece_kind,ptr) is None: unc.append(ptr)
        except ValueError as ex: unc.append(str(ex))
    return (len(unc)==0), sorted(unc)
```

- [ ] **5.3 Tests** `scripts/tests/test_governed_coverage.py` — **over every real file**:

```python
import glob, json
from scripts.governance import load_governed_fields, field_class, coverage_check
REG=load_governed_fields()
def test_every_week_leaf_covered():
    for fp in glob.glob("content/weeks/week*_content.json"):
        ok,unc=coverage_check(REG,"week",json.load(open(fp,encoding="utf-8"))); assert ok, f"{fp}: {unc}"
def test_preseason_covered():
    ok,unc=coverage_check(REG,"preseason",json.load(open("content/preseason-2025/preseason_content.json",encoding="utf-8"))); assert ok, unc
def test_unknown_leaf_fails_closed():
    ok,unc=coverage_check(REG,"week",{"essay":"x","surprise":{"z":"y"}}); assert not ok and any("/surprise/z" in u for u in unc)
def test_spread_and_special_picks_are_forecast():
    assert field_class(REG,"week","/picks/2/spread")=="forward_pick" and field_class(REG,"week","/special_picks/teaser")=="forward_pick"
def test_equal_specificity_conflict_fails_closed():
    ok,_=coverage_check({"week":{"authorial_prose":["/x/*"],"structured_fact":["/x/*"]}},"week",{"x":{"y":"z"}}); assert not ok
```

- [ ] **5.4** → PASS. **5.5** Add `REPO_ROOT/"content"/"governance"` to the watched tuple in `scripts/tests/conftest.py`. **5.6 Schema** `governed_fields.schema.json` (body in **§Schemas**). **5.7** Commit (P1 T5).

### Task 6 — temporal policy (uniform `first_known_at≤cutoff`) + testable canonical hash + lens_providers

Files: create `content/governance/temporal_policy.json`, `content/governance/lens_providers.json`; extend tests.

- [ ] **6.1 Artifact** `content/governance/temporal_policy.json`:

```json
{
  "version": 1,
  "admissibility_rule": "first_known_at <= knowledge_cutoff",
  "classes": {
    "forecast": {
      "effective_at": "predicted period",
      "first_known_at_derivation": "immutable snapshot publication",
      "enforced_at": "P2"
    },
    "realized-outcome": {
      "effective_at": "event period",
      "first_known_at_derivation": "event conclusion",
      "enforced_at": "P2"
    },
    "value-snapshot": {
      "effective_at": "snapshot effective date",
      "first_known_at_derivation": "capture time; backfills keep effective_at, take capture as first_known_at",
      "enforced_at": "P2"
    },
    "static-roster": {
      "effective_at": "week",
      "first_known_at_derivation": "week lock",
      "enforced_at": "P2"
    }
  }
}
```

- [ ] **6.2 Implement**:

```python
def load_temporal_policy(path: Path = _GOV/"temporal_policy.json") -> dict: return load_json(path, required=True)
def is_admissible(first_known_at: str, knowledge_cutoff: str) -> bool:
    return parse_utc(first_known_at) <= parse_utc(knowledge_cutoff)
def policy_hash(policy: dict) -> str:
    return "sha256:"+hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def load_lens_providers(path: Path = _GOV/"lens_providers.json") -> dict: return load_json(path, required=True)
```

- [ ] **6.3 Tests**:

```python
from scripts.governance import is_admissible, policy_hash, load_lens_providers, load_temporal_policy
def test_admissibility_uniform():
    assert is_admissible("2025-09-04T00:00:00Z","2025-09-08T17:00:00Z")
    assert not is_admissible("2025-09-09T00:00:00Z","2025-09-08T17:00:00Z")   # backfill known after cutoff
def test_policy_hash_canonical_testable():
    assert policy_hash({"a":1})==policy_hash({"a":1}) and policy_hash({"a":1})!=policy_hash({"a":2})
def test_policy_uniform_rule():
    assert load_temporal_policy()["admissibility_rule"]=="first_known_at <= knowledge_cutoff"
def test_lens_providers_empty():
    assert load_lens_providers()=={"version":1,"providers":{}}
```

- [ ] **6.4** `content/governance/lens_providers.json` = `{"version":1,"providers":{}}`; schemas `temporal_policy.schema.json`, `lens_providers.schema.json` (bodies in **§Schemas**). **6.5** Commit (P1 T6).

### Task 7 — hard completion seam (named script + deterministic clean-state gate)

- [ ] **7.1** Focused: `python -m pytest scripts/tests/test_starter_levels.py scripts/tests/test_governance.py scripts/tests/test_governed_coverage.py -v` → all PASS.
- [ ] **7.2 Named schema-validation script** `scripts/validate_governance_artifacts.py`:

```python
"""Validate every committed governance artifact against its schema; exit 1 on any error."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsonschema
from shared import load_json
PAIRS = ["starter_level_result","claim_registry","governed_fields","temporal_policy","lens_providers"]
def main() -> int:
    errs=0
    for name in PAIRS:
        obj=load_json(Path("content/governance")/f"{name}.json", required=True)
        schema=load_json(Path("scripts/schemas")/f"{name}.schema.json", required=True)
        for e in jsonschema.Draft202012Validator(schema).iter_errors(obj):
            print(f"[{name}] {list(e.absolute_path)}: {e.message}"); errs+=1
    print("OK" if errs==0 else f"{errs} errors"); return 1 if errs else 0
if __name__=="__main__": raise SystemExit(main())
```

Run `python scripts/validate_governance_artifacts.py` → prints `OK`, exit 0.

- [ ] **7.3** Real-file coverage over all six `week*_content.json` + preseason → 0 uncovered.
- [ ] **7.4** Full suite `python -m pytest scripts/tests/ -v` → green.
- [ ] **7.5 Deterministic clean-state gate:** `git status --porcelain` must show **no unexpected** staged/unstaged/untracked entries — every path is a planned Phase-1 commit target or the allowlisted user-owned `chatgpt-ignore/`; **fail otherwise** (not merely print). Report `git diff --stat`, commit list, and `sha256` of each new `content/governance/*.json` + `scripts/schemas/*.schema.json`. **STOP for explicit review before Phase 2.**

### §Schemas — the six bodies (all valid 2020-12; each verified to accept its artifact)

```json
// scripts/schemas/starter_level_result.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "version",
    "lens_id",
    "semantics",
    "represents_unique_league_slots",
    "allocation_rule",
    "method",
    "league_config_id",
    "dedicated_thresholds",
    "flex",
    "none_reasons"
  ],
  "properties": {
    "version": { "type": "integer" },
    "lens_id": { "const": "starter_level_result" },
    "semantics": { "type": "string" },
    "represents_unique_league_slots": { "type": "boolean" },
    "allocation_rule": { "type": "string" },
    "method": { "type": "string" },
    "league_config_id": {
      "type": "string",
      "pattern": "^sha256:[0-9a-f]{64}$"
    },
    "dedicated_thresholds": {
      "type": "object",
      "additionalProperties": { "type": "integer" }
    },
    "flex": { "type": "object", "required": ["positions", "band"] },
    "none_reasons": { "type": "array" }
  }
}
```

```json
// scripts/schemas/claim_registry.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["version", "lens_catalog", "claim_types"],
  "properties": {
    "version": { "type": "integer" },
    "lens_catalog": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["temporal_class", "value_shape"]
      }
    },
    "claim_types": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": [
          "admissible_lens_ids",
          "allowed_temporal_orientations",
          "predicate_schema",
          "required_context_fields",
          "no_provider_behavior"
        ]
      }
    }
  }
}
```

```json
// scripts/schemas/claim_context.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "subject_refs",
    "claim_type",
    "lens_id",
    "knowledge_cutoff",
    "temporal_orientation"
  ],
  "properties": {
    "subject_refs": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "object", "required": ["type", "id"] }
    },
    "claim_type": { "type": "string" },
    "lens_id": { "type": "string" },
    "knowledge_cutoff": { "type": "string" },
    "temporal_orientation": { "type": "string" },
    "predicate": { "type": "object" },
    "league_config_id": { "type": "string" },
    "comparison_universe": { "type": "array" },
    "position_or_slot": { "type": "string" },
    "subtype": { "type": "string" },
    "target_period": { "type": "string" }
  }
}
```

```json
// scripts/schemas/governed_fields.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["version", "week", "preseason"],
  "properties": { "version": { "type": "integer" } },
  "patternProperties": {
    "^(week|preseason)$": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "items": { "type": "string", "pattern": "^/" }
      }
    }
  }
}
```

```json
// scripts/schemas/temporal_policy.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["version", "admissibility_rule", "classes"],
  "properties": {
    "version": { "type": "integer" },
    "admissibility_rule": { "const": "first_known_at <= knowledge_cutoff" },
    "classes": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": {
        "type": "object",
        "required": ["effective_at", "first_known_at_derivation", "enforced_at"]
      }
    }
  }
}
```

```json
// scripts/schemas/lens_providers.schema.json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["version", "providers"],
  "properties": {
    "version": { "type": "integer" },
    "providers": { "type": "object" }
  }
}
```

Each Task's schema step writes the corresponding body above + a `Draft202012Validator.check_schema` + artifact-passes test.

### Self-review

No prose-described tests remain — Tasks 1–7 carry real code, real artifacts, six real schema bodies, exact commands, expected pass/fail, and commits. Signatures legal; audit shape retained on every tier; participation precedence operational; fixture `expected` literal + manifest-hashed (non-circular); predicates encode the asserted proposition without duplicating subject/cutoff; comparative base==lens∈catalog + temporal-compatible; `other_evaluative` subtype lens **and** predicate validated; composite types force decomposition; strict whole-second UTC + normalized hashing; `league_config_id` computed + format-validated; `/picks/*/spread`=forward_pick; conflicts fail closed; coverage over real files; Task-7 gate deterministic. All executed read-only and matched. Deferrals (DB/scoring/aggregation/NLP/optional-source) unchanged.

---

## PHASE 0 — Execution preflight (after explicit approval, before Task 1)

1. **Worktree first** — branch+worktree off `main` via `superpowers:using-git-worktrees`; all writes inside it.
2. **Materialize authoritative v4.1** (baseline + Part A′, A′ wins) → `docs/superpowers/specs/2026-07-11-jailyard-evidence-reconciliation-design.md`; this plan → `docs/superpowers/plans/2026-07-11-governance-foundation.md`. Compute a **new full-artifact sha256 each**; keep `FE03786A` only as the historical-baseline line.
3. **Persistence-diff checkpoint** — show docs diff + v4.1/plan hashes; confirm which are authorized; **dedicated documentation commit** (no code).
4. Confirm clean scope; **preserve untracked user-owned `chatgpt-ignore/`**.
5. Run the **complete baseline suite**; on any baseline failure **stop and surface it**.
6. **Checkpoint before Task 1.**

_No DB, no evidence scoring, no confidence aggregation, no deterministic-NLP completeness, no optional-source ingestion before M2._
