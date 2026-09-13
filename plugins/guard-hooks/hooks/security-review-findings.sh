#!/usr/bin/env bash
# PostToolUse hook (matcher: Bash): right after a `git commit`, surface any
# finding the harness's automatic security-review subsessions produced for
# this session's project in the last two days.
#
# When the harness runs its automatic review of an edit, it does so in a
# background session whose first prompt is `Review this change for security
# vulnerabilities.`, stored beside the session that made the edit. Those
# sessions commit nothing and modify nothing, so a finding they produce has no
# delivery path: measured over seven weeks on one machine, 448 such sessions
# ran, 437 of 450 verdicts were empty, and the 12 unique findings in the rest —
# prompt-injection in a workflow, a secret-exposure regression in
# settings.json, an account-separation bypass — were never surfaced anywhere a
# session could read them. (Not every edit gets one: the same machine went a
# whole session of dozens of edits with none, so this hook is silent then.)
#
# This hook is that path. It WARNS and never blocks: the findings describe work
# that is already committed or already discarded, and some are false positives.
# It runs after the commit rather than before because PreToolUse has no
# additionalContext channel — only PostToolUse does — and the timing costs
# nothing for findings about already-committed work.
#
# `--print [cwd]` runs the same lookup from a terminal (no hook JSON on stdin)
# and prints plain text; a git pre-commit action can call it that way.
#
# Two things must be handled or findings are silently lost: the verdict nests
# as {"findings": {"findings": [...]}} in roughly 7% of calls; and the project
# slug is the session's FULL cwd with every character that is not a letter or
# digit dashed, so a basename is not a substring of it
# (`/Users/me/.claude` → `-Users-me--claude`).

set -euo pipefail

PRINT_MODE=""
if [[ "${1:-}" == "--print" ]]; then
  PRINT_MODE=1
  CWD="${2:-$PWD}"
else
  HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
fi

# Opt-out: set CC_GUARD_DISABLE_SECURITY_FINDINGS=1 to disable this hook. Checked after stdin is
# drained so a disabled hook never leaves the harness writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_SECURITY_FINDINGS:-}" ]] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

# Global git options that take a separate value, consumed so the token after
# them is never mistaken for the subcommand. Their values are not used: the
# findings live under the SESSION's project directory (see below), not under
# whichever repository the commit lands in.
takes_value() {
  case "$1" in
    -C | -c | --git-dir | --work-tree | --namespace | --super-prefix | --exec-path | --config-env | --list-cmds | --attr-source) return 0 ;;
    *) return 1 ;;
  esac
}

# Walk one shell segment (`git …`), consuming git's global options, and answer
# whether the subcommand is `commit`. Position decides, so `git log --grep
# commit` is not a commit and `git -c commit.gpgSign=false commit` is.
is_git_commit_segment() {
  local tok
  while (($#)); do
    tok=$1
    shift
    case "$tok" in
      -C | -c)
        (($#)) || return 1
        shift
        ;;
      -C* | -c*) ;; # attached forms, `-C/path` and `-ckey=value`
      --*=*) ;;
      -*)
        if takes_value "$tok"; then
          (($#)) || return 1
          shift
        fi
        ;;
      commit) return 0 ;;
      *) return 1 ;;
    esac
  done
  return 1
}

