---
name: memory-promotion
description: The weekly ritual that turns Claude's machine-local auto memory into durable, committed project knowledge. Use when asked to review memory, promote lessons, run the weekly review, or when auto memory has grown large.
---

# Memory promotion ritual

Claude Code's auto memory is **machine-local and never synced**. Everything it learns
about your corrections lives in one directory on one machine, and disappears with it.
This ritual moves the durable parts into the repo, where they survive machines,
teammates, and reinstalls.

Run it weekly, or whenever `MEMORY.md` approaches its limits. It costs tokens, so it
is a ritual, not a per-session habit.

## 1. Read the memory index

Auto memory lives at `~/.claude/projects/<project>/memory/`. Read `MEMORY.md` — it is
an index, one line per memory, and only its first **200 lines / 25KB** load at session
start. Anything past that is silently dropped, so keeping it tight is not cosmetic.

Then read the `feedback_*.md` topic files. Those are the corrections the user gave —
the raw material for "never repeat the same mistake".

## 2. Sort each entry

For every memory, decide one of four:

| Decision | When | Where it goes |
|---|---|---|
| **Promote to a rule** | It is a hard convention that should bind everyone, always | `.claude/rules/<scope>.md` — path-scoped so it costs nothing when irrelevant |
| **Promote to a lesson** | A real mistake was made and should not recur, but it is not a mechanical rule | `docs/lessons.md` |
| **Promote to the overview** | It is architectural — where something lives, how data flows | `.claude/skills/codebase-overview/SKILL.md` |
| **Leave it** | Genuinely personal or machine-specific (editor, local paths, your preferences) | stays in auto memory |

Two things to be strict about:

- **A preference is not a lesson.** "User prefers pnpm" is a rule. "We shipped a
  migration without a rollback and lost an afternoon" is a lesson. Do not inflate the
  ledger with trivia — a `lessons.md` nobody reads protects nothing.
- **If it is derivable from the code, it does not belong in memory at all.** Claude
  already skips these when writing auto memory. Do not reintroduce them by hand.

## 3. Write the promotions

Append to `docs/lessons.md` in its existing format. One line per lesson, detail
linked out. If a lesson makes an existing rule clearer, edit the rule instead of
adding a duplicate.

## 4. Prune

After promoting, tell the user which entries are now redundant in auto memory, and
offer to remove them. Do not delete memory files without asking — they are the user's
notes, not yours.

Report the final `MEMORY.md` line count so its budget stays visible.

## 5. Report

```
REVIEWED: <n> memories
PROMOTED: <n> rules, <n> lessons, <n> overview updates
LEFT:     <n> (machine-local)
MEMORY.md: <n>/200 lines
```

## Rule

Promote only what you actually read. Do not invent lessons to make the report look
productive — a padded ledger is how this system rots.
