# ADR-0015: Modularity — manifests, enforcement points, and how many boundaries are real at launch

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

§4 makes module boundaries the SKU boundaries and requires that any purchased
subset build, deploy and run alone — twelve modules, each independently
deployable, each with its own migrations, contracts and deployment topology.

That is the correct long-run structure and the wrong launch structure. Twelve
deployment stories is a large, permanent tax paid before any customer has said
which subsets they would buy. It is a reliable way for a platform company to
spend a year shipping infrastructure instead of product.

The discipline that preserves the option, however, is cheap.

## Decision

### Enforced from Phase 0 (cheap, non-negotiable)

- Every module has its own directory, `module.manifest.yaml`, entitlement key,
  migrations and tests.
- The manifest declares: id, version, capabilities provided, capabilities
  required, events published/consumed, tools registered, entitlement key, data
  touched, required scopes.
- **No module imports another module's internals.** Cross-module communication
  is the event bus or a published interface. A **dependency-graph test fails the
  build** on any violation.
- Entitlement gating at **two** points: the API boundary, and the tool registry
  — where a disabled module's tools are *invisible* to agents, not rejected
  (ADR-0008).

### Deployable at launch: five boundaries, not twelve

Kernel, `M01 conversation`, `M02 itsm-core`, `M03 knowledge`, `M04 agents`,
`M05 automation` are independently deployable. `M06`–`M12` are properly bounded
modules that ship inside the main deployment until a customer's purchase
actually splits one. Because the import discipline held from day one, splitting
one later is days of work, not a refactor.

`make demo MODULES=…` is a Phase 7 gate over the five real boundaries, so it
tests something true.

### Promotion criterion

A module becomes independently deployable when a customer buys it separately, or
when a deployment shape requires it — not on principle and not on a schedule.

## Consequences

**Positive.** The expensive part of modularity (import discipline, manifests,
entitlement enforcement) is present from the first commit, so the option is
preserved at close to zero marginal cost. The cheap-looking part that is
actually expensive (twelve deployment topologies, twelve migration sets in
production, twelve upgrade paths) is deferred until it is paid for by a sale.

**Negative.** A customer demanding a `M07`-only deployment on short notice gets
days of work, not zero. Acceptable, and predictable enough to quote.

**Negative.** This is a deliberate deviation from §4 as written; if module-based
licensing (Q5) firms up with specific named subsets, the promotion list changes
accordingly and this ADR is revised.

## Alternatives considered

- **Twelve independently deployable modules from Phase 0, as specified.**
  Maximum commercial flexibility; months of infrastructure work against
  speculative demand, and twelve upgrade paths to keep green forever. Rejected.
- **A monolith, modularized later.** Cheapest now; the import discipline is
  exactly what cannot be retrofitted, since by then everything imports
  everything. Rejected.
