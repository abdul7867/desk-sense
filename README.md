# Tokensaver

A token-saving, memory-backed, production-grade setup for **Claude Code on the Pro
($20) plan** — without trading away code quality.

Clone it, run `install.sh` against a project, install a short list of vetted external
skills, and measure the difference.

---

## The honest framing, first

This is **not** purely a token *reduction* system. It is a token *reallocation* system.

It strips waste — re-exploring your codebase every session, unfiltered test logs,
stale context, repeated mistakes — and spends the reclaimed budget on rigor: tests,
docs, review, verification. Production-grade discipline costs *more* tokens per task,
not fewer. Savings are what make it affordable on $20.

If a repo promises 90% savings *and* better code with no tradeoff, it hasn't measured
either. This README gives you the real numbers and their sources.

---

## Quick start

```bash
git clone <this-repo> tokensaver
cd tokensaver
./install.sh --dry-run /path/to/your/project   # see what it would do
./install.sh /path/to/your/project             # balanced profile (default)
```

Then, the part that actually matters:

1. **Fill in `.claude/skills/codebase-overview/SKILL.md`.** This is the single biggest
   token saver in the bundle. An empty one saves nothing.
2. **Trim `CLAUDE.md`** to your project. Keep it under 200 lines.
3. **Edit `.claude/rules/*.md`**, delete what doesn't apply.
4. **Baseline before judging:** `npx ccusage@latest daily`.

