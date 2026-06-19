# ADR-0005: Determinism boundary

- Status: Accepted
- Date: 2026-06-18

## Context

Reused from a prior project (LedgerLens). Language models are strong at deciding and explaining but must not be the source of truth for numbers, data reads, or state changes.

## Decision

The agent reasons, selects tools, and explains its choices. Deterministic code performs the actual data reads, calculations, and actions. The model never computes a figure or mutates state directly; it calls a tool that does, and the tool's result is authoritative.

## Consequences

Correctness and reproducibility for anything that matters, and a clean separation that makes the system testable in isolation from the model. The trade-off is a larger tool surface to build and maintain, which is the right cost for trustworthy behavior over sensitive data.
