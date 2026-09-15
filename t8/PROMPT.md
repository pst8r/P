# T8 IT Service Desk — Claude Code Build Prompt

> Paste this whole document into Claude Code as the opening prompt, or save it as `PROMPT.md` at the repo root and start with: *"Read PROMPT.md and follow Section 0."*

---

## 0. How you are to work (read this first)

You are the founding engineer of a new product. Act as a principal-level architect who has shipped ITSM platforms, not as a code generator.

**Before writing any code:**

1. Read this entire document.
2. Answer the **Open Questions (Section 13)** back to me. Do not guess on anything marked `[BLOCKING]` — stop and ask. For everything else, state the assumption you're making and proceed.
3. Produce `PLAN.md`: the phase breakdown, the module boundaries you'll enforce, and every architectural decision you're about to make with its trade-off.
4. Produce `docs/adr/0001-*.md` through `000N` for each irreversible decision (datastore, event bus, agent framework, auth model, LLM abstraction).
5. Wait for my approval on `PLAN.md` before scaffolding.

**While building:**

- **Phase gates, not big bang.** Each phase in Section 11 ends with something demonstrable and testable. Never leave the repo in a non-running state between phases.
- **Contracts before implementations.** Define the interface, write the contract test, then implement. Every external system gets an adapter interface plus a fake used in tests — no test may ever call a live tenant.
- **Your training data has a cutoff.** Verify current versions, APIs, and breaking changes against official documentation before pinning any dependency or calling any vendor API (Microsoft Graph, Entra ID, Intune, Anthropic/Bedrock/Azure OpenAI, MCP spec). Do not trust a version number from memory.
- **Determinism where it matters.** Business rules, state machines, SLA math, approval routing, and entitlement checks are *code*, not prompts. LLMs classify, retrieve, summarize, converse, and draft. They do not decide whether a change is authorized.
- Conventional commits, small focused commits, tests alongside code. `make dev` must bring the whole stack up locally with seeded demo data.
- When you hit ambiguity mid-build, stop and ask rather than inventing enterprise behavior.

---

## 1. Product definition

**T8 IT Service Desk** — an agentic, ITIL-native IT service desk platform that resolves end-user issues autonomously, builds and curates its own knowledge base, and produces a defensible audit trail for every action taken by a human or an AI agent.

**Primary use case at launch:** Tier-0/Tier-1 support for off-the-shelf enterprise software — Microsoft 365 (Outlook, Teams, Excel, Word, OneDrive, SharePoint), Windows/Intune device issues, Entra ID identity and access, plus a generic connector pattern that extends to any SaaS.

**Buyer:** enterprise IT / Digital Workplace leadership. **User:** the employee, inside Teams or Slack. **Operator:** the service desk analyst and the knowledge manager.

**Competitive frame** (study the category shape, do not clone any product): Moveworks, ServiceNow Virtual Agent + Now Assist, Aisera, Espressive Barista, Atomicwork, Leena AI.

**Where T8 wins — these three differentiators must be visible in the architecture, not just the pitch:**

1. **ITIL 4 + KCS v6 native.** Not a chatbot bolted onto a ticket table. The domain model *is* the ITIL practice model, and knowledge is produced by the resolution workflow rather than maintained separately.
2. **Audit-by-construction.** Every AI decision is reconstructable: which model, which prompt version, which retrieved evidence, what confidence, which policy allowed it, who could have stopped it. Competitors bolt this on; T8 cannot function without it.
3. **Deploy anywhere, model-agnostic.** Identical capability in public cloud, customer VPC, on-prem, and air-gapped. No hard dependency on any single LLM vendor or hyperscaler managed service.

---

## 2. Non-negotiable engineering principles

