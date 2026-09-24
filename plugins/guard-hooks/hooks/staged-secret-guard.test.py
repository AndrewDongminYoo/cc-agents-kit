#!/usr/bin/env python3
"""Prove staged-secret-guard.sh blocks credentials in the staged diff, and only then."""

import json
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import _optout

HOOK = str(Path(__file__).resolve().with_name("staged-secret-guard.sh"))

# Fake values assembled at runtime so this file carries no scannable literal.
NPM = "//registry.npmjs.org/:_authToken=" + "0" * 36
GITHUB = "ghp_" + "A" * 36
OPENAI = "sk-" + "B" * 32
AWS = "AKIA" + "C" * 16
PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----"


def repo(files, stage=True):
    """Create a git repo with files staged, and return its path."""
    d = tempfile.mkdtemp()
    run = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)
    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    for name, body in files.items():
        Path(d, name).write_text(body)
    if stage:
        run("add", "-A")
    return d


def commit_seed(d):
    """Commit the current index so later fixtures can exercise tracked changes."""
    subprocess.run(["git", "-C", d, "commit", "-qm", "seed"], check=True)


def marker_command(directory, name):
    """Create an external diff command that leaves a marker when executed."""
    marker = Path(directory, f"{name}.marker")
    command = Path(directory, f"{name}.sh")
    command.write_text(f'#!/bin/bash\ntouch "{marker}"\nexit 1\n')
    command.chmod(0o755)
    return command, marker


def check_hook(command, cwd, env=None, timeout=None):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        ["/bin/bash", HOOK], input=payload, capture_output=True, text=True, cwd=cwd, env=env, timeout=timeout
    )
    return proc.returncode, proc.stderr


fails = 0


def check(label, condition, detail=""):
    global fails
    fails += not condition
    print(f"{'ok  ' if condition else 'FAIL'}  {label}")
    if not condition and detail:
        print(f"       {detail}")


# --- each credential shape blocks -------------------------------------------
for label, body in (
    ("npm auth token", f".npmrc content\n{NPM}\n"),
    ("GitHub token", f"const t = '{GITHUB}'\n"),
    ("OpenAI-style key", f"KEY={OPENAI}\n"),
    ("AWS access key id", f"aws_access_key_id = {AWS}\n"),
    ("private key block", f"{PRIVATE_KEY}\nMIIEow...\n"),
):
    d = repo({"config.txt": body})
    rc, err = check_hook("git commit -m 'add config'", d)
    check(f"blocks {label}", rc == 2, f"exit={rc} stderr={err.strip()[:120]}")
    check(f"names {label} in the message", label in err, f"stderr={err.strip()[:160]}")

# --- the value itself is never echoed in full -------------------------------
d = repo({"config.txt": f"{GITHUB}\n"})
_, err = check_hook("git commit -m x", d)
check("does not echo the whole value", GITHUB not in err, f"stderr={err.strip()[:160]}")

# --- must NOT block ---------------------------------------------------------
d = repo({"README.md": "# hello\nNo secrets here.\n"})
rc, _ = check_hook("git commit -m docs", d)
check("clean diff passes", rc == 0, f"exit={rc}")

# "sk-" inside a kebab-case word is prose, not a key — "live-task-status-transitioning"
# blocked a real commit on 2026-08-24 because "sk-status-transitioning" clears the
# 20-char floor.
d = repo({"notes.md": "see the live-task-status-transitioning page slug\n"})
rc, _ = check_hook("git commit -m docs", d)
check("kebab-case word containing sk- passes", rc == 0, f"exit={rc}")

# The boundary must not weaken detection of a key that starts its line.
d = repo({"config.txt": f"{OPENAI}\n"})
rc, _ = check_hook("git commit -m x", d)
check("key at line start still blocks", rc == 2, f"exit={rc}")

# A secret being REMOVED must not block its own removal.
d = repo({"config.txt": f"{GITHUB}\n"})
subprocess.run(["git", "-C", d, "commit", "-qm", "seed"], capture_output=True)
Path(d, "config.txt").write_text("cleaned\n")
subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
rc, _ = check_hook("git commit -m 'remove the token'", d)
check("removing a secret is allowed", rc == 0, f"exit={rc}")

d = repo({"README.md": "# hello\n"}, stage=False)
rc, _ = check_hook("git commit -m nothing", d)
check("nothing staged passes", rc == 0, f"exit={rc}")

