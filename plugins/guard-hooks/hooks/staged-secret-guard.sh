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

block_unparsed() {
  echo "Blocked: could not safely parse this git commit command. Run a single git commit with explicit, conventionally quoted arguments so the effective commit candidate can be scanned." >&2
  exit 2
}

# Separate message: the command above is usually not a commit at all, and the
# parse advice would send the reader looking for one that is not there.
block_config_override() {
  echo "Blocked: this command sets git configuration with -c or --config-env before a subcommand this hook cannot identify. Command-scoped config can rename commit through an alias, directly or through an include, so the staged diff cannot be cleared. Drop the -c override, or name the subcommand's real work in a separate command." >&2
  exit 2
}

unsafe_value() {
  [[ "$1" == *'$'* || "$1" == *'`'* || "$1" == *'<'* || "$1" == *'>'* ]]
}

# Tokenize the full input once without eval, expansion, or command execution.
# Shell operators and newlines become boundary tokens. A malformed quote blocks
# only if the token stream identifies an actual git commit invocation.
TOKENS=()
token=""
quote=""
escaped=""
token_started=""
# What kind of expansion the token being built carries: "" for none, "quoted"
# for one that cannot add words, "split" for one outside quotes that can. Both
# matter and they matter in different places -- "$x" is a single argument but
# can still BE the subcommand, while $x can also carry extra words after it. An
# escaped \$ and a '$x' in single quotes expand to nothing and stay empty.
token_expansion=""
TOKEN_EXPANSION=()
TOKENIZATION_ERROR=""
BOUNDARY_PREFIX=$'\034'
command_len=${#COMMAND}
command_pos=0
while ((command_pos < command_len)); do
  char="${COMMAND:command_pos:1}"
  if [[ -n "$escaped" ]]; then
    if [[ "$char" != $'\n' ]]; then
      token="$token$char"
      token_started=1
    fi
    escaped=""
  elif [[ "$quote" == "'" ]]; then
    if [[ "$char" == "'" ]]; then quote=""; else token="$token$char"; fi
  elif [[ "$quote" == '"' ]]; then
    if [[ "$char" == '"' ]]; then
      quote=""
    elif [[ "$char" == "\\" ]]; then
      escaped=1
    else
      token="$token$char"
      if [[ "$char" == '$' || "$char" == '`' ]] && [[ -z "$token_expansion" ]]; then
        token_expansion="quoted"
      fi
    fi
  else
    case "$char" in
      "'" | '"') quote="$char"; token_started=1 ;;
      "\\") escaped=1 ;;
      " " | $'\t')
        if [[ -n "$token_started" ]]; then TOKENS+=("$token"); TOKEN_EXPANSION+=("$token_expansion"); token=""; token_started=""; token_expansion=""; fi
        ;;
      $'\n')
        if [[ -n "$token_started" ]]; then TOKENS+=("$token"); TOKEN_EXPANSION+=("$token_expansion"); token=""; token_started=""; token_expansion=""; fi
        TOKENS+=("$BOUNDARY_PREFIX;")
        TOKEN_EXPANSION+=("")
        ;;
      ";" | "|" | "&" | "(" | ")")
        if [[ -n "$token_started" ]]; then TOKENS+=("$token"); TOKEN_EXPANSION+=("$token_expansion"); token=""; token_started=""; token_expansion=""; fi
        TOKENS+=("$BOUNDARY_PREFIX$char")
        TOKEN_EXPANSION+=("")
        ;;
      *)
        token="$token$char"
        token_started=1
        # Unquoted wins over a quoted expansion seen earlier in the token:
        # "$base"$d splits, however the first half was written.
        [[ "$char" == '$' || "$char" == '`' ]] && token_expansion="split"
        ;;
    esac
  fi
  ((command_pos += 1))
done
[[ -z "$quote" && -z "$escaped" ]] || TOKENIZATION_ERROR=1
if [[ -n "$token_started" ]]; then TOKENS+=("$token"); TOKEN_EXPANSION+=("$token_expansion"); fi

