# ADR-0005: Durable execution — WorkflowPort, Postgres adapter first, Temporal at Phase 5

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

PROMPT.md §9 lists a durable execution engine (Temporal or a justified
alternative) among the stack defaults, and §11 places foundations in Phase 0.
But the workloads that need durable execution — multi-system sagas with
compensating transactions, long-running approvals, fulfillment workflows — do
not appear until Phase 5.

Standing Temporal up in Phase 0 means every developer machine, every CI run and
every air-gapped install carries that dependency for five phases before it does
any work. Conversely, retrofitting durability into code written without it is
genuinely painful.

The resolution: what is painful to retrofit is the **abstraction**, not the
implementation behind it.

## Decision

**Phase 0:** define `WorkflowPort` in `core-contracts` — durable step execution,
saga definition with compensating steps, timers, signals, deterministic replay,
and query of in-flight state. Implement a **Postgres-backed adapter**: a
transactional outbox plus a durable step runner that persists workflow state so
a restart resumes rather than restarts.

**Phase 0, also:** write the **contract test suite** against the port, including
the cases a Postgres runner is weakest at (long timers, high fan-out, worker
crash mid-compensation). These tests exist before the Temporal adapter does,
so the port cannot quietly grow Postgres-shaped assumptions.

**Phase 5:** adopt **Temporal** behind the same port when sagas and long-running
approvals arrive. Version pinned after verification against official
documentation at adoption time — not from memory.

## Consequences

**Positive.** Five phases without a heavy operational dependency; `make dev`
stays fast and the air-gap story stays simple for longer. P3 is satisfied
properly — a port with two adapters, one of which runs anywhere Postgres does.
If the Postgres adapter proves sufficient for the deployment shapes we actually
sell, that is a legitimate outcome rather than a shortcut.

**Negative.** We write and maintain a durable step runner. Bounded — a few
hundred lines over machinery we already have — but it is real code with real
edge cases, and it will be less battle-tested than Temporal.

**Risk.** The port leaks Postgres assumptions and the Phase 5 swap turns out to
be a rewrite. This is the reason for writing the contract tests in Phase 0; if
they cannot be written against the port without naming Postgres, the port is
wrong and we find out immediately rather than in month six.

## Alternatives considered

- **Temporal from Phase 0.** Best-in-class, and we will likely get there. The
  cost is carried for five phases against no workload. Rejected on timing, not
  on merit.
- **No durable engine; ad-hoc retries and state columns.** This is what
  "half-provisioned tenant" incidents are made of. PROMPT.md §5 is right to
  demand sagas with compensation. Rejected.
- **A lighter library (e.g. a DBOS-style or job-queue-based approach).**
  Plausible; evaluated properly at Phase 5 against Temporal, with the contract
  tests as the yardstick.
