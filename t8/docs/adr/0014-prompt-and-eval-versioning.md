# ADR-0014: Prompt and model versioning, and the evaluation gate

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

§12 requires prompts to be versioned artifacts with changelogs, pinned per
deployment, rolled out behind flags, with no production prompt change without an
eval run — and AI regressions treated exactly like code regressions.

This only works if the eval harness produces numbers that mean something. §12
also asks for ≥200 real-shaped tickets per language built in Phase 2, which is
a problem: real-shaped tickets require real tickets, and a golden set we invent
encodes our assumptions and then congratulates us for meeting them. That is
worse than no harness, because it produces confident numbers.

## Decision

### Prompts as artifacts

Prompt templates live in the repository with an id, a semantic version and a
changelog. A deployment pins **template version and model id together**; the
pair is recorded in every AI Decision Record (ADR-0003). Changes roll out behind
flags, per tenant.

### The eval gate

Any change to a prompt, model, retrieval configuration or policy triggers an
eval run in CI. A regression beyond threshold fails the build. This applies to
every tenant provider binding (ADR-0006): a binding without a passing run is
marked **unvalidated** and blocked from autonomous tiers.

### Provenance tagging — the honesty mechanism

Every golden-set item is tagged `real`, `real-derived`, or `synthetic`, and
**all metrics are reported split by provenance**. Synthetic items exercise the
harness; they are never evidence for a claim about quality. If the design
partner's ticket export (§13 Q3) has not arrived, the Phase 2 review states
"the harness runs; the numbers are not yet meaningful" rather than showing a
board of green derived from data we wrote ourselves.

### Suites

- **Golden sets**, ≥200 items per language once real data exists, spanning
  intent classification, retrieval, resolution and refusal cases.
- **Adversarial suite** — authored by us immediately, no external data needed,
  and the first gate to go live: prompt injection in email and KB content,
  ambiguous requests, social engineering, out-of-scope requests, and requests
  that must escalate.
- **Scored:** intent accuracy, retrieval precision/recall@k, grounding and
  citation faithfulness, hallucination rate, **unauthorized action rate** and
  **inappropriate proposal rate** separately (ADR-0013), escalation
  appropriateness, cost and latency per resolution.

Bilingual from the start (P8): no gate passes on one language alone.

Eval runs use batch inference where the provider offers it, since they are not
latency-sensitive and the cost difference is material at CI frequency.

## Consequences

**Positive.** AI changes get the same treatment as code changes. The adversarial
suite gates merges from Phase 2, which is the earliest point at which the
riskiest behaviours can be caught.

**Negative.** CI gets slower and costs real money per run. Mitigated by batch
inference, by caching stable prefixes, and by running the full golden set on
merge rather than on every push.

**Negative.** Provenance splitting will make early numbers look thin. That is
the point.

## Alternatives considered

- **Synthetic golden sets presented as evidence.** Faster and produces better
  slides. Rejected: it converts an evaluation harness into a confidence machine.
- **Manual eval before release.** Does not scale, and is skipped under deadline
  pressure exactly when it matters.
- **Prompts in a database, editable at runtime.** Operationally flexible;
  destroys reproducibility of an AI Decision Record six months later, which is
  the §8 success criterion. Rejected — this is also why `M12` defers to
  config-as-code.
