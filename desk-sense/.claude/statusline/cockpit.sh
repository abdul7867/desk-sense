#!/usr/bin/env bash
# Status line: the cockpit. Runs OUTSIDE the context window, so it costs zero tokens.
#
# The line that matters is the cache one. On a subscription the prompt cache TTL is
# one hour; when it lapses, your next message reprocesses the whole conversation.
# Claude Code reports exactly what that will cost (recache_tokens_if_cold) and when
# the cache expires (expires_at), so this turns your largest hidden cost into a
# visible countdown you can act on — finish the thought now, or accept the rebuild.
set -uo pipefail

input=$(cat)
command -v jq >/dev/null 2>&1 || { echo "tokensaver: jq required for status line"; exit 0; }

j() { jq -r "$1 // empty" <<<"$input" 2>/dev/null; }

model=$(j '.model.display_name')
pct=$(j '.context_window.used_percentage'); pct=${pct%%.*}; pct=${pct:-0}
cost=$(j '.cost.total_cost_usd')
branch=$(j '.workspace.git_worktree')
curdir=$(j '.workspace.current_dir')
dir=$(basename "$curdir" 2>/dev/null)
# Read git from the SESSION's directory, not wherever this script happens to run,
# or the line reports a branch from an unrelated repo.
if [[ -z "$branch" && -n "$curdir" && -d "$curdir" ]]; then
  branch=$(git -C "$curdir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
fi

# Context bar, 20 cells, colour-coded by pressure.
filled=$((pct / 5)); (( filled > 20 )) && filled=20
bar=""
for ((i = 0; i < 20; i++)); do [[ $i -lt $filled ]] && bar+="█" || bar+="░"; done
if   (( pct >= 80 )); then cc=$'\033[31m'   # red: compact or clear now
elif (( pct >= 60 )); then cc=$'\033[33m'   # amber: plan the handoff
else                       cc=$'\033[32m'; fi
R=$'\033[0m'; DIM=$'\033[2m'

line1="${DIM}${model:-?}${R}  ${dir:-?}"
[[ -n "$branch" ]] && line1+="  ${DIM}(${branch})${R}"

line2="${cc}${bar}${R} ${pct}% ctx"
[[ -n "$cost" ]] && line2+=$(printf '  $%.2f' "$cost" 2>/dev/null || echo "")

# Cache panel
# NOTE: do not use `// empty` on a boolean — jq treats `false` as unset, which
# silently hid the whole cache panel whenever the cache was cold.
warm=$(jq -r 'if (.prompt_cache | type) == "object" then (.prompt_cache.warm | tostring) else "" end' <<<"$input" 2>/dev/null)
if [[ "$warm" == "true" || "$warm" == "false" ]]; then
  hit=$(j '.prompt_cache.hit_ratio')
  hit_pct=$(awk -v h="${hit:-0}" 'BEGIN{printf "%d", h*100}' 2>/dev/null || echo 0)
  if [[ "$warm" == "true" ]]; then
    exp=$(j '.prompt_cache.expires_at')
    now=$(date +%s)
    if [[ -n "$exp" ]] && (( exp > now )); then
      mins=$(( (exp - now) / 60 ))
      recache=$(j '.prompt_cache.recache_tokens_if_cold')
      rk=""
      [[ -n "$recache" ]] && rk=$(awk -v r="$recache" 'BEGIN{printf "%.0fk", r/1000}')
      if (( mins <= 10 )); then
        line2+="  ${cc}cache ${mins}m left${rk:+ (${rk} to rebuild)}${R}"
      else
        line2+="  ${DIM}cache warm ${mins}m${R}"
      fi
    else
      line2+="  ${DIM}cache warm${R}"
    fi
    [[ "$hit_pct" -gt 0 ]] && line2+="${DIM} ${hit_pct}% hit${R}"
  else
    line2+="  ${DIM}cache cold${R}"
  fi
  cause=$(j '.prompt_cache.last_miss_cause.causes[0]')
  [[ -n "$cause" ]] && line2+="${DIM} · last miss: ${cause}${R}"
fi

printf '%s\n%s\n' "$line1" "$line2"
