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
    # Options alone leave the parameters in place; -o takes an option name.
    ("a wrapper that only sets options", 'f() { set -euo pipefail; git "$@"; }; f status'),
    ("a wrapper with a bare set -", 'f() { set -; git "$@"; }; f status'),
    # A closed group leaves later definitions certain again.
    ("a function redefined after a brace group", "{ :; }; f() { git commit -m x; }; f() { git status; }; f"),
    # unset -v removes a variable, never the function.
    ("a git function kept through unset -v", "git() { :; }; unset -v git; git commit -m x"),
    # A comment is not a command, and a # inside a word is not a comment.
    ("a commit only in a comment", "# git commit -m x"),
    ("a commit after a comment's semicolon", "echo hi # ; git commit -m x"),
    # A quoted brace is a word, so it does not end the body early.
    ("a definition with a quoted brace as an argument", 'f() { echo "}"; git commit -m x; }'),
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
    # "$@" keeps each word whole, and `git "commit -m x"` names no subcommand
    # git has; only an unquoted $@ splits it.
    ("a wrapper passed one word holding a commit", 'g() { git "$@"; }; g "commit -m x"'),
    ("a logging wrapper running a read-only command unquoted", 'run() { echo "+ $*"; $@; }; run "git status"'),
    ("a git wrapper passing an unquoted $* a read-only verb", "g() { git $*; }; g status"),
    # A quoted < or >, or one an expansion produced, is part of a word, never a
    # redirection, and `git "commit>x"` names no subcommand git has.
    ("a wrapper passed a quoted word holding a redirection", 'g() { git "$@"; }; g "commit>x"'),
    ("a wrapper passed an expansion holding a redirection", 'f() { g $1; }; g() { git "$@"; }; f "commit>x"'),
    ("a wrapper whose output is redirected", 'g() { git "$@"; }; g status >/dev/null 2>&1'),
    # "$*" joins the words into one, and `"git commit -m x"` is no program.
    ("a wrapper running its words joined by \"$*\"", 'run() { "$*"; }; run git commit -m x'),
    # `commit` after an unreadable program name is only judged where git would
    # read its subcommand; anything else is ordinary work.
    ("a program named by a variable", "$PYTHON script.py commit"),
    ("a program named by a variable, with -c", "\"$PY\" -c 'print(1)'"),
    ("a program named by a variable, with an option and its value", '"$EDITOR" --wait notes.txt'),
    # Only git's own options are assumed to take the next word as a value.
    ("a program named by a substitution, with an option before commit", "$(git rev-parse --show-toplevel)/scripts/check.sh --since HEAD~1 commit"),
    ("a variable naming git, then an option and its value", "g=git; $g --git-dir .git log --grep commit"),
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
    # Stepping over a redirection or exec still finds the real subcommand.
    ("git log after a redirection", "git >/dev/null log -1"),
    ("git log after a descriptor duplication", "git 2>&1 log -1"),
    ("a read-only git behind exec", "exec git status"),
    ("a read-only git behind exec -a", "exec -a g git log -1"),
    ("exec that only redirects", "exec 3>&1"),
    ("a read-only git after a quoted redirection target", 'git >"/tmp/out" status'),
    ("a search term after a quoted redirection target", 'git >"/tmp/out" log --grep commit'),
    ("a pathspec after a quoted redirection target", 'git >"/tmp/out" diff -- commit'),
    ("a clobber redirection on a read-only git", "git log -1 >| out.txt"),
    ("an &> redirection on a read-only git", "git log -1 &>/dev/null && echo ok"),
    ("&& straight before a redirection", "true &&>/dev/null git status"),
    ("exec with a redirection before a read-only program", "exec 3>&1 ls"),
    ("a {varname} descriptor redirection on a read-only git", "git {fd}>out log -1"),
    ("a read-only git behind exec -a with its name attached", "exec -afoo git log -1"),
    ("a redirection before a read-only git", "2>/dev/null git log -1"),
    ("a redirection with a separate target before a read-only git", "2> /dev/null git log -1"),
    ("a read-only git behind a cluster of exec's c and l", "exec -clc git status"),
    ("a read-only git past an exec function that may be unset", "exec() { :; }; unset -f exec; exec git status"),
    ("a separate <<- target on a read-only git", "git <<- EOF log -1\nEOF"),
    ("a command substitution target after a read-only git's subcommand", "git log -1 > $(echo f)"),
    ("a function without git given a process substitution target", 'g() { echo "$@"; }; g > >(cat) hi'),
    # A function may be named exec: defining it runs nothing, and calling it
    # runs its body, not the builtin.
    ("a function named exec, defined only", 'exec() { git commit -m x; }; echo defined'),
    ("a function named exec, called for a read-only verb", 'exec() { git "$@"; }; exec status'),
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

# Runners execute a program, not a same-named shell function. sudo may change
# repository/config context and xargs appends unknown input; their commits must
# be refused rather than cleared using the current index alone.
runner_repo = repo({"fixture.txt": f"{GITHUB}\n"})
runner_clean = repo({"fixture.txt": "clean\n"})
for prefix in (
    "nohup", "/usr/bin/nohup --", "nice", "nice -n 4", "nice --adjustment=4",
    "nice -10", "timeout 5", "timeout -s TERM -k 1 5", "timeout --foreground 5",
    "nohup nice -n 4 timeout 5", "exec nohup",
):
    for directory, expected in ((runner_repo, 2), (runner_clean, 0)):
        rc, err = check_hook(prefix + " git commit -m fixture", directory)
        check(f"{prefix} scans the {'credential' if expected else 'clean'} candidate",
              rc == expected and (expected == 0 or "GitHub token" in err), f"exit={rc} stderr={err.strip()[:160]}")
for prefix in (
    "sudo", "sudo -u nobody --", "sudo -D /tmp", "sudo --chdir=/tmp",
    "echo fixture | xargs", "xargs -0 -r -n 1", "xargs --max-args=1 --",
    "xargs -I{}", "xargs -a input.txt", "xargs --arg-file=input.txt",
):
    rc, err = check_hook(prefix + " git commit -m fixture", runner_clean)
    check(f"{prefix} refuses an unknown commit context", rc == 2 and "could not safely parse" in err,
          f"exit={rc} stderr={err.strip()[:160]}")
for label, command in (
    ("runner prose", "echo nohup git commit -m fixture"),
    ("runner data argument", "nohup echo git commit -m fixture"),
    ("runner read-only command", "nice -n 4 git status"),
    ("sudo option value", "sudo -u git echo commit"),
    ("xargs option value", "xargs -a git echo commit"),
    ("sudo read-only command", "sudo -u nobody git log --grep commit"),
    ("xargs read-only command", "xargs -n 1 git log --grep commit"),
    ("runner function shadow", "nohup() { :; }; nohup git commit -m fixture"),
    ("defined git behind runner", "git() { git commit -m fixture; }; nohup git status"),
):
    rc, err = check_hook(command, runner_repo)
    check(f"preserves {label}", rc == 0, f"exit={rc} stderr={err.strip()[:160]}")
for command in (
    "git() { :; }; nohup git commit -m fixture",
    "nohup() { :; }; unset -f nohup; nohup git commit -m fixture",
    "if false; then nice() { :; }; fi; nice git commit -m fixture",
    "function /usr/bin/nohup { :; }; unset -f /usr/bin/nohup; /usr/bin/nohup git commit -m fixture",
    "echo commit | xargs git",
):
    rc, err = check_hook(command, runner_repo)
    check("runner function uncertainty retains external fallback", rc == 2,
          f"exit={rc} stderr={err.strip()[:160]}")