d = repo({"config.txt": f"{GITHUB}\n"})
for label, command in (
    ("non-commit git command", "git status --short"),
    ("commit word in a later non-git segment", "git status --short && echo commit"),
    ("prose mentioning git commit", "echo 'run git commit next'"),
    ("unrelated command", "ls -la"),
    ("malformed non-commit command", 'echo "'),
    ("git help commit", "git help commit"),
    ("git version", "git --version"),
    ("quoted operator before git commit words", 'echo "|" git commit -m x'),
    # Global options before a non-commit subcommand used to trip block_unparsed
    # (2026-09-03: a `git -C "$d" log` loop was blocked as an unparsable commit).
    ("git log with a quoted shell-variable -C", 'git -C "$d" log --oneline -1'),
    ("git log with a fully quoted composite -C", 'git -C "$base/$d" log -1'),
    ("git log with an escaped dollar in -C", 'git -C /tmp/\\$lit log -1'),
    # "$*" and "${name[*]}" join to one word, so they stay allowed.
    ("quoted star expansion is one word", 'git -C "${arr[*]}" log -1'),
    # [@] is three ordinary characters in a path; only ${...[@]} is an array.
    ("literal bracket-at in a quoted path", 'git -C "$root/project[@]" log -1'),
    ("braced scalar then a literal bracket-at", 'git -C "$root/${x}dir[@]" log -1'),
    # The braces come from two different expansions, so no array is involved.
    ("bracket-at between two expansions", 'git -C "$root/${x}dir[@]${suffix}" log'),
    # Defining a function executes nothing -- including every line of its body,
    # not only the first, which is all the parser used to skip.
    ("a function definition containing a commit", 'f() { git commit -m x; }'),
    ("a definition whose second line commits", "f() { echo; git commit -m x; }"),
    ("a function-keyword definition", "function f { git commit -m x; }"),
    ("a function called before it is defined", "f; f() { git commit -m x; }"),
    # The body ends at the right brace. Every `}` closes one, and `{` opens one
    # only where a command can start, so a body is never read past its end.
    ("a definition closed straight after fi", "f() { if true; then git commit -m x; fi }"),
    ("a definition containing a brace group", "f() { { git status; }; git commit -m x; }"),
    ("a function-keyword definition with parentheses", "function f() { git commit -m x; }"),
    ("a function-keyword definition with a nested one", "function f { function g { :; }; git commit -m x; }"),
    # The latest definition wins, as in the shell.
    ("a function redefined before its call", "f() { git commit -m x; }; f() { git status; }; f"),
    # A definition that may not have taken effect is read alongside the ones it
    # would replace, and here none of them commits.
    ("a read-only function shadowed in a subshell", "f() { git status; }; ( f() { git log -1; } ); f"),
    # Past its recursion bound a function has been read at every level above,
    # so a read-only body is not refused for naming git.
    ("a recursive function running a read-only git command", "f() { git status; f; }; f"),
    # An inlined body is appended after the command, behind a separator, so a
    # bare git at the very end does not read the body's first word as its
    # subcommand.
    ("a bare git after a call whose body starts with commit", "f() { commit -m x; }; f; git"),
    # A setup script: thirty steps, each logging through a helper and checking
    # status, run three times. 180 calls in all, none of them a commit.
    ("a script of thirty steps run three times", 'log() { printf "%s\\n" "$*"; }\nR=/repo\n' + "".join(f'step{i}() {{\n  log "step {i}"\n  git -C "$R" status --short\n  npm run task{i} -- --flag "$1"\n}}\n' for i in range(30)) + "".join(f"step{i} arg{r}\n" for r in range(3) for i in range(30))),
    # A finished `if` leaves later definitions certain again.
    ("a function redefined after an if", "if true; then :; fi; f() { git commit -m x; }; f() { git status; }; f"),
    # `command` and `env` run a program named f, never the function.
    ("a function name behind command", "f() { git commit -m x; }; command f"),
    ("a function name behind env", "f() { git commit -m x; }; env f"),
    # "$2" with no second argument is still a word, and `git "" commit` is not a
    # commit.
    ("a missing quoted parameter standing as the subcommand", 'c() { git "$2" commit -m x; }; c a'),
    # "$1" is one word whatever the call passed, so an unquoted `$d` given to it
    # is a single unknown path, not a word that could turn into a subcommand.
    ("a quoted parameter given an unquoted word", 'gs() { git -C "$1" status --short; }; for d in */; do gs $d; done'),
    ("a quoted parameter given a substitution", 'show() { git -C "$1" log -3; }; show $(git rev-parse --show-toplevel)'),
    ("a slice of the arguments", 'in_repo() { git -C "$1" "${@:2}"; }; in_repo ./frontend status'),
    # The `}` of `${ROOT:-$(pwd)}` ends a parameter expansion, not the body.
    ("a body holding a defaulted substitution", 'f() { local d=${ROOT:-$(pwd)}; git -C "$d" "$@"; }; f status'),
    ("a git wrapper running a read-only verb", 'g() { git "$@"; }; g status'),
    # `commit` after an unreadable program name is only judged where git would
    # read its subcommand; anything else is ordinary work.
    ("a program named by a variable", "$PYTHON script.py commit"),
    ("a program named by a variable, with -c", "\"$PY\" -c 'print(1)'"),
    ("a program named by a variable, with unquoted flags", "$PYTHON $flags script.py"),
    ("a quoted program and a quoted argument", '"$EDITOR" "$f"'),
    ("a substitution glued to the program name", "$(npm bin)/eslint ."),
    ("a variable naming git for a read-only verb", "$g log --oneline"),
    # A substitution among the arguments leaves the words after it arguments.
    ("git as an argument after a substitution", "echo $(date) git commit -m x"),
    # Heredoc prose is parsed as commands here, and markdown often starts a line
    # with a backticked word.
    ("a heredoc line starting with a backticked word", "cat > n.md <<'EOF'\n`git` commit messages are conventional\nEOF"),
    ("git log with an unparsed --option", "git --no-pager log -1"),
    ("git log behind a long option carrying its own value", "git --git-dir=/repo/.git log -1"),
    ("git log behind a pathspec flag", "git --literal-pathspecs log -1"),
    # A subcommand argument whose value is the word commit is a search term, not
    # an invocation; the scan must stop at the subcommand to tell them apart.
    ("commit as a --grep value", "git --no-pager log --grep commit"),
    ("commit inside a pathspec", "git --no-pager diff -- README.commit"),
    ("git log inside command substitution", 'c=$(git -C "$HOME/x" log --since=30.days --oneline); echo "$c"'),
):
    rc, _ = check_hook(command, d)
    check(f"ignores {label}", rc == 0, f"exit={rc}")

