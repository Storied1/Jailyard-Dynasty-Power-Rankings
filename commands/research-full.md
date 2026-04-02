You are executing the FULL MECE deep research pipeline — all phases (0-6) in sequence.

## Input
Topic: $ARGUMENTS

If --depth is specified, use that depth level. Otherwise default to 3 (practitioner).
If --format is specified, use that output format. Otherwise default to briefing.

## Execution Sequence

Run all three phases in sequence. Do NOT skip any phase.

### 1. SCOPE FRAME (Phase 0)
- Parse the topic into a clear research question
- Set boundaries (in scope / out of scope)
- Apply the specified depth level
- Identify the decision context if any
- Generate the layer-by-layer research plan
- Save to `research-plan.md`
- DO NOT ask for confirmation — proceed directly (the user chose /research-full because they want the whole thing)

### 2. MECE SWEEP (Phases 1-5)
- Execute all five layers per the plan
- Keep layers clean — no bleed between layers
- Scale effort to depth level
- Use web search aggressively for current data (Facts, Temporal)
- Use targeted searches for expert analysis (Mechanisms, Contrarian)
- Save to `research-sweep.md`

### 3. SYNTHESIS (Phase 6)
- Reorganize findings by importance, not by layer
- Produce the deliverable in the specified format
- Tag confidence levels on major claims
- List open questions for follow-up
- Save to `research-output.md`

## Output

Present the final research deliverable to the user. Also note:
- Where the supporting files are (plan, sweep, output)
- The top 2-3 open questions for potential follow-up
- Your overall confidence in the research quality given the depth level

## Pacing

For depth 1-2: This should be a focused, efficient pass. Don't over-research.
For depth 3: Thorough but not exhaustive. 5-10 searches total.
For depth 4-5: Go deep. 10-20+ searches. Pull full articles. Cross-reference sources.
