#!/usr/bin/env bash
# Stop hook: refuse to let Claude finish while the project is in a failing state.
#
# This is the enforcement layer. CLAUDE.md and memory are context, which Claude can
# reason its way past; a Stop hook is mechanical and cannot be talked out of.
#
# Behaviour:
#   - no source changes since HEAD  -> silent pass (cheap: nothing to verify)
#   - lint / typecheck / tests fail -> exit 2, Claude must keep working
#   - all pass                      -> silent pass
#
# Control with TOKENSAVER_VERIFY:
#   full  (default) lint + typecheck + tests
#   quick           lint + typecheck only
#   off             disabled
set -uo pipefail

MODE="${TOKENSAVER_VERIFY:-full}"
[[ "$MODE" == "off" ]] && exit 0

input=$(cat 2>/dev/null || echo '{}')

# Loop guard: Claude Code sets stop_hook_active when a Stop hook is already running
# or the last tool call came from inside one. Without this check, a blocking hook
# that triggers tool calls can recurse forever.
if command -v jq >/dev/null 2>&1; then
  [[ "$(jq -r '.stop_hook_active // false' <<<"$input" 2>/dev/null)" == "true" ]] && exit 0
  cwd=$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)
  [[ -n "$cwd" && -d "$cwd" ]] && cd "$cwd" || true
fi

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# Only verify when source actually changed. Docs-only or config-only edits skip the
# suite, which keeps the common case free.
changed=$(git status --porcelain 2>/dev/null \
  | awk '{print $NF}' \
  | grep -E '\.(ts|tsx|js|jsx|py|go|rs|java|rb|php|css|scss|sql)$' || true)
[[ -z "$changed" ]] && exit 0

has_script() {  # $1 = package.json script name
  [[ -f package.json ]] || return 1
  if command -v jq >/dev/null 2>&1; then
    jq -e --arg s "$1" '.scripts[$s] // empty' package.json >/dev/null 2>&1
  else
    grep -qE "\"$1\"[[:space:]]*:" package.json
  fi
}

PM="npm"
[[ -f pnpm-lock.yaml ]] && PM="pnpm"
[[ -f yarn.lock ]] && PM="yarn"
[[ -f bun.lockb ]] && PM="bun"

failures=""
run_check() {  # $1 = label, $2... = command
  local label="$1"; shift
  local out status
  out=$("$@" 2>&1); status=$?
  if [[ $status -ne 0 ]]; then
    failures+="
--- ${label} failed (exit ${status}) ---
$(tail -n 25 <<<"$out")
"
  fi
}

# Lint
if has_script lint; then
  run_check "lint" "$PM" run lint
elif [[ -f .ruff.toml || -f ruff.toml ]] || grep -qs '\[tool.ruff\]' pyproject.toml 2>/dev/null; then
  command -v ruff >/dev/null 2>&1 && run_check "ruff" ruff check .
fi

# Typecheck
if has_script typecheck; then
  run_check "typecheck" "$PM" run typecheck
elif [[ -f tsconfig.json ]] && command -v npx >/dev/null 2>&1; then
  run_check "tsc" npx --no-install tsc --noEmit
fi
if grep -qs '\[tool.mypy\]' pyproject.toml 2>/dev/null && command -v mypy >/dev/null 2>&1; then
  run_check "mypy" mypy .
fi

# Tests
if [[ "$MODE" == "full" ]]; then
  if has_script test; then
    run_check "tests" "$PM" test
  elif [[ -f pytest.ini || -f pyproject.toml || -d tests ]] && command -v pytest >/dev/null 2>&1; then
    run_check "pytest" pytest -q
  fi
fi

# --- Gates a linter cannot catch -------------------------------------------
# These two are the ones that actually get skipped, because nothing mechanical
# has ever checked them.

# Secrets in the working tree
secrets=$(git status --porcelain 2>/dev/null | awk '{print $NF}' \
  | grep -E '(^|/)\.env(\.|$)|\.pem$|(^|/)id_(rsa|ed25519)$|credentials\.json$' || true)
if [[ -n "$secrets" ]]; then
  if ! git check-ignore -q $secrets 2>/dev/null; then
    failures+="
--- secrets gate ---
These look like secret files and are not gitignored:
$secrets
Add them to .gitignore before finishing.
"
  fi
fi

# Docs should change with the code they describe
if [[ "${TOKENSAVER_DOCS_GATE:-on}" == "on" ]]; then
  code_changed=$(git status --porcelain 2>/dev/null | awk '{print $NF}' \
    | grep -E '\.(ts|tsx|js|jsx|py|go|rs|java|rb|php)$' | grep -vE '(test|spec)\.' || true)
  docs_changed=$(git status --porcelain 2>/dev/null | awk '{print $NF}' \
    | grep -E '(\.md$|^docs/|README)' || true)
  n_code=$(grep -c . <<<"$code_changed" 2>/dev/null || echo 0)
  if [[ -n "$code_changed" ]] && [[ -z "$docs_changed" ]] && (( n_code >= 3 )); then
    failures+="
--- docs gate ---
${n_code} non-test source files changed and no documentation changed with them.
Update the README, API docs, or .claude/skills/codebase-overview/SKILL.md in this
same change, or state plainly why none was needed.
Disable this gate with TOKENSAVER_DOCS_GATE=off.
"
  fi
fi

# --- Record the outcome for the next session's situation report -------------
status_dir=".claude"; [[ -d "$status_dir" ]] && {
  if [[ -n "$failures" ]]; then
    echo "FAILED ($(date '+%Y-%m-%d %H:%M'))" > "$status_dir/.tokensaver-status"
  else
    echo "passed ($(date '+%Y-%m-%d %H:%M'))" > "$status_dir/.tokensaver-status"
  fi
}

if [[ -n "$failures" ]]; then
  cat >&2 <<EOF
Definition of Done not met — the project is in a failing state, so this work is not finished.
$failures
Fix the failures above, then finish. Do not describe them as pre-existing without
checking git: if they fail on HEAD too, say so explicitly and continue.
To skip this gate for a deliberate work-in-progress stop, set TOKENSAVER_VERIFY=off.
EOF
  exit 2
fi

exit 0
