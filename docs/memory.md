# Memory — the two-layer design

Goal: never explain the codebase twice, and never repeat a mistake. On a Pro plan,
with the context cost kept honest.

---

## Why two layers

Claude Code ships a **built-in auto memory** system that already does most of this,
and is already token-smart. Most people don't know it exists.

But it has one property that rules it out as the whole answer: **it is machine-local
and never synced.** Everything Claude learns lives in one directory on one machine and
disappears with it. So we pair it with a committed layer that travels with the repo.

| | Layer 1: Auto memory | Layer 2: Repo-tracked |
|---|---|---|
| Written by | Claude, automatically | You and Claude, deliberately |
| Lives in | `~/.claude/projects/<project>/memory/` | The git repo |
| Survives | This machine only | Machines, teammates, reinstalls |
| Good for | Your preferences, recent corrections, in-flight context | Architecture, conventions, durable lessons |

---

## Layer 1 — Auto memory (built-in)

On by default. Claude writes four kinds of note, tagged by `type`:

- **`user`** — your role, expertise, working preferences
- **`feedback`** — *corrections you give Claude and approaches you confirm* ← **this is
  the "never repeat the same mistake" engine, and it ships in the box**
- **`project`** — ongoing work, deadlines, decisions not derivable from code or git
- **`reference`** — where to find things outside the project

### How it stays cheap

```
~/.claude/projects/<project>/memory/
├── MEMORY.md            # index — only the first 200 lines / 25KB load at session start
├── user_role.md         # topic file — loaded ON DEMAND
└── feedback_testing.md  # topic file — loaded ON DEMAND
```

That split is the whole trick. The index is small and always present; detail is read
only when relevant. Content past 200 lines / 25KB is **silently dropped** at session
start, so keeping the index tight is a real budget, not style advice.

### Things worth knowing

- **All worktrees of a repo share one memory directory.** Memory and worktrees compose
  cleanly — you don't lose context by working in a worktree.
- **It's excluded from the session-transcript cleanup sweep**, so it persists while
  transcripts are pruned.
- **Claude deliberately skips anything derivable from the codebase** — architecture,
  file paths, how a bug was fixed. So auto memory alone will *not* stop codebase
  re-explanation. That's Layer 2's job.
- **Subagents don't inherit the main conversation's auto memory** (except forks).

### Controls

```
/memory                     # browse, edit, toggle
```
```json
{ "autoMemoryEnabled": false }          // per project
{ "autoMemoryDirectory": "~/my-mem" }   // relocate
```
```bash
CLAUDE_CODE_DISABLE_AUTO_MEMORY=1
```

---

## Layer 2 — Repo-tracked knowledge

Committed, portable, reviewable.

| File | Holds | Loads |
|---|---|---|
| `CLAUDE.md` | Essentials only, under 200 lines | Every session |
| `.claude/rules/*.md` | Path-scoped conventions | **Only when matching files are touched** |
| `.claude/skills/codebase-overview/SKILL.md` | Architecture map | On demand |
| `docs/lessons.md` | Durable mistakes and their rules | When you or Claude read it |
| `docs/decisions.md` | Why things are the way they are | When you or Claude read it |

### The anti-re-explanation weapon

`codebase-overview` is the highest-value file in this bundle. Without it, Claude
rebuilds your mental model by reading files — thousands of tokens, every session,
forever. With it, one on-demand read replaces all of that.

Two rules:

1. **Fill it in.** An empty template saves nothing.
2. **Keep it current.** A stale map is *worse* than none, because Claude trusts it.
   When `codebase-scout` reports a mismatch, treat that as a bug.

---

## The promotion ritual — what makes it self-improving

Weekly, or when `MEMORY.md` gets long, run the `memory-promotion` skill. It reads auto
memory and sorts each entry:

| Decision | When | Destination |
|---|---|---|
| Promote to a **rule** | A hard convention that should always bind | `.claude/rules/<scope>.md` |
| Promote to a **lesson** | A real mistake that shouldn't recur | `docs/lessons.md` |
| Promote to the **overview** | Architectural: where things live, how data flows | `codebase-overview/SKILL.md` |
| **Leave it** | Genuinely personal or machine-specific | stays in auto memory |

That is the loop that turns machine-local learning into repo-permanent knowledge.

**A preference is not a lesson.** "Prefers pnpm" is a rule. "We shipped a migration
without a rollback and lost an afternoon" is a lesson. A padded ledger is how this
system rots — nobody reads a `lessons.md` full of trivia, and then nobody reads the
one entry that mattered.

---

## The token guardrail

Everything here except topic files is **startup cost, paid on every request**.

| Source | Budget |
|---|---|
| `MEMORY.md` | 200 lines / 25KB (hard limit — overflow is dropped) |
| `CLAUDE.md` | under 200 lines (guidance) |
| `.claude/rules/*` | only unscoped rules count at startup — **scope them** |
| Topic files, skills | on demand, ~0 at startup |

Check the real number with `/context`, not by guessing. Memory that grows unbounded is
a slow leak: it costs a little more every session, and nothing ever tells you.

---

## Honest limits

- **Not synced across machines.** New laptop, empty auto memory. Layer 2 is what
  carries over — one reason to actually commit it.
- **Memory is context, not enforcement.** Claude Code is explicit about this: CLAUDE.md
  and memory are treated as context, and a model can reason past context. To make
  something *impossible*, use a hook. That's why `verify-before-done.sh` exists.
- **The ritual needs a human.** A few minutes a week. Fully autonomous
  self-improvement is not something I can honestly promise you today.
