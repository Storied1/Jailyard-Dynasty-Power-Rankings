# Edit the Preseason Edition

The binary quality gate for `content/preseason-2025/preseason_content.json`.
Same standard, source-traceability, style, temporal, and verdict discipline as
`/edit-week` (APPROVE / REVISE / REJECT; no "approve with notes"), applied at
the preseason vantage: nothing from the season itself is knowable, every claim
traces to a source dated at or before the preseason cutoff, and the rankings
are falsifiable positions the season will grade. Log passes to
`content/review-log.jsonl` as `"piece": "preseason-2025"`.

## Executable gates (run both; any RED is an automatic REVISE)

```bash
python scripts/build_preseason_evidence.py --verify
python scripts/verify_week_content.py --preseason --pretty
```

The first verifies the private writer bundle against the tracked manifest
(the source the claims must trace to). The second is the preseason ranking
gate: authored content exists, `meta.ranking_source` resolves to a
gate-passed judgment record, and the published order matches it exactly.
Source traceability is checked against the private bundle
`private_bundles/preseason-2025/preseason_evidence.json`.

## Read by eye, because no gate covers these

Criteria 8 and 9 of `/edit-week` apply in full and carry extra weight at the
preseason vantage, where there are no results and the human hand is nearly all
the material there is:

- **Interpretive warrant.** Every attributed belief traces to the owner's own
  words plus a decision he made. Repeated conduct supports a qualified
  characterization only. A roster or transaction alone supports "bets as if",
  never private motive. Thin evidence must read as an open question.
  Fabricated inner life is REJECT, not REVISE.
- **Function preservation.** On a revision pass, name the editorial function of
  every removed passage. A working function that vanished without being ruled
  unsupported, redundant, unsuccessful or unearned is REVISE. Structure,
  wording, length and evidence selection may all change; function survives.

The executable gates are negative safety constraints. They detect the absence
of defects and cannot detect the absence of a virtue. A pass that only removes
material is a pass that made the edition safer and worse.
