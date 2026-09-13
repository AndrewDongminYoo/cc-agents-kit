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
# `--print [--full] [cwd]` runs the same lookup from a terminal (no hook JSON
# on stdin) and prints plain text; a git pre-commit action calls it that way,
# so it is cut at the same 200 lines as the hook report unless `--full` asks
# for everything.
#
# The same report is not repeated: a session that has already been shown it
# is silent on its next commit until the findings change (state under
# $TMPDIR, keyed by the hook's session_id), so semantic-commit splitting does
# not inject the identical text three to five times per session.
#
# Two things must be handled or findings are silently lost: the verdict nests
# as {"findings": {"findings": [...]}} in roughly 7% of calls; and the project
# slug is the session's FULL cwd with every character that is not a letter or
# digit dashed, so a basename is not a substring of it
# (`/Users/me/.claude` → `-Users-me--claude`).

set -euo pipefail

PRINT_MODE=""
PRINT_FULL=""
if [[ "${1:-}" == "--print" ]]; then
  PRINT_MODE=1
  shift
  if [[ "${1:-}" == "--full" ]]; then
    PRINT_FULL=1
    shift
  fi
  # The physical path: Claude Code keys projects/ by process.cwd(), which has
  # symlinks resolved, so a logical $PWD under a symlink would miss the
  # directory (`/tmp` is `/private/tmp` on macOS). Also drops a trailing slash.
  CWD=$(cd "${1:-.}" 2>/dev/null && pwd -P) || exit 0
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
    -C | -c | --git-dir | --work-tree | --namespace | --super-prefix | --config-env | --list-cmds | --attr-source) return 0 ;;
    *) return 1 ;;
  esac
}

# Global options after which git prints something and exits without
# dispatching a subcommand, so `git --version commit` is not a commit.
# A bare `--exec-path` prints the path; `--exec-path=<dir>` sets it.
is_terminal() {
  case "$1" in
    --version | -v | --help | -h | --html-path | --man-path | --info-path | --exec-path) return 0 ;;
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
        is_terminal "$tok" && return 1
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

