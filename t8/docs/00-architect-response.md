# T8 IT Service Desk — First Response (PROMPT.md §14)

**Status:** awaiting answers to the `[BLOCKING]` questions in §1 below.
No code written. No scaffolding. `PLAN.md` and the ADRs follow approval.

---

## 1. Section 13 — answers, assumptions, and what I need from you

### `[BLOCKING]` — I need your answer

**Q1. Replace or front?**

This is the one that most changes the build, but less than the prompt assumes —
provided we make the split deliberately. My position:

T8 is **always** the system of record for `Interaction`, `KnowledgeArticle`,
`AgentRun`/`AgentStep`, `AuditEvent`, and `Approval`. Those are the product.
Only `Incident` / `ServiceRequest` are negotiable, and they get a
`system_of_record` discriminator on the aggregate:

- `T8` — we own the lifecycle; the state machine is authoritative.
- `EXTERNAL` — the incumbent owns the lifecycle; our aggregate is a
  **projection** with a reconciliation loop, and our state machine validates
  proposed transitions but the incumbent's response is truth.

Cost of building both: roughly one extra engineer-month in Phase 1, mostly in
the repository layer and conflict handling. Cost of picking wrong and
retrofitting: three to four months, because it contaminates every write path.

**My recommendation: launch as a front-end to the incumbent (`EXTERNAL`), build
the `T8` path in parallel.** Enterprise IT will not rip out ServiceNow to trial
an AI service desk; they will let you sit in front of it. Fronting is also the
honest test of the product thesis — if T8 only wins because it owns the ticket
table, it does not win.

**What I need from you:** which incumbent, and is it in the design partner's
tenant today?

**Q2. First deployment target — cloud, private, on-prem? Air-gapped at launch?**

Recommendation: **Azure first**, single-tenant-per-customer namespace inside
our subscription for the pilot, with the customer-VPC path proven by Phase 8.
Rationale: the buyer is an M365 shop, Entra ID is already the identity plane,
Graph is next door, and the security review is dramatically easier when the
data never leaves the same cloud as the mail it is reasoning about.

**Air-gapped should be a roadmap item, not a launch requirement** — but the
*port discipline* (P3) is a day-one, non-negotiable rule. The discipline is
nearly free; a day-one air-gap install path is about two engineer-months of
work (bundled model, offline registry, license/telemetry handling) that buys
nothing until a customer asks. I will not let anyone take a managed-service
shortcut that closes the door.

**What I need from you:** Azure, AWS, or the customer's own VPC first — and is
there a deal on the table that requires on-prem or air-gapped at signing?

**Q3. First design-partner tenant.**

Not a design question, but it gates the entire evaluation harness (§12) and my
week-one risk test (§5 below). I need:

- approximate seat count and the share of M365-vs-other ticket volume;
- tenant complexity: hybrid or cloud-only identity, number of Intune policies,
  how much of the estate is actually managed;
- **a non-production M365 tenant I can get Graph app registrations in** — if I
  cannot get one, Phase 5 slips and every automation test becomes a fake;
- **an export of 6–12 months of closed tickets** (anonymized). This is the
  single most valuable asset you can hand me, more than any infrastructure.

**Q4. LLM constraint.**

**What I need from you:** which providers are contractually available, and is
there a data-residency or no-third-party-model constraint for customer one?

Absent an answer I will assume: Anthropic API as primary, Bedrock as the
fallback/residency answer, Azure OpenAI as the adapter we prove but do not
depend on. The gateway (P4) means this is a config decision we can revisit —
but the *evaluation* baselines are model-specific, so a late switch costs a
re-run of the golden sets, not a rewrite.

**Q5. Commercial model.**

**What I need from you:** the pricing intent, even if it is provisional.

But here is the architectural answer that de-risks the question: **meter all
three from day one, and do not couple pricing to the meter.** The metering
layer counts, per tenant, per period:

