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

# Separate message for the same reason as block_config_override below: the
# command that lands here is usually not a commit, and naming one sends the
# reader hunting for a commit that is not there. It is reached when an unquoted
# expansion sits where the subcommand could be -- `git -C $R log`, or a git call
# inside a `for` loop over an unquoted path -- so the actionable fix is quoting,
# not rewriting a commit. 0.2.7 already narrowed which `-C` expansions are
# judged, and read-only calls kept being refused after it: over 2026-09-04..12,
# 18 refusals carried no `commit` token at all, on status, log, rev-parse,
# diff, ls-files, branch and worktree. Refusal is correct -- an unquoted
# expansion can still carry `commit` in words this parser never sees -- so only
# the advice changes here.
block_unquoted_expansion() {
  echo "Blocked: an unquoted expansion sits where git's subcommand could be, so this hook cannot tell whether the command commits — it is not necessarily a commit at all. Quote the expansion (\"\$VAR\") so it cannot split into extra words, or write the value literally." >&2
  exit 2
}

# Separate message: the command above is usually not a commit at all, and the
# parse advice would send the reader looking for one that is not there.
block_config_override() {
  echo "Blocked: this command sets git configuration with -c or --config-env before a subcommand this hook cannot identify. Command-scoped config can rename commit through an alias, directly or through an include, so the staged diff cannot be cleared. Drop the -c override, or name the subcommand's real work in a separate command." >&2
  exit 2
}

