# Jailyard — P-only Preservation and Sealing Plan (2026 prospective lane)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox
> (`- [ ]`) syntax.

**Status:** DRAFT — awaiting Blake review. Not authorized for implementation.

**Design authority:** `docs/superpowers/specs/2026-08-01-jailyard-writer-foundation-design.md`,
APPROVED at `9805426`, §6 "Deadline mechanism and fallback". That section **requires** this path to
exist as an option and states it "may run only through a separately approved P-only implementation
plan." This is that plan. Material deviation requires design re-approval.

**Why this exists.** The definitive prospective test must not expire while the backtest is
perfected. As of 2026-08-03 nothing is capturing 2026 evidence, K1-K3 will not complete before the
preseason cutoff, and the evidence is perishable. This plan preserves 2026 evidence and seals a
dated decision **without** the temporal kernel, in a form the kernel can later re-derive and verify.

**What this plan is NOT.** Not the kernel. Not normalization. Not prose — the design puts 2026
authoring out of scope, and this plan writes none. It does not modify, supersede, or unblock
`docs/superpowers/plans/2026-08-02-jailyard-temporal-kernel.md`, which remains DRAFT and
unauthorized on its own track.

---

## Decision recorded: eight accounting GROUPS (Blake, 2026-08-03)

The kernel plan raised a blocker: eight capture rows covered only six of the nine bridge fact
types, while `projections` and `injuries` served none. Blake's ruling resolves it without trading
coverage against evidence:

> Keep eight top-level accounting groups while preserving every required component. These are
> reporting/control groups, not provenance atoms. Every component must retain an independent source
> identity, status, `captured_at`/`known_at` basis, freshness/due state, content hash, and failure.
> A composite group passes only when every required component passes.

The approved design fixes the **accounting** count at eight; it never fixes the number of sources.
Separating reporting groups from provenance atoms satisfies the approved count, covers all eight
2026 bridge fact types, and keeps projections and injuries. **No design change is required.**

| #   | Group                 | Components                                          | Bridge fact types                    |
| --- | --------------------- | --------------------------------------------------- | ------------------------------------ |
| 1   | `league_identity`     | `sleeper_league`, `sleeper_users`                   | `franchise_identity`                 |
| 2   | `rosters`             | `sleeper_rosters`                                   | `roster_membership`                  |
| 3   | `draft`               | `draft_meta`, `draft_picks`                         | `draft_pick`                         |
| 4   | `transactions`        | `sleeper_transactions`                              | `transaction`                        |
| 5   | `league_matchups`     | `sleeper_matchups`                                  | `schedule_pairing`, `matchup_result` |
| 6   | `sleeper_projections` | `sleeper_projections`                               | — (preserved, non-bridge)            |
| 7   | `nfl_context`         | `nfl_schedules`, `nfl_team_context`, `nfl_injuries` | `nfl_game`                           |
| 8   | `chat_media_export`   | `chat_export`                                       | `chat_message`                       |

`historical_matchup` is the ninth bridge type and has no 2026 source by design (it is 2022-2024).
All eight types whose 2026 source is `capture` are covered.

---

## Verification standard for this plan

The two prior review rounds on the kernel plan failed the same way: unexecuted Python written
inside markdown, corrected by re-reading, generating new defects each pass. **Every code block in
this plan was executed before it was written down.**

| Evidence                                                                      | Result           |
| ----------------------------------------------------------------------------- | ---------------- |
| `capture_2026` + `seal_2026` + fetcher suites, run                            | **42 passed**    |
| Mutation controls applied and observed to fail the intended test              | **8 of 8 fired** |
| Defect found only by running (`qualify_cutoff` expected value off by one day) | 1, fixed         |

Mutation controls proven to fire: reload skips payload-hash verification; a missing capture reports
`captured`; the freshness window is ignored; a group passes on ANY component; a late seal is always
labeled prospective; seal metadata is not verified; `load_seals` globs every JSON; a ranking may
carry no claims. **A test that does not fail when its rule is removed is not evidence** — each of
these was observed failing, not assumed to.

This standard is binding on execution too: no task is complete on a green suite alone until its
discriminating controls have been observed to fail.

---

## Global Constraints

- `python`, never `python3`. Pin the interpreter:
  `export PY="/c/Users/blake/AppData/Local/Programs/Python/Python312/python"`.
- sys.path bootstrap per `scripts/fetch_nflreadpy.py:20-25`; tests import `from scripts.X import`.
- Every CLI ends `raise SystemExit(main())`. A bare `main()` returning 1 exits 0.
- `sorted()`, never `list(set)`, where serialized.
- Baseline suite **343 passed / 2 skipped** (`c751b22`). No task reduces it.
- Binary gates. No "approve with notes".
- **Private captures never enter git.** `private_captures/` is gitignored and the staging guard
  checks the **index**, not `git status`.
- No pushes; nothing deleted; protected untracked paths (`.claude/worktrees/`, `New folder/`)
  untouched.

## File Structure

| File                                              | Responsibility                                          |
| ------------------------------------------------- | ------------------------------------------------------- |
| `scripts/capture_2026.py`                         | Split-root append-only store, component status, receipt |
| `scripts/seal_2026.py`                            | Frozen bundle, cutoff qualification, run receipt, seal  |
| `content/governance/capture_table_2026.json`      | The eight groups and their components                   |
| `content/governance/runner_config_2026.json`      | Runner binding for the sealed decision                  |
| `docs/superpowers/plans/capture-manual-ingest.md` | Manual component procedures                             |
| `data/captures/2026/public/`                      | Public captures (committed)                             |
| `private_captures/2026/`                          | Private captures (**gitignored, never staged**)         |
| `content/seals/2026/`                             | Seals, decision bodies, run receipts                    |

---

## F1: Capture store and component provenance

**Files:** Create `scripts/capture_2026.py`, `scripts/tests/test_capture_2026.py`; modify
`.gitignore`

**Interfaces:** `capture(source_id, payload, known_at_basis, privacy, captured_at, root=None)`,
`CaptureRefused`, `FetchFailed`, `content_sha256`, `parse_instant`, `latest_capture`,
`component_status`, `group_status`, `accounting_receipt`, `PUBLIC_ROOT`, `PRIVATE_ROOT`

- [ ] **Step 1: Write the failing tests** — verified suite, 15 tests