- seats seen (distinct employees with an `Interaction`),
- resolutions by disposition and autonomy tier (deflected / autonomous /
  approval-gated / human),
- module usage against entitlement keys,
- token and infrastructure cost attributable per ticket.

That is maybe three engineer-weeks in Phase 0–1 and it makes the pricing
decision reversible. What is *not* reversible is failing to count from day one
— you cannot invoice on retroactive data you never recorded, and you cannot
price per-resolution without knowing what a resolution costs you.

**My recommendation:** platform fee per seat (predictable, procurement-friendly)
+ module entitlements (your §4 SKU boundaries) + a metered autonomous-resolution
component. Avoid pure per-resolution at launch: it puts the customer's finance
team in the room every time your agent gets better, and it makes deflection —
your best metric — look like a cost line.

### Assumptions I am making (say so if any is wrong)

**6. Primary channel is Teams.** Accepted — with one amendment. **Email intake
is not a "follows later" channel; it is the largest real intake surface in most
enterprises** and it is where prompt-injection actually arrives. I want email
intake in Phase 3 alongside Teams, not after. Slack and the web widget can
wait. Building the untrusted-content path early is also the honest way to test
the guardrails.

**7. es-MX and en-US at launch.** Accepted, and I will hold it as a hard gate:
no phase is "done" if it works in one language only, and both golden sets run
in CI from Phase 2.

**8. Team size and horizon (my assumption — correct me).** I am planning for
**6 engineers plus a part-time ITSM domain SME**: 2 TypeScript backend, 2
Python/AI, 1 frontend, 1 platform/infra, ~0.5 FTE SME who has actually run a
service desk. On that shape:

- Phases 0–2: ~10 weeks
- Phases 3–5 (the demonstrable product): ~14 weeks — **~6 months to a design
  partner running real T0–T2 automation**
- Phases 6–10: ~5 further months, with 7 (modularity) and 9 (compliance)
  pulled forward if the first deal demands them.

With 3 engineers, double it and cut M06/M07/M11/M12 from the v1 conversation
entirely. The SME is not optional: the fastest way to build the wrong ITSM
product is to build it from documentation about ITIL.

**9. Autonomy at launch: T0/T1 autonomous, T2 approval-gated, T3 human.**
Accepted — with a shadow-mode amendment. Every action class ships **disabled by
default per tenant**, runs in dry-run/shadow for a defined period (I suggest 30
days or 200 executions, whichever first), and is promoted to autonomous only on
evidence from the eval harness plus an explicit tenant opt-in. Autonomy is
earned per-tenant, not granted per-release. This costs nothing to build if the
kill switch and dry-run mode (§7) exist anyway, and it is the difference
between a trust incident and a graph in a QBR.

**10. Admin Studio (M12) in v1?** **My recommendation: defer the no-code
studio; ship config-as-code plus a read-only viewer in v1.** A genuine no-code
workflow/prompt/policy authoring surface is 3–4 engineer-months of frontend
that closes zero first deals — the first customer's workflows will be authored
by us, in the repo, under review, which is also the only way they are auditable
at that stage. What v1 *does* need: YAML/JSON definitions in version control, a
viewer so an admin can see what is configured without reading Git, and the
approval-gated change path (§8) so a config change is itself a governed
mutation. The studio becomes the UI over that same substrate later, not a
parallel system.

---

## 2. Architectural position — where this document is right, and where it is wrong

You asked for disagreement. Here it is, strongest objection first.

### 2.1 The audit design as written will not scale, and the fix matters

§8 asks for two things that conflict: **"every governed mutation writes an
audit event in the same database transaction"** and **"append-only,
hash-chained event log where each entry carries the previous entry's hash."**

Hash-chaining requires a total order. Computing "the previous entry's hash"
inside the mutation transaction means every governed write in a tenant
serializes behind a single chain tail — a hot row, a lock convoy, and a
deadlock source under exactly the concurrency an agent platform generates
(agents write far more audit events per unit time than humans do). It also
couples write latency on the hot path to the ledger.

