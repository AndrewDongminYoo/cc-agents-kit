#!/usr/bin/env bash
# PostToolUse hook (matcher: Edit|MultiEdit|Write): after an edit to a dependency
# manifest, warn when the sibling lockfile is now older than the manifest so
# the lockfile gets regenerated with the CI-equivalent command before commit.
# Ecosystem-agnostic by design — detects the manifest, never assumes a stack.

set -euo pipefail

# Opt-out: set CC_GUARD_DISABLE_LOCKFILE_DRIFT=1 to disable this hook.
[[ -n "${CC_GUARD_DISABLE_LOCKFILE_DRIFT:-}" ]] && exit 0

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
FILE_PATH=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
[[ -n "$FILE_PATH" && -f "$FILE_PATH" ]] || exit 0

DIR=$(dirname "$FILE_PATH")
BASE=$(basename "$FILE_PATH")

# manifest basename → candidate lockfiles in the same directory
case "$BASE" in
  package.json) LOCKS=("yarn.lock" "package-lock.json" "pnpm-lock.yaml" "bun.lock" "bun.lockb") ;;
  pubspec.yaml) LOCKS=("pubspec.lock") ;;
  Cargo.toml) LOCKS=("Cargo.lock") ;;
  pyproject.toml) LOCKS=("poetry.lock" "uv.lock" "pdm.lock") ;;
  Gemfile) LOCKS=("Gemfile.lock") ;;
  Podfile) LOCKS=("Podfile.lock") ;;
  composer.json) LOCKS=("composer.lock") ;;
  *) exit 0 ;;
esac

STALE=""
for lock in "${LOCKS[@]}"; do
  if [[ -f "$DIR/$lock" && "$DIR/$lock" -ot "$FILE_PATH" ]]; then
    STALE="${STALE:+$STALE, }$lock"
  fi
done
[[ -n "$STALE" ]] || exit 0

MSG="⚠️ $BASE was edited and $STALE is now older than the manifest. If dependencies changed, regenerate the lockfile with the CI-equivalent command (e.g. yarn install --immutable / flutter pub get / cargo check) and commit it together with the manifest."
jq -n --arg ctx "$MSG" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'