# A substitution executes even when its output is a quoted argument or an
# assignment. Its quoting must be independent of the surrounding word.
substitution_commits = (
    ('quoted assignment', 'out="$(git commit -m fixture)"'),
    ('quoted argument', 'echo "prefix $(git commit -m fixture) suffix"'),
    ('inner quotes', 'out="$(git commit -m "inner message")"'),
    ('nested quotes', 'out="$(echo "$(git commit -m fixture)")"'),
    ('quoted function call', 'g() { git commit -m fixture; }; out="$(g)"'),
    ('after quoted assignment', 'out="$(date)" git commit -m fixture'),
    ('backtick assignment', 'out=`git commit -m fixture`'),
    ('quoted backticks', 'echo "before `git commit -m fixture` after"'),
    ('backtick function call', 'g() { git commit -m fixture; }; out=`g`'),
    ('dollar substitution in backticks', 'out=`echo $(git commit -m fixture)`'),
    ('nested escaped backticks', r'out=`echo \`git commit -m fixture\``'),
)
for label, command in substitution_commits:
    for directory, expected in ((runner_repo, 2), (runner_clean, 0)):
        rc, err = check_hook(command, directory)
        check(f"{label} scans the {'credential' if expected else 'clean'} candidate",
              rc == expected and (expected == 0 or "GitHub token" in err), f"exit={rc} stderr={err.strip()[:160]}")

# A case pattern's ')' ends the pattern, not its enclosing substitution.
# These commands are parsed only; both fixture repositories are disposable.
case_substitution_commits = (
    ('quoted case arm', 'echo "$(case x in x) git commit -m fixture;; esac)"'),
    ('case assignment', 'out="$(case x in x) git commit -m fixture;; esac)"'),
    ('quoted case pattern', 'echo "$(case x in "x") git commit -m fixture;; esac)"'),
    ('parenthesized case pattern', 'echo "$(case x in (x) git commit -m fixture;; esac)"'),
    ('second case arm', 'echo "$(case x in y) :;; x) git commit -m fixture;; esac)"'),
    ('nested case arms', 'echo "$(case x in x) case y in y) git commit -m fixture;; esac;; esac)"'),
    ('case subject substitution', 'echo "$(case "$(printf x)" in x) git commit -m fixture;; esac)"'),
    ('case pattern substitution', 'echo "$(case x in "$(printf x)") git commit -m fixture;; esac)"'),
    ('conditional case', 'echo "$(if true; then case x in x) git commit -m fixture;; esac; fi)"'),
    ('timed case', 'echo "$(time -p case x in x) git commit -m fixture;; esac)"'),
    ('subshell in case arm', 'echo "$(case x in x) (git commit -m fixture);; esac)"'),
    ('function in case arm', 'echo "$(case x in x) g() { git commit -m fixture; }; g;; esac)"'),
    ('unquoted case substitution', 'out=$(case x in x) git commit -m fixture;; esac)'),
    ('backtick case substitution', 'out=`case x in x) git commit -m fixture;; esac`'),
)
for label, command in case_substitution_commits:
    syntax = subprocess.run(['/bin/bash', '-n'], input=command, text=True, capture_output=True)
    check(f"{label} is valid Bash", syntax.returncode == 0, syntax.stderr)
    for directory, expected in ((runner_repo, 2), (runner_clean, 0)):
        rc, err = check_hook(command, directory)
        check(f"{label} scans the {'credential' if expected else 'clean'} candidate",
              rc == expected and (expected == 0 or "GitHub token" in err), f"exit={rc} stderr={err.strip()[:160]}")
for label, command in (
    ('case arm prose', 'echo "$(case x in x) printf "%s" "git commit -m fixture";; esac)"'),
    ('arguments after case substitution', 'echo "$(case x in x) printf x;; esac)" git commit -m fixture'),
    ('case words as arguments', 'echo "$(echo case; echo esac)" git commit -m fixture'),
    ('case after keyword argument', 'echo "$(echo then case x in x)" git commit -m fixture'),
    ('case keyword as pattern', 'echo "$(case case in x) :;; case) printf x;; esac)" git commit -m fixture'),
    ('quoted esac pattern', 'echo "$(case esac in "esac") printf x;; esac)" git commit -m fixture'),
    ('empty case', 'echo "$(case x in esac)" git commit -m fixture'),
):
    rc, err = check_hook(command, runner_repo)
    check(f"preserves {label}", rc == 0, f"exit={rc} stderr={err.strip()[:160]}")

for label, command in (
    ('single-quoted substitution', "echo '$(git commit -m fixture)'"),
    ('single-quoted backticks', "echo '`git commit -m fixture`'"),
    ('escaped dollar', r'echo "\$(git commit -m fixture)"'),
    ('escaped backticks', r'echo "\`git commit -m fixture\`"'),
    ('arguments after quoted substitution', 'echo "$(date)" git commit -m fixture'),
    ('arguments after backticks', 'echo `date` git commit -m fixture'),
    ('inner quoted prose', 'echo "$(printf "%s" "git commit -m fixture")"'),
    ('backtick quoted prose', 'echo `printf "%s" "git commit -m fixture"`'),
    ('uninvoked quoted function', 'g() { out="$(git commit -m fixture)"; }'),
):
    rc, err = check_hook(command, runner_repo)
    check(f"preserves {label}", rc == 0, f"exit={rc} stderr={err.strip()[:160]}")
for command in ('"$(command -v git)" commit -m fixture', '`which git` commit -m fixture'):
    rc, err = check_hook(command, runner_clean)
    check("refuses a program name produced by a substitution", rc == 2 and "program name this hook cannot read" in err,
          f"exit={rc} stderr={err.strip()[:160]}")

# The common last-word cat heredoc supplies data to its surrounding command.
# Apostrophes, quotes and backticks in that body must not corrupt shell state.
message_body = "A user's \"quoted\" note with `git` commit prose\n$GIT commit is documentation\n"
for prefix in ('git commit -m ', 'echo ', 'gh pr create --body '):
    command = prefix + '"$(cat <<\'EOF\'\n' + message_body + 'EOF\n)"'
    for directory, expected in ((runner_repo, 2 if prefix.startswith('git') else 0), (runner_clean, 0)):
        rc, err = check_hook(command, directory)
        check(f"quoted heredoc data for {prefix.strip()} preserves its candidate", rc == expected,
              f"exit={rc} stderr={err.strip()[:160]}")
for prefix in ('eval ', 'bash -c ', 'sh -c ', 'source '):
    command = prefix + '"$(cat <<\'EOF\'\n$GIT commit -m fixture\nEOF\n)"'
    rc, err = check_hook(command, runner_clean)
    check(f"{prefix.strip()} still reads executable heredoc output", rc == 2,
          f"exit={rc} stderr={err.strip()[:160]}")

# A quoted substitution in a global option cannot end the subcommand scan.
for command, expected in (
    ('git -C "$(pwd)" commit -m fixture', 2),
    ('git --git-dir="$(echo .git)" commit -m fixture', 2),
    ('git -C "$(pwd)" status', 0),
    ('git -C "$(pwd)""$(printf /child)" commit -m fixture', 2),
    ('echo "$(cat <<\'EOF\'\n$GIT commit -m x\nEOF\n)" | bash', 2),
    ('echo "$(cat <<\'EOF\' | sh\n$GIT commit -m x\nEOF\n)"', 2),
):
    rc, err = check_hook(command, runner_repo)
    check("substitution context preserves repository and execution boundaries", rc == expected,
          f"exit={rc} stderr={err.strip()[:160]}")

# Quoted message substitutions cannot hide later candidate-changing flags.
subst_auto_repo = repo({"tracked.txt": "clean\n"})
commit_seed(subst_auto_repo)
Path(subst_auto_repo, 'tracked.txt').write_text(f"{GITHUB}\n")
for tail, expected in (('', 0), (' -a', 2), (' tracked.txt', 2)):
    rc, err = check_hook('git commit -m "$(printf message)"' + tail, subst_auto_repo)
    check(f"message substitution preserves trailing candidate args {tail!r}", rc == expected,
          f"exit={rc} stderr={err.strip()[:160]}")

# Function argument collection stops at substitution boundaries. The words
# after a message substitution still belong to that call: losing -a or a
# pathspec would scan the empty index instead of tracked worktree changes.
for wrapper, invocation in (
    ('g() { git commit "$@"; }; ', 'g -m '),
    ('g() { git commit -m "$1" "$2"; }; ', 'g '),
):
    for message in ('"$(printf message)"', '"`printf message`"', '`printf message`'):
        for tail in (' -a', ' tracked.txt'):
            command = wrapper + invocation + message + tail
            rc, err = check_hook(command, subst_auto_repo)
            check("function substitutions retain candidate-changing trailing arguments",
                  rc == 2 and "Blocked:" in err, f"exit={rc} stderr={err.strip()[:160]}")
