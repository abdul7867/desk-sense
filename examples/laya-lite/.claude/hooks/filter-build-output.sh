#!/usr/bin/env bash
# PreToolUse(Bash): rewrite build/install commands so only errors and warnings land
# in the context window. Same exit-code-preserving technique as filter-test-output.sh.
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
cmd=$(jq -r '.tool_input.command // empty' <<<"$input" 2>/dev/null) || exit 0
[[ -z "$cmd" ]] && exit 0

case "$cmd" in
  *TOKENSAVER_FILTERED*) exit 0 ;;
  *'|'*|*'>'*) exit 0 ;;
esac

if ! grep -qE '^[[:space:]]*((npm|pnpm|yarn|bun)[[:space:]]+(run[[:space:]]+)?(build|install|ci)|npx[[:space:]]+(tsc|expo[[:space:]]+prebuild)|tsc\b|next[[:space:]]+build|vite[[:space:]]+build|pip[[:space:]]+install|poetry[[:space:]]+install|uv[[:space:]]+(sync|pip)|make\b|cargo[[:space:]]+build|go[[:space:]]+build|(\./)?gradlew?\b|mvn\b|xcodebuild\b)' <<<"$cmd"; then
  exit 0
fi

pattern='error|Error|ERROR|warning|Warning|WARN|failed|Failed|FAILED|cannot|Cannot|not found|TS[0-9]{4}|^e: |BUILD (SUCCESSFUL|FAILED)|FAILURE:'

# Noise that matches the pattern above but says nothing. Gradle repeats the JVM
# options banner once per forked process, and dependency deprecation warnings
# from inside node_modules are not actionable by the caller.
noise='JAVA_TOOL_OPTIONS|^w: file:///.*/node_modules/|^Note: Some input files use|^Note: Recompile with|checkKotlinGradlePluginConfigurationErrors|SKIPPED$|UP-TO-DATE$|^You can use .--warning-mode|^For more on this, please refer to|^Deprecated Gradle features were used'

filtered="set -o pipefail; { $cmd ; } 2>&1 | { grep -E '$pattern' || true; } | { grep -vE '$noise' || true; } | tail -n 80  # TOKENSAVER_FILTERED"

jq -n --arg c "$filtered" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "allow",
    updatedInput: { command: $c }
  },
  systemMessage: "tokensaver: build output filtered to errors/warnings (exit code preserved)"
}'