**The fix, and this is ADR-0003:** separate durability from tamper-evidence.

1. In the mutation transaction, insert the audit event into an append-only
   table with a per-tenant monotonic sequence. No hashing, no cross-row read.
   This preserves P5 exactly — the mutation and its evidence commit or fail
   together, enforced in the repository layer plus a database constraint.
2. A separate sealer process batches sequence ranges into a **Merkle tree**,
   chains the batch roots, and publishes periodically **signed checkpoints**.
   Each event gets an inclusion proof.

You get the same property an auditor actually cares about — any alteration or
deletion is detectable, and provable to a third party — without serializing
production writes. It is also *stronger* than a naive chain: Merkle inclusion
proofs let you hand an auditor evidence for one ticket without exposing the
rest of the ledger.

Hold me to the §8 success criterion as written, though: *given any ticket id,
reconstruct exactly why the system did what it did, six months later.* That is
the right bar and I would build the ledger before the domain model to meet it.

### 2.2 "False-action rate target: zero" is the right goal stated as an
unachievable metric

You cannot drive a *model* metric to zero, and a target of zero on a stochastic
system either gets quietly redefined or gets gamed. The goal is right; the
framing needs to change, because the framing determines the architecture.

**Reframe it as two metrics:**

- **Unauthorized action rate — zero by construction, not by training.** The
  LLM never emits an action. It emits an *action proposal*: a typed object
  naming a catalog action and its arguments. A deterministic pipeline —
  schema validation → precondition checks → entitlement check → policy engine
  → risk-tier autonomy check → approval state — decides whether it executes.
  Any proposal that fails any gate is refused and logged. This is testable the
  way code is testable, and it is where §2's P6 and §7's risk tiers actually
  live. A target of zero here is meaningful because it is a property of the
  gate, not the model.
- **Inappropriate proposal rate** — a model quality metric, measured against
  the adversarial suite, driven down over time, never expected to hit zero.

This is the same instinct as your §0 "determinism where it matters," taken one
step further: the model does not decide, and it also does not *act*. It
proposes. I agree with the principle so strongly that I want it structurally
enforced rather than stated.

### 2.3 Twelve modules before one customer is over-engineering

§4 makes module boundaries the SKU boundaries and asks that every subset build,
deploy, and run alone. That is the correct *long-run* structure and the wrong
*launch* structure. Twelve independently deployable modules with their own
migrations, contracts, and deployment topology is a large, permanent tax paid
before a single customer has told you which subsets they would actually buy.
It is one of the reliable ways platform companies spend a year shipping
infrastructure instead of product.

**My counter-proposal, which keeps your optionality and most of your cost:**

- **Enforce the boundary discipline from day one** — this part is cheap and I
  will not compromise on it. Every module gets its directory, its
  `module.manifest.yaml`, its entitlement key, and its own migrations. The
  dependency-graph CI test that fails the build on illegal cross-module imports
  exists in Phase 0. No module imports another's internals, ever.
- **But only five boundaries are independently *deployable* at launch:**
  kernel, `M01 conversation`, `M02 itsm-core`, `M03 knowledge`, `M04 agents`,
  `M05 automation`. These are the ones a reduced deployment plausibly needs.
- M06–M12 live as properly-bounded modules inside the main deployment until a
  customer's purchase actually splits them. Because the import discipline held,
  splitting one later is days of work, not a refactor.
- Keep `make demo MODULES=...` as a Phase 7 gate over the five real ones. It is
  a good test; it should test something real.

If you tell me the commercial model is module-based licensing (Q5) and a
specific customer wants a specific subset, I will build exactly those
boundaries deployable. What I will not do is build twelve deployment stories on
speculation.

### 2.4 MCP everywhere is wrong for internal tools, right for the interop surface

