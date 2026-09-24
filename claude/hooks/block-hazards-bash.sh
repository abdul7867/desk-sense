#!/usr/bin/env bash
# PreToolUse(Bash): refuse the small set of commands whose damage is hard to undo.
#
# This is a DENY hook, not advice. Claude can reason past a CLAUDE.md instruction;
# it cannot reason past this. Scope is deliberately narrow — a gate that fires on
# things you legitimately wanted is a gate you will disable, and then it protects
# nothing. Four categories only: secrets, history rewrites on the default branch,
# destructive removals, and AI co-author / session trailers in commits and PRs.
#
# Escape hatch: TOKENSAVER_ALLOW_HAZARD=1 for a single deliberate command.
set -uo pipefail

[[ "${TOKENSAVER_ALLOW_HAZARD:-0}" == "1" ]] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

input=$(cat)
cmd=$(jq -r '.tool_input.command // empty' <<<"$input" 2>/dev/null) || exit 0
[[ -z "$cmd" ]] && exit 0
cwd=$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)
[[ -n "$cwd" && -d "$cwd" ]] && cd "$cwd" 2>/dev/null || true

deny() {
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

# --- 1. Secrets about to be committed -------------------------------------
if grep -qE '\bgit\s+(add|commit)\b' <<<"$cmd"; then
  files=$(git diff --cached --name-only 2>/dev/null || true)
  # Files named directly on a `git add` line count too — they are about to be staged.
  for tok in $cmd; do
    [[ -f "$tok" ]] && files+=$'\n'"$tok"
  done
  secret_named=$(grep -E '(^|/)\.env(\.|$)|\.pem$|\.p12$|\.pfx$|(^|/)id_(rsa|ed25519)$|(^|/)\.npmrc$|credentials\.json$' <<<"$files" | sort -u || true)
  [[ -n "$secret_named" ]] && deny "Refusing: these look like secret files and are about to be committed:
$secret_named

Add them to .gitignore instead. If one is genuinely safe to commit, re-run with TOKENSAVER_ALLOW_HAZARD=1."

  # Content scan of what is actually staged.
  leak=$(git diff --cached 2>/dev/null \
    | grep -E '^\+' \
    | grep -nE '(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{32,}|ghp_[A-Za-z0-9]{36}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(api[_-]?key|secret|password|token)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{12,})' \
    | head -3 || true)
  [[ -n "$leak" ]] && deny "Refusing: the staged diff contains what looks like a live credential:
$leak

Remove it, use an environment variable, and rotate the key if it was ever real.
Override with TOKENSAVER_ALLOW_HAZARD=1 only if this is a false positive."
fi

# --- 2. History rewrite on the default branch ------------------------------
default_branch=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
[[ -z "$default_branch" ]] && default_branch="main"
current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

is_push=0;  grep -qE '\bgit[[:space:]]+push\b' <<<"$cmd" && is_push=1
# --force-with-lease is the safe form and is NOT blocked; only a bare force is.
is_force=0
if grep -qE -- '--force([^-]|$)' <<<"$cmd" || grep -qE -- '(^|[[:space:]])-f([[:space:]]|$)' <<<"$cmd"; then
  is_force=1
fi
targets_default=0
if grep -qE "(^|[[:space:]])(${default_branch}|main|master)([[:space:]]|:|$)" <<<"$cmd"; then
  targets_default=1
elif [[ "$current_branch" == "$default_branch" ]]; then
  # No explicit refspec means the push goes to the CURRENT branch's upstream. Count
  # only positional args — an earlier version counted "--force" itself as a branch
  # name, so a bare `git push --force` on main slipped straight through.
  positional=$(tr ' ' '\n' <<<"${cmd#*push}" | grep -vE '^-|^$' | wc -l | tr -d ' ')
  (( positional < 2 )) && targets_default=1
fi

if (( is_push && is_force && targets_default )); then
  deny "Refusing: force-push to '${default_branch}'. This rewrites shared history and breaks every clone.
Push to a feature branch and open a PR, or use --force-with-lease on your own branch.
Override with TOKENSAVER_ALLOW_HAZARD=1 if you truly mean it."
fi

if grep -qE '\bgit[[:space:]]+reset[[:space:]]+--hard\b' <<<"$cmd" && [[ "$current_branch" == "$default_branch" ]]; then
  deny "Refusing: 'git reset --hard' while on '${default_branch}'. This discards work irreversibly.
Commit or stash first, or switch to a feature branch. Override with TOKENSAVER_ALLOW_HAZARD=1."
fi

# --- 3. Destructive removals ----------------------------------------------
if grep -qE '\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+' <<<"$cmd"; then
  # Absolute paths outside the project, or the classic catastrophes.
  if grep -qE 'rm\s+(-[a-zA-Z]+\s+)*(/|~|\$HOME|/\*|\.\.)($|[[:space:]/])' <<<"$cmd"; then
    deny "Refusing: recursive delete targeting a path outside the project (or the filesystem root).
Delete inside the project with an explicit relative path. Override with TOKENSAVER_ALLOW_HAZARD=1."
  fi
  project_root=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")
  for tok in $cmd; do
    [[ "$tok" == /* ]] || continue
    case "$tok" in
      "$project_root"*) ;;                 # inside the project: allowed
      /tmp/*|/var/folders/*) ;;            # scratch space: allowed
      *) deny "Refusing: recursive delete of '$tok', which is outside the project ($project_root).
Override with TOKENSAVER_ALLOW_HAZARD=1 if this is intentional." ;;
    esac
  done
fi


# --- 4. AI co-author / session trailers ------------------------------------
# Commits and PRs in this project are credited to their human author only. The
# "attribution" setting turns these off; this catches a message typed by hand.
if grep -qE '\bgit[[:space:]]+commit\b|\bgh[[:space:]]+pr[[:space:]]+(create|edit)\b' <<<"$cmd" \
   && grep -qiE 'co-authored-by:.*(claude|anthropic)|claude-session:|generated with \[?claude code' <<<"$cmd"; then
  deny "Refusing: this commit/PR text credits Claude (Co-Authored-By / Claude-Session / 'Generated with Claude Code').
This project does not use AI co-author trailers. Remove those lines and run it again."
fi

exit 0
