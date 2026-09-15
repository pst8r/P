# ADR-0010: Tenancy — pooled multi-tenancy with RLS, context propagated everywhere

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15
- **Settles:** part of PROMPT.md §13 Q2 (SaaS delivery)

## Context

The product owner chose **SaaS delivery**. That makes pooled multi-tenancy the
launch architecture rather than one option among several: we operate one
deployment serving many tenants, with the economics and the risks that implies.
P7 requires row-level isolation enforced at the datastore, with tenant context
flowing through every call **including agent tool calls** — the path most likely
to lose it, since it crosses a language boundary (ADR-0009) and sometimes a
network boundary (ADR-0008).

## Decision

**Pooled multi-tenancy, isolated by PostgreSQL Row-Level Security.**

- Every governed table carries `tenant_id` with an RLS policy. There is no
  application-level tenant filtering as the primary control.
- Tenant context is set as a session variable by the repository layer on every
  connection checkout and cleared on release. Connection pools are never shared
  across tenant contexts without an explicit reset.
- **Tenant context is part of every contract**: API calls, events on the bus,
  blackboard writes, tool invocations on both registry surfaces, LLM gateway
  calls (which also select the tenant's provider binding, ADR-0006), and every
  audit event.
- **Tenant context is re-derived server-side, never trusted from a request
  body.** A tool call that asserts its own tenant is a rejected call.
- **Silo deployment is the same code.** A single-tenant VPC or air-gapped
  install (ADR-0017) runs the identical build with one tenant. We do not
  maintain a separate single-tenant path.

**Standing negative test suite, from Phase 0, as a release gate:** for every
access path — API, event consumer, retrieval, blackboard, tool call, gateway,
ledger query, evidence pack — a test that *attempts* a cross-tenant read or
write and asserts it fails. New access paths ship with their negative test or
they do not ship.

## Consequences

**Positive.** SaaS economics, one deployment to operate and upgrade, and
isolation that fails closed at the database rather than depending on every
developer remembering a `WHERE` clause. The silo shape costs nothing extra
because it is the same build.

**Negative.** A single RLS misconfiguration is a cross-tenant data leak — the
incident from which an enterprise product does not recover. This is the reason
the negative suite is a gate rather than a nice-to-have, and the reason RLS is
the primary control rather than a backstop.

**Negative.** Noisy-neighbour effects are ours to manage: per-tenant rate limits,
agent step and cost budgets (ADR-0007), and per-tenant resource accounting are
operational requirements from day one, not scale-up work.

**Negative.** Some queries are harder to optimize under RLS, and per-tenant
index strategies are constrained. Accepted.

## Alternatives considered

- **Schema-per-tenant.** Stronger isolation optics; painful migrations across
  hundreds of schemas and a much worse `M03`/analytics story. Rejected.
- **Database-per-tenant.** Strongest isolation; contradicts SaaS economics at
  the scale we are building for, and multiplies operational surface. It remains
  available as a deployment shape for a customer who requires it, since the
  build is identical.
- **Application-level filtering with RLS as backstop.** Inverts the failure
  mode: the safety net becomes the thing you rely on noticing. Rejected.
