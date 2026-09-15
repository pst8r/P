# ADR-0004: Event bus — port with adapters, NATS JetStream as the default

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

P1 makes the event bus the primary cross-module communication mechanism, so it
is on the critical path for every module boundary. P3 forbids a hard dependency
on a proprietary managed service. The bus must deliver durably (a lost event can
mean a lost SLA clock or an unprocessed approval), preserve ordering where the
domain requires it, and run in SaaS, in a customer VPC, and air-gapped.

## Decision

Define an **`EventBusPort`** in `core-contracts` with:

- publish with an idempotency key and a correlation/causation pair,
- durable consumer groups with at-least-once delivery,
- per-subject ordering,
- dead-letter handling with replay,
- tenant context carried in event metadata, not in the payload alone.

**Default adapter: NATS JetStream** (self-hostable, durable streams, good
operational story, small footprint, runs air-gapped). **Second adapter: Redis
Streams**, for small private deployments that already run Redis. Managed
equivalents may be added per cloud without touching module code.

**Consumers are idempotent by contract.** At-least-once is the delivery
guarantee; exactly-once is achieved by the consumer, and the contract test suite
for every consumer includes duplicate delivery.

Every module's manifest declares events published and consumed; the schemas live
in `core-contracts` as AsyncAPI and are versioned.

## Consequences

**Positive.** Module decoupling is real rather than nominal. Identical semantics
across every deployment shape. Replay from a dead-letter queue is a supported
operation, which matters for a system whose audit story depends on not losing
events.

**Negative.** One more component to operate in SaaS. At-least-once pushes
idempotency onto every consumer — deliberately, since the alternative is a bus
guarantee that does not survive adapter swaps.

**Negative.** Two adapters means two contract-test runs in CI. Cheap, and it is
the only way P3 stays true rather than aspirational.

## Alternatives considered

- **Kafka.** Excellent at scale; heavy to operate and to install air-gapped,
  and we do not have Kafka-scale volume. Revisit only if throughput demands it.
- **Postgres as the queue (`LISTEN`/`NOTIFY` plus an outbox).** Tempting given
  ADR-0002 — one fewer component. Rejected as the *default* because fan-out and
  durable consumer groups get awkward, but the transactional outbox pattern is
  still used to bridge writes into the bus atomically.
- **A managed cloud bus as the primary.** Violates P3.
