# ADR-0001: Cohere-native agent stack

- Status: Accepted
- Date: 2026-06-18

## Context

This project is a portfolio piece targeting Cohere's Forward Deployed Engineer, Agentic Platform role. The strongest signal we can send is fluency with Cohere's own platform. Several agent frameworks exist (Google ADK, LangGraph), and an earlier draft of this project leaned on Google ADK for a different role with a GCP-native emphasis.

## Decision

Build the agent directly on Cohere's API: Command (Chat with tool use) for reasoning and tool selection, Embed 4 for embeddings, and rerank-v3.5 for retrieval reranking. Do not adopt Google ADK. Introduce LangGraph only if the agent's control flow genuinely outgrows a single tool-use loop.

## Consequences

Maximum alignment with the target platform and minimal abstraction between our code and Cohere's primitives. We own the orchestration logic ourselves, which is the point: it demonstrates real fluency rather than framework familiarity. The trade-off is reduced portability to other model providers, which is acceptable for this project's goals.
