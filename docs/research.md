# Research — what was evaluated, and on what evidence

Research date: **September 2026**. Everything below was checked against current
Anthropic documentation or the repository itself, not from memory. Where a popular
claim didn't survive checking, that's recorded too.

---

## Selection criteria

1. **Proven** — an independent benchmark, official adoption, or large verifiable usage.
   Self-reported numbers in a README are not evidence.
2. **Current** — actively maintained in 2026. Claude Code's surface changed
   substantially; 2024-era advice is often actively wrong now.
3. **Quality-safe** — no technique that trades correctness for tokens.
4. **Cheap at rest** — every installed skill costs ~100 tokens of context permanently.

---

## Accepted

### `obra/superpowers` — quality + completeness
MIT, by Jesse Vincent. **Accepted into Anthropic's official plugin marketplace
(January 2026)** — the strongest third-party signal available.

Supplies `test-driven-development` (RED-GREEN-REFACTOR), `systematic-debugging`,
`writing-plans`, `requesting-code-review`, and `verification-before-completion`.

Dormant cost ~1,400 tokens via progressive disclosure (~100 tokens of metadata per
skill; bodies load on trigger).

**Tradeoff, stated plainly:** it *increases* tokens per task. It earns that by
preventing the expensive failure — a long run in the wrong direction.

### `anthropics/skills` — official
First-party. The authoritative `SKILL.md` spec, which the custom skills here follow.

### `vercel-labs/agent-skills` — frontend quality
React performance rules, composition patterns, accessibility/design audit. Install
**path-scoped** so it costs nothing on backend work.

### `ccusage` — measurement
~18k stars; the de-facto community usage tracker. Reads the JSONL logs Claude Code
already writes locally. No account, no signup. This is how you verify any claim here.

### `trailofbits/skills` — security (optional)
CodeQL and Semgrep backed, by an actual security firm.

### `JuliusBrussee/caveman` — output compression, conditionally
Backed by an Adobe Research paper (CAVEWOMAN) and an independent JetBrains test.

**The number that matters:** the viral "65–90% reduction" figures are from
**chat-style Q&A**. The JetBrains coding benchmark — 86 real tasks — measured
**8.5% fewer output tokens with no detectable quality change**.

Real, modest, and honest. Not enabled by default; worth adding per-session for
research and triage, not implementation.

---

## Rejected

### `valorisa/Claude-Skills` (the "rescue-tokens" skill)
Claims **"90% verbosity reduction"** and **"$750/month → $100/month (85% reduction)"**,
described as "tested with TDD methodology".

Inspected the repository:
- **No test files.** No `test_*.py`, no `*.test.js`, nothing executable.
- **No CI pipeline**, no run artifacts.
- **No agent transcripts, no benchmark data, no reproducible measurement.**
- The "TDD methodology" is markdown *describing* RED-GREEN-REFACTOR — prose about
  testing, not tests.
- The dollar figures are labelled "documented results" with no linked documentation.
- ~13 stars, 2 forks, single maintainer.

It may well contain reasonable prompt advice. But the headline claims are
unsubstantiated, and this bundle's whole premise is not shipping unverified claims.

### `KINGSTAR-OMEGA/claude-token-optimizer`
"Antigravity Protocol" and "Ultimate Protocol Simulator (zero-English, JSON-only
compiler mode)". Forcing JSON-only output for coding work trades correctness for
tokens — exactly the tradeoff explicitly ruled out. No evidence offered.

### Mega "awesome toolkit" repos
Repos advertising 135 agents / 380 skills / 176 plugins. On Pro these are **actively
harmful**: every installed skill's description is permanently resident in context.
Breadth is the wrong optimization target when your context window is the budget.

### `ENABLE_TOOL_SEARCH`
Recommended by several 2026 posts for deferring MCP tool definitions. **It is not in
the current environment-variable documentation.** MCP tool definitions are now
deferred **by default** — only tool names and server instructions enter context until
Claude uses a specific tool. The advice is stale, so it isn't shipped here.

*This one is the useful lesson: token-optimization advice goes stale fast, because the
product keeps absorbing the optimizations. Check the docs, not the blogs.*

---

## The official mechanics this bundle encodes

All from Anthropic's own documentation.

| Mechanism | Detail | Documented effect |
|---|---|---|
| Model routing | Sonnet default, Opus for architecture, Haiku for subagents | up to ~75% cost reduction |
| Subagent delegation | Verbose work in its own context; only a summary returns | Keeps main context clean |
| Hook preprocessing | Filter tool output before Claude reads it | "tens of thousands of tokens to hundreds" |
| CLAUDE.md → skills | Move workflow detail to on-demand skills | Smaller base context |
| CLAUDE.md size | Keep under 200 lines | Better adherence too |
| Path-scoped rules | `paths:` frontmatter | Loads only on matching files |
| `/clear` vs `/compact` | `/clear` is free; `/compact` reads the whole conversation first | Avoids a large request |
| MCP hygiene | `/mcp` to disable unused; prefer CLI tools | Per-server instructions hit every turn |
| Effort level | `/effort` for routine work | Thinking bills as output tokens |
| Code intelligence plugins | Symbol navigation instead of grep-and-read | Fewer unnecessary file reads |

### Pro-plan specifics

- Rolling **5-hour** window plus a **weekly** cap, shared with claude.ai and the
  desktop/mobile apps. No separate coding allowance.
- Prompt cache TTL is **1 hour** on a subscription (drops to 5 minutes on usage
  credits). The first message after a longer gap reprocesses full context.
- Agent teams run **~7×** a standard session — relevant before going parallel.
- `/usage` attributes usage to skills, subagents, and individual MCP servers, and
  flags any behavior above 10% of recent usage.

---

## Sources

Claude Code documentation: [costs](https://code.claude.com/docs/en/costs) ·
[memory](https://code.claude.com/docs/en/memory) ·
[worktrees](https://code.claude.com/docs/en/worktrees) ·
[subagents](https://code.claude.com/docs/en/sub-agents) ·
[hooks](https://code.claude.com/docs/en/hooks) ·
[env vars](https://code.claude.com/docs/en/env-vars) ·
[settings](https://code.claude.com/docs/en/settings) ·
[plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)

Repositories: [obra/superpowers](https://github.com/obra/superpowers) ·
[anthropics/skills](https://github.com/anthropics/skills) ·
[vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) ·
[trailofbits/skills](https://github.com/trailofbits/skills) ·
[JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) ·
[ccusage](https://github.com/ccusage/ccusage)

Analysis: [Firecrawl — 14 best Claude Code skills](https://www.firecrawl.dev/blog/best-claude-code-skills) ·
[Firecrawl — 12 ways to cut token consumption](https://www.firecrawl.dev/blog/claude-code-token-efficiency) ·
[The honest tradeoffs of Superpowers](https://www.joanmedia.dev/ai-blog/the-honest-tradeoffs-of-superpowers-token-costs-overkill-and-the-alternatives) ·
[Claude Code usage limits 2026](https://www.morphllm.com/claude-code-usage-limits) ·
[Path-scoped Claude Code skills](https://claudefa.st/blog/guide/mechanics/path-scoped-skills)