# "quoted" was shorthand for "one word", and for two forms that is wrong: "$@"
# and "${name[@]}" emit one word per element even inside quotes, so
# `args=(/repo commit -m x --); git -C "${args[@]}" log` really runs a commit.
# "$*" and "${name[*]}" do join to a single word and stay as they are. Upgrading
# here rather than mid-tokenizer keeps it one pass over finished tokens, where
# the whole form is visible instead of one character at a time.
for ((token_index = 0; token_index < ${#TOKENS[@]}; token_index++)); do
  [[ "${TOKEN_EXPANSION[token_index]-}" == "quoted" ]] || continue
  # shellcheck disable=SC2016  # the single quotes are the point: these are
  # literal spellings to match in the token, not expansions to perform.
  case "${TOKENS[token_index]}" in
    *'$@'* | *'${@'* | *'[@]'*) TOKEN_EXPANSION[token_index]="split" ;;
  esac
done

REPO_ARGS=()
commit_index=-1
commit_count=0
token_count=${#TOKENS[@]}
token_index=0
at_command_start=1
command_prefix=""
env_prefix=""
while ((token_index < token_count)); do
  current="${TOKENS[token_index]}"
  if [[ "$current" == "$BOUNDARY_PREFIX"* ]]; then
    at_command_start=1
    command_prefix=""
    env_prefix=""
    token_index=$((token_index + 1))
    continue
  fi
  if ((at_command_start)) && [[ "$current" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
    token_index=$((token_index + 1))
    continue
  fi
  if ((at_command_start)) && [[ "$current" == "command" ]]; then
    command_prefix=1
    token_index=$((token_index + 1))
    continue
  fi
  if ((at_command_start)) && [[ -n "$command_prefix" ]]; then
    case "$current" in
      -p) token_index=$((token_index + 1)); continue ;;
      --) command_prefix=""; token_index=$((token_index + 1)); continue ;;
    esac
  fi
  if ((at_command_start)) && [[ "$current" == "env" || "$current" == */env ]]; then
    env_prefix=1
    token_index=$((token_index + 1))
    continue
  fi
  if ((at_command_start)) && [[ -n "$env_prefix" ]]; then
    case "$current" in
      -i | --ignore-environment)
        token_index=$((token_index + 1))
        continue
        ;;
      -u | --unset)
        if ((token_index + 1 < token_count)) && [[ "${TOKENS[token_index + 1]}" != "$BOUNDARY_PREFIX"* ]]; then
          token_index=$((token_index + 2))
          continue
        fi
        ;;
      -u?* | --unset=*)
        token_index=$((token_index + 1))
        continue
        ;;
      --)
        env_prefix=""
        token_index=$((token_index + 1))
        continue
        ;;
    esac
  fi
  if ((at_command_start)) && [[ "$current" == "git" || "$current" == */git ]]; then
    scan_index=$((token_index + 1))
    candidate_repo_args=()
    # A global option this parser cannot resolve (-c, --no-pager, a -C value
    # with shell syntax) is only a problem when the subcommand turns out to be
    # `commit`. Defer the verdict: remember it, keep scanning for `commit`, and
    # let `git -C "$d" log` / `git --no-pager log` through untouched.
    pending_block=""
    config_override=""
    split_risk=""
    opaque_option=""
    scanned_past_commit=1
    while ((scan_index < token_count)); do
      current="${TOKENS[scan_index]}"
      [[ "$current" == "$BOUNDARY_PREFIX"* ]] && break
      # One splittable token anywhere ahead of the subcommand is enough: the
      # words it expands to are git's arguments and never reach this parser, so
      # nothing read after it can be trusted to be the subcommand.
      [[ "${TOKEN_EXPANSION[scan_index]-}" != split ]] || split_risk=1
      case "$current" in
        -C)
          if ((scan_index + 1 < token_count)) && [[ "${TOKENS[scan_index + 1]}" != "$BOUNDARY_PREFIX"* ]]; then
            unsafe_value "${TOKENS[scan_index + 1]}" && pending_block=1
            [[ "${TOKEN_EXPANSION[scan_index + 1]-}" != split ]] || split_risk=1
            candidate_repo_args+=("$current" "${TOKENS[scan_index + 1]}")
            scan_index=$((scan_index + 2))
          else
            pending_block=1
            scan_index=$((scan_index + 1))
          fi
          ;;
        -C?*)
          unsafe_value "${current:2}" && pending_block=1
          candidate_repo_args+=("${current:0:2}" "${current:2}")
          scan_index=$((scan_index + 1))
          ;;
        --version) break ;;
        # `git --help` lists exactly two global options that take a separate
        # value token: -C <path> and -c <name>=<value>. Every other long option
        # carries its value with `=`. Consuming -c's value is what keeps the
        # subcommand search honest: without it, `core.pager=cat` looks like the
        # subcommand and the scan runs on into the subcommand's own arguments.
        -c)
          pending_block=1
          config_override=1
          scan_index=$((scan_index + 2))
          ;;
        -c?* | --config-env*)
          pending_block=1
          config_override=1
          scan_index=$((scan_index + 1))
          ;;
        # The global options that take no value, from git's own synopsis. Naming
        # the flags rather than the value-takers is the direction that fails
        # safe: an option git adds later is unrecognised, and unrecognised means
        # refuse rather than mistake its value for the subcommand.
        -p | -P | --paginate | --no-pager | --bare | --exec-path | --html-path \
          | --man-path | --info-path | --no-replace-objects | --no-lazy-fetch \
          | --no-optional-locks | --no-advice | --literal-pathspecs \
          | --no-literal-pathspecs | --glob-pathspecs | --noglob-pathspecs \
          | --icase-pathspecs | --no-icase-pathspecs)
          pending_block=1
          scan_index=$((scan_index + 1))
          ;;
        --*=*)
          # The value rides along with the =, so nothing extra is consumed.
          pending_block=1
          scan_index=$((scan_index + 1))
          ;;
        --*)
          # Unrecognised and without an =, so the next token may be its value.
          # `git --git-dir /repo/.git commit -m x` is accepted by git and would
          # otherwise read /repo/.git as the subcommand.
          pending_block=1
          opaque_option=1
          scan_index=$((scan_index + 1))
          ;;
        commit)
          [[ -z "$pending_block" ]] || block_unparsed
          scanned_past_commit=""
          ((commit_count += 1))
          if ((commit_count == 1)); then
            commit_index=$scan_index
            if [[ -n "${candidate_repo_args[*]-}" ]]; then
              REPO_ARGS=("${candidate_repo_args[@]}")
            fi
          fi
          break
          ;;
        *)
          # The first token that is not a global option is the subcommand -- if
          # it is a literal. An expansion here resolves to a word this hook
          # cannot see, and `git "$cmd" -m x` with cmd=commit is a commit, so it
          # is refused whether or not it could also split. main has this hole
          # too; it is closed here because this branch owns the question of when
          # the scan may trust a token.
          [[ -z "${TOKEN_EXPANSION[scan_index]-}" ]] || block_unparsed
          # Scanning past it would read its own arguments, where a value such as
          # `--grep commit` is a search term rather than an invocation.
          #
          # Unless command-scoped config was set: then this token's expansion is
          # unknown and could be commit. Deciding that from the config key loses
          # a race it cannot win — `alias.ci=commit` is the obvious spelling,
          # `include.path` and `includeIf.*.path` reach the same place through a
          # file, and the next key is one review away. So -c before an
          # unidentified subcommand is refused whatever it sets.
          break
          ;;
      esac
    done
    # Reached without identifying a commit. Command-scoped config could rename
    # one, and an unquoted expansion could carry one in words this parser never
    # saw, so neither may end the scan quietly.
    if [[ -n "$scanned_past_commit" ]]; then
      [[ -z "$config_override" ]] || block_config_override
      [[ -z "$split_risk" ]] || block_unparsed
      [[ -z "$opaque_option" ]] || block_unparsed
    fi
  fi
  at_command_start=0
  token_index=$((token_index + 1))
