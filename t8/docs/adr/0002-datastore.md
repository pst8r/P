# ADR-0002: PostgreSQL as system of record, pgvector for embeddings, RLS for tenancy

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

The product must run identically in multi-tenant SaaS (the launch shape,
ADR-0017), in a customer VPC, and eventually air-gapped (P3). It needs
relational integrity for ITIL aggregates, vector search for knowledge
retrieval, row-level tenant isolation, and an object store for attachments and
evidence packs.

Every additional datastore is a component that must be operated, backed up,
secured, upgraded, and — critically — **installed in an air-gapped environment
by a customer's own operations team**.

## Decision

- **PostgreSQL** is the system of record for all governed data.
- **pgvector** holds embeddings, in the same database, under the same
  transactions and the same backup.
- **Row-Level Security** enforces tenant isolation *at the datastore*, not in
  application code. Every governed table has a `tenant_id` and an RLS policy;
  connections carry tenant context as a session variable set by the repository
  layer.
- **Object storage via an S3-compatible port** — S3, Azure Blob, or MinIO
  self-hosted — for attachments, ingested documents and evidence packs.
- Each module ships its **own migrations**; no module migrates another's tables.

## Consequences

**Positive.** One datastore to operate, secure and install everywhere. Vectors
participate in the same transaction as the records they describe, so an article
and its embedding cannot diverge. RLS makes tenant isolation a property of the
database rather than a rule developers must remember — it fails closed.

**Negative.** pgvector is slower than a dedicated vector store at very large
scale, and its index tuning is less forgiving. We accept this: portability is
differentiator #3, and a knowledge corpus per tenant is measured in tens of
thousands of chunks, not billions.

**Negative.** RLS bugs are cross-tenant data leaks. Mitigation: a standing
negative test suite that *attempts* cross-tenant reads through every access
path, run in CI from Phase 0, treated as a release gate.

**Revisit when:** a benchmark on a real tenant corpus shows retrieval latency
missing its target with pgvector properly tuned. Not before, and not on
principle — the retrieval interface (ADR-0012) keeps the option open.

## Alternatives considered

- **Postgres + a dedicated vector DB.** Better vector performance; a second
  system to operate, secure and install air-gapped, plus consistency problems
  between article and embedding. Rejected on P3.
- **A managed cloud database service.** Better operationally in SaaS; violates
  P3 outright.
- **Application-level tenant filtering.** Rejected: one forgotten `WHERE`
  clause is a breach. RLS fails closed; developer discipline does not.
