You are executing the SYNTHESIS phase — Phase 6 of the deep research framework.

## Prerequisites
Both `research-plan.md` and `research-sweep.md` must exist. Read both before proceeding. If either is missing, tell the user which command to run first.

## Input
$ARGUMENTS (optional: override output format, add specific synthesis questions)

## Core Principle

The synthesis is NOT a summary of each layer. It reorganizes insights by IMPORTANCE and RELEVANCE to the user's decision context. The MECE layers were research scaffolding — the output structure should serve the reader, not mirror the research process.

## Execution

1. **Re-read the scope frame** — What was the research question? What decision is this feeding? What format was requested?

2. **Extract the top findings** — Across ALL five layers, identify the 5-10 most important findings. Rank by:
   - Surprisingness (did this challenge priors?)
   - Decision-relevance (does this change what you'd do?)
   - Confidence (how well-sourced is this?)

3. **Produce the deliverable** based on the format set in the plan:

   **Briefing Doc:**
   - Executive summary (3-5 sentences capturing the full picture)
   - Key findings organized by insight, not by layer
   - Implications and "watch for" items
   - Confidence assessment (what are we sure about, what's uncertain?)
   - Recommended next steps

   **Decision Memo:**
   - The decision, stated clearly
   - Key findings bearing on the decision (cite which layers)
   - Recommendation with confidence level (high/medium/low)
   - Key risks and mitigants
   - What new information would change the recommendation

   **Investigation Report:**
   - Summary of findings
   - Evidence organized by claim
   - Gaps in evidence
   - Confidence assessment per finding
   - Recommended next investigative steps

   **Conversational:**
   - Lead with the most surprising or important finding
   - Walk through the logic naturally
   - End with "here's what I'd do / watch for"

4. **Confidence tagging** — For each major claim in the synthesis, tag confidence:
   - HIGH: Multiple independent sources, no credible dissent
   - MEDIUM: Good sourcing but some uncertainty or debate
   - LOW: Limited sourcing, significant contrarian arguments, or extrapolation

5. **Open questions** — List 2-5 questions the research couldn't fully answer. These are the natural next investigations.

## Output

Save the final deliverable to `research-output.md` (or `.docx` if the user requested a formal document) in the current working directory.

Present the deliverable to the user. End with the open questions as suggested follow-ups.