for command in (
    'g() { echo "$@"; }; g "$(printf message)" -a',
    'g() { git -C "$1" status; }; g "$(pwd)"',
):
    rc, err = check_hook(command, runner_repo)
    check("unplaced substitution arguments preserve non-committing function bodies",
          rc == 0, f"exit={rc} stderr={err.strip()[:160]}")

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
    # Nor does a quoted or escaped brace open a group inside it, which would let
    # the body's real close pair with that and run on past the commit.
    ("commit after a body holding a quoted brace", 'f() { if "{"; then :; fi; }; git commit -m x; echo "}"'),
    ("commit after a body holding an escaped brace", 'f() { if \\{; then :; fi; }; git commit -m x; echo \\}'),
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
    ("commit through an unquoted $@", 'run() { echo "+ $*"; $@; }; run "git commit -m x"'),
    ("commit through an unquoted slice", 'f() { git ${@:2}; }; f x "commit -m y"'),
    ("commit through an unquoted $*", 'run() { echo "+ $*"; $*; }; run git commit -m x'),
    ("commit through an unquoted ${*}", 'run() { ${*}; }; run "git commit -m x"'),
    # A redirection is removed before the call's words become its parameters,
    # wherever it stands, operator and target alike.
    ("commit through a wrapper after a redirection", 'g() { git "$@"; }; g > /dev/null commit -m x'),
    ("commit through a wrapper after an attached redirection", 'g() { git "$@"; }; g >/dev/null commit -m x'),
    ("commit through a wrapper after a duplicated descriptor", 'g() { git "$@"; }; g 2>&1 commit -m x'),
    ("commit through a wrapper after a redirection to an expansion", 'g() { git "$@"; }; g >"$log" commit -m x'),
    ("commit through a wrapper with a redirection glued to a word", 'g() { git "$@"; }; g commit>/dev/null -m x'),
    ("commit through a wrapper followed by redirections", 'g() { git "$@"; }; g commit -m x >/dev/null 2>&1'),
    ("commit through git past a redirection, its definition uncertain", '( git() { :; } ); git >/dev/null commit -m x'),
    # An expanded name given to unset may be any function's.
    ("commit through git after an expanded unset -f", 'git() { :; }; x=git; unset -f "$x"; git commit -m x'),
    ("commit through git after an unquoted expanded unset", 'git() { :; }; x=git; unset $x; git commit -m x'),
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
    # A newline after && or || continues the command, so the definition on the
    # next line is still conditional; a comment before that newline too.
    ("commit through a function shadowed after && and a newline", "f() { git commit -m x; }; false &&\nf() { echo safe; }; f"),
    ("commit through a function shadowed after && and a comment", "f() { git commit -m x; }; false && # why\nf() { echo safe; }; f"),
    # A function-shaped line in a heredoc is text, not a definition.
    ("commit through a function shadowed only in heredoc text", "f() { git commit -m x; }; cat <<'EOF'\nf() { echo safe; }\nEOF\nf"),
    # A brace group can be conditional, backgrounded or piped.
    ("commit through a function shadowed in a conditional group", "f() { git commit -m x; }; false && { :; f() { echo safe; }; }; f"),
    ("commit through a function shadowed in a piped group", "f() { git commit -m x; }; { :; f() { echo safe; }; } | cat; f"),
    # unset removes the function, and the program of that name runs instead.
    ("commit after a git function is unset with -f", "git() { :; }; unset -f git; git commit -m x"),
    ("commit after a git function is unset by name", "git() { :; }; unset git; git commit -m x"),
    ("commit after a git function is unset through builtin", "git() { :; }; builtin unset -f git; git commit -m x"),
    # A trailing comment is not a pathspec: read as one, it made the scan look
    # at files the commit never takes, and let the staged ones through.
    ("commit with a trailing comment", "git commit -m x # note"),
    ("commit after a # inside a word", "echo a#b $#; git commit -m x"),
    # The comment ends at its newline, which still separates the next command.
    ("commit on the line after a comment", "echo start # note\ngit commit -m x"),
    # A brace a call passes in is an expanded word inside the body, never a
    # reserved one, and a body never closes outside the region that holds it:
    # here the unmatched { of a heredoc line paired with the } that `g }`
    # copied into g's body, and the commit after the heredoc went unread.
    ("commit after a call that passes a brace", "g() { echo \"$@\"; }; g }; cat <<EOF\nfoo() {\nEOF\ngit commit -m x"),
    ("commit with an apostrophe in a trailing comment", "git commit -m x # don't forget"),
    # Recursion is read several levels deep, where arguments can shift into
    # place: the second level of this one commits.
    ("commit reached at the second level of a recursion", 'f() { git "$1" -m x; f "$2" "$3"; }; f status commit'),
    ("commit through a wrapper after a recursive countdown", 'countdown() { [ "$1" -le 0 ] && return; countdown $(( $1 - 1 )); }; countdown 3; g() { git "$@"; }; g commit -m x'),
    # The rest of an assignment's word is still the assignment.
    ("commit behind an assignment glued to a substitution", "out=$(date)x git commit -m x"),
    # An assignment's substitution leaves the next word a command.
    ("commit behind an assignment's substitution", "out=$(date) git commit -m x"),
    ("commit inside an assignment's substitution", "x=$(git commit -m y)"),
    # exec runs its words as a program, as command does, with its own options.
    ("commit behind exec", "exec git commit -m x"),
    ("commit behind exec -c", "exec -c git commit -m x"),
    ("commit behind exec -cl", "exec -cl git commit -m x"),
    ("commit behind exec -a and its name", "exec -a mygit git commit -m x"),
    ("commit behind exec --", "exec -- git commit -m x"),
    # A redirection before the subcommand is set up and removed by the shell,
    # target and all, so the word after it is still git's subcommand.
    ("commit after a redirection to /dev/null", "git >/dev/null commit -m x"),
    ("commit after a redirection with a separate target", "git > out.txt commit -m x"),
    ("commit after a descriptor duplication", "git 2>&1 commit -m x"),
    ("commit after an input redirection", "git </dev/null commit -m x"),
    ("commit after -C and a redirection", 'git -C . 2>/dev/null commit -m x'),
    # A word glued to a redirection is still a word: commit>x runs commit.
    ("commit glued to a redirection", "git commit>out.txt -m x"),
    ("commit through a function named exec", 'exec() { git "$@"; }; exec commit -m x'),
    # Several redirections can share a word, and the last one's target is the
    # next word: `2>err>` takes out.txt.
    ("commit after two redirections in one word", "git 2>err.txt> out.txt commit -m x"),
    ("commit after >& with a separate target", "git >& out.txt commit -m x"),
    ("commit after -C glued to a redirection", "git -C.>/dev/null commit -m x"),
    # >| is the clobber redirection, and its target is a word like any other.
    ("commit after a clobber redirection", "git >| out.txt commit -m x"),
    ("commit after a glued clobber redirection", "git >|out.txt commit -m x"),
    # &> and &>> redirect both streams; the & is not a background job.
    ("commit after an &> redirection", "git &>out.txt commit -m x"),
    ("commit after an &>> redirection with a separate target", "git &>> out.txt commit -m x"),
    ("commit after a {varname} descriptor redirection", "git {fd}>out commit -m x"),
    # A redirection before the program is removed and the rest read as usual.
    ("commit after exec and a redirection", "exec 3>&1 git commit -m x"),
    ("commit after a redirection before git", ">/dev/null git commit -m x"),
    ("commit after a redirection straight after &&", "true &&>/dev/null git commit -m x"),
    ("commit after a redirection with a separate target before git", "2> /dev/null git commit -m x"),
    ("commit after a program glued to a redirection", "git>/dev/null commit -m x"),
    ("commit behind exec -a with its name attached", "exec -afoo git commit -m x"),
    ("commit behind exec -la with its name attached", "exec -lafoo git commit -m x"),
    ("commit behind exec -a with an attached name ending in a", "exec -afooa git commit -m x"),
    ("commit behind a cluster of exec's c and l", "exec -clc git commit -m x"),
    ("commit behind a long cluster ending in an attached name", "exec -lllclcafoo git commit -m x"),
    ("commit behind exec past an exec function that may be unset", "exec() { :; }; unset -f exec; exec git commit -m x"),
    ("commit after a separate <<- target", "git <<- EOF commit -m x\nEOF"),
    ("commit after a separate <<- target before git", "<<- EOF git commit -m x\nEOF"),
    # A function's arguments lose their redirections too, so none narrows the scan to a path.
    ("commit through a function with an &> redirection", 'g() { git "$@"; }; g commit -m x &>/dev/null'),
    ("commit through a function with a separate &> target", 'g() { git "$@"; }; g commit -m x &> /dev/null'),
    ("commit through a function with a separate >| target", 'g() { git "$@"; }; g commit -m x >| /dev/null'),
    ("commit through a function with a {varname} redirection", 'g() { git "$@"; }; g commit -m x {fd}>/dev/null'),
    ("commit through a function after a closed descriptor", 'g() { git "$@"; }; g 2>&- commit -m x'),
    ("commit after -C's glued path runs into an &> redirection", "git -C.&>/dev/null commit -m x"),
    # A redirection with a quoted part is still removed by bash, so the word
    # after it, or after its separate target, is the subcommand.
    ("commit after a quoted redirection target", 'git >"/tmp/out" commit -m x'),
    # command and builtin skip functions, so they reach the builtin exec even
    # when a function of that name exists.
    ("commit behind command exec past a function named exec", "exec() { :; }; command exec git commit -m x"),
    ("commit behind builtin exec past a function named exec", "exec() { :; }; builtin exec git commit -m x"),
):
    rc, err = check_hook(command, continued_commit_repo)
    check(f"{label} scans the staged credential", rc == 2 and "GitHub token" in err, f"exit={rc} stderr={err.strip()[:160]}")