done
((commit_index >= 0)) || exit 0
[[ -z "$TOKENIZATION_ERROR" ]] || block_unparsed
((commit_count == 1)) || block_unparsed

ALL_MODE=""
PATHS=()
after_separator=""
token_index=$((commit_index + 1))
while ((token_index < token_count)); do
  current="${TOKENS[token_index]}"
  [[ "$current" == "$BOUNDARY_PREFIX"* ]] && break
  if [[ -n "$after_separator" ]]; then
    unsafe_value "$current" && block_unparsed
    [[ "$current" == *'*'* || "$current" == *'?'* || "$current" == *'['* ]] && block_unparsed
    PATHS+=("$current")
    token_index=$((token_index + 1))
    continue
  fi
  case "$current" in
    --) after_separator=1 ;;
    -a | --all) ALL_MODE=1 ;;
    -am | -ma) ALL_MODE=1; token_index=$((token_index + 1)) ;;
    -m | --message | -F | --file | -C | --reuse-message | -c | --reedit-message | --author | --date | --cleanup | --fixup | --squash | -t | --template | --trailer)
      ((token_index + 1 < token_count)) || block_unparsed
      token_index=$((token_index + 1))
      ;;
    --message=* | --file=* | --reuse-message=* | --reedit-message=* | --author=* | --date=* | --cleanup=* | --fixup=* | --squash=* | --template=* | --trailer=* | --untracked-files=* | --gpg-sign=*) ;;
    # -u and -S take an OPTIONAL ATTACHED value (-uall, -S<key-id>); git never
    # reads the next token as their value. Consuming one made the following -m
    # the "value" and its message a pathspec, so the candidate came out empty,
    # scanned clean, and the staged credential was committed anyway.
    -u | -u?* | --untracked-files | -S | -S?* | --gpg-sign | --no-gpg-sign) ;;
    # No-value flags that change neither what is committed nor where from.
    -v | --verbose | -q | --quiet | -z | --null | --short | --branch | --porcelain | --long | --dry-run | --status | --no-status) ;;
    # -e/--edit is deliberately absent: it opens $EDITOR, which has no TTY here,
    # so admitting it trades a millisecond refusal for a hung tool call.
    -s | --signoff | --no-signoff | -n | --no-verify | --verify | --amend | --no-edit | --reset-author | --allow-empty | --allow-empty-message | --no-post-rewrite | -o | --only) ;;
    -i | --include) block_unparsed ;;
    --pathspec-from-file | --pathspec-from-file=* | --pathspec-file-nul) block_unparsed ;;
    -*) block_unparsed ;;
    *)
      unsafe_value "$current" && block_unparsed
      [[ "$current" == *'*'* || "$current" == *'?'* || "$current" == *'['* ]] && block_unparsed
      PATHS+=("$current")
      ;;
  esac
  token_index=$((token_index + 1))
