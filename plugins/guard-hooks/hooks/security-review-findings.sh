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
# Two shapes must be handled or findings are silently lost: the verdict nests as
# {"findings": {"findings": [...]}} in roughly 7% of calls, and the project slug
# is the FULL repository path with every `/`, `.` and `_` dashed, so a basename
# is not a substring of it (`/Users/x/.claude` → `-Users-x--claude`).

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

if [[ -z "$PRINT_MODE" ]]; then
  COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  [[ -n "$COMMAND" ]] || exit 0
  # `git … commit` with any global options between (`-C <path>`, a quoted path
  # with whitespace, `-c key=value`, `--no-pager`). This recognizer is loose on
  # purpose: the hook only warns, so matching a `git log --grep commit` costs a
  # lookup that finds nothing, while missing a real commit loses the one moment
  # this hook exists for. Parsing git's argument grammar properly is
  # staged-secret-guard's job, where a wrong answer has consequences.
  printf '%s' "$COMMAND" | grep -Eq '(^|[[:space:];&|(])git([[:space:]]+[^[:space:]]+)*[[:space:]]+commit([[:space:]]|$)' || exit 0
  CWD=$(printf '%s' "$HOOK_INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
  [[ -n "$CWD" ]] || exit 0
fi

REPO_ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -n "$REPO_ROOT" ]] || exit 0

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SLUG=$(printf '%s' "$REPO_ROOT" | tr './_' '-')
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
