#!/usr/bin/env bash
# PostToolUse hook (matcher: Edit|MultiEdit|Write): after an edit to a shell script,
# run shellcheck and surface its findings so they are seen at edit time
# rather than at commit time. Advisory only — never blocks.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_SHELLCHECK=1 to disable this hook. Checked after stdin is
# drained so a disabled hook never leaves the harness writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_SHELLCHECK:-}" ]] && exit 0
FILE_PATH=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
[[ -n "$FILE_PATH" && -f "$FILE_PATH" ]] || exit 0

case "$FILE_PATH" in
  *.sh | *.bash) ;;
  *) exit 0 ;;
esac

SC=""
if command -v shellcheck >/dev/null 2>&1; then
  SC=$(command -v shellcheck)
elif [[ -x "/opt/homebrew/bin/shellcheck" ]]; then
  SC="/opt/homebrew/bin/shellcheck"
fi
[[ -n "$SC" ]] || exit 0

if OUT=$("$SC" "$FILE_PATH" 2>&1); then
  exit 0
fi

OUT=$(printf '%s\n' "$OUT" | head -n 40)
MSG="⚠️ shellcheck found issues in $FILE_PATH:
$OUT"
jq -n --arg ctx "$MSG" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'
exit 0
