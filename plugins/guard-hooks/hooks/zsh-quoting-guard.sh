#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash): catch the two zsh quoting mistakes that keep
# recurring across sessions, both of which fail *silently or destructively*
# rather than with an obvious syntax error.
#
#   1. A backtick inside a double-quoted commit/PR message. zsh runs it as
#      command substitution, so the backticked word is deleted from the message
#      (and its "command not found" is easy to miss in the commit output).
#   2. An unquoted glob in an option value (--include=*.dart, -name *.md).
#      What zsh does depends on how many files in the CWD match, and only one
#      of the three outcomes is quiet: no match aborts the whole command
#      (`nomatch`), several expand to a list the tool rejects, and exactly one
#      expands to that filename — so the tool searches a single file instead of
#      the pattern, exits 0, and the answer looks complete.
#
# Regex on the command string — a guardrail against an accidental slip, not a
# parser. Must fail open (exit 0) on any empty/malformed input.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_ZSH_QUOTING=1 to disable this hook. Checked after stdin is
# drained so a disabled hook never leaves the harness writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_ZSH_QUOTING:-}" ]] && exit 0
COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -z "$COMMAND" ]] && exit 0

# A quoted heredoc delimiter (<<'EOF') makes its whole body literal, and that
# body is usually prose — including prose ABOUT these mistakes. Scan only what
# precedes it. An unquoted <<EOF still interpolates, so it is not exempted.
# Note this also discards anything chained AFTER the heredoc terminator —
# deliberate fail-open, consistent with the guardrail contract above.
SCAN="$COMMAND"
if [[ "$SCAN" =~ \<\<[[:space:]]*[\'\"] ]]; then
  SCAN=${SCAN%%<<*}
fi

# --- 1. backtick in a message-carrying command -------------------------------
MSG_CMD_RE='(git[[:space:]]+commit|git[[:space:]]+tag[[:space:]]+-a|gh[[:space:]]+(pr|issue|release)[[:space:]]+(create|comment|edit))'
if [[ "$SCAN" =~ $MSG_CMD_RE ]]; then
  # -F/--body-file read the message from a file: already the safe carrier.
  # `-F -` is not one — it reads stdin, which an unquoted heredoc interpolates.
  if [[ ! "$SCAN" =~ (-F[[:space:]]+[^-[:space:]]|--file[[:space:]]+[^-[:space:]]|--body-file|--notes-file) ]]; then
    # Strip single-quoted spans and backslash-escaped backticks: both are literal.
    stripped=${SCAN//\\\`/}
    stripped=$(printf '%s' "$stripped" | sed "s/'[^']*'//g")
    if [[ "$stripped" == *'`'* ]]; then
      echo "Blocked: a backtick inside a double-quoted message runs as command substitution in zsh — the backticked word is silently deleted from the message. Write the message to a file and pass it with -F/--body-file, or single-quote it." >&2
      exit 2
    fi
  fi
fi

# --- 2. unquoted glob in an option value -------------------------------------
GLOB_EQ_RE='--(include|exclude|glob|iglob|ignore)=[^"'\''[:space:]]*[*?]'
GLOB_ARG_RE='[[:space:]]-(name|iname|path|ipath)[[:space:]]+[^"'\''[:space:]]*[*?]'
if [[ "$SCAN" =~ $GLOB_EQ_RE ]] || [[ "$SCAN" =~ $GLOB_ARG_RE ]]; then
  echo "Blocked: unquoted glob pattern (${BASH_REMATCH[0]# }). zsh expands it against the CWD before the tool sees it: no match aborts the whole command, several become a filename list the tool rejects, and exactly one silently searches that single file instead of the pattern. Quote it: --include='*.dart', -name '*.md'." >&2
  exit 2
fi

exit 0
