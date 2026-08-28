#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash): blocks a formatter or rewriter invoked with
# no path argument, where its no-path default is "everything reachable".
# `jsonsort` with no file opens an interactive picker and walks the tree (its
# own --help says so); `trunk fmt` with no path formats every changed file;
# `ruff format` defaults to the working directory. One of these turns a
# verification step into a repo-wide rewrite that reads as a formatting diff.
# Tools that error out without a path (black, dart format) are not listed —
# they already fail loudly. Must fail open (exit 0) on any empty/malformed
# input so unrelated tool calls are never blocked.

set -euo pipefail

HOOK_INPUT=$(cat 2>/dev/null || echo '{}')

# Opt-out: set CC_GUARD_DISABLE_PATHLESS_REWRITER=1 to disable this hook. Checked after stdin is
# drained so a disabled hook never leaves the harness writing to a closed pipe.
[[ -n "${CC_GUARD_DISABLE_PATHLESS_REWRITER:-}" ]] && exit 0
COMMAND=$(printf '%s' "$HOOK_INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
[[ -z "$COMMAND" ]] && exit 0

# "<invocation>|<write flags, space separated>" — an empty flag field means the
# tool always writes, so a missing path alone is enough to block.
REWRITERS=(
  'jsonsort|'
  'sortjson|'
  'trunk fmt|'
  'ruff format|'
  'prettier|-w --write'
  'eslint|--fix'
  'shfmt|-w'
)
RUNNERS=('npx --yes' 'npx -y' npx bunx uvx 'pnpm dlx' 'pnpm exec' 'uv run' 'poetry run' 'yarn dlx')

has_token() { # has_token "<haystack>" "<needle> [<needle>...]"
  local haystack=" $1 " needle
  for needle in $2; do
    [[ "$haystack" == *" $needle "* || "$haystack" == *" $needle="* ]] && return 0
  done
  return 1
}

while IFS= read -r segment; do
  # Collapse whitespace so the literal comparisons below are exact.
  segment=$(printf '%s' "$segment" | tr -s '[:space:]' ' ')
  segment="${segment# }"
  segment="${segment% }"

  # Strip subshell/brace delimiters, leading env assignments, and package runners.
  while [[ "$segment" == \(* || "$segment" == \{* ]]; do
    segment="${segment#?}"
    segment="${segment# }"
  done
  while [[ "$segment" == *\) || "$segment" == *\} ]]; do
    segment="${segment%?}"
    segment="${segment% }"
  done
  while [[ "$segment" =~ ^[A-Za-z_][A-Za-z0-9_]*=[^\ ]*\ (.*)$ ]]; do
    segment="${BASH_REMATCH[1]}"
  done
  for runner in "${RUNNERS[@]}"; do
    [[ "$segment" == "$runner "* ]] && segment="${segment#"$runner" }"
  done
  if [[ "$segment" == "--" ]]; then
    segment=""
  elif [[ "$segment" == "-- "* ]]; then
    segment="${segment#-- }"
  fi
  # Drop a leading directory on the binary: /opt/homebrew/bin/prettier -> prettier
  first="${segment%% *}"
  [[ "$first" == */* ]] && segment="${first##*/}${segment#"$first"}"

  for entry in "${REWRITERS[@]}"; do
    tool="${entry%%|*}"
    write_flags="${entry#*|}"
    candidate="$segment"
    first="${candidate%% *}"
    tool_command="${tool%% *}"
    if [[ "$first" == "$tool_command"@* ]]; then
      candidate="$tool_command${candidate#"$first"}"
    fi

    [[ "$candidate" == "$tool" || "$candidate" == "$tool "* ]] || continue

    rest="${candidate#"$tool"}"
    # A write-mode tool is only dangerous once it is actually writing.
    if [[ -n "$write_flags" ]] && ! has_token "$rest" "$write_flags"; then
      continue
    fi

    # Anything that is not a flag counts as the path the rule asks for.
    has_path=""
    skip_value=""
    for token in $rest; do
      if [[ -n "$skip_value" ]]; then
        skip_value=""
        continue
      fi
      case "$token" in
        --config)
          [[ "$tool" == "ruff format" ]] && skip_value=1
          ;;
        -*) ;;
        *)
          has_path=1
          break
          ;;
      esac
    done
    [[ -n "$has_path" ]] && continue

    echo "Blocked: \`$tool\` invoked with no path argument. With no path it rewrites everything it can reach — that is how a verification step becomes a repo-wide formatting diff. Pass an explicit file, directory, or quoted glob." >&2
    exit 2
  done
done < <(printf '%s\n' "$COMMAND" | tr ';|&' '\n')

exit 0