# A clean index, so a refusal below cannot be a credential that was found.
plain = repo({"README.md": "# hello\n"})
# An uncertain git/exec function can have fallen back to the external program
# or builtin. Substitution redirections truncate the call words used to inline
# its body; those words must not silently clear the fallback as a non-commit.
uncertain_substitution_commands = (
    ("unset git with a process substitution", "git() { :; }; unset -f git; git > >(cat) commit -m x"),
    ("unset git with a command substitution", "git() { :; }; unset -f git; git > $(echo f) commit -m x"),
    ("unset git with a glued process target", "git() { :; }; unset -f git; git> >(cat) commit -m x"),
    ("unset git with a glued command target", "git() { :; }; unset -f git; git >$(echo f) commit -m x"),
    ("unset git with a target suffix", "git() { :; }; unset -f git; git >$(echo f).txt commit -m x"),
    ("unset git with a nested target", "git() { :; }; unset -f git; git > $(echo $(echo f)) commit -m x"),
    ("unset git with a target pipeline", "git() { :; }; unset -f git; git > >(cat | cat) commit -m x"),
    ("unset git with a target separator", "git() { :; }; unset -f git; git > >(cat; cat) commit -m x"),
    ("unset git with an alias after the target", "git() { :; }; unset -f git; git > >(cat) -c alias.ci=commit ci -m x"),
    ("unset git with alias config before the target", "git() { :; }; unset -f git; git -c alias.ci=commit > $(echo f) ci -m x"),
    ("unset git with -C before the target", "git() { :; }; unset -f git; git -C . > >(cat) commit -m x"),
    ("unset git with a target before -C", "git() { :; }; unset -f git; git > $(echo f) -C . commit -m x"),
    ("unset git with a target where -C takes its value", "git() { :; }; unset -f git; git -C > >(cat) . commit -m x"),
    ("unset git with a redirection after commit", "git() { :; }; unset -f git; git commit > $(echo f) -m x"),
    ("unset git with a glued program", "git() { :; }; unset -f git; git>$(echo f) commit -m x"),
    ("unset exec with git before a process target", "exec() { :; }; unset -f exec; exec git > >(cat) commit -m x"),
    ("unset exec with git before a command target", "exec() { :; }; unset -f exec; exec git > $(echo f) commit -m x"),
    ("unset exec with git after a process target", "exec() { :; }; unset -f exec; exec > >(cat) git commit -m x"),
    ("unset exec with git after a command target", "exec() { :; }; unset -f exec; exec > $(echo f) git commit -m x"),
    ("unset exec with an option cluster", "exec() { :; }; unset -f exec; exec -clc git > >(cat) commit -m x"),
    ("unset exec with a separate argv0", "exec() { :; }; unset -f exec; exec -a foo git > $(echo f) commit -m x"),
    ("unset exec with an attached argv0", "exec() { :; }; unset -f exec; exec -afoo git> >(cat) commit -m x"),
    ("unset exec with a target before argv0", "exec() { :; }; unset -f exec; exec > $(echo f) -a foo git commit -m x"),
    ("unset exec with an alias commit", "exec() { :; }; unset -f exec; exec git > >(cat | cat) -c alias.ci=commit ci -m x"),
    ("unset exec with a git-commit argv0", "exec() { :; }; unset -f exec; exec -a git-commit git > $(echo f) -m x"),
    ("git unset through an expanded name", 'git() { :; }; n=git; unset -f "$n"; git > >(cat) commit -m x'),
    ("git defined in an untaken branch", "if false; then git() { :; }; fi; git > $(echo f) commit -m x"),
)
for label, command in uncertain_substitution_commands:
    syntax = subprocess.run(["/bin/bash", "-n", "-c", command], capture_output=True, text=True)
    check(f"{label} has valid shell syntax", syntax.returncode == 0, syntax.stderr)
    for state, directory in (("staged credential", continued_commit_repo), ("clean index", plain)):
        rc, err = check_hook(command, directory)
        check(f"refuses {label} with a {state}", rc == 2 and "Blocked:" in err,
              f"exit={rc} stderr={err.strip()[:160]}")

# Read-only prefixes are identified by the regular git/exec parser, not by a
# search for a safe word that might instead be an option value or an argument.
for label, command in (
    ("certain git no-op", "git() { :; }; git > >(cat) commit -m x"),
    ("certain exec no-op", "exec() { :; }; exec git > $(echo f) commit -m x"),
    ("unset git log before a command target", "git() { :; }; unset -f git; git log -1 > $(echo f)"),
    ("unset git status before a process target", "git() { :; }; unset -f git; git status > >(cat)"),
    ("unset git log after ordinary redirection", "git() { :; }; unset -f git; git >/dev/null log -1 > $(echo f)"),
    ("unset git log after -C", 'git() { :; }; unset -f git; git -C "$d" log > >(cat)'),
    ("unset git log after --no-pager", "git() { :; }; unset -f git; git --no-pager log --grep commit > $(echo f)"),
    ("unset exec running echo", "exec() { :; }; unset -f exec; exec echo safe > $(echo f)"),
    ("unset exec redirecting before echo", "exec() { :; }; unset -f exec; exec > >(cat) echo safe"),
    ("unset exec running git log", "exec() { :; }; unset -f exec; exec git log -1 > $(echo f)"),
    ("unset exec with options running git log", "exec() { :; }; unset -f exec; exec -cl -a foo git log -1 > >(cat)"),
    ("read-only call followed by another command", "git() { :; }; unset -f git; git log > $(echo f); echo commit"),
):
    rc, err = check_hook(command, continued_commit_repo)
    check(f"preserves {label} with substitution redirection", rc == 0,
          f"exit={rc} stderr={err.strip()[:160]}")

