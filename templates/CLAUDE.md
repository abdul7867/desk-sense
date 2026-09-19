# <Project name>

<!--
  TOKEN BUDGET: keep this file under 200 lines. It loads into EVERY session, so
  every line is paid for on every request, forever.

  Rule of thumb: if Claude can derive it by reading the code, delete it.
  If it is workflow detail, move it to a skill (loads on demand).
  If it is path-specific, move it to .claude/rules/ (loads only for those files).
-->

One sentence on what this project is.

## Commands

```bash
<install>
<dev>
<test>
<lint / typecheck>
<build>
```

## Architecture

See `.claude/skills/codebase-overview` — invoke it instead of exploring the tree.
Keep that skill current; a stale map costs tokens every session.

## Non-negotiables

- Definition of Done lives in `DEFINITION-OF-DONE.md`. Work is not finished until
  every gate passes. Run the `ship-it` skill before declaring anything done.
- Every bug fix ships with a test that fails before the fix.
- Docs change in the same commit as the code they describe.
- Never commit secrets. Read them from the environment.

## Working agreements

- Delegate verbose work to subagents: `test-runner` for suites, `log-digger` for
  logs, `codebase-scout` for "where is X". Their output stays in their own context.
- Use `code-reviewer` before finishing anything non-trivial.
- Record durable mistakes in `docs/lessons.md`. Read it when touching an area it
  mentions.

## Compact instructions

When compacting, preserve: the current task and its acceptance criteria, file paths
already identified, decisions made and why, and any failing test output. Drop
resolved tangents and superseded approaches.