# The same unparsed options still block once the subcommand is a real commit.
for label, command in (
    ("shell-variable -C before commit", 'git -C "$d" commit -m x'),
    ("unparsed --option before commit", "git --no-pager commit -m x"),
    ("-c config before commit", "git -c core.pager=cat commit -m x"),
    ("-c with its value before commit", "git -c x=y commit -m x"),
    # A command-scoped alias can rename commit, and its expansion is invisible
    # here, so an unknown subcommand behind one has to be refused.
    ("commit behind a command-scoped alias", "git -c alias.ci=commit ci -m x"),
    ("alias config with an unrelated subcommand", "git -c alias.st=status st"),
    ("config-env, whose value cannot be read", "git --config-env=alias.ci=E ci"),
    # An include reaches an alias through a file, so reading the config key is
    # not a way to tell a safe -c from a dangerous one.
    ("alias reachable through an include", "git -c include.path=/tmp/a ci -m x"),
    # The cost of that: -c in front of a subcommand this hook cannot identify is
    # refused even when it only sets a pager.
    ("plain -c before a read-only subcommand", "git -c core.pager=cat log -1"),
    # Unquoted, the value word-splits and the later words are git's own
    # arguments, so a commit can ride in behind an apparently read-only verb.
    ("unquoted -C expansion before a read-only subcommand", "git -C $d log"),
    ("unquoted attached -C expansion", "git -C$d log"),
    # Quoted on one half only: the unquoted half still splits, so "looks
    # quoted" is not the test — an expansion outside quotes is.
    ("partly quoted -C expansion", 'git -C "$base"$d log'),
    ("command substitution outside quotes", "git -C $(pwd) log"),
    # Any splittable token ahead of the subcommand does it, not just a -C value.
    ("unquoted expansion as the option itself", "git --$opts log"),
    ("unquoted expansion between options", "git --no-pager $flags log"),
    # A quoted expansion adds no words but can still be the subcommand itself.
    ("quoted expansion as the subcommand", 'git "$cmd" -m x'),
    ("command substitution as the subcommand", 'git "$(printf commit)" -m x'),
    ("unquoted expansion as the subcommand", "git $cmd -m x"),
    # Quoted, and still several words: one per element.
    ("quoted array expansion", 'args=(/repo commit -m x --); git -C "${args[@]}" log'),
    # Every modified form still expands to one word per element.
    ("array expansion with an offset", 'args=(/repo commit -m x --); git -C "${args[@]:0}" log'),
    ("array expansion with suffix removal", 'args=(/repo commit -m x --); git -C "${args[@]%x}" log'),
    ("array expansion with a replacement", 'args=(/repo commit -m x --); git -C "${args[@]/a/b}" log'),
    ("array indices expansion", 'args=(/repo commit -m x --); git -C "${!args[@]}" log'),
    ("quoted positional parameters", 'git -C "$@" log'),
    ("quoted braced positional parameters", 'git -C "${@}" log'),
    # git accepts a separate value for its long options, verified against the
    # binary for --git-dir, --work-tree and --namespace, so the token after an
    # unrecognised one is not necessarily the subcommand.
    ("long option with a separate value then commit", "git --git-dir /repo/.git commit -m x"),
    ("long option with a separate value then a read-only verb", "git --work-tree /repo log"),
):
    rc, _ = check_hook(command, d)
    check(f"blocks {label}", rc == 2, f"exit={rc}")

# An unparseable quote blocks only after the full token stream has located an
# actual git commit invocation, including a shell builtin prefix or a later line.
malformed_commit_repo = repo({"README.md": "# hello\n"})
for label, command in (
    ("command-prefixed malformed commit", 'command git commit "'),
    ("newline-separated malformed commit", 'echo prepared\ngit commit "'),
):
    rc, _ = check_hook(command, malformed_commit_repo)
    check(f"blocks {label}", rc == 2, f"exit={rc}")

# A Bash line continuation joins `git` and `commit` into one command.
continued_commit_repo = repo({"config.txt": f"{GITHUB}\n"})
rc, _ = check_hook("git \\\ncommit -m x", continued_commit_repo)
check("line-continuation commit scans the staged credential", rc == 2, f"exit={rc}")

for label, command in (
    ("env prefix", "env git commit -m x"),
    # A keyword introduces the command; the git after it is still a command.
    ("commit after an if keyword", "if git commit -m x; then echo ok; fi"),
    ("commit inside a for body", "for d in a b; do git -C \"$d\" commit -m x; done"),
    ("commit after then", "if true; then git commit -m x; fi"),
    ("commit after a negation", "! git commit -m x"),
    ("commit behind the time keyword", "time git commit -m x"),
    ("commit behind time -p", "time -p git commit -m x"),
    # A value that can add words can add -a, which commits unstaged tracked files.
    ("multiword expansion as a commit option value", 'args=(msg -a); git commit -m "${args[@]}"'),
    ("absolute env prefix", "/usr/bin/env git commit -m x"),
    ("env -i prefix", "env -i git commit -m x"),
    ("env --ignore-environment prefix", "env --ignore-environment git commit -m x"),
):
    rc, _ = check_hook(command, continued_commit_repo)
    check(f"{label} scans the staged credential", rc == 2, f"exit={rc}")

for label, command in (
    ("command -p prefix", "command -p git commit -m x"),
    ("env -u prefix", "env -u NAME git commit -m x"),
):
    rc, err = check_hook(command, continued_commit_repo)
    check(f"{label} is parsed, not refused", "could not safely parse" not in err, f"stderr={err.strip()[:160]}")
    check(f"{label} scans the staged credential", rc == 2 and "GitHub token" in err, f"exit={rc} stderr={err.strip()[:160]}")

