# Definition of Done

Work is finished when every applicable gate passes. Not "mostly" — every one.
Mark a gate N/A only when it genuinely does not apply, and say why.

The `ship-it` skill walks this list. The Stop hook enforces the mechanical gates.
CI is the backstop. Edit this file to fit the project; it is the project's standard,
not a suggestion from a bundle.

## Gates

- [ ] **Implemented** — edge cases and error paths handled, not only the happy path
- [ ] **Tested** — unit tests for logic, integration tests for seams, and at least
      one test covering the *failure* path. A bug fix includes a test that fails
      before the fix.
- [ ] **Tests pass** — the full suite, green, locally
- [ ] **Lint + typecheck clean** — no new suppressions, no new `any`
- [ ] **Documented** — README / API docs updated in this same change; comments where
      intent is not obvious from the code
- [ ] **Errors handled** — no silent catches; user-facing failures are actionable
- [ ] **Secure** — no secrets committed, inputs validated at the boundary, authz
      checked on new endpoints, dependencies free of known criticals
- [ ] **Accessible** (UI changes) — keyboard reachable, labelled, sufficient contrast
- [ ] **Performance sane** — no obvious N+1, no unbounded query, no blocking work on
      the request path
- [ ] **Reviewed** — `code-reviewer` subagent run; findings addressed or explicitly waived
- [ ] **CI green** — the pipeline agrees, not just this machine
- [ ] **Overview current** — if the architecture moved,
      `.claude/skills/codebase-overview/SKILL.md` was updated

## Waiving a gate

Waiving is allowed. Waiving *silently* is not. Write the waiver in the PR or commit
body: which gate, why, and what would un-waive it.
