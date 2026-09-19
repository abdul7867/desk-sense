#!/usr/bin/env bash
# PreToolUse(Bash): rewrite test commands so only failures reach the context window.
#
# A passing suite prints hundreds of lines that Claude does not need. This rewrites
# the command to filter for failure signal only. A green run then costs ~0 tokens.
#
# Exit-code safety: `cmd | grep` would make the PIPELINE's status come from grep, so
# a passing suite with no matches would look like a failure. We use `pipefail` plus
# `|| true` on the grep so the ORIGINAL command's exit code is what survives.
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
cmd=$(jq -r '.tool_input.command // empty' <<<"$input" 2>/dev/null) || exit 0
[[ -z "$cmd" ]] && exit 0

# Already filtered by us, or the user is deliberately piping/redirecting: leave alone.
case "$cmd" in
  *TOKENSAVER_FILTERED*) exit 0 ;;
  *'|'*|*'>'*) exit 0 ;;
esac

# Only touch recognised test runners at the start of the command.
if ! grep -qE '^[[:space:]]*((npm|pnpm|yarn|bun)[[:space:]]+(run[[:space:]]+)?test|npx[[:space:]]+(vitest|jest)|vitest|jest|pytest|python[[:space:]]+-m[[:space:]]+pytest|go[[:space:]]+test|cargo[[:space:]]+test|(\./)?gradlew?[[:space:]]+.*\btest|mvn[[:space:]]+.*\btest)\b' <<<"$cmd"; then
  exit 0
fi

pattern='FAIL|FAILED|ERROR|Error:|error:|✕|✗|AssertionError|Traceback|panic:|--- FAIL|[0-9]+ (failed|failing)|[0-9]+ passed'

filtered="set -o pipefail; { $cmd ; } 2>&1 | { grep -E -A 5 '$pattern' || true; } | tail -n 120  # TOKENSAVER_FILTERED"

jq -n --arg c "$filtered" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "allow",
    updatedInput: { command: $c }
  },
  systemMessage: "tokensaver: test output filtered to failures only (exit code preserved)"
}'
