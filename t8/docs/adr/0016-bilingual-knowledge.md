# ADR-0016: Bilingual knowledge and cross-lingual retrieval

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

P8 makes Spanish (es-MX) and English (en-US) equal citizens in UI, knowledge,
intent handling and evaluation sets — "not a translation layer added later."
§6 requires articles to be language-linked rather than naively machine
translated, and cross-lingual retrieval: a Spanish query reaching an English
article and producing a Spanish answer whose citation points at the real source.

The failure mode to avoid is the common one: build in English, machine-translate
at the edges, and ship a product whose Spanish half is measurably worse while
the metrics — computed on the English set — look fine.

## Decision

**Language is a first-class property of a `KnowledgeArticle`, not a variant of
it.** Articles in different languages are **linked siblings** with their own
lifecycle state, validator, reuse count and decay date. A Spanish article is a
real article with a real owner, not a rendering of an English one.

**Translation is a drafting aid, never a publication path.** A machine
translation enters as `WIP`/`Not Validated` and follows the same KCS promotion
as any other draft (human validator, or the policy-defined confidence + reuse
threshold). It is never auto-published.

**Retrieval is cross-lingual.** A query in either language searches the whole
entitled corpus. When the best evidence is in the other language, the answer is
produced in the **user's** language and the **citation resolves to the actual
source article and section** — not to a translated shadow copy that does not
exist. Where the answer's language differs from its evidence's, that fact is
recorded in the AI Decision Record, because it is a quality signal worth
measuring.

**Language-asymmetric coverage is a measured gap, not an accident.** Gap
detection (§6) clusters by language, so "this topic exists only in English and
40% of the queries about it are Spanish" surfaces as ranked authoring work.

**No gate passes on one language.** Golden sets, the adversarial suite and every
phase's definition of done run in both (ADR-0014). Metrics are reported per
language; an aggregate that hides a 15-point Spanish gap is not an acceptable
report.

## Consequences

**Positive.** The Spanish experience is built, measured and staffed rather than
inherited. For the LATAM enterprise market this is a differentiator against
products that treat Spanish as localization.

**Negative.** Roughly double the knowledge curation effort, and a validator pool
that must cover both languages. This is a real staffing implication for the
customer's knowledge manager, and it belongs in the commercial conversation.

**Negative.** Cross-lingual retrieval quality depends on the embedding model's
multilingual behaviour, which constrains the choice in ADR-0012 — benchmarking
must be bilingual, and a model that wins on English alone does not win.

## Alternatives considered

- **English corpus, translate answers at the edge.** Much cheaper; produces a
  second-class Spanish product, citations that point at nothing a user can read,
  and metrics that conceal the gap. Rejected — it is precisely what P8 forbids.
- **Fully duplicated corpora per language.** Clean; doubles authoring and
  guarantees drift between siblings. Rejected in favour of linkage with
  independent lifecycles.
