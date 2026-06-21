# ADR-0007 — Native grounded citations over the agent's final answer

- Status: Accepted
- Date: 2026-06-20
- Refines: ADR-0002 (grounded citations required)
- Affects: spec-0001 (RAG), spec-0003 (agent), spec-0004 (UI)

## Context

`rag_search` currently returns a pre-composed grounded answer plus citations whose character offsets map to that sub-answer. But the agent's final answer is composed separately by Command and is usually shorter. The live SSE smoke confirmed the mismatch: the final answer was a single sentence while the citations spanned the full sub-answer (offsets to ~985 over a ~108-char answer). Only the first few citations aligned by coincidence; the rest pointed at text not present in the displayed answer. The UI cannot reliably highlight citations inline against the answer it shows.

## Decision

The agent produces citations natively over its own final answer.

- `rag_search` becomes a retrieval tool. It returns the reranked passages (id, source, title, section, text), not a pre-composed answer.
- The agent's final Command turn receives those passages as `documents`, so Command grounds its answer and returns Cohere-native citations whose offsets map to the answer it actually generated.
- Citation events surfaced to the UI carry offsets over the final answer text and a mapping from each citation to its source passages.

This is also the idiomatic Cohere RAG-in-tool-use pattern, which strengthens the Cohere-native story.

## Consequences

- Citations align with the displayed answer; the UI can highlight them inline without guesswork.
- Grounded generation moves out of a separate compose step and into the agent's Command call. `rag_search` no longer composes prose.
- The retrieval eval (spec-0001) is unchanged; it still validates retrieval quality independent of generation. The agent eval still asserts citations are present, now native.
- The standalone RAG answer path (CLI) may keep its own compose step; the agent path uses native grounding.
- The documents-to-citation mapping must be verified live with the key, since it depends on Command's citation output referencing the supplied document ids.