# --- a commit reached through a group, a function, or a substitution --------
# A brace group runs where it stands, and a call runs its function's body with
# the call's words in place of "$@" and $1..$9. Each of these names the
# credential, so the commit was found and scanned rather than refused unread.
for label, command in (
    ("commit inside a brace group", "{ git commit -m x; }"),
    ("commit inside a nested brace group", "{ { git commit -m x; } }"),
    ("commit through a wrapper that forwards its arguments", 'g() { git "$@"; }; g commit -m x'),
    ("commit inside a called function", "f() { git add -A && git commit -m wip; }; f"),
    ("commit in a body defined over several lines", "f()\n{\n  git commit -m x\n}\nf"),
    ("commit in a function-keyword body", "function f { git commit -m x; }; f"),
    # "$1" standing where the subcommand goes is refused unread unless the call's
    # word is put in its place.
    ("commit through positional parameters", 'c() { git "$1" -m "$2"; }; c commit msg'),
    ("commit through two wrappers", 'a() { git "$@"; }; b() { a commit "$@"; }; b -m x'),
    # `command` inside the body reaches the real git, not the function again.
    ("commit through a function named git", 'git() { command git "$@"; }; git commit -m x'),
    ("commit through a wrapper behind time", 'g() { git "$@"; }; time g commit -m x'),
    # `}` closes a body after fi as well as after a separator; after an ordinary
    # word it is only an argument.
    ("commit in a body closed straight after fi", "f() { if true; then git commit -m x; fi }; f"),
    ("commit after a brace that is only an argument", "f() { echo }; git commit -m x; }; f"),
    # Leaning the other way: a `}` that is only an argument still ends the body,
    # so what follows it is read as though it ran even with no call.
    ("commit after an argument brace, uncalled", "f() { echo }; git commit -m x; }"),
    # A body that ends straight after `]]` must not swallow the commands after it.
    ("commit after a body closed by ]]", 'is_clean() { [[ -z "$(git status --porcelain)" ]] }\ngit add -A && git commit -m wip\nfunction cleanup { rm -f tmp; }'),
    # A heredoc's prose is parsed as commands, and its braces must not pair with
    # real ones across a commit.
    ("commit between two heredocs of JavaScript", "cat > a.js <<'EOF'\nfunction init() {\n  if (!ready) { return }\n  start();\n}\nEOF\ngit add a.js && git commit -m init\ncat > b.js <<'EOF'\nmodule.exports = {\n  a: 1,\n};\nEOF"),
    ("commit after a body that holds a heredoc", "f() { cat <<EOF\n{\nEOF\n}\ngit commit -m x\ncat <<EOF\n}\nEOF"),
    ("commit through ${1}", 'c() { git "${1}" -m x; }; c commit'),
    # Unquoted, a parameter splits into words, and the words are what run.
    ("commit through an unquoted parameter", 'step() { echo ">> $1"; $1; }; step "git commit -m wip"'),
    ("commit through an empty unquoted parameter", 'c() { git $1 commit -m x; }; c ""'),
    # A function inside the body has positional parameters of its own.
    ("commit through a function defined inside another", 'outer() { inner() { git "$@"; }; inner commit -m x; }; outer status'),
    ("commit through a function-keyword function inside another", 'outer() { function inner { git "$@"; }; inner commit -m x; }; outer status'),
    # Inlining is bounded, but not so tightly that ordinary helper calls use it up.
    ("commit after sixteen helper calls", 'run() { "$@"; }; ' + "run true; " * 16 + "run git commit -m x"),
    ("commit through a slice of the arguments", 'in_repo() { git -C "$1" "${@:2}"; }; in_repo . commit -m x'),
    # The recursion bound is a depth, not a count: a wrapper called twenty times,
    # or one called after a recursive helper, is still inlined and scanned.
    ("commit through a wrapper on its twenty-first call", 'g() { git "$@"; }; ' + "g status; " * 20 + "g commit -m x"),
    ("commit through a wrapper after a recursive helper", 'f() { f; }; f; g() { git "$@"; }; g commit -m x'),
    # Depth counts one function inside its own body, not nesting in general.
    ("commit through nine nested wrappers", "".join(f'a{i}() {{ a{i + 1} "$@"; }}; ' for i in range(1, 9)) + 'a9() { git "$@"; }; a1 commit -m x'),
    # A body that goes on after a nested call keeps its own end in step, so the
    # recursion in it still stops at its depth instead of running to the call cap.
    ("commit through a wrapper after recursion with a call before it", 'f() { g; f; }; g() { :; }; f; h() { git "$@"; }; h commit -m x'),
    # A definition replaces an earlier one only where it certainly runs in this
    # shell. Everywhere else the earlier body may still be the one called.
    ("commit through a function shadowed only in a subshell", "f() { git commit -m x; }; ( f() { echo safe; } ); f"),
    ("commit through a function shadowed only in an untaken branch", "f() { git commit -m x; }; if false; then f() { echo safe; }; fi; f"),
    # The same, where the shadowing definition is not the first command inside.
    ("commit through a function shadowed later in an untaken branch", "f() { git commit -m x; }; if false; then :; f() { echo safe; }; fi; f"),
    ("commit through a function shadowed mid-subshell", "f() { git commit -m x; }; ( :; f() { echo safe; }; : ); f"),
    ("commit through a function shadowed only behind &&", "f() { git commit -m x; }; false && f() { echo safe; }; f"),
    ("commit through a function shadowed only in a pipeline", "f() { git commit -m x; }; f() { echo safe; } | cat; f"),
    ("commit through a function shadowed only by an uncalled one", "f() { git commit -m x; }; g() { f() { echo safe; }; }; false && g; f"),
    # And a git function defined only in a subshell leaves git itself to run.
    ("commit after a git function defined in a subshell", "( git() { :; } ); git commit -m x"),
    # Recursion is read several levels deep, where arguments can shift into
    # place: the second level of this one commits.
    ("commit reached at the second level of a recursion", 'f() { git "$1" -m x; f "$2" "$3"; }; f status commit'),
    ("commit through a wrapper after a recursive countdown", 'countdown() { [ "$1" -le 0 ] && return; countdown $(( $1 - 1 )); }; countdown 3; g() { git "$@"; }; g commit -m x'),
    # The rest of an assignment's word is still the assignment.
    ("commit behind an assignment glued to a substitution", "out=$(date)x git commit -m x"),
    # An assignment's substitution leaves the next word a command.
    ("commit behind an assignment's substitution", "out=$(date) git commit -m x"),
    ("commit inside an assignment's substitution", "x=$(git commit -m y)"),
):
    rc, err = check_hook(command, continued_commit_repo)
    check(f"{label} scans the staged credential", rc == 2 and "GitHub token" in err, f"exit={rc} stderr={err.strip()[:160]}")