# Words spelling read-only verbs do not clear unresolved subcommands.
for command in (
    "git() { :; }; unset -f git; git -C log > >(cat) commit -m x",
    "git() { :; }; unset -f git; git -c alias.log=commit log > $(echo f) -m x",
    'git() { :; }; unset -f git; verb=commit; git "$verb" > >(cat) -m x',
    "exec() { :; }; unset -f exec; exec -a git-commit git log > $(echo f)",
):
    rc, err = check_hook(command, plain)
    check("read-only words do not hide an unresolved committing fallback", rc == 2 and "Blocked:" in err,
          f"command={command} exit={rc} stderr={err.strip()[:160]}")

# A commit inside the target is read once, even if the outer git call is
# already recognized as read-only. Replaying the complete tail would count it
# twice and falsely reject its clean candidate.
rc, err = check_hook("git() { :; }; unset -f git; git log > $(git commit -m x; echo f)", plain)
check("a clean commit inside a read-only fallback target is counted once", rc == 0,
      f"exit={rc} stderr={err.strip()[:160]}")

# Seventy calls to a sixty-word body add more tokens than inlining may, so the
# calls after them are past the budget.
BUDGET_SPENT = "h() { : " + " ".join(f"w{i}" for i in range(60)) + "; }; " + "h; " * 70

# Exhausting the existing inlining budget must not skip the same unresolved
# external/builtin fallback. The function bodies themselves contain no git.
for label, command in (
    ("git process target", "git() { :; }; unset -f git; git > >(cat) commit -m x"),
    ("git command target", "git() { :; }; unset -f git; git > $(echo f) commit -m x"),
    ("exec process target", "exec() { :; }; unset -f exec; exec git > >(cat) commit -m x"),
    ("exec command target", "exec() { :; }; unset -f exec; exec git > $(echo f) commit -m x"),
):
    for state, directory in (("staged credential", continued_commit_repo), ("clean index", plain)):
        rc, err = check_hook(BUDGET_SPENT + command, directory)
        check(f"refuses uncertain {label} past the inlining budget with a {state}",
              rc == 2 and "Blocked:" in err, f"exit={rc} stderr={err.strip()[:160]}")
for command in (
    "git() { :; }; unset -f git; git log -1 > $(echo f)",
    "exec() { :; }; unset -f exec; exec git log -1 > >(cat)",
    "git() { :; }; git > >(cat) commit -m x",
    "exec() { :; }; unset -f exec; exec echo safe > $(echo f)",
):
    rc, err = check_hook(BUDGET_SPENT + command, continued_commit_repo)
    check("preserves safe substitution calls past the inlining budget", rc == 0,
          f"command={command} exit={rc} stderr={err.strip()[:160]}")

# The wrapper gets the verdict its body would get written out, so what is
# refused inline is refused through the call too.
for label, command, reason in (
    ("a wrapper adding -c before a commit", 'GC() { git -c user.name=x "$@"; }; GC commit -q -m y', "could not safely parse"),
    # A token does not record which of its > were quoted, so a -C value holding
    # one is not cut there: the path cannot be read, and the commit is refused.
    ("a -C path holding a quoted > before a redirection", 'git -C"/tmp/clean>dirty">/dev/null commit -m x', "could not safely parse"),
    # Nor is a redirection with a quoted part stepped over: a quoted > at its
    # end is part of a file name, not an operator waiting for a target.
    ("a redirection target ending in a quoted >", 'sink=out; git >"${sink}>" commit -m x', "could not safely parse"),
    # When the last > may be quoted, the next word may be git's own option
    # rather than a target, so a commit anywhere after it is refused.
    ("a quoted > before git's own options", 'sink=/tmp/out; git >"${sink}>" -C . commit -m x', "could not safely parse"),
    # Where a redirection is not followed, a commit after it is refused.
    # Run as git-commit, git commits whatever its arguments say.
    ("git run by exec under a git- name", "exec -a git-commit git -m x", "could not safely parse"),
    ("an alias commit after a redirection before git", ">/dev/null git -c alias.ci=commit ci -m x", "sets git configuration"),
    ("git run by exec under an attached git- name", "exec -agit-commit git -m x", "could not safely parse"),
    ("git run by exec under a git- name after a c and l cluster", "exec -clca git-commit git -m x", "could not safely parse"),
    ("git glued to a redirection run by exec under a git- name", "exec -a git-commit git>/dev/null -m x", "could not safely parse"),
    ("git run by exec under a git- name with a path", "exec -a /usr/libexec/git-core/git-commit /usr/bin/git -m x", "could not safely parse"),
    ("an expanded program run by exec under a git- name", 'g=/usr/bin/git; exec -a git-commit "$g" -m x', "could not safely parse"),
    ("a redirection where -C's path should be", "git -C >out . commit -m x", "could not safely parse"),
    ("a commit after a process substitution target", "git > >(cat) commit -m x", "could not safely parse"),
    # An operator inside the substitution does not end the command around it.
    ("a commit after a process substitution holding a pipe", "git > >(cat | cat) commit -m x", "could not safely parse"),
    ("a commit after a process substitution holding a ;", "git > >(cat; cat) commit -m x", "could not safely parse"),
    ("a commit after a process substitution holding &&", "git > >(cat && cat) commit -m x", "could not safely parse"),
    # Git's subcommand can be spelled many ways, so git itself is refused there.
    ("a read-only git after a process substitution target", "git > >(cat) log -1", "could not safely parse"),
    ("an alias commit after a process substitution target", "git > >(cat) -c alias.ci=commit ci -m x", "could not safely parse"),
    ("an alias commit after a redirection where -C's path should be", "git -C >/dev/null . -c alias.ci=commit ci -m x", "could not safely parse"),
    ("git after a process substitution target before the program", "> >(cat) git -c alias.ci=commit ci -m x", "could not safely parse"),
    ("git after exec -a whose name is a redirection", "exec -a >/dev/null git-commit git -m x", "could not safely parse"),
    ("a commit after a command substitution target", "git > $(echo f) commit -m x", "could not safely parse"),
    ("git after a command substitution target before the program", "> $(echo f) git commit -m x", "could not safely parse"),
    ("a commit through a function after a process substitution target", 'g() { git "$@"; }; g > >(cat) commit -m x', "unquoted expansion"),
    ("a commit through a function after a command substitution target", 'g() { git "$@"; }; g > $(echo f) commit -m x', "unquoted expansion"),
    ("git after a redirection and exec -a under a git- name", "exec >/dev/null -a git-commit git -m x", "could not safely parse"),
    ("git after a quoted redirection before the program", 'sink=/dev/null; >"${sink}>" git log -1', "could not safely parse"),
    ("git glued to a redirection whose target is the next word", "git> /dev/null commit -m x", "could not safely parse"),
    ("git glued to a command substitution target", "git>$(echo f) commit -m x", "could not safely parse"),
    # Among commit's own arguments, &> is refused as > always was.
    ("an &> redirection glued to commit", "git commit&>/dev/null -m x", "could not safely parse"),
    ("two redirections in one word with a quoted target", 'sink=/dev/null; git 2>"$sink"> /dev/null commit -m x', "could not safely parse"),
    # A word glued to a redirection whose target is the next word is not cut:
    # the target, here a file named commit, would be read as the subcommand.
    ("a -C value glued to a redirection with a separate target", "git -C.> commit commit -m x", "could not safely parse"),
    ("a wrapper passed an unquoted -C expansion", 'g() { git "$@"; }; g -C $d log', "unquoted expansion"),
    # After `shift` the call's words no longer line up with $1 and "$@", so they
    # are left unresolved and the parse cannot identify the subcommand.
    ("a wrapper that shifts its arguments", 'f() { local r=$1; shift; git -C "$r" "$@"; }; f /repo commit -m x', "unquoted expansion"),
    # Left unresolved, an unquoted $@ can split like any unquoted expansion,
    # whether git reads it or another call passes it on.
    ("a wrapper that shifts its arguments, unquoted", 'f() { shift; git $@; }; f x commit -m y', "unquoted expansion"),
    ("a wrapper that shifts and passes its arguments on, unquoted", 'f() { shift; g $@; }; g() { git -C "$1" "$2"; }; f x /repo commit', "could not safely parse"),
    ("a wrapper that shifts its arguments into a message, unquoted", 'f() { shift; git commit -m $@; }; f y x -a', "could not safely parse"),
    ("a wrapper that resets its arguments with set --", 'f() { set -- commit -m x; git "$@"; }; f status', "unquoted expansion"),
    ("a wrapper that resets its arguments with set", 'f() { set commit -m x; git "$@"; }; f status', "unquoted expansion"),
    # A bare - or +, and words after options, reset them too.
    ("a wrapper that resets its arguments with set -", 'f() { set - commit -m x; git "$1" "$2" "$3"; }; f status', "could not safely parse"),
    ("a wrapper that resets its arguments with set +", 'f() { set + commit -m x; git "$1" "$2" "$3"; }; f status', "could not safely parse"),
    ("a wrapper that resets its arguments after an option", 'f() { set -e commit -m x; git "$@"; }; f status', "unquoted expansion"),
    # After a bare -, even a word spelled like an option is a parameter, and a
    # bare -- clears them. Reading the call's words instead would pass a
    # pathspec the real commit never gets, and scan too little.
    ("a wrapper that resets its arguments to an option-like word", 'f() { set - --amend; git commit -m x "$@"; }; f -- other.txt', "could not safely parse"),
    ("a wrapper that clears its arguments", 'f() { set --; git commit -m x "$@"; }; f -- other.txt', "could not safely parse"),
    # A word that can split moves every parameter after it, so what lands in
    # "$2" or in a slice is unknown.
    ("a parameter after a word that can split", 'run_in() { git -C "$1" "$2"; }; run_in $d status', "could not safely parse"),
    ("a slice after a word that can split", 'f() { git "${@:2}"; }; f $x commit -m x', "unquoted expansion"),
    # An expansion passed to an unquoted parameter can split, however the call
    # quoted it, and so move every parameter of the call it is passed on to.
    ("an unquoted parameter given a quoted expansion", 'f() { g $1; }; g() { git -C "$1" "$2"; }; f "$x"', "could not safely parse"),
    # A command that mentions IFS may have changed how a parameter splits, so an
    # unquoted one is not resolved, and a literal holding commit is refused.
    ("a wrapper that changes IFS before an unquoted parameter", 'f() { IFS=:; git $1; }; f commit:-m:x', "unquoted expansion"),
    ("a wrapper that changes IFS before an unquoted $@", 'f() { IFS=X; git $@; }; f commitX-mXx', "unquoted expansion"),
    ("a wrapper that changes IFS and runs its parameter", 'f() { IFS=:; $1; }; f git:commit:-m:x', "unquoted expansion"),
    ("a wrapper that changes IFS and runs its parameter as the program", 'f() { IFS=:; $1 commit -m x; }; f env:git', "program name this hook cannot read"),
    # IFS is looked for as the shell reads the words, escapes and quotes removed.
    ("a wrapper naming IFS through escapes", 'g() { :; printf -v I\\F\\S :; git $1; }; g commit:-m:x', "unquoted expansion"),
    ("a wrapper naming IFS through quotes", 'g() { :; printf -v "I"FS :; git $1; }; g commit:-m:x', "unquoted expansion"),
    # A body that multiplies its arguments stops being inlined at the token
    # budget, and is then judged as a program name this hook cannot read.
    ("a wrapper that doubles its arguments", 'f() { f "$@" "$@"; }; f commit -m x', "program name this hook cannot read"),
    # Past the token budget a body is no longer read, but it may still not say
    # commit, and nothing it reaches through another function may either.
    ("a committing function called past the token budget", BUDGET_SPENT + 'c() { git commit -m x; }; c', "program name this hook cannot read"),
    ("a function reaching a commit through another, past the token budget", BUDGET_SPENT + 'g() { git commit -m x; }; c() { g; }; c', "program name this hook cannot read"),
    ("a function committing through a variable, past the token budget", BUDGET_SPENT + 'c() { "$GIT" commit -m x; }; c', "program name this hook cannot read"),
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
    # git's own options may take the next word as their value.
    ("a variable naming git, then an option and its value", "g=git; $g --git-dir .git commit -m x"),
    ("a variable naming git, then --work-tree and its value", "g=git; $g --work-tree . commit -m x"),
    ("a variable naming git, then --config-env and its value", "g=git; $g --config-env user.name=HOME commit -m x"),
):
    rc, err = check_hook(command, plain)
    check(f"{label} is refused", rc == 2, f"exit={rc}")
    check(f"{label} names the unreadable program", "program name this hook cannot read" in err, f"stderr={err.strip()[:160]}")

