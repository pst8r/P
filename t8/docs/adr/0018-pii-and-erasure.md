# ADR-0018: PII redaction, pseudonymization, and crypto-shredding erasure

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

§8 requires right-to-erasure that **preserves ledger integrity** — explicitly
"crypto-shredding / pseudonymization, not deletion" — plus retention, legal
hold, and an access log of who read what. §5 requires PII detection and
redaction before egress to any model. §8 maps controls to ISO/IEC 27001 Annex A,
SOC 2, ISO/IEC 20000, NIST AI RMF, EU AI Act transparency and logging
obligations, and Mexico's LFPDPPP (Aviso de Privacidad, ARCO rights).

The tension is structural: an append-only, tamper-evident ledger (ADR-0003) and
a legal obligation to erase personal data appear to be incompatible. They are
not, if personal data never sits in the ledger in a form that must be deleted.

## Decision

### Personal data is referenced, not embedded

Governed records and audit events reference personal data through a
**pseudonymous subject id**. Identifying attributes live in a separate,
per-tenant **subject store**, encrypted with a **per-subject key**.

### Erasure is crypto-shredding

An ARCO / erasure request destroys that subject's key. Every reference becomes
permanently undecryptable while **every hash, Merkle leaf and inclusion proof
remains valid** — the ledger still proves exactly what happened and when, and no
longer reveals to whom. The erasure is itself a governed, audited event.

Where free-text inevitably carries identifiers (a ticket description, a
transcript), those fields are stored in the subject-keyed envelope rather than
in the clear, so shredding reaches them too.

### Redaction before egress

PII detection and redaction runs in the LLM gateway (ADR-0006) before any
provider call, including to a tenant's own endpoint — the tenant's provider is
still a third party for some of their own data. Redaction is recorded per call:
what class was redacted, not the value. A detector failure fails closed (P10) —
the call does not proceed unredacted.

### Retention, hold, and read access

- Retention policies are per tenant and per record class; the ledger's lifecycle
  is separate from operational data (ADR-0003).
- **Legal hold overrides retention** and suspends erasure, with the conflict
  recorded rather than silently resolved.
- **Reads of sensitive records are themselves audited** — the §8 "access log of
  who read what" — including reads by agents.
- Segregation of duties: the role that can shred cannot also seal the ledger.

### Compliance mapping

Control mappings live in `docs/compliance/` and are maintained as the system
changes, not written once before an audit.

## Consequences

**Positive.** Erasure and tamper-evidence coexist rather than trading off — the
main reason ADR-0003 avoids hashing raw content into a chain. Residency and
erasure both become deployment and data-model properties rather than code
changes.

**Negative.** Per-subject key management is real cryptographic infrastructure:
key rotation, escrow, recovery, and the certainty that a lost key is
indistinguishable from an erasure. Failure modes here are severe and the design
needs review beyond this ADR.

**Negative.** Every read of identifying data costs a decrypt, and analytics over
personal attributes becomes deliberately hard. That is the intended shape.

**Negative.** Redaction has false negatives. It reduces exposure; it is not a
guarantee, and should never be presented to a customer as one.

## Alternatives considered

- **Hard deletion on erasure request.** Simple and legally clean; destroys the
  audit trail the product exists to provide. Rejected.
- **Full-text encryption of all records.** Stronger; makes retrieval and
  analytics impractical. Rejected in favour of subject-scoped envelopes.
- **Tokenize only obvious identifiers (name, email, employee id).** Cheaper;
  leaves identifying material in free text, where it actually lives. Rejected.
