# ADR-0002: Grounded answers with inline citations are required

- Status: Accepted
- Date: 2026-06-18

## Context

The agent answers questions over enterprise documents in a simulated sensitive-data, multi-tenant setting. Ungrounded model output is a liability in exactly the regulated environments this project mirrors. Cohere's Chat endpoint returns verifiable inline citations natively.

## Decision

Every agent answer that draws on documents must carry inline citations tying each claim back to its source passage. An answer over documents that lacks citations is treated as a defect, not a stylistic variation. The UI must surface these sources to the user.

## Consequences

Higher trust and auditability, and a clear visual story in the interface. The eval harness must check both citation presence and correctness, not just answer text. The trade-off is some added latency and prompt complexity, accepted as core to the value of the product.
