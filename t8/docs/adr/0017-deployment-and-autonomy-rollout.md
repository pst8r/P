# ADR-0017: Deployment — SaaS at launch, other shapes later; and how autonomy is promoted

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15
- **Settles:** PROMPT.md §13 Q2

## Context

The product owner chose **SaaS delivery**. Differentiator #3 nonetheless
promises identical capability in public cloud, customer VPC, on-prem and
air-gapped, and P3 forbids a hard dependency on any proprietary managed service.

Separately, §13 assumption 9 sets launch autonomy at T0/T1 autonomous, T2
approval-gated, T3 human-executed. Autonomy granted per release is a trust
incident waiting for its first bad week; autonomy earned per tenant is a graph
in a quarterly review. Since both questions are about *rollout*, they are
decided together.

## Decision

### Deployment

**SaaS is the launch topology** (pooled multi-tenant, ADR-0010) and we operate
it: SLOs, upgrade cadence, noisy-neighbour control, per-tenant cost attribution.

**Every other shape is the same build.** Customer VPC and air-gapped installs
run the identical artifacts with a different adapter configuration and one
tenant. We do not maintain a separate single-tenant codebase.

**Port discipline is enforced from Phase 0 even though nothing needs it yet.**
Every infrastructure dependency has a port and at least two adapters — one
cloud, one self-hosted (ADR-0002, 0004, 0005). The discipline is nearly free;
retrofitting it after a managed-service shortcut is not. This is what keeps
differentiator #3 true rather than aspirational while we ship SaaS.

**Packaging:** OCI containers, Helm charts, Terraform modules, `docker compose`
for local and small private deployments, and a documented, tested air-gapped
install path with a bundled model option. Delivered in Phase 8; the constraints
that make it possible are honoured from Phase 0.

**Data residency is a deployment parameter, not a code change** — including
where inference runs, which the LLM gateway pins per tenant binding (ADR-0006).

### Autonomy rollout

**Every action class ships disabled.** Enabling is per tenant, per action class,
and proceeds through:

1. **Shadow** — the action is proposed and fully evaluated through the pipeline
   (ADR-0013), dry-run executed where the adapter supports it, and the outcome
   recorded. Nothing changes in the customer's tenant.
2. **Evidence** — 30 days or 200 executions, whichever comes first, with
   inappropriate-proposal rate and dry-run divergence measured against the eval
   harness (ADR-0014).
3. **Explicit tenant opt-in** — a recorded decision by a named person at the
   customer, not a default.
4. **Autonomous**, with the per-tenant, per-action-class kill switch live.

A binding with no passing eval run (ADR-0006) cannot be promoted at all.

## Consequences

**Positive.** SaaS economics now, without foreclosing the deployments that win
regulated deals later. The autonomy ladder turns "how do we know your agent
won't do something stupid" into a shadow-mode report from the customer's own
tenant — a far better answer than a benchmark.

**Negative.** Port discipline costs real design effort and a second adapter's
worth of contract tests for infrastructure nobody is asking for yet. Accepted
deliberately: this is the cost of differentiator #3.

**Negative.** Shadow mode delays visible autonomous value by weeks per action
class per tenant, and some customers will want it skipped. The skip path is an
explicit, recorded exception, not a configuration default.

**Negative.** Operating SaaS is a permanent organizational commitment — on-call,
upgrades, incident response — that a licensed on-prem product does not carry.

## Alternatives considered

- **Cloud-native SaaS using managed services freely.** Faster and cheaper to
  operate; abandons differentiator #3 and forecloses regulated and air-gapped
  deals. Rejected.
- **Air-gapped from day one.** ~2 extra engineer-months (bundled model, offline
  registry, licensing and telemetry) against no signed demand. Deferred to
  Phase 8, with the constraints honoured throughout.
- **Autonomy on by default at T0/T1.** What the category does. One bad
  automated action at a design partner costs more than the weeks saved.