# Does the command contain a `git … commit`? Segments are split on shell
# control operators and each is tokenised through xargs, which honours shell
# quoting without evaluating anything; a segment it cannot tokenise is skipped.
has_git_commit() {
  local command=$1 seg tok
  local -a words
  while IFS= read -r seg; do
    seg=${seg#"${seg%%[![:space:]]*}"}
    [[ -n "$seg" ]] || continue
    # One token per line, collected without a second round of word splitting
    # so a quoted `-C "/a b"` stays one token (bash 3.2: no mapfile).
    words=()
    while IFS= read -r tok; do words+=("$tok"); done < <(printf '%s\n' "$seg" | xargs -n1 printf '%s\n' 2>/dev/null)
    ((${#words[@]})) || continue
    # `(git commit …)`: the subshell paren rides on the first token. Splitting
    # segments on parens instead would cut a `-m "fix (x)"` in half.
    words[0]=${words[0]#"${words[0]%%[!(]*}"}
    [[ "${words[0]}" == git ]] || continue
    is_git_commit_segment "${words[@]:1}" && return 0
  done < <(printf '%s\n' "$command" | sed -E 's/&&|\|\||;|\|/\
/g')
  return 1
}

if [[ -z "$PRINT_MODE" ]]; then
  COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  [[ -n "$COMMAND" ]] || exit 0
  # Cheap pre-filter so every Bash call that is nowhere near a commit exits
  # after one grep; the real decision is the parse below.
  printf '%s' "$COMMAND" | grep -q commit || exit 0
  has_git_commit "$COMMAND" || exit 0
  CWD=$(printf '%s' "$HOOK_INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
  [[ -n "$CWD" ]] || exit 0
fi

# The findings belong to the SESSION, not to a repository. Claude Code stores
# every session — the automatic reviews included — under a directory named for
# the session's cwd, so that cwd is the lookup key, untouched by `-C`, `cd`, or
# `--git-dir` in the commit command and not walked up to the repository root:
# a session opened in /repo/subdir lives under `-repo-subdir`. The rule is the
# one context-handoff/bin/session-to-md already uses — every character that is
# not a letter or digit becomes a dash — so a path with spaces or any other
# punctuation still lands on the directory Claude Code actually wrote.
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SLUG=$(printf '%s' "$CWD" | tr -c 'A-Za-z0-9' '-')
PROJECT_DIR="$CONFIG_DIR/projects/$SLUG"
[[ -d "$PROJECT_DIR" ]] || exit 0

AUTO_PROMPT='Review this change for security vulnerabilities.'
FINDINGS=""
while IFS= read -r file; do
  [[ -n "$file" ]] || continue
  # The first user entry decides whether this is an automatic review; a later
  # session that merely quotes the prompt must not count.
  grep -m1 -E '"type": ?"user"' "$file" 2>/dev/null | grep -qF "$AUTO_PROMPT" || continue
  stamp=$(grep -m1 -oE '"timestamp": ?"[0-9-]*' "$file" 2>/dev/null | head -1 | sed -E 's/.*"([0-9-]*)$/\1/' || true)
  rows=$(grep -F StructuredOutput "$file" 2>/dev/null | jq -r --arg d "${stamp:-?}" '
    select(.type == "assistant")
    | (.message.content // [])[]?
    | select(type == "object" and .name == "StructuredOutput")
    | .input.findings
    | until(type != "object" or (has("findings") | not); .findings)
    | select(type == "array")
    | .[]
    | select(type == "object")
    | "\($d)  \(.filePath // "?")  [\(.category // "?")]\n    \((.explanation // .description // "") | gsub("\\s+"; " ") | .[0:300])"
  ' 2>/dev/null || true)
  [[ -n "$rows" ]] && FINDINGS="${FINDINGS:+$FINDINGS
}$rows"
done < <(find "$PROJECT_DIR" -maxdepth 1 -name '*.jsonl' -mtime -2 2>/dev/null)

[[ -n "$FINDINGS" ]] || exit 0

# Cap the report: a session with hundreds of findings would otherwise push the
# whole text through one argument, and past ARG_MAX that turns a warning into
# a hook error after every commit. The report goes through stdin as well, so
# the cap is a courtesy to the reader rather than the only guard.
MAX_LINES=200
TOTAL_LINES=$(printf '%s\n' "$FINDINGS" | wc -l | tr -d ' ')
if ((TOTAL_LINES > MAX_LINES)); then
  # sed, not head: head closes the pipe after MAX_LINES and the printf behind
  # it dies of SIGPIPE, which pipefail then turns into a hook error.
  FINDINGS=$(printf '%s\n' "$FINDINGS" | sed -n "1,${MAX_LINES}p")
  FINDINGS="$FINDINGS
    … $((TOTAL_LINES - MAX_LINES)) more line(s) not shown; run with --print for the full list"
fi

MSG="Automatic security review flagged this session's project in the last two days (warning only — nothing is blocked):
$FINDINGS"

if [[ -n "$PRINT_MODE" ]]; then
  printf '%s\n' "$MSG"
else
  # stdin, not --arg: the report is not an argument, so it cannot hit ARG_MAX.
  # A jq failure here must not become a hook error — fail open, like every
  # other exit in this file.
  printf '%s' "$MSG" | jq -Rs '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: .}}' 2>/dev/null || exit 0
fi
