#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash): best-effort guard against (1) recursive rm
# aimed at $HOME or filesystem roots and (2) download-and-execute pipelines
# (curl|wget ... | sh). Regex on the command string — a guardrail against
# ACCIDENTAL invocation, not a sandbox: deliberate obfuscation can bypass it,
# and the auto-mode classifier remains the semantic enforcement layer.
# Must fail open (exit 0) on any empty/malformed input so unrelated tool
# calls are never blocked.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_DANGEROUS_COMMAND=1 to disable this hook. Checked after stdin is
# drained so a disabled hook never leaves the harness writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_DANGEROUS_COMMAND:-}" ]] && exit 0
COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -z "$COMMAND" ]] && exit 0

# --- recursive rm targeting home/root ---------------------------------------
# Grab each rm invocation segment (start or after ; | & (), any binary path or
# backslash escape), then require BOTH a recursive flag spelling AND a bare
# home/root target (optionally quoted, optionally with a trailing /* or *).
RM_SEG_RE='(^|[;|&([:space:]])\\?(/bin/|/usr/bin/)?rm[[:space:]][^;|&]*'
RM_RECURSIVE_RE='[[:space:]]-[[:alnum:]]*[rR]|--recursive'
# shellcheck disable=SC2016  # $HOME is a literal regex token, not an expansion
RM_TARGET_RE='[[:space:]]["'\'']?(/|~|\$HOME|\$\{HOME(:?[?][^}]*)?\})["'\'']?(/\*?|\*)?["'\'']?\*?([[:space:]]|$)'
while IFS= read -r command_segment; do
  if [[ "$command_segment" =~ $RM_SEG_RE ]]; then
    seg="${BASH_REMATCH[0]}"
  else
    continue
  fi
  if [[ "$seg" =~ $RM_RECURSIVE_RE ]] && [[ "$seg" =~ $RM_TARGET_RE ]]; then
    echo "Blocked: recursive rm targeting \$HOME or a filesystem root. Scope the deletion to a specific subdirectory instead." >&2
    exit 2
  fi
done < <(printf '%s\n' "$COMMAND" | tr ';|&' '\n')

# --- download-and-execute pipeline ------------------------------------------
FETCH_PIPE_RE='(curl|wget|aria2c|httpie|fetch)[^|;&]*\|[[:space:]]*(sudo[[:space:]]+)?(/[^[:space:]]*/)?(sh|bash|zsh|dash|ksh|python[0-9.]*|perl|ruby|node)([[:space:]]|$)'
if [[ "$COMMAND" =~ $FETCH_PIPE_RE ]]; then
  echo "Blocked: piping a downloaded script directly into an interpreter. Download to a file first, let the user inspect it, then execute it as an explicit separate step." >&2
  exit 2
fi

exit 0