§5 says "expose every integration as an MCP server." MCP is genuinely the right
answer for the boundary you want: reusable by the customer's own agents, across
deployments, third-party clients. But making *every internal* integration an
MCP server adds a process hop, a serialization boundary, and — critically — a
place where tenant context and least-privilege scopes can be lost or forged,
which is precisely where you cannot afford ambiguity.

**Position: one tool registry, two surfaces.** The registry is the single
source of truth for schema, risk tier, entitlement, scopes, idempotency
strategy, rate limit, rollback, and dry-run. Internal agents call tools through
a typed in-process interface. The MCP servers are a **published projection** of
that same registry for external consumers, with tenant context and scope
propagation as an explicit, designed part of the protocol binding — not an
afterthought. One definition, two transports; the risk metadata cannot drift
between them.

This gets its own ADR because the tenant-propagation-over-MCP question is
genuinely hard and I do not want it solved incidentally.

### 2.5 Temporal in Phase 0 buys nothing and costs the air-gap story

§9 lists a durable execution engine among the defaults and §11 puts foundations
in Phase 0, but sagas do not appear until Phase 5. Standing up Temporal in
Phase 0 means every developer, every CI run, and every air-gapped install
carries that operational dependency for five phases before it does any work.

**Position:** define `WorkflowPort` in Phase 0 and implement the
Postgres-backed adapter (transactional outbox plus a durable step runner —
a few hundred lines, and we already have Postgres). Adopt Temporal in Phase 5
when sagas and long-running approvals arrive, behind the same port. If the
Postgres adapter turns out to be sufficient for the deployment shapes we
actually sell, that is a win, not a shortcut. This satisfies P3 properly: a
port with two adapters, one of which runs anywhere.

The counter-argument — that retrofitting durability is painful — is real, which
is exactly why the *port* exists from Phase 0. What is painful is retrofitting
the abstraction, not swapping the adapter behind it.

### 2.6 Auto-authoring from every resolved ticket will drown the curation queue

§6 says the Knowledge-Author agent drafts an article on incident resolution.
Run that against real volume and you generate hundreds of near-duplicate drafts
a week, the human validators stop reading the queue within a month, and the KCS
loop is dead — not because the model wrote bad articles, but because nobody
can triage that much output.

**Position:** draft only on **novelty or delta**. An article is drafted when
retrieval missed (no article above the relevance threshold was used) *and* the
resolution succeeded; an edit is proposed when an existing article was used but
the analyst deviated from it. Everything else feeds the gap-detection
clustering instead, which surfaces authoring work ranked by frequency × cost —
which §6 already asks for and which is the better mechanism. The queue should
be sized to what a human validator can actually process in a week, and the
ranking should be the thing that decides what is in it.

### 2.7 200 golden tickets per language, before a design partner, is fiction

§12 asks for ≥200 real-shaped tickets per language built in Phase 2. You cannot
have real-shaped tickets before you have real tickets, and a golden set that we
invent will encode our assumptions and then congratulate us for meeting them.
That is worse than no eval harness, because it produces confident numbers.

**Position:** build the harness in Phase 2 as specified — the machinery is
right and early is right. But populate it from the design partner's ticket
export (Q3), and **tag every item with its provenance: `real`, `real-derived`,
or `synthetic`.** Report all metrics split by provenance. Synthetic items are a
scaffold for the harness, never evidence for a claim. If the partner export
does not arrive, the honest statement in the Phase 2 review is "the harness
runs; the numbers are not yet meaningful," not a dashboard of green.

The adversarial suite is the exception — prompt injection, social engineering,
scope drift. Those we can and should author ourselves, immediately, and they
are the ones I would gate releases on first.

### 2.8 Some domain modeling in §3 is Phase-8 work wearing Phase-0 clothes

Per-tenant business calendars with LATAM/US time zones and clock-stop
semantics, major incident declaration with comms fan-out, and the Continual
Improvement register are all correct ITIL and all significant workflow
surface. Model the *types* in `core-domain` from the start so the shape is
right. Do not build the workflows until SLM (Phase 8-equivalent) and do not let
them into the Phase 0 definition of done. SLA clock math with pause semantics
alone is a week of work and a long tail of bugs; it should arrive when there is
an SLA being measured.

