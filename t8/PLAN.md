# T8 IT Service Desk — PLAN.md

**Status:** awaiting your approval. No scaffolding begins until you approve this
document (PROMPT.md §0.5).

**Inputs settled:** your answers to the four `[BLOCKING]` questions (§1).
**Still open:** Q3 (design-partner logistics) and three assumptions flagged in
§2. Neither blocks this plan; both are called out where they bite.

---

## 1. Decisions you made, and what each one changes

| Question | Your answer | What it changes |
|---|---|---|
| **Q1 — Replace or front?** | **Both, equal priority from day one** | `Incident`/`ServiceRequest` are built as a discriminated aggregate with `system_of_record ∈ {T8, EXTERNAL}` from the first commit. Phase 1 grows by ~1 engineer-month and carries a second set of tests. See ADR-0001. |
| **Q2 — Deployment target** | **SaaS** | Pooled multi-tenancy with Postgres RLS is the *launch* architecture, not an option. We operate it: SLOs, upgrade cadence, noisy-neighbour control, per-tenant cost attribution. Single-tenant/VPC and air-gap become later deployment *shapes* of the same build. See ADR-0010, ADR-0017. |
| **Q4 — LLM** | **Anthropic first, plus customer-paid API, customer MCP servers, and "any other option to take advantage of the customer's investments"** | This is the largest change to the original document. The gateway is not one provider config — it is **per-tenant provider identity**: bring-your-own-key, bring-your-own-endpoint, bring-your-own-MCP-tools. It also splits metering into T8-borne and customer-borne cost. See ADR-0006, ADR-0008. |
| **Q5 — Commercial model** | **Undecided — meter everything** | Full metering layer in Phases 0–1 (~3 engineer-weeks), pricing deferred. Metering is written so no pricing model is foreclosed. See §6. |

### Why Q4 is the consequential answer

"Take advantage of the customer's investments" turns the LLM gateway from an
abstraction over *our* providers into a **tenant-scoped capability broker**. A
tenant may arrive with any of:

- their own Anthropic key or a committed spend agreement (BYO-key);
- an existing Bedrock, Foundry or Vertex deployment they already pay for
  (BYO-endpoint — and these are *different SDK client classes*, not a base-URL
  swap, so the adapter boundary has to be real);
- their own MCP servers already wrapping their internal systems (BYO-tools);
- a residency requirement that pins where inference runs.

Each is a per-tenant configuration with its own credentials, its own cost
ledger, its own failure modes and its own trust level. That is a first-class
subsystem, not a config file — and it is a genuine differentiator, because the
competitors named in PROMPT.md §1 all bill you for tokens you are already
paying someone else for.

**It also creates a security problem the original document does not have.**
A customer-supplied MCP server is a tool source we did not write, reached over
the network, returning content we must not trust. It cannot inherit autonomy.
ADR-0008 makes externally-registered tools **T3 by default** — no autonomous
execution, ever, until a human explicitly tiers them down per tenant.

---

## 2. Assumptions I am proceeding on (contradict any of these and I adjust)

1. **Email intake ships in Phase 3 alongside Teams**, not later. It is the
   largest real intake surface in most enterprises and the main arrival path
   for prompt injection. Slack and the web widget follow.
2. **Every action class ships disabled, runs in shadow/dry-run, and is promoted
   per tenant on evidence** (30 days or 200 executions, whichever first) plus
   an explicit tenant opt-in. Autonomy is earned per tenant, not granted per
   release.
3. **`M12 admin-studio` is deferred.** v1 ships config-as-code in Git, a
   read-only admin viewer, and the approval-gated change path. The studio
   becomes a UI over that substrate later, not a parallel system.
4. **Team shape:** 6 engineers (2 TS backend, 2 Python/AI, 1 frontend,
   1 platform) + ~0.5 FTE ITSM SME who has actually run a service desk. The
   SME is not optional.
5. **Q3 is unanswered.** Without the design partner's ticket export and a
   non-production M365 tenant, the Phase 2 eval numbers are not evidence and
   Phase 5 cannot be tested against anything real. I will build both phases
   regardless and report their status honestly rather than quietly substituting
   synthetic data for proof.

---

## 3. Architectural decisions and their trade-offs

Each line is an ADR (§7). This table is the summary; the ADR carries the argument.