# A clean index, so a refusal below cannot be a credential that was found.
plain = repo({"README.md": "# hello\n"})
# Seventy calls to a sixty-word body add more tokens than inlining may, so the
# calls after them are past the budget.
BUDGET_SPENT = "h() { : " + " ".join(f"w{i}" for i in range(60)) + "; }; " + "h; " * 70

# The wrapper gets the verdict its body would get written out, so what is
# refused inline is refused through the call too.
for label, command, reason in (
    ("a wrapper adding -c before a commit", 'GC() { git -c user.name=x "$@"; }; GC commit -q -m y', "could not safely parse"),
    ("a wrapper passed an unquoted -C expansion", 'g() { git "$@"; }; g -C $d log', "unquoted expansion"),
    # After `shift` the call's words no longer line up with $1 and "$@", so they
    # are left unresolved and the parse cannot identify the subcommand.
    ("a wrapper that shifts its arguments", 'f() { local r=$1; shift; git -C "$r" "$@"; }; f /repo commit -m x', "unquoted expansion"),
    ("a wrapper that resets its arguments with set --", 'f() { set -- commit -m x; git "$@"; }; f status', "unquoted expansion"),
    ("a wrapper that resets its arguments with set", 'f() { set commit -m x; git "$@"; }; f status', "unquoted expansion"),
    # A word that can split moves every parameter after it, so what lands in
    # "$2" or in a slice is unknown.
    ("a parameter after a word that can split", 'run_in() { git -C "$1" "$2"; }; run_in $d status', "could not safely parse"),
    ("a slice after a word that can split", 'f() { git "${@:2}"; }; f $x commit -m x', "unquoted expansion"),
    # A body that multiplies its arguments stops being inlined at the token
    # budget, and is then judged as a program name this hook cannot read.
    ("a wrapper that doubles its arguments", 'f() { f "$@" "$@"; }; f commit -m x', "program name this hook cannot read"),
    # Past the token budget a body is no longer read, but it may still not say
    # commit, and nothing it reaches through another function may either.
    ("a committing function called past the token budget", BUDGET_SPENT + 'c() { git commit -m x; }; c', "program name this hook cannot read"),
    ("a function reaching a commit through another, past the token budget", BUDGET_SPENT + 'g() { git commit -m x; }; c() { g; }; c', "program name this hook cannot read"),
):
    # Bounded, because an unbounded inliner does not fail this case: it hangs.
    rc, err = check_hook(command, plain, timeout=60)
    check(f"{label} is refused", rc == 2 and reason in err, f"exit={rc} stderr={err.strip()[:160]}")

# A program name this hook cannot read, followed by `commit` where git reads its
# subcommand. It may be git, carrying its own -C or -c, so there is nothing to
# scan: refused in a clean repository too, with a message that says to name git.
for label, command in (
    ("a variable naming git", "g=git; $g commit -m x"),
    ("a quoted variable naming git", '"$g" commit -m x'),
    ("a defaulted expansion naming git", "${GIT:-git} commit -m x"),
    ("a command substitution naming git", "$(echo git) commit -m x"),
    ("a substitution naming git, then a global option", "$(command -v git) -C . commit -m x"),
    ("a substitution glued to the rest of the name", '$(dirname "$x")/git commit -m x'),
    ("two substitutions forming the name", "$(a)$(b) commit"),
    ("a variable naming git, then a flag", "$g --no-pager commit -m x"),
):
    rc, err = check_hook(command, plain)
    check(f"{label} is refused", rc == 2, f"exit={rc}")
    check(f"{label} names the unreadable program", "program name this hook cannot read" in err, f"stderr={err.strip()[:160]}")

# Recursion is bounded: the hook must return, not inline forever.
try:
    rc, _ = check_hook("a() { b; }; b() { a; }; a commit -m x", plain, timeout=20)
    check("mutually recursive functions terminate", rc == 0, f"exit={rc}")
except subprocess.TimeoutExpired:
    check("mutually recursive functions terminate", False, "timed out")

# Recursion in a long command must stay cheap: it once ran on to the token
# budget, copying the token list at every call, and took 11 s here against the
# hook's 10 s timeout, where it fails open.
long_recursion = "echo " + " ".join(f"w{i}" for i in range(1500)) + "\na() { b; }; b() { a; }; a"
try:
    rc, _ = check_hook(long_recursion, plain, timeout=10)
    check("recursion in a long command finishes within the hook timeout", rc == 0, f"exit={rc}")
except subprocess.TimeoutExpired:
    check("recursion in a long command finishes within the hook timeout", False, "timed out")