| # | Principle | What it forbids |
|---|---|---|
| P1 | **Modular by construction** | No module may import another module's internals. Cross-module communication is via the event bus or a published interface only. |
| P2 | **Entitlement-gated capability** | Every module declares a capability manifest and an entitlement key. Disabling a module must degrade the product gracefully, never break it. |
| P3 | **Portable runtime** | No hard dependency on a proprietary managed service. Every infra need has a port + at least two adapters (one cloud, one self-hosted). |
| P4 | **Model-agnostic** | All LLM calls go through one abstraction. Swapping Claude ↔ Bedrock ↔ Azure OpenAI ↔ self-hosted must be config, not code. |
| P5 | **Audit-by-construction** | It must be impossible to mutate a governed record without emitting an audit event in the same transaction. |
| P6 | **Human-in-the-loop by risk tier** | Autonomy level is a property of the *action*, not the agent. See Section 7. |
| P7 | **Multi-tenant and data-isolated** | Row-level isolation enforced at the datastore. Tenant context flows through every call including agent tool calls. |
| P8 | **Bilingual from day one** | Spanish (es-MX) and English (en-US) are equal citizens in UI, knowledge, intent handling, and evaluation sets. Not a translation layer added later. |
| P9 | **Observable** | Every agent run is traceable end-to-end (OpenTelemetry). Token cost, latency, and outcome attributable per ticket and per tenant. |
| P10 | **Fail closed** | On policy engine unavailability, retrieval failure, or low confidence, the system escalates to a human. It never improvises an action. |

---

## 3. Domain model — ITIL 4 native

Model these as first-class aggregates with explicit state machines, not as rows with a `status` string. Generate the state machines as code with illegal-transition tests.

**Records**
- `Interaction` — a conversation/session with an employee. Many interactions may resolve without ever creating a ticket (this is the deflection metric).
- `Incident` — unplanned interruption / quality reduction. States: `New → Assigned → In Progress → Pending(Customer|Vendor|Change) → Resolved → Closed`, plus `Cancelled`. Priority derived from Impact × Urgency matrix (configurable per tenant).
- `ServiceRequest` — from a `ServiceCatalogItem`, with a fulfillment workflow and approval chain.
- `Problem` — root cause. Links many Incidents. States: `Detected → Logged → Investigated → KnownError → ResolutionApplied → Closed`. A `KnownError` carries a workaround that is publishable to the KB.
- `Change` — with `Standard | Normal | Emergency` types. Standard changes are pre-authorized and are the *only* type an agent may execute autonomously.
- `KnowledgeArticle` — see Section 6.
- `ConfigurationItem` — lightweight CMDB: user, device, application, service, license, group. Relationships typed (`runs_on`, `depends_on`, `assigned_to`, `member_of`). Federated from Entra ID/Intune rather than re-mastered.
- `Service` + `SLA` / `OLA` — targets, business calendars, pause/clock-stop semantics, breach prediction.
- `Approval` — actor, scope, expiry, delegation, decision record.
- `AuditEvent` — Section 8.
- `AgentRun` / `AgentStep` — the execution trace of an agent, linked to whichever record it touched.

**Explicitly model:** priority matrix, business calendars and time zones (LATAM + US), major incident declaration and its comms fan-out, ticket linkage graph (`caused_by`, `duplicate_of`, `child_of`), and Continual Improvement register.

---

## 4. Modular architecture and commercial packaging

Build a monorepo whose **module boundaries are the SKU boundaries**. A customer buys a subset; the subset must build, deploy, and run on its own.

**Kernel (always present, never sold separately):** identity & tenancy, event bus, audit ledger, policy/entitlement engine, configuration, observability, LLM gateway, tool registry.

**Modules — each independently deployable, each with a `module.manifest.yaml` declaring: id, version, capabilities provided, capabilities required, events published/consumed, tools registered, entitlement key, data it touches, required scopes.**

| Module | Scope |
|---|---|
| `M01 conversation` | Teams / Slack / web widget / email intake; identity resolution; session state |
| `M02 itsm-core` | Incident + Request records, assignment, queues, state machines |
| `M03 knowledge` | KCS lifecycle, retrieval service, authoring, curation, decay |
| `M04 agents` | Orchestrator + specialist agents (Section 5) |
| `M05 automation` | Action catalog, adapters, remediation runbooks (Section 7) |
| `M06 cmdb` | CI graph, federation, relationship queries |
| `M07 problem-change` | Problem Management, Change Enablement, CAB workflow |
| `M08 slm` | SLAs, OLAs, breach prediction, escalation policies |
| `M09 audit-compliance` | Ledger query, evidence packs, retention, legal hold, AI decision records |
| `M10 analytics` | Deflection/containment dashboards, cost per ticket, CSAT, XLA |
| `M11 integrations` | ServiceNow / Jira SM / Zendesk / Freshservice bidirectional sync |
| `M12 admin-studio` | No-code workflow, catalog, prompt and policy authoring; approval-gated changes |