# A heredoc fed to a literal cat or tee is only written, so its body is not read
# as commands, and a line in it that names git through a variable is no refusal.
for label, command in (
    ("a script written through a heredoc", "cat > r.sh <<'X'\n$GIT commit -m release\nX"),
    ("a Makefile written through a heredoc", "cat > Makefile <<'X'\nrelease:\n\t$(GIT) commit -am rel\nX"),
    ("a script with -c written through a heredoc", "cat > s.sh <<'X'\ngit -c user.name=bot commit -m x\nX"),
    ("a script written through tee", "tee r.sh <<'X'\n$GIT commit -m release\nX"),
    ("a <<- body whose terminator is tab-indented", "cat > t.sh <<-'X'\n\t$GIT commit -m x\n\tX"),
    ("two heredocs opened on one line", "cat > a <<'A' > b <<\\B\n$GIT commit -m a\nA\n$GIT commit -m b\nB"),
    # bash reads the whole word as the delimiter, not its identifier prefix.
    ("a delimiter that is not an identifier", "cat > d.sh <<'A-B'\n$GIT commit -m x\nA-B"),
    # The skip is counted in characters, as the tokenizer reads them.
    # Those words only count at a command's start, not in a body's prose.
    ("a body whose prose names hash, enable and alias", "cat > m.txt <<'X'\nrecord the commit hash; enable it with an alias\n$GIT commit -m x\nX"),
    # The shape agents write: a variable, a directory, then the file.
    ("a file written after an assignment and mkdir", "S=/tmp/x\nmkdir -p \"$S\"\ncat > \"$S/m.txt\" <<'X'\n$GIT commit -m x\nX"),
    ("a multibyte body, then a read-only command", "cat > k.md <<'EOF'\n한국어 본문 예시\n$GIT commit -m x\nEOF\ngit status"),
):
    rc, err = check_hook(command, plain)
    check(f"{label} is not refused", rc == 0, f"exit={rc} stderr={err.strip()[:160]}")