done
[[ -n "$ALL_MODE" && -n "${PATHS[*]-}" ]] && block_unparsed

# `${a[@]+"${a[@]}"}` not `"${a[@]}"`: under `set -u`, bash 3.2 — the version at
# /bin/bash on macOS — treats an empty array expansion as an unbound variable and
# aborts. With the `|| true` at the call sites that would swallow the abort and
# leave DIFF empty, silently turning the guard off on exactly the machines it targets.
gitq() { git ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} "$@"; }
DIFF_SPEC=()
[[ -z "${PATHS[*]-}" ]] || DIFF_SPEC=(-- "${PATHS[@]}")

FILTER_CANDIDATE_FILE=""
FILTER_ATTR_FILE=""
FILTER_ATTR_PID=""

cleanup_filter_scan() {
  if [[ -n "$FILTER_ATTR_PID" ]]; then
    kill "$FILTER_ATTR_PID" 2>/dev/null || true
    wait "$FILTER_ATTR_PID" 2>/dev/null || true
    FILTER_ATTR_PID=""
  fi
  [[ -z "$FILTER_CANDIDATE_FILE" ]] || rm -f -- "$FILTER_CANDIDATE_FILE"
  [[ -z "$FILTER_ATTR_FILE" ]] || rm -f -- "$FILTER_ATTR_FILE"
}

# Invoked indirectly by the signal traps installed during the filter scan.
# shellcheck disable=SC2317,SC2329
terminate_filter_scan() {
  local signal_status="$1"
  trap '' HUP INT TERM
  cleanup_filter_scan
  trap - EXIT HUP INT TERM
  exit "$signal_status"
}

