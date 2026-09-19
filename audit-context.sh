#!/usr/bin/env bash
# Context budget audit: what does this setup cost you before you type a word?
#
# This system tells you to make every component prove it pays for itself. This is
# the script that holds the system to its own standard. Run it in any project that
# has the bundle installed.
#
#   ./audit-context.sh [project-dir]
#
# Token figures are ESTIMATES (chars/4). Treat them as relative, not exact — use
# /context inside Claude Code for the authoritative number.
set -uo pipefail

TARGET="${1:-$PWD}"
cd "$TARGET" 2>/dev/null || { echo "not a directory: $TARGET" >&2; exit 1; }

B=$'\033[1m'; DIM=$'\033[2m'; R=$'\033[0m'
RED=$'\033[31m'; AMB=$'\033[33m'; GRN=$'\033[32m'

est() { [[ -f "$1" ]] && echo $(( $(wc -c < "$1") / 4 )) || echo 0; }

total=0
row() { # label, tokens, note
  printf '  %-34s %6s  %s\n' "$1" "$2" "${3:-}"
  total=$((total + $2))
}

echo
echo "${B}Context budget audit${R}  ${DIM}$TARGET${R}"
echo "${DIM}Estimates (chars/4). Authoritative numbers come from /context.${R}"
echo

# --- Always loaded ---------------------------------------------------------
echo "${B}Loaded every session${R}"

t=$(est CLAUDE.md)
note=""; (( t > 2000 )) && note="${RED}over budget — move detail into skills${R}"
row "CLAUDE.md" "$t" "$note"

# Rules without a paths: key load at launch; scoped ones do not.
unscoped=0; scoped=0; n_scoped=0
if [[ -d .claude/rules ]]; then
  while IFS= read -r f; do
    c=$(est "$f")
    if head -10 "$f" | grep -q '^paths:'; then
      scoped=$((scoped + c)); n_scoped=$((n_scoped + 1))
    else
      unscoped=$((unscoped + c))
    fi
  done < <(find .claude/rules -name '*.md' 2>/dev/null)
fi
note=""; (( unscoped > 0 )) && note="${AMB}unscoped — add a paths: key${R}"
row "rules (unscoped)" "$unscoped" "$note"

# Skill + agent descriptions are resident; bodies are not.
sk_desc=0; n_sk=0
while IFS= read -r f; do
  d=$(grep -m1 '^description:' "$f" 2>/dev/null | wc -c)
  sk_desc=$((sk_desc + d / 4)); n_sk=$((n_sk + 1))
done < <(find .claude/skills -name 'SKILL.md' 2>/dev/null)
row "skill descriptions (${n_sk})" "$sk_desc"

ag_desc=0; n_ag=0
while IFS= read -r f; do
  d=$(grep -m1 '^description:' "$f" 2>/dev/null | wc -c)
  ag_desc=$((ag_desc + d / 4)); n_ag=$((n_ag + 1))
done < <(find .claude/agents -name '*.md' 2>/dev/null)
row "agent descriptions (${n_ag})" "$ag_desc"

# Auto memory index
mem_idx=0
proj=$(git rev-parse --show-toplevel 2>/dev/null || echo "$TARGET")
memdir="$HOME/.claude/projects/$(basename "$proj")/memory"
if [[ -f "$memdir/MEMORY.md" ]]; then
  lines=$(wc -l < "$memdir/MEMORY.md")
  mem_idx=$(est "$memdir/MEMORY.md")
  note=""
  (( lines > 200 )) && note="${RED}${lines}/200 lines — OVERFLOW IS DROPPED${R}"
  (( lines > 160 && lines <= 200 )) && note="${AMB}${lines}/200 lines${R}"
  row "MEMORY.md index" "$mem_idx" "$note"
else
  row "MEMORY.md index" 0 "${DIM}none yet${R}"
fi

sitrep=0
if [[ -x .claude/hooks/situation-report.sh ]]; then
  sitrep=$(echo "{\"cwd\":\"$TARGET\"}" | .claude/hooks/situation-report.sh 2>/dev/null \
    | { command -v jq >/dev/null && jq -r '.hookSpecificOutput.additionalContext // ""' || cat; } | wc -c)
  sitrep=$((sitrep / 4))
fi
row "situation report (injected)" "$sitrep"

echo
printf "  %-34s ${B}%6s${R}\n" "SUBTOTAL (bundle)" "$total"
echo
echo "${DIM}  Not counted: Claude Code's own system prompt and tool definitions,${R}"
echo "${DIM}  MCP servers, and installed plugins. Run /context for the full picture.${R}"

# --- Loaded on demand ------------------------------------------------------
echo
echo "${B}Loaded only when needed${R} ${DIM}(costs nothing at rest)${R}"
sk_body=0
while IFS= read -r f; do sk_body=$((sk_body + $(est "$f"))); done < <(find .claude/skills -name 'SKILL.md' 2>/dev/null)
printf '  %-34s %6s\n' "skill bodies (${n_sk})" "$sk_body"
printf '  %-34s %6s  %s\n' "rules (path-scoped, ${n_scoped})" "$scoped" "${GRN}only on matching files${R}"
[[ -d "$memdir" ]] && printf '  %-34s %6s\n' "memory topic files" \
  "$(( $(find "$memdir" -name '*.md' ! -name MEMORY.md -exec cat {} + 2>/dev/null | wc -c) / 4 ))"

# --- Verdict ---------------------------------------------------------------
echo
if   (( total > 6000 )); then v="${RED}heavy${R} — prune before adding anything"
elif (( total > 3000 )); then v="${AMB}moderate${R} — watch it"
else                          v="${GRN}lean${R}"
fi
echo "  Verdict: $v"
echo
echo "${DIM}  Biggest levers, in order:${R}"
echo "${DIM}   1. Shorten CLAUDE.md — move workflow detail into skills${R}"
echo "${DIM}   2. Add a paths: key to every rule that is not universal${R}"
echo "${DIM}   3. Remove skills you have not used in a month${R}"
echo "${DIM}   4. Keep MEMORY.md one line per entry${R}"
echo
