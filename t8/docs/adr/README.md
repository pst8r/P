# Architecture Decision Records

Ordered by cost of reversal. All are **Proposed** pending approval of
[`../../PLAN.md`](../../PLAN.md).

Three ADRs deviate from `PROMPT.md` as written; the argument for each is in
[`../00-architect-response.md`](../00-architect-response.md) §2.

| ADR | Decision | Origin |
|---|---|---|
| [0001](0001-system-of-record.md) | System of record: discriminated aggregate, both modes first-class | §13 Q1 |
| [0002](0002-datastore.md) | PostgreSQL + pgvector + RLS; S3-compatible object port | default |
| [0003](0003-audit-ledger.md) | **Audit ledger: in-transaction append + async Merkle sealing** — *supersedes §8's per-entry hash chain* | disagreement |
| [0004](0004-event-bus.md) | Event bus: port + adapters, NATS JetStream default | default |
| [0005](0005-durable-execution.md) | `WorkflowPort`, Postgres adapter first, Temporal at Phase 5 | disagreement |
| [0006](0006-llm-gateway.md) | **LLM gateway: per-tenant provider identity, BYO-key/endpoint/residency** | §13 Q4 |
| [0007](0007-agent-orchestration.md) | Agent orchestration: custom supervisor over typed contracts | default |
| [0008](0008-tool-registry-mcp.md) | **Tool registry: one registry, two surfaces; external MCP tools T3 by default** | §13 Q4 |
| [0009](0009-language-split.md) | Language split and the governed-write rule | default |
| [0010](0010-tenancy-isolation.md) | Pooled multi-tenancy with RLS, context propagated everywhere | §13 Q2 |
| [0011](0011-auth-and-scopes.md) | Entra OIDC, on-behalf-of, per-action least-privilege scopes | default |
| [0012](0012-retrieval.md) | Hybrid retrieval, reranked, entitlement-filtered before ranking | default |
| [0013](0013-policy-engine-and-action-proposals.md) | **Policy engine + the action-proposal rule** — *reframes §12's zero false-action target* | disagreement |
| [0014](0014-prompt-and-eval-versioning.md) | Prompt/model versioning and the eval gate, with provenance tagging | default |
| [0015](0015-modularity-mechanics.md) | Modularity mechanics; five deployable boundaries at launch, not twelve | disagreement |
| [0016](0016-bilingual-knowledge.md) | Bilingual knowledge and cross-lingual retrieval | default |
| [0017](0017-deployment-and-autonomy-rollout.md) | SaaS at launch, other shapes later; autonomy promoted per tenant | §13 Q2 |
| [0018](0018-pii-and-erasure.md) | PII redaction, pseudonymization, crypto-shredding erasure | default |
| [0019](0019-untrusted-content.md) | **Untrusted content: structural data/instruction separation** — *gap not in PROMPT.md* | gap |