**Requirements on this structure:**
- A dependency-graph test in CI that **fails the build** on any illegal cross-module import.
- Each module ships its own migrations, seed data, tests, and OpenAPI/AsyncAPI contract.
- The entitlement engine gates at the API boundary *and* in the tool registry — a disabled module's tools must be invisible to agents, not merely rejected.
- `make demo MODULES=M01,M02,M03,M04` must produce a working reduced deployment. This is the proof of modularity; treat it as a test.

---

## 5. Multi-agent architecture

**Topology:** supervisor/orchestrator with specialist agents. Not a free-for-all agent swarm — the orchestrator owns control flow, budget, and escalation; specialists own narrow competence.

**Agents**

| Agent | Responsibility | May it act? |
|---|---|---|
| `Orchestrator` | Intent → plan → delegate → verify → close/escalate. Owns step budget, cost budget, deadlines. | Delegates only |
| `Triage` | Intent classification, entity extraction, urgency/impact scoring, duplicate & major-incident detection, language detection | No |
| `Knowledge` | Hybrid retrieval, evidence assembly, grounded answer drafting with citations | No |
| `Diagnostic` | Read-only interrogation of source systems to form a hypothesis (license state, group membership, mailbox rules, device compliance) | Read only |
| `Remediation` | Executes actions from the catalog, within risk tier and entitlement | Yes, tiered |
| `Approval` | Resolves approver from CMDB/HR graph, requests, tracks, expires | No |
| `Knowledge-Author` | Drafts/updates KB articles from resolved tickets per KCS | Drafts only |
| `Critic/QA` | Adversarial review before any Tier-2+ action or article publication; checks grounding, policy fit, blast radius | Veto power |
| `Escalation` | Assembles the human handoff package: transcript, hypothesis, evidence, actions attempted, next steps | No |

**Shared knowledge between agents — this is a core requirement, so make it explicit:**

- **One knowledge service, not per-agent vector stores.** All retrieval goes through `M03`. There is exactly one index of record.
- **Case blackboard.** Each `Interaction` has a shared, append-only working memory: facts, hypotheses (with confidence), evidence with provenance, actions attempted and outcomes, open questions. Every agent reads and writes it; nothing is passed as opaque prose between agents. Contributions are attributed and timestamped.
- **Memory tiers:** (a) session/working memory = blackboard, (b) organizational memory = KB + resolved-case corpus, (c) entity memory = user/device/service profile in the CMDB, (d) procedural memory = runbooks and learned resolution paths. Be explicit about which tier any given retrieval hits.
- **Structured handoffs.** Inter-agent messages are typed schemas (Pydantic/Zod), validated, and logged. Free-text-only handoffs are forbidden.

**Tools:** expose every integration as an **MCP server** so tools are reusable across agents, across deployments, and by the customer's own agents. Central tool registry holds: schema, risk tier, required entitlement, required scopes, idempotency key strategy, rate limit, rollback procedure, and a dry-run mode. **Every mutating tool must implement dry-run and be idempotent.**

**Guardrails:** step and cost budget per run; loop/oscillation detection; prompt-injection defense on all retrieved and user content (untrusted content is never treated as instructions); PII detection and redaction before egress to any model; jailbreak and scope-drift detection; a global kill switch per tenant per action class; graceful degradation to human at any failure.

**Orchestration of multi-system actions:** compose actions as a saga with explicit compensating transactions. A failed 4-step onboarding must not leave the tenant half-provisioned. Persist workflow state durably so a restart resumes rather than restarts.

---

## 6. Knowledge fabric (ITIL Knowledge Management + KCS v6)

**Lifecycle:** Capture in the workflow → Structure to the template → Reuse (search is the resolution path) → Improve on use. Article states: `WIP → Not Validated → Validated → Published → (Archived)`. Model the **Solve** loop and the **Evolve** loop distinctly.

**Article schema:** issue, environment, resolution, cause, metadata (products, CIs, intent tags, audience: internal vs employee-facing), confidence score, reuse count, last-validated date, decay date, author + validator, source ticket(s), language + translation linkage, required entitlements to view.

