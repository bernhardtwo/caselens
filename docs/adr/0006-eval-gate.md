# ADR-0006: Evaluation as a CI gate

- Status: Accepted
- Date: 2026-06-18

## Context

The role values rapid, high-quality experimentation. Agent quality regresses silently without a measurement loop, and changes to prompts, retrieval, or tools can break behavior in ways unit tests do not catch.

## Decision

Maintain a golden set of cases covering retrieval quality, tool-use correctness, citation presence, and scoping enforcement. Wire it into CI as a gate. The agent does not ship if it regresses against the golden set.

## Consequences

Confidence to iterate quickly, with regressions caught before deploy rather than in a demo. The golden set becomes a first-class artifact and evidence of engineering rigor. The trade-off is that the set needs maintenance as the agent evolves, accepted as part of the workflow.
