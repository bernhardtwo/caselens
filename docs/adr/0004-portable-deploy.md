# ADR-0004: Portable, cloud-agnostic deployment

- Status: Accepted
- Date: 2026-06-18

## Context

The target role values deploying into private or hybrid cloud and into customer environments. Tying the system to one cloud's managed services would undercut that story and the project's central narrative.

## Decision

The deliverable is a cloud-agnostic container that can run on any cloud or inside a customer VPC. The first deploy target is Azure Container Apps with scale-to-zero, reusing prior deployment experience, but no managed-service lock-in is introduced into the core of the system.

## Consequences

Demonstrable portability and an easy re-target to GCP Cloud Run or a customer environment later. The container, not a cloud account, is the unit of delivery. The trade-off is forgoing some convenience of deep managed-service integration, accepted deliberately.