| Decision | Choice | Trade-off accepted |
|---|---|---|
| Ticket system of record | Discriminated aggregate, both modes first-class | +1 engineer-month, two test matrices, conflict semantics to design. Buys: no bet on Q1. |
| Datastore | PostgreSQL SoR + pgvector + RLS; S3-compatible object port | pgvector is worse than a dedicated vector DB at very large scale. Buys: one dependency that runs in SaaS, VPC and air-gap unchanged. Revisit only on benchmark evidence. |
| **Audit ledger** | **In-transaction append + async Merkle sealing with signed checkpoints** | Tamper-evidence is eventual (seconds), not synchronous. Buys: no write serialization on the hot path, and per-ticket inclusion proofs an auditor can verify without seeing the rest of the ledger. **This supersedes PROMPT.md §8's per-entry hash chain — see ADR-0003.** |
| Event bus | Port + adapters; NATS JetStream default | An extra component to operate in SaaS. Buys: identical semantics self-hosted. |
| Durable workflow | `WorkflowPort`, Postgres adapter first, Temporal adopted in Phase 5 | Risk of the port leaking Postgres assumptions — mitigated by writing the Temporal adapter's contract test in Phase 0, before it has an implementation. Buys: five phases without a heavy dependency. |
| **LLM gateway** | **Per-tenant provider identity: BYO-key, BYO-endpoint, BYO-residency; task-tier routing; prompt-version pinning** | Substantially more surface than a single-provider config. Buys: Q4's requirement, and P4 for real. |
| Agent orchestration | Custom supervisor over typed contracts | We write the loop. Buys: the blackboard, budgets, veto and audit hooks are ours, and agent frameworks move faster than our audit guarantees can. |
| **Tool registry** | **One registry; in-process for internal tools, MCP as published projection; external MCP tools T3 by default** | Two transports to keep in sync — mitigated by one definition generating both. Buys: no tenant-context loss on the hot path, and Q4's BYO-tools without handing autonomy to code we did not write. |
| Language split | Python (AI) + TypeScript (business/API); **Python never writes governed tables** | Cross-language contract maintenance. Buys: one place where "audit event in the same transaction" is implemented, therefore one place to audit it. |
| Tenancy | Pooled + RLS, tenant context propagated through every call including agent tool calls | A single RLS mistake is a cross-tenant leak. Mitigated by a standing negative test suite. Buys: SaaS economics. |
| Policy engine | Typed in-house decision point, externalizable later | We build it. Buys: decisions are versioned, explainable and inline with the audit write. |
| Retrieval | Hybrid BM25 + dense + metadata, reranked; **entitlement filter before ranking** | Pre-filtering constrains index design and costs recall tuning. Buys: no possibility of ranking a document the user may not see. |
| Action authorization | **The model emits a typed action *proposal*; a deterministic pipeline decides** | Fewer "clever" agent behaviours. Buys: unauthorized-action rate is zero *by construction*, testable like code. Uses strict tool schemas so proposal arguments are schema-valid by contract. |
| Grounding | Anthropic citations on document blocks, article/section IDs carried through | Ties the answer path to a provider capability; the gateway abstracts a fallback. Buys: citations with real character/page spans rather than model-asserted references. |
| Untrusted content | Marked as data at ingestion, stays marked through blackboard and prompts; operator instructions via mid-conversation system messages, never concatenated into user content | Extra plumbing on every ingestion path. Buys: a defensible answer to "could a ticket description tell your agent to grant access?" |

---

## 4. Module boundaries I will enforce

**Kernel packages** — importable by any module, never importing a module:
`core-domain`, `core-contracts`, `audit-ledger`, `policy-engine`,
`llm-gateway`, `knowledge-service`, `tool-registry`, `ui-kit`.

**Modules** — `M01`…`M12`, each with `src`, `tests`, `migrations`,
`module.manifest.yaml`, `README.md`.

**The rules, enforced by CI from Phase 0:**

1. No module imports another module's internals. Cross-module communication is
   the event bus or a published interface. A dependency-graph test **fails the
   build** on violation.
2. Every module declares capabilities provided/required, events
   published/consumed, tools registered, entitlement key, data touched,
   required scopes.
3. The entitlement engine gates at the API boundary **and** in the tool
   registry. A disabled module's tools are *invisible* to agents, not rejected.
4. Python may read governed tables under an RLS-scoped connection. Python never
   writes them.

