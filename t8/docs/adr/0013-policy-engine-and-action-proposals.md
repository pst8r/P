# ADR-0013: Policy engine — typed decision point, and the action-proposal rule

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15
- **Reframes:** PROMPT.md §12's "false-action rate (target: zero)"

## Context

P6 makes autonomy a property of the *action*, not the agent. §7 defines risk
tiers T0–T3. §12 names false-action rate as "the trust-killing metric" with a
target of zero.

Zero is the right goal stated as an unachievable metric. You cannot drive a
*stochastic model* metric to zero, and a zero target on a model either gets
quietly redefined or gets gamed. But zero is entirely achievable as a property
of a **gate** — and which of those two things it is determines the architecture.

## Decision

### The action-proposal rule

**The model never emits an action. It emits an action *proposal*:** a typed
object naming a catalog action and its arguments. Between the proposal and any
effect sits a deterministic pipeline, every stage of which is code:

1. **Schema validation** — arguments match the catalog entry's schema. Tool
   schemas are declared strict at the provider where supported so arguments
   arrive well-formed, but they are **re-validated server-side regardless**;
   provider-side validation is a convenience, never the authorization boundary.
2. **Precondition checks** — the world is in the state the action requires.
3. **Entitlement check** — the tenant has the module and the action enabled.
4. **Policy decision** — the policy engine authorizes, with a rule id.
5. **Risk-tier autonomy check** — is this tier autonomous *for this tenant right
   now* (ADR-0017's shadow-mode promotion)?
6. **Approval state** — for T2, a valid, unexpired approval from the resolved
   owner.

Any stage failing refuses the proposal and records it. **There is no path from
model output to effect that bypasses this pipeline** — structurally guaranteed
by the governed-write rule (ADR-0009): the agent runtime has no write grant, so
the only way to change anything is an API call that enters this pipeline.

### The metric, restated

- **Unauthorized action rate — zero by construction.** A property of the gate,
  tested like code, with the adversarial suite attempting to get past it.
- **Inappropriate proposal rate** — a model quality metric measured against the
  adversarial suite, driven down over time, never expected to reach zero.

Reporting these separately is a requirement, not a presentation choice: merging
them hides which one regressed.

### The engine

A **typed, in-house decision point** in TypeScript, colocated with the
repository layer so the decision and its audit event commit in the same
transaction as the mutation (ADR-0003). Policies are versioned artifacts; every
decision records the rule id and the policy version. Decisions are explainable —
"which policy allowed it" (§8) is a lookup, not an inference.

**Fail closed.** Policy engine unavailable, entitlement state unknown, approval
state ambiguous, or confidence below threshold ⇒ escalate to a human (P10).
The unavailable case has an explicit test; a policy engine that fails open once
is worse than no policy engine, because it will be trusted.

## Consequences

**Positive.** The trust-killing metric becomes a property we can actually
guarantee and demonstrate to a security reviewer, rather than a number we hope
stays low. Social-engineering attacks ("I'm the CEO, skip approval") fail at a
stage that cannot be persuaded, because it does not read prose.

**Negative.** Less agent flexibility. An agent cannot compose a novel action out
of primitives; it can only propose catalog entries. This is the intended
constraint and it caps what autonomy can ever do — a limit worth naming in the
roadmap rather than discovering.

**Negative.** We build and maintain the policy engine. Justified by the
in-transaction audit requirement, which an external decision point cannot
satisfy without distributed-transaction problems.

**Negative.** Six stages on every mutating call is latency. Measured; all six
are local and cheap relative to the model call that preceded them.

## Alternatives considered

- **OPA or Cedar as the decision point.** Mature, expressive, externally
  auditable policy languages. Rejected for now on the in-transaction
  requirement and on air-gapped packaging; the interface is kept narrow enough
  that either could back it later, and the versioned-policy-artifact design is
  deliberately compatible.
- **Let the model call tools directly with guardrail prompting.** The industry
  default. It makes the trust-killing metric a model property. Rejected.
- **Human approval for everything.** Zero false actions, zero product.