# Separate message: the program itself is what cannot be read. `g=git; $g commit`
# and `$(command -v git) commit` run a commit, but only `commit` is visible here,
# and a word that expands to git can carry its own -C or -c as well, so there is
# no candidate to scan. The fix is to name git, not to requote anything.
block_indirect_commit() {
  echo "Blocked: \`commit\` follows a program name this hook cannot read — a variable, a command substitution, or a shell function it could not follow — so this may be a git commit whose repository and options are unknown. Call git by name (git commit ...) so the staged diff can be scanned." >&2
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
# A parenthesis opened straight after an unquoted `$` is a command substitution,
# not a subshell, and the parser needs to know which one closed: `$(echo git)
# commit` runs the substitution's output with `commit` as its first argument,
# where `(git status) commit` is not valid shell at all. So `$(` and its closing
# `)` get their own boundary spellings, `$)` and `$)+`, the second when a word
# follows with no space and so continues the substitution's word
# (`$(npm bin)/eslint`). One character per open parenthesis, s or p, pairs them.
subst_stack=""
last_unquoted_dollar=""
command_len=${#COMMAND}
command_pos=0
while ((command_pos < command_len)); do
  char="${COMMAND:command_pos:1}"
  prev_dollar=$last_unquoted_dollar
  last_unquoted_dollar=""
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
      ";" | "|" | "&")
        if [[ -n "$token_started" ]]; then TOKENS+=("$token"); TOKEN_EXPANSION+=("$token_expansion"); token=""; token_started=""; token_expansion=""; fi
        TOKENS+=("$BOUNDARY_PREFIX$char")
        TOKEN_EXPANSION+=("")
        ;;
      "(")
        if [[ -n "$token_started" ]]; then TOKENS+=("$token"); TOKEN_EXPANSION+=("$token_expansion"); token=""; token_started=""; token_expansion=""; fi
        if [[ -n "$prev_dollar" ]]; then
          subst_stack="${subst_stack}s"
          TOKENS+=("$BOUNDARY_PREFIX\$(")
        else
          subst_stack="${subst_stack}p"
          TOKENS+=("$BOUNDARY_PREFIX(")
        fi
        TOKEN_EXPANSION+=("")
        ;;
      ")")
        if [[ -n "$token_started" ]]; then TOKENS+=("$token"); TOKEN_EXPANSION+=("$token_expansion"); token=""; token_started=""; token_expansion=""; fi
        closing="${subst_stack#"${subst_stack%?}"}"
        subst_stack="${subst_stack%?}"
        if [[ "$closing" == s ]]; then
          case "${COMMAND:command_pos+1:1}" in
            "" | " " | $'\t' | $'\n' | ";" | "|" | "&" | "(" | ")") TOKENS+=("$BOUNDARY_PREFIX\$)") ;;
            *) TOKENS+=("$BOUNDARY_PREFIX\$)+") ;;
          esac
        else
          TOKENS+=("$BOUNDARY_PREFIX)")
        fi
        TOKEN_EXPANSION+=("")
        ;;
      *)
        token="$token$char"
        token_started=1
        # Unquoted wins over a quoted expansion seen earlier in the token:
        # "$base"$d splits, however the first half was written.
        [[ "$char" == '$' || "$char" == '`' ]] && token_expansion="split"
        [[ "$char" != '$' ]] || last_unquoted_dollar=1
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
#
# The array form has to be matched as ${...[@]...}, and inside ONE expansion. A
# bare [@] also appears in ordinary paths, so "$root/project[@]" was refused;
# requiring [@] immediately before the closing brace then missed every modified
# form, since "${args[@]:0}", "${args[@]%x}" and "${args[@]/a/b}" still emit one
# word per element; and a glob anchored on ${ and } separately took its opening
# brace from one expansion and its closing brace from a later one, refusing
# "$root/${x}dir[@]${suffix}". The regex says what all three attempts meant: a
# [@] reached from a ${ without passing a } on the way.
ARRAY_AT_RE='\$\{[^}]*\[@\]'
for ((token_index = 0; token_index < ${#TOKENS[@]}; token_index++)); do
  [[ "${TOKEN_EXPANSION[token_index]-}" == "quoted" ]] || continue
  # shellcheck disable=SC2016  # the single quotes are the point: these are
  # literal spellings to match in the token, not expansions to perform.
  case "${TOKENS[token_index]}" in
    *'$@'* | *'${@'*) TOKEN_EXPANSION[token_index]="split" ;;
    *) [[ "${TOKENS[token_index]}" =~ $ARRAY_AT_RE ]] && TOKEN_EXPANSION[token_index]="split" ;;
  esac
done

# Pair each `{` with the `}` that closes it, in one pass over the tokens, into
# BRACE_MATCH (opening index -> closing index). A function body is skipped up to
# its pair, so an error here decides what goes unread, and the two directions are
# not equally safe. Closing too early leaves the rest of a body to be read as
# though it ran: a refusal at worst. Closing too late skips whatever real
# commands follow the body, and a heredoc's prose (`if (!ready) { return }`,
# `module.exports = {`) is parsed as commands here, so its braces pair up with
# anything. So every `}` closes, and `{` opens only where a command could start:
# after a separator, a keyword, another `{`, or `function NAME`.
match_braces() {
  local index prev stack=""
  BRACE_MATCH=()
  for ((index = 0; index < token_count; index++)); do
    case "${TOKENS[index]}" in
      "{")
        prev=""
        ((index == 0)) || prev=${TOKENS[index - 1]}
        case "$prev" in
          "" | "$BOUNDARY_PREFIX"* | "{" | if | then | elif | else | do | while | until | "!" | time) stack="$stack $index" ;;
          *) if ((index >= 2)) && [[ "${TOKENS[index - 2]}" == "function" ]]; then stack="$stack $index"; fi ;;
        esac
        ;;
      "}")
        # Glued to a closing substitution, as in `${ROOT:-$(pwd)}`, the brace
        # ends a parameter expansion, which is part of a word, not a body.
        if ((index > 0)) && [[ "${TOKENS[index - 1]}" == "$BOUNDARY_PREFIX\$)+" ]]; then
          continue
        fi
        if [[ -n "$stack" ]]; then
          BRACE_MATCH[${stack##* }]=$index
          stack=${stack% *}
        fi
        ;;
    esac
  done
  braces_stale=""
}

REPO_ARGS=()
commit_index=-1
commit_count=0
token_count=${#TOKENS[@]}
orig_end=$token_count
token_index=0
at_command_start=1
command_prefix=""
env_prefix=""
# `command` runs a builtin or a program, never a shell function, so a name behind
# it is not looked up among the functions defined below.
function_lookup=1
# The main loop's own record of open parentheses, one character each: p for a
# subshell, c for a command substitution that is (part of) the program name, and
# 0 or 1 for any other substitution -- the command-start state to restore once it
# closes. `echo $(date) git commit` passes git as an argument to echo, while
# `out=$(date) git commit` runs git behind an assignment.
paren_stack=""
# Set when a substitution closes glued to the next word, which then continues
# that word rather than starting a new one: the program name for
# `$(npm bin)/eslint`, the assignment for `out=$(date)x git commit`.
cmdword_continues=""
assignment_continues=""
# Functions defined earlier in the same command: name and body token range. A
# call is replaced by its body with the call's words in place of "$@" and $1..$9,
# so the git parse below judges what the call actually runs -- the same verdict
# the body would get written out inline. Definitions themselves run nothing.
FUNC_NAMES=()
FUNC_BODY_START=()
FUNC_BODY_END=()
FUNC_CERTAIN=()
FUNC_NAME_SET=" "
# Open if/while/until/for/case/select constructs, so that a definition inside one
# is known not to be certain to run.
cond_depth=0
BRACE_MATCH=()
braces_stale=1
# A call is inlined by appending the body after everything read so far and
# reading it there, then returning to just after the call: the regions being
# read form a stack of function, end and return index. Appending costs the size
# of the body, where splicing it into place copied the whole token list on every
# call and passed the hook's 10 s timeout for a few hundred calls in a long
# command. Inlining is bounded twice. Recursion (`f() { f; }; f`) stops at a
# depth of 8 calls of one function inside its own body, so that a helper called
# twenty times in a row is not mistaken for one calling itself. And the tokens
# inlining may add are capped, which bounds the work in all, and stops a body
# that multiplies its arguments (`f() { f "$@" "$@"; }`) from doubling them at
# every level. Past a bound a call is not read; what it may still not do is
# described where it is judged, below.
RECURSION_LIMIT=8
inline_budget=$((token_count + 4096))
REGION_FUNC=()
REGION_END=()
REGION_RETURN=()
region_depth=0
while :; do
  while ((region_depth > 0)) && ((token_index >= REGION_END[region_depth - 1])); do
    token_index=${REGION_RETURN[region_depth - 1]}
    region_depth=$((region_depth - 1))
  done
  ((region_depth > 0 || token_index < orig_end)) || break
  current="${TOKENS[token_index]}"
  scan_start=-1
  indirect=""
  if [[ "$current" == "$BOUNDARY_PREFIX"* ]]; then
    resume=1
    cmdword_continues=""
    assignment_continues=""
    case "$current" in
      "$BOUNDARY_PREFIX(") paren_stack="${paren_stack}p" ;;
      "$BOUNDARY_PREFIX\$(") paren_stack="${paren_stack}${at_command_start}" ;;
      "$BOUNDARY_PREFIX)" | "$BOUNDARY_PREFIX\$)" | "$BOUNDARY_PREFIX\$)+")
        opener="${paren_stack#"${paren_stack%?}"}"
        paren_stack="${paren_stack%?}"
        case "$opener" in
          0) resume=0 ;;
          1) [[ "$current" != "$BOUNDARY_PREFIX\$)+" ]] || assignment_continues=1 ;;
          c)
            resume=0
            if [[ "$current" == "$BOUNDARY_PREFIX\$)+" ]]; then
              cmdword_continues=1
            else
              scan_start=$((token_index + 1))
              indirect=1
            fi
            ;;
        esac
        ;;
    esac
    at_command_start=$resume
    command_prefix=""
    env_prefix=""
    function_lookup=1
    if ((scan_start < 0)); then
      token_index=$((token_index + 1))
      continue
    fi
  elif [[ -n "$assignment_continues" ]]; then
    # The rest of `out=$(date)x`: still the assignment, so the next word is still
    # the command.
    assignment_continues=""
    token_index=$((token_index + 1))
    continue
  elif [[ -n "$cmdword_continues" ]]; then
    # The word glued to a closing command-name substitution: `$(npm bin)/eslint`.
    # It may open another one (`$(a)$(b)`); otherwise the arguments follow it.
    cmdword_continues=""
    if [[ "${TOKENS[token_index + 1]-}" == "$BOUNDARY_PREFIX\$(" ]]; then
      paren_stack="${paren_stack}c"
      at_command_start=1
      token_index=$((token_index + 2))
      continue
    fi
    scan_start=$((token_index + 1))
    indirect=1
  fi
  if ((at_command_start)) && [[ "$current" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
    token_index=$((token_index + 1))
    continue
  fi
  if ((at_command_start)); then
    case "$current" in
      "if" | "while" | "until" | "for" | "case" | "select") cond_depth=$((cond_depth + 1)) ;;
      "fi" | "done" | "esac") ((cond_depth == 0)) || cond_depth=$((cond_depth - 1)) ;;
    esac
  fi
  # A shell keyword introduces a command rather than being one, so the word after
  # it is still at a command start. Without this, `if git commit ...` and the
  # body of a `for ... do` loop are never recognised as git invocations at all.
  # `{` is in the list because a function body never reaches it: a definition is
  # recognised by its name, below, and skipped whole, so a `{` seen here opens a
  # group, which runs where it stands.
  if ((at_command_start)); then
    case "$current" in
      if | then | elif | else | do | while | until | "!" | "{")
        token_index=$((token_index + 1))
        continue
        ;;
    esac
  fi
  if ((at_command_start)) && [[ "$current" == "command" || "$current" == "time" ]]; then
    command_prefix=1
    [[ "$current" != "command" ]] || function_lookup=""
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
  # A function definition: `name() {`, `function name {` or `function name() {`,
  # with any newlines before the brace. Record the body and step over all of it;
  # defining a function runs nothing, so nothing in the body is judged here. A
  # body that is not a brace group, or a brace that never closes, is left to the
  # ordinary parse, which reads it as though it ran.
  if ((at_command_start)) && [[ -z "$command_prefix$env_prefix" && -z "${TOKEN_EXPANSION[token_index]-}" ]]; then
    def_name=""
    def_open=-1
    if [[ "$current" == "function" ]] && ((token_index + 1 < token_count)) \
      && [[ "${TOKENS[token_index + 1]}" != "$BOUNDARY_PREFIX"* && -z "${TOKEN_EXPANSION[token_index + 1]-}" ]]; then
      def_name=${TOKENS[token_index + 1]}
      def_open=$((token_index + 2))
      if [[ "${TOKENS[def_open]-}" == "$BOUNDARY_PREFIX(" && "${TOKENS[def_open + 1]-}" == "$BOUNDARY_PREFIX)" ]]; then
        def_open=$((def_open + 2))
      fi
    elif [[ "${TOKENS[token_index + 1]-}" == "$BOUNDARY_PREFIX(" && "${TOKENS[token_index + 2]-}" == "$BOUNDARY_PREFIX)" ]]; then
      def_name=$current
      def_open=$((token_index + 3))
    fi
    if [[ -n "$def_name" ]]; then
      while [[ "${TOKENS[def_open]-}" == "$BOUNDARY_PREFIX;" ]]; do def_open=$((def_open + 1)); done
    fi
    if [[ -n "$def_name" && "${TOKENS[def_open]-}" == "{" ]]; then
      [[ -z "$braces_stale" ]] || match_braces
      def_close=${BRACE_MATCH[def_open]--1}
      # A heredoc inside the range means prose was parsed as commands, and its
      # braces may have paired with the wrong ones, so the range is not trusted
      # to be a body: it is read as though it ran instead.
      for ((brace_index = def_open + 1; brace_index < def_close; brace_index++)); do
        case "${TOKENS[brace_index]}" in
          *'<<<'*) ;;
          *'<<'*) def_close=-1; break ;;
        esac
      done
      if ((def_close >= 0)); then
        # Certain means this definition replaces any earlier one in the shell that
        # runs the command: not in a subshell or substitution, not inside a
        # conditional or a loop, not in a function body, and not joined to its
        # neighbours by `&&`, `||`, `|` or `&`. `( f() { :; } ); f` still runs the
        # outer f, and `if false; then f() { :; }; fi` defines nothing.
        def_certain=1
        if [[ -n "$paren_stack" ]] || ((region_depth > 0 || cond_depth > 0)); then
          def_certain=""
        fi
        def_prev=""
        ((token_index == 0)) || def_prev=${TOKENS[token_index - 1]}
        case "$def_prev" in
          "" | "$BOUNDARY_PREFIX;") ;;
          *) def_certain="" ;;
        esac
        case "${TOKENS[def_close + 1]-}" in
          "" | "$BOUNDARY_PREFIX;") ;;
          *) def_certain="" ;;
        esac
        FUNC_NAMES+=("$def_name")
        FUNC_BODY_START+=("$((def_open + 1))")
        FUNC_BODY_END+=("$def_close")
        FUNC_CERTAIN+=("$def_certain")
        FUNC_NAME_SET="$FUNC_NAME_SET$def_name "
        at_command_start=0
        token_index=$((def_close + 1))
        continue
      fi
    fi
  fi
  # A call to a function defined above; a name called before its definition is
  # not yet a function. The call is read as every definition that may be the one
  # in effect: the latest, and each earlier one back to the latest that is
  # certain, since an uncertain definition may never have replaced it. As in the
  # shell, a certain definition replaces everything before it.
  func_index=-1
  call_certain=""
  CALL_DEFS=()
  if ((at_command_start)) && [[ -n "$function_lookup" && -z "$env_prefix" && -z "${TOKEN_EXPANSION[token_index]-}" \
    && "$FUNC_NAME_SET" == *" $current "* ]]; then
    for ((lookup_index = ${#FUNC_NAMES[@]} - 1; lookup_index >= 0; lookup_index--)); do
      [[ "${FUNC_NAMES[lookup_index]}" == "$current" ]] || continue
      ((func_index >= 0)) || func_index=$lookup_index
      CALL_DEFS+=("$lookup_index")
      if [[ -n "${FUNC_CERTAIN[lookup_index]}" ]]; then
        call_certain=1
        break
      fi
    done
  fi
  recursion=0
  if ((func_index >= 0)); then
    for ((region_index = 0; region_index < region_depth; region_index++)); do
      ((REGION_FUNC[region_index] != func_index)) || recursion=$((recursion + 1))
    done
  fi
  if ((func_index >= 0 && recursion < RECURSION_LIMIT)); then
    call_end=$((token_index + 1))
    while ((call_end < token_count)) && [[ "${TOKENS[call_end]}" != "$BOUNDARY_PREFIX"* ]]; do
      call_end=$((call_end + 1))
    done
    # The first of the call's words that can split into several. Up to it each
    # word is exactly one positional parameter; from it on, which word lands in
    # which parameter is unknown.
    first_split=0
    for ((arg_index = token_index + 1; arg_index < call_end; arg_index++)); do
      if [[ "${TOKEN_EXPANSION[arg_index]-}" == split ]]; then
        first_split=$((arg_index - token_index))
        break
      fi
    done
    inline_room=$((inline_budget - token_count))
    # Each body starts at a separator, so that no scan of the command before it
    # runs on into the body.
    INLINE_TOKENS=("$BOUNDARY_PREFIX;")
    INLINE_EXPANSION=("")
    for def_index in "${CALL_DEFS[@]}"; do
      body_start=${FUNC_BODY_START[def_index]}
      body_end=${FUNC_BODY_END[def_index]}
      # The call's words replace the positional parameters only where they are
      # sure to line up. `shift` and `set` renumber them partway through the
      # body, and a function defined inside the body has positional parameters
      # of its own. In any of those the expansions are left unresolved, and the
      # parse refuses what it cannot place.
      substitute=1
      for ((body_index = body_start; body_index < body_end; body_index++)); do
        case "${TOKENS[body_index]}" in
          shift | function) substitute="" ;;
          set)
            case "${TOKENS[body_index + 1]-}" in
              -- | [!+-]*) substitute="" ;;
            esac
            ;;
          "$BOUNDARY_PREFIX(") [[ "${TOKENS[body_index + 1]-}" != "$BOUNDARY_PREFIX)" ]] || substitute="" ;;
        esac
      done
      for ((body_index = body_start; body_index < body_end; body_index++)); do
        ((${#INLINE_TOKENS[@]} <= inline_room)) || break
        body_token=${TOKENS[body_index]}
        body_expansion=${TOKEN_EXPANSION[body_index]-}
        if [[ -n "$substitute" && -n "$body_expansion" ]]; then
          # shellcheck disable=SC2016  # literal spellings of positional parameters
          case "$body_token" in
            '$@' | '${@}')
              # Read as "$@" either way: once tokenized, the quoted and unquoted
              # spellings are the same token, and unquoted is the rarer one.
              for ((arg_index = token_index + 1; arg_index < call_end; arg_index++)); do
                INLINE_TOKENS+=("${TOKENS[arg_index]}")
                INLINE_EXPANSION+=("${TOKEN_EXPANSION[arg_index]-}")
              done
              continue
              ;;
            '${@:'[1-9]'}')
              # "${@:2}": the call's words from the second on, once the words
              # before it are known to be one parameter each.
              position=${body_token//[^0-9]/}
              if ((first_split == 0 || position <= first_split)); then
                for ((arg_index = token_index + position; arg_index < call_end; arg_index++)); do
                  INLINE_TOKENS+=("${TOKENS[arg_index]}")
                  INLINE_EXPANSION+=("${TOKEN_EXPANSION[arg_index]-}")
                done
                continue
              fi
              ;;
            '$'[1-9] | '${'[1-9]'}')
              position=${body_token//[^1-9]/}
              arg_index=$((token_index + position))
              if ((first_split > 0 && position >= first_split)); then
                # A word that can split sits at or before this parameter, so its
                # value is unknown. Quoted it is still exactly one word, and a
                # quoted expansion is what the parse makes of it: `"$1"` given
                # `$d` is a single path to `-C`, never an extra subcommand.
                INLINE_TOKENS+=("$body_token")
                INLINE_EXPANSION+=("$body_expansion")
              elif ((arg_index >= call_end)); then
                # "$3" with no third argument is still one, empty, word; $3 is none.
                if [[ "$body_expansion" == quoted ]]; then
                  INLINE_TOKENS+=("")
                  INLINE_EXPANSION+=("")
                fi
              elif [[ "$body_expansion" == quoted ]]; then
                INLINE_TOKENS+=("${TOKENS[arg_index]}")
                INLINE_EXPANSION+=("${TOKEN_EXPANSION[arg_index]-}")
              else
                # Unquoted, the value splits into words: `step "git commit -m x"`
                # with a body of `$1` runs a commit.
                split_words=()
                IFS=$' \t\n' read -r -d '' -a split_words <<<"${TOKENS[arg_index]}" || true
                for split_word in ${split_words[@]+"${split_words[@]}"}; do
                  INLINE_TOKENS+=("$split_word")
                  INLINE_EXPANSION+=("${TOKEN_EXPANSION[arg_index]-}")
                done
              fi
              continue
              ;;
          esac
        fi
        INLINE_TOKENS+=("$body_token")
        INLINE_EXPANSION+=("$body_expansion")
      done
      INLINE_TOKENS+=("$BOUNDARY_PREFIX;")
      INLINE_EXPANSION+=("")
    done
    if [[ -z "$call_certain" && "$current" == "git" ]]; then
      # No definition of git is sure to be in effect, so git itself may run.
      INLINE_TOKENS+=(command git)
      INLINE_EXPANSION+=("" "")
      for ((arg_index = token_index + 1; arg_index < call_end; arg_index++)); do
        INLINE_TOKENS+=("${TOKENS[arg_index]}")
        INLINE_EXPANSION+=("${TOKEN_EXPANSION[arg_index]-}")
      done
      INLINE_TOKENS+=("$BOUNDARY_PREFIX;")
      INLINE_EXPANSION+=("")
    fi
    if ((${#INLINE_TOKENS[@]} <= inline_room)); then
      TOKENS+=("${INLINE_TOKENS[@]}")
      TOKEN_EXPANSION+=("${INLINE_EXPANSION[@]}")
      REGION_FUNC[region_depth]=$func_index
      REGION_RETURN[region_depth]=$call_end
      token_index=$token_count
      token_count=${#TOKENS[@]}
      REGION_END[region_depth]=$token_count
      region_depth=$((region_depth + 1))
      braces_stale=1
      continue
    fi
  fi
  if ((at_command_start && func_index >= 0)); then
    # A call past the inlining bounds is not read, but its words may not say
    # commit.
    for ((arg_index = token_index + 1; arg_index < token_count; arg_index++)); do
      [[ "${TOKENS[arg_index]}" != "$BOUNDARY_PREFIX"* ]] || break
      [[ "${TOKENS[arg_index]}" != commit ]] || block_indirect_commit
    done
    # Past the recursion bound nothing more is needed: the same bodies were
    # inlined and parsed at every level above this one.
    if ((recursion < RECURSION_LIMIT)); then
      # Past the token cap, a body may never have been read at all, and
      # neither may the functions it calls: `c() { g; }` commits through g. So
      # nothing the call can reach, function by function, may name git or commit.
      CLOSURE=("${CALL_DEFS[@]}")
      closure_seen=" ${CALL_DEFS[*]} "
      closure_index=0
      while ((closure_index < ${#CLOSURE[@]})); do
        def_index=${CLOSURE[closure_index]}
        body_end=${FUNC_BODY_END[def_index]}
        for ((body_index = FUNC_BODY_START[def_index]; body_index < body_end; body_index++)); do
          body_token=${TOKENS[body_index]}
          case "$body_token" in
            git | */git | *commit*) block_indirect_commit ;;
          esac
          [[ "$FUNC_NAME_SET" == *" $body_token "* ]] || continue
          for ((lookup_index = 0; lookup_index < ${#FUNC_NAMES[@]}; lookup_index++)); do
            if [[ "${FUNC_NAMES[lookup_index]}" == "$body_token" && "$closure_seen" != *" $lookup_index "* ]]; then
              CLOSURE+=("$lookup_index")
              closure_seen="$closure_seen$lookup_index "
            fi
          done
        done
        closure_index=$((closure_index + 1))
      done
    fi
    at_command_start=0
    token_index=$((token_index + 1))
    continue
  fi
  # What runs is git itself, or a program name this hook cannot read: an
  # expansion (`$g`, "${GIT:-git}") or a command substitution. The second kind
  # is judged only on whether `commit` turns up where git would read its
  # subcommand; anything else is left alone, since `$PYTHON -c ...` and
  # `"$EDITOR" "$f"` are ordinary work. A word with a backtick is not judged at
  # all: a heredoc's prose is parsed as commands here, and markdown puts
  # backticks at the start of a line far more often than any command does.
  if ((at_command_start && scan_start < 0)); then
    if [[ "$current" == "git" || "$current" == */git ]]; then
      scan_start=$((token_index + 1))
    elif [[ -n "${TOKEN_EXPANSION[token_index]-}" && "$current" != *'`'* ]]; then
      if [[ "${TOKENS[token_index + 1]-}" == "$BOUNDARY_PREFIX\$(" ]]; then
        # `$(echo git) commit`: the program name is still being built. Its
        # arguments start where the substitution closes.
        paren_stack="${paren_stack}c"
        command_prefix=""
        env_prefix=""
        function_lookup=1
        token_index=$((token_index + 2))
        continue
      fi
      scan_start=$((token_index + 1))
      indirect=1
    fi
  fi
  if ((scan_start >= 0)); then
    scan_index=$scan_start
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
          [[ -z "$indirect" ]] || block_indirect_commit
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
          # the scan may trust a token. Only a splittable expansion earns the
          # quoting advice: `git "$sub"` is already quoted and still cannot be
          # identified, so telling it to quote would send it in a circle.
          #
          # None of that applies behind a program name this hook cannot read:
          # nothing says it is git, and `"$EDITOR" "$f"` is not a commit.
          [[ -z "$indirect" ]] || break
          case "${TOKEN_EXPANSION[scan_index]-}" in
            split) block_unquoted_expansion ;;
            quoted) block_unparsed ;;
          esac
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
    # saw, so neither may end the scan quietly. Behind an unreadable program
    # name they may: `$PYTHON -c ...` sets no git config.
    if [[ -n "$scanned_past_commit" && -z "$indirect" ]]; then
      [[ -z "$config_override" ]] || block_config_override
      [[ -z "$split_risk" ]] || block_unquoted_expansion
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
  # A token that can add words is as dangerous here as before the subcommand:
  # it can introduce -a, which commits tracked files the index scan never saw.
  [[ "${TOKEN_EXPANSION[token_index]-}" != split ]] || block_unparsed
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
      # Checked here rather than at the top of the loop, because consuming the
      # value is exactly what stops it from being seen there.
      [[ "${TOKEN_EXPANSION[token_index + 1]-}" != split ]] || block_unparsed
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
