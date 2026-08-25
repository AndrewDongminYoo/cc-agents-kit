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


def check_hook(command, cwd, env=None):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        ["/bin/bash", HOOK], input=payload, capture_output=True, text=True, cwd=cwd, env=env
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
):
    rc, _ = check_hook(command, d)
    check(f"ignores {label}", rc == 0, f"exit={rc}")

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
WRAP = 'cd "$3" && cat "$1" | bash "$2"; echo "STATUS ${PIPESTATUS[0]} ${PIPESTATUS[1]}"'
HUGE = json.dumps(
    {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.sh", "content": "x" * 200_000}}
)
BLOCKING = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
SAFE = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la /tmp"}})
dirty = repo({"config.txt": f"{GITHUB}\n"})


def run_piped(payload, disabled, cwd):
    """Feed the hook over a real pipe. Returns (writer_status, hook_status, stdout, stderr)."""
    env = dict(os.environ)
    env.pop(DISABLE_VAR, None)
    if disabled:
        env[DISABLE_VAR] = "1"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(payload)
        tmp = fh.name
    try:
        proc = subprocess.run(
            ["/bin/bash", "-c", WRAP, "_", tmp, HOOK, cwd], capture_output=True, text=True, env=env
        )
    finally:
        os.unlink(tmp)
    lines = proc.stdout.splitlines()
    writer, hook = (int(x) for x in lines[-1].split()[1:3])
    return writer, hook, "\n".join(lines[:-1]), proc.stderr


# --- opt-out contract -------------------------------------------------------
# The opt-out is checked AFTER stdin is drained, on purpose. A hook that exits
# before reading leaves the harness writing to a closed pipe, so a *disabled*
# hook makes the tool call report an error. The large-payload case below pins
# that placement: it fails (writer killed by SIGPIPE, 141) if the check moves
# above the read.
for label, disabled, payload, want_exit in (
    ("opt-out on: staged secret passes", True, BLOCKING, 0),
    ("opt-out off: staged secret still blocks", False, BLOCKING, 2),
    ("opt-out on: unrelated input passes", True, SAFE, 0),
):
    _, hook_rc, _, _ = run_piped(payload, disabled, dirty)
    check(f"{label} (exit={hook_rc})", hook_rc == want_exit, f"want {want_exit}")

writer_rc, hook_rc, _, _ = run_piped(HUGE, True, dirty)
check(
    "disabled hook still drains a 200KB payload",
    writer_rc == 0 and hook_rc == 0,
    f"writer={writer_rc} hook={hook_rc}",
)

print("\nALL PASS" if not fails else f"\n{fails} FAILURES")
raise SystemExit(1 if fails else 0)