# Many ordinary calls in a long command must stay cheap too: when each one
# copied the token list, 1500 of them took 18 s under bash 3.2.
many_calls = "echo " + " ".join(f"w{i}" for i in range(400)) + "\nh() { :; }; " + "h; " * 1500
try:
    rc, _ = check_hook(many_calls, plain, timeout=10)
    check("many calls in a long command finish within the hook timeout", rc == 0, f"exit={rc}")
except subprocess.TimeoutExpired:
    check("many calls in a long command finish within the hook timeout", False, "timed out")

# The token budget is what bounds functions that multiply their arguments in a
# cycle: each is only one deep in its own body, so the recursion bound lets all
# three through eight times over, and without the budget this ran past 30 s.
doubling_cycle = 'a() { b "$@" "$@"; }; b() { c "$@" "$@"; }; c() { a "$@" "$@"; }; a commit -m x'
try:
    rc, err = check_hook(doubling_cycle, plain, timeout=10)
    check("a cycle of doubling functions is refused within the hook timeout", rc == 2 and "program name this hook cannot read" in err, f"exit={rc} stderr={err.strip()[:160]}")
except subprocess.TimeoutExpired:
    check("a cycle of doubling functions is refused within the hook timeout", False, "timed out")

# --- honours git -C so the right repo is scanned ----------------------------
dirty = repo({"config.txt": f"{GITHUB}\n"})
clean = repo({"README.md": "# hello\n"})
rc, _ = check_hook(f"git -C {dirty} commit -m x", clean)
check("git -C scans the named repo", rc == 2, f"exit={rc}")

rc, err = check_hook(
    f"git commit -m safe && git -C {dirty} commit -m secret",
    clean,
)
check("multiple git commit segments are rejected", rc == 2, f"exit={rc}")
check("multiple commit rejection is explained", "single git commit" in err, f"stderr={err.strip()[:160]}")

# Command-supplied Git config must not be propagated into the guard's own Git
# process, where config keys such as diff.external can execute code.
config_repo = repo({"config.txt": f"{GITHUB}\n"})
config_command, config_marker = marker_command(config_repo, "command-config")
rc, _ = check_hook(f"git -c diff.external={config_command} commit -m x", config_repo)
check("command-supplied git -c is blocked", rc == 2, f"exit={rc}")
check("command-supplied diff.external is not executed", not config_marker.exists())

# Repository-local diff configuration and attributes are untrusted too. The
# fixed internal diff must disable both external diff and text conversion.
external_repo = repo({"config.txt": f"{GITHUB}\n"})
external_command, external_marker = marker_command(external_repo, "repo-external")
subprocess.run(
    ["git", "-C", external_repo, "config", "diff.external", str(external_command)],
    check=True,
)
rc, _ = check_hook("git commit -m x", external_repo)
check("credential still blocks with repository diff.external", rc == 2, f"exit={rc}")
check("repository diff.external is not executed", not external_marker.exists())

textconv_repo = repo(
    {".gitattributes": "config.txt diff=marker\n", "config.txt": f"{GITHUB}\n"}
)
textconv_command, textconv_marker = marker_command(textconv_repo, "repo-textconv")
subprocess.run(
    ["git", "-C", textconv_repo, "config", "diff.marker.textconv", str(textconv_command)],
    check=True,
)
rc, _ = check_hook("git commit -m x", textconv_repo)
check("credential still blocks with repository textconv", rc == 2, f"exit={rc}")
check("repository textconv is not executed", not textconv_marker.exists())

# A whitespace-containing -C value is one argument, not a truncated repo path.
space_parent = tempfile.mkdtemp(prefix="staged secret parent ")
space_repo = str(Path(space_parent, "repo with spaces"))
Path(space_repo).mkdir()
subprocess.run(["git", "-C", space_repo, "init", "-q"], check=True)
subprocess.run(["git", "-C", space_repo, "config", "user.email", "t@example.invalid"], check=True)
subprocess.run(["git", "-C", space_repo, "config", "user.name", "t"], check=True)
Path(space_repo, "config.txt").write_text(f"{GITHUB}\n")
subprocess.run(["git", "-C", space_repo, "add", "-A"], check=True)
rc, _ = check_hook(f'git -C "{space_repo}" commit -m x', clean)
check("quoted git -C path with whitespace is scanned", rc == 2, f"exit={rc}")

rc, err = check_hook('git -C "$repo" commit -m x', clean)
check("dynamic git -C path is blocked instead of mis-scanned", rc == 2, f"exit={rc}")
check("unsafe commit form explains the parse failure", "could not safely parse" in err, f"stderr={err.strip()[:160]}")

# --- a refusal must name the reason it was actually refused for -------------
# An unquoted expansion can carry extra words, so a command that never mentions
# commit still cannot be cleared -- but the old message called every one of
# these a "git commit command" and sent the reader looking for a commit that is
# not there. Refusal stays; only the advice changes, so each case below asserts
# BOTH that it is still blocked and that the message points at quoting.
for label, command in (
    ("read-only log behind an unquoted path", "repo=/tmp; git -C $repo log --oneline -1"),
    ("read-only status behind an unquoted path", "repo=/tmp; git -C $repo status --porcelain"),
    ("a git call inside a loop over unquoted words", "for d in a b; do git -C /tmp/$d status -s; done"),
    ("an expansion standing where the subcommand goes", "sub=log; git $sub --oneline -1"),
):
    rc, err = check_hook(command, clean)
    check(f"{label} is still refused", rc == 2, f"exit={rc}")
    check(f"{label} is not called a commit", "could not safely parse" not in err, f"stderr={err.strip()[:160]}")
    check(f"{label} advises quoting", "unquoted expansion" in err, f"stderr={err.strip()[:160]}")