**Requirements**
- **Auto-authoring:** on incident resolution, the Knowledge-Author agent drafts an article or proposes an edit to an existing one. It never publishes unilaterally — a human validator or a policy-defined confidence+reuse threshold promotes it.
- **Gap detection:** cluster escalated/unresolved interactions to surface missing knowledge; feed a prioritized authoring queue ranked by frequency × cost.
- **Hybrid retrieval:** BM25/keyword + dense vector + metadata filters, with reranking. Justify and benchmark the embedding model; make it swappable. Retrieval must be filtered by tenant, entitlement, and audience *before* ranking, never after.
- **Grounded answers only.** Every employee-facing answer carries citations to article IDs and sections. If grounding is insufficient, say so and escalate — never fabricate a procedure.
- **Decay and review:** articles expire; usage without positive outcome flags for review; a change to a linked CI flags dependent articles.
- **Ingestion connectors:** SharePoint, Confluence, existing ServiceNow KB, PDF/DOCX, public vendor documentation (Microsoft Learn), with provenance preserved per chunk.
- **Bilingual:** articles are language-linked, not naively machine-translated. Retrieval works cross-lingually (Spanish query → English article → Spanish answer, with the citation pointing to the real source).

---

## 7. Automation & the Microsoft-suite action catalog

Every action is a declarative entry: id, description, inputs + validation, **risk tier**, required entitlement, required Graph/API scopes, preconditions, idempotency, dry-run behavior, rollback, audit fields, and success criteria.

**Risk tiers govern autonomy:**

- **T0 — Informational.** Read-only. Fully autonomous. *(Check license, mailbox size, device compliance, group membership, service health.)*
- **T1 — Self-service, reversible, user-scoped.** Autonomous with notification. *(Clear Teams cache guidance, resend meeting invite, restore OneDrive file version, unlock account after MFA re-verification, re-run Intune sync, release quarantined message per policy.)*
- **T2 — Entitlement-changing.** Requires approval from the resolved owner. *(Assign/reclaim M365 license, add to security or distribution group, grant SharePoint/Teams access, assign Intune policy, create shared mailbox.)*
- **T3 — Broad blast radius or privileged.** Human-executed; agent prepares the change record and evidence only. *(Tenant-level config, conditional access, mail flow rules, anything touching >N users, anything on a privileged identity.)*

**Build these first (highest-volume M365 service desk drivers):** password reset / self-service unlock via Entra, MFA re-registration, license assignment and reclamation, group membership, shared mailbox and calendar permissions, Outlook profile and OST corruption path, Teams cache/audio-device path, OneDrive sync failure path, SharePoint access request, Intune device compliance and app install, VPN/network triage, printer mapping, distribution list management.

**Adapters:** Microsoft Graph, Entra ID, Intune, Exchange Online, SharePoint/OneDrive, Teams. Plus ITSM bridges (ServiceNow, Jira Service Management) so T8 can front an incumbent rather than replacing it — this is the realistic enterprise entry point and must work well.

**Hard rules:** no action executes without a policy engine authorization and an audit event in the same transaction; every T2+ action has a tested rollback; all mutating calls are idempotent under retry; scopes follow least privilege and are documented per action.

---

## 8. Audit trail and compliance

**Design the audit ledger first — it is a foundation, not a feature.**

