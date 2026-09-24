# Tokensaver repository

The Tokensaver bundle (`claude/`, `install.sh`, `profiles/`, `templates/`) and the projects built with
it (`examples/`). Each example has its own CLAUDE.md; read that one when working inside it.

## Commits and pull requests

- Commits are authored by the human owner only. **Never add `Co-Authored-By: Claude …`,
  `Claude-Session: …` or "Generated with Claude Code" lines** to commits or PR descriptions.
- Enforced three ways: `attribution` is off in `.claude/settings.json`; `claude/hooks/block-hazards-bash.sh`
  refuses such commits; `.githooks/commit-msg` strips them (enable with `git config core.hooksPath .githooks`).
