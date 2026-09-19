# Measuring — prove it worked

Do not take this bundle's word for it, or mine. Measure. Every step below produces a
number or a pass/fail you can check yourself.

---

## Step 0 — Baseline BEFORE installing

This is the step people skip, and without it nothing later means anything.

```bash
npx ccusage@latest daily     # record the last 7 days
```

Then in Claude Code, in the project, on a **fresh** session:

```
/context
```

Record the startup token count — everything loaded before you type a word. Typically
20k–30k. Write both numbers down.

---

## Step 1 — Install

```bash
./install.sh --profile balanced /path/to/project
```

Fill in `codebase-overview/SKILL.md` and trim `CLAUDE.md`. **The bundle does almost
nothing until you do this** — an empty overview saves zero tokens.

---

## Step 2 — Re-measure startup

`/context` on a fresh session again. Compare to Step 0.

What you're looking for: a lean `CLAUDE.md` plus path-scoped rules should show a
smaller and better-attributed baseline. `/context` breaks it down by system prompt,
CLAUDE.md, MCP servers, subagents, and skills — so you can see exactly what is
expensive.

> If your baseline went **up**, that's informative, not a failure. The likely cause is
> too many installed skills. Prune, and re-measure.

---

## Step 3 — Verify hooks are live

```
/hooks
```

Expect `filter-test-output.sh` and `filter-build-output.sh` under **PreToolUse**, and
`verify-before-done.sh` under **Stop**.

Then prove the rewrite actually fires:

```bash
claude --debug-file ./claude-debug.txt
# ask Claude to run the test suite, then:
grep "modified tool input keys" claude-debug.txt
```

A line listing `command` is proof the hook rewrote the call.

---

## Step 4 — Verify the Stop gate blocks (requirement: never miss anything)

The acceptance test for the whole quality half of this system:

1. Deliberately break one test.
2. Ask Claude to finish the work.
3. **Claude must refuse to declare it done**, and should report the failure.

If Claude says "done" anyway, the gate is not wired up. Check:
- `.claude/hooks/verify-before-done.sh` is executable (`ls -l`)
- `TOKENSAVER_VERIFY` is not set to `off`
- the project has a `test` or `lint` script the hook can detect

Undo the break afterwards.

---

## Step 5 — Verify subagent isolation

Ask Claude to run the suite via the `test-runner` subagent. Then `/context`.

The main conversation should **not** contain the full test output — only the summary.
That difference is the saving.

---

## Step 6 — Verify memory

1. Correct Claude on something specific ("we use pnpm, not npm").
2. Later, in a **new** session, run `/memory`.
3. Confirm a `feedback` entry exists, and check `MEMORY.md` is within its 200-line limit.

Anything past 200 lines / 25KB is silently dropped at session start, so this is a real
budget, not a guideline.

---

## Step 7 — Verify worktrees

```bash
claude --worktree test-isolation
```

Confirm:
- the worktree exists under `.claude/worktrees/test-isolation/`
- `.env` was copied in (that's `.worktreeinclude` working)
- Claude is **blocked** from editing files in the main checkout

Then exit and let it clean up.

---

## Step 8 — Verify the Definition of Done end to end

Build one small real feature through the system. Then check each gate produced an
actual artifact:

- [ ] tests exist **and** at least one covers a failure path
- [ ] docs changed in the same commit as the code
- [ ] `code-reviewer` ran, findings addressed or explicitly waived
- [ ] CI is green

**Any gate that produced nothing is decorative.** Fix it or delete it — a checklist
with dead entries teaches everyone to ignore the live ones.

---

## Step 9 — Measure for real

Work normally for a week. Then:

```bash
npx ccusage@latest daily
```

Compare against Step 0. Also check, in Claude Code:

- `/usage` — attributes recent usage to skills, subagents, and individual MCP servers,
  and flags behaviors (long context, cache misses) over 10% of your total. The
  `Prompt cache (main)` line shows your cache hit rate and why misses happened.
- `/insights` — analyzes recent sessions and reports friction points.

---

## Step 10 — The quality gate (non-negotiable)

Over that same week:

- tests and lint stayed green
- code review findings did **not** increase
- no rise in "Claude did the wrong thing" moments

**If quality dropped, revert the aggressive profile first**, then re-measure. Token
savings that cost correctness are not savings.

---

## What good looks like

| Signal | Where | Direction |
|---|---|---|
| Startup context | `/context` | down |
| Daily tokens | `ccusage` | down |
| Cache hit rate | `/usage` | up |
| Long-context / cache-miss flags | `/usage` | absent |
| Test suite | CI | green |
| Review findings | `code-reviewer` | flat or down |
| Repeated mistakes | your judgment | down |

If tokens fell and the last two rows got worse, the system is failing at its actual
job. Back the aggressive settings out.
