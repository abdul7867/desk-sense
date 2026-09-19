---
name: codebase-overview
description: The architecture map of this project — what it does, how it is laid out, where things live, and the conventions that are not obvious from any single file. Use whenever you need to orient in this codebase, before exploring or searching for where something belongs.
---

# Codebase overview

> **This file is the single highest-value token saver in the bundle.** Without it,
> Claude re-derives your architecture by reading files — thousands of tokens, every
> session, forever. With it, one on-demand read replaces all of that.
>
> Fill it in for your project and delete this quote block. Keep it under ~150 lines:
> it should answer "where does this belong?", not duplicate the code.
>
> **Refresh it whenever the architecture shifts.** A stale map is worse than none,
> because Claude trusts it. Treat a mismatch found by `codebase-scout` as a bug.

## What this project is

<One paragraph: what it does, who uses it, what it talks to.>

## Stack

- Language / runtime:
- Framework:
- Database / storage:
- Test runner:
- Package manager:
- Deployed to:

## Layout

```
src/
├── <dir>/    # <what lives here, and what does NOT>
└── <dir>/    # <...>
```

## Where things go

| I need to add... | It goes in... |
|---|---|
| a new API endpoint | |
| a new UI component | |
| a database migration | |
| shared types | |
| a background job | |

## Data flow

<How a request travels through the system. 3-6 bullets. This is the part that is
most expensive for Claude to reconstruct by reading code, so it earns its space.>

## Conventions that are not obvious

<The things a new contributor gets wrong. Naming, error handling, module boundaries,
"we tried X and it did not work". Be specific — vague conventions get ignored.>

## Known rough edges

<Areas that are messy, being migrated, or deliberately unusual. Saying "this is
legacy, do not copy its pattern" here saves a whole class of mistake.>

## Commands

```bash
# install
# dev
# test
# lint / typecheck
# build
```
