#!/usr/bin/env bash
# Tokensaver installer — copies the bundle into a target project.
#
#   ./install.sh [--profile balanced|aggressive] [--dry-run] [--force] <target-dir>
#
# Non-destructive by default: an existing file is never overwritten unless --force
# is given, and --force backs it up first. Safe to re-run.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="balanced"
DRY_RUN=0
FORCE=0
TARGET=""

die() { printf 'error: %s\n' "$1" >&2; exit 1; }
say() { printf '%s\n' "$1"; }

usage() {
  sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --profile=*) PROFILE="${1#*=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage 0 ;;
    -*) die "unknown option: $1 (try --help)" ;;
    *) [[ -n "$TARGET" ]] && die "only one target directory"; TARGET="$1"; shift ;;
  esac
done

[[ -n "$TARGET" ]] || usage 1
[[ -d "$TARGET" ]] || die "target is not a directory: $TARGET"
[[ -f "$SRC/profiles/$PROFILE.json" ]] || die "unknown profile: $PROFILE (expected balanced or aggressive)"
TARGET="$(cd "$TARGET" && pwd)"
[[ "$TARGET" == "$SRC" ]] && die "refusing to install Tokensaver into itself"

say "Tokensaver → $TARGET   (profile: $PROFILE)"
[[ $DRY_RUN -eq 1 ]] && say "DRY RUN — nothing will be written"
say ""

installed=0; skipped=0; backed_up=0

# copy_file <src> <dest-relative-to-target>
copy_file() {
  local src="$1" rel="$2" dest="$TARGET/$2"
  if [[ -e "$dest" ]]; then
    if [[ $FORCE -eq 0 ]]; then
      say "  skip    $rel  (exists — use --force to replace)"
      skipped=$((skipped + 1)); return
    fi
    if [[ $DRY_RUN -eq 0 ]]; then
      cp -p "$dest" "$dest.tokensaver-bak"
    fi
    say "  backup  $rel → $rel.tokensaver-bak"
    backed_up=$((backed_up + 1))
  fi
  if [[ $DRY_RUN -eq 0 ]]; then
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
  fi
  say "  install $rel"
  installed=$((installed + 1))
}

say "Bundle → .claude/"
while IFS= read -r f; do
  copy_file "$f" ".claude/${f#"$SRC"/claude/}"
done < <(find "$SRC/claude" -type f ! -name settings.json | sort)

# settings.json: base merged with the chosen profile.
say ""
say "Settings (.claude/settings.json, profile: $PROFILE)"
merged="$(mktemp)"
trap 'rm -f "$merged"' EXIT

if command -v jq >/dev/null 2>&1; then
  jq -s '.[0] * .[1] | del(._comment)' \
     "$SRC/claude/settings.json" "$SRC/profiles/$PROFILE.json" > "$merged"
elif command -v python3 >/dev/null 2>&1; then
  python3 - "$SRC/claude/settings.json" "$SRC/profiles/$PROFILE.json" "$merged" <<'PY'
import json, sys
base, prof, out = sys.argv[1], sys.argv[2], sys.argv[3]
def merge(a, b):
    r = dict(a)
    for k, v in b.items():
        r[k] = merge(r[k], v) if isinstance(v, dict) and isinstance(r.get(k), dict) else v
    return r
d = merge(json.load(open(base)), json.load(open(prof)))
d.pop("_comment", None)
json.dump(d, open(out, "w"), indent=2)
open(out, "a").write("\n")
PY
else
  die "need jq or python3 to merge settings"
fi
copy_file "$merged" ".claude/settings.json"

say ""
say "Project templates (root)"
copy_file "$SRC/templates/CLAUDE.md"            "CLAUDE.md"
copy_file "$SRC/templates/DEFINITION-OF-DONE.md" "DEFINITION-OF-DONE.md"
copy_file "$SRC/templates/.worktreeinclude"      ".worktreeinclude"
copy_file "$SRC/templates/lessons.md"            "docs/lessons.md"
copy_file "$SRC/templates/decisions.md"          "docs/decisions.md"

if [[ -d "$TARGET/.github/workflows" || $FORCE -eq 1 ]]; then
  copy_file "$SRC/templates/ci.yml" ".github/workflows/ci.yml"
else
  say "  skip    .github/workflows/ci.yml  (no workflows dir — copy templates/ci.yml yourself)"
  skipped=$((skipped + 1))
fi

# Hooks must be executable or the Stop gate silently never fires.
if [[ $DRY_RUN -eq 0 ]]; then
  chmod +x "$TARGET"/.claude/hooks/*.sh 2>/dev/null || true
fi

# .gitignore: worktrees must not show up as untracked noise in the main checkout.
gi="$TARGET/.gitignore"
for entry in ".claude/worktrees/" "*.tokensaver-bak"; do
  if [[ ! -f "$gi" ]] || ! grep -qxF "$entry" "$gi" 2>/dev/null; then
    [[ $DRY_RUN -eq 0 ]] && printf '%s\n' "$entry" >> "$gi"
    say "  gitignore += $entry"
  fi
done

say ""
say "Done — $installed installed, $skipped skipped, $backed_up backed up."
say ""
say "Next:"
say "  1. Fill in CLAUDE.md and .claude/skills/codebase-overview/SKILL.md."
say "     The overview is the biggest single token saver — an empty one saves nothing."
say "  2. Edit .claude/rules/*.md to match your conventions; delete what does not apply."
say "  3. Baseline before you judge it:  npx ccusage@latest daily"
say "  4. In Claude Code, run /context and /hooks to confirm what loaded."
say ""
say "See README.md for the external skills to install and how to measure the result."