# Anywhere the body can still run, it is read as commands as before, so the
# unreadable program name in it is refused. Each case holds one condition of
# the skip, and fails if that condition is dropped.
for label, command in (
    ("a heredoc fed to bash", "bash <<'X'\n$GIT commit -m x\nX"),
    ("a heredoc piped to sh", "cat <<'X' | sh\n$GIT commit -m x\nX"),
    ("a heredoc written into a process substitution", "cat <<'X' > >(sh)\n$GIT commit -m x\nX"),
    ("a heredoc written to a duplicated descriptor", "cat <<'X' >&3\n$GIT commit -m x\nX"),
    ("a heredoc inside a substitution that eval runs", "eval $(cat <<'X'\n$GIT commit -m x\nX\n)"),
    ("a heredoc fed to a function named cat", "cat() { bash; }; cat <<'X'\n$GIT commit -m x\nX"),
    ("a heredoc after PATH is changed", "PATH=/tmp/bin:$PATH; cat <<'X'\n$GIT commit -m x\nX"),
    ("a heredoc glued to its command word", "cat<<'X'\n$GIT commit -m x\nX"),
    ("a heredoc behind an assignment prefix", "LC_ALL=C cat <<'X'\n$GIT commit -m x\nX"),
    # No terminator means the parse may disagree with bash about where it ends.
    ("an unterminated heredoc", "cat > u.sh <<'X'\n$GIT commit -m x"),
    # An arithmetic shift is not a heredoc, and y is no delimiter.
    ("an arithmetic shift", "(( x << y ))\n$GIT commit -m x\ny"),
    # An unquoted delimiter leaves the body's substitutions to run, even for cat.
    ("a heredoc whose unquoted body substitutes a command", "cat > o.txt <<EOF\n$($GIT commit -m x)\nEOF"),
    # A group, loop or branch can pipe the whole body onward after its end.
    ("a heredoc inside a group piped to bash", "{\ncat <<'EOF'\n$GIT commit -m x\nEOF\n} | bash"),
    ("a heredoc inside a loop piped to sh", "for i in 1; do cat <<'EOF'\n$GIT commit -m x\nEOF\ndone | sh"),
    # exec can point the command's own output at a shell.
    ("a heredoc after exec redirects the output", "exec > >(bash)\ncat <<'EOF'\n$GIT commit -m x\nEOF"),
    # A body that is read may open a heredoc of its own, which then runs in the
    # outer body's context: substituted by an unquoted outer, or fed onward.
    ("a quoted heredoc inside an unquoted outer body", "cat <<OUTER\ncat <<'INNER'\n$($GIT commit -m x)\nINNER\nOUTER"),
    ("a quoted heredoc inside a body piped to bash", "bash <<'OUTER' | bash\ncat <<'INNER'\n$GIT commit -m x\nINNER\nOUTER"),
    # bash removes a backslash inside a double-quoted delimiter, so E\OF ends it.
    ("a double-quoted delimiter holding a backslash", 'cat <<"E\\\\OF"\nbody\nE\\OF\n$GIT commit -m x\nE\\\\OF'),
    # Quote state can drift from the shell's: a quote in a comment inside a
    # double-quoted substitution closes nothing for zsh or bash 5, which run
    # this body through eval, but it did close the string here.
    ("a heredoc inside a double-quoted substitution whose comment holds a quote", 'eval "$( # "\ncat <<\'Y\'\n$GIT commit -m x\nY\n)"'),
    # A backtick substitution is not tracked, so a heredoc inside one runs.
    ("a heredoc inside a backtick substitution that eval runs", "eval `\ncat <<'X'\n$GIT commit -m x\nX\n`"),
    # Only a prefix of plain words and separators is trusted, so even a closed
    # subshell before the heredoc keeps its body read.
    ("a heredoc after a subshell", "(true)\ncat > f.sh <<'X'\n$GIT commit -m x\nX"),
    # hash -p points cat at another program without a function, alias or PATH.
    ("a heredoc fed to cat after hash -p", "hash -p /bin/bash cat\ncat <<'X'\n$GIT commit -m x\nX"),
    # Mid-word, << is not an operator: here it is a default value, and the
    # command after it runs.
    ("a << inside a parameter expansion", 'cat ${v:-<<"X"}\n$GIT commit -m x\nX}'),
    # However hash is spelled or reached, it can repoint cat.
    ("a heredoc fed to cat after builtin hash", "builtin hash -p /bin/bash cat\ncat <<'X'\n$GIT commit -m x\nX"),
    ("a heredoc fed to cat after a quoted hash", "'hash' -p /bin/bash cat\ncat <<'X'\n$GIT commit -m x\nX"),
    ("a heredoc fed to cat after a hash named by a variable", "h=hash; $h -p /bin/bash cat\ncat <<'X'\n$GIT commit -m x\nX"),
    ("a << after a space inside a parameter expansion", "cat ${v:- <<'X'}\n$GIT commit -m x\nX}"),
    # A prefix word the hook does not read as a program keeps the body read.
    ("a heredoc in a negated group piped to bash", "! {\ncat <<'X'\n$GIT commit -m x\nX\n} | bash"),
    ("a heredoc fed to cat after time hash", "time hash -p /bin/bash cat\ncat <<'X'\n$GIT commit -m x\nX"),
    ("a heredoc fed to cat after a redirected hash", ">/dev/null hash -p /bin/bash cat\ncat <<'X'\n$GIT commit -m x\nX"),
    # cat<<B is a heredoc to the shell; left unnoted, it hides where its body
    # ends, and a later cat <<'C' inside it would look top-level.
    ("a heredoc after one glued to its command", "cat <<'A'; cat<<B\ndata\nA\ncat <<'C'\n$($GIT commit -m x)\nC\nB"),
    # PATH can be set by a builtin that names it, and zsh's rehash applies it.
    ("a heredoc fed to cat after read sets PATH", "read -r PATH <<< /tmp/evil; rehash; cat <<'X'\n$GIT commit -m x\nX"),
    ("a heredoc fed to cat after printf -v sets PATH", "printf -v PATH %s /tmp/evil\ncat <<'X'\n$GIT commit -m x\nX"),
    # zsh can autoload a function named cat from FPATH; only programs on a
    # short list may run before a skipped heredoc, and autoload is not one.
    ("a heredoc fed to cat after FPATH and autoload", "FPATH=/tmp/fns; autoload cat; cat <<'X'\n$GIT commit -m x\nX"),
    ("a heredoc fed to cat after autoload alone", "autoload cat\ncat <<'X'\n$GIT commit -m x\nX"),
    # A ${ opened after the heredoc on its line can span lines, and what runs
    # inside it is not a body.
    ("a parameter expansion spanning lines after the heredoc", "cat <<'X' ${v:-\n$($GIT commit -m x >&2)\nX\n}\nactual body\nX"),
    # A string that spans lines is where a drifted quote state shows, so a
    # heredoc after one is read even when, as here, nothing would run it.
    ("a heredoc after a string that spans lines", 'echo "a\nb"\ncat > f.sh <<\'X\'\n$GIT commit -m x\nX'),
):
    rc, err = check_hook(command, plain)
    check(f"{label} is still read and refused", rc == 2 and "program name this hook cannot read" in err, f"exit={rc} stderr={err.strip()[:160]}")

# What follows a skipped body is read from the right place, with a credential
# staged, so a commit there is scanned.
for label, command in (
    ("commit after a skipped body", "cat > a.txt <<'EOF'\nhello\nEOF\ngit commit -m x"),
    ("commit after a skipped multibyte body", "cat > k.md <<'EOF'\n한국어 본문입니다 — 예시\nEOF\ngit commit -m x"),
    ("commit after a skipped <<- body", "cat > t.txt <<-'EOF'\n\tbody\n\tEOF\ngit commit -m x"),
    ("commit after two skipped bodies", "cat > a <<'A' > b <<\"B\"\na\nA\nb\nB\ngit commit -m x"),
    ("commit after a line that only starts with the delimiter", "cat > a <<'EOF'\nEOFX\nEOF\ngit commit -m x"),
    ("commit on the line that opens the heredoc", "cat > a <<'EOF'; git commit -m x\nbody\nEOF"),
    ("commit after a delimiter that is not an identifier", "cat <<\\A-B\nx\nA-B\ngit commit -m x\nA"),
    ("commit after a here-string", "cat <<<EOF\ngit commit -m x"),
):
    rc, err = check_hook(command, continued_commit_repo)
    check(f"{label} scans the staged credential", rc == 2 and "GitHub token" in err, f"exit={rc} stderr={err.strip()[:160]}")

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

# Calls to the oldest name used to scan every later definition. Exercise
# lookup repeatedly with a bounded definition/token count: thousands of distinct
# definitions also measure Bash 3.2's indexed-array traversal, a separate cost.
# Check the real scan after all calls plus a clean control, so an early refusal
# cannot masquerade as an improvement. On Linux main takes 10.90 s; indexed
# lookup takes 3.12 s for the same 500 definitions and 3,000 calls.
distinct_functions = "".join(f"f{i}() {{ :; }};\n" for i in range(500))
lookup_workload = distinct_functions + "f0;\n" * 3000
for label, directory, expected in (("clean", plain, 0), ("credential", continued_commit_repo, 2)):
    try:
        rc, err = check_hook(lookup_workload + "git commit -m fixture", directory, timeout=10)
        check(f"3,000 calls among 500 definitions reach the {label} scan within 10 s",
              rc == expected and (expected == 0 or "GitHub token" in err), f"exit={rc}")
    except subprocess.TimeoutExpired:
        check(f"3,000 calls among 500 definitions reach the {label} scan within 10 s", False, "timed out")

