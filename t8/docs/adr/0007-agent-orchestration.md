# ADR-0007: Agent orchestration — custom supervisor over typed contracts

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

PROMPT.md §5 specifies a supervisor/orchestrator topology with specialist
agents, a shared case blackboard, typed inter-agent handoffs, step and cost
budgets, loop detection, a Critic with veto power, and complete reconstructability
of every run from AI Decision Records.

The question is whether to build this on an existing agent framework or to own
the loop.

The deciding constraint is that **our audit guarantees are stricter than any
framework's abstractions**. Every step must emit an AI Decision Record in a
known schema, tied to a tenant, a ticket and a policy decision, inside our
transaction boundaries. Frameworks that own the control flow tend to own the
state, the retries and the error handling too — which is exactly the surface we
must instrument.

## Decision

**Build the orchestrator, on typed contracts, in Python.**

- **Supervisor owns control flow**, step budget, cost budget, deadlines and
  escalation. Specialists own narrow competence and cannot delegate to each
  other; all delegation goes through the supervisor.
- **The blackboard is the only inter-agent memory.** Per `Interaction`,
  append-only, attributed and timestamped: facts, hypotheses with confidence,
  evidence with provenance, actions attempted with outcomes, open questions.
  **Free-text-only handoffs are a build failure**, not a style preference —
  every inter-agent message is a validated schema (Pydantic).
- **Memory tiers are explicit at the call site.** Session/working (blackboard),
  organizational (KB + resolved-case corpus, via `M03` only), entity
  (user/device/service in `M06`), procedural (runbooks, learned paths). Any
  retrieval names its tier; "the agent remembered" is not an acceptable
  provenance.
- **Every step emits an AI Decision Record** (ADR-0003) before its effects are
  visible to the next step.
- **Guardrails are supervisor-level:** step and cost budget, loop and
  oscillation detection, scope-drift detection, a global kill switch per tenant
  per action class, and graceful degradation to a human at any failure (P10).
- **The Critic has veto power** before any T2+ action or article publication,
  checking grounding, policy fit and blast radius. A veto is a recorded outcome
  with a reason, not a silent retry.

Agent *reasoning* is model work. Agent *authority* is not: see ADR-0013 for the
rule that the model emits a typed action proposal and a deterministic pipeline
decides.

## Consequences

**Positive.** The blackboard, budgets, veto and audit hooks are ours, so the
§8 success criterion — reconstruct any ticket's reasoning six months later — is
achievable rather than hoped for. No dependency whose release cadence can break
our compliance surface.

**Negative.** We write and maintain the loop, including retries, partial
failure, and concurrency between specialists. This is real work and it is the
main engineering content of Phase 4.

**Negative.** We forgo framework ecosystem conveniences (prebuilt patterns,
tracing integrations, community debugging tools). Partly offset by OpenTelemetry
throughout (P9), which gives us the tracing story independently.

**Revisit when:** a framework offers pluggable persistence and step
instrumentation strong enough to carry our AI Decision Record contract without
wrapping. Not before.

## Alternatives considered

- **A graph-based agent framework.** Good ergonomics for control flow; we would
  still write the blackboard, the budgets, the policy gate and the audit
  records, and we would inherit an upgrade treadmill on the one component whose
  behaviour we must be able to explain to an auditor. Rejected.
- **A managed/hosted agent runtime.** Removes loop and sandbox work; violates
  P3 (no air-gap, no customer VPC) and puts the audit trail in someone else's
  system. Rejected on portability, which is differentiator #3.
- **A free-for-all agent swarm.** Explicitly rejected by §5 and correctly so:
  no budget owner, no single escalation point, no reconstructable control flow.
