#!/usr/bin/env bash
# PostToolUse hook (matcher: Bash): right after a `git commit`, surface any
# finding the harness's automatic security-review subsessions produced for
# this repository in the last two days.
#
# Every file edit spawns a background session whose first prompt is
# `Review this change for security vulnerabilities.`. Those sessions commit
# nothing and modify nothing, so a finding they produce has no delivery path:
# measured over seven weeks on one machine, 437 of 450 verdicts were empty and
# the 12 unique findings in the rest — prompt-injection in a workflow, a
# secret-exposure regression in settings.json, an account-separation bypass —
# were never surfaced anywhere a session could read them.
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
# Three things must be handled or findings are silently lost or misattributed:
# the verdict nests as {"findings": {"findings": [...]}} in roughly 7% of
# calls; the project slug is the FULL repository path with every character that
# is not a letter or digit dashed, so a basename is not a substring of it
# (`/Users/me/.claude` → `-Users-me--claude`); and `git -C <path> commit` runs
# in <path>, not in the hook's cwd, so the repository is taken from the command.

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

# Global git options that take a separate value. `-C` is handled on its own
# because its value decides which repository the findings belong to; the rest
# are consumed so the token after them is never mistaken for the subcommand.
takes_value() {
  case "$1" in
    -c | --git-dir | --work-tree | --namespace | --super-prefix | --exec-path | --config-env | --list-cmds | --attr-source) return 0 ;;
    *) return 1 ;;
  esac
}

# Walk one shell segment (`git …`), consuming git's global options, and answer
# whether its subcommand is `commit`. Sets COMMIT_DIR to the directory git
# would run in: the hook cwd, moved by every `-C <path>` in order, the way git
# applies them. Returns 1 for anything that is not a commit, and for a `-C`
# whose value this hook cannot resolve (a shell expansion, a missing path):
# reporting another repository's findings would be worse than silence.
is_git_commit_segment() {
  local base=$1
  shift
  local tok
  COMMIT_DIR=$base
  while (($#)); do
    tok=$1
    shift
    case "$tok" in
      -C)
        (($#)) || return 1
        case "$1" in
          *'$'* | *'`'*) return 1 ;;
          /*) COMMIT_DIR=$1 ;;
          *) COMMIT_DIR="$COMMIT_DIR/$1" ;;
        esac
        [[ -d "$COMMIT_DIR" ]] || return 1
        shift
        ;;
      -C*) # attached form, `-C/path`
        case "${tok#-C}" in
          *'$'* | *'`'*) return 1 ;;
          /*) COMMIT_DIR=${tok#-C} ;;
          *) COMMIT_DIR="$COMMIT_DIR/${tok#-C}" ;;
        esac
        [[ -d "$COMMIT_DIR" ]] || return 1
        ;;
      -c*) # `-c key=value` or attached `-ckey=value`
        [[ "$tok" == -c ]] && { (($#)) || return 1; shift; }
        ;;
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

# Find the first `git … commit` in the command. Segments are split on shell
# control operators; a leading `cd <absolute path>` segment moves the base
# directory the way it would for the segments after it. Tokenising each
# segment through xargs honours shell quoting (`-C "/a b"`) without evaluating
# anything; a segment it cannot tokenise is skipped.
find_commit_dir() {
  local command=$1 base=$2 seg tok
  local -a words
  COMMIT_DIR=""
  while IFS= read -r seg; do
    seg=${seg#"${seg%%[![:space:]]*}"}
    [[ -n "$seg" ]] || continue
    # One token per line from xargs, collected without a second round of word
    # splitting so a quoted `-C "/a b"` stays one token (bash 3.2: no mapfile).
    words=()
    while IFS= read -r tok; do words+=("$tok"); done < <(printf '%s\n' "$seg" | xargs -n1 printf '%s\n' 2>/dev/null)
    ((${#words[@]})) || continue
    # `(git commit …)`: the subshell paren rides on the first token. Splitting
    # segments on parens instead would cut a `-m "fix (x)"` in half.
    words[0]=${words[0]#"${words[0]%%[!(]*}"}
    case "${words[0]}" in
      cd)
        if ((${#words[@]} > 1)) && [[ "${words[1]}" == /* && "${words[1]}" != *'$'* && -d "${words[1]}" ]]; then base=${words[1]}; fi
        ;;
      git)
        if is_git_commit_segment "$base" "${words[@]:1}"; then return 0; fi
        ;;
    esac
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
  HOOK_CWD=$(printf '%s' "$HOOK_INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
  [[ -n "$HOOK_CWD" ]] || exit 0
  find_commit_dir "$COMMAND" "$HOOK_CWD" || exit 0
  CWD=$COMMIT_DIR
fi

REPO_ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -n "$REPO_ROOT" ]] || exit 0

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
# The same rule context-handoff/bin/session-to-md applies: every character that
# is not a letter or digit becomes a dash, so a path with spaces or any other
# punctuation still lands on the directory Claude Code actually wrote.
SLUG=$(printf '%s' "$REPO_ROOT" | tr -c 'A-Za-z0-9' '-')
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

MSG="Automatic security review flagged this repository in the last two days (warning only — nothing is blocked):
$FINDINGS"

if [[ -n "$PRINT_MODE" ]]; then
  printf '%s\n' "$MSG"
else
  jq -n --arg ctx "$MSG" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'
fi