**Independently deployable at launch (five boundaries):** kernel, `M01`,
`M02`, `M03`, `M04`, `M05`. `M06`–`M12` are properly bounded modules inside the
main deployment until a customer's purchase actually splits one — which, because
the import discipline held, is days of work rather than a refactor. This is the
amendment argued in `docs/00-architect-response.md` §2.3; twelve deployment
stories on speculation is the expensive way to discover which two mattered.

---

## 5. Phases

Each ends running, tested and demonstrable. I do not start one without your
sign-off on the previous.

### Phase 0 — Foundations *(~4 weeks)*
Monorepo; CI with the dependency-graph test; `core-domain` aggregates and state
machines; **audit ledger (in-transaction append + Merkle sealer)**; policy
engine; tenancy + RLS; `WorkflowPort` (Postgres adapter, Temporal contract test
written); LLM gateway skeleton with per-tenant provider identity; OTel; metering
counters; `make dev`.

*Done when:* illegal transitions rejected by tests; ledger verification and
inclusion proofs pass; a test that **attempts** an ungoverned mutation fails to
achieve one; a cross-tenant read test fails to read.

### Phase 1 — ITSM core *(~5 weeks, +1wk for dual SoR)*
`M02` incident/request lifecycle, queues, assignment, analyst workspace,
**both SoR modes** with reconciliation and conflict handling.

*Done when:* an analyst runs a ticket end-to-end in the UI in both modes; every
touch reconstructable from the ledger. SLA *types* modeled; clock deferred to
Phase 8.

### Phase 2 — Knowledge + eval harness *(~5 weeks)*
`M03` KCS lifecycle; hybrid retrieval with entitlement-pre-filtering; ingestion
connectors; bilingual language-linked articles; **eval harness in CI**;
adversarial suite authored.

*Done when:* grounded, cited answers on the seeded corpus; retrieval benchmarked
with **metrics split by provenance** (`real` / `real-derived` / `synthetic`); a
test that tries to leak an out-of-entitlement article fails; the adversarial
suite gates merges.

### Phase 3 — Conversation + Triage *(~5 weeks)*
`M01` Teams bot **and email intake**; identity resolution; Triage agent;
deflection path; untrusted-content marking end to end.

*Done when:* an employee resolves a known issue in Teams with no ticket created,
fully audited; **an injected instruction in an email body provably fails to
influence any decision.**

### Phase 4 — Multi-agent orchestration *(~5 weeks)*
`M04` orchestrator, blackboard, Critic/QA, escalation package, guardrails, step
and cost budgets. `M06 cmdb` lands here — Diagnostic needs the CI graph and
Approval needs the ownership graph.

*Done when:* a multi-step case with delegation, a Critic veto and a clean human
handoff is **reconstructed from its AI Decision Records by someone who did not
watch it run.**

### Phase 5 — Automation *(~6 weeks)*
`M05` action catalog; tool registry + MCP projection + external MCP registration;
T0–T2 M365 actions; approvals; sagas (Temporal adopted); shadow mode.
`M07 problem-change` lands here — Standard changes gate autonomous execution.

*Done when:* real password reset / license assignment / group membership in the
**test tenant**, with dry-run, approval, rollback and audit proven; every T2
action has a tested rollback; a customer-registered MCP tool executes at T3 with
a human in the loop.

### Phase 6 — Knowledge loop *(~3 weeks)*
Novelty-gated auto-authoring (retrieval miss + successful resolution, or an edit
proposal when an article was used but deviated from), gap detection, decay,
promotion policy.

*Done when:* a resolved novel ticket produces a validated article that
**measurably** resolves the next occurrence.

### Phase 7 — Modularity proof *(~3 weeks)*
Manifests, entitlement gating at both points, reduced-SKU build over the five
deployable boundaries.

*Done when:* `make demo MODULES=…` runs a subset with no dead code paths, no
broken UI, and a disabled module's tools invisible to agents.

### Phase 8 — SLM + deployment shapes *(~5 weeks)*
`M08` SLA/OLA clocks, business calendars (LATAM + US), pause/stop semantics,
breach prediction, escalation; Helm, Terraform, compose; VPC shape; air-gap path.

*Done when:* the same suite is green in SaaS and in a disconnected environment;
clock-stop semantics correct across time zones and DST boundaries.