### 2.9 The language split is justified, and here is the boundary I will enforce

§9's Python/TypeScript split is a real tax and I am accepting it, because the
AI side genuinely needs Python (evals, embeddings, retrieval tooling,
the ecosystem) and forcing that into TypeScript costs more than the boundary
does. But an unmanaged split becomes two half-systems.

**The rule I will enforce, and it also makes P5 structurally enforceable:**
**Python services never write to governed tables.** All governed mutations go
through the TypeScript repository layer, which is the single place where the
"audit event in the same transaction" invariant lives. Python reads (blackboard,
retrieval, CI graph) are fine and go through RLS-scoped connections. Anything
an agent wants to *change* is an API call with tenant context, which is also
where the policy gate sits. One invariant, one implementation, one place to
audit it.

### 2.10 Where I agree without reservation

Worth stating explicitly, because these are the non-obvious calls this document
gets right and I would defend them against pushback:

- **Entitlement filtering before ranking, never after** (§6). Most RAG systems
  get this backwards and it is a data-leak incident waiting to happen. It is
  also harder than it sounds — it constrains the index design, which is why it
  belongs in the retrieval ADR.
- **Risk tier is a property of the action, not the agent** (P6/§7). This is the
  correct decomposition and it is what makes autonomy governable.
- **Blackboard over opaque prose handoffs** (§5). Typed, attributed, append-only
  shared memory is the difference between a debuggable multi-agent system and a
  telephone game. Free-text handoffs should be a build failure.
- **Fail closed** (P10). Non-negotiable, and it needs to be tested adversarially,
  not just asserted.
- **Audit-by-construction as a foundation, built first** (§8). Right call. It is
  also the differentiator that is hardest to retrofit, which is why competitors
  bolt it on and cannot catch up.
- **Standard changes as the only autonomously-executable change type** (§3).
  Correct, and it maps cleanly onto the T0–T2 catalog.
- **PostgreSQL + pgvector as one portable dependency** (§9). Right trade:
  slightly worse than a dedicated vector store at scale, dramatically better
  for the deploy-anywhere requirement. Revisit only with benchmark evidence.

### 2.11 One thing the document does not mention and should

**Prompt injection via the ITSM record itself.** The adversarial suite covers
injection in email and KB content. The higher-value attack is an employee
putting instructions in a ticket description or a Teams message that the
Triage or Knowledge agent later reads as context — an insider path to
privilege escalation that looks exactly like normal usage. Every piece of
content that originated outside the trust boundary must be structurally marked
as data, at ingestion, and stay marked through the blackboard and into every
prompt. This is an architecture decision, not a prompt-engineering one, and it
belongs in the guardrails ADR.

---

## 3. Phase plan and enforced module boundaries

Structure follows §11 with the amendments argued above. **Each phase ends
running, tested, and demonstrable; I will not start one without your sign-off
on the previous.**

