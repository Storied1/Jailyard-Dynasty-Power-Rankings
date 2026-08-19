# Edit an Edition (week ${WEEK})

The binary quality gate for `content/weeks/week${WEEK}_content.json`. Verdict
is APPROVE, REVISE, or REJECT; there is no "approve with notes." If anything
needs fixing, the verdict is REVISE. Fix first, approve second.

## Run the validator first

```bash
python scripts/verify_week_content.py --week ${WEEK} --pretty
```

Any validator error is an automatic REVISE.

## Review against

1. `content/editorial-standard.md`: the product bar, style constraints, and
   the reader test. Review for judgment, specificity, rhythm, surprise,
   owner-level attention, and fair comedy; not against a section checklist.
2. **Source traceability**: every quote verbatim in the chat context; every
   number in the data packet; every callback in a published edition; outside
   coverage carries a publication date at or before the cutoff. Untraceable
   material is REVISE.
3. **Style constraints**: any em dash, any "it's not X, it's Y" construction,
   any prose about how the column gets made, any machine-made phrasing is
   REVISE.
4. **Temporal integrity**: nothing the edition's moment could not know: no
   later results, quotes, injuries, standings, or Elo; no prophecy framing of
   unresolved events.
5. **Data accuracy**: scores, records, margins, stat lines, NFL opponents,
   Elo, and h2h claims match the packet exactly. Momentum language tracks the
   packet's momentum labels.
6. **Rankings**: order matches the gate-passed judgment record declared in
   `meta.ranking_source`; per-team facts match the standings.
7. **Tone**: roasts land on rosters and decisions, never on people's lives.
   Non-partisan, never cruel.
8. **Interpretive warrant**: every attributed belief traces to the owner's own
   words plus a decision he made. Repeated conduct supports a qualified
   characterization only. A roster or transaction alone supports "bets as if",
   never private motive. Thin evidence must read as an open question. An
   invented interior passes every executable gate, so this one is read by eye
   or it is not checked at all. Fabricated inner life is REJECT, not REVISE.
9. **Function preservation** (revision passes only): compare against the
   previous version. For every removed passage, name the editorial function it
   carried: factual grounding, causal explanation, character, tension, comedy,
   surprise, comparison, wider meaning, or a receipt a later edition settles. A
   working function that vanished without being ruled unsupported, redundant,
   unsuccessful or unearned is REVISE. Location, wording, length and structure
   may all change freely; the function is what has to survive.

Note on 8 and 9: the executable gates are negative safety constraints. They
detect the absence of defects and cannot detect the absence of a virtue. Do not
resolve that by cutting. A pass that only removes material is a pass that made
the edition safer and worse.

## Output

A short report: verdict, findings with exact locations, and what worked.
Append one JSONL line to `content/review-log.jsonl` per pass (create the file
on first use): `{"piece": "week-${WEEK}", "pass_number": N,
"reviewed_at_utc": "...", "verdict": "...", "findings": ["..."]}`. The log is
append-only; never rewrite existing lines.
