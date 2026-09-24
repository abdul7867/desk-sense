#!/usr/bin/env bash
# SessionStart hook: inject a compact situation report so Claude opens oriented
# instead of spending thousands of tokens re-deriving where things stand.
#
# THE RULE THIS FILE LIVES BY: it must cost less than the exploration it replaces.
# Everything below is hard-capped, and the whole report is truncated to MAX_LINES.
# If you add a section, cap it too.
set -uo pipefail

MAX_LINES="${TOKENSAVER_SITREP_MAX_LINES:-40}"
[[ "${TOKENSAVER_SITREP:-on}" == "off" ]] && exit 0

input=$(cat 2>/dev/null || echo '{}')
if command -v jq >/dev/null 2>&1; then
  cwd=$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)
  [[ -n "$cwd" && -d "$cwd" ]] && cd "$cwd" 2>/dev/null || true
fi

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

out=""
add() { out+="$1"$'\n'; }

# --- Git state -------------------------------------------------------------
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
add "## Situation report"
add ""
add "Branch: \`${branch}\`"

recent=$(git log --oneline -3 2>/dev/null | sed 's/^/  - /')
if [[ -n "$recent" ]]; then
  add "Recent commits:"
  add "$recent"
fi

changed=$(git status --porcelain 2>/dev/null | head -12)
if [[ -n "$changed" ]]; then
  n=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  add "Uncommitted changes (${n}):"
  add "$(sed 's/^/  /' <<<"$changed")"
  [[ "$n" -gt 12 ]] && add "  ... and $((n - 12)) more"
else
  add "Working tree: clean"
fi

# --- Last known test status (written by verify-before-done.sh) -------------
status_file=".claude/.tokensaver-status"
if [[ -f "$status_file" ]]; then
  add ""
  add "Last verification: $(head -1 "$status_file")"
fi

# --- Lessons relevant to what is currently being touched -------------------
# This is what makes docs/lessons.md actually get read at the moment it matters,
# instead of being a write-only ledger.
if [[ -f docs/lessons.md ]]; then
  changed_files=$(git status --porcelain 2>/dev/null | awk '{print $NF}')
  if [[ -n "$changed_files" ]]; then
    terms=$(tr '/' '\n' <<<"$changed_files" \
      | sed 's/\.[a-zA-Z]*$//' \
      | grep -vE '^(src|lib|app|test|tests|docs|\.|)$' \
      | sort -u | head -8)
    hits=""
    while IFS= read -r t; do
      [[ ${#t} -lt 3 ]] && continue
      m=$(grep -i -m1 -- "$t" docs/lessons.md 2>/dev/null | grep -v '^<!--' || true)
      [[ -n "$m" ]] && hits+="  - ${m#- }"$'\n'
    done <<<"$terms"
    hits=$(sort -u <<<"$hits" | grep -v '^$' | head -3)
    if [[ -n "$hits" ]]; then
      add ""
      add "Lessons matching files you are touching:"
      add "$hits"
    fi
  fi
fi

# --- TODO / FIXME markers, changed files only ------------------------------
changed_src=$(git status --porcelain 2>/dev/null | awk '{print $NF}' \
  | grep -E '\.(ts|tsx|js|jsx|py|go|rs|java|rb|php)$' || true)
if [[ -n "$changed_src" ]]; then
  markers=$(grep -n -E '(TODO|FIXME|HACK|XXX)' $changed_src 2>/dev/null | head -5 | sed 's/^/  /' || true)
  if [[ -n "$markers" ]]; then
    add ""
    add "Markers in files you changed:"
    add "$markers"
  fi
fi

report=$(head -n "$MAX_LINES" <<<"$out")

if command -v jq >/dev/null 2>&1; then
  jq -n --arg c "$report" '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $c
    }
  }'
else
  printf '%s\n' "$report"   # plain stdout is injected as context too
fi