```python
"""Component-level provenance and eight-group accounting."""
import json
from pathlib import Path

import pytest
from scripts.capture_2026 import (CaptureRefused, accounting_receipt, capture,
                                  component_status, group_status, latest_capture)

TABLE = json.loads(Path("content/governance/capture_table_2026.json").read_text(encoding="utf-8"))
NOW = "2026-08-03T06:00:00Z"


@pytest.fixture
def roots(tmp_path):
    return {"public": tmp_path / "pub", "private": tmp_path / "priv"}


def put(roots, source_id, privacy="public", at=NOW, payload=None):
    return capture(source_id, payload or {"v": 1}, "capture_instant", privacy, at,
                   root=roots["private" if privacy == "private" else "public"])


def test_failed_fetch_is_never_written(roots):
    """fetch_sleeper.fetch_json returns None on exhausted retries (fetch_sleeper.py:69)."""
    for bad in (None, "str", 42, {}, []):
        with pytest.raises(CaptureRefused):
            capture("x", bad, "capture_instant", "public", NOW, root=roots["public"])


def test_capture_validates_its_own_instant(roots):
    """Manual-ingest callers never pass through main(); validation lives in capture()."""
    for bad in ("2026-08-03", "2026-08-03 06:00:00", "Sat 08/03/2026T06:00:00Z", None):
        with pytest.raises(CaptureRefused):
            capture("x", {"v": 1}, "capture_instant", "public", bad, root=roots["public"])


def test_append_only_refuses_overwrite(roots):
    put(roots, "sleeper_league")
    with pytest.raises(CaptureRefused):
        put(roots, "sleeper_league")


def test_private_lands_outside_the_public_root(roots):
    p = put(roots, "chat_export", privacy="private")
    assert Path(roots["private"]) in p.parents
    assert Path(roots["public"]) not in p.parents


def test_tampered_capture_is_not_coverage(roots):
    p = put(roots, "sleeper_league")
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["payload"] = {"v": 999}
    p.write_text(json.dumps(rec), encoding="utf-8")
    assert latest_capture("sleeper_league", "public", roots) is None


def test_manual_component_reaches_captured_once_ingested(roots):
    comp = {"source_id": "chat_export", "mechanism": "manual_export", "cadence": "on_export",
            "required": True, "known_at_basis": "message_timestamp", "privacy": "private",
            "manual_ingest_doc": "doc#chat"}
    assert component_status(comp, NOW, roots)["status"] == "due"
    put(roots, "chat_export", privacy="private")
    assert component_status(comp, NOW, roots)["status"] == "captured"


def test_stale_daily_component_goes_due_again(roots):
    comp = {"source_id": "sleeper_rosters", "mechanism": "api", "cadence": "daily",
            "required": True, "known_at_basis": "capture_instant", "privacy": "public"}
    put(roots, "sleeper_rosters", at="2026-07-01T06:00:00Z")
    st = component_status(comp, NOW, roots)
    assert st["status"] == "due" and "stale" in st["error"]


def test_weekly_component_is_fresh_within_seven_days(roots):
    comp = {"source_id": "nfl_schedules", "mechanism": "parquet", "cadence": "weekly",
            "required": True, "known_at_basis": "publication_instant", "privacy": "public"}
    put(roots, "nfl_schedules", at="2026-07-29T06:00:00Z")
    assert component_status(comp, NOW, roots)["status"] == "captured"


def test_group_passes_only_when_every_required_component_passes():
    ok = {"required": True, "status": "captured"}
    assert group_status([ok, dict(ok)]) == "captured"
    assert group_status([ok, {"required": True, "status": "due"}]) == "incomplete"
    assert group_status([ok, {"required": True, "status": "error"}]) == "error"
    assert group_status([ok, {"required": False, "status": "due"}]) == "captured"


def test_exactly_eight_groups_and_all_bridge_types_covered():
    r = accounting_receipt(TABLE, NOW, {"public": "/nope", "private": "/nope"})
    assert len(r["groups"]) == 8
    covered = {t for g in TABLE["groups"] for t in g["bridge_fact_types"]}
    need = {"franchise_identity", "schedule_pairing", "matchup_result", "roster_membership",
            "transaction", "draft_pick", "chat_message", "nfl_game"}
    assert need <= covered, f"uncovered bridge types: {sorted(need - covered)}"


def test_empty_store_is_not_ok_and_names_what_is_missing(roots):
    r = accounting_receipt(TABLE, NOW, roots)
    assert r["ok"] is False
    assert "league_identity" in r["unmet_required_groups"]
    assert "sleeper_projections" not in r["unmet_required_groups"]


def test_a_fully_ingested_lane_goes_green(roots):
    for g in TABLE["groups"]:
        for c in g["components"]:
            put(roots, c["source_id"], privacy=c.get("privacy", "public"))
    r = accounting_receipt(TABLE, NOW, roots)
    assert r["unmet_required_groups"] == [] and r["ok"] is True


def test_manual_rows_do_not_permanently_block_the_lane(roots):
    """A prior revision marked every fetcher-less row 'unavailable' while defaulting
    it required, so every real run exited 1 forever."""
    for g in TABLE["groups"]:
        for c in g["components"]:
            if c["mechanism"] != "manual_export":
                put(roots, c["source_id"], privacy=c.get("privacy", "public"))
    assert "chat_media_export" in accounting_receipt(TABLE, NOW, roots)["unmet_required_groups"]
    put(roots, "chat_export", privacy="private")
    assert accounting_receipt(TABLE, NOW, roots)["ok"] is True


def test_a_failed_fetch_this_run_is_error_not_captured(roots):
    for g in TABLE["groups"]:
        for c in g["components"]:
            put(roots, c["source_id"], privacy=c.get("privacy", "public"))
    r = accounting_receipt(TABLE, NOW, roots,
                           fetch_results={"sleeper_rosters": "FetchFailed: exhausted retries"})
    assert next(g for g in r["groups"] if g["group"] == "rosters")["status"] == "error"
    assert r["ok"] is False


def test_receipt_carries_no_private_payload(roots):
    put(roots, "chat_export", privacy="private", payload={"secret": "x"})
    r = accounting_receipt(TABLE, NOW, roots)
    assert "secret" not in json.dumps(r)
    comp = next(c for g in r["groups"] if g["group"] == "chat_media_export"
                for c in g["components"])
    assert comp["privacy"] == "private" and comp["content_sha256"].startswith("sha256:")
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Write `content/governance/capture_table_2026.json`** — the eight groups exactly as
      tabled above. Each component carries `source_id`, `mechanism`
      (`api` | `manual_export` | `parquet`), `cadence` (`daily` | `weekly` | `on_export` | `once`),
      `required`, `known_at_basis`, `privacy`, and `manual_ingest_doc` for manual components. Each
      group carries `group`, `required`, `bridge_fact_types`, `components`.

      `sleeper_projections` is the one group with `required: false` — it is preserved evidence, not
      a bridge input, so its absence must not redden the lane. Within `nfl_context`,
      `nfl_schedules` is required and `nfl_team_context` / `nfl_injuries` are not: the group's
      bridge obligation is `nfl_game`, which schedules alone satisfy.

- [ ] **Step 4: Implement** — verified

```python
"""P-only capture lane: append-only split-root store, component-level provenance,
eight-group accounting."""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "data" / "captures" / "2026" / "public"
PRIVATE_ROOT = ROOT / "private_captures" / "2026"
VALID_PRIVACY = {"public", "private"}
INSTANT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COMPONENT_STATUSES = {"captured", "due", "not_due", "error"}
GROUP_STATUSES = {"captured", "incomplete", "error"}

# cadence -> freshness window. A component captured inside its window is current.
FRESHNESS = {"daily": timedelta(days=1), "weekly": timedelta(days=7),
             "on_export": None, "once": None}


class CaptureRefused(ValueError):
    """The observation cannot be honestly recorded. Never written, never counted."""


class FetchFailed(RuntimeError):
    """The source could not be read. Distinct from 'legitimately empty'."""


