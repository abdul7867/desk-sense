---
name: ship-it
description: Walks the project's Definition of Done before declaring work complete. Use when finishing a feature, fix, or refactor, or whenever about to tell the user something is done.
---

# Ship it — the Definition of Done walk

Run this before saying a piece of work is finished. The Stop hook enforces the
mechanical parts (lint, typecheck, tests); this skill covers what a script cannot check.

## 1. Read the gate

Read `DEFINITION-OF-DONE.md` at the project root. That file wins over this one — it
is the project's own standard. If it does not exist, use the defaults in section 3.

## 2. Check each gate honestly

Go gate by gate. For each: state PASS, FAIL, or N/A with one line of evidence.

Evidence means a fact, not an intention. "Added tests in `auth.test.ts:40-72`
covering the expired-token path" is evidence. "Tests added" is not.

## 3. Default gates

- **Implemented** — edge cases and error paths, not only the happy path
- **Tested** — unit tests for logic, integration tests for seams, and at least one
  test for the *failure* path. A bug fix without a test that fails before the fix
  is not a fix, it is a guess.
- **Tests pass** — the full suite, locally
- **Lint + typecheck** — clean, with no new suppressions
- **Documented** — README/API docs updated *in this same change*; comments where
  intent is not obvious from the code
- **Errors handled** — no silent catches; failures are actionable to the user
- **Secure** — no secrets committed, inputs validated at the boundary, authz
  checked on new endpoints
- **Accessible** (UI changes) — keyboard reachable, labelled, sufficient contrast
- **Reviewed** — run the `code-reviewer` subagent; address or explicitly waive findings
- **CI green** — the pipeline agrees, not just this machine
- **Overview current** — if the architecture moved, update
  `.claude/skills/codebase-overview/SKILL.md`. A stale map costs tokens every
  future session.

## 4. Report

Give the user the gate summary, then either "done" or exactly what is outstanding.

## Rules

- **Never mark a gate PASS you did not verify.** Run the command, read the file. An
  unverified PASS is the single most expensive thing in this system — it defeats the
  entire point of the gate and the user stops trusting all of it.
- If a gate genuinely does not apply, mark it N/A and say why in four words.
- If you cannot meet a gate, say so plainly and say what it would take. A blocked
  gate reported honestly is a good outcome; a skipped gate is not.
- Do not soften the summary. If three gates fail, lead with that.
