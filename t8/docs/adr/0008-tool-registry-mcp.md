# ADR-0008: Tool registry — one registry, two surfaces; external MCP tools are T3 by default

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15
- **Settles:** part of PROMPT.md §13 Q4 ("connect with … MCP")

## Context

PROMPT.md §5 says "expose every integration as an MCP server so tools are
reusable across agents, across deployments, and by the customer's own agents."
The interop goal is right. Making *every internal* integration an MCP server is
not: it adds a process hop and a serialization boundary to the hot path, and it
introduces a place where tenant context and least-privilege scopes can be lost
or forged — precisely where ambiguity is unaffordable.

Q4 adds the other direction: T8 must **consume the customer's existing MCP
servers**, so that their prior integration investment becomes usable capability.
This is valuable and it is a new trust boundary. A customer-supplied MCP server
is code we did not write, reached over the network, returning content we must
not trust, wrapping systems whose blast radius we cannot assess.

## Decision

### One registry, two surfaces

The **tool registry** is the single source of truth for every tool, internal or
external. Per tool: schema, description, **risk tier**, required entitlement,
required scopes, idempotency key strategy, rate limit, rollback procedure, and
dry-run behaviour.

- **Internal surface:** agents call tools through a typed in-process interface.
  No network hop, no context re-serialization, tenant identity carried in-band.
- **External surface:** MCP servers are a **published projection** of the same
  registry entries, for the customer's own agents and third-party clients. One
  definition generates both, so risk metadata cannot drift between them.

**Every mutating tool implements dry-run and is idempotent under retry.** This
is a registration requirement; a tool without both is rejected at registration,
not at call time.

### Tool arguments are schema-valid by contract

Tool schemas are declared strict where the provider supports it, so arguments
arrive validated rather than parsed hopefully. Arguments are still re-validated
server-side — provider-side validation is a convenience, never the authorization
boundary (ADR-0013).

### Inbound MCP: customer-registered tools

A tenant may register their own MCP servers. Such tools are:

- **T3 by default — no autonomous execution, ever, until a human explicitly
  tiers them down for that tenant** with a recorded justification. We cannot
  assess the blast radius of a tool we did not write.
- **Entitlement-gated and tenant-scoped.** Registration binds the server to one
  tenant; its tools are invisible to every other tenant and to agents lacking
  the entitlement.
- **Treated as untrusted content sources.** Everything returned is data, never
  instruction (ADR-0019).
- **Separately budgeted and rate-limited**, with failures degrading to escalation
  rather than retry storms (P10).
- **Audited identically to internal tools** — same AI Decision Record fields,
  plus the external server identity.

### Tenant and scope propagation

Tenant identity and the caller's scope set propagate on every tool invocation on
both surfaces, and are re-derived server-side rather than trusted from the
request. The MCP binding's propagation design is the security-sensitive part of
this ADR and gets its own threat model and test suite in Phase 5.

### Entitlement gating is visibility, not rejection

Per §4: a disabled module's tools are **invisible** to agents — absent from the
registry projection the agent sees — not present-and-rejected. An agent that
cannot see a tool cannot plan around it, be socially engineered toward it, or
leak its existence.

## Consequences

**Positive.** No tenant-context loss on the hot path. Q4's BYO-tools requirement
is met without handing autonomy to third-party code. The customer's own agents
get a genuine, documented tool surface — a real differentiator against products
that keep integrations internal.

**Negative.** Two transports to keep in sync. Mitigated by generating both from
one definition and contract-testing the projection.

**Negative.** T3-by-default will frustrate customers who want their own tools
automated immediately. This is the correct default and the tier-down path is
explicit, per tenant, and recorded. We will be asked to relax it; the answer is
the documented tier-down, not a global default change.

## Alternatives considered

- **MCP for everything, internal included.** Maximum uniformity; pays a process
  hop per tool call and weakens the tenant-context guarantee. Rejected.
- **Internal-only tools, no MCP surface.** Simplest and most secure; forecloses
  Q4's interop requirement and a real differentiator. Rejected.
- **Trust customer MCP tools at their declared tier.** Rejected outright: a
  tool's declared risk tier is an assertion by its author, and autonomy granted
  on an assertion is how false-action incidents happen.
