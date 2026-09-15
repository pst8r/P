# ADR-0009: Language split and the governed-write rule

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

PROMPT.md §9 splits the stack: Python (typed, Pydantic) for agent/AI services,
TypeScript for business/API services. A two-language backend is a real tax —
duplicated types, two toolchains, two dependency surfaces, a contract that can
drift, and a hiring profile that must cover both.

It is nonetheless the right call: the AI side genuinely needs Python for the
evaluation harness, embeddings and retrieval tooling, and forcing that into
TypeScript costs more than the boundary does. But an unmanaged split becomes two
half-systems that each implement half the invariants.

## Decision

**Python** owns: agent runtime and orchestration (ADR-0007), retrieval and
ranking, the evaluation harness, embedding and ingestion pipelines.

**TypeScript** owns: the API gateway, ITSM domain services, the repository
layer, the policy decision point, workflow coordination, and the web
applications.

**The boundary is one generated contract surface.** Types and API/event schemas
live in `core-contracts` and are generated into both languages. No hand-written
duplicate of a shared type on either side; a schema change that breaks a
consumer breaks CI.

**The governed-write rule — the load-bearing part of this ADR:**

> **Python services never write to governed tables.**

All governed mutations go through the TypeScript repository layer, which is the
single place implementing "audit event in the same transaction" (ADR-0003, P5).
Python may *read* governed data through RLS-scoped connections (blackboard,
retrieval, CI graph). Anything an agent wants to **change** is an API call
carrying tenant context — which is also exactly where the policy gate sits
(ADR-0013).

Enforced by: distinct database roles (the Python role has no write grant on
governed tables), plus a CI check on migrations that a governed table grants
write only to the repository role.

## Consequences

**Positive.** One invariant, one implementation, one place to audit. The rule
also forces every agent mutation through the policy decision point by
construction rather than by convention — the two most important guarantees in
the product fall out of a single database grant.

**Positive.** The boundary is coarse and legible: "agents read, services write."
New engineers can hold it in their head, which matters more than elegance.

**Negative.** An agent action is a network call, not a function call — added
latency and a failure mode. Accepted: an agent mutation that *cannot* fail
independently of its authorization check would be worse.

**Negative.** Contract maintenance is permanent overhead. Mitigated by
generation rather than hand-written mirrors, and by failing CI on drift.

## Alternatives considered

- **TypeScript only.** One language, one toolchain; gives up the Python AI
  ecosystem where the evaluation harness and retrieval work actually live.
  Rejected.
- **Python only.** Viable, and simpler in some ways; weaker for the transactional
  service layer and the frontend shares nothing. Rejected.
- **Split without the governed-write rule.** The default outcome, and the bad
  one: two repository layers, two audit implementations, and eventually a
  mutation path that forgot one. Rejected.
