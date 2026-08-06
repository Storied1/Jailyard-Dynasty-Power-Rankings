# Jailyard Dynasty — Power Ranking Decision (K3 evaluation prompt)

This prompt is IDENTICAL across all four model arms. Arm differences measure
evidence, never prompt: only the evidence bundle differs between arms.

## Task

You are ranking the 12 franchises of a fantasy football dynasty league at a
fixed temporal cutoff. You receive one JSON evidence bundle. It is your ONLY
source of truth.

Rules:

1. **Use only the bundle.** Do not use outside knowledge of any fantasy league,
   NFL season outcome, or player performance beyond what the bundle contains.
   Facts about real NFL teams and players appearing in the bundle are genuine
   public context; everything after the stated cutoff is unknown to you.
2. **Teams are opaque.** Franchises appear as opaque tokens and roster_ids.
   Do not attempt to identify owners or real team names. Rank the roster_ids.
3. **Rank all 12 franchises**, 1 = strongest going forward. Exactly one entry
   per franchise; every roster_id in the bundle's franchise list must appear
   exactly once.
4. **Every position carries at least one scoreable claim.** A claim asserts a
   verifiable future outcome for that franchise, with a resolution rule fixed
   now. Claim types:
   - `ordinal_rank` — asserted final regular-season standings position
     (integer 1-12); rule `final_regular_season_rank`, source `standings`.
   - `binary_probability` — probability in [0, 1] of a stated binary outcome.
   - `bounded_quantity` — a numeric estimate with a stated `bound` used to
     normalize error.
5. **Confidence is honest.** `confidence` in [0, 1] reflects your actual
   uncertainty given the evidence; do not report uniform confidence.
6. **Evidence citations are bundle-relative.** `decisive_evidence` lists the
   bundle facts that drove the position; `contrary_evidence` names the
   strongest fact against it. Cite what exists; never invent.

## Output

Reply with EXACTLY one JSON object, no markdown fences, no commentary:

```
{
  "ranking": {
    "entries": [{ "team": "<roster_id>", "rank": 1 }, ...12 entries...]
  },
  "claims": [
    {
      "target": "<roster_id>",
      "claim_type": "ordinal_rank",
      "horizon": "rest_of_season",
      "assertion": 3,
      "confidence": 0.62,
      "decisive_evidence": ["<bundle citation>", "..."],
      "contrary_evidence": "<bundle citation>",
      "resolution_rule": {
        "rule": "final_regular_season_rank",
        "source": "standings",
        "resolve_on": "2026-01-06T00:00:00Z"
      }
    },
    ...at least one claim per ranking entry...
  ]
}
```

The response must parse as JSON. An unparseable response is a failed trial.
