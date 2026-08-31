#!/usr/bin/env bash
# PostToolUse hook (matcher: Bash): masks credential-shaped values in a
# command's stdout/stderr before the model sees them. A `cat` of a config
# file, a `printenv`, or a verbose CLI that echoes its token would otherwise
# put the live value into the transcript, where it stays for the rest of the
# session and in the JSONL on disk.
# Detection is gitleaks' default rule set over the combined output; every
# distinct Secret it reports is replaced with [REDACTED] in both streams and
# the tool result is rewritten through hookSpecificOutput.updatedToolOutput.
# Never blocks. Fails open: no gitleaks, no jq, no tool_response object, or an
# output over the size cap means the result passes through untouched.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_OUTPUT_SECRET_MASK=1 to disable this hook. Checked after
# stdin is drained so a disabled hook never leaves the harness writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_OUTPUT_SECRET_MASK:-}" ]] && exit 0

command -v gitleaks >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

# Only the two text streams are scanned; a tool_response that is not an object
# (older payload shapes) is left alone.
TEXT=$(printf '%s' "$HOOK_INPUT" | jq -r '
  if (.tool_response | type) == "object"
  then [.tool_response.stdout, .tool_response.stderr] | map(select(type == "string")) | join("\n")
  else "" end' 2>/dev/null || true)
[[ -n "$TEXT" ]] || exit 0

# Above 2 MB the scan would start to be the slow part of the tool call; such
# outputs are dumps the user asked for, not a leaked token.
[[ ${#TEXT} -le 2097152 ]] || exit 0

REPORT=$(mktemp "${TMPDIR:-/tmp}/output-secret-mask.XXXXXX")
trap 'rm -f "$REPORT"' EXIT

printf '%s\n' "$TEXT" | gitleaks stdin --no-banner --exit-code 0 --report-format json \
  --report-path "$REPORT" --log-level error >/dev/null 2>&1 || exit 0

# gitleaks leaves the report empty when nothing matched. Very short "secrets"
# would mask ordinary words, so only values of 8+ characters are replaced.
SECRETS=$(jq -c '[.[].Secret | select(type == "string" and length >= 8)] | unique' "$REPORT" 2>/dev/null || echo '[]')
[[ "$SECRETS" != "[]" ]] || exit 0

printf '%s' "$HOOK_INPUT" | jq -c --argjson secrets "$SECRETS" '
  def mask: if type == "string" then reduce $secrets[] as $s (.; split($s) | join("[REDACTED]")) else . end;
  (.tool_response | .stdout |= mask | .stderr |= mask) as $updated
  | {hookSpecificOutput: {
      hookEventName: "PostToolUse",
      updatedToolOutput: $updated,
      additionalContext: ("guard-hooks: masked \($secrets | length) credential-shaped value(s) in the output of this command; [REDACTED] marks each one. Treat the value as live — do not try to recover, echo, or write it.")
    }}' 2>/dev/null || exit 0
