# ADR-0003: Audit ledger — in-transaction append plus asynchronous Merkle sealing

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15
- **Supersedes:** PROMPT.md §8's per-entry hash chain

## Context

PROMPT.md §8 requires two things that conflict at the implementation level:

1. *"Every governed mutation writes an audit event in the same database
   transaction as the mutation"* (P5), and
2. *"Append-only, hash-chained event log — each entry carries the previous
   entry's hash."*

Computing "the previous entry's hash" inside the mutation transaction requires
reading the chain tail, which imposes a **total order on every governed write in
a tenant**. That is a hot row, a lock convoy, and a deadlock source under
exactly the concurrency an agent platform produces — agents emit far more audit
events per unit time than humans do. It also couples production write latency to
ledger maintenance.

Both requirements are correct in intent. The intent of (1) is *durability of
evidence*: it must be impossible to mutate without recording why. The intent of
(2) is *tamper-evidence*: alteration or deletion must be detectable and provable
to a third party. These are separable.

## Decision

**Separate durability from tamper-evidence.**

**1. Hot path — in the mutation transaction.** Insert the audit event into an
append-only table with a per-tenant monotonic sequence. No chain-tail read, no
hashing, no cross-row dependency. Enforced structurally: governed mutations are
only reachable through a repository layer that writes both, plus database
constraints and triggers that reject a governed-table write without a
corresponding event in the same transaction. **P5 is preserved exactly.**

**2. Sealing — asynchronous.** A sealer process batches contiguous sequence
ranges into a **Merkle tree**, chains batch roots to their predecessor, and
publishes **periodically signed checkpoints**. Every event gains an inclusion
proof against a signed root.

**3. Verification.** An independent verifier recomputes roots from raw events
and validates checkpoint signatures. It runs in CI against seeded data (Phase 0
gate) and on demand for a real tenant.

**Event schema** (per §8): event id, tenant, timestamp (UTC + tenant-local),
actor (human | agent id + version | system), on-behalf-of, action, target record
and CI, before/after state, justification, policy decision + rule id,
correlation and causation ids, source IP/device, outcome.

**AI Decision Record**, attached to every agent action or recommendation: model
id and version, prompt template id and version, input hash, retrieved evidence
ids and scores, tool calls with arguments and results, confidence, alternatives
considered and rejected, guardrails triggered, human review status, final
disposition.

**Storage lifecycle is separate from operational data** — different retention,
different backup policy, legal hold independent of the records it describes.

## Consequences

**Positive.** No write serialization on the hot path; throughput scales with the
database rather than with a single chain tail. Merkle inclusion proofs are
*stronger* than a naive chain for the actual audit use case: we can prove one
ticket's events are intact and unaltered **without exposing any other tenant
data or any other ticket** — which is precisely what an evidence pack (§8,
Phase 9) needs to be.

**Negative.** Tamper-evidence is eventual, not synchronous. Between an event's
commit and the next checkpoint (seconds, configurable) it is durable and
append-only but not yet sealed. An attacker with database write access inside
that window could alter an unsealed event undetectably. Mitigations: short
checkpoint interval, append-only permissions at the database role level, and
the sealer running with separate credentials.

**Negative.** A second process to operate and monitor. Sealer lag is an alerted
SLO; sustained lag is a compliance incident, not a performance one.

**Enables Phase 9.** Crypto-shredding erasure (ADR-0018) works cleanly here:
pseudonymized fields can be shredded while their hashes — and therefore the
Merkle proofs — remain valid. A naive chain over raw content makes
right-to-erasure and ledger integrity mutually exclusive.

## Alternatives considered

- **Per-entry hash chain as literally specified.** Simplest to explain; the
  write-serialization cost is real and arrives exactly when the product is
  succeeding. Rejected.
- **Chain per (tenant, aggregate) instead of per tenant.** Reduces contention
  without eliminating it; complicates verification (many chains) and still
  serializes hot tickets, which are the ones that matter.
- **External append-only ledger service (QLDB or similar).** Strong properties;
  violates P3 and cannot be installed air-gapped. Rejected.
- **Write-ahead to an event bus, seal downstream.** Loses the same-transaction
  guarantee — the mutation could commit while the event is lost in flight.
  Rejected: that is the one property P5 exists to provide.
