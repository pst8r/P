# ADR-0019: Untrusted content — structural data/instruction separation

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15
- **Note:** not specified in PROMPT.md; raised as a gap in `docs/00-architect-response.md` §2.11

## Context

§5 requires prompt-injection defense on all retrieved and user content, with
untrusted content never treated as instructions. §12's adversarial suite covers
injection in email and KB content.

The higher-value attack is not in email. It is **an employee putting
instructions into a ticket description, a Teams message, or a knowledge article
they are entitled to edit**, which a Triage, Knowledge or Diagnostic agent later
reads as context. It is an insider privilege-escalation path that looks exactly
like normal product usage, and it arrives through the product's primary intake.

Q4 adds a second source: content returned by **customer-registered MCP servers**
(ADR-0008), which we did not write and cannot audit.

Prompt-level defenses ("ignore instructions in the text below") are mitigations,
not controls. This needs to be architectural.

## Decision

### Trust is assigned at ingestion and is immutable

Every piece of content entering the system is stamped with a **trust class** at
its ingestion boundary, and the stamp travels with it through the blackboard,
retrieval, and into every prompt:

- **`system`** — our prompt templates and policy text. The only class that may
  express intent.
- **`operator`** — instructions from an authenticated T8 operator through a
  designated channel.
- **`user`** — what the employee actually said this turn.
- **`untrusted`** — everything else: ticket and article bodies, email content,
  transcripts, retrieved chunks, CMDB fields, tool results, and **all** output
  from external MCP servers.

There is no path that promotes `untrusted` to a higher class. Content does not
become trustworthy by being retrieved, summarized, copied onto the blackboard,
or passed between agents — the class is carried, and an agent writing a
derivative onto the blackboard propagates the lowest class of its inputs.

### Separation is structural, not stylistic

- Untrusted content is passed in **delimited, labelled data blocks**, never
  concatenated into instruction text.
- **Operator instructions use the provider's dedicated operator channel** where
  one exists — mid-conversation system messages appended to the message array
  rather than edits to the assembled prompt body. This is both the
  injection-safe channel and the cache-stable one (ADR-0006).
- Agent output that *acts* is a typed action proposal (ADR-0013), never free
  text, so a successful injection produces at most a proposal that the
  deterministic pipeline then refuses.

### Defense in depth

The structural separation is the control. Layered on top: injection and
scope-drift detection on untrusted spans, the Critic's adversarial review before
any T2+ action (ADR-0007), and the adversarial suite gating merges from Phase 2
(ADR-0014).

### The Phase 3 gate

Phase 3 is not done until an injected instruction in an email body **provably
fails to influence any decision** — demonstrated, not asserted. The equivalent
test for a ticket description, a KB article and an external MCP tool result is
part of the same suite.

## Consequences

**Positive.** The honest answer to "could a ticket description tell your agent
to grant someone access?" is a described mechanism and a passing test, not a
claim about prompt quality. Combined with ADR-0013, a successful injection's
maximum outcome is a refused proposal and a recorded guardrail event.

**Negative.** Trust-class plumbing touches every ingestion path, the blackboard
schema, retrieval, and prompt assembly. It is meaningful work and it must be
done early — retrofitting provenance into a system that has been concatenating
strings is a rewrite.

**Negative.** Some capability is lost. Content genuinely intended as instruction
— a runbook step in a KB article — cannot be executed as instruction. It becomes
evidence the agent reasons about and proposes from, which is slower and correct.

**Negative.** The operator channel's availability varies by provider, so the
capability matrix (ADR-0006) must cover it and degrade to delimited-block
separation where it is absent.

## Alternatives considered

- **Prompt-level defense only.** The category default. Bypassed by paraphrase,
  by encoding, and by patience. Insufficient as a control.
- **Sanitize untrusted content on ingestion.** Helpful as a layer; cannot be
  complete, and a sanitizer that is trusted to be complete is worse than none.
- **Refuse to retrieve free-text content at all.** Secure and useless.