# One shell segment (`git …`) as an array of tokens: strip a subshell paren,
# an environment-assignment prefix and `command`, compare the basename of
# what is left with `git`, and hand the rest to the option walk.
segment_is_git_commit() {
  local -a words=("$@")
  ((${#words[@]})) || return 1
  # `(git commit …)`: the subshell paren rides on the first token.
  words[0]=${words[0]#"${words[0]%%[!(]*}"}
  # `GIT_EDITOR=true git commit`, `env GIT_EDITOR=true git commit`,
  # `command git commit`, `exec git commit`: skip the prefix words.
  while ((${#words[@]})) && [[ "${words[0]}" =~ ^(command|env|exec|time|nohup)$ || "${words[0]}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; do
    words=("${words[@]:1}")
  done
  ((${#words[@]})) || return 1
  # `/usr/bin/git commit`: compare the basename.
  [[ "${words[0]##*/}" == git ]] || return 1
  is_git_commit_segment "${words[@]:1}"
}

# Does the command contain a `git … commit`? Each line is tokenised through
# xargs, which honours shell quoting without evaluating anything, and the
# token stream is cut at the control operators that stand alone as tokens —
# so a `;` inside `-C "/a;b"` stays inside its token instead of cutting the
# command before `commit`. Line continuations are joined first, and the
# operators are padded with spaces before tokenising so `x;git` splits too.
# A heredoc body is data: the lines after `<<EOF` up to the `EOF` line are
# skipped, so writing a script that contains `git commit` is not a commit,
# while `git commit -m "$(cat <<'EOF'` is still read from the line that
# opens the heredoc.
has_git_commit() {
  local command=$1 line tok heredoc="" opens probe
  local -a words
  local heredoc_re="<<-?[[:space:]]*[\"']?([A-Za-z_][A-Za-z0-9_]*)"
  # `git -C /repo \` + newline + `commit`: one logical line.
  command=${command//\\$'\n'/ }
  while IFS= read -r line; do
    if [[ -n "$heredoc" ]]; then
      # `<<-` lets the terminator carry leading tabs.
      [[ "${line#"${line%%[!$'\t']*}"}" == "$heredoc" ]] && heredoc=""
      continue
    fi
    # Does this line open a heredoc? A here-string `<<<` is not one.
    opens=""
    probe=${line//<<</ }
    [[ "$probe" =~ $heredoc_re ]] && opens=${BASH_REMATCH[1]}
    # Only a line that names git is worth tokenising: xargs costs ~8 ms per
    # call, and a heredoc body of a thousand lines would otherwise hold the
    # hook for eight seconds after a command that merely contains the word.
    if [[ "$line" != *git* ]]; then
      heredoc=$opens
      continue
    fi
    # One token per line, collected without a second round of word splitting
    # so a quoted `-C "/a b"` stays one token (bash 3.2: no mapfile). -n1, one
    # printf per token, is deliberate: when a line ends inside a quote — the
    # first line of `git commit -m "$(cat <<'EOF'` — xargs -n1 has already
    # printed the tokens before the unterminated quote, while a batched printf
    # prints nothing at all.
    words=()
    while IFS= read -r tok; do
      case "$tok" in
        ';' | '&&' | '||' | '|')
          ((${#words[@]})) && segment_is_git_commit "${words[@]}" && return 0
          words=()
          ;;
        *) words+=("$tok") ;;
      esac
    done < <(printf '%s\n' "$line" | sed -E 's/(&&|\|\||;|\|)/ \1 /g' | xargs -n1 printf '%s\n' 2>/dev/null)
    ((${#words[@]})) && segment_is_git_commit "${words[@]}" && return 0
    heredoc=$opens
  done <<<"$command"
  return 1
}

if [[ -z "$PRINT_MODE" ]]; then
  COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  [[ -n "$COMMAND" ]] || exit 0
  # Cheap pre-filter so every Bash call that is nowhere near a commit exits
  # here; the real decision is the parse below. A shell match, not a pipe
  # into grep: on a multi-line command past the pipe buffer, grep -q would
  # exit at the first match, the printf would take SIGPIPE, and pipefail
  # would turn that TRUE match into a silent exit.
  [[ "$COMMAND" == *commit* ]] || exit 0
  has_git_commit "$COMMAND" || exit 0
  CWD=$(printf '%s' "$HOOK_INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
  [[ -n "$CWD" ]] || exit 0
  SESSION_ID=$(printf '%s' "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
fi

# The findings belong to the SESSION, not to a repository. Claude Code stores
# every session — the automatic reviews included — under a directory named for
# the session's cwd, so the cwd the hook input reports is the lookup key: the
# hook reads no `-C`, `cd`, or `--git-dir` out of the command, and does not
# walk up to the repository root — a session opened in /repo/subdir lives
# under `-repo-subdir`. The rule is the one context-handoff/bin/session-to-md
# already uses — every character that is not a letter or digit becomes a dash.
# That rule is a JavaScript regex without the `u` flag, so it works on UTF-16
# code units: a character outside the BMP (an emoji) is two dashes. The jq
# below reproduces that per code point rather than per byte, which `tr -c`
# under a C locale would do, turning one Korean character into three dashes.
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SLUG=$(printf '%s' "$CWD" | jq -Rr '
  explode
  | map(if (. >= 48 and . <= 57) or (. >= 65 and . <= 90) or (. >= 97 and . <= 122) then [.]
        elif . > 65535 then [45, 45]
        else [45] end)
  | flatten | implode' 2>/dev/null || true)
[[ -n "$SLUG" ]] || exit 0
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
    | "\($d)  \(.filePath // "?")  [\(.category // "?")] \(.severity // "?")/\(.confidence // "?")\n    \((.explanation // .description // "") | gsub("\\s+"; " ") | .[0:300])"
  ' 2>/dev/null || true)
  [[ -n "$rows" ]] && FINDINGS="${FINDINGS:+$FINDINGS
}$rows"
done < <(find "$PROJECT_DIR" -maxdepth 1 -name '*.jsonl' -mtime -2 2>/dev/null)

[[ -n "$FINDINGS" ]] || exit 0

# Cap the report: a session with hundreds of findings would otherwise push
# the whole text through one argument, and past ARG_MAX that turns a warning
# into a hook error after every commit. The report goes through stdin as
# well, so the cap is a courtesy to the reader rather than the only guard —
# and --print, which a pre-commit action runs before every terminal commit,
# is cut the same way unless --full asks for the whole list.
# The dedupe below compares the UNCUT findings, so a change past the cap in
# a report of the same length is still shown.
FINDINGS_SUM=$(printf '%s' "$FINDINGS" | cksum 2>/dev/null || true)
MAX_LINES=200
TOTAL_LINES=$(printf '%s\n' "$FINDINGS" | wc -l | tr -d ' ')
if [[ -z "$PRINT_FULL" ]] && ((TOTAL_LINES > MAX_LINES)); then
  # sed, not head: head closes the pipe after MAX_LINES and the printf behind
  # it dies of SIGPIPE, which pipefail then turns into a hook error.
  FINDINGS=$(printf '%s\n' "$FINDINGS" | sed -n "1,${MAX_LINES}p")
  FINDINGS="$FINDINGS
    … $((TOTAL_LINES - MAX_LINES)) more line(s) not shown; run security-review-findings.sh --print --full for the full list"
fi

MSG="Automatic security review flagged this session's project in the last two days (warning only — nothing is blocked):
$FINDINGS"

if [[ -n "$PRINT_MODE" ]]; then
  printf '%s\n' "$MSG"
else
  # Once per session: a checksum of the uncut findings is kept under $TMPDIR
  # keyed by the session id, and the same findings on the next commit are not
  # repeated. A session without an id, or a state directory that cannot be
  # written, simply gets the report every time.
  if [[ -n "${SESSION_ID:-}" && -n "$FINDINGS_SUM" && "$SESSION_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
    STATE_DIR="${TMPDIR:-/tmp}/cc-guard-security-findings"
    STATE="$STATE_DIR/$SESSION_ID.last"
    [[ "$(cat "$STATE" 2>/dev/null || true)" == "$FINDINGS_SUM" ]] && exit 0
    { mkdir -p "$STATE_DIR" && printf '%s' "$FINDINGS_SUM" >"$STATE"; } 2>/dev/null || true
  fi
  # stdin, not --arg: the report is not an argument, so it cannot hit ARG_MAX.
  # A jq failure here must not become a hook error — fail open, like every
  # other exit in this file.
  printf '%s' "$MSG" | jq -Rs '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: .}}' 2>/dev/null || exit 0
fi
