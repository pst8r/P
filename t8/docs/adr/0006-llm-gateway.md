# ADR-0006: LLM gateway — per-tenant provider identity, task-tier routing, prompt pinning

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15
- **Settles:** PROMPT.md §13 Q4

## Context

P4 requires that swapping Claude ↔ Bedrock ↔ Azure/Foundry ↔ self-hosted be
config, not code. The product owner's answer to Q4 goes further:

> *"Anthropic first but can connect with customer paid through API, MCP and any
> other option to take advantage of the customer's investments."*

That converts the gateway from an abstraction over **our** providers into a
**tenant-scoped capability broker**. A tenant may arrive with their own
Anthropic key or committed spend, an existing Bedrock/Foundry/Vertex deployment
they already pay for, their own MCP servers (ADR-0008), or a residency
constraint pinning where inference may run.

Two facts make this more than a configuration field:

1. **Provider bindings are different client classes, not base-URL swaps.**
   Bedrock, Foundry and Vertex each have their own SDK client type, their own
   credential mechanism (AWS region/role, Entra, GCP ADC) and their own model-id
   conventions. An adapter that assumes a shared HTTP shape will not hold.
2. **Provider capability is not uniform.** Features we depend on — response
   citations, structured outputs, prompt caching, effort control, extended
   context, the MCP connector, refusal-fallback behaviour — are not available
   identically across providers and platforms. A tenant on a restricted provider
   must degrade in a defined way, not fail unpredictably.

## Decision

**One internal gateway service. Every LLM call in the product goes through it.
No module or agent constructs a provider client directly.**

### Per-tenant provider identity

Each tenant has a **provider binding**: provider kind, credential reference
(vault, never in config or the database in plaintext), endpoint/region/resource,
allowed model set, residency constraint, and cost bearer (`T8` or `CUSTOMER`).
Bindings are per tenant and per task tier, so a tenant can route cheap
classification to their own deployment and keep grounded answering on ours, or
the reverse.

### Capability negotiation, not assumption

The gateway holds a **capability matrix** per (provider, model): citations,
structured outputs, caching, effort, context window, MCP connector, fallbacks.
Model capabilities are discovered from the provider's models API where available
rather than hardcoded. A request declares the capabilities it *requires*; the
gateway routes to a binding that satisfies them, or **fails closed** to a
defined degradation with an audit event — it never silently drops grounding or
schema validation.

### Task-tier routing

Tiers are declared by the caller (`classify`, `retrieve-synthesize`,
`converse`, `plan`, `critic`, `author`), not chosen by the model. Each tier maps
to a model and effort setting per tenant binding. Defaults on Anthropic at time
of writing — re-verified against official documentation before pinning:
Opus-class for planning, critique and grounded answering; Sonnet-class for
conversation; Haiku-class for classification and bulk extraction. Non-latency-
sensitive work (knowledge ingestion, auto-authoring drafts, eval runs) uses the
batch API where the provider offers it.

### Prompt and model pinning

Prompt templates are **versioned artifacts in the repository** with changelogs.
A deployment pins template version *and* model id. The pair is recorded in every
AI Decision Record (ADR-0003). Rollout is flag-gated and gated on an eval run
(ADR-0014). No prompt reaches production without one.

### Cost accounting split by bearer

Every call records tokens, cache hits, latency and computed cost, attributed to
tenant, ticket, agent run and **bearer** — T8-borne or customer-borne. This is
the metering split PLAN.md §6 requires and it is impossible to reconstruct after
the fact.

### Caching discipline

Provider prompt caching is prefix-based: any byte change invalidates everything
after it, and the render order is tools → system → messages. The gateway
therefore owns prompt assembly — stable content first (frozen system prompt,
deterministically ordered tool list), volatile content (timestamps, per-request
ids, the user's actual question) last. Cache-read token counts are monitored;
a hit rate that collapses is an alert, because it is usually a silent
invalidator rather than a pricing surprise.

### Safety plumbing

PII detection and redaction before egress to any model (ADR-0018). Provider
refusal signals are treated as a defined outcome, not an exception — the gateway
surfaces them to the caller, which escalates to a human under P10. Where a
provider offers server-side fallback routing it is used; otherwise the gateway
implements fallback itself across bindings that satisfy the same capability set.

## Consequences

**Positive.** Q4 is satisfied as asked: a customer's existing model investment
becomes usable capacity rather than a line we bill over the top of. Residency
becomes a deployment parameter (§8) rather than a code change. Cost attribution
is honest, which makes any of Q5's pricing models implementable later.

**Negative.** Substantially more surface than a single-provider config: a
credential vault, a capability matrix, per-tenant routing tables, and a support
burden when a tenant's own endpoint misbehaves. Expect the gateway to be one of
the larger kernel packages.

**Negative.** Eval baselines are model-specific. A tenant running a different
model is, strictly, running an unvalidated configuration. Mitigation: the eval
harness (ADR-0014) runs per binding, and a binding without a passing eval run is
marked unvalidated in the admin surface and blocked from autonomous tiers.

**Negative.** Capability degradation paths multiply the test matrix. Accepted:
the alternative is discovering in production that a tenant's provider silently
returned ungrounded answers.

## Alternatives considered

- **Single provider, config-swappable later.** Simplest; contradicts both P4
  and the explicit Q4 answer. Rejected.
- **Direct SDK use with a thin wrapper.** Cheaper initially; loses central cost
  accounting, prompt pinning, redaction and capability negotiation — all of
  which are audit requirements, not conveniences. Rejected.
- **An off-the-shelf LLM proxy/router.** Attractive, and reconsidered at Phase 5
  scale. Rejected for now: none of them carry prompt-version pinning tied to an
  audit ledger or per-tenant cost-bearer accounting, which is most of why this
  component exists.