# Indexing must retain exact names and all possibly active definitions. Unusual
# but valid Bash function names must not alias identifier/encoded names.
for label, command, expected in (
    ("punctuated name", "a-b() { git commit -m fixture; }; a-b", 2),
    ("distinct punctuation", "a-b() { git commit -m fixture; }; a_b() { :; }; a-b", 2),
    ("punctuated redefinition", "a-b() { git commit -m fixture; }; a-b() { :; }; a-b", 0),
    ("uncertain punctuated redefinition", "a-b() { git commit -m fixture; }; ( a-b() { :; } ); a-b", 2),
    ("unset git after many definitions", distinct_functions + "git() { :; }; unset -f git; git commit -m fixture", 2),
):
    rc, err = check_hook(command, continued_commit_repo)
    check(f"function index preserves {label}", rc == expected, f"exit={rc} stderr={err.strip()[:160]}")

# Imported variables must not seed the private name index or be interpreted as
# arithmetic. The marker is synthetic and the payload is never executed.
with tempfile.TemporaryDirectory() as tmp:
    marker = Path(tmp, "lookup-marker")
    for value in ("0", "000000008", "99999999999999999999999999999", f"a[$(touch {marker})]"):
        env = dict(os.environ, _cc_func_l_git=value, _cc_func_l_f=value)
        rc, err = check_hook("f() { :; }; git commit -m fixture", continued_commit_repo, env=env)
        check("imported function index cannot hide a commit", rc == 2 and "GitHub token" in err, f"exit={rc}")
    check("function lookup never evaluates imported index text", not marker.exists())

# The tokenizer reads bytes whatever the caller's locale, because under a
# multibyte one each character read walks the command from its start: this
# 22 KB command took 6 s under en_US.UTF-8 and 1 s under C.
UTF8 = dict(os.environ)
UTF8["LC_ALL"] = UTF8["LANG"] = "en_US.UTF-8" if os.uname().sysname == "Darwin" else "C.UTF-8"
long_line = "echo " + " ".join(f"word{i}" for i in range(2600))
try:
    rc, _ = check_hook(long_line, plain, env=UTF8, timeout=4)
    check("a long command under a UTF-8 locale finishes in bytes' time", rc == 0, f"exit={rc}")
except subprocess.TimeoutExpired:
    check("a long command under a UTF-8 locale finishes in bytes' time", False, "timed out")
# Reading bytes must not change what a multibyte command means.
for label, command in (
    ("commit whose message is multibyte", 'git commit -m "한국어 메시지 ✓"'),
    ("commit after a skipped multibyte body", "cat > k.md <<'EOF'\n한국어 본문입니다 — 예시\nEOF\ngit commit -m x"),
    ("commit after a multibyte word in a chain", 'echo "한글" && git commit -m x'),
):
    rc, err = check_hook(command, continued_commit_repo, env=UTF8)
    check(f"{label}, under a UTF-8 locale, scans the staged credential", rc == 2 and "GitHub token" in err, f"exit={rc} stderr={err.strip()[:160]}")

# Large input must still reach the real commit after it before the harness's
# 10 s timeout. A data-only heredoc can be skipped, but a body piped to node
# cannot, and a long quoted word used to spend 13 s in the per-byte loop on
# Linux. Assert the credential finding, not just exit 2 (also a syntax error).
large_js = "class Example {\n" + "".join(
    f"  method{i}() {{ return this.value + {i}; }}\n" for i in range(1400)
) + "}\n"
large_inputs = (
    ("61KB executable heredoc", "cat <<'EOF' | node\n" + large_js + "EOF\n"),
    ("60KB quoted word", 'echo "' + "x" * 60000 + '" >/dev/null\n'),
)
for locale in ("C", UTF8["LC_ALL"]):
    env = dict(os.environ, LC_ALL=locale)
    for label, prefix in large_inputs:
        try:
            rc, err = check_hook(prefix + "git commit -m fixture", continued_commit_repo, env=env, timeout=10)
            check(f"{label} reaches credential scan within 10 s under {locale}", rc == 2 and "GitHub token" in err, f"exit={rc} stderr={err.strip()[:160]}")
        except subprocess.TimeoutExpired:
            check(f"{label} reaches credential scan within 10 s under {locale}", False, "timed out")

# Put syntax at and around byte-window edges. The filler is an ordinary word,
# so it is read rather than skipped as a comment or a safe heredoc. Each form
# is checked both alone (prose must not commit) and before a genuine commit.
boundary_forms = (
    ("opening single quote", "echo 'text\ngit commit -m prose'", "'"),
    ("closing single quote", "echo 'text\ngit commit -m prose'", "prose'"),
    ("opening double quote", 'echo "text\ngit commit -m prose"', '"'),
    ("closing double quote", 'echo "text\ngit commit -m prose"', 'prose"'),
    ("escaped quote", 'echo "text \\"\ngit commit -m prose"', '\\"'),
    ("escaped newline", "echo gi\\\nt commit -m prose", "\\\n"),
    ("substitution opener", "echo $(printf git) commit -m prose", "$("),
    ("substitution closer", "echo $(printf git) commit -m prose", ")"),
    ("redirection operator", "echo text 2>&1", ">&"),
    ("heredoc operator", "cat > note.txt <<'EOF'\n$GIT commit -m prose\nEOF", "<<"),
    ("multibyte word", 'echo "한국어 ✓"', "한국어"),
)
for edge in (1023, 1024, 1025, 2047, 2048, 2049):
    for label, fragment, marker in boundary_forms:
        marker_pos = len(fragment[:fragment.index(marker)].encode())
        # Closing-quote markers include the preceding word to select the
        # second quote; position the quote itself, rather than that word.
        if label.startswith("closing"):
            marker_pos += len("prose")
        command = "echo " + "x" * (edge - len("echo ; ") - marker_pos) + "; " + fragment
        for suffix, expected in (("", 0), ("\ngit commit -m fixture", 2)):
            rc, err = check_hook(command + suffix, continued_commit_repo, env=UTF8)
            check(f"{label} at byte {edge}, {'commit' if suffix else 'prose'}", rc == expected and (expected == 0 or "GitHub token" in err), f"exit={rc} stderr={err.strip()[:160]}")

# Losing quote removal or backslash continuation at an edge must not hide a
# program/subcommand that really spells git commit. A multibyte pathspec must
# also survive splitting between the bytes of a character.
unicode_name = "한국어✓.txt"
unicode_commit_repo = repo({unicode_name: f"{GITHUB}\n"})
for edge in (1023, 1024, 1025):
    for label, fragment, marker, directory in (
        ("quoted program", '"gi"t commit -m fixture', '"', continued_commit_repo),
        ("escaped program", "g\\it commit -m fixture", "\\", continued_commit_repo),
        ("continued program", "gi\\\nt commit -m fixture", "\\\n", continued_commit_repo),
        ("escaped subcommand", "git co\\mmit -m fixture", "\\", continued_commit_repo),
        ("multibyte pathspec", f"git commit -m fixture -- '{unicode_name}'", unicode_name, unicode_commit_repo),
    ):
        marker_pos = len(fragment[:fragment.index(marker)].encode())
        command = "echo " + "x" * (edge - len("echo ; ") - marker_pos) + "; " + fragment
        rc, err = check_hook(command, directory, env=UTF8)
        check(f"{label} at byte {edge} scans the credential", rc == 2 and "GitHub token" in err, f"exit={rc} stderr={err.strip()[:160]}")

# Comment and safe-heredoc skips move the cursor beyond its current window;
# the next words must be read from their new position, with bytes unchanged.
for label, command in (
    ("long comment jump", "# " + "x" * 5000 + "\ngit commit -m fixture"),
    ("long skipped heredoc jump", "cat > note.txt <<'EOF'\n" + "x" * 5000 + "\nEOF\ngit commit -m fixture"),
    ("single-quoted multibyte span", "echo '" + "한글 ✓ " * 400 + "'\ngit commit -m fixture"),
):
    rc, err = check_hook(command, continued_commit_repo, env=UTF8)
    check(f"{label} reaches the credential scan", rc == 2 and "GitHub token" in err, f"exit={rc} stderr={err.strip()[:160]}")

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