Profiles: `--profile balanced` (default) or `--profile aggressive`. See
[Profiles](#profiles).

---

## What gets installed

| Path | What it does |
|---|---|
| `.claude/settings.json` | Sonnet default, Haiku subagents, hooks and status line wired up |
| `.claude/hooks/situation-report.sh` | **`SessionStart`** — injects branch, test status, matching lessons and TODOs. ~170 tokens, replaces thousands of orientation tokens |
| `.claude/statusline/cockpit.sh` | Context %, cost, and **prompt-cache countdown**. Runs outside the context window — zero tokens |
| `.claude/hooks/block-hazards-bash.sh` | **Denies** secret commits, force-push to the default branch, destructive deletes |
| `.claude/hooks/block-hazards-write.sh` | **Denies** hand-edited lockfiles, writes into `node_modules`, edits to generated files |
| `.claude/audit-context.sh` | Reports what this setup costs you at startup |
| `.claude/agents/test-runner.md` | Runs tests in its own context, returns **only failures** |
| `.claude/agents/log-digger.md` | Greps big logs, returns matches with context |
| `.claude/agents/codebase-scout.md` | Read-only "where is X" — returns `file:line`, not file dumps |
| `.claude/agents/code-reviewer.md` | Reviews the diff against your Definition of Done |
| `.claude/agents/refactorer.md` | Multi-file refactors in an isolated git worktree |
| `.claude/rules/frontend.md` | TS/React conventions — **loads only on frontend files** |
| `.claude/rules/backend.md` | Python conventions — **loads only on Python files** |
| `.claude/hooks/filter-test-output.sh` | Rewrites test commands so a green run costs ~0 tokens |
| `.claude/hooks/filter-build-output.sh` | Same for builds and typechecks |
| `.claude/hooks/verify-before-done.sh` | **Stop gate** — refuses "done" while tests/lint fail |
| `.claude/skills/codebase-overview/` | Architecture map — stops re-exploration |
| `.claude/skills/ship-it/` | Walks the Definition of Done before finishing |
| `.claude/skills/memory-promotion/` | Weekly ritual: machine-local memory → committed knowledge |
| `CLAUDE.md`, `DEFINITION-OF-DONE.md` | Lean project instructions and the quality gate |
| `docs/lessons.md`, `docs/decisions.md` | Mistake ledger and decision log |
| `.worktreeinclude` | Carries `.env` into every new worktree |
| `.github/workflows/ci.yml` | The backstop |

Nothing is overwritten without `--force`, which backs up first. Re-running is safe.

---

## The three things that make it more than a config bundle

### 1. Claude opens oriented, not blind

A `SessionStart` hook injects a situation report: branch, recent commits, uncommitted
files, last verification result, **lessons matching the files you're touching**, and
TODO markers in changed files.

Measured at **~171 tokens** in normal use and **~231** under adversarial load (60
changed files, 100 lessons) — it's hard-capped. It replaces the thousands of tokens
Claude would otherwise spend working out where things stand.

It's also what finally makes `docs/lessons.md` get *read*. A ledger nobody reads
protects nothing.

```bash
TOKENSAVER_SITREP=off              # disable
TOKENSAVER_SITREP_MAX_LINES=25     # tighten the cap
```

### 2. The cache countdown

The status line shows something you currently can't see:

```
Sonnet  myapp  (feature-auth)
████████████░░░░░░░░ 64% ctx  $2.15  cache 4m left (118k to rebuild)  88% hit
```

On a subscription your prompt cache TTL is **one hour**. When it lapses, your next
message reprocesses the entire conversation. That's the largest hidden cost on the Pro
plan and right now you simply pay it without knowing.

Claude Code reports both `expires_at` and `recache_tokens_if_cold`, so the line turns
it into a decision: finish the thought now, or accept the rebuild. **Costs zero
tokens** — status lines run outside the context window.

### 3. Hazards are refused, not discouraged

`PreToolUse` deny hooks block four things outright:

| Blocked | Not blocked |
|---|---|
| Committing `.env`, keys, or a staged diff containing a live-looking credential | Ordinary commits |
| Force-push / `reset --hard` on the **default** branch | `--force-with-lease`, force-push to a feature branch |
| Hand-editing lockfiles or `@generated` files | `package.json`, normal source |
| `rm -rf` outside the project or on `$HOME`/`/` | `rm -rf ./dist`, anything in `/tmp` |

Scope is deliberately narrow. A gate that fires on things you legitimately wanted is a
gate you disable — and then it protects nothing. Verified against 27 block/allow cases.

```bash
TOKENSAVER_ALLOW_HAZARD=1 <command>   # deliberate override
```

---

## Holding the system to its own standard

```bash
.claude/audit-context.sh
```

```
Loaded every session
  CLAUDE.md                             399
  rules (unscoped)                        0
  skill descriptions (3)                172
  agent descriptions (5)                244
  MEMORY.md index                         0
  situation report (injected)            22
  SUBTOTAL (bundle)                     837

Loaded only when needed (costs nothing at rest)
  skill bodies (3)                     1913
  rules (path-scoped, 2)                733   only on matching files

  Verdict: lean
```

**The whole bundle costs ~837 tokens per session; 2,646 more are deferred until
needed.** It flags a bloated `CLAUDE.md`, rules missing a `paths:` key, and a
`MEMORY.md` past its 200-line limit (where the overflow is silently dropped).

This system tells you every component must prove it pays for itself. This is the script
that holds it to that. Run it before adding anything.

---

## External skills to install

Deliberately short. **Every installed skill's description sits in your context
permanently** (~100 tokens each), so a 380-skill mega-repo is a net loss on Pro.

```bash
# Official marketplace is auto-registered. Superpowers lives there.
/plugin install superpowers@claude-plugins-official

# Official Anthropic skills
/plugin marketplace add anthropics/skills

# Frontend quality (skip if you don't write React)
npx skills add vercel-labs/agent-skills --agent claude-code

# Security review (optional, for security-sensitive work)
npx skills add trailofbits/skills --agent claude-code

# Measurement — not a skill, a CLI
npx ccusage@latest daily
```

### Why Superpowers

`obra/superpowers` (MIT, Jesse Vincent) was accepted into Anthropic's **official**
plugin marketplace in January 2026. It supplies `test-driven-development`,
`systematic-debugging`, `writing-plans`, `requesting-code-review`, and
`verification-before-completion` — the last of which is precisely the
"don't-miss-anything" requirement. Dormant cost is ~1,400 tokens thanks to
progressive disclosure.

**It will increase tokens per task.** Planning, test-first, and self-review are extra
work. It earns its cost by preventing the expensive failure — forty minutes down the
wrong path — not by being cheap.

---

## Profiles

| | balanced (default) | aggressive |
|---|---|---|
| Model / subagents | sonnet / haiku | sonnet / haiku |
| Output-filter + Stop hooks | on | on |
| Path-scoped rules, memory, worktrees | on | on |
| Telemetry + non-essential traffic | default | disabled |
| MCP output cap | default | 10,000 tokens |
| Session retention | 30 days | 14 days |

### On "caveman" and output compression

The `caveman` skill is widely cited at **65–90% token reduction**. Those figures are
from **chat-style Q&A, not coding**. The one independent coding benchmark — JetBrains,
86 real tasks — measured **8.5% fewer output tokens with no detectable quality
change**.

So it is **not** enabled by either profile. It's worth adding per-session for
non-implementation work (research, triage, Q&A). Keep it away from sessions where
Claude's reasoning-in-prose is load-bearing:

```bash
npx skills add JuliusBrussee/caveman -g
```

---

## What was rejected, and why

Because "proven only" means saying no to things.

| Repo | Claim | Why rejected |
|---|---|---|
| `valorisa/Claude-Skills` (rescue-tokens) | "90% verbosity reduction", "$750/mo → $100/mo" | Inspected the repo: **no test files, no CI, no transcripts, no benchmark data.** The "TDD-tested" framing is markdown *describing* TDD, not executed tests. ~13 stars, single maintainer. |
| `KINGSTAR-OMEGA/claude-token-optimizer` | "Zero-English JSON-only compiler mode" | Forcing JSON-only output for coding trades correctness for tokens. No evidence offered. |
| "Awesome toolkit" mega-repos (135 agents / 380 skills) | Breadth | Actively harmful on Pro — every skill description is permanently resident in context. |
| `ENABLE_TOOL_SEARCH` env var | "Defers MCP tool loading" | All over 2026 blog posts, **not in the current env-var docs.** MCP tool definitions are deferred **by default** now. Stale advice. |

---

## How the pieces map to what you asked for

| Requirement | Mechanism |
|---|---|
| Save tokens | Filter hooks, subagent isolation, path-scoped rules, lean CLAUDE.md, model routing, MCP hygiene |
| Never compromise quality | Superpowers TDD + `code-reviewer` + Definition of Done + CI |
| Never miss anything | Built-in task tracking → `ship-it` skill → **Stop hook** (mechanical enforcement) → CI |
| Never repeat a mistake | Auto memory (`feedback` type) → `docs/lessons.md` → `.claude/rules/` |
| Persistent memory | Two layers — see [docs/memory.md](docs/memory.md) |
| Git worktrees | `claude --worktree`, `.worktreeinclude`, `refactorer` agent with `isolation: worktree` |
| Production-grade | `DEFINITION-OF-DONE.md` enforced at three levels |

Details: [docs/research.md](docs/research.md) · [docs/memory.md](docs/memory.md) ·
[docs/measuring.md](docs/measuring.md)

---

## Worktrees — read this before going parallel

```bash
claude --worktree feature-auth     # isolated checkout, branch worktree-feature-auth
```

Claude Code *hard-blocks* edits, command working directories, and git redirects that
escape into the main checkout. Real enforcement, not convention.

**The Pro-plan warning:** worktrees give isolation, but parallel Claude sessions
multiply token burn — each carries its own full context, and Anthropic measures agent
teams at roughly **7× a standard session**. On $20, use worktrees for **isolation and
clean context-switching, mostly serially** — not four Claudes at once. Plugins,
permission approvals, and auto memory are all shared across a repo's worktrees, so
serial use costs you almost nothing.

---

## Habits that matter more than any config

- **`/clear` between unrelated tasks.** Free. `/compact` is itself a large request
  because it reads the whole conversation first.
- **Work in focused blocks.** The subscription prompt-cache TTL is **1 hour**. Your
  first message after a longer gap reprocesses your full context at full price.
- **`/context` when a session feels heavy.** It breaks down exactly what is loaded.
- **`/usage`** attributes recent usage to skills, subagents, and individual MCP
  servers, and flags any behavior over 10% of your total.
- **`/mcp`** — disable servers you aren't using.
- **`/insights`** weekly — analyzes your recent sessions and reports friction points.

---

## Limits — the parts I won't oversell

1. **Not autonomous self-improvement.** The memory-promotion ritual and `/insights`
   review need you, roughly weekly, for a few minutes. Anything claiming hands-off
   self-improvement is in the same genre as the repos rejected above.
2. **Auto memory is machine-local and never synced.** That's exactly why the
   repo-tracked layer exists. Memory "at any cost" is achievable *in the repo*, not
   in Claude's head.
3. **Pro has a real ceiling.** Production-grade discipline on a substantial app will
   hit the weekly cap. This buys headroom, not unlimited runway. If you're still
   capped twice a week after applying all of the above, the honest answer is
   **Max 5× ($100)** — not a cleverer prompt.

---

## Sources

Claude Code docs: [costs](https://code.claude.com/docs/en/costs) ·
[memory](https://code.claude.com/docs/en/memory) ·
[worktrees](https://code.claude.com/docs/en/worktrees) ·
[subagents](https://code.claude.com/docs/en/sub-agents) ·
[hooks](https://code.claude.com/docs/en/hooks) ·
[env vars](https://code.claude.com/docs/en/env-vars) ·
[plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)

[obra/superpowers](https://github.com/obra/superpowers) ·
[anthropics/skills](https://github.com/anthropics/skills) ·
[JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) ·
[ccusage](https://github.com/ccusage/ccusage) ·
[Firecrawl: 14 best Claude Code skills](https://www.firecrawl.dev/blog/best-claude-code-skills) ·
[Firecrawl: 12 ways to cut token consumption](https://www.firecrawl.dev/blog/claude-code-token-efficiency) ·
[Honest tradeoffs of Superpowers](https://www.joanmedia.dev/ai-blog/the-honest-tradeoffs-of-superpowers-token-costs-overkill-and-the-alternatives)

---

## Environment variables

| Variable | Effect |
|---|---|
| `TOKENSAVER_VERIFY` | `full` (default) / `quick` (lint+typecheck only) / `off` — the Stop gate |
| `TOKENSAVER_DOCS_GATE` | `on` (default) / `off` — the docs-with-code check |
| `TOKENSAVER_SITREP` | `on` (default) / `off` — the situation report |
| `TOKENSAVER_SITREP_MAX_LINES` | Cap on report length (default 40) |
| `TOKENSAVER_ALLOW_HAZARD` | `1` to override a hazard block for one command |

All default to the safe, enabled state. Each is a deliberate escape hatch, not a
setting you should need day to day.
