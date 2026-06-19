# ADR-0003: Security-first by default

- Status: Accepted
- Date: 2026-06-18

## Context

The agent operates over sensitive, multi-tenant enterprise data and can take actions on it. The target role explicitly involves agents interacting with sensitive customer data in regulated sectors such as finance, healthcare, and telecommunications.

## Decision

Enforce tenant and user data scoping at the data-access layer, not in prompts or application glue. Apply role-based access control to tools and actions. Record an append-only audit entry for every tool call and every action the agent takes.

## Consequences

A stronger, demonstrable security posture: scoping lives below the agent, so it cannot be bypassed by prompt injection or a misbehaving model. The audit log gives a reviewable trail of agent behavior. The trade-off is more upfront data-layer work and the discipline of applying scoping in every query path.