| Phase | What ships | Definition of done |
|---|---|---|
| **0 — Foundations** | Monorepo, CI incl. dependency-graph test, `core-domain` aggregates + state machines, **audit ledger (in-transaction append + Merkle sealer)**, policy engine, tenancy/RLS, `WorkflowPort` (Postgres adapter), LLM gateway skeleton, OTel, metering counters, `make dev` | Illegal transitions rejected by tests; ledger verification + inclusion proofs pass; an ungoverned mutation is impossible by construction (proven by a test that tries); tenant isolation proven by a cross-tenant read test |
| **1 — ITSM core** | `M02` incident/request lifecycle, queues, assignment, analyst workspace, **both SoR modes** (T8-owned and projection) | An analyst runs a ticket end-to-end in the UI; every touch reconstructable from the ledger; SLA *types* modeled, clock deferred to Phase 8 |
| **2 — Knowledge + eval harness** | `M03` KCS lifecycle, hybrid retrieval with entitlement-pre-filtering, ingestion, bilingual articles; **eval harness in CI**, adversarial suite authored | Grounded cited answers on the seeded corpus; retrieval benchmarked with provenance-split metrics; entitlement filtering verified by a test that tries to leak; adversarial suite gating merges |
| **3 — Conversation + Triage** | `M01` Teams bot **and email intake**, identity resolution, Triage agent, deflection path, untrusted-content marking | An employee resolves a known issue in Teams with no ticket created, fully audited; an injected instruction in an email body provably fails to influence any decision |
| **4 — Multi-agent orchestration** | `M04` orchestrator, blackboard, Critic/QA, escalation package, guardrails, step/cost budgets | A multi-step case with delegation, a Critic veto, and a clean handoff — all reconstructable from AI Decision Records six months later (tested by reconstructing one) |
| **5 — Automation** | `M05` action catalog, tool registry + MCP projection, T0–T2 M365 actions, approvals, sagas (Temporal adopted here), shadow mode | Real password reset / license assignment / group membership in the **test tenant**, with dry-run, approval, rollback and audit proven; every T2 action has a tested rollback |
| **6 — Knowledge loop** | Novelty-gated auto-authoring, gap detection, decay, promotion policy | A resolved novel ticket produces a validated article that measurably resolves the next occurrence — measured, not asserted |
| **7 — Modularity proof** | Manifests, entitlement gating at API + tool registry, reduced-SKU build over the five deployable boundaries | `make demo MODULES=...` runs a subset with no dead code paths, no broken UI, and a disabled module's tools invisible to agents |
| **8 — SLM + deployment matrix** | `M08` SLA/OLA clocks, calendars, breach prediction, escalation; Helm, Terraform, compose, air-gap path | Same suite green in cloud and disconnected; clock-stop semantics correct across time zones |
| **9 — Compliance & analytics** | `M09` evidence packs, retention, legal hold, crypto-shredding erasure; `M10` dashboards | Auditor-ready pack for an arbitrary range; erasure preserves ledger verifiability; deflection/containment/cost-per-ticket per tenant |
| **10 — ITSM integrations** | `M11` ServiceNow / Jira SM bidirectional sync | T8 fronts an incumbent with no state divergence under induced conflict |

`M06 cmdb` lands inside Phase 4 (the Diagnostic agent needs the CI graph and
the Approval agent needs the ownership graph). `M07 problem-change` lands with
Phase 5 (Standard changes gate autonomous execution). `M12 admin-studio` is
deferred per §1 Q10 — its substrate (config-as-code + approval-gated change)
is built in Phase 0 regardless.

**Boundaries enforced from Phase 0, by CI:** kernel packages
(`core-domain`, `core-contracts`, `audit-ledger`, `policy-engine`,
`llm-gateway`, `tool-registry`, `knowledge-service`, `ui-kit`) may be imported
by modules; **no module may import another module**, only publish/consume
events or call a published interface. Python may read governed tables under RLS
and must never write them.

---

## 4. ADRs I will write

Ordered by how expensive each is to reverse. `0001` depends on your Q1 answer;
`0006`'s routing defaults depend on Q4; `0017` depends on Q2.

