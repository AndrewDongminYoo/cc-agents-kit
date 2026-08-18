#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash): scans the staged diff for credentials before
# a `git commit` runs. This is the commit-time counterpart to
# secrets-path-guard.sh, which blocks *reading* secret files — a value can
# still reach a diff by being typed, pasted, or written by a generator, and
# review is too late once it is in a commit.
# High-confidence patterns only: a guard that cries wolf gets switched off.
# It is not a replacement for a full scanner — run trufflehog or gitleaks in CI
# for entropy-based detection. Must fail open (exit 0) on any empty/malformed
# input so unrelated tool calls are never blocked.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_STAGED_SECRET=1 to disable this hook. Checked after stdin is
# drained so a disabled hook never leaves the harness writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_STAGED_SECRET:-}" ]] && exit 0
COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -z "$COMMAND" ]] && exit 0

# Only act on a real `git commit` invocation at a command position, so prose or
# an argument mentioning it is not mistaken for one.
GIT_COMMIT_RE='(^|[;|&(][[:space:]]*)(([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+)*)?(/[^[:space:]]*/)?git([[:space:]]+-[cC][[:space:]]+[^[:space:]]+)*[[:space:]]+commit([[:space:]]|$)'
[[ "$COMMAND" =~ $GIT_COMMIT_RE ]] || exit 0

# Honour `git -C <path>` so the scan reads the repository being committed to.
REPO_ARGS=()
if [[ "$COMMAND" =~ git[[:space:]]+-C[[:space:]]+([^[:space:]]+) ]]; then
  REPO_ARGS=(-C "${BASH_REMATCH[1]//\"/}")
fi

# `${a[@]+"${a[@]}"}` not `"${a[@]}"`: under `set -u`, bash 3.2 — the version at
# /bin/bash on macOS — treats an empty array expansion as an unbound variable and
# aborts. With the `|| true` below that would swallow the abort and leave DIFF
# empty, silently turning the guard off on exactly the machines it targets.
DIFF=$(git ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} diff --cached 2>/dev/null || true)
[[ -n "$DIFF" ]] || exit 0

# Added lines only — an existing secret being deleted must not block its removal.
ADDED=$(printf '%s\n' "$DIFF" | grep -E '^\+' | grep -Ev '^\+\+\+' || true)
[[ -n "$ADDED" ]] || exit 0

# Each entry is "<label>|<extended regex>".
PATTERNS=(
  'npm auth token|_authToken[[:space:]]*=[[:space:]]*[^[:space:]$"'"'"']{16,}'
  'GitHub token|gh[pousr]_[A-Za-z0-9]{36,}'
  'OpenAI-style key|sk-[A-Za-z0-9_-]{20,}'
  'Anthropic key|sk-ant-[A-Za-z0-9_-]{20,}'
  'AWS access key id|AKIA[0-9A-Z]{16}'
  'Slack token|xox[baprs]-[A-Za-z0-9-]{10,}'
  'Google API key|AIza[A-Za-z0-9_-]{35}'
  'private key block|-----BEGIN[A-Z ]*PRIVATE KEY-----'
  'PyPI token|pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{10,}'
)

HITS=""
for entry in "${PATTERNS[@]}"; do
  label="${entry%%|*}"
  regex="${entry#*|}"
  # -e is required: a pattern starting with `-` is otherwise read as an option.
  match=$(printf '%s\n' "$ADDED" | grep -Eom1 -e "$regex" || true)
  [[ -n "$match" ]] || continue
  # Show enough to identify the line, never the whole value.
  HITS="${HITS}  - ${label}: ${match:0:12}…"$'\n'
done

[[ -n "$HITS" ]] || exit 0

printf 'Blocked: the staged diff contains what looks like a live credential.\n%s\nUnstage it, move the value to the environment or the keychain, and rotate it if it was ever written to disk. If this is a fixture or a documented example, set CC_GUARD_DISABLE_STAGED_SECRET=1 for this one command.\n' "$HITS" >&2
exit 2