block_active_filters() {
  local candidate_path attr_path attr_name attr_value trailing_attr

  FILTER_CANDIDATE_FILE=$(mktemp "${TMPDIR:-/tmp}/cc-staged-secret-candidates.XXXXXX") || block_unparsed
  trap cleanup_filter_scan EXIT
  trap 'terminate_filter_scan 129' HUP
  trap 'terminate_filter_scan 130' INT
  trap 'terminate_filter_scan 143' TERM
  FILTER_ATTR_FILE=$(mktemp "${TMPDIR:-/tmp}/cc-staged-secret-attributes.XXXXXX") || block_unparsed

  gitq diff --no-ext-diff --no-textconv --cached --name-only -z ${DIFF_SPEC[@]+"${DIFF_SPEC[@]}"} >"$FILTER_CANDIDATE_FILE" 2>/dev/null || block_unparsed
  gitq ls-files -m -d -z ${DIFF_SPEC[@]+"${DIFF_SPEC[@]}"} >>"$FILTER_CANDIDATE_FILE" 2>/dev/null || block_unparsed

  # Spelled out rather than through gitq: backgrounding a function makes `$!` the
  # subshell's pid, so the kill and wait below would never reach git itself and
  # a terminated hook would leave the child running.
  git ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} check-attr -z --stdin filter <"$FILTER_CANDIDATE_FILE" >"$FILTER_ATTR_FILE" 2>/dev/null &
  FILTER_ATTR_PID=$!
  if wait "$FILTER_ATTR_PID"; then
    FILTER_ATTR_PID=""
  else
    FILTER_ATTR_PID=""
    block_unparsed
  fi

  exec 4<"$FILTER_CANDIDATE_FILE"
  exec 3<"$FILTER_ATTR_FILE"
  while IFS= read -r -d '' candidate_path <&4; do
    if ! IFS= read -r -d '' attr_path <&3 ||
      ! IFS= read -r -d '' attr_name <&3 ||
      ! IFS= read -r -d '' attr_value <&3; then
      block_unparsed
    fi
    if [[ "$attr_path" != "$candidate_path" || "$attr_name" != "filter" ]]; then
      block_unparsed
    fi
    if [[ "$attr_value" != "unspecified" && "$attr_value" != "unset" && -n "$attr_value" ]]; then
      echo "Blocked: this commit form would inspect working-tree content through an active clean filter. Stage reviewed content without the filter before committing." >&2
      exit 2
    fi
  done
  trailing_attr=""
  if IFS= read -r -d '' trailing_attr <&3 || [[ -n "$trailing_attr" ]]; then
    block_unparsed
  fi
  exec 3<&-
  exec 4<&-

  cleanup_filter_scan
  FILTER_CANDIDATE_FILE=""
  FILTER_ATTR_FILE=""
  trap - EXIT HUP INT TERM
}

# A pathspec or `-a` commit records working-tree content, so it is diffed against
# HEAD and has to clear the clean-filter check first. Everything else — including
# either of those in a repository with no HEAD yet — is the staged diff.
if [[ -n "${PATHS[*]-}" || -n "$ALL_MODE" ]] && gitq rev-parse --verify HEAD >/dev/null 2>&1; then
  block_active_filters
  REF=HEAD
else
  REF=--cached
fi
DIFF=$(gitq diff --no-ext-diff --no-textconv "$REF" ${DIFF_SPEC[@]+"${DIFF_SPEC[@]}"} 2>/dev/null || true)
[[ -n "$DIFF" ]] || exit 0

# Added lines only — an existing secret being deleted must not block its removal.
ADDED=$(printf '%s\n' "$DIFF" | grep -E '^\+' | grep -Ev '^\+\+\+' || true)
[[ -n "$ADDED" ]] || exit 0

# Each entry is "<label>|<extended regex>".
PATTERNS=(
  'npm auth token|_authToken[[:space:]]*=[[:space:]]*[^[:space:]$"'"'"']{16,}'
  'GitHub token|gh[pousr]_[A-Za-z0-9]{36,}'
  # sk- needs a left boundary: "live-task-status-transitioning" contains
  # "sk-status-transitioning", which clears the 20-char floor.
  'OpenAI-style key|(^|[^A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}'
  'Anthropic key|(^|[^A-Za-z0-9_-])sk-ant-[A-Za-z0-9_-]{20,}'
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
