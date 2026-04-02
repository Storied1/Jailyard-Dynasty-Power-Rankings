You are executing the SCOPE FRAME phase of a MECE deep research workflow.

Your job: Define the research scope before any investigation begins. This is Plan Mode for research — nothing gets researched until the scope is locked.

## Input
Topic: $ARGUMENTS

## Steps

1. **Parse the topic** — Restate it as a single clear research question.

2. **Set boundaries** — Propose what's IN scope and what's explicitly OUT. Be specific. "Everything about X" is not a scope.

3. **Calibrate depth** — Unless the user specified --depth, propose a depth level (1-5):
   - 1 = Executive briefing (5 min read)
   - 2 = Working knowledge (discuss intelligently)
   - 3 = Practitioner depth (make decisions)
   - 4 = Expert analysis (advise others)
   - 5 = Exhaustive (investigative/academic)

4. **Identify the decision** — Is this research feeding a specific decision? If so, name it. Research without a decision context tends to sprawl.

5. **Output format** — Propose: briefing doc, decision memo, investigation report, or conversational.

6. **Generate the layer plan** — For each of the 6 MECE layers, write 2-3 bullet points describing what specifically will be investigated in that layer FOR THIS TOPIC. This is the research plan.

   - FACTS: What specific data/definitions/stats will we gather?
   - MECHANISMS: What causal chains will we map?
   - STAKEHOLDERS: Which actors and incentives will we analyze?
   - TEMPORAL: What timeline and trajectories matter?
   - CONTRARIAN: What consensus views will we stress-test?
   - SYNTHESIS: What format will the final output take?

7. **Estimate effort** — Based on depth level, estimate how many searches/sources each layer needs.

## Output

Present the complete research plan and ask the user to confirm or adjust before proceeding to /research-sweep.

Save the plan to `research-plan.md` in the current working directory.
