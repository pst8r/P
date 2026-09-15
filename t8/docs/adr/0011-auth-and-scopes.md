# ADR-0011: Auth — Entra OIDC, on-behalf-of, and per-action least-privilege scopes

- **Status:** Proposed (pending PLAN.md approval)
- **Date:** 2026-09-15

## Context

The buyer is an M365 enterprise; Entra ID is already the identity plane. T8 has
three distinct identity problems, and conflating them is how service desks
become privilege-escalation paths:

1. **Who is the employee?** — resolving a Teams or email sender to a real
   directory identity, reliably enough to act on their behalf.
2. **Who is the analyst/admin?** — authenticating operators into the workspace
   and Admin surfaces with role-appropriate authority.
3. **Under whose authority does an action execute?** — the agent's own service
   principal, or the user's delegated permission.

PROMPT.md §7 requires scopes to follow least privilege and be documented per
action.

## Decision

**Employees and operators authenticate via Entra ID OIDC.** Channel identity
(Teams user id, verified email sender) is *resolved* to a directory identity and
the resolution itself is recorded; an unresolvable or ambiguous identity
escalates to a human rather than proceeding on a guess (P10).

**Two execution identities, chosen per action, never per convenience:**

- **On-behalf-of (delegated)** where the action is genuinely the user's own and
  the directory can authorize it directly.
- **Service principal (application)** for actions requiring privilege the user
  does not hold — which is most T2 work. These execute **only** after the
  approval chain and policy gate have authorized them (ADR-0013), and the audit
  event records both the service principal and the `on_behalf_of` human.

**Scopes are declared per action in the action catalog, not per application.**
Each catalog entry names the exact scopes it needs. The union of scopes across
enabled actions is what a tenant's admin consents to, and the consent screen is
therefore explainable action by action. Adding a scope is a reviewed change with
a documented justification.

**Scope grants are auditable and revocable per tenant.** Disabling an action
class removes its tools from the registry projection (ADR-0008) and, where
possible, narrows the consented scope set.

**Per §13 Q3, the exact scope list for the first five actions goes to the design
partner's security team in week one.** If a required scope is a non-starter in
that organization, T2 autonomy is not available there and the roadmap says so
plainly rather than discovering it in Phase 5.

## Consequences

**Positive.** Least privilege is a property of the catalog, so it is reviewable
as data rather than as code. The dual-identity record makes "who could have
stopped this" (§8) answerable. Tenant-level revocation is a real kill switch.

**Negative.** Per-action scope declaration is more bookkeeping than one broad
app registration, and the consent conversation with each customer is longer.
This is the correct trade: the shorter conversation is the one where you ask for
`Directory.ReadWrite.All` and lose the deal.

**Risk.** Identity resolution from a channel is the weak link — display names
collide, shared mailboxes exist, external senders spoof. Resolution confidence
is explicit, and low confidence escalates.

## Alternatives considered

- **Single broad application registration.** Far simpler; fails least privilege,
  makes tenant-level revocation all-or-nothing, and is the likeliest cause of a
  security review failing. Rejected.
- **Delegated-only.** Safest, and insufficient: most T2 actions require
  privilege the requesting employee does not have.
- **Application-only.** Simplest to implement; loses the delegated-authority
  distinction that makes the audit trail meaningful. Rejected.