- **Append-only, hash-chained** event log (each entry carries the previous entry's hash; periodic signed checkpoints). Tamper-evident and independently verifiable. Separate storage lifecycle from operational data.
- **Every** governed mutation writes an event in the same database transaction as the mutation. Enforce structurally (repository layer or DB triggers), not by developer discipline.
- **Event schema:** event id, tenant, timestamp (UTC + local), actor (human user | agent id + version | system), on-behalf-of, action, target record + CI, before/after state, justification, policy decision + rule id, correlation and causation ids, source IP/device, outcome.
- **AI Decision Record** — attached to every agent action or recommendation: model id and version, prompt template id and version, input hash, retrieved evidence ids and scores, tool calls with arguments and results, confidence, alternatives considered and rejected, guardrails triggered, human review status, final disposition. **Success criterion: given any ticket id, reconstruct exactly why the system did what it did, six months later.**
- **Compliance surfaces:** one-click evidence pack for an auditor (scoped by date/tenant/user/record); retention and legal hold; right-to-erasure that preserves ledger integrity (crypto-shredding / pseudonymization, not deletion); segregation of duties; access log of who read what.
- **Map controls explicitly** in `docs/compliance/` to ISO/IEC 27001 Annex A, SOC 2 CC-series, ISO/IEC 20000, NIST AI RMF, EU AI Act transparency/logging obligations, and Mexico's LFPDPPP (Aviso de Privacidad, ARCO rights). Data residency is a deployment parameter, not a code change.

---

## 9. Technology stack

This is an **enterprise** product, not a consumer app — so no consumer BaaS, and no dependency that can't run inside a customer VPC or air-gapped.

**Defaults (challenge any of these in `PLAN.md` if you disagree — justify with trade-offs):**

- **Monorepo:** pnpm workspaces + Turborepo (or Nx). Shared `packages/core` for domain types, contracts, and validation consumed by every app.
- **Agent/AI services:** Python (typed, Pydantic). **Business/API services:** TypeScript (NestJS or Fastify). Keep the boundary clean and contract-tested; don't scatter the language split.
- **Datastore:** PostgreSQL as the system of record, with `pgvector` for embeddings (one dependency, portable everywhere) and row-level security for tenancy. Object storage via an S3-compatible port (S3 / Azure Blob / MinIO).
- **Event bus:** port with adapters — NATS JetStream or Redis Streams self-hosted; managed equivalents in cloud.
- **Workflow/durability:** a durable execution engine (Temporal, or a well-justified lighter alternative) for sagas, approvals, and long-running fulfillment.
- **LLM gateway:** one internal service. Adapters for Anthropic API, Amazon Bedrock, Azure OpenAI, and a self-hosted OpenAI-compatible endpoint (vLLM/Ollama) for air-gapped. Handles routing by task tier, fallback, caching, token accounting per tenant, PII redaction, and prompt-version pinning.
- **Tools:** MCP servers, one per integration domain.
- **Frontend:** React + TypeScript. Analyst workspace and Admin Studio as web apps; employee experience primarily inside Teams/Slack. Design system token-based so tenants can rebrand.
- **Packaging:** OCI containers, Helm charts, Terraform modules for AWS/Azure. `docker compose` for local and small private deployments. Air-gapped install path with a bundled model option, documented and tested.
- **Quality:** OpenTelemetry throughout; contract tests on every adapter; an LLM evaluation harness in CI (Section 12).

Verify current versions and breaking changes against official docs before pinning anything.

---

## 10. Repository structure

```
t8/
├── PROMPT.md  PLAN.md  README.md  Makefile
├── apps/
│   ├── api-gateway/  analyst-workspace/  admin-studio/
│   ├── teams-bot/    agent-runtime/
├── packages/
│   ├── core-domain/        # ITIL aggregates, state machines, invariants
│   ├── core-contracts/     # OpenAPI/AsyncAPI, shared schemas, events
│   ├── audit-ledger/       # hash-chained ledger, AI decision records
│   ├── policy-engine/      # entitlements, autonomy tiers, authorization
│   ├── llm-gateway/        # provider abstraction, routing, cost, redaction
│   ├── knowledge-service/  # KCS lifecycle + hybrid retrieval
│   ├── tool-registry/      # MCP tool catalog, risk tiers, dry-run
│   └── ui-kit/
├── modules/                # M01..M12, each self-contained
│   └── <module>/{src,tests,migrations,module.manifest.yaml,README.md}
├── mcp-servers/            # graph, entra, intune, exchange, sharepoint,
│                           # teams, servicenow, jira-sm
├── evals/                  # golden sets, scenario suites, regression gates
├── deploy/                 # helm/, terraform/, compose/, airgap/
└── docs/                   # adr/, compliance/, runbooks/, api/
```

---

## 11. Phases and definition of done

Each phase must end running, tested, and demonstrable. **Do not start a phase before I approve the previous one.**

| Phase | Deliverable | Done when |
|---|---|---|
| **0 — Foundations** | Monorepo, CI, core domain + state machines, audit ledger, policy engine, tenancy, observability, `make dev` | Illegal state transitions rejected by tests; ledger hash-chain verification passes; an ungoverned mutation is impossible by construction |
| **1 — ITSM core** | M02 incident/request lifecycle, queues, assignment, SLA clock, analyst workspace | An analyst can run a ticket end-to-end through the UI; every touch appears correctly in the ledger |
| **2 — Knowledge** | M03 KCS lifecycle, hybrid retrieval, ingestion, bilingual articles | Grounded, cited answers on a seeded corpus; retrieval benchmarked against the golden set; entitlement filtering verified |
| **3 — Conversation + Triage** | M01 Teams bot, identity resolution, Triage agent, deflection path | An employee resolves a known issue in Teams without a ticket being created; the interaction is fully audited |
| **4 — Multi-agent orchestration** | M04 orchestrator, blackboard, Critic/QA, escalation package, guardrails, budgets | Multi-step case with delegation, a Critic veto, and a clean human handoff — all reconstructable from the AI Decision Records |
| **5 — Automation** | M05 action catalog, MCP servers, T0–T2 M365 actions, approvals, saga compensation | Real password reset / license assignment / group membership in a test tenant, with dry-run, approval, rollback, and audit proven |
| **6 — Knowledge loop** | Auto-authoring, gap detection, decay, promotion policy | A resolved novel ticket produces a validated article that measurably resolves the next occurrence |
| **7 — Modularity proof** | Manifests, entitlement gating, dependency-graph CI test, reduced-SKU build | `make demo MODULES=…` deploys and runs a subset with no dead code paths and no broken UI |
| **8 — Deployment matrix** | Helm, Terraform, compose, air-gapped path, self-hosted model | Same test suite green in cloud and in a disconnected environment |
| **9 — Compliance & analytics** | M09 evidence packs, retention, legal hold; M10 dashboards | An auditor-ready pack generated for an arbitrary date range; deflection/containment/cost-per-ticket reported per tenant |
| **10 — ITSM integrations** | M11 ServiceNow / Jira SM bidirectional sync | T8 fronts an incumbent ITSM without state divergence under conflict |

---

## 12. Metrics and the evaluation harness

Build this in **Phase 2** and run it in CI on every change to a prompt, model, retrieval config, or policy. Treat AI regressions exactly like code regressions.

- **Golden sets:** ≥200 real-shaped tickets per language, spanning intent classification, retrieval, resolution, and refusal cases.
- **Adversarial suite:** prompt injection in email/KB content, ambiguous requests, social engineering ("I'm the CEO, skip approval"), out-of-scope requests, requests that must escalate.
- **Scored:** intent accuracy, retrieval precision/recall@k, grounding/citation faithfulness, hallucination rate, **false-action rate (target: zero — this is the trust-killing metric)**, escalation appropriateness, cost and latency per resolution.
- **Product metrics:** deflection rate, autonomous containment rate, MTTR, first-contact resolution, reopen rate, CSAT/XLA, knowledge reuse rate, cost per ticket, agent-hours saved.
- Prompts are **versioned artifacts** in the repo with changelogs, pinned per deployment, and rolled out behind flags. No prompt changes in production without an eval run.

---

## 13. Open questions — answer these before `PLAN.md`

**`[BLOCKING]` — I need answers before you design:**

1. **Replace or front?** Is T8 the system of record, or does it sit in front of an incumbent ITSM (ServiceNow/Jira SM) at launch? This changes the core data model.
2. **First deployment target:** which cloud, or private/on-prem first? And is air-gapped a launch requirement or a roadmap item?
3. **First design-partner tenant:** approximate seat count, M365 tenant complexity, and whether I can get a non-production tenant for integration testing.
4. **LLM constraint:** which provider(s) are contractually available, and is there a data-residency or no-third-party-model constraint for the first customer?
5. **Commercial model:** per-seat, per-resolution, or module-based licensing? This determines what the metering layer must count from day one.

**Assume and state, unless I say otherwise:**

6. Primary channel is Microsoft Teams; Slack and web widget follow.
7. Languages: es-MX and en-US at launch.
8. Team size and delivery horizon for phasing purposes — tell me what you assumed.
9. Autonomy at launch: T0/T1 autonomous, T2 approval-gated, T3 human-executed.
10. Whether the Admin Studio (M12) is in scope for v1 or deferred.

---

## 14. Your first response

Do **not** write code. Respond with:

1. Answers/assumptions for Section 13, with `[BLOCKING]` items flagged as questions to me.
2. Your architectural position: where you agree with this document, and — specifically — where you think it's wrong or over-engineered. I want the disagreement.
3. A phase-by-phase plan with the module boundaries you'll enforce.
4. The ADR list you'll write.
5. The riskiest assumption in the whole design and how you'd test it in week one.
