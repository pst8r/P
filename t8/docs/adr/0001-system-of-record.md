# ADR-0001: Ticket system of record — discriminated aggregate, both modes first-class

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15
- **Settles:** PROMPT.md §13 Q1

## Context

T8 can own the `Incident`/`ServiceRequest` lifecycle, or sit in front of an
incumbent ITSM (ServiceNow, Jira SM) that owns it. The two shapes have opposite
write paths: in one our state machine is authoritative, in the other it is
advisory and a remote system's response is truth.

Picking one and retrofitting the other is expensive because the choice
contaminates every write path — roughly three to four engineer-months. Building
both costs about one engineer-month in Phase 1, concentrated in the repository
layer and conflict handling.

The product owner chose **both, equal priority from day one**.

## Decision

`Incident` and `ServiceRequest` carry a **`system_of_record` discriminator**:

- **`T8`** — we own the lifecycle. The state machine in `core-domain` is
  authoritative. Transitions commit locally with their audit event.
- **`EXTERNAL`** — the incumbent owns the lifecycle. Our aggregate is a
  **projection**. The state machine *validates* a proposed transition before we
  attempt it remotely, but the incumbent's response is truth: on divergence the
  remote state wins and we record a reconciliation event.

Both modes share one aggregate type, one set of invariants, and one audit path.
They differ only in who commits the transition.

**Always T8-owned regardless of mode:** `Interaction`, `KnowledgeArticle`,
`AgentRun`/`AgentStep`, `AuditEvent`, `Approval`, `ConfigurationItem`. These are
the product; they are never projections.

Conflict handling in `EXTERNAL` mode:

- Every outbound transition carries an idempotency key and the projection
  version we believed current.
- A rejected or superseded transition produces a `ReconciliationEvent` in the
  ledger, never a silent overwrite.
- Fields the incumbent owns are never written locally except by reconciliation.
- Divergence detectable for longer than a configured window escalates rather
  than retrying indefinitely (P10, fail closed).

## Consequences

**Positive.** No bet is placed on the go-to-market question. T8 can front an
incumbent — the realistic enterprise entry point — and can become the system of
record for the same customer later without a migration of our code. The
discipline of writing an aggregate that cannot assume local authority also
produces a cleaner domain model than the T8-only version would.

**Negative.** Two test matrices for every lifecycle change, permanently. The
`EXTERNAL` path has failure modes (remote unavailability, partial writes,
clock skew, field ownership) that do not exist locally and must be designed,
not discovered. Phase 1 grows by ~1 engineer-month.

**Risk.** The projection can drift silently if reconciliation is not
adversarially tested. Phase 10's definition of done is therefore *induced*
conflict, not observed absence of conflict.

## Alternatives considered

- **T8 as sole system of record.** Simpler write path, cleaner state machine,
  much harder first sale, and it delays every `M11` integration's value.
- **Front-only, projection-only.** Fastest to a first deal; forecloses ever
  being the system of record without the retrofit this ADR exists to avoid.
- **Two separate aggregate types.** Rejected: duplicates invariants, and the
  duplication would drift.
