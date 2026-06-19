# spec-0001 — RAG core

- Status: Draft
- Date: 2026-06-18
- Related: ADR-0001 (Cohere-native), ADR-0002 (grounded citations), ADR-0005 (determinism boundary), ADR-0006 (eval gate)

## Purpose

Build the retrieval spine: ingest enterprise documents, retrieve the right passages for a query, and produce a grounded answer with inline citations using Cohere's stack. This is the foundation the agent's `rag_search` tool will call later.

## Scope

**In**
- A small synthetic corpus of enterprise documents (warranty policies and manuals)
- Ingestion: load, chunk, embed (Embed 4), store in pgvector
- Retrieval: embed query, vector search, rerank (Rerank 4)
- Grounded answer: Command produces an answer with verifiable inline citations
- A retrieval eval set and a script that scores it

**Out (later days)**
- The agent loop and tool wiring (Day 4-6)
- The claims database and tenant scoping (Day 3-4)
- The UI (Day 6-8)

## Synthetic corpus

A handful (6-10) of short, synthetic warranty documents: a warranty policy, a coverage matrix, an exclusions list, an RMA/returns procedure, and a couple of product manuals. Plain markdown, IP-clean, with clear headings so chunks map to citable sections. These live under `data/corpus/`.

## Pipeline

**Ingest** (`caselens.rag.ingest`)
1. Load each document and split into section-aware chunks (respect headings; target ~800-1000 chars with ~100 char overlap; tunable).
2. Embed each chunk with Embed 4 (`embed-v4.0`, `input_type=search_document`), batched to conserve the call budget.
3. Store chunk text, source metadata, and the embedding vector in pgvector.

**Retrieve** (`caselens.rag.retrieve`)
1. Embed the query with Embed 4 (`input_type=search_query`).
2. Vector search for the top-k candidates (k=20, cosine distance; tunable).
3. Rerank candidates with Rerank 4 (`rerank-v4.0`) and keep the top-n (n=5; tunable).

**Answer** (`caselens.rag.answer`)
1. Pass the top-n chunks to Command Chat as documents.
2. Return the grounded answer plus the structured inline citations Cohere provides.
3. An answer over documents that carries no citations is a defect (ADR-0002).

Retrieval and reranking are deterministic code; the model only writes the final answer (ADR-0005).

## Data model (pgvector)

- `documents(id, source_path, title, created_at)`
- `chunks(id, document_id, section, ordinal, text, embedding vector(1536), metadata jsonb)`
- Index: `chunks.embedding` with `vector_cosine_ops`.
- Embedding dimension must match the Embed 4 output dimension in config (default 1536; tunable).

## Interfaces (Python)

- `ingest_documents(paths: list[str]) -> IngestReport`
- `retrieve(query: str, k: int = 20, n: int = 5) -> list[RetrievedChunk]`
- `answer(query: str) -> GroundedAnswer`  where `GroundedAnswer = {text, citations, sources}`

## Decisions in this spec

- Store: Postgres + pgvector, cosine distance.
- Embedding: Embed 4, `search_document` for chunks and `search_query` for queries, output dim 1536.
- Chunking: heading/section-aware, ~800-1000 chars, ~100 overlap.
- Retrieval: top-k=20 vector search, then Rerank 4 to top-n=5.
- Grounded answer via Command with documents and inline citations.

## Eval (retrieval golden set)

- `eval/golden/retrieval.jsonl`: 10-15 cases, each `{query, expected_source, expected_section}`.
- Metrics: recall@k (did the expected section make the top-k), and rerank lift (rank before vs after Rerank 4).
- A grounded-answer check: the answer cites at least one of the expected sources.
- This script is the seed of the CI eval gate (ADR-0006); wire it into CI on a later day, not yet.

## Cost guardrails

- Batch chunk embeddings into as few calls as possible.
- The corpus is small on purpose so ingestion stays well within the 1,000-call trial budget.
- Re-ingest only on corpus change, not on every run.

## Tunables

Chunk size and overlap, k, n, and embedding dimension are all config values, not hardcoded.