| ADR | Decision |
|---|---|
| 0001 | System-of-record posture: T8-owned vs projection-of-incumbent, and the discriminated aggregate |
| 0002 | Datastore: PostgreSQL as SoR, pgvector for embeddings, RLS for tenancy; S3-compatible object port |
| 0003 | **Audit ledger: in-transaction append + asynchronous Merkle sealing with signed checkpoints** (supersedes naive hash-chaining) |
| 0004 | Event bus: port + adapters; NATS JetStream as the self-hosted default |
| 0005 | Durable execution: `WorkflowPort`, Postgres adapter first, Temporal adopted at Phase 5 |
| 0006 | LLM gateway: provider abstraction, task-tier routing, fallback, caching, token accounting, prompt-version pinning |
| 0007 | Agent orchestration: custom supervisor over typed contracts vs. an off-the-shelf framework |
| 0008 | Tool registry as single source of truth; MCP as published projection; tenant + scope propagation over MCP |
| 0009 | Language split: the Python/TypeScript contract boundary and the governed-write rule |
| 0010 | Tenancy and isolation: pooled-with-RLS vs silo, and tenant-context propagation through agent tool calls |
| 0011 | Auth: Entra OIDC, on-behalf-of flow, service principals, least-privilege scope sets per action |
| 0012 | Retrieval: hybrid architecture, embedding model selection and swappability, entitlement-before-ranking |
| 0013 | Policy engine: OPA/Cedar vs. in-house typed rules; where the decision point sits |
| 0014 | Prompt and model versioning: artifacts, changelogs, pinning, flagged rollout, eval gating |
| 0015 | Modularity mechanics: manifest schema, entitlement enforcement points, dependency-graph CI test |
| 0016 | Bilingual knowledge: language-linked articles and cross-lingual retrieval |
| 0017 | Deployment topology: first target, customer-VPC path, air-gap constraints |
| 0018 | PII redaction, pseudonymization, and right-to-erasure via crypto-shredding with ledger integrity preserved |
| 0019 | Untrusted-content handling: structural data/instruction separation from ingestion through prompts |

---

## 5. The riskiest assumption, and how I test it in week one

**The riskiest assumption is not technical.** It is this:

> A meaningful share of real Tier-1 volume is resolvable by a *bounded,
> pre-authorizable* action catalog plus knowledge retrieval.

Everything else in this document is engineering with known shapes. This one
determines whether the product has a market, what the pricing model can be, and
whether Phase 5 is the centre of the product or a demo feature. If the true
figure is 40%, T8 is a strong business. If it is 12%, the same engineering
produces a well-audited chatbot and the commercial model in Q5 cannot be
per-resolution.

Everyone in this category quotes a deflection number. Nobody's number survives
contact with a specific enterprise's actual ticket mix.

**Week-one test — five days, one script, no platform:**

1. Take 500 anonymized closed tickets from the design partner (Q3), stratified
   by category and sampled across the year, both languages.
2. Two people — me and the ITSM SME — independently label each into:
   **(i)** answerable from knowledge alone, **(ii)** resolvable by one of ~15
   candidate catalog actions, **(iii)** needs a human. Measure inter-rater
   agreement; where we disagree, that disagreement is itself a finding about
   how ambiguous the category boundary is.
3. Build a thin retrieval + classification prototype — a script, not a system
   — against the partner's existing KB, and compare its labels to ours. The gap
   between *human-judged resolvable* and *machine-judged resolvable* is the
   honest starting accuracy, before any platform exists to flatter it.
4. Cost the top 15 actions by frequency × average handle time. That ranking,
   not §7's list, decides what gets built first in Phase 5.

**Decision rule, set before seeing the data:** if (i)+(ii) is below ~35%, the
thesis and the pricing model both change, and I want to know that in week one
rather than in month seven.

**Second risk, also testable in week one, on paper:** that the customer's
security team will actually grant the Graph scopes T2 actions require. Put the
exact scope list for the first five actions in front of them in week one. If
`Group.ReadWrite.All` is a non-starter in that organization, T2 autonomy is
dead there and the product is T0/T1 plus excellent escalation — which is still
a product, but a different one, and the roadmap should say so honestly.

---

## 6. What I need to proceed

Answers to **Q1, Q2, Q4, Q5**, the logistics in **Q3** (especially the ticket
export and the non-production tenant), plus a yes/no on my amendments to
assumptions 6, 9, and 10 — email intake in Phase 3, shadow-mode promotion, and
deferring the Admin Studio.

On receiving those I will produce `PLAN.md` and ADRs `0001`–`0019`, and wait
for your approval on `PLAN.md` before any scaffolding.
