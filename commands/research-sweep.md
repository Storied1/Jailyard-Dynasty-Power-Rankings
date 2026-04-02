You are executing the MECE RESEARCH SWEEP — Phases 1-5 of the deep research framework.

## Prerequisites
A research plan MUST exist (created by /research-plan). Read `research-plan.md` first. If it doesn't exist, tell the user to run /research-plan first.

## Input
$ARGUMENTS (optional overrides or focus areas)

## Execution

Work through each layer IN ORDER. Each layer builds on the previous but contains ONLY information that belongs in that layer. Keep layers clean — no bleed.

### Layer 1: FACTS
Gather verifiable, non-interpretive information per the research plan.
- Search for current data, statistics, definitions
- Pull primary sources (gov data, official docs, peer-reviewed research)
- Record each fact with its source
- Flag anything contested — move the debate to Layer 5
- Output: Bullet list of sourced facts

### Layer 2: MECHANISMS
Map causal chains and system dynamics per the research plan.
- Identify the 2-3 most important causal relationships
- Draw out feedback loops (reinforcing and balancing)
- Use first-principles reasoning where expert sources are thin
- Output: Causal chain descriptions, optionally with simple diagrams

### Layer 3: STAKEHOLDERS
Map actors, incentives, and power dynamics per the research plan.
- For each actor: What do they want? What do they fear? What's their leverage?
- Follow the money
- Identify silent stakeholders (affected but not at the table)
- Map alliances and oppositions
- Output: Stakeholder map with incentive analysis

### Layer 4: TEMPORAL
Map timeline and trajectories per the research plan.
- Origin story and key inflection points
- Current state as a point on a trajectory
- 2-3 plausible future scenarios (not predictions)
- Search for RECENT developments that shift trajectories
- Output: Timeline + scenario descriptions

### Layer 5: CONTRARIAN
Stress-test the consensus per the research plan.
- State the consensus view explicitly
- Find the strongest counterarguments (sourced, not invented)
- Surface underweighted risks and blind spots
- Identify assumptions baked into conventional wisdom
- Ask: "What would need to be true for the consensus to be wrong?"
- Output: Structured red team analysis

## Layer Discipline

After completing each layer, do a quick check:
- Did I put anything in this layer that belongs in another? Move it.
- Did I leave gaps in this layer? Fill them.
- Is this layer proportionate to the depth level? Calibrate.

## Output

Save all layer outputs to `research-sweep.md` in the current working directory, organized by layer with clear headers. This feeds into /research-synthesize.

Tell the user the sweep is complete and summarize the most surprising or important finding from each layer before they review the full document.