# The same shape with the expansion quoted carries no extra words, so the
# subcommand is trustworthy and a read-only call must pass untouched.
rc, err = check_hook('repo=/tmp; git -C "$repo" status --porcelain', clean)
check("a quoted expansion leaves a read-only call alone", rc == 0, f"exit={rc} stderr={err.strip()[:160]}")

# A quoted expansion AS the subcommand is a different case: it cannot split,
# but it still resolves to a word this hook never sees, so it is refused -- and
# telling it to quote would send it in a circle. It keeps the parse message.
rc, err = check_hook('sub=log; git "$sub" --oneline -1', clean)
check("a quoted expansion as the subcommand is still refused", rc == 2, f"exit={rc}")
check("a quoted expansion as the subcommand is not told to quote", "unquoted expansion" not in err, f"stderr={err.strip()[:160]}")
check("a quoted expansion as the subcommand keeps the parse message", "could not safely parse" in err, f"stderr={err.strip()[:160]}")

# A real commit keeps the parse message: quoting is not the fix there. Both
# halves are asserted -- a message with exit 0 would be a hook that fails open.
rc, err = check_hook("dir=/tmp; git commit -F $dir/msg.txt", dirty)
check(
    "a commit whose -F cannot be resolved is blocked with the commit message",
    rc == 2 and "could not safely parse" in err,
    f"exit={rc} stderr={err.strip()[:160]}",
)

# --- the commit flag table must match git's own grammar ---------------------
# Every case below distinguishes "parsed, scanned, found the credential" from
# "refused to parse". Both exit 2, so exit code alone proves nothing.
for label, command in (
    ("-q", "git commit -q -m x"),
    ("--quiet", "git commit --quiet -m x"),
    # -u and -S carry an optional ATTACHED value. Reading the next token as
    # their value made -m the value and x a pathspec: an empty candidate that
    # scanned clean while git committed the staged credential. This case
    # exited 0 before the table was corrected.
    ("-u before -m", "git commit -u -m x"),
    ("-uall", "git commit -uall -m x"),
    ("--untracked-files before -m", "git commit --untracked-files -m x"),
    ("-S before -m", "git commit -S -m x"),
):
    rc, err = check_hook(command, dirty)
    check(f"{label} is parsed, not refused", "could not safely parse" not in err, f"stderr={err.strip()[:160]}")
    check(f"{label} still scans the staged credential", rc == 2, f"exit={rc}")

rc, _ = check_hook("git commit -q -m docs", clean)
check("a parsed flag does not block a clean diff", rc == 0, f"exit={rc}")

# Flags that change WHICH content is committed stay fail-closed, so widening
# the no-value list cannot quietly admit one.
for label, command in (
    ("-p", "git commit -p -m x"),
    ("--interactive", "git commit --interactive -m x"),
    # -e parses fine but would open $EDITOR against a shell with no TTY, so a
    # fast refusal beats a hung tool call.
    ("-e", "git commit -e -m x"),
    ("an unknown flag", "git commit --not-a-real-flag -m x"),
):
    rc, err = check_hook(command, dirty)
    check(f"{label} is still refused", rc == 2 and "could not safely parse" in err, f"exit={rc} stderr={err.strip()[:160]}")

# Working-tree diffs must not invoke repository-configured clean filters. The
# guard blocks these commit forms before content inspection instead.
filter_all_repo = repo({".gitattributes": "tracked.txt filter=marker\n", "tracked.txt": "clean\n"})
commit_seed(filter_all_repo)
filter_all_command, filter_all_marker = marker_command(filter_all_repo, "commit-all-clean-filter")
subprocess.run(
    ["git", "-C", filter_all_repo, "config", "filter.marker.clean", str(filter_all_command)],
    check=True,
)
Path(filter_all_repo, "tracked.txt").write_text(f"{GITHUB}\n")
rc, _ = check_hook("git commit -am x", filter_all_repo)
check("git commit -a blocks an active clean filter", rc == 2, f"exit={rc}")
check("git commit -a does not execute the clean filter", not filter_all_marker.exists())

filter_path_repo = repo({".gitattributes": "tracked.txt filter=marker\n", "tracked.txt": "clean\n"})
commit_seed(filter_path_repo)
filter_path_command, filter_path_marker = marker_command(filter_path_repo, "pathspec-clean-filter")
subprocess.run(
    ["git", "-C", filter_path_repo, "config", "filter.marker.clean", str(filter_path_command)],
    check=True,
)
Path(filter_path_repo, "tracked.txt").write_text(f"{GITHUB}\n")
rc, _ = check_hook("git commit tracked.txt -m x", filter_path_repo)
check("pathspec commit blocks an active clean filter", rc == 2, f"exit={rc}")
check("pathspec commit does not execute the clean filter", not filter_path_marker.exists())

# Attribute inspection must stay bounded as candidate counts grow. A PATH shim
# observes the real hook-to-Git process boundary and forwards every invocation.
batch_repo = repo({"first.txt": "clean\n", "second.txt": "clean\n"})
commit_seed(batch_repo)
Path(batch_repo, "first.txt").write_text(f"{GITHUB}\n")
Path(batch_repo, "second.txt").write_text("changed\n")
with tempfile.TemporaryDirectory() as wrapper_dir:
    count_file = Path(wrapper_dir, "check-attr.count")
    wrapper = Path(wrapper_dir, "git")
    real_git = shutil.which("git")
    wrapper.write_text(
        "#!/bin/bash\n"
        'for arg in "$@"; do\n'
        '  if [[ "$arg" == "check-attr" ]]; then\n'
        f"    printf 'call\\n' >> {shlex.quote(str(count_file))}\n"
        "    break\n"
        "  fi\n"
        "done\n"
        f'exec {shlex.quote(real_git)} "$@"\n'
    )
    wrapper.chmod(0o755)
    wrapper_env = dict(os.environ)
    wrapper_env["PATH"] = wrapper_dir + os.pathsep + wrapper_env["PATH"]
    rc, _ = check_hook("git commit -am x", batch_repo, env=wrapper_env)
    check_attr_calls = count_file.read_text().splitlines() if count_file.exists() else []