### Phase 9 — Compliance & analytics *(~4 weeks)*
`M09` evidence packs, retention, legal hold, crypto-shredding erasure; `M10`
deflection/containment/cost dashboards.

*Done when:* an auditor-ready pack for an arbitrary range; **erasure preserves
ledger verifiability**; cost per ticket reported per tenant, split T8-borne vs
customer-borne.

### Phase 10 — ITSM integrations *(~4 weeks)*
`M11` ServiceNow / Jira SM bidirectional sync.

*Done when:* T8 fronts an incumbent with no state divergence under **induced**
conflict.

**Horizon** (sum of the per-phase estimates above, run as sequential gates):
Phases 0–5 ≈ **31 weeks / ~7 months** to a design partner running real T0–T2
automation. Phases 6–10 ≈ **19 weeks / ~4.5 months**. Total ≈ **50 weeks**.

The ~6-month figure in `docs/00-architect-response.md` §1.8 assumed some overlap
between phases; these numbers assume none, because §11 gates each phase on your
approval of the previous one. Seven months is the number to plan against unless
you want phases to overlap, which trades the gate for the schedule.

---

## 6. Metering (Q5 — pricing undecided, so count everything)

Built in Phases 0–1 because uncounted history cannot be reconstructed later.
Per tenant, per period:

- **Seats seen** — distinct employees with at least one `Interaction`.
- **Resolutions by disposition** — deflected (no ticket), autonomous, approval-gated,
  human-resolved — and by **risk tier** of the actions involved.
- **Module usage** against entitlement keys (the SKU boundary, whatever pricing lands on).
- **Cost, split by bearer** — T8-borne tokens vs customer-borne (BYO-key/BYO-endpoint),
  attributable per ticket and per agent run, alongside infrastructure cost.
- **Knowledge reuse** — article → resolution attribution, for the KCS loop and for
  any value-based pricing conversation.

Metering is emitted as events and aggregated separately from the operational
path, so a metering failure degrades billing data, never service. No pricing
model in Q5's option set is foreclosed by this design.

---

## 7. ADRs

Written on approval of this plan, ordered by cost of reversal.

| ADR | Decision | Settled by |
|---|---|---|
| 0001 | System of record: discriminated aggregate, both modes | Q1 |
| 0002 | Datastore: PostgreSQL + pgvector + RLS; S3-compatible object port | default |
| 0003 | **Audit ledger: in-transaction append + async Merkle sealing** (supersedes §8 chaining) | disagreement |
| 0004 | Event bus: port + adapters, NATS JetStream default | default |
| 0005 | Durable execution: `WorkflowPort`, Postgres first, Temporal at Phase 5 | disagreement |
| 0006 | **LLM gateway: per-tenant provider identity, BYO-key/endpoint/residency, task-tier routing, prompt pinning** | Q4 |
| 0007 | Agent orchestration: custom supervisor over typed contracts | default |
| 0008 | **Tool registry: one registry, two surfaces; external MCP tools T3 by default** | Q4 + disagreement |
| 0009 | Language split and the governed-write rule | default |
| 0010 | Tenancy: pooled + RLS, context propagation through agent tool calls | Q2 |
| 0011 | Auth: Entra OIDC, on-behalf-of, service principals, per-action least-privilege scopes | default |
| 0012 | Retrieval: hybrid architecture, swappable embeddings, entitlement-before-ranking | default |
| 0013 | Policy engine: typed in-house decision point | default |
| 0014 | Prompt and model versioning: artifacts, pinning, flagged rollout, eval gating | default |
| 0015 | Modularity mechanics: manifest schema, enforcement points, CI graph test | disagreement |
| 0016 | Bilingual knowledge and cross-lingual retrieval | default |
| 0017 | Deployment: SaaS launch topology, VPC and air-gap as later shapes | Q2 |
| 0018 | PII redaction, pseudonymization, crypto-shredding erasure with ledger integrity | default |
| 0019 | **Untrusted content: structural data/instruction separation** (not in PROMPT.md) | gap |

---

## 8. What I need from you

1. **Approve this plan**, or tell me what to change.
2. **Q3 logistics** — the ticket export and the non-production M365 tenant.
   These gate evidence, not progress.
3. **Yes/no on the three assumptions in §2** — email intake in Phase 3,
   shadow-mode promotion, deferring the Admin Studio.

On approval I scaffold Phase 0 and nothing beyond it.
