# ADR-0012: Retrieval — hybrid, reranked, entitlement-filtered before ranking

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

`M03` is the single index of record: all retrieval goes through it, and there
are no per-agent vector stores (§5). Retrieval quality determines deflection
rate, and retrieval *correctness* — never surfacing content the user may not see
— determines whether the product survives a security review.

PROMPT.md §6 requires hybrid retrieval with reranking, a benchmarked and
swappable embedding model, grounded answers with citations, and filtering by
tenant, entitlement and audience **before** ranking.

## Decision

**Hybrid retrieval:** BM25/keyword + dense vector + metadata filters, combined
and then reranked. Keyword recall matters more than usual here because service
desk queries are full of exact tokens — error codes, product names, policy
identifiers — that dense retrieval alone handles poorly.

**Entitlement filtering happens before ranking, never after.** Tenant,
entitlement and audience (internal vs employee-facing) are applied as index-level
predicates. Post-filtering a ranked list is forbidden: it leaks existence through
result counts and ranking behaviour, and one bug in the filter step becomes a
disclosure. This constrains index design — the filters must be first-class
indexed fields — and that cost is accepted deliberately.

**The embedding model is swappable and benchmarked.** The choice is made on
measured performance against the golden set (ADR-0014) in **both** languages,
not on reputation. Embeddings carry their model id and version; a model change
is a re-index, tracked as a migration, and the retrieval benchmark is re-run
before promotion.

**Grounded answers only.** Employee-facing answers carry citations to article
ids and sections. Where the provider supports document citations natively
(returning cited spans with character or page locations), the gateway
(ADR-0006) requests them, so citations point at real spans rather than
model-asserted references. Where it does not, the caller degrades to a defined
weaker mode and the answer is marked accordingly — it never silently becomes
uncited prose.

**Insufficient grounding escalates.** Below a confidence and coverage threshold
the system says so and hands off (P10). It never fabricates a procedure. This is
a code path with tests, not a prompt instruction.

**Provenance per chunk** is preserved through ingestion (SharePoint, Confluence,
existing ServiceNow KB, PDF/DOCX, public vendor documentation), because a
citation is only useful if it resolves to a source a human can open.

## Consequences

**Positive.** Correct-by-construction entitlement behaviour. Citations that
survive scrutiny. A retrieval component that can be improved on measurements
rather than opinion.

**Negative.** Pre-filtering costs recall tuning effort and constrains how the
index is built and sharded. Accepted.

**Negative.** Native citation support is a provider capability, so answer
quality varies across tenant bindings (ADR-0006). The capability matrix makes
this explicit rather than surprising.

**Negative.** Re-indexing on embedding change is operationally heavy at tenant
scale. Treated as a migration with a defined runbook rather than an ad-hoc job.

## Alternatives considered

- **Dense-only retrieval.** Simpler; measurably worse on exact-token service
  desk queries. Rejected.
- **Post-filtering by entitlement.** Easier to implement over an existing index;
  a disclosure risk and an information leak through ranking. Rejected outright.
- **Per-agent indices.** Explicitly rejected by §5, and correctly: multiple
  indices of record means multiple entitlement implementations.