check("multiple candidates still block a credential", rc == 2, f"exit={rc}")
check("multiple candidates use one batch attribute query", len(check_attr_calls) == 1, f"calls={len(check_attr_calls)}")

# A parent-only signal must interrupt the hook's wait, reap the attribute child,
# and remove both hook-owned temporary files within the hook timeout.
termination_repo = repo({"tracked.txt": "clean\n"})
commit_seed(termination_repo)
Path(termination_repo, "tracked.txt").write_text("changed\n")
with tempfile.TemporaryDirectory() as wrapper_dir, tempfile.TemporaryDirectory() as hook_tmpdir:
    ready_file = Path(wrapper_dir, "check-attr.ready")
    child_pid_file = Path(wrapper_dir, "check-attr.pid")
    wrapper = Path(wrapper_dir, "git")
    real_git = shutil.which("git")
    wrapper.write_text(
        "#!/bin/bash\n"
        'for arg in "$@"; do\n'
        '  if [[ "$arg" == "check-attr" ]]; then\n'
        f"    printf '%s\\n' \"$$\" > {shlex.quote(str(child_pid_file))}\n"
        f"    touch {shlex.quote(str(ready_file))}\n"
        "    exec /bin/sleep 30\n"
        "  fi\n"
        "done\n"
        f'exec {shlex.quote(real_git)} "$@"\n'
    )
    wrapper.chmod(0o755)
    wrapper_env = dict(os.environ)
    wrapper_env["PATH"] = wrapper_dir + os.pathsep + wrapper_env["PATH"]
    wrapper_env["TMPDIR"] = hook_tmpdir
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -am x"}})
    proc = subprocess.Popen(
        ["/bin/bash", HOOK],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=termination_repo,
        env=wrapper_env,
        start_new_session=True,
    )
    proc.stdin.write(payload)
    proc.stdin.close()
    deadline = time.monotonic() + 5
    while (
        (not ready_file.exists() or not child_pid_file.exists())
        and proc.poll() is None
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    reached_attribute_query = ready_file.exists() and child_pid_file.exists()
    child_pid = int(child_pid_file.read_text()) if child_pid_file.exists() else None
    parent_exited = proc.poll() is not None
    if reached_attribute_query and not parent_exited:
        proc.terminate()
        try:
            proc.wait(timeout=2)
            parent_exited = True
        except subprocess.TimeoutExpired:
            parent_exited = False
    child_alive = False
    if child_pid is not None:
        try:
            os.kill(child_pid, 0)
            child_alive = True
        except ProcessLookupError:
            child_alive = False
    leftovers = list(Path(hook_tmpdir).glob("cc-staged-secret-*"))
    if not parent_exited:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
    elif child_alive:
        os.kill(child_pid, signal.SIGKILL)
check("termination reaches attribute inspection", reached_attribute_query)
check("parent-only SIGTERM exits the hook promptly", parent_exited)
check("parent-only SIGTERM reaps the attribute child", not child_alive)
check("termination removes candidate and attribute temp files", not leftovers, f"leftovers={len(leftovers)}")

# `commit -a` includes unstaged modifications to tracked files.
auto_repo = repo({"tracked.txt": "clean\n"})
commit_seed(auto_repo)
Path(auto_repo, "tracked.txt").write_text(f"{GITHUB}\n")
rc, _ = check_hook("git commit -am x", auto_repo)
check("git commit -a scans tracked unstaged changes", rc == 2, f"exit={rc}")

# A pathspec commit takes the named working-tree content and excludes staged
# changes outside that pathspec.
pathspec_repo = repo({"selected.txt": "clean\n", "other.txt": "clean\n"})
commit_seed(pathspec_repo)
Path(pathspec_repo, "selected.txt").write_text(f"{GITHUB}\n")
rc, _ = check_hook("git commit selected.txt -m x", pathspec_repo)
check("pathspec commit scans selected working-tree content", rc == 2, f"exit={rc}")

Path(pathspec_repo, "selected.txt").write_text("clean again\n")
Path(pathspec_repo, "other.txt").write_text(f"{GITHUB}\n")
subprocess.run(["git", "-C", pathspec_repo, "add", "other.txt"], check=True)
rc, _ = check_hook("git commit selected.txt -m x", pathspec_repo)
check("pathspec commit excludes staged changes outside pathspec", rc == 0, f"exit={rc}")

# --- fail-open contract -----------------------------------------------------
for label, payload in (
    ("empty object", "{}"),
    ("no command key", '{"tool_input": {"file_path": "/tmp/x"}}'),
    ("malformed", "not json at all"),
    ("empty stdin", ""),
):
    proc = subprocess.run(["/bin/bash", HOOK], input=payload, capture_output=True, text=True)
    check(f"fail-open: {label}", proc.returncode == 0, f"exit={proc.returncode}")

# --- not a git repository at all --------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    rc, _ = check_hook("git commit -m x", tmp)
    check("outside a repository passes", rc == 0, f"exit={rc}")

DISABLE_VAR = "CC_GUARD_DISABLE_STAGED_SECRET"
BLOCKING = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
SAFE = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la /tmp"}})
dirty = repo({"config.txt": f"{GITHUB}\n"})

# --- opt-out contract -------------------------------------------------------
fails += _optout.contract(HOOK, DISABLE_VAR, BLOCKING, SAFE, dirty)

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