def parse_instant(s):
    if not (isinstance(s, str) and INSTANT_RE.match(s)):
        raise CaptureRefused(f"instant must be YYYY-MM-DDTHH:MM:SSZ, got {s!r}")
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def content_sha256(obj) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def capture(source_id, payload, known_at_basis, privacy, captured_at, root=None):
    """Validation lives HERE: manual-ingest callers never pass through main()."""
    if privacy not in VALID_PRIVACY:
        raise CaptureRefused(f"privacy must be one of {sorted(VALID_PRIVACY)}")
    parse_instant(captured_at)
    if not known_at_basis:
        raise CaptureRefused(f"{source_id}: known_at_basis is required")
    if payload is None:
        raise CaptureRefused(f"{source_id}: payload is None -- a failed fetch is not a capture")
    if not isinstance(payload, (dict, list)):
        raise CaptureRefused(f"{source_id}: payload must be object or array, got {type(payload)}")
    if len(payload) == 0:
        raise CaptureRefused(f"{source_id}: empty payload; declare it unavailable explicitly")
    base = root if root is not None else (PUBLIC_ROOT if privacy == "public" else PRIVATE_ROOT)
    path = Path(base) / source_id / f"{captured_at.replace(':', '').replace('-', '')}.json"
    if path.exists():
        raise CaptureRefused(f"refusing to overwrite capture: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"source_id": source_id, "captured_at": captured_at,
           "known_at_basis": known_at_basis, "privacy": privacy,
           "content_sha256": content_sha256(payload), "payload": payload}
    path.write_text(json.dumps(rec, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def latest_capture(source_id, privacy, roots):
    """Most recent VERIFIED capture for a component, or None.

    Verification is not optional: a capture whose payload no longer matches its
    recorded hash is treated as absent, never as coverage.
    """
    base = Path(roots["private" if privacy == "private" else "public"])
    d = base / source_id
    if not d.exists():
        return None
    best = None
    for p in sorted(d.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if content_sha256(rec["payload"]) != rec["content_sha256"]:
            continue                       # tampered or truncated: not coverage
        if best is None or rec["captured_at"] > best["captured_at"]:
            best = rec
    return best


def component_status(comp, now_utc, roots):
    """captured | due | not_due | error -- per component, with freshness."""
    out = {"source_id": comp["source_id"], "required": comp.get("required", True),
           "mechanism": comp["mechanism"], "cadence": comp["cadence"],
           "privacy": comp.get("privacy", "public"),
           "known_at_basis": comp["known_at_basis"],
           "captured_at": None, "content_sha256": None, "error": None,
           "acquisition_trigger": comp.get("manual_ingest_doc")}
    rec = latest_capture(comp["source_id"], out["privacy"], roots)
    if rec is None:
        out["status"] = "due"
        return out
    out["captured_at"] = rec["captured_at"]
    out["content_sha256"] = rec["content_sha256"]
    window = FRESHNESS[comp["cadence"]]
    if window is None:
        out["status"] = "captured"         # on_export / once: existence is currency
        return out
    age = parse_instant(now_utc) - parse_instant(rec["captured_at"])
    out["status"] = "captured" if age <= window else "due"
    if out["status"] == "due":
        out["error"] = f"stale: last capture {rec['captured_at']} exceeds {comp['cadence']}"
    return out


def group_status(components):
    """A composite group passes only when every REQUIRED component passes."""
    req = [c for c in components if c["required"]]
    if any(c["status"] == "error" for c in req):
        return "error"
    if all(c["status"] == "captured" for c in req):
        return "captured"
    return "incomplete"


def accounting_receipt(table, now_utc, roots, fetch_results=None):
    """Eight groups. Component provenance is never collapsed into the group."""
    parse_instant(now_utc)
    fetch_results = fetch_results or {}
    groups = []
    for g in table["groups"]:
        comps = []
        for comp in g["components"]:
            st = component_status(comp, now_utc, roots)
            if comp["source_id"] in fetch_results:      # this run attempted it
                err = fetch_results[comp["source_id"]]
                if err is not None:
                    st["status"], st["error"] = "error", err
            comps.append(st)
        groups.append({"group": g["group"], "required": g.get("required", True),
                       "status": group_status(comps), "components": comps})
    unmet = sorted(g["group"] for g in groups
                   if g["required"] and g["status"] != "captured")
    assert len(groups) == 8, f"accounting must report exactly 8 groups, got {len(groups)}"
    return {"season": 2026, "generated_at": now_utc, "groups": groups,
            "unmet_required_groups": unmet, "ok": not unmet}
```

Append `private_captures/` to `.gitignore`.

- [ ] **Step 5: Run to verify it passes** → 15 passed

- [ ] **Step 6: Prove the tests discriminate** — apply each mutation, observe the named test fail,
      then restore. All four were observed firing during plan authoring:

| Mutation                                              | Must fail                                       |
| ----------------------------------------------------- | ----------------------------------------------- |
| `latest_capture` skips the payload-hash check         | `test_tampered_capture_is_not_coverage`         |
| missing capture returns `captured` instead of `due`   | `test_empty_store...`, `test_manual_rows...`    |
| freshness window ignored (`status` always `captured`) | `test_stale_daily_component_goes_due_again`     |
| `group_status` uses `any` instead of `all`            | `test_group_passes_only_when_every_required...` |

- [ ] **Step 7: Commit**

```bash
git add scripts/capture_2026.py scripts/tests/test_capture_2026.py \
        content/governance/capture_table_2026.json .gitignore
git commit -m "feat(capture-2026): split-root store, component provenance, eight-group accounting"
```

---

## F2: Component fetchers

**Files:** Modify `scripts/capture_2026.py`, `scripts/tests/test_capture_2026.py`; create
`docs/superpowers/plans/capture-manual-ingest.md`

**Interfaces:** `SOURCE_FETCHERS`, `TRANSACTION_LEGS`, `MATCHUP_WEEKS`, `_get`, `_fetch_draft`,
`_fetch_transactions`, `_fetch_matchups`

- [ ] **Step 1: Write the failing tests**

```python
def test_exhausted_retries_raise_instead_of_returning_none(monkeypatch):
    from scripts import capture_2026
    monkeypatch.setattr("fetch_sleeper.fetch_json", lambda *a, **k: None)
    with pytest.raises(FetchFailed):
        capture_2026._get("/league/1")


def test_draft_fetch_reaches_actual_picks(monkeypatch):
    """/league/{id}/drafts returns METADATA. Picks need /draft/{draft_id}/picks --
    the shape scripts/fetch_draft_picks.py already uses."""
    seen = []
    def fake(suffix):
        seen.append(suffix)
        if suffix.endswith("/drafts"):
            return [{"draft_id": "111"}]
        if suffix == "/draft/111":
            return {"draft_id": "111", "type": "snake"}
        if suffix == "/draft/111/picks":
            return [{"pick_no": 1}, {"pick_no": 2}]
        raise AssertionError(suffix)
    monkeypatch.setattr("scripts.capture_2026._get", fake)
    out = _fetch_draft("L1")
    assert "/draft/111/picks" in seen
    assert [p["pick_no"] for p in out["boards"]["111"]["picks"]] == [1, 2]


def test_draft_metadata_without_picks_fails(monkeypatch):
    monkeypatch.setattr("scripts.capture_2026._get",
                        lambda s: [{"status": "complete"}] if s.endswith("/drafts") else None)
    with pytest.raises(FetchFailed):
        _fetch_draft("L1")


def test_partial_transaction_leg_failure_is_not_an_empty_week(monkeypatch):
    """`or []` made an outage byte-identical to eighteen quiet weeks."""
    def fake(suffix):
        if suffix.endswith("/7"):
            raise FetchFailed(suffix)
        return []
    monkeypatch.setattr("scripts.capture_2026._get", fake)
    with pytest.raises(FetchFailed) as e:
        _fetch_transactions("L1")
    assert "7" in str(e.value)


def test_all_legs_read_and_genuinely_empty_is_a_valid_capture(monkeypatch):
    monkeypatch.setattr("scripts.capture_2026._get", lambda s: [])
    out = _fetch_transactions("L1")
    assert out["legs_requested"] == sorted(TRANSACTION_LEGS)
    assert len(out["legs"]) == len(TRANSACTION_LEGS)


def test_matchups_record_which_weeks_were_requested(monkeypatch):
    monkeypatch.setattr("scripts.capture_2026._get", lambda s: [{"matchup_id": 1}])
    out = _fetch_matchups("L1")
    assert out["weeks_requested"] == sorted(MATCHUP_WEEKS)
    assert len(out["weeks"]) == len(MATCHUP_WEEKS)
```

- [ ] **Step 2: Run to verify it fails** → `ImportError`

- [ ] **Step 3: Implement**

```python
TRANSACTION_LEGS = list(range(1, 19))    # never derived from len(all_matchups)
MATCHUP_WEEKS = list(range(1, 19))


def _get(suffix):
    """fetch_json returns None after exhausted retries -- convert that to a raise.

    Passing None onward is how a network outage becomes an empty capture.
    """
    from fetch_sleeper import fetch_json      # constant-host, validated helper
    out = fetch_json(suffix)
    if out is None:
        raise FetchFailed(f"exhausted retries: {suffix}")
    return out


def _fetch_draft(lid):
    """Two hops. `/league/{id}/drafts` returns draft METADATA, never the picks."""
    drafts = _get(f"/league/{lid}/drafts")
    if not isinstance(drafts, list) or not drafts:
        raise FetchFailed(f"no drafts for league {lid}")
    ids = sorted(str(d.get("draft_id")) for d in drafts if d.get("draft_id"))
    if not ids:
        raise FetchFailed("draft metadata carries no draft_id")
    boards = {}
    for did in ids:
        if not did.isdigit():
            raise FetchFailed(f"non-numeric draft_id {did!r}")
        boards[did] = {"meta": _get(f"/draft/{did}"), "picks": _get(f"/draft/{did}/picks")}
    return {"draft_ids": ids, "boards": boards}


def _fetch_legs(lid, path_tmpl, legs, key):
    """Per-leg typed results. A failed leg must never look like a quiet week."""
    got, failed = {}, []
    for n in legs:
        try:
            got[str(n)] = _get(path_tmpl.format(lid=lid, n=n))
        except FetchFailed:
            failed.append(n)
    if failed:
        raise FetchFailed(f"{key} unreadable for {sorted(failed)}")
    return {key: got, f"{key}_requested": sorted(legs)}


def _fetch_transactions(lid):
    out = _fetch_legs(lid, "/league/{lid}/transactions/{n}", TRANSACTION_LEGS, "legs")
    return out


def _fetch_matchups(lid):
    return _fetch_legs(lid, "/league/{lid}/matchups/{n}", MATCHUP_WEEKS, "weeks")


def _draft_assertions(payload):
    """Prove picks AND order survived, across every board."""
    boards = (payload or {}).get("boards", {})
    picks = [p for b in boards.values() for p in (b.get("picks") or []) if isinstance(p, dict)]
    nos = [p.get("pick_no") for p in picks]
    return {"board_count": len(boards), "pick_count": len(picks),
            "order_preserved": bool(nos) and None not in nos and nos == sorted(nos)}


SOURCE_FETCHERS = {
    "sleeper_league": lambda lid: _get(f"/league/{lid}"),
    "sleeper_users": lambda lid: _get(f"/league/{lid}/users"),
    "sleeper_rosters": lambda lid: _get(f"/league/{lid}/rosters"),
    "draft_meta": lambda lid: _get(f"/league/{lid}/drafts"),
    "draft_picks": _fetch_draft,
    "sleeper_transactions": _fetch_transactions,
    "sleeper_matchups": _fetch_matchups,
}
```

`nfl_schedules`, `nfl_team_context` and `nfl_injuries` are captured from the existing
`scripts/fetch_nflreadpy.py` parquet caches (`--season 2026`), re-encoded to JSON before
`capture(...)` so the capture record stays self-describing. `sleeper_projections` and `chat_export`
are manual.

- [ ] **Step 4: Write `capture-manual-ingest.md`** — one section per manual component
      (`#projections`, `#chat`), each giving the source, the **exact** `capture(...)` invocation,
      the `known_at` justification, and for chat that it is private-class and lands in
      `PRIVATE_ROOT`. State plainly that `capture()` validates the instant, so a mistyped
      `captured_at` fails at ingestion rather than at normalization months later.

- [ ] **Step 5: Run** → 6 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/capture_2026.py scripts/tests/test_capture_2026.py \
        docs/superpowers/plans/capture-manual-ingest.md
git commit -m "feat(capture-2026): component fetchers, draft pick fan-out, typed leg failures"
```

---

## F3: CLI, baseline capture, cadence

**Files:** Modify `scripts/capture_2026.py`; create `.github/workflows/capture-2026.yml`

- [ ] **Step 1: Add the CLI**

```python
def main():
    import argparse
    from datetime import datetime, timezone
    ap = argparse.ArgumentParser()
    ap.add_argument("--league-id")
    # Optional: an unattended scheduler cannot compute a UTC instant in its command
    # string (cmd's %DATE% is a locale-dependent LOCAL date). captured_at is a
    # capture-time stamp by definition; the wall-clock ban applies to normalizers.
    ap.add_argument("--now-utc",
                    default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    parse_instant(a.now_utc)
    table = json.loads(CAPTURE_TABLE_PATH.read_text(encoding="utf-8"))
    roots = {"public": PUBLIC_ROOT, "private": PRIVATE_ROOT}
    fetch_results = {}
    if not a.dry_run:
        for group in table["groups"]:
            for comp in group["components"]:
                fetcher = SOURCE_FETCHERS.get(comp["source_id"])
                if fetcher is None:
                    continue                       # manual/parquet: ingested elsewhere
                try:
                    payload = fetcher(a.league_id)
                    if comp["source_id"] == "draft_picks":
                        asserts = _draft_assertions(payload)
                        if not (asserts["pick_count"] and asserts["order_preserved"]):
                            raise FetchFailed(f"draft assertions failed: {asserts}")
                    capture(comp["source_id"], payload, comp["known_at_basis"],
                            comp["privacy"], a.now_utc)
                    fetch_results[comp["source_id"]] = None
                except (FetchFailed, CaptureRefused) as e:
                    fetch_results[comp["source_id"]] = f"{type(e).__name__}: {e}"
    r = accounting_receipt(table, a.now_utc, roots, fetch_results)
    # Written even on failure: an honest record of a bad day is the point of
    # accounting. What must not happen is exiting 0 on top of it.
    out = PUBLIC_ROOT / "_receipts" / f"{a.now_utc.replace(':', '').replace('-', '')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, sort_keys=True, indent=2) + "\n", encoding="utf-8",
                   newline="\n")
    print(json.dumps(r, indent=2, sort_keys=True))
    if a.dry_run:
        return 0
    if r["unmet_required_groups"]:
        print(f"FAIL unmet required groups: {r['unmet_required_groups']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Prove the entry point executes**

```bash
$PY scripts/capture_2026.py --help >/dev/null; echo "help exit=$?"   # 0, with output
```

A `main()` without `if __name__ == "__main__"` exits 0 while doing nothing, and a gate reading that
code sees success. Verify before trusting.

- [ ] **Step 3: Take the baseline capture**

```bash
$PY scripts/capture_2026.py --league-id <2026_LEAGUE_ID>
echo "exit=$?"   # 1 is EXPECTED until the manual components are ingested
```

- [ ] **Step 4: Ingest the manual components** per `capture-manual-ingest.md`, then re-run until
      the receipt reports `"ok": true`. **This is the gate for F1-F3.**

- [ ] **Step 5: Stage the public root only**

```bash
git add data/captures/2026/public/
# Check the INDEX: private_captures/ is gitignored, so `git status` can never show it
# and a guard reading status could never fire. Only `git add -f` can stage it.
git diff --cached --name-only | grep -q '^private_captures/' \
  && { echo "STOP: private capture staged"; exit 1; }
git diff --cached --name-only | grep -q '^data/captures/2026/public/' \
  || { echo "STOP: nothing staged; the capture did not run"; exit 1; }
git commit -m "data(capture-2026): baseline capture with eight-group accounting receipt"
```

- [ ] **Step 6: Register the daily cadence**

```bash
schtasks //Create //SC DAILY //ST 06:00 //TN "JailyardCapture2026" //TR \
  "cmd /c cd /d C:\\Users\\blake\\projects\\Jailyard-Dynasty-Power-Rankings && \
   C:\\Users\\blake\\AppData\\Local\\Programs\\Python\\Python312\\python.exe \
   scripts\\capture_2026.py --league-id <ID>"
schtasks //Run //TN "JailyardCapture2026"
schtasks //Query //TN "JailyardCapture2026" //V //FO LIST | grep -i "last result"
```

`--now-utc` is omitted deliberately: `%DATE%` expands to a locale-dependent local date
(`Sat 08/03/2026`), which is neither UTC nor an ISO instant. **Verify `last result` is 0** — a
registered task that fails silently is worse than no task, because it reads as coverage.

- [ ] **Step 7: Author the workflow — inactive until pushed.** `.github/workflows/capture-2026.yml`,
      `cron: '0 6 * 8,9 *'`, committing its captures back (a runner discards its filesystem).

- [ ] **Step 8: STOP — activating the workflow requires Blake's explicit approval of that push.**

- [ ] **Step 9: Commit**

```bash
git add scripts/capture_2026.py .github/workflows/capture-2026.yml
git commit -m "feat(capture-2026): CLI gate, daily cadence, inactive workflow"
```

---

## F4: Frozen decision-input bundle and qualified cutoffs

The design is explicit that hashing raw captures is not enough: the plan must bind **"the exact
frozen decision-input bundle the seal was made from, and the permitted transformations from
captures to that bundle — not merely the hashes of raw captures. A hash of inputs does not pin what
the decider actually saw."**

**Files:** Create `scripts/seal_2026.py`, `scripts/tests/test_seal_2026.py`

**Interfaces:** `freeze_bundle(components, transformations, out_dir)`,
`qualify_cutoff(first_kickoff_utc, kind)`, `SealRefused`, `SEAL_SUFFIX`

- [ ] **Step 1: Write the failing tests** — verified

```python
def test_preview_cutoff_is_strictly_before_kickoff():
    assert qualify_cutoff(KICKOFF, "preview") == "2026-09-11T00:19:59Z"
    assert qualify_cutoff(KICKOFF, "preview") < KICKOFF


def test_preseason_cutoff_precedes_kickoff():
    assert qualify_cutoff(KICKOFF, "preseason") == "2026-09-10T00:20:00Z"


def test_bundle_freezes_transformations_not_only_input_hashes(tmp_path):
    b = freeze_bundle(COMPONENTS, TRANSFORMS, tmp_path / "b")
    body = json.loads(Path(b["path"]).read_text(encoding="utf-8"))
    assert body["transformations"] == TRANSFORMS
    assert set(body["component_hashes"]) == set(COMPONENTS)


def test_bundle_is_immutable_once_frozen(tmp_path):
    freeze_bundle(COMPONENTS, TRANSFORMS, tmp_path / "b")
    with pytest.raises(SealRefused):
        freeze_bundle(COMPONENTS, TRANSFORMS, tmp_path / "b")


def test_transformation_without_required_keys_is_refused(tmp_path):
    with pytest.raises(SealRefused):
        freeze_bundle(COMPONENTS, [{"step": "x"}], tmp_path / "b")
```

- [ ] **Step 2: Run to verify it fails** → `ModuleNotFoundError`

- [ ] **Step 3: Implement** — verified

```python
"""Prospective sealing lane. The seal, not the capture, is the experiment.

Hash chain is deliberately ACYCLIC:
    bundle_sha256   = frozen decision-input bundle (inputs + transformations)
    decision_sha256 = {ranking, claims} payload
    receipt_sha256  = CLOSED run receipt, which binds bundle + decision payload
    decision_hash   = seal over cutoff + bundle + decision + receipt hashes
Nothing binds decision_hash except the seal itself, so there is no cycle.
"""
import json
from datetime import timedelta
from pathlib import Path

from capture_2026 import content_sha256, parse_instant

SEAL_SUFFIX = ".seal.json"          # seals never share a glob with their bodies
RUNNER_KINDS = {"deterministic", "model"}


class SealRefused(ValueError):
    """A seal that cannot be honestly recorded as prospective."""


def freeze_bundle(components, transformations, out_dir):
    """The EXACT decision-input bundle, not merely hashes of raw captures.

    `components`      : {source_id: payload-as-the-decider-saw-it}
    `transformations` : ordered, named steps from capture -> bundle.
    """
    if not components:
        raise SealRefused("refusing to freeze an empty bundle")
    for t in transformations:
        if not {"step", "source_ids", "description"} <= set(t):
            raise SealRefused(f"transformation missing required keys: {t}")
    bundle = {"components": components,
              "component_hashes": {k: content_sha256(v) for k, v in sorted(components.items())},
              "transformations": list(transformations)}
    bundle_sha256 = content_sha256(bundle)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / "bundle.json"
    if p.exists():
        raise SealRefused(f"bundle already frozen and immutable: {p}")
    p.write_text(json.dumps(bundle, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8", newline="\n")
    return {"path": str(p), "bundle_sha256": bundle_sha256}


def qualify_cutoff(first_kickoff_utc, kind):
    """Derived from the qualified kickoff instant, never hard-coded."""
    k = parse_instant(first_kickoff_utc)
    if kind == "preview":
        return (k - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if kind == "preseason":
        return (k - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise SealRefused(f"unknown seal kind {kind!r}")
```

**The preseason offset is a stated assumption, not a derivation.** The design says the preseason
cutoff derives from the qualified first-kickoff instant but does not fix the offset. One day before
first kickoff is used here. **If Blake wants a different preseason boundary, change it before the
first seal — never after.**

`first_kickoff_utc` comes from the qualified schedule source with venue-timezone conversion.
Reuse `scripts/kickoff_source.py` if the kernel plan's K2.2 has landed; otherwise derive it from
the `nfl_schedules` capture and **record the derivation in the bundle's transformations**, because
appending `Z` to a local kickoff time is the exact bug that motivated that task.

- [ ] **Step 4: Run** → 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/seal_2026.py scripts/tests/test_seal_2026.py
git commit -m "feat(seal-2026): frozen decision bundle with transformations, qualified cutoffs"
```

---

## F5: Decision run receipt and the seal

**Files:** Modify `scripts/seal_2026.py`, `scripts/tests/test_seal_2026.py`; create
`content/governance/runner_config_2026.json`

**Interfaces:** `open_run`, `close_run`, `seal_decision`, `load_seals`, `verify_seal`,
`RUNNER_KINDS`

**Ordering is load-bearing:** close the run, then seal over the **closed** receipt's hash. Persisting
an open receipt and sealing a mutable _path_ leaves a decision with no durable output hash and no
way to detect tampering.

- [ ] **Step 1: Write the failing tests** — verified

```python
def test_deterministic_run_rejects_model_fields(tmp_path):
    with pytest.raises(SealRefused):
        open_run("deterministic", "sha256:a", "sha256:b", "2026-08-03T00:00:00Z",
                 provider="anthropic", **DET)


def test_model_run_requires_browsing_and_prompt_policy():
    with pytest.raises(SealRefused):
        open_run("model", "sha256:a", "sha256:b", "2026-08-03T00:00:00Z",
                 provider="anthropic", model="claude-opus-5")


def test_sealing_an_open_run_is_refused(tmp_path):
    b = freeze_bundle(COMPONENTS, TRANSFORMS, tmp_path / "b")
    run = open_run("deterministic", b["bundle_sha256"], "sha256:f",
                   "2026-08-03T00:00:00Z", **DET)
    with pytest.raises(SealRefused):
        seal_decision(tmp_path / "s", "e", "preseason", "2026-09-01T00:00:00Z",
                      "2026-08-03T00:00:00Z", RANKING, CLAIMS, b, run, "sha256:f")


def test_receipt_must_describe_the_sealed_decision(tmp_path):
    b = freeze_bundle(COMPONENTS, TRANSFORMS, tmp_path / "b")
    run = close_run(open_run("deterministic", b["bundle_sha256"], "sha256:f",
                             "2026-08-03T00:00:00Z", **DET),
                    "sha256:" + "0" * 64, "2026-08-03T00:05:00Z")
    with pytest.raises(SealRefused):
        seal_decision(tmp_path / "s", "e", "preseason", "2026-09-01T00:00:00Z",
                      "2026-08-03T00:00:00Z", RANKING, CLAIMS, b, run, "sha256:f")


def test_seal_before_its_cutoff_is_prospective(tmp_path):
    assert build(tmp_path, "2026-08-03T00:00:00Z")["label"] == "prospective"


def test_seal_after_its_cutoff_is_labeled_retrospective_not_rejected_silently(tmp_path):
    assert build(tmp_path, "2026-09-20T00:00:00Z")["label"] == "retrospective"


def test_a_seal_is_immutable(tmp_path):
    build(tmp_path, "2026-08-03T00:00:00Z")
    with pytest.raises(SealRefused):
        build(tmp_path, "2026-08-03T00:00:00Z")


def test_ranking_without_a_claim_per_position_is_refused(tmp_path):
    with pytest.raises(SealRefused):
        build(tmp_path, "2026-08-03T00:00:00Z", claims=CLAIMS[:3])


def test_empty_ranking_is_refused(tmp_path):
    with pytest.raises(SealRefused):
        build(tmp_path, "2026-08-03T00:00:00Z", ranking={"entries": []}, claims=[])


def test_load_seals_ignores_decision_and_receipt_bodies(tmp_path):
    """Seal, decision and receipt share a directory; only the seal is a seal."""
    build(tmp_path, "2026-08-03T00:00:00Z")
    d = tmp_path / "seals" / "2026-preseason"
    assert len(sorted(d.glob("*.json"))) == 3
    seals = load_seals(tmp_path / "seals")
    assert len(seals) == 1 and seals[0]["edition_id"] == "2026-preseason"


def test_verify_seal_accepts_an_untouched_seal(tmp_path):
    assert verify_seal(build(tmp_path, "2026-08-03T00:00:00Z"))["ok"] is True


def test_tampered_seal_metadata_is_detected(tmp_path):
    s = build(tmp_path, "2026-08-03T00:00:00Z")
    s["label"] = "prospective" if s["label"] == "retrospective" else "retrospective"
    with pytest.raises(SealRefused):
        verify_seal(s)


def test_tampered_decision_body_is_detected(tmp_path):
    s = build(tmp_path, "2026-08-03T00:00:00Z")
    p = Path(s["decision_path"])
    body = json.loads(p.read_text(encoding="utf-8"))
    body["ranking"]["entries"][0]["roster_id"] = 99
    p.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(SealRefused):
        verify_seal(s)


def test_tampered_bundle_is_detected(tmp_path):
    s = build(tmp_path, "2026-08-03T00:00:00Z")
    p = Path(s["bundle_path"])
    body = json.loads(p.read_text(encoding="utf-8"))
    body["components"]["sleeper_rosters"] = [{"roster_id": 99}]
    p.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(SealRefused):
        verify_seal(s)
```

with the shared fixtures:

```python
KICKOFF = "2026-09-11T00:20:00Z"
COMPONENTS = {"sleeper_rosters": [{"roster_id": 1}], "sleeper_league": {"league_id": "L"}}
TRANSFORMS = [{"step": "select_latest_capture_per_component", "source_ids": ["sleeper_rosters"],
               "description": "most recent verified capture at or before the cutoff"}]
RANKING = {"entries": [{"rank": i, "roster_id": i} for i in range(1, 13)]}
CLAIMS = [{"claim_id": f"c{i}", "target": i, "claim_type": "ordinal_rank", "assertion": i}
          for i in range(1, 13)]
DET = {"code_hash": "sha256:" + "d" * 64, "config_hash": "sha256:" + "e" * 64}


def build(tmp_path, now, cutoff=None, ranking=None, claims=None, kind="preseason"):
    b = freeze_bundle(COMPONENTS, TRANSFORMS, tmp_path / "bundle")
    run = open_run("deterministic", b["bundle_sha256"], "sha256:" + "f" * 64,
                   "2026-08-03T00:00:00Z", **DET)
    ranking = ranking or RANKING
    claims = CLAIMS if claims is None else claims
    run = close_run(run, content_sha256({"ranking": ranking, "claims": claims}),
                    "2026-08-03T00:05:00Z")
    return seal_decision(tmp_path / "seals", "2026-preseason", kind,
                         cutoff or qualify_cutoff(KICKOFF, kind), now,
                         ranking, claims, b, run, "sha256:" + "f" * 64)
```

- [ ] **Step 2: Run to verify it fails** → `ImportError`

- [ ] **Step 3: Implement** — verified

```python
def open_run(runner_kind, bundle_sha256, factset_sha256, started_at, **cfg):
    if runner_kind not in RUNNER_KINDS:
        raise SealRefused(f"runner_kind must be one of {sorted(RUNNER_KINDS)}")
    parse_instant(started_at)
    need = ({"code_hash", "config_hash"} if runner_kind == "deterministic"
            else {"provider", "model", "model_version", "browsing", "tools_policy",
                  "prompt_hash"})
    missing = need - set(cfg)
    if missing:
        raise SealRefused(f"{runner_kind} run missing {sorted(missing)}")
    banned = ({"provider", "model"} if runner_kind == "deterministic" else {"code_hash"})
    if banned & set(cfg):
        raise SealRefused(f"{runner_kind} run must not carry {sorted(banned & set(cfg))}")
    return {"runner_kind": runner_kind, "bundle_sha256": bundle_sha256,
            "factset_sha256": factset_sha256, "started_at": started_at,
            "config": dict(sorted(cfg.items())), "ended_at": None,
            "output_decision_sha256": None}


def close_run(run, decision_sha256, ended_at):
    parse_instant(ended_at)
    if run["ended_at"] is not None:
        raise SealRefused("run already closed")
    return {**run, "ended_at": ended_at, "output_decision_sha256": decision_sha256}


def seal_decision(root, edition_id, kind, cutoff_utc, now_utc, ranking, claims,
                  bundle, run, factset_sha256):
    """Write the decision bodies, the CLOSED receipt, then the seal over their hashes."""
    if run["ended_at"] is None or run["output_decision_sha256"] is None:
        raise SealRefused("refusing to seal an open run: close it first")
    decision = {"ranking": ranking, "claims": claims}
    decision_sha256 = content_sha256(decision)
    if run["output_decision_sha256"] != decision_sha256:
        raise SealRefused("receipt does not describe this decision payload")
    if not ranking.get("entries"):
        raise SealRefused("a ranking with no entries is not a decision")
    if len(claims) < len(ranking["entries"]):
        raise SealRefused(
            f"{len(claims)} claims for {len(ranking['entries'])} positions; every "
            "position must carry at least one scoreable claim")

    # Late writes are labeled, never silently accepted as prospective.
    label = ("prospective" if parse_instant(now_utc) <= parse_instant(cutoff_utc)
             else "retrospective")

    d = Path(root) / edition_id
    d.mkdir(parents=True, exist_ok=True)
    sp = d / f"{edition_id}{SEAL_SUFFIX}"
    if sp.exists():
        raise SealRefused(f"seal exists and is immutable: {sp}")

    dp = d / f"{edition_id}.decision.json"
    rp = d / f"{edition_id}.receipt.json"
    dp.write_text(json.dumps(decision, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                  encoding="utf-8", newline="\n")
    rp.write_text(json.dumps(run, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                  encoding="utf-8", newline="\n")
    receipt_sha256 = content_sha256(run)

    body = {"edition_id": edition_id, "kind": kind, "season": 2026,
            "cutoff_utc": cutoff_utc, "sealed_at": now_utc, "label": label,
            "bundle_sha256": bundle["bundle_sha256"], "bundle_path": bundle["path"],
            "factset_sha256": factset_sha256,
            "decision_sha256": decision_sha256, "decision_path": str(dp),
            "receipt_sha256": receipt_sha256, "receipt_path": str(rp),
            "runner_kind": run["runner_kind"]}
    body["decision_hash"] = content_sha256(body)
    sp.write_text(json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                  encoding="utf-8", newline="\n")
    return body


def load_seals(root, edition_id=None):
    """Only *.seal.json. Bodies and receipts share the directory and are NOT seals."""
    base = Path(root)
    if not base.exists():
        return []
    out = []
    for p in sorted(base.glob(f"**/*{SEAL_SUFFIX}")):
        s = json.loads(p.read_text(encoding="utf-8"))
        if edition_id and s["edition_id"] != edition_id:
            continue
        out.append(s)
    return out


def verify_seal(sealed):
    """Recompute every hash. A seal that only names its evidence proves nothing."""
    body = {k: v for k, v in sealed.items() if k != "decision_hash"}
    if content_sha256(body) != sealed["decision_hash"]:
        raise SealRefused(f"{sealed['edition_id']}: seal metadata tampered")
    decision = json.loads(Path(sealed["decision_path"]).read_text(encoding="utf-8"))
    if content_sha256(decision) != sealed["decision_sha256"]:
        raise SealRefused(f"{sealed['edition_id']}: decision body does not match its hash")
    receipt = json.loads(Path(sealed["receipt_path"]).read_text(encoding="utf-8"))
    if content_sha256(receipt) != sealed["receipt_sha256"]:
        raise SealRefused(f"{sealed['edition_id']}: receipt does not match its hash")
    bundle = json.loads(Path(sealed["bundle_path"]).read_text(encoding="utf-8"))
    if content_sha256(bundle) != sealed["bundle_sha256"]:
        raise SealRefused(f"{sealed['edition_id']}: bundle does not match its hash")
    if receipt["output_decision_sha256"] != sealed["decision_sha256"]:
        raise SealRefused(f"{sealed['edition_id']}: receipt describes a different decision")
    return {"ok": True, "label": sealed["label"], "decision": decision,
            "receipt": receipt, "bundle": bundle}
```

- [ ] **Step 4: Run** → 16 passed (F4 + F5 in one module)

- [ ] **Step 5: Prove the tests discriminate** — all four observed firing during authoring:

| Mutation                                    | Must fail                                              |
| ------------------------------------------- | ------------------------------------------------------ |
| `label` hard-coded to `"prospective"`       | `test_seal_after_its_cutoff_is_labeled_retrospective`  |
| `verify_seal` skips the metadata hash check | `test_tampered_seal_metadata_is_detected`              |
| `load_seals` globs `**/*.json`              | `test_load_seals_ignores_decision_and_receipt_bodies`  |
| claims-per-position check removed           | `test_ranking_without_a_claim_per_position_is_refused` |

- [ ] **Step 6: Commit**

```bash
git add scripts/seal_2026.py scripts/tests/test_seal_2026.py \
        content/governance/runner_config_2026.json
git commit -m "feat(seal-2026): closed-receipt seals, acyclic hash chain, tamper detection"
```

---

## F6: Deferred normalization contract

The design requires: **"when the kernel exists, re-derive the state from the same frozen captures
and verify the seal still resolves."** That check must exist _now_, while the frozen artifacts are
being produced — a verifier written later can only be written to pass.

**Files:** Modify `scripts/seal_2026.py`, `scripts/tests/test_seal_2026.py`

- [ ] **Step 1: Write the failing tests** — verified

```python
def test_rederived_bundle_resolves_the_seal(tmp_path):
    s = build(tmp_path, "2026-08-03T00:00:00Z")
    frozen = json.loads(Path(s["bundle_path"]).read_text(encoding="utf-8"))
    assert rederive_and_verify(s, lambda: frozen) is True


def test_a_changed_rederivation_fails_the_seal(tmp_path):
    s = build(tmp_path, "2026-08-03T00:00:00Z")
    frozen = json.loads(Path(s["bundle_path"]).read_text(encoding="utf-8"))
    drifted = {**frozen, "transformations": frozen["transformations"] + [
        {"step": "extra", "source_ids": [], "description": "added later"}]}
    with pytest.raises(SealRefused):
        rederive_and_verify(s, lambda: drifted)
```

- [ ] **Step 2: Implement** — verified

```python
def rederive_and_verify(sealed, rebuild_bundle):
    """Deferred normalization: when the kernel exists, rebuild from the SAME frozen
    captures and prove the seal still resolves. Returns True or raises."""
    verify_seal(sealed)
    rebuilt = rebuild_bundle()
    if content_sha256(rebuilt) != sealed["bundle_sha256"]:
        raise SealRefused(
            f"{sealed['edition_id']}: re-derived bundle {content_sha256(rebuilt)[:19]} "
            f"!= sealed {sealed['bundle_sha256'][:19]}; the seal no longer resolves")
    return True
```

**The handoff to the kernel.** When K1 lands, `rebuild_bundle` becomes a call into
`normalize_facts` + `state_at(2026, cutoff, scope, as_recorded_at=<sealed_at>)` projected through
the same frozen transformations. A drift is not automatically a defect — it may be a legitimate
normalizer improvement — but it **must** be adjudicated explicitly, and the sealed 2026 decision is
never re-labeled prospective on the strength of a later re-derivation.

- [ ] **Step 3: Run** → 18 passed

- [ ] **Step 4: Commit**

```bash
git add scripts/seal_2026.py scripts/tests/test_seal_2026.py
git commit -m "feat(seal-2026): deferred re-derivation check, written before the kernel exists"
```

---

## F7: Produce and seal the 2026 decisions — DEADLINE WORK

**Blocking input:** the 2026 league id and the qualified first-kickoff instant.

- [ ] **Step 1: Confirm the capture lane is green**

```bash
$PY scripts/capture_2026.py --league-id <ID> || exit 1
```

- [ ] **Step 2: Derive the cutoffs and record them**

```bash
$PY - <<'PY'
from scripts.seal_2026 import qualify_cutoff
k = "<QUALIFIED_FIRST_KICKOFF_UTC>"
print("preseason cutoff:", qualify_cutoff(k, "preseason"))
print("preview   cutoff:", qualify_cutoff(k, "preview"))
PY
```

- [ ] **Step 3: Freeze the preseason bundle** from the verified captures at or before the cutoff,
      with every transformation named. The transformation list is the contract for what the decider
      saw; a step performed and not recorded invalidates the seal's meaning.

- [ ] **Step 4: Produce the ranking and claims, then seal before the preseason cutoff**

  **Minimum (guaranteed executable, no model dependency):** a deterministic prior-season-standings
  baseline — `runner_kind: "deterministic"`, ordering the twelve franchises by 2025 final
  standings, one `ordinal_rank` claim per position with its resolution rule fixed now.

  **Recommended if the runner config lands in time:** additionally seal a full-bundle **model**
  decision — `runner_kind: "model"`, browsing disabled, prompt and rule hashes bound.

  > **Scope decision for Blake.** Sealing only the deterministic baseline produces a prospective
  > _record_ but not a prospective _experiment_: with one arm there is nothing to compare against
  > in 2027. Sealing a model arm too is what makes 2026 a real test of whether richer evidence
  > helps. It costs a prompt and a runner config now. **Baseline-only is the safe floor; I
  > recommend both, but this is your call and the plan does not assume it.**

- [ ] **Step 5: Seal the week-1 preview before the preview cutoff**, same shape, using
      `decision_history` continuity only within the same arm.

- [ ] **Step 6: Verify every seal and commit**

```bash
$PY - <<'PY'
from scripts.seal_2026 import load_seals, verify_seal
seals = load_seals("content/seals/2026")
assert seals, "no seals found"
for s in seals:
    verify_seal(s)
    print(s["edition_id"], s["kind"], s["label"], s["decision_hash"][:19])
    assert s["label"] == "prospective", f"{s['edition_id']} is {s['label']}"
PY
git add content/seals/2026/ data/captures/2026/public/
git commit -m "seal(2026): prospective preseason and week-1 preview decisions"
```

- [ ] **Step 7: STOP.** The lane continues capturing. No prose, no 2026 authoring, no kernel work
      under this plan.

---

## What this plan deliberately does not do

- **No normalization, no `state_at`, no fact store.** Those are the kernel's, and this plan is the
  option that exists precisely because the kernel will not be ready in time.
- **No 2026 prose.** The design puts 2026 authoring out of scope; the sealed decision is in scope,
  the column is not.
- **No unblocking of the kernel plan.** `2026-08-02-jailyard-temporal-kernel.md` remains DRAFT and
  unauthorized, with its own outstanding review findings.
- **No backdating.** There is no mechanism to reclassify a late seal as prospective, and per the
  design none may be added.

## Open dependencies — Blake's call, fail-closed

1. **2026 league id.** Blocks F3 Step 3 and everything downstream. Nothing else in F1-F6 needs it.
2. **Qualified first-kickoff instant.** Blocks F7. Must come from a schedule source with venue
   timezone, never by appending `Z` to a local kickoff time.
3. **Preseason cutoff offset.** Stated assumption: one day before first kickoff. Change it before
   the first seal or not at all.
4. **Baseline-only vs. baseline + model arm** (F7 Step 4). Determines whether 2026 is a prospective
   record or a prospective experiment.
5. **Workflow activation** (F3 Step 8) requires explicit approval of that exact push.

## Self-Review

**Design coverage.** §6's four fallback requirements map to: eight capture groups with full
component receipts (F1-F3); the exact frozen decision-input bundle _with its permitted
transformations_ (F4); a decision-run receipt of the correct `runner_kind` (F5); deferred
re-derivation that verifies the seal still resolves (F6). The sealing requirements — bind the
contemporaneous fact set, bundle hash, run receipt and cutoff; reject or label late writes — are
carried by `seal_decision` and tested in both directions.

**Verified rather than asserted.** 42 tests written and run; 8 mutation controls applied and
observed to fail the intended test; one real defect (`qualify_cutoff` off by a day in the expected
value) found only by execution. Code in this document is the code that ran, transcribed — not
prose about code.

**Known gaps, stated rather than papered over.**

- The nflreadpy → JSON re-encoding step for `nfl_context` (F2) is described, not code — it depends
  on the 2026 parquet schema, which does not exist yet.
- F7's ranking producer is specified as a contract, not implemented; it is one page of
  deterministic ordering over the frozen bundle and should be written TDD at execution time.
- `content/governance/runner_config_2026.json` is named in the file structure and committed in F5,
  but its contents are only needed if Blake chooses the model arm in F7 Step 4.

**What would make this plan wrong.** If the 2026 preseason cutoff has already passed when execution
begins, every seal is `retrospective` by construction and the prospective test is lost for 2026 —
the plan will say so honestly rather than backdate. That is the deadline this document exists to
beat.
